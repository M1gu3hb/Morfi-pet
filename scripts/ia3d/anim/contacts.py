"""Contact solver: hands that really touch props, never through them, never in the air.

Runs inside Blender after rigmap.bake(). A clip may declare

  clip.contacts = [{"side": "R", "tip": "index.03.R", "target": "Prop_Tablet_Screen",
                    "local": (x, z), "frames": (f0, f1), "ramp": 6}, ...]
      a fingertip press: from f0 to f1 the pad of `tip` rests exactly on the target's front
      face (local -Y) at local (x, z) (None = the face centre, e.g. a calculator key).
      Between presses the finger hovers HOVER above the surface and comes straight down.
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

HOVER = 0.020          # finger height above the surface between presses (m)
LEAD = 8               # frames to blend from the action's own path into the tapping path
ITER = 6               # Newton steps per frame (the hand moves rigidly with its IK target)
TOUCH_TOL = 0.0015     # |gap| accepted as touching (m)
PEN_TOL = 0.0010       # overlap accepted (m): skin compresses a little
MAX_REACH = 1.08       # shoulder->wrist distance on IK, as a fraction of the rest arm length:
                       # Blender's IK stretch has no upper bound, so targets are pulled back to
                       # this (a cartoon reach, never a rubber arm)


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


def _target_point(spec):
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


def _clamp_frame(rig, fcs, side, f):
    """Pull the hand_ik target back within MAX_REACH of the shoulder at frame f (evaluated)."""
    up = rig.pose.bones[f"upper_arm.{side}"]
    reach = (up.bone.length + rig.pose.bones[f"forearm.{side}"].bone.length) * MAX_REACH
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
            parts[key] = [tuple(p.vertices) for p in body.data.polygons if all(m[i] for i in p.vertices)]
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


def resolve_body(rig, action, n, body_name="Morfi_Body", margin=0.002):
    """Hands never inside Morfi's own head or torso: on every IK frame where a hand goes in,
    its target is pushed out along the surface normal until it only touches (+ margin).
    A fist under the chin or a palm on the belly then rests on the surface."""
    from mathutils.bvhtree import BVHTree
    from . import rigmap
    rigmap.assign(rig, action)
    body = bpy.data.objects[body_name]
    parts = _body_parts(body)
    hands = {s: bpy.data.objects[f"Hand_{s}"] for s in ("L", "R")}
    curves = {s: (_ik_curve(action, s), _loc_curves(action, f"hand_ik.{s}")) for s in ("L", "R")}
    fixed = 0
    for f in range(n):
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


def _solve_press_frame(rig, fcs, bone, spec, hand, tip_mask, f):
    _frame(f)
    for _ in range(ITER):
        err, n, dmin = _press_error(spec, hand, tip_mask)
        if np.linalg.norm(err) < 2e-4:
            break
        J = _jacobian(rig, bone)
        _set_loc(fcs, f, _get_loc(fcs, f) + np.linalg.solve(J, err))
        _refresh(fcs)
        _frame(f)
        if _clamp_frame(rig, fcs, spec["side"], f):     # out of reach: stop short, verify() says so
            _frame(f)
            break
    return n


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
    masks = [_group_mask(hand, [spec["tip"]]) for spec in specs]
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
        a, b = keys[0][0], keys[-1][0]
        w = C.keys(n_frames, [(0, 0.0), (a - LEAD, 0.0), (a, 1.0), (b, 1.0), (b + LEAD, 0.0), (n_frames - 1, 0.0)])
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
        m = np.zeros(len(body.data.vertices), bool)
        for v in body.data.vertices:
            m[v.index] = sum(g.weight for g in v.groups if g.group in idx) > 0.3
        _CUFF[side] = m & _faced(body)
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
        for f in range(a, b + 1):                  # the target lives in prop space: one offset
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
    rows, worst = [], {"pen": -1.0, "press": 0.0, "support": 0.0}
    tips = {}
    for spec in getattr(clip, "contacts", []):
        tips.setdefault(spec["tip"], _group_mask(hands[spec["side"]], [spec["tip"]]))
    for f in range(clip.n):
        _frame(f)
        boxes = _prop_boxes(rig, f)
        if not boxes:
            continue
        P = {s: _eval_coords(h) for s, h in hands.items()}
        B = _eval_coords(body)[_faced(body)]
        pen = max(max(_depth(ob, half, X) for X in (P["L"], P["R"], B)) for ob, half in boxes)
        row = {"frame": f, "pen": pen}
        for spec in getattr(clip, "contacts", []):
            f0, f1 = spec["frames"]
            if f0 <= f <= f1:
                S, n = _target_point(spec)
                row["press"] = float(((P[spec["side"]][tips[spec["tip"]]] - S) @ n).min())
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
    ok = worst["pen"] <= PEN_TOL and worst["press"] <= TOUCH_TOL and worst["support"] <= 0.004
    return ok, worst, rows
