"""Body mesh fixes on the final look blend: neck seam, sleeves / cuffs, finger web.

blender -b work/ia3d/morfi_ia_look5.blend --python scripts/ia3d/fix_body.py -- \
    --out work/ia3d/morfi_ia_look6.blend

Runs after fix_glasses.py and is idempotent: what it changes is stored on the meshes
(`body_fix_orig`) and put back first, so a second run gives the same result.

NECK. The skin of the head's underside and the hoodie / shirt collar shared the vertices of the
hood opening, and the collar was skinned partly to neck / head / shoulders: when the head turned or
tilted, the skin between the head weights and the chest weights stretched into a strip.
Now the head is a separate piece like a toy's:
  * the seam edges between the neck skin and the collar are split (the skin side gets its own copy
    of the seam vertices, appended at the end of the mesh, shape keys carried along);
  * every neck / head skin vertex is rigid on the head bone, every collar vertex (hoodie, shirt,
    zipper) is rigid on the chest (+ its shoulder share);
  * the old neck stub and the head's underside stay as they were, and a smooth skin tube (the neck: same
    material / UV colour, as wide as the stub per angle) is added around the stub: its bottom is inside the
    shirt, its top inside the head, weighted chest -> head along its height, so it bends like a neck. The
    jagged lower border of the stub hides inside it (spikes sticking out are pulled in) and the spiky seam
    outline of the head's ceiling is smoothed, so no gap, slit or tooth shows when the head turns;
  * the head was open underneath: its underside ended in a ragged border up to 19 cm from the neck axis that the
    hood roll used to close, so with the collar on the chest the hollow head showed through the ring between that
    border and the tube whenever the head turned or was seen from below. A floor closes it (close_floor): a
    regular disc of rings, rigid on the head, from inside the tube out past the border, a little above the old
    underside, in its colour; the folded fans and loose teeth of the underside next to the gap are removed (the
    floor covers all they covered), the faces around it take the floor's colour, and the border is lifted into
    the floor, so the head is closed and continues smoothly under the neck, with no hole, slit, shard or fin;
  * the long flat triangles of the head's underside are shaded flat (flatten_floor), so their smooth normals no
    longer run into dark fins beside the neck when the head turns;
  * TUCK / TUCK_IN can slide the skin copies under the collar, but the head is no solid of
    revolution about the neck axis, so any tuck shows as spikes when the head turns: off.
SLEEVES. The wrist of Hand_L/R (a 3.5 cm-radius tube as wide as the sleeve) came out of the cloth
whenever the wrist bent, the cuff turned only 30 % with the hand while the wrist front turned 100 %
(the hand crossed the cuff wall) and the hidden tail followed the forearm. Now the wrist inside
the sleeve is slimmed (it tapers to a point), the cuff rim follows the hand 85 % and fades to the
forearm over 5 cm, and the wrist skin uses the same fade, so cloth and wrist move together.
FINGER WEB. Faces that join two different fingers (the skin web) are removed; finger vertices
already followed only their own finger. The thumb is one of those fingers: in the hands there are no
faces joining thumb and index (nearest vertices 9.5 mm apart), only the finger-to-finger webs existed.
"""
import argparse
import os
import sys

import bmesh
import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STORE = "body_fix_orig"
TUBE = ((0.40, 0.0), (0.44, 0.0), (0.48, 0.0), (0.50, 0.0), (0.51, 0.008), (0.52, 0.020), (0.54, 0.035))
                             # (z, extra radius) rings of the neck tube; its base radius follows the old neck stub per angle (m)
TUBE_GAP = 0.003             # the tube is this much wider than the stub (m); spikes of the stub are pulled in to inside it
CEIL_Z = (0.515, 0.535)       # seam vertices of the head's ceiling are those between these heights ...
CEIL_R = 0.10                # ... and farther than this from the neck axis (m)
CEIL_WIN = 12.0              # their outline is the radius envelope over this many degrees around each vertex
STUB_Z = (0.485, 0.515)      # heights of the old neck stub that give the tube its shape (m)
TUBE_BLEND = (0.43, 0.49)    # chest -> head weight blend of the tube between these heights (m)
TUBE_SEG = 48
FLAT_Z = (0.49, 0.56)        # head skin faces in this height band, farther than FLAT_R from the neck axis ...
FLAT_R = 0.09
FLAT_EDGE = 0.03             # ... with an edge longer than this (m) are shaded flat (see flatten_floor)
FOLD_NZ = -0.5               # head skin faces around the neck facing less down than this (normal z) ...
FOLD_R = 0.21                # ... nearer the axis than this (and outside the tube) are folds, removed (m)
FLOOR_RINGS = 5              # rings of the head's floor between the neck tube and its outer rim (+ one inside the tube)
FLOOR_OVER = 0.03            # the floor reaches this far past the border of the head's underside, above it ...
FLOOR_GAP = 0.002            # ... and stays this far above the underside wherever both are (m)
FLOOR_KEEP = 0.012           # where there is a gap, the underside under the floor goes, all but a band this wide (m)
FLOOR_SEAL = 0.0005          # the border of the underside is lifted to this far above the floor (tucked in) ...
FLOOR_FADE = 0.03            # ... the underside around it following over this distance (m)
FLOOR_LIFT = 0.02            # border vertices the floor passes higher above than this are left alone (m)
FLOOR_TOP = 0.565            # a ray cast up past this height has gone into the hollow head: no underside there (m)
BAND_Z = (0.40, 0.56)        # neck / collar zone of the body (m)
TUCK = 0.0                   # optional: the head skin goes on this far down under the collar (m) ... (0: off, see docstring)
TUCK_IN = 0.0                # ... and this far toward the neck axis
AXIS = (0.0, 0.06)           # vertical axis of the neck (x, y)
COLLAR_MATS = {"Hoodie", "Shirt", "Metal"}
CUFF_HAND = 0.85             # share of the hand that the cuff rim keeps ...
CUFF_BAND = 0.05             # ... fading out to the forearm over this distance behind the opening (m)
FINGER_MIN = 0.5            # a hand vertex belongs to a finger above this share of its bones
WRIST_K = 0.62               # the wrist inside the sleeve is slimmed to this fraction ...
WRIST_FADE = 0.03            # ... over this distance behind the cuff opening (m)
WRIST_TAPER = (0.040, 0.065)  # the tail of the wrist closes to a point between these depths (m)
WRIST_R = 0.040              # only vertices this close to the wrist axis (not the thumb base)


