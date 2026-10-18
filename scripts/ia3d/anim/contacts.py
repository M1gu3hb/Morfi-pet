"""Contact solver: hands that really touch props, never through them, never in the air.

Runs inside Blender after rigmap.bake(). A clip may declare

  clip.contacts = [{"side": "R", "tip": "index.03.R", "target": "Prop_Tablet_Screen",
                    "local": (x, z), "frames": (f0, f1), "ramp": 6}, ...]
      a fingertip press: from f0 to f1 the pad of `tip` rests exactly on the target's front
      face (local -Y) at local (x, z) (None = the face centre, e.g. a calculator key).
      Between presses the finger hovers HOVER above the surface and comes straight down.
  clip.contacts = [{"side": "R", "touch": "head", "point": (x, y, z), "region": [groups],
                    "frames": (f0, f1), "ramp": 10}, ...]
      the hand touches Morfi himself (a palm on the cheek, a fist under the chin): `point` is a
      spot near the head / torso surface at rest; it rides with that bone, is projected on the
      deformed skin every frame, and the hand `region` (vertex groups of Hand_<side>) rests on it.
  clip.supports = [{"side": "L", "prop": "Prop_Calc", "frames": (a, b)}, ...]
      a prop resting on a palm: the hand is moved along the prop's normal until its upper
      surface touches the prop's back face (local +Y) with no overlap. The hand target is a
      child of the prop bone, so the hand then follows the prop wherever the action takes it.

solve() edits the baked hand_ik.<side> location curves; verify() measures every frame.
"""
import bpy
import numpy as np
from mathutils import Vector

from . import curves as C

HOVER = 0.015          # finger height above the surface between presses (m)
LEAD = 8               # frames to blend from the action's own path into the tapping path
ITER = 6               # Newton steps per frame (the hand moves rigidly with its IK target)
TOUCH_TOL = 0.0015     # |gap| accepted as touching a prop (m)
BODY_TOL = 0.003       # ... and Morfi's own soft skin (a fist under the chin, a palm on a cheek)
PEN_TOL = 0.0010       # overlap accepted (m): skin compresses a little
MAX_REACH = 1.08       # shoulder->wrist distance on IK, as a fraction of the rest arm length:
                       # Blender's IK stretch has no upper bound, so targets are pulled back to
                       # this (a cartoon reach, never a rubber arm). A clip may raise it a little
                       # (clip.max_reach) for a hand that reaches his own face
ARM_BONES = ("upper_arm", "forearm", "hand")


# ---------------------------------------------------------------- evaluation helpers
_FACED = {}


def _faced(ob):
    """Vertices used by a face (the AI hands were deleted faces-only: their loose vertices
    are invisible and must not count as body)."""
    if ob.name not in _FACED:
        m = np.zeros(len(ob.data.vertices), bool)
        idx = np.empty(len(ob.data.loops), int)
        ob.data.loops.foreach_get("vertex_index", idx)
        m[idx] = True
        _FACED[ob.name] = m
    return _FACED[ob.name]


