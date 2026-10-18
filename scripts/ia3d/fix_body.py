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
  * the long flat triangles of the head's underside are shaded flat and its needle-thin fins removed (flatten_floor), so
    their smooth normals / sharp tips no longer show beside the neck or over the hood edge when the head turns;
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
FIN_EDGE = 0.04              # and those longer than this that are also thin (area / edge^2 below FIN_ASPECT) are removed
FIN_ASPECT = 0.03
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
    if "gone_n" in st:                        # the old underside faces that the cup replaced come back
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


def flatten_floor(body, bm, store, report):
    """The floor of the head (its underside around the neck) is a few long flat triangles, up to 12 cm, that share
    smooth vertex normals with the lip and the seam copies. Interpolated over such a triangle the normals ran
    into dark / glassy fins that stuck out beside the neck as blue shards when the head turned. These faces are
    shaded flat (their shape stays; the original smooth flags are stored for --undo). The needle-thin ones (9 cm
    long, a few mm wide: nothing can see them under the hood in the rest pose) are removed; they are stored like
    the old cup faces, so --undo brings them back."""
    mats = [m.name for m in body.data.materials]
    uvl = bm.loops.layers.uv.active
    zone = []
    for f in bm.faces:
        if mats[f.material_index] != "Skin":
            continue
        c = f.calc_center_median()
        if FLAT_Z[0] < c.z < FLAT_Z[1] and np.hypot(c.x - AXIS[0], c.y - AXIS[1]) >= FLAT_R:
            zone.append(f)
    fins = []
    for f in zone:
        edge = max(e.calc_length() for e in f.edges)
        if edge > FIN_EDGE and f.calc_area() / edge ** 2 < FIN_ASPECT:
            fins.append(f)
    store["gone_v"] = [int(v.index) for f in fins for v in f.verts]
    store["gone_n"] = [len(f.verts) for f in fins]
    store["gone_m"] = [int(f.material_index) for f in fins]
    store["gone_s"] = [bool(f.smooth) for f in fins]
    store["gone_uv"] = [float(x) for f in fins for lp in f.loops for x in lp[uvl].uv]
    bmesh.ops.delete(bm, geom=fins, context="FACES_ONLY")
    report["fin_faces_removed"] = len(fins)
    bm.faces.index_update()
    bm.faces.ensure_lookup_table()
    flat = []
    for f in bm.faces:
        if mats[f.material_index] != "Skin" or not f.smooth:
            continue
        c = f.calc_center_median()
        if not (FLAT_Z[0] < c.z < FLAT_Z[1]) or np.hypot(c.x - AXIS[0], c.y - AXIS[1]) < FLAT_R:
            continue
        if max(e.calc_length() for e in f.edges) > FLAT_EDGE:
            flat.append(f)
    for f in flat:
        f.smooth = False
    store["flat_f"] = [int(f.index) for f in flat]
    report["floor_faces_flat_shaded"] = len(flat)


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
    flatten_floor(body, bm, store, report)
    fix_sleeves(body, bm, report, store)
    store["w_idx"] = [int(i) for i in sorted(store["w_old"])]
    store["w_rows"] = [float(x) for i in sorted(store["w_old"]) for x in store["w_old"][i]]
    del store["w_old"], store["nv0"]
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    body.data[STORE] = store
    print("REPORT", report)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("DONE", a.out)


if __name__ == "__main__":
    main()