def args_():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--undo", action="store_true", help="only put the original body back")
    ap.add_argument("--tuck", type=float, default=None)
    ap.add_argument("--tuck-in", type=float, default=None)
    return ap.parse_args(argv)


# ---------------------------------------------------------------- store / restore
def restore(body, bm):
    """Undo a previous run on the bmesh of the body (welds the split seam, puts weights back)."""
    st = body.data.get(STORE)
    if st is None:
        return False
    bm.verts.ensure_lookup_table()
    if "flat_f" in st:                        # faces that were shaded flat get their smooth flag back
        bm.faces.ensure_lookup_table()
        for i in st["flat_f"]:
            bm.faces[int(i)].smooth = True
    if "uv_f" in st:                          # faces that took the floor's colour get their own UVs back
        uvl = bm.loops.layers.uv.active
        uvs, k = np.array(st["uv_old"]).reshape(-1, 2), 0
        for i in st["uv_f"]:
            for lp in bm.faces[int(i)].loops:
                lp[uvl].uv = uvs[k]
                k += 1
    if "gone_n" in st:                        # removed faces (old cup, folds, pieces in the gap) come back
        uvl = bm.loops.layers.uv.active
        ids, uvs, k, ku = np.array(st["gone_v"], int), np.array(st["gone_uv"]).reshape(-1, 2), 0, 0
        for n, mi, sm in zip(st["gone_n"], st["gone_m"], st["gone_s"]):
            f = bm.faces.new([bm.verts[int(i)] for i in ids[k:k + n]])
            f.material_index, f.smooth = int(mi), bool(sm)
            for lp, uv in zip(f.loops, uvs[ku:ku + n]):
                lp[uvl].uv = uv
            k += n
            ku += n
    cap = st.get("tube_v0", st.get("cap_v0"))
    if cap is not None:                       # the neck tube (or an older chin cap) was appended after the seam copies
        bmesh.ops.delete(bm, geom=[bm.verts[i] for i in range(int(cap), len(bm.verts))], context="VERTS")
        bm.verts.ensure_lookup_table()
    sh = [bm.verts.layers.shape[k.name] for k in body.data.shape_keys.key_blocks]
    for i, d in zip(st["moved_i"], np.array(st["moved_d"]).reshape(-1, 3)):
        v = bm.verts[int(i)]
        v.co -= type(v.co)(d)
        for lay in sh:
            v[lay] -= type(v.co)(d)
    names = [g.name for g in body.vertex_groups]
    dl = bm.verts.layers.deform.verify()
    welds = {bm.verts[int(n)]: bm.verts[int(o)] for n, o in np.array(st["weld"]).reshape(-1, 2)}
    if welds:
        bmesh.ops.weld_verts(bm, targetmap=welds)
    bm.verts.ensure_lookup_table()
    for i, row in zip(st["w_idx"], np.array(st["w_rows"]).reshape(len(st["w_idx"]), -1)):
        v = bm.verts[int(i)]
        v[dl].clear()
        for gi in np.nonzero(row > 0)[0]:
            v[dl][int(gi)] = float(row[gi])
    del body.data[STORE]
    return True


# ---------------------------------------------------------------- neck
def fix_neck(body, bm, store, report):
    mats = [m.name if m else "" for m in body.data.materials]
    group = {g.name: g.index for g in body.vertex_groups}
    dl = bm.verts.layers.deform.verify()
    sh = [bm.verts.layers.shape[k.name] for k in body.data.shape_keys.key_blocks]
    bm.verts.ensure_lookup_table()
    nv0 = len(bm.verts)
    w_old = {}

    def remember(v):
        if v.index < nv0 and v.index not in w_old:
            row = np.zeros(len(group))
            for gi, w in v[dl].items():
                row[gi] = w
            w_old[v.index] = row

    def set_w(v, w):
        remember(v)
        v[dl].clear()
        for k, x in w.items():
            if x > 1e-4:
                v[dl][group[k]] = float(x)

    def in_band(v):
        return BAND_Z[0] <= v.co.z <= BAND_Z[1] and abs(v.co.x) < 0.21 and -0.11 < v.co.y < 0.21

    def mset(v):
        return {mats[f.material_index] for f in v.link_faces}

    # 1. split the seam between the neck skin and the collar
    seam = []
    for e in bm.edges:
        if len(e.link_faces) == 2 and in_band(e.verts[0]) and in_band(e.verts[1]):
            m = {mats[f.material_index] for f in e.link_faces}
            if "Skin" in m and m & COLLAR_MATS:
                seam.append(e)
    seam_v = {v.index for e in seam for v in e.verts}
    res = bmesh.ops.split_edges(bm, edges=seam)
    bm.verts.ensure_lookup_table()
    where = {}
    for i in seam_v:
        where.setdefault(tuple(np.round(bm.verts[i].co, 6)), []).append(i)
    pairs = []                                       # (original id, new copy)
    for v in bm.verts[nv0:]:
        for i in where.get(tuple(np.round(v.co, 6)), []):
            pairs.append((i, v.index))
    store["weld"] = [int(x) for o, n in pairs for x in (n, o)]
    report["seam_edges"], report["seam_vertices"] = len(seam), len(pairs)

    # 2. the skin side of every split vertex is the head's: tuck it under the collar
    moved = []
    for o, n in pairs:
        vo, vn = bm.verts[o], bm.verts[n]
        skin_v = vo if any(mats[f.material_index] == "Skin" for f in vo.link_faces) else vn
        c = np.array(skin_v.co) - np.array((*AXIS, 0.0))
        c[2] = 0.0
        d = -c / max(np.linalg.norm(c), 1e-9) * TUCK_IN + np.array((0.0, 0.0, -TUCK))
        d = type(skin_v.co)(d)
        skin_v.co += d
        for lay in sh:
            skin_v[lay] += d
        moved.append((skin_v.index, d))
    store["moved_i"] = [int(i) for i, _ in moved]
    store["moved_d"] = [float(x) for _, d in moved for x in d]

    # 3. weights: the head's skin rigid on the head, the collar rigid on the chest
    n_skin = n_collar = 0
    for v in bm.verts:
        if not in_band(v):
            continue
        m = mset(v)
        w = {bm_name: v[dl].get(gi, 0.0) for bm_name, gi in group.items() if v[dl].get(gi, 0.0) > 0}
        if m == {"Skin"} or ("Skin" in m and not (m & COLLAR_MATS)):
            if v.co.z >= 0.46:
                set_w(v, {"head": 1.0})
                n_skin += 1
        elif m & COLLAR_MATS and "Skin" not in m:
            extra = w.pop("neck", 0.0) + w.pop("head", 0.0)
            if extra > 0:
                w["chest"] = w.get("chest", 0.0) + extra
                set_w(v, w)
                n_collar += 1
    # the new copies of the skin keep the head weight; the cloth copies were handled above
    report["skin_vertices_on_head"], report["collar_vertices_on_chest"] = n_skin, n_collar
    store["w_old"], store["nv0"] = w_old, nv0