def _eval_coords(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    P = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", P)
    ev.to_mesh_clear()
    P = P.reshape(-1, 3)
    M = np.array(ob.matrix_world)
    return P @ M[:3, :3].T + M[:3, 3]


def _group_mask(ob, names, thr=0.5):
    idx = {ob.vertex_groups[n].index for n in names if n in ob.vertex_groups}
    m = np.zeros(len(ob.data.vertices), bool)
    for v in ob.data.vertices:
        m[v.index] = any(g.group in idx and g.weight > thr for g in v.groups)
    return m


def _front_face(ob):
    """World point and outward normal of an object's front face (local -Y)."""
    ys = [v.co.y for v in ob.data.vertices]
    M = ob.matrix_world
    return M, min(ys), (M.to_3x3() @ Vector((0, -1, 0))).normalized()


def _tip_groups(spec):
    return tuple(spec["region"]) if "region" in spec else (spec["tip"],)


def _tip_mask(hand, spec):
    return _group_mask(hand, list(_tip_groups(spec)), 0.3 if "region" in spec else 0.5)


def _body_target(spec, body_name="Morfi_Body"):
    """Surface point and outward normal of Morfi's own head / torso nearest to the spec point
    (the point is given at rest and carried by the head or chest bone)."""
    from mathutils.bvhtree import BVHTree
    rig = bpy.data.objects["Morfi_Rig"]
    pb = rig.pose.bones["head" if spec["touch"] == "head" else "chest"]
    M = rig.matrix_world @ pb.matrix @ pb.bone.matrix_local.inverted()
    q = M @ Vector(spec["point"])
    body = bpy.data.objects[body_name]
    P = _eval_coords(body)
    tree = BVHTree.FromPolygons([tuple(v) for v in P], _body_parts(body)[spec["touch"]])
    loc, nrm, _, _ = tree.find_nearest(q)
    n = np.array(nrm)
    return np.array(loc), n / np.linalg.norm(n)


def _target_point(spec):
    if "touch" in spec:
        return _body_target(spec)
    ob = bpy.data.objects[spec["target"]]
    M, y0, n = _front_face(ob)
    x, z = spec.get("local") or (0.0, 0.0)
    return np.array(M @ Vector((x, y0, z))), np.array(n)


def _loc_curves(action, bone):
    path = f'pose.bones["{bone}"].location'
    return [action.fcurves.find(path, index=i) for i in range(3)]


def _get_loc(fcs, f):
    return np.array([fc.keyframe_points[f].co[1] for fc in fcs])


def _set_loc(fcs, f, v):
    for fc, x in zip(fcs, v):
        fc.keyframe_points[f].co[1] = float(x)


def _jacobian(rig, bone):
    """World displacement of the bone head per unit of its pose location."""
    pb = rig.pose.bones[bone]
    A = (pb.matrix @ pb.matrix_basis.inverted()).to_3x3()
    return np.array(rig.matrix_world.to_3x3() @ A)


class bones_only:
    """Evaluate the rig without deforming the meshes (fast frame_set for bone-only passes)."""

    def __enter__(self):
        self.saved = [(m, m.show_viewport) for ob in bpy.data.objects if ob.type == "MESH" for m in ob.modifiers]
        for m, _ in self.saved:
            m.show_viewport = False
        return self

    def __exit__(self, *exc):
        for m, v in self.saved:
            m.show_viewport = v


def _ik_curve(action, side):
    return action.fcurves.find(f'pose.bones["forearm.{side}"].constraints["ArmIK"].influence')


_REACH = {"limit": MAX_REACH}


def set_max_reach(limit=None):
    """Reach cap for the next solves (None = the default MAX_REACH)."""
    _REACH["limit"] = MAX_REACH if limit is None else float(limit)


def _clamp_frame(rig, fcs, side, f):
    """Pull the hand_ik target back within the reach cap of the shoulder at frame f (evaluated)."""
    up = rig.pose.bones[f"upper_arm.{side}"]
    reach = (up.bone.length + rig.pose.bones[f"forearm.{side}"].bone.length) * _REACH["limit"]
    M = rig.matrix_world
    s = np.array(M @ up.head)
    t = np.array(M @ rig.pose.bones[f"hand_ik.{side}"].head)
    d = np.linalg.norm(t - s)
    if d <= reach:
        return False
    delta = s + (t - s) * (reach / d) - t
    _set_loc(fcs, f, _get_loc(fcs, f) + np.linalg.solve(_jacobian(rig, f"hand_ik.{side}"), delta))
    _refresh(fcs)
    return True


def clamp_reach(rig, action, n):
    """Every IK frame of an action within MAX_REACH. Returns the number of frames pulled back."""
    from . import rigmap
    rigmap.assign(rig, action)
    fixed = 0
    with bones_only():
        for side in ("L", "R"):
            ik = _ik_curve(action, side)
            if ik is None:
                continue
            fcs = _loc_curves(action, f"hand_ik.{side}")
            for f in range(n):
                if ik.evaluate(f) < 0.01:
                    continue
                _frame(f)
                fixed += _clamp_frame(rig, fcs, side, f)
    return fixed


# ---------------------------------------------------------------- the body is solid
_BODY_PARTS = {}


def _body_parts(body):
    """Head and torso faces of the body (by skin weights), for nearest-surface queries."""
    if body.name not in _BODY_PARTS:
        gi = {g.name: g.index for g in body.vertex_groups}

        def mask(names, thr):
            idx = {gi[n] for n in names if n in gi}
            m = np.zeros(len(body.data.vertices), bool)
            for v in body.data.vertices:
                m[v.index] = sum(g.weight for g in v.groups if g.group in idx) >= thr
            return m
        parts = {}
        for key, names, thr in (("head", {"head"}, 0.95), ("torso", {"hips", "spine", "chest"}, 0.8)):
            m = mask(names, thr)
            polys = [p for p in body.data.polygons if all(m[i] for i in p.vertices)]
            if key == "torso":
                # the open hoodie has inward-facing lining panels a few cm under its outside: keep
                # the faces that look away from the spine, so inside / outside is decided right
                def outward(p):
                    c, nrm = p.center, p.normal
                    radial = Vector((c.x, c.y - 0.03, 0.0))
                    return radial.length < 1e-6 or nrm.dot(radial.normalized()) > 0.1
                polys = [p for p in polys if outward(p)]
            parts[key] = [tuple(p.vertices) for p in polys]
        _BODY_PARTS[body.name] = parts
    return _BODY_PARTS[body.name]


def _penetration(trees, H):
    """Deepest hand point inside the head / torso (m, > 0) and the surface normal there."""
    from mathutils.bvhtree import BVHTree  # noqa: F401  (trees are BVHTree)
    worst, normal = 0.0, None
    for tree in trees:
        for q in H:
            loc, nrm, _, d = tree.find_nearest(Vector(q))
            if loc is None or d > 0.03:
                continue
            if (Vector(q) - loc).dot(nrm) < 0 and d > worst:
                worst, normal = d, np.array(nrm)
    return worst, normal


def resolve_body(rig, action, n, body_name="Morfi_Body", margin=0.002, sides=("L", "R"), skip=()):
    """Hands never inside Morfi's own head or torso: on every IK frame where a hand goes in,
    its target is pushed out along the surface normal until it only touches (+ margin).
    A fist under the chin or a palm on the belly then rests on the surface."""
    from mathutils.bvhtree import BVHTree
    from . import rigmap
    rigmap.assign(rig, action)
    body = bpy.data.objects[body_name]
    parts = _body_parts(body)
    hands = {s: bpy.data.objects[f"Hand_{s}"] for s in ("L", "R")}
    curves = {s: (_ik_curve(action, s), _loc_curves(action, f"hand_ik.{s}")) for s in sides}
    fixed = 0
    for f in range(n):
        if any(a <= f <= b for a, b in skip):          # a press or a touch owns these frames
            continue
        active = [s for s, (ik, _) in curves.items() if ik is not None and ik.evaluate(f) > 0.01]
        if not active:
            continue
        for _ in range(3):
            _frame(f)
            P = _eval_coords(body)
            trees = [BVHTree.FromPolygons([tuple(p) for p in P], parts[k]) for k in ("head", "torso")]
            moved = False
            for s in active:
                depth, nrm = _penetration(trees, _eval_coords(hands[s])[::2])
                if depth <= 0.0005:
                    continue
                fcs = curves[s][1]
                w = max(curves[s][0].evaluate(f), 0.2)          # partial IK moves the hand less
                d = np.linalg.solve(_jacobian(rig, f"hand_ik.{s}"), nrm * (depth + margin) / w)
                _set_loc(fcs, f, _get_loc(fcs, f) + d)
                _refresh(fcs)
                moved = True
            if not moved:
                break
            fixed += 1
    return fixed


def _frame(f):
    bpy.context.scene.frame_set(f)
    bpy.context.view_layer.update()


def _refresh(fcs):
    for fc in fcs:
        fc.update()


# ---------------------------------------------------------------- presses
def _press_error(spec, hand, tip_mask):
    S, n = _target_point(spec)
    T = _eval_coords(hand)[tip_mask]
    d = (T - S) @ n
    dmin = d.min()
    pad = T[d < dmin + 0.002].mean(0)
    off = S - pad
    tangential = off - (off @ n) * n
    return tangential - dmin * n, n, dmin


def _touch_error(spec, hand, step=3, slide_gain=0.3):
    """Touching Morfi himself: the hand's closest point (true distance to the curved skin, not to
    a plane) goes onto the skin and nothing of the hand goes in; the contact slides towards the
    chosen spot. Returns (correction, normal at the contact, signed gap)."""
    from mathutils.bvhtree import BVHTree
    S, _ = _body_target(spec)
    body = bpy.data.objects["Morfi_Body"]
    tree = BVHTree.FromPolygons([tuple(v) for v in _eval_coords(body)], _body_parts(body)[spec["touch"]])
    best = (np.inf, None, None)
    for q in _eval_coords(hand)[::step]:
        loc, nrm, _, d = tree.find_nearest(Vector(q), 0.10)
        if loc is None:
            continue
        sd = d if (Vector(q) - loc).dot(nrm) >= 0 else -d
        if sd < best[0]:
            best = (sd, np.array(q), np.array(nrm))
    sd, q, n = best
    if q is None:
        raise RuntimeError(f"touch {spec}: the hand is more than 10 cm from the {spec['touch']}")
    n = n / np.linalg.norm(n)
    slide = S - q
    slide -= (slide @ n) * n
    return -sd * n + slide_gain * slide, n, sd


def _solve_press_frame(rig, fcs, bone, spec, hand, tip_mask, f):
    _frame(f)
    touch = "touch" in spec
    best = (np.inf, None)                  # a touch on his curved skin can overshoot: keep the best step
    for it in range(ITER + 2):
        if it >= ITER and not touch:
            break
        if touch:
            # slide towards the spot first, then two pure "rest on the skin" steps
            err, n, dmin = _touch_error(spec, hand, slide_gain=0.3 if it < ITER else 0.0)
            if abs(dmin) < best[0]:
                best = (abs(dmin), _get_loc(fcs, f))
        else:
            err, n, dmin = _press_error(spec, hand, tip_mask)
        if np.linalg.norm(err) < 2e-4:
            best = (np.inf, None)          # converged: nothing to restore
            break
        J = _jacobian(rig, bone)
        _set_loc(fcs, f, _get_loc(fcs, f) + np.linalg.solve(J, err))
        _refresh(fcs)
        _frame(f)
        if _clamp_frame(rig, fcs, spec["side"], f):     # out of reach: stop short, verify() says so
            _frame(f)
            break
    if touch and best[1] is not None:
        last = abs(_touch_error(spec, hand, slide_gain=0.0)[2])
        if last > best[0] + 5e-4:                       # the last step made it worse: go back
            _set_loc(fcs, f, best[1])
            _refresh(fcs)
            _frame(f)
    return n


def _dedup(pts):
    out = []
    for f, v in pts:
        if out and f <= out[-1][0]:
            continue
        out.append((f, v))
    return out


def _press_track(rig, action, clip, side, specs):
    """Rebuild hand_ik.<side> location: action path -> hover/press path -> action path.

    The path is a spline through hover / contact keys; the contact keys come from solving the
    pressed frames, so after a first build the pressed frames are solved again and the spline
    rebuilt from those exact contacts (the frames around a press then never dip below it)."""
    bone = f"hand_ik.{side}"
    fcs = _loc_curves(action, bone)
    hand = bpy.data.objects[f"Hand_{side}"]
    n_frames = clip.n
    orig = np.array([_get_loc(fcs, f) for f in range(n_frames)])
    masks = [_tip_mask(hand, spec) for spec in specs]
    contact, normals = [], []
    for spec, tip_mask in zip(specs, masks):
        f0, f1 = spec["frames"]
        normals.append(_solve_press_frame(rig, fcs, bone, spec, hand, tip_mask, f0))
        contact.append((_get_loc(fcs, f0), _get_loc(fcs, f0)))
    for _ in range(2):
        keys = []
        for spec, (L0, L1), nw in zip(specs, contact, normals):
            f0, f1 = spec["frames"]
            _frame(f0)
            hover = np.linalg.solve(_jacobian(rig, bone), nw * HOVER)
            r = spec.get("ramp", 6)
            keys += [(f0 - r, L0 + hover), (f0, L0), (f1, L1), (f1 + r, L1 + hover)]
        keys.sort(key=lambda k: k[0])
        tap = np.stack([C.keys(n_frames, [(f, v[i]) for f, v in keys]) for i in range(3)], 1)
        # the tap path owns the frames around each contact only (merged when contacts are close):
        # in a long performance the same hand also gestures between them on its own targets
        w = np.zeros(n_frames)
        for spec in specs:
            f0, f1 = spec["frames"]
            r = spec.get("ramp", 6)
            pts = [(f0 - r - LEAD, 0.0), (f0 - r, 1.0), (f1 + r, 1.0), (f1 + r + LEAD, 0.0)]
            pts = [(min(max(f, 0), n_frames - 1), v) for f, v in pts]
            if pts[0][0] > 0:
                pts = [(0, 0.0)] + pts
            if pts[-1][0] < n_frames - 1:
                pts = pts + [(n_frames - 1, 0.0)]
            w = np.maximum(w, C.keys(n_frames, _dedup(pts)))
        for i, spec in enumerate(specs[:-1]):         # bridge contacts that are close together
            gap = specs[i + 1]["frames"][0] - spec["frames"][1]
            if gap <= 2 * (spec.get("ramp", 6) + LEAD):
                w[spec["frames"][1]:specs[i + 1]["frames"][0] + 1] = 1.0
        track = orig * (1 - w[:, None]) + tap * w[:, None]
        for f in range(n_frames):
            _set_loc(fcs, f, track[f])
        _refresh(fcs)
        # exact contact on every pressed frame (the body breathes under the hand)
        contact = []
        for spec, tip_mask in zip(specs, masks):
            f0, f1 = spec["frames"]
            for f in range(f0, f1 + 1):
                _solve_press_frame(rig, fcs, bone, spec, hand, tip_mask, f)
            contact.append((_get_loc(fcs, f0), _get_loc(fcs, f1)))


def smooth_touches(rig, action, clip, win=5, max_step=0.015, iters=6):
    """A hand resting on Morfi is solved frame by frame; on his curved, breathing body the solver
    can land on a different spot from one frame to the next (a jittering hand). Median + mean
    filter the target over each touch, then let the hand rest on the skin again without sliding
    (each correction capped, so a nearest point on the wrong side never throws the hand)."""
    from . import rigmap
    rigmap.assign(rig, action)
    h = win // 2
    for spec in getattr(clip, "contacts", []):
        if "touch" not in spec:
            continue
        bone = f"hand_ik.{spec['side']}"
        fcs = _loc_curves(action, bone)
        hand = bpy.data.objects[f"Hand_{spec['side']}"]
        f0, f1 = spec["frames"]
        L = np.array([_get_loc(fcs, f) for f in range(f0, f1 + 1)])
        med = np.array([np.median(L[max(0, i - h):i + h + 1], 0) for i in range(len(L))])
        sm = np.array([med[max(0, i - h):i + h + 1].mean(0) for i in range(len(L))])
        for k, f in enumerate(range(f0, f1 + 1)):
            _set_loc(fcs, f, sm[k])
        _refresh(fcs)
        for f in range(f0, f1 + 1):
            _frame(f)
            for _ in range(iters):
                err, _n, sd = _touch_error(spec, hand, slide_gain=0.0)
                if abs(sd) < 3e-4:
                    break
                norm = np.linalg.norm(err)
                if norm > max_step:
                    err = err * (max_step / norm)
                _set_loc(fcs, f, _get_loc(fcs, f) + np.linalg.solve(_jacobian(rig, bone), err))
                _refresh(fcs)
                _frame(f)


def smooth_ik(rig, action, clip, sides=("L", "R"), sigma=1.8, ramp=5):
    """Every solver above corrects one frame at a time (reach, body, presses): side by side
    those corrections can zig-zag (a trembling hand). Low-pass each IK target and keep the
    contact frames exact, blending back to them over `ramp` frames."""
    from . import rigmap
    rigmap.assign(rig, action)
    k = int(3 * sigma) + 1
    g = np.exp(-0.5 * (np.arange(-k, k + 1) / sigma) ** 2)
    g /= g.sum()
    n = clip.n
    for side in sides:
        fcs = _loc_curves(action, f"hand_ik.{side}")
        L = np.array([_get_loc(fcs, f) for f in range(n)])
        P = np.pad(L, ((k, k), (0, 0)), mode="edge")
        S = np.stack([np.convolve(P[:, i], g, "valid") for i in range(3)], 1)
        m = np.zeros(n)
        for spec in getattr(clip, "contacts", []):
            if spec["side"] == side:
                f0, f1 = spec["frames"]
                m[max(0, f0):min(n, f1 + 1)] = 1.0
        soft = m.copy()
        for d in range(1, ramp + 1):
            w = 1.0 - d / (ramp + 1)
            soft[d:] = np.maximum(soft[d:], m[:-d] * w)
            soft[:-d] = np.maximum(soft[:-d], m[d:] * w)
        out = S * (1 - soft[:, None]) + L * soft[:, None]
        for f in range(n):
            _set_loc(fcs, f, out[f])
        _refresh(fcs)


def hold_prop(rig, action, bone, obj, side, frames, ref):
    """The prop rides in the hand. A prop parked in space makes the hand chase it (and tremble
    at the edge of its reach); a held prop goes wherever the hand goes. The grip is taken at
    `ref` (prop as posed there, moved onto the palm so it rests on it), then the prop bone
    follows hand.<side> on every frame of `frames`."""
    from mathutils import Matrix
    from . import rigmap
    rigmap.assign(rig, action)
    pb, hb = rig.pose.bones[bone], rig.pose.bones[f"hand.{side}"]
    W = rig.matrix_world
    hand = bpy.data.objects[f"Hand_{side}"]
    _frame(ref)
    T = W @ pb.matrix
    gap, nb = _support_gap({"prop": obj, "side": side}, hand)
    if gap is not None:                              # rest it on the palm: down by the gap
        T = Matrix.Translation(Vector(nb * gap)) @ T
    G = (W @ hb.matrix).inverted() @ T
    a, b = frames
    locs, rots = [], []
    for f in range(a, b + 1):
        _frame(f)
        sc = pb.scale.copy()
        pb.matrix = W.inverted() @ (W @ hb.matrix) @ G
        locs.append(pb.location.copy())
        q = pb.rotation_quaternion.copy()
        if rots and q.dot(rots[-1]) < 0:             # keep the quaternion on one side: no flips
            q.negate()
        rots.append(q)
        pb.scale = sc
    path = f'pose.bones["{bone}"]'
    n_all = int(bpy.context.scene.frame_end) + 1
    for attr, vals, count, rest in (("location", locs, 3, (0.0, 0.0, 0.0)),
                                    ("rotation_quaternion", rots, 4, (1.0, 0.0, 0.0, 0.0))):
        for i in range(count):
            fc = action.fcurves.find(f"{path}.{attr}", index=i) or action.fcurves.new(f"{path}.{attr}", index=i,
                                                                                      action_group=bone)
            old = [fc.evaluate(f) if len(fc.keyframe_points) else rest[i] for f in range(n_all)]
            for f, v in zip(range(a, b + 1), vals):
                if 0 <= f < n_all:
                    old[f] = v[i]
            fc.keyframe_points.clear()
            fc.keyframe_points.add(n_all)
            co = np.empty(2 * n_all)
            co[0::2] = np.arange(n_all, dtype=float)
            co[1::2] = old
            fc.keyframe_points.foreach_set("co", co)
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
            fc.update()
    _frame(ref)
    gap2, _ = _support_gap({"prop": obj, "side": side}, hand)
    return gap, gap2


# ---------------------------------------------------------------- supports
def _local(ob, P):
    Mi = np.array(ob.matrix_world.inverted())
    return P @ Mi[:3, :3].T + Mi[:3, 3]


def _slab(ob):
    """Half extents of a prop body (x, y, z) in its local frame."""
    co = np.array([v.co[:] for v in ob.data.vertices])
    return np.abs(co).max(0)


_CUFF = {}


def _cuff(side, body_name="Morfi_Body"):
    """Sleeve cuff around the wrist (body faces skinned to the hand bone): it is
    thicker than the hand, so it touches a held prop first."""
    if side not in _CUFF:
        body = bpy.data.objects[body_name]
        idx = {body.vertex_groups[f"hand.{side}"].index}
        w = np.zeros(len(body.data.vertices))
        for v in body.data.vertices:
            w[v.index] = sum(g.weight for g in v.groups if g.group in idx)
        # fix_wrists.py hands most of the cuff to the forearm (the hand keeps 30 %): relative threshold
        _CUFF[side] = (w > 0.3 * w.max()) & _faced(body)
    return _eval_coords(bpy.data.objects[body_name])[_CUFF[side]]


def _support_gap(spec, hand):
    prop = bpy.data.objects[spec["prop"]]
    hx, hy, hz = _slab(prop)
    L = _local(prop, np.concatenate([_eval_coords(hand), _cuff(spec["side"])]))
    inside = (np.abs(L[:, 0]) < hx * 0.99) & (np.abs(L[:, 2]) < hz * 0.99)   # under the footprint
    if not inside.any():
        return None, None
    gap = (L[inside, 1] - hy).min()               # back face is local +Y
    nb = np.array(prop.matrix_world.to_3x3() @ Vector((0, 1, 0))).ravel()
    return gap, nb / np.linalg.norm(nb)


def _solve_support(rig, action, clip, spec):
    bone = f"hand_ik.{spec['side']}"
    fcs = _loc_curves(action, bone)
    hand = bpy.data.objects[f"Hand_{spec['side']}"]
    a, b = spec["frames"]
    ref = spec.get("ref", a)
    _frame(ref)
    for _ in range(ITER):
        gap, nb = _support_gap(spec, hand)
        if gap is None:
            raise RuntimeError(f"support {spec}: the hand is not under {spec['prop']} at frame {ref}")
        if abs(gap) < 2e-4:
            break
        d = np.linalg.solve(_jacobian(rig, bone), -gap * nb)
        for f in range(*spec.get("apply", (a, b + 1))):    # the target lives in prop space: one offset
            _set_loc(fcs, f, _get_loc(fcs, f) + d)
        _refresh(fcs)
        _frame(ref)


def solve(rig, action, clip):
    """Apply the clip's supports, then its presses, to the baked action."""
    from . import rigmap
    rigmap.assign(rig, action)
    for spec in getattr(clip, "supports", []):
        _solve_support(rig, action, clip, spec)
    if getattr(clip, "supports", None):
        pulled = clamp_reach(rig, action, clip.n)        # a support out of reach stops short
        if pulled:
            print(f"  support out of reach on {pulled} frames: the prop must come closer")
    by_side = {}
    for spec in getattr(clip, "contacts", []):
        by_side.setdefault(spec["side"], []).append(spec)
    for side, specs in by_side.items():
        _press_track(rig, action, clip, side, sorted(specs, key=lambda s: s["frames"][0]))


# ---------------------------------------------------------------- arms: volume-kept stretch
def _curves(action, bone, attr, count, n, rest):
    """The fcurves of a bone attribute with one key per frame (created at `rest` if missing)."""
    path = f'pose.bones["{bone}"].{attr}'
    out = []
    for i in range(count):
        fc = action.fcurves.find(path, index=i)
        if fc is None or len(fc.keyframe_points) < n:
            old = fc
            vals = [old.evaluate(f) for f in range(n)] if old is not None else [rest[i]] * n
            if old is not None:
                action.fcurves.remove(old)
            fc = action.fcurves.new(path, index=i, action_group=bone)
            fc.keyframe_points.add(n)
            co = np.empty(2 * n)
            co[0::2] = np.arange(n, dtype=float)
            co[1::2] = vals
            fc.keyframe_points.foreach_set("co", co)
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        out.append(fc)
    return out


def _fk_basis(P, d, x_d, length, thick):
    """Local rotation + scale that give a bone whose rest-to-pose matrix (identity basis) is P
    the world (armature) Y axis d * length and a thickness `thick` across it, whatever scale it
    inherits from its parent. A parent's non-uniform scale shears its child: the axis along the
    bone stays exact, the cross axes are only scaled back to `thick` (the shear left is small)."""
    from mathutils import Matrix
    Pi = P.inverted()
    yl = (Pi @ d).normalized()
    xl = Pi @ x_d
    xl = (xl - xl.dot(yl) * yl).normalized()
    zl = xl.cross(yl)
    R = Matrix((xl, yl, zl)).transposed()
    scale = (thick / (P @ xl).length, length / (P @ yl).length, thick / (P @ zl).length)
    return R, scale


def rebake_arms(rig, action, n, sides=("L", "R")):
    """The arms as FK with a stretch that keeps their volume, the hands at their own size.

    Blender's IK stretch scales the arm bones uniformly (a fatter arm and a bigger hand), and an
    FK .sy stretch compounds down the chain (fingers elongate). This pass takes the evaluated
    arm on every frame (IK, contacts and all), switches the arm to FK and keys each bone so that
    its axis lands exactly where it was (same elbow, same wrist), stretched with its volume kept
    (thinner as it gets longer); the hand gets its own size back. Call it with the rig's normal
    inheritance (contacts are solved with the hands not inheriting the IK scale, see
    hands_keep_size). Returns per-side stats: wrist error (mm), hand direction error (deg),
    max stretch and the hand shear left (deg)."""
    from mathutils import Matrix
    from . import rigmap
    rigmap.assign(rig, action)
    stats = {}
    pbs = {s: [rig.pose.bones[f"{b}.{s}"] for b in ARM_BONES] for s in sides}
    offs = {s: [(pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local) for pb in pbs[s]] for s in sides}
    ref = {s: [] for s in sides}                 # evaluated arm per frame (armature space)
    with bones_only():
        for f in range(n):
            _frame(f)
            for s in sides:
                ref[s].append([pbs[s][0].parent.matrix.copy()] + [pb.matrix.copy() for pb in pbs[s]])
        for s in sides:
            for path in (f'pose.bones["forearm.{s}"].constraints["ArmIK"].influence',
                         f'pose.bones["hand.{s}"].constraints["HandIK"].influence'):
                fc = action.fcurves.find(path)
                if fc is not None:
                    for kp in fc.keyframe_points:
                        kp.co[1] = 0.0
                    fc.update()
            rot = [_curves(action, pb.name, "rotation_quaternion", 4, n, (1, 0, 0, 0)) for pb in pbs[s]]
            scl = [_curves(action, pb.name, "scale", 3, n, (1, 1, 1)) for pb in pbs[s]]
            prev = [None] * 3
            kmax = 1.0
            for f in range(n):
                parent = ref[s][f][0]
                for b in range(3):
                    M = ref[s][f][b + 1]
                    y = M.col[1].to_3d()
                    k = y.length
                    d = y / k
                    x = M.col[0].to_3d().normalized()
                    x_d = (x - x.dot(d) * d).normalized()
                    if b == 2:
                        k = 1.0                          # the hand keeps its own size
                    kmax = max(kmax, k)
                    P = parent @ offs[s][b]
                    R, sc = _fk_basis(P.to_3x3(), d, x_d, k, 1.0 / np.sqrt(k))
                    q = R.to_quaternion()
                    if prev[b] is not None and q.dot(prev[b]) < 0:
                        q.negate()
                    prev[b] = q
                    for i in range(4):
                        rot[b][i].keyframe_points[f].co[1] = q[i]
                    for i in range(3):
                        scl[b][i].keyframe_points[f].co[1] = sc[i]
                    basis = R.to_4x4() @ Matrix.Diagonal((*sc, 1.0))
                    parent = P @ basis                   # this bone as its child will see it
                    parent.translation = M.translation   # (connected: the head is the parent's tail)
            for fc in sum(rot, []) + sum(scl, []):
                fc.update()
            stats[s] = {"stretch": kmax}
        werr = {s: 0.0 for s in sides}
        derr = {s: 0.0 for s in sides}
        shear = {s: 0.0 for s in sides}
        for f in range(n):
            _frame(f)
            for s in sides:
                H, H0 = pbs[s][2].matrix, ref[s][f][3]
                werr[s] = max(werr[s], (H.translation - H0.translation).length)
                a = H.col[1].to_3d().normalized().angle(H0.col[1].to_3d().normalized(), 0.0)
                derr[s] = max(derr[s], float(np.degrees(a)))
                cx, cy = H.col[0].to_3d().normalized(), H.col[1].to_3d().normalized()
                shear[s] = max(shear[s], abs(90.0 - float(np.degrees(cx.angle(cy, 0.0)))))
        for s in sides:
            stats[s].update(wrist_mm=werr[s] * 1000, dir_deg=derr[s], shear_deg=shear[s])
    return stats


class meshes_only:
    """Evaluate only these meshes (the others keep their modifiers off): a faster frame_set."""

    def __init__(self, names):
        self.names = set(names)

    def __enter__(self):
        self.saved = [(m, m.show_viewport) for ob in bpy.data.objects
                      if ob.type == "MESH" and ob.name not in self.names for m in ob.modifiers]
        for m, _ in self.saved:
            m.show_viewport = False
        return self

    def __exit__(self, *exc):
        for m, v in self.saved:
            m.show_viewport = v


FK_MARGIN = 0.004      # clearance the FK pass leaves between a hand / sleeve and the head or torso (m)
FK_FADE = 7            # frames over which a correction fades in and out (no pop)


def _signed_gaps(tree, kd, Q, shallow=0.03):
    """Signed distance of the points Q to a surface (negative inside, trusted within `shallow`),
    the worst point and the outward normal there. kd (scipy) skips the points far from it."""
    d0, _ = kd.query(Q, distance_upper_bound=0.05)
    worst = (np.inf, None, None)
    for q in Q[np.isfinite(d0)]:
        loc, nrm, _, d = tree.find_nearest(Vector(q), 0.05)
        if loc is None:
            continue
        v = -d if ((Vector(q) - loc).dot(nrm) < 0 and d < shallow) else d
        if v < worst[0]:
            worst = (v, q, np.array(nrm))
    return worst


def _arm_fix(shoulder, q, nrm, need):
    """Rotation vector (armature space) about the shoulder that moves the point q by `need`
    along the normal (only the part of the normal across the arm can be reached by a rotation)."""
    u = q - shoulder
    L = np.linalg.norm(u)
    uh = u / L
    perp = nrm - (nrm @ uh) * uh
    k = np.linalg.norm(perp)
    if k < 0.25:                      # pushing along the arm itself: a rotation cannot do it
        return np.zeros(3)
    t = need / k                      # distance to travel across the arm
    return np.cross(uh, perp / k) * (t / L)


def _spread(r, loop, skip):
    """Per-frame correction vectors -> a smooth track: every needed correction holds over its
    frames, fades in and out over FK_FADE frames, and is zero where a contact owns the hand."""
    n = len(r)
    mag = np.linalg.norm(r, axis=1)
    out = np.zeros_like(r)
    best = np.zeros(n)
    for g in np.flatnonzero(mag > 0):
        for k in range(-FK_FADE - 1, FK_FADE + 2):
            f = g + k
            if loop:
                f %= n
            elif not 0 <= f < n:
                continue
            w = 1.0 if abs(k) <= 1 else 0.5 + 0.5 * np.cos(np.pi * (abs(k) - 1) / (FK_FADE + 1))
            if mag[g] * w > best[f]:
                best[f] = mag[g] * w
                out[f] = r[g] * w
    for a, b in skip:
        out[max(0, a):b + 1] = 0.0
    return out


def resolve_body_fk(rig, action, n, loop=False, skip=(), body_name="Morfi_Body", rounds=4):
    """The body is solid for FK arms too (every arm is FK after rebake_arms): on the frames where
    a hand goes into the head or the torso, or a sleeve into the head (his 60 cm head over 20 cm
    arms: a hand raised by the cheek, a squash that widens the head), the whole arm turns about
    the shoulder just enough to clear it (+FK_MARGIN). The corrections fade in and out over a few
    frames so the arm keeps its arc; frames in `skip` (contacts) are left alone: a list of
    (first, last) frames for both arms, or {side: list} per arm.
    Returns {side: (frames corrected, worst gap before, worst gap after)} in m."""
    from mathutils import Quaternion
    from mathutils.bvhtree import BVHTree
    from scipy.spatial import cKDTree
    from . import rigmap
    rigmap.assign(rig, action)
    body = bpy.data.objects[body_name]
    hands = {s: bpy.data.objects[f"Hand_{s}"] for s in ("L", "R")}
    parts = _body_parts(body)
    pverts = {k: np.unique(np.array([i for p in pl for i in p])) for k, pl in parts.items()}
    faced = _faced(body)
    sleeves = {s: np.flatnonzero(_group_mask(body, [f"forearm.{s}", f"hand.{s}"], 0.6) & faced)[::2]
               for s in ("L", "R")}
    Minv = np.array(rig.matrix_world.inverted())
    W3 = np.array(rig.matrix_world.to_3x3())
    up = {s: rig.pose.bones[f"upper_arm.{s}"] for s in ("L", "R")}
    rot = {s: [action.fcurves.find(f'pose.bones["upper_arm.{s}"].rotation_quaternion', index=i)
               for i in range(4)] for s in ("L", "R")}
    if any(fc is None or len(fc.keyframe_points) < n for fcs in rot.values() for fc in fcs):
        raise RuntimeError("resolve_body_fk runs after rebake_arms (one quaternion key per frame)")
    offs = {s: up[s].parent.bone.matrix_local.inverted() @ up[s].bone.matrix_local for s in ("L", "R")}
    if not isinstance(skip, dict):
        skip = {"L": list(skip), "R": list(skip)}
    owned = {s: {f for f in range(n) if any(a <= f <= b for a, b in skip.get(s, ()))} for s in ("L", "R")}
    todo = [f for f in range(n) if not (f in owned["L"] and f in owned["R"])]
    gaps = {s: np.full(n, np.inf) for s in ("L", "R")}
    first = {s: np.inf for s in ("L", "R")}
    fixed = {s: np.zeros(n, bool) for s in ("L", "R")}
    rest_q = {}                       # shoulder frame of the upper arm per frame (corrections leave it alone)

    def measure(f):
        """Worst (gap, point, normal) per side at frame f, in armature space."""
        _frame(f)
        P = _eval_coords(body)
        trees = {k: (BVHTree.FromPolygons([tuple(v) for v in P], parts[k]), cKDTree(P[pverts[k]]))
                 for k in ("head", "torso")}
        res = {}
        for s in ("L", "R"):
            rest_q.setdefault((s, f), (up[s].parent.matrix @ offs[s]).to_quaternion())
            H = _eval_coords(hands[s])[::2]
            g, q, nrm = min((_signed_gaps(*trees["head"], H), _signed_gaps(*trees["torso"], H),
                             _signed_gaps(*trees["head"], P[sleeves[s]])), key=lambda c: c[0])
            if q is not None:
                q = Minv[:3, :3] @ q + Minv[:3, 3]
                nrm = np.linalg.solve(W3, nrm)
                nrm /= np.linalg.norm(nrm)
            res[s] = (g, q, nrm, np.array(up[s].head))
        return res

    with meshes_only([body_name, *(h.name for h in hands.values())]):
        frames = todo
        for rnd in range(rounds + 1):
            need = {s: np.zeros((n, 3)) for s in ("L", "R")}
            for f in frames:
                for s, (g, q, nrm, sh) in measure(f).items():
                    if f in owned[s]:                 # a contact owns this arm here
                        continue
                    gaps[s][f] = g
                    if rnd == 0:
                        first[s] = min(first[s], g)
                    if q is not None and g < FK_MARGIN - 5e-4:
                        need[s][f] = _arm_fix(sh, q, nrm, FK_MARGIN - g)
            if rnd == rounds or not any(np.any(v) for v in need.values()):
                break
            moved = set()
            for s in ("L", "R"):
                corr = _spread(need[s], loop, skip.get(s, ()))
                for f in np.flatnonzero(np.linalg.norm(corr, axis=1) > 1e-6):
                    f = int(f)
                    a = float(np.linalg.norm(corr[f]))
                    Pq = rest_q[(s, f)]
                    q0 = Quaternion([fc.keyframe_points[f].co[1] for fc in rot[s]])
                    q1 = Pq.inverted() @ Quaternion(Vector(corr[f] / a), a) @ Pq @ q0
                    if q1.dot(q0) < 0:
                        q1.negate()
                    for i, fc in enumerate(rot[s]):
                        fc.keyframe_points[f].co[1] = q1[i]
                    fixed[s][f] = True
                    moved.add(f)
                for fc in rot[s]:
                    fc.update()
            frames = sorted(moved)
    return {s: (int(fixed[s].sum()), first[s], float(gaps[s].min())) for s in ("L", "R")}


def _touch_gap(spec, hand, step=2):
    """Signed gap of the hand to his own skin (as verify() measures it), the hand point and the
    skin normal there (world)."""
    from mathutils.bvhtree import BVHTree
    body = bpy.data.objects["Morfi_Body"]
    tree = BVHTree.FromPolygons([tuple(v) for v in _eval_coords(body)], _body_parts(body)[spec["touch"]])
    best = (np.inf, None, None)
    for q in _eval_coords(hand)[::step]:
        loc, nrm, _, d = tree.find_nearest(Vector(q), 0.10)
        if loc is None:
            continue
        sd = d if (Vector(q) - loc).dot(nrm) >= 0 else -d
        if sd < best[0]:
            best = (sd, np.array(q), np.array(nrm))
    return best


def _support_point(spec, hand):
    """Gap of a palm under a prop (as _support_gap), the hand / cuff point and the prop's back normal."""
    prop = bpy.data.objects[spec["prop"]]
    hx, hy, hz = _slab(prop)
    P = np.concatenate([_eval_coords(hand), _cuff(spec["side"])])
    L = _local(prop, P)
    inside = (np.abs(L[:, 0]) < hx * 0.99) & (np.abs(L[:, 2]) < hz * 0.99)
    if not inside.any():
        return None, None, None
    k = np.flatnonzero(inside)[np.argmin(L[inside, 1])]
    nb = np.array(prop.matrix_world.to_3x3() @ Vector((0, 1, 0))).ravel()
    return float(L[k, 1] - hy), P[k], nb / np.linalg.norm(nb)


def refine_contacts_fk(rig, action, clip, tol=0.0006, iters=4, body_name="Morfi_Body"):
    """Touches and palm supports exact again on the final FK arm. rebake_arms keeps every wrist
    where the IK put it, but the thinner, longer arm turns the hand's local frame a little, and
    the Wrist limit (fix_wrists.py) then clamps a hand that was right at its limit by a few
    degrees: a palm on a cheek ends up some mm in or out, a palm under a prop tilts. On every
    contact frame the arm turns about the shoulder until the gap closes (presses are left to
    the IK solve: a fingertip barely moves); the correction fades out over the contact's ramp.
    Returns {side: (frames, worst |gap| before, worst |gap| after)} in m."""
    from mathutils import Quaternion
    from . import rigmap
    specs = [s for s in getattr(clip, "contacts", []) if "touch" in s] + list(getattr(clip, "supports", []) or [])
    if not specs:
        return {}
    rigmap.assign(rig, action)
    n = clip.n
    hands = {s: bpy.data.objects[f"Hand_{s}"] for s in ("L", "R")}
    Minv = np.array(rig.matrix_world.inverted())
    W3 = np.array(rig.matrix_world.to_3x3())
    up = {s: rig.pose.bones[f"upper_arm.{s}"] for s in ("L", "R")}
    offs = {s: up[s].parent.bone.matrix_local.inverted() @ up[s].bone.matrix_local for s in ("L", "R")}
    rot = {s: [action.fcurves.find(f'pose.bones["upper_arm.{s}"].rotation_quaternion', index=i)
               for i in range(4)] for s in ("L", "R")}
    owned = np.zeros(n, bool)
    for spec in specs:
        owned[max(0, spec["frames"][0]):min(n - 1, spec["frames"][1]) + 1] = True

    def turn(s, f, Wq):
        """Turn the upper arm by Wq (armature space, about the shoulder) at frame f."""
        Pq = (up[s].parent.matrix @ offs[s]).to_quaternion()
        q0 = Quaternion([fc.keyframe_points[f].co[1] for fc in rot[s]])
        q1 = Pq.inverted() @ Wq @ Pq @ q0
        if q1.dot(q0) < 0:
            q1.negate()
        for i, fc in enumerate(rot[s]):
            fc.keyframe_points[f].co[1] = q1[i]
            fc.update()

    def gap(spec, s):
        if "touch" in spec:
            return _touch_gap(spec, hands[s])
        return _support_point(spec, hands[s])

    stats = {}
    with meshes_only([body_name, *(h.name for h in hands.values())]):
        for spec in specs:
            s = spec["side"]
            f0, f1 = max(0, spec["frames"][0]), min(n - 1, spec["frames"][1])
            acc = {}
            st = stats.setdefault(s, [0, 0.0, 0.0])
            for f in range(f0, f1 + 1):
                total = Quaternion()
                g = None
                for it in range(iters + 1):
                    _frame(f)
                    g, q, nrm = gap(spec, s)
                    if g is None:
                        break
                    if it == 0:
                        st[1] = max(st[1], abs(g))
                    if abs(g) < tol or it == iters:
                        break
                    q = Minv[:3, :3] @ q + Minv[:3, 3]
                    nrm = np.linalg.solve(W3, nrm)
                    r = _arm_fix(np.array(up[s].head), q, nrm / np.linalg.norm(nrm), -g)
                    a = float(np.linalg.norm(r))
                    if a < 1e-7:
                        break
                    Wq = Quaternion(Vector(r / a), a)
                    turn(s, f, Wq)
                    total = Wq @ total
                if g is not None:
                    st[2] = max(st[2], abs(g))
                if total.angle > 1e-7:
                    st[0] += 1
                acc[f] = total
            # fade the edge corrections out over the ramp (frames no other contact owns)
            ramp = int(spec.get("ramp", 6))
            for edge, frames in ((f0, range(f0 - 1, f0 - ramp - 1, -1)), (f1, range(f1 + 1, f1 + ramp + 1))):
                if edge not in acc or acc[edge].angle < 1e-7:
                    continue
                for k, f in enumerate(frames):
                    if not 0 <= f < n or owned[f]:
                        continue
                    w = 1.0 - (k + 1) / (ramp + 1)
                    _frame(f)
                    turn(s, f, Quaternion().slerp(acc[edge], w))
    return {s: tuple(v) for s, v in stats.items()}


SWIVEL_STEPS = np.radians([-40, -30, -20, -12, -6, 6, 12, 20, 30, 40])   # swivels tried per touch


def clear_sleeves_fk(rig, action, clip, body_name="Morfi_Body"):
    """A hand resting on his face can leave its sleeve inside the big head (a forearm along the
    side of the head to scratch it, under the chin to think). For each touch on the head the arm
    swivels about the shoulder-wrist line: the elbow goes out, the wrist stays exactly where it
    is and the hand keeps its orientation. The swivel is searched (several angles tried on the
    first, middle and last frames of the touch, the one that clears the sleeve most wins), held
    over the touch and eased in and out over its ramp. Call refine_contacts_fk() afterwards (the
    Wrist limit may turn the hand a hair). Returns {side: (frames, worst gap before, worst gap
    after)} in m."""
    from mathutils import Quaternion
    from mathutils.bvhtree import BVHTree
    from scipy.spatial import cKDTree
    from . import rigmap
    specs = [s for s in getattr(clip, "contacts", []) if s.get("touch") == "head"]
    if not specs:
        return {}
    rigmap.assign(rig, action)
    n = clip.n
    body = bpy.data.objects[body_name]
    parts = _body_parts(body)
    hv = np.unique(np.array([i for p in parts["head"] for i in p]))
    faced = _faced(body)
    stats = {}
    for s in sorted({sp["side"] for sp in specs}):
        # the whole sleeve, cuff included (its weight is shared by the forearm and the hand)
        gi = {body.vertex_groups[g].index for g in (f"forearm.{s}", f"hand.{s}") if g in body.vertex_groups}
        w = np.array([sum(g.weight for g in v.groups if g.group in gi) for v in body.data.vertices])
        sleeve = np.flatnonzero((w >= 0.6) & faced)[::2]
        up, hb = rig.pose.bones[f"upper_arm.{s}"], rig.pose.bones[f"hand.{s}"]
        offs = {pb.name: pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local for pb in (up, hb)}
        rot = {pb.name: [action.fcurves.find(f'pose.bones["{pb.name}"].rotation_quaternion', index=i)
                         for i in range(4)] for pb in (up, hb)}
        first, last, count = np.inf, np.inf, 0

        def gap(f):
            _frame(f)
            P = _eval_coords(body)
            tree = BVHTree.FromPolygons([tuple(v) for v in P], parts["head"])
            return _signed_gaps(tree, cKDTree(P[hv]), P[sleeve])[0]

        def keys(f):
            return {b: [fc.keyframe_points[f].co[1] for fc in fcs] for b, fcs in rot.items()}

        def put(f, vals):
            for b, fcs in rot.items():
                for fc, v in zip(fcs, vals[b]):
                    fc.keyframe_points[f].co[1] = v
                    fc.update()

        def swivel(f, ang):
            """Turn the arm by `ang` about its shoulder-wrist line at frame f (hand kept)."""
            _frame(f)
            sh, wr = np.array(up.head), np.array(hb.head)
            Wq = Quaternion(Vector((wr - sh) / np.linalg.norm(wr - sh)), ang)
            Pu = (up.parent.matrix @ offs[up.name]).to_quaternion()
            Ph = (hb.parent.matrix @ offs[hb.name]).to_quaternion()
            vals = keys(f)
            for b, turn in ((up.name, Pu.inverted() @ Wq @ Pu), (hb.name, Ph.inverted() @ Wq.inverted() @ Ph)):
                q0 = Quaternion(vals[b])
                q1 = turn @ q0
                if q1.dot(q0) < 0:
                    q1.negate()
                vals[b] = list(q1)
            put(f, vals)

        with meshes_only([body_name]):
            for sp in [sp for sp in specs if sp["side"] == s]:
                a0, b0 = max(0, sp["frames"][0]), min(n - 1, sp["frames"][1])
                probe = sorted({a0, (a0 + b0) // 2, b0})
                base = min(gap(f) for f in probe)
                first = min(first, base)
                if base >= FK_MARGIN:
                    last = min(last, base)
                    continue
                best = (base, 0.0)
                for ang in SWIVEL_STEPS:
                    score = np.inf
                    for f in probe:
                        saved = keys(f)
                        swivel(f, float(ang))
                        score = min(score, gap(f))
                        put(f, saved)
                    if score > best[0] + 0.001:
                        best = (score, float(ang))
                last = min(last, best[0])
                if best[1] == 0.0:
                    continue
                ramp = int(sp.get("ramp", 6))
                for f in range(a0 - ramp, b0 + ramp + 1):
                    if 0 <= f < n:
                        d = max(a0 - f, f - b0, 0)
                        w = 1.0 if d == 0 else 0.5 + 0.5 * np.cos(np.pi * d / (ramp + 1))
                        swivel(f, best[1] * w)
                        count += 1
        stats[s] = (count, first, last)
    return stats


class hands_keep_size:
    """While contacts are solved on IK the hands do not inherit the arms' IK stretch, so they
    touch with the size they will have after rebake_arms()."""

    def __init__(self, rig):
        self.bones = [rig.data.bones[f"hand.{s}"] for s in ("L", "R")]

    def __enter__(self):
        for b in self.bones:
            b.inherit_scale = "NONE"
        bpy.context.view_layer.update()
        return self

    def __exit__(self, *exc):
        for b in self.bones:
            b.inherit_scale = "FULL"
        bpy.context.view_layer.update()


# ---------------------------------------------------------------- verification
def _prop_boxes(rig, f):
    """Visible prop bodies (and calculator keys) as (object, half extents)."""
    out = []
    for bone, root in (("prop_tablet", "Prop_Tablet"), ("prop_calc", "Prop_Calc")):
        if bone not in rig.pose.bones or rig.pose.bones[bone].scale[0] < 0.5:
            continue
        ob = bpy.data.objects[root]
        out.append((ob, _slab(ob)))
        for ch in ob.children:
            if "_Key_" in ch.name:
                out.append((ch, _slab(ch)))
    return out


def _depth(ob, half, P):
    L = _local(ob, P)
    d = np.min(half - np.abs(L), axis=1)
    return d.max() if len(d) else -1.0


def verify(rig, action, clip, body_name="Morfi_Body"):
    """Per frame: deepest overlap of hands / body with the props (m), press and support gaps."""
    from . import rigmap
    rigmap.assign(rig, action)
    hands = {s: bpy.data.objects[f"Hand_{s}"] for s in ("L", "R")}
    body = bpy.data.objects[body_name]
    rows, worst = [], {"pen": -1.0, "press": 0.0, "support": 0.0, "touch": 0.0}
    tips = {}
    for spec in getattr(clip, "contacts", []):
        tips.setdefault((spec["side"],) + _tip_groups(spec), _tip_mask(hands[spec["side"]], spec))
    for f in range(clip.n):
        boxes = None
        _frame(f)
        boxes = _prop_boxes(rig, f)
        active = [sp for sp in getattr(clip, "contacts", []) if sp["frames"][0] <= f <= sp["frames"][1]]
        if not boxes and not active:
            continue
        P = {s: _eval_coords(h) for s, h in hands.items()}
        pen = -1.0
        if boxes:
            B = _eval_coords(body)[_faced(body)]
            pen = max(max(_depth(ob, half, X) for X in (P["L"], P["R"], B)) for ob, half in boxes)
        row = {"frame": f, "pen": pen}
        for spec in getattr(clip, "contacts", []):
            f0, f1 = spec["frames"]
            if f0 <= f <= f1:
                if "touch" in spec:
                    row["touch"] = float(_touch_error(spec, hands[spec["side"]], step=2)[2])
                    worst["touch"] = max(worst["touch"], abs(row["touch"]))
                    continue
                else:
                    S, n = _target_point(spec)
                    row["press"] = float(((P[spec["side"]][tips[(spec["side"],) + _tip_groups(spec)]] - S) @ n).min())
                worst["press"] = max(worst["press"], abs(row["press"]))
        for spec in getattr(clip, "supports", []):
            a, b = spec["frames"]
            if a <= f <= b:
                gap, _ = _support_gap(spec, hands[spec["side"]])
                row["support"] = gap
                # a hand that is not under the prop at all does not support it
                worst["support"] = max(worst["support"], abs(gap) if gap is not None else float("inf"))
        worst["pen"] = max(worst["pen"], pen)
        rows.append(row)
    ok = (worst["pen"] <= PEN_TOL and worst["press"] <= TOUCH_TOL and worst["support"] <= 0.004
          and worst["touch"] <= BODY_TOL)
    return ok, worst, rows