def add_neck(body, bm, store, report):
    """Neck tube: a smooth skin funnel just outside the old (jagged-edged) neck stub, from inside the shirt
    up into the head, blended chest -> head along its height. The old neck skin and the head underside stay
    as they were, hidden inside it; the tube is what shows between head and collar (no gap, slit or teeth).
    Appended after the seam copies."""
    mats = [m.name if m else "" for m in body.data.materials]
    group = {g.name: g.index for g in body.vertex_groups}
    dl = bm.verts.layers.deform.verify()
    sh = [bm.verts.layers.shape[k.name] for k in body.data.shape_keys.key_blocks]
    bm.verts.ensure_lookup_table()
    store["tube_v0"] = len(bm.verts)
    skin = mats.index("Skin")
    uvl = bm.loops.layers.uv.active
    # template vertex / face of plain neck skin, and its median UV (the colour of the neck at rest)
    neck = [v for v in bm.verts if all(f.material_index == skin for f in v.link_faces)
            and 0.47 < v.co.z < 0.51 and np.hypot(v.co.x - AXIS[0], v.co.y - AXIS[1]) < 0.10]
    tv = min(neck, key=lambda v: np.hypot(v.co.x - AXIS[0], v.co.y - AXIS[1]))
    tf = tv.link_faces[0]
    uv = np.median([lp[uvl].uv[:] for v in neck for f in v.link_faces for lp in f.loops], axis=0)
    # the neck is not round: per-angle radius of the old stub (90th percentile, so its spikes do not count)
    stub = [(np.arctan2(v.co.y - AXIS[1], v.co.x - AXIS[0]), np.hypot(v.co.x - AXIS[0], v.co.y - AXIS[1]))
            for v in bm.verts if STUB_Z[0] < v.co.z < STUB_Z[1] and all(f.material_index == skin for f in v.link_faces)
            and np.hypot(v.co.x - AXIS[0], v.co.y - AXIS[1]) < 0.14]
    th, rr = np.array(stub).T
    nb = 24
    bi = ((th + np.pi) / (2 * np.pi) * nb).astype(int) % nb
    env = np.array([np.percentile(rr[bi == i], 90) if (bi == i).sum() > 2 else np.median(rr) for i in range(nb)])
    env = np.convolve(np.r_[env[-2:], env, env[:2]], np.ones(3) / 3, "same")[2:-2]
    cen = (np.arange(nb) + 0.5) / nb * 2 * np.pi - np.pi

    def base(a):
        return float(np.interp(a, np.r_[cen[-1] - 2 * np.pi, cen, cen[0] + 2 * np.pi], np.r_[env[-1], env, env[0]]))

    ring = []
    for z, extra in TUBE:
        t = smoothstep(*TUBE_BLEND, z)
        row = []
        for k in range(TUBE_SEG):
            a = 2 * np.pi * k / TUBE_SEG - np.pi
            rad = base(a) + extra + TUBE_GAP
            co = type(tv.co)((AXIS[0] + rad * np.cos(a), AXIS[1] + rad * np.sin(a), z))
            v = bm.verts.new(co, tv)
            v.co = co
            for lay in sh:
                v[lay] = co
            v[dl].clear()
            if t < 1.0:
                v[dl][group["chest"]] = float(1.0 - t)
            if t > 0.0:
                v[dl][group["head"]] = float(t)
            row.append(v)
        ring.append(row)
    nf = 0
    for r0, r1 in zip(ring[:-1], ring[1:]):
        for k in range(TUBE_SEG):
            k2 = (k + 1) % TUBE_SEG
            f = bm.faces.new([r0[k], r0[k2], r1[k2], r1[k]], tf)
            for lp in f.loops:
                lp[uvl].uv = uv
            f.material_index = skin
            f.smooth = True
            f.normal_update()
            c = f.calc_center_median()
            if f.normal.dot(type(tv.co)((c.x - AXIS[0], c.y - AXIS[1], 0.0))) < 0:
                f.normal_flip()
            nf += 1
    # spikes of the old stub that stick out of the tube are pulled in (they would show as teeth when the head tilts)
    tz, tx = zip(*TUBE)
    n_in = 0
    for v in list(bm.verts)[:store["tube_v0"]]:
        c = np.array((v.co.x - AXIS[0], v.co.y - AXIS[1]))
        r = np.hypot(*c)
        if 0.46 < v.co.z < 0.515 and r < 0.14 and all(f.material_index == skin for f in v.link_faces):
            over = r - (base(np.arctan2(c[1], c[0])) + np.interp(v.co.z, tz, tx))
            if over > 0:
                d = type(v.co)((*(-c / r * over), 0.0))
                v.co += d
                for lay in sh:
                    v[lay] += d
                store["moved_i"].append(int(v.index))
                store["moved_d"].extend(float(x) for x in d)
                n_in += 1
    report["tube_vertices"], report["tube_faces"], report["stub_spikes_pulled_in"] = len(bm.verts) - store["tube_v0"], nf, n_in


def smooth_seam(body, bm, store, report):
    """The ceiling of the head ends in long radial spikes along the hood opening (they were interlocked with
    the hood roll). The seam vertices of the ceiling are put on a smooth outline (the outer envelope of their radius,
    averaged heights) so that no tooth is left to poke out of the collar when the head turns."""
    mats = [m.name if m else "" for m in body.data.materials]
    sh = [bm.verts.layers.shape[k.name] for k in body.data.shape_keys.key_blocks]
    bm.verts.ensure_lookup_table()
    seam = {int(i) for i in store["weld"]}
    pts = []
    for i in sorted(seam):
        v = bm.verts[i]
        c = np.array((v.co.x - AXIS[0], v.co.y - AXIS[1]))
        r = np.hypot(*c)
        if (CEIL_Z[0] < v.co.z < CEIL_Z[1] and r > CEIL_R and all(mats[f.material_index] == "Skin" for f in v.link_faces)):
            pts.append((v, np.arctan2(c[1], c[0]), r, v.co.z, c))
    ang = np.array([p[1] for p in pts])
    rad = np.array([p[2] for p in pts])
    zz = np.array([p[3] for p in pts])
    win = np.radians(CEIL_WIN)
    for v, a, r, z, c in pts:
        near = np.abs((ang - a + np.pi) % (2 * np.pi) - np.pi) < win
        r2, z2 = rad[near].max(), zz[near].mean()
        d = type(v.co)((*(c / r * (r2 - r)), z2 - z))
        v.co += d
        for lay in sh:
            v[lay] += d
        store["moved_i"].append(int(i := v.index))
        store["moved_d"].extend(float(x) for x in d)
    report["ceiling_seam_vertices_smoothed"] = len(pts)


def remove_faces(bm, faces, store):
    """Delete faces, keeping what --undo needs to bring them back (appended to the stored ones)."""
    uvl = bm.loops.layers.uv.active
    store.setdefault("gone_v", []).extend(int(v.index) for f in faces for v in f.verts)
    store.setdefault("gone_n", []).extend(len(f.verts) for f in faces)
    store.setdefault("gone_m", []).extend(int(f.material_index) for f in faces)
    store.setdefault("gone_s", []).extend(bool(f.smooth) for f in faces)
    store.setdefault("gone_uv", []).extend(float(x) for f in faces for lp in f.loops for x in lp[uvl].uv)
    bmesh.ops.delete(bm, geom=faces, context="FACES_ONLY")


def head_rays(body, bm, t0):
    """The head's own skin around the neck (not the tube) and a ray cast straight up from below at (r, angle)
    onto it: the height of the first hit, or None (no hit, or so high that the ray went into the hollow head)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    skin = [m.name if m else "" for m in body.data.materials].index("Skin")
    gh = body.vertex_groups["head"].index
    dl = bm.verts.layers.deform.verify()
    bm.verts.index_update()
    bm.verts.ensure_lookup_table()
    head = [f for f in bm.faces if f.material_index == skin and f.calc_center_median().z > 0.49
            and polar(f.calc_center_median())[0] < 0.32 and all(v.index < t0 and v[dl].get(gh, 0.0) > 0.5 for v in f.verts)]
    ids = sorted({v.index for f in head for v in f.verts})
    pos = {i: k for k, i in enumerate(ids)}
    tree = BVHTree.FromPolygons([bm.verts[i].co.copy() for i in ids], [[pos[v.index] for v in f.verts] for f in head])
    up = Vector((0.0, 0.0, 1.0))

    def under(r, a):
        loc = tree.ray_cast(Vector((AXIS[0] + r * np.cos(a), AXIS[1] + r * np.sin(a), 0.44)), up, 0.2)[0]
        return None if loc is None or loc.z > FLOOR_TOP else loc.z

    return under, head


def drop_folds(body, bm, store, report):
    """Where the head's underside was tucked into the hood roll it folds back on itself: fans of needle triangles
    facing up or sideways, 14 to 19 cm from the neck axis beside the neck, that showed from below as dark shards
    and stripes. They all lie where close_floor puts the floor (just above whatever is left), so they are removed
    and the floor shows there instead: no hole. Stored, so --undo brings them back."""
    skin = [m.name if m else "" for m in body.data.materials].index("Skin")
    gh = body.vertex_groups["head"].index
    dl = bm.verts.layers.deform.verify()
    bm.normal_update()                                 # smooth_seam moved the border: some faces turned over
    bm.verts.index_update()
    bm.verts.ensure_lookup_table()
    t0 = store["tube_v0"]
    _, tube_r = tube_radius(bm, t0)
    folds = []
    for f in bm.faces:
        if f.material_index != skin or f.normal.z < FOLD_NZ or any(v.index >= t0 or v[dl].get(gh, 0.0) <= 0.5 for v in f.verts):
            continue
        c = f.calc_center_median()
        r, a = polar(c)
        if FLAT_Z[0] < c.z < FLAT_Z[1] and tube_r(a, c.z) + 0.002 < r < FOLD_R:
            folds.append(f)
    remove_faces(bm, folds, store)
    report["underside_folds_removed"] = len(folds)


def plan_floor(body, bm, store):
    """Where the floor goes, per angle of the tube: the gap in the underside (from the tube's top ring out to the
    first solid underside, rb), the underside's height just past it (zb) and the floor's rim (ro)."""
    t0 = store["tube_v0"]
    tube, tube_r = tube_radius(bm, t0)
    under, _ = head_rays(body, bm, t0)
    ang = 2 * np.pi * np.arange(TUBE_SEG) / TUBE_SEG - np.pi            # the tube's own angles (add_neck)
    rb, zb = floor_profile(under, tube[-1], ang)
    ro = np.maximum.reduce([np.roll(rb, i) for i in (-1, 0, 1)]) + FLOOR_OVER
    ro = np.maximum((np.roll(ro, 1) + ro + np.roll(ro, -1)) / 3, tube[-1] + 0.03)
    return dict(ang=ang, rt=tube[-1], rb=rb, zb=zb, ro=ro, tube_r=tube_r)


def at(plan, key, a):
    """A per-angle value of the plan at any angle (rad), interpolated around the circle."""
    ang = plan["ang"]
    return float(np.interp(a, np.r_[ang, ang[0] + 2 * np.pi], np.r_[plan[key], plan[key][0]], period=2 * np.pi))


def clear_gap(body, bm, store, report, plan):
    """What is left of the underside inside the gap is pieces: long teeth that reached into the hood roll, some
    10 cm out. Flat-shaded, patchy and lit at odd angles, they looked like blue shards on the floor. At the angles
    with a gap (wider than 1 cm) every face whose centre lies under the floor (inside its rim less FLOOR_KEEP,
    outside the tube) is removed, and the rim is pushed out to FLOOR_KEEP past all of each such face, so the floor
    alone shows there and covers everything they covered. Stored with the folds."""
    skin = [m.name if m else "" for m in body.data.materials].index("Skin")
    gh = body.vertex_groups["head"].index
    dl = bm.verts.layers.deform.verify()
    t0 = store["tube_v0"]
    bm.verts.index_update()
    tube_r = plan["tube_r"]
    gone = []
    for f in bm.faces:
        if f.material_index != skin or any(v.index >= t0 or v[dl].get(gh, 0.0) <= 0.5 for v in f.verts):
            continue
        c = f.calc_center_median()
        r, a = polar(c)
        if (FLAT_Z[0] < c.z < FLAT_Z[1] and tube_r(a, c.z) + 0.002 < r < at(plan, "ro", a) - FLOOR_KEEP
                and at(plan, "rb", a) - at(plan, "rt", a) > 0.01):
            gone.append(f)
    ro, ang, seg = plan["ro"].copy(), plan["ang"], 2 * np.pi / TUBE_SEG
    for f in gone:                                     # points along every edge, 5 mm apart
        vs = [np.array(v.co) for v in f.verts]
        for p0, p1 in zip(vs, vs[1:] + vs[:1]):
            for t in np.linspace(0.0, 1.0, int(np.linalg.norm(p1 - p0) / 0.005) + 2):
                x, y = p0[:2] + t * (p1[:2] - p0[:2]) - np.array(AXIS)
                k = int(np.floor((np.arctan2(y, x) - ang[0]) / seg)) % TUBE_SEG
                for kk in (k, (k + 1) % TUBE_SEG):
                    ro[kk] = max(ro[kk], np.hypot(x, y) + FLOOR_KEEP)
    report["gap_pieces_removed"] = len(gone)
    report["floor_rim_pushed_cm"] = round(float((ro - plan["ro"]).max()) * 100, 1)
    plan["ro"] = ro
    remove_faces(bm, gone, store)


def flatten_floor(body, bm, store, report):
    """The underside of the head around the neck is a few long flat triangles, up to 12 cm, that share smooth
    vertex normals with the lip and the seam copies. Interpolated over such a triangle the normals ran into dark /
    glassy fins beside the neck when the head turned. These faces are shaded flat (their shape stays; the original
    smooth flags are stored for --undo). Nothing is cut here: an earlier pass removed the needle-thin ones and left
    holes that showed the hollow head; faces now go only where the floor covers them (drop_folds, clear_gap)."""
    mats = [m.name for m in body.data.materials]
    t0 = store["tube_v0"]
    bm.verts.index_update()
    bm.faces.index_update()
    bm.faces.ensure_lookup_table()
    flat = []
    for f in bm.faces:
        if mats[f.material_index] != "Skin" or not f.smooth or any(v.index >= t0 for v in f.verts):
            continue
        c = f.calc_center_median()
        if not (FLAT_Z[0] < c.z < FLAT_Z[1]) or np.hypot(c.x - AXIS[0], c.y - AXIS[1]) < FLAT_R:
            continue
        if max(e.calc_length() for e in f.edges) > FLAT_EDGE:
            flat.append(f)
    for f in flat:
        f.smooth = False
    store["_flat"] = flat                              # indices are taken at the end (see main)
    report["floor_faces_flat_shaded"] = len(flat)


def skin_blocks(body, mat_index):
    """The skin's colour texture in 32-texel blocks: mean colour (0..1 RGB) and spread (of the block and its
    neighbours, the largest), plus the lookup of a UV's block and a block's centre UV."""
    mat = body.data.materials[mat_index]
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    img = bsdf.inputs["Base Color"].links[0].from_node.image
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    B = 32
    ny, nx = h // B, w // B
    mean, spread = np.zeros((ny, nx, 3)), np.zeros((ny, nx))
    for by in range(ny):                                   # block rows one at a time (the image is large)
        blk = px[by * B * w * 4:(by + 1) * B * w * 4].reshape(B, nx, B, 4)[..., :3]
        mean[by], spread[by] = blk.mean((0, 2)), blk.std((0, 2)).max(-1)
    del px
    near = np.max([np.roll(np.roll(spread, i, 0), j, 1) for i in (-1, 0, 1) for j in (-1, 0, 1)], axis=0)

    def block(uv):
        return int(uv[1] % 1 * h) // B, int(uv[0] % 1 * w) // B

    def centre(b):
        return (b[1] + 0.5) * B / w, (b[0] + 0.5) * B / h

    return mean, near, block, centre


def flat_uv(blocks, uvs, target):
    """The UV (centre of a flat block, among the blocks of `uvs`) whose colour is closest to `target`."""
    mean, near, block, centre = blocks
    cand = np.array(sorted({block(uv) for uv in uvs}))
    score = np.linalg.norm(mean[cand[:, 0], cand[:, 1]] - target, axis=1) + 2.0 * near[cand[:, 0], cand[:, 1]]
    b = tuple(cand[int(np.argmin(score))])
    return centre(b), mean[b]


def floor_profile(under, rt, ang):
    """Per angle of the tube, going out from its top ring: the radius where the gap in the underside ends (the
    first solid underside, 3 rays in a row, over 5 rays across the segment) and the underside's height just past it."""
    sub = np.linspace(-0.5, 0.5, 5) * 2 * np.pi / TUBE_SEG
    step = 0.002
    rb, zb = rt.copy(), np.full(len(rt), np.nan)
    for k in range(len(rt)):
        hits = []
        for d in sub:
            r, run, last = rt[k] + step, 0, rt[k]
            while r < rt[k] + 0.14 and run < 3:
                z = under(r, ang[k] + d)
                run, last = (run + 1, last) if z is not None else (0, r)
                if z is not None:
                    hits.append((r, z))
                r += step
            rb[k] = max(rb[k], last)
        near_b = [z for r, z in hits if rb[k] < r <= rb[k] + 0.02]
        zb[k] = np.median(near_b) if near_b else np.nan
    zb = np.where(np.isnan(zb), np.nanmedian(zb), zb)
    return rb, (np.roll(zb, 1) + zb + np.roll(zb, -1)) / 3


def close_floor(body, bm, store, report, plan):
    """The head was open underneath. Its underside ends in a ragged border up to 19 cm from the neck axis that was
    sewn to the hood roll (the hood closed it); with the collar on the chest, the ring between that border and the
    neck tube showed the hollow head inside whenever the head turned or was seen from below. A floor closes it: a
    regular disc of rings, rigid on the head, at the height of the underside next to the border, from inside the
    neck tube (the tube meets it like a neck meets a head) out to past the border, everywhere a little above the
    old underside (so it only shows where the underside is missing), in the underside's colour. The border of the
    underside is then lifted into the floor, so no slit or step is left. Appended after the tube (undo removes it
    with the tube; the lifted underside is in `moved`)."""
    skin = [m.name if m else "" for m in body.data.materials].index("Skin")
    uvl = bm.loops.layers.uv.active
    t0 = store["tube_v0"]
    under, head = head_rays(body, bm, t0)
    rb = plan["rb"]
    # colour: the underside next to the border, from a flat patch of the skin texture
    blocks = skin_blocks(body, skin)
    near_border = []
    for f in head:
        r, a = polar(f.calc_center_median())
        if f.normal.z < -0.5 and 0.0 < r - at(plan, "rb", a) < 0.04:
            near_border.extend(lp[uvl].uv[:] for lp in f.loops)
    target = np.median([blocks[0][blocks[2](uv)] for uv in near_border], axis=0)
    uv, colour = flat_uv(blocks, [lp[uvl].uv[:] for f in head for lp in f.loops], target)
    n_even = even_colour(body, bm, store, plan, uv)
    floor = build_floor(body, bm, plan["tube_r"], (rb, plan["zb"] + FLOOR_GAP, plan["ro"], plan["ang"]), under, uv)
    lifted, left = seal_border(body, bm, floor, t0, plan["tube_r"], store)
    report["floor_vertices"], report["floor_faces"] = (FLOOR_RINGS + 1) * TUBE_SEG + 1, len(floor)
    report["floor_gap_cm"] = [round(float((rb - plan["rt"]).min()) * 100, 1), round(float((rb - plan["rt"]).max()) * 100, 1)]
    report["underside_vertices_lifted"], report["border_vertices_left"] = lifted, left
    report["floor_colour"] = [int(round(c * 255)) for c in colour]
    report["underside_faces_in_floor_colour"] = n_even


def even_colour(body, bm, store, plan, uv):
    """The texture of the underside next to the gap is patchy (dark where it was painted in the hood roll's shadow,
    light streaks): revealed when the head turns, those faces read as dark or light shards around the floor. At the
    angles with a gap, the underside faces under the floor's rim and within FLOOR_FADE past it take the floor's
    flat colour (their own UVs are stored for --undo). Returns how many."""
    skin = [m.name if m else "" for m in body.data.materials].index("Skin")
    gh = body.vertex_groups["head"].index
    dl = bm.verts.layers.deform.verify()
    uvl = bm.loops.layers.uv.active
    t0 = store["tube_v0"]
    step = 2 * np.pi / TUBE_SEG

    def gap(a):                                        # a gap wider than 1 cm at this angle or the next ones
        return max(at(plan, "rb", a + d) - at(plan, "rt", a + d) for d in (-step, 0.0, step)) > 0.01

    faces = []
    for f in bm.faces:
        if f.material_index != skin or any(v.index >= t0 or v[dl].get(gh, 0.0) <= 0.5 for v in f.verts):
            continue
        c = f.calc_center_median()
        r, a = polar(c)
        if FLAT_Z[0] < c.z < 0.57 and plan["tube_r"](a, c.z) + 0.002 < r < at(plan, "ro", a) + FLOOR_FADE and gap(a):
            faces.append(f)
    store["_uv"] = faces                               # indices are taken at the end (see main)
    store["uv_old"] = [float(x) for f in faces for lp in f.loops for x in lp[uvl].uv]
    for f in faces:
        for lp in f.loops:
            lp[uvl].uv = uv
    return len(faces)


def polar(co):
    """Distance from the neck axis and angle around it."""
    return np.hypot(co.x - AXIS[0], co.y - AXIS[1]), np.arctan2(co.y - AXIS[1], co.x - AXIS[0])


def tube_radius(bm, t0):
    """The neck tube's ring radii (ring, angle of add_neck) and its radius at any angle (rad) and height."""
    tube = np.array([[polar(bm.verts[t0 + i * TUBE_SEG + k].co)[0] for k in range(TUBE_SEG)] for i in range(len(TUBE))])
    tz = [z for z, _ in TUBE]

    def radius(a, z):
        return float(np.interp(z, tz, tube[:, int(round((a + np.pi) / (2 * np.pi) * TUBE_SEG)) % TUBE_SEG]))

    return tube, radius


def build_floor(body, bm, tube_r, prof, under, uv):
    """The floor: per angle at the underside's height next to the border (zf), one ring inside the tube, then
    FLOOR_RINGS rings from the tube out to the rim, never closer than FLOOR_GAP to the underside below (checked
    inside every face too), a hub closing it inside the tube; rigid on the head, facing down."""
    from mathutils import Vector
    rb, zf, ro, ang = prof
    gh = body.vertex_groups["head"].index
    dl = bm.verts.layers.deform.verify()
    sh = [bm.verts.layers.shape[k.name] for k in body.data.shape_keys.key_blocks]
    uvl = bm.loops.layers.uv.active
    rc = np.array([tube_r(ang[k], zf[k]) for k in range(TUBE_SEG)])      # where the floor meets the tube
    R = np.vstack([rc - 0.006, rc + (ro - rc) * (np.arange(1, FLOOR_RINGS + 1)[:, None] / FLOOR_RINGS)])
    Z = np.tile(zf, (FLOOR_RINGS + 1, 1))
    for j in range(FLOOR_RINGS + 1):
        for k in range(TUBE_SEG):
            zu = under(R[j, k], ang[k])
            Z[j, k] = Z[j, k] if zu is None else max(Z[j, k], zu + FLOOR_GAP)
    for _ in range(3):                                                 # no face may dip to the underside in between
        lift = np.zeros_like(Z)
        for j in range(FLOOR_RINGS):
            for k in range(TUBE_SEG):
                k2 = (k + 1) % TUBE_SEG
                a2 = ang[k] + (ang[k2] - ang[k]) % (2 * np.pi)
                for u in (0.25, 0.5, 0.75):
                    for w in (0.25, 0.5, 0.75):
                        r = (1 - w) * ((1 - u) * R[j, k] + u * R[j, k2]) + w * ((1 - u) * R[j + 1, k] + u * R[j + 1, k2])
                        z = (1 - w) * ((1 - u) * Z[j, k] + u * Z[j, k2]) + w * ((1 - u) * Z[j + 1, k] + u * Z[j + 1, k2])
                        zu = under(r, (1 - u) * ang[k] + u * a2)
                        if zu is not None and zu + FLOOR_GAP - z > 1e-4:
                            for jj, kk in ((j, k), (j, k2), (j + 1, k), (j + 1, k2)):
                                lift[jj, kk] = max(lift[jj, kk], zu + FLOOR_GAP - z)
        if not lift.any():
            break
        Z += lift

    skin = [m.name if m else "" for m in body.data.materials].index("Skin")
    uv = Vector(uv)

    def vert(co):
        v = bm.verts.new(co)
        for lay in sh:
            v[lay] = co
        v[dl][gh] = 1.0
        return v

    def face(vs, smooth):
        f = bm.faces.new(vs)
        f.material_index, f.smooth = skin, smooth
        for lp in f.loops:
            lp[uvl].uv = uv
        f.normal_update()
        if f.normal.z > 0:                                 # the floor faces down, out of the head
            f.normal_flip()
        return f

    rings = [[vert(Vector((AXIS[0] + R[j, k] * np.cos(ang[k]), AXIS[1] + R[j, k] * np.sin(ang[k]), Z[j, k])))
              for k in range(TUBE_SEG)] for j in range(FLOOR_RINGS + 1)]
    hub = vert(Vector((AXIS[0], AXIS[1], float(Z[0].mean()))))
    floor = [face([rings[0][k], rings[0][(k + 1) % TUBE_SEG], hub], False) for k in range(TUBE_SEG)]
    for r0, r1 in zip(rings[:-1], rings[1:]):
        floor += [face([r0[k], r0[(k + 1) % TUBE_SEG], r1[(k + 1) % TUBE_SEG], r1[k]], True) for k in range(TUBE_SEG)]
    bm.verts.index_update()
    return floor


def seal_border(body, bm, floor, t0, tube_r, store):
    """The open border of the head's underside (outside the tube) is lifted to just above the floor, and the
    underside around it follows with a fade over FLOOR_FADE (staying under the floor), so the underside runs
    into the floor and its edge is tucked away behind it: no slit, step or lip, nothing to see past the edge.
    A border vertex the floor passes more than FLOOR_LIFT above stays (none expected). Returns (lifted vertices,
    border vertices left)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree
    skin = floor[0].material_index
    gh = body.vertex_groups["head"].index
    dl = bm.verts.layers.deform.verify()
    sh = [bm.verts.layers.shape[k.name] for k in body.data.shape_keys.key_blocks]
    fv = sorted({v for f in floor for v in f.verts}, key=lambda v: v.index)
    fpos = {v: k for k, v in enumerate(fv)}
    ftree = BVHTree.FromPolygons([v.co.copy() for v in fv], [[fpos[v] for v in f.verts] for f in floor])
    up = Vector((0.0, 0.0, 1.0))

    def room(v):                                       # how far the floor is above v (None: no floor above)
        loc = ftree.ray_cast(v.co - Vector((0.0, 0.0, 0.01)), up, 0.1)[0]
        return None if loc is None else loc.z - v.co.z

    def outside(v):
        r, a = polar(v.co)
        return r > tube_r(a, v.co.z) + 0.001

    head = [v for v in bm.verts[:t0] if v[dl].get(gh, 0.0) > 0.5 and 0.50 < v.co.z < 0.56 and v.link_faces
            and all(f.material_index == skin for f in v.link_faces) and outside(v)]
    border = [v for v in head if any(len(e.link_faces) == 1 for e in v.link_edges)]
    lift, left = {}, 0
    for v in border:
        d = room(v)
        if d is None or d < 0:
            continue
        if d > FLOOR_LIFT:
            left += 1
            continue
        lift[v] = d + FLOOR_SEAL
    kd = KDTree(len(lift))
    for i, v in enumerate(lift):
        kd.insert(Vector((v.co.x, v.co.y, 0.0)), i)
    kd.balance()
    amount = list(lift.values())
    for v in head:
        if v in lift:
            continue
        near = kd.find_range(Vector((v.co.x, v.co.y, 0.0)), FLOOR_FADE)
        fade = max((amount[i] * (1.0 - smoothstep(0.0, FLOOR_FADE, dist)) for _, i, dist in near), default=0.0)
        d = room(v) if fade > 1e-5 else None
        if d is not None:
            lift[v] = min(fade, d - FLOOR_GAP / 2)
    n = 0
    for v, dz in sorted(lift.items(), key=lambda x: x[0].index):
        if dz <= 1e-5:
            continue
        d = Vector((0.0, 0.0, dz))
        v.co += d
        for lay in sh:
            v[lay] += d
        store["moved_i"].append(int(v.index))
        store["moved_d"].extend((0.0, 0.0, float(dz)))
        n += 1
    return n, left


def clear_normals(body):
    """Drop the custom split normals that an earlier run put on the body (the mesh keeps its own shading)."""
    if body.data.has_custom_normals:
        with bpy.context.temp_override(object=body, active_object=body):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()


# ---------------------------------------------------------------- sleeves and cuffs
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ring_frame(body, side):
    """Rest-pose cuff opening of one side: centre, axis pointing out of the sleeve, vertex ids."""
    from check_sleeves import cuff_ring
    rig = bpy.data.objects["Morfi_Rig"]
    ring = cuff_ring(body, rig, side)
    R = np.array([body.data.vertices[i].co[:] for i in ring])
    c = R.mean(0)
    a = np.linalg.svd(R - c)[2][2]
    elbow = np.array(rig.matrix_world @ rig.data.bones[f"forearm.{side}"].head_local)
    return c, (a if a @ (c - elbow) > 0 else -a), ring


def fix_cuff(body, bm, side, c, a, report, store):
    """The cuff turns with the hand at its opening and gives over to the forearm behind it."""
    group = {g.name: g.index for g in body.vertex_groups}
    dl = bm.verts.layers.deform.verify()
    gf, gh, gu = group[f"forearm.{side}"], group[f"hand.{side}"], group[f"upper_arm.{side}"]
    n = 0
    for v in bm.verts:
        if v.index >= store["nv0"] or v[dl].get(gu, 0.0) > 0.3 or not (v[dl].get(gf, 0.0) + v[dl].get(gh, 0.0)) > 0.3:
            continue
        p = np.array(v.co) - c
        ax = p @ a
        if ax < -CUFF_BAND or np.linalg.norm(p - ax * a) > 0.10 or ax > 0.02:
            continue
        fh = v[dl].get(gf, 0.0) + v[dl].get(gh, 0.0)
        hand = max(v[dl].get(gh, 0.0), CUFF_HAND * smoothstep(-CUFF_BAND, -0.004, ax) * fh)
        if v.index not in store["w_old"]:
            row = np.zeros(len(group))
            for gi, w in v[dl].items():
                row[gi] = w
            store["w_old"][v.index] = row
        v[dl][gh] = float(hand)
        v[dl][gf] = float(fh - hand)
        n += 1
    report[f"cuff_{side}_vertices_retargeted"] = n


def fresh_hand(ob):
    """The hand mesh as it was before the first run (kept as a fake-user mesh next to the real one)."""
    key = f"bodyfix_orig_{ob.name}"
    orig = bpy.data.meshes.get(key)
    if orig is None:
        orig = ob.data.copy()
        orig.name = key
        orig.use_fake_user = True
        orig["mesh_name"] = ob.data.name
        return
    old = ob.data
    name = orig["mesh_name"]
    new = orig.copy()
    del new["mesh_name"]
    ob.data = new
    bpy.data.meshes.remove(old)
    new.name = name


def remove_web(ob, side, report):
    """Cut the skin web between the fingers: faces that join two different fingers go away, and
    the vertices left at the cut follow only their own finger."""
    names = [g.name for g in ob.vertex_groups]
    fing = {f: [i for i, n in enumerate(names) if n.startswith(f) and n.endswith(f".{side}")]
            for f in ("thumb", "index", "middle", "ring")}
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    dl = bm.verts.layers.deform.verify()
    fn = list(fing)
    S = np.array([[sum(v[dl].get(g, 0.0) for g in fing[n]) for n in fn] for v in bm.verts])
    dom = np.where(S.max(1) > FINGER_MIN, S.argmax(1), -1)           # -1: palm / wrist
    cut = [f for f in bm.faces if len({dom[v.index] for v in f.verts} - {-1}) >= 2]
    bmesh.ops.delete(bm, geom=cut, context="FACES_ONLY")
    n_hard = 0                                                         # vertices blended between fingers
    for v in bm.verts:
        s = S[v.index]
        if (s > 0.05).sum() >= 2:
            keep = fn[int(s.argmax())]
            tot = sum(v[dl].values())
            for n in fn:
                if n != keep:
                    for g in fing[n]:
                        if g in v[dl]:
                            del v[dl][g]
            new = sum(v[dl].values())
            if new > 0:
                for g in list(v[dl].keys()):
                    v[dl][g] = v[dl][g] * tot / new
            n_hard += 1
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    report[f"web_{side}_faces_removed"], report[f"web_{side}_vertices_hardened"] = len(cut), n_hard


def fix_sleeves(body, bm, report, store):
    rig = bpy.data.objects["Morfi_Rig"]
    for side in ("L", "R"):
        ob = bpy.data.objects[f"Hand_{side}"]
        fresh_hand(ob)
        me = ob.data
        co0 = np.array([v.co[:] for v in me.vertices])
        c, a, _ = ring_frame(body, side)
        fix_cuff(body, bm, side, c, a, report, store)
        Mo = np.array(ob.matrix_world)
        W = co0 @ Mo[:3, :3].T + Mo[:3, 3]
        hb = rig.data.bones[f"hand.{side}"]
        o = np.array(rig.matrix_world @ hb.head_local)
        D = np.array(rig.matrix_world @ hb.tail_local) - o
        D /= np.linalg.norm(D)
        ax = (W - c) @ a                                    # behind the cuff plane < 0
        t = (W - o) @ D
        rv = (W - o) - np.outer(t, D)                       # from the hand axis
        rr = np.linalg.norm(rv, axis=1)
        k = 1.0 - (1.0 - WRIST_K) * smoothstep(0.0, -WRIST_FADE, ax) * (rr < WRIST_R)
        k *= 1.0 - smoothstep(-WRIST_TAPER[0], -WRIST_TAPER[1], ax) * (rr < WRIST_R)     # the hidden tail closes to the axis
        new = o + np.outer(t, D) + rv * k[:, None]
        Mi = np.linalg.inv(Mo)
        newo = new @ Mi[:3, :3].T + Mi[:3, 3]
        for i, v in enumerate(me.vertices):
            v.co = newo[i]
        me.update()
        report[f"wrist_{side}_vertices_slimmed"] = int((k < 0.999).sum())
        # the wrist inside the sleeve gives over to the forearm exactly like the cuff does
        gf, gh = ob.vertex_groups[f"forearm.{side}"], ob.vertex_groups[f"hand.{side}"]
        n = 0
        for i, v in enumerate(me.vertices):
            if ax[i] >= 0 or rr[i] >= WRIST_R:
                continue
            w = {e.group: e.weight for e in v.groups}
            fh = w.get(gf.index, 0.0) + w.get(gh.index, 0.0)
            if fh < 0.99:                                   # also skinned to fingers: leave alone
                continue
            h = CUFF_HAND * smoothstep(-CUFF_BAND, -0.004, ax[i])
            gh.add([i], float(h), "REPLACE")
            gf.add([i], float(1.0 - h), "REPLACE")
            n += 1
        report[f"wrist_{side}_vertices_follow_cuff"] = n
        remove_web(ob, side, report)


# ---------------------------------------------------------------- main
def main():
    a = args_()
    src = bpy.data.filepath
    if os.path.abspath(a.out) == os.path.abspath(src):
        sys.exit("refusing to overwrite the input blend")
    global TUCK, TUCK_IN
    TUCK = TUCK if a.tuck is None else a.tuck
    TUCK_IN = TUCK_IN if a.tuck_in is None else a.tuck_in
    body = bpy.data.objects["Morfi_Body"]
    bm = bmesh.new()
    bm.from_mesh(body.data)
    if restore(body, bm):                    # back to the original, then start again from a clean bmesh
        bm.to_mesh(body.data)
        bm.free()
        clear_normals(body)
        bm = bmesh.new()
        bm.from_mesh(body.data)
    store, report = {}, {}
    if a.undo:
        for side in ("L", "R"):
            fresh_hand(bpy.data.objects[f"Hand_{side}"])
        bm.to_mesh(body.data)
        bm.free()
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
        return
    fix_neck(body, bm, store, report)
    add_neck(body, bm, store, report)
    smooth_seam(body, bm, store, report)
    drop_folds(body, bm, store, report)
    plan = plan_floor(body, bm, store)
    clear_gap(body, bm, store, report, plan)
    flatten_floor(body, bm, store, report)
    close_floor(body, bm, store, report, plan)
    fix_sleeves(body, bm, report, store)
    store["w_idx"] = [int(i) for i in sorted(store["w_old"])]
    store["w_rows"] = [float(x) for i in sorted(store["w_old"]) for x in store["w_old"][i]]
    del store["w_old"], store["nv0"]
    # face indices as they will be saved: new faces fill the slots of removed ones, so only now are they final
    bm.faces.index_update()
    store["flat_f"] = [int(f.index) for f in store.pop("_flat")]
    store["uv_f"] = [int(f.index) for f in store.pop("_uv")]
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    body.data[STORE] = store
    print("REPORT", report)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("DONE", a.out)


if __name__ == "__main__":
    main()
