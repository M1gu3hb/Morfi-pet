"""Morfi's glasses as real geometry: a clean frame, smooth lenses and a face that stays behind them.

blender -b work/ia3d/morfi_ia_look4.blend --python scripts/ia3d/fix_glasses.py -- \
    --out work/ia3d/morfi_ia_look5.blend

The AI painted AND sculpted the frame on the head (a 15-40 mm relief): its faces are coarse fans
with sliver bevels that read as facets under the coat, its border with the skin is a triangle
sawtooth, the cheek and mouth keys bent it, and the old lenses were a gridded copy of the face with
a staircase outline and a hole over the eye. This post step works on any look blend of the chain
and is idempotent (the original body data is stored on the mesh and restored first):
  * measures the painted frame on the head texture and its sculpted height in cylindrical
    coordinates around the head's vertical axis (front, corners and temples in one unwrapped map);
  * rebuilds it as one clean quad mesh, Glasses_Frame: smooth outline a little wider than the
    paint, the sculpted height, rounded edges, a lens groove and the temples, rigid on the head;
  * builds polar lenses (Lens_L / Lens_R) whose rim sits in that groove: one smooth dome over the
    whole opening;
  * flattens the old frame relief under the new frame, keeps the skin behind the eye decals, takes
    the glasses area out of the cheek / mouth keys (skin and mouth decal alike, every key kept
    consistent) and gives the old frame faces outside the new frame back to the skin or the hood.
"""
import argparse
import json
import os
import sys

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import glasses_geom as G  # noqa: E402
from build_face import parent_to_bone  # noqa: E402  (pure helper)

FLAT = 0.0010                # old relief under the new frame is pressed this far under the skin
OPEN_CAP = 0.0015            # ... and in the lens openings nothing stands higher than this
KEY_FEATHER = 0.012          # cheek / mouth keys fade in over this distance outside the glasses
GLASS_GLOSS = 0.45           # Lens_Glass mirror colour (build_look.py: 0.8)
STORE = "glasses_fix_orig"   # ID property with the original body data


def args_():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--debug", default="", help="folder for layout images and measurements")
    return ap.parse_args(argv)


# ---------------------------------------------------------------- measuring the painted frame
def load_texture(body):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    img = next(n.image for n in body.data.materials[0].node_tree.nodes
               if n.type == "TEX_IMAGE" and n.image and n.image.size[0] >= 8192)
    path = bpy.path.abspath(img.filepath)
    if path and os.path.exists(path):
        return np.asarray(Image.open(path).convert("RGB"))
    w, h = img.size                                     # packed: read its pixels
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    return (np.clip(px.reshape(h, w, 4)[::-1, :, :3], 0, 1) * 255 + 0.5).astype(np.uint8)


def sample_head(co, tri, uv, tex):
    """Outermost hit of rays coming in toward the head axis on a (z, theta) grid: radius + colour."""
    tree = BVHTree.FromPolygons([tuple(v) for v in co], [tuple(t) for t in tri])
    ths = np.arange(-G.TH_MAX, G.TH_MAX + 1e-9, G.DTH)
    zs = np.arange(G.Z0, G.Z1 + 1e-9, G.PX)
    sn, cs = np.sin(ths), np.cos(ths)
    R = np.full((len(zs), len(ths)), np.nan)
    hit = np.zeros((len(zs), len(ths), 3))
    fi = np.full((len(zs), len(ths)), -1)
    cast = tree.ray_cast
    for j, z in enumerate(zs):
        for i in range(len(ths)):
            p, _n, f, d = cast((sn[i] * 1.5, G.CY - cs[i] * 1.5, z), (-sn[i], cs[i], 0.0), 3.0)
            if p is not None:
                R[j, i], hit[j, i], fi[j, i] = 1.5 - d, p, f
    ok = fi >= 0
    f = fi[ok]
    a, b, c = co[tri[f, 0]], co[tri[f, 1]], co[tri[f, 2]]
    v0, v1, v2 = b - a, c - a, hit[ok] - a
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    w1 = (d11 * d20 - d01 * d21) / den
    w2 = (d00 * d21 - d01 * d20) / den
    t = uv[f, 0] * (1 - w1 - w2)[:, None] + uv[f, 1] * w1[:, None] + uv[f, 2] * w2[:, None]
    H, W = tex.shape[:2]
    rgb = np.zeros(R.shape + (3,), np.uint8)
    rgb[ok] = tex[np.clip(((1 - t[:, 1]) * H).astype(int), 0, H - 1), np.clip((t[:, 0] * W).astype(int), 0, W - 1)]
    return ths, zs, R, rgb


# ---------------------------------------------------------------- the new objects
def make_object(name, verts, faces, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(int(i) for i in f) for f in faces])
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def frame_material(colour):
    mat = bpy.data.materials.get("Glasses_Frame") or bpy.data.materials.new("Glasses_Frame")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    # the painted frame's colour; glossier than build_look.py's Frame (0.3 / coat 0.35): its
    # sharp highlights came from the painted streaks and the normal map, a smooth shell needs
    # a tighter reflection to read as the same black acetate
    vals = {"Base Color": (*colour, 1.0), "Roughness": 0.2, "Specular IOR Level": 0.4, "IOR": 1.5,
            "Coat Weight": 0.5, "Coat Roughness": 0.1, "Metallic": 0.0}
    for k, v in vals.items():
        bsdf.inputs[k].default_value = v
    return mat


def replace_lens(name, V, faces, mat, rig):
    """Keep the Lens_<side> object (name, parent, users), swap in the new mesh at rest."""
    ob = bpy.data.objects.get(name)
    me = bpy.data.meshes.new(name)
    if ob is None:
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        Minv = np.eye(4)
    else:
        old = ob.data
        ob.data = me
        if old.users == 0:
            bpy.data.meshes.remove(old)
        me.name = name
        Minv = np.linalg.inv(np.array(ob.matrix_world))
    loc = V @ Minv[:3, :3].T + Minv[:3, 3]
    me.from_pydata([tuple(v) for v in loc], [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    if ob.parent is None:
        parent_to_bone(ob, rig, "head")
    return ob


def tune_glass(mat, gloss):
    """Lens_Glass of build_look.py with a weaker mirror: the lens now covers the pupils too."""
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_GLOSSY":
            n.inputs["Color"].default_value = (gloss, gloss, gloss, 1.0)


# ---------------------------------------------------------------- the face under the glasses
KEY_NAMES = ("Cheek_L", "Cheek_R", "Mouth_Shift", "Jaw_Open")
LENS_CLEAR = 0.003           # skin at least this far behind the lens
DECAL_CLEAR = 0.0006         # skin at least this far behind the eye decals (along +Y, as projected)


def key_arrays(ob):
    me = ob.data
    out = {}
    for kb in me.shape_keys.key_blocks:
        a = np.zeros((len(me.vertices), 3))
        kb.data.foreach_get("co", a.ravel())
        out[kb.name] = a
    return out


def write_keys(ob, keys):
    me = ob.data
    basis = me.shape_keys.reference_key.name
    for name, a in keys.items():
        me.shape_keys.key_blocks[name].data.foreach_set("co", a.ravel())
    me.vertices.foreach_set("co", keys[basis].ravel())
    me.update()


def restore_body(body, mouth):
    """Undo a previous run (original vertices, keys and face materials are stored on the mesh)."""
    st = body.data.get(STORE)
    if st is None:
        return False
    keys = key_arrays(body)
    idx = np.array(st["v"], int)
    for name in keys:
        if name in st["keys"]:
            keys[name][idx] = np.array(st["keys"][name]).reshape(-1, 3)
    write_keys(body, keys)
    mi = np.zeros(len(body.data.polygons), int)
    body.data.polygons.foreach_get("material_index", mi)
    mi[np.array(st["f"], int)] = np.array(st["mat"], int)
    body.data.polygons.foreach_set("material_index", mi)
    if mouth is not None and "mouth" in st:
        mk = key_arrays(mouth)
        for name in mk:
            if name in st["mouth"]:
                mk[name] = np.array(st["mouth"][name]).reshape(-1, 3)
        write_keys(mouth, mk)
    del body.data[STORE]
    return True


def clear_behind(points, origins_dir, objs, clear):
    """Distance from each point along dir to the first of objs (BVH), inf if none."""
    dg = bpy.context.evaluated_depsgraph_get()
    trees = [BVHTree.FromObject(o, dg) for o in objs]
    mats = [np.linalg.inv(np.array(o.matrix_world)) for o in objs]
    out = np.full(len(points), np.inf)
    for t, Mi in zip(trees, mats):
        P = points @ Mi[:3, :3].T + Mi[:3, 3]
        D = origins_dir @ Mi[:3, :3].T
        for i, (p, d) in enumerate(zip(P, D)):
            hit = t.ray_cast(p, d, clear * 4)
            if hit[0] is not None:
                out[i] = min(out[i], hit[3])
    return out


def relax_surface(tri, ok, sel, s, z, iters=60):
    """Spread the selected vertices along the unwrapped surface (Laplacian in (s, z), the others
    and the unmapped ones fixed)."""
    import scipy.sparse as sp
    n = len(s)
    e = np.vstack([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    A = sp.coo_matrix((np.ones(2 * len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    A = A @ sp.diags(ok.astype(float))
    deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1.0)
    S = np.c_[s, z]
    for _ in range(iters):
        avg = (A @ S) / deg[:, None]
        S[sel] = 0.5 * S[sel] + 0.5 * avg[sel]
    return S[:, 0], S[:, 1]


def flatten_relief(U, tri, ok, brow, s, z, h, sdf_f, sdf_g, old):
    """The old sculpted frame (and its inner bevel, now behind the lens) goes flat: under the new
    frame, in the openings and on its sawtooth rims just outside. Away from the frame's outline
    the flattened vertices are also spread along the surface, so the old walls leave no collapsed
    slivers (not near it: the texture moves with them and the paint under the frame must stay
    hidden)."""
    df, dg = U.sample(sdf_f, s, z), U.sample(sdf_g, s, z)
    cap = lambda df, dg: np.where(dg < 0, np.minimum(-FLAT + 1.3 * np.maximum(df, 0.0), OPEN_CAP),  # noqa: E731
                                  -FLAT + 1.3 * np.maximum(df, 0.0))
    sel = ok & ~brow & ((df < 0.004) | (dg < 0)) & (h > cap(df, dg))
    free = sel & ((df < -0.0015) | ((df > 0.0008) & (dg < 0)))
    s2, z2 = relax_surface(tri, ok, free, s, z)
    crossed = np.sign(U.sample(sdf_f, s2, z2)) != np.sign(df)
    s2[crossed], z2[crossed] = s[crossed], z[crossed]
    new = old.copy()
    new[sel] = U.to3d(s2[sel], z2[sel], cap(U.sample(sdf_f, s2[sel], z2[sel]), U.sample(sdf_g, s2[sel], z2[sel])))
    return new, int(sel.sum())


def clear_openings(new, inner, lenses, eyes):
    """In the openings the skin stays LENS_CLEAR behind the lens and DECAL_CLEAR behind the eye
    decals (they are rigid: nothing pokes through them)."""
    n_lens = n_eye = 0
    idx = np.nonzero(inner)[0]
    for ob, nrm in lenses:
        dist = clear_behind(new[idx], np.tile(nrm, (len(idx), 1)), [ob], LENS_CLEAR)
        push = np.maximum(LENS_CLEAR - dist, 0.0)
        new[idx] -= push[:, None] * nrm[None]
        n_lens += int((push > 0).sum())
    for ob in eyes:
        E = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
        lo, hi = E.min(0), E.max(0)
        near = np.nonzero((new[:, 0] > lo[0]) & (new[:, 0] < hi[0]) & (new[:, 2] > lo[2]) & (new[:, 2] < hi[2])
                          & (new[:, 1] < hi[1] + 0.01))[0]
        start = new[near].copy()
        start[:, 1] = -1.5
        yd = -1.5 + clear_behind(start, np.tile([0.0, 1.0, 0.0], (len(near), 1)), [ob], 1.0)
        bad = np.isfinite(yd) & (new[near, 1] < yd + DECAL_CLEAR)
        new[near[bad], 1] = yd[bad] + DECAL_CLEAR
        n_eye += int(bad.sum())
    return n_lens, n_eye


def keyed(keys, basis_name, old, new, W):
    """Every key moves with the new basis; the cheek / mouth / jaw keys also fade out (1 - W)."""
    out = {}
    for name, a in keys.items():
        d = a - old
        if name in KEY_NAMES:
            d = d * (1.0 - W)[:, None]
        out[name] = new + d if name != basis_name else new
    return out


def fix_mouth_keys(mouth, U, sdf_g):
    """The mouth decal's lower-face keys fade out in the glasses area exactly like the skin's."""
    mk = key_arrays(mouth)
    basis = mouth.data.shape_keys.reference_key.name
    Mw = np.array(mouth.matrix_world)
    mb = mk[basis]
    ms, mz, _mh = U.from3d(mb @ Mw[:3, :3].T + Mw[:3, 3])
    W = 1.0 - G.smoothstep(0.0, KEY_FEATHER, U.sample(sdf_g, ms, mz))
    write_keys(mouth, keyed(mk, basis, mb, mb, W))
    return {n: a.ravel().tolist() for n, a in mk.items()}


def reassign_faces(body, U, new, tri, mi, mats, sdf_f):
    """Old frame faces outside the new frame are skin again (painted pupils and lens edges in the
    openings: no more glossy zig-zags), the ones along the hood line become hoodie."""
    cen = new[tri].mean(1)
    cs, cz, _ch = U.from3d(cen)
    cin = (cz > G.Z0) & (cz < G.Z1) & (np.abs(np.arctan2(cen[:, 0], G.CY - cen[:, 1])) < G.TH_MAX)
    dcf = np.where(cin, U.sample(sdf_f, cs, cz), 1.0)
    fi = mats.index("Frame") if "Frame" in mats else -1
    to_skin = (mi == fi) & (dcf > -0.0005) & (cen[:, 2] >= 0.56) & (cen[:, 1] < 0.0)
    to_hood = (mi == fi) & (cen[:, 2] < 0.56)
    nmi = mi.copy()
    if "Skin" in mats:
        nmi[to_skin] = mats.index("Skin")
    if "Hoodie" in mats:
        nmi[to_hood] = mats.index("Hoodie")
    body.data.polygons.foreach_set("material_index", nmi)
    return nmi, int(to_skin.sum()), int(to_hood.sum()), int((nmi == fi).sum())


def fix_body(body, mouth, U, sdf_f, sdf_g, lenses, eyes, report):
    keys = key_arrays(body)
    basis_name = body.data.shape_keys.reference_key.name
    old = keys[basis_name]
    s, z, h = U.from3d(old)
    ok = (np.abs(np.arctan2(old[:, 0], G.CY - old[:, 1])) < G.TH_MAX - 0.03) & (z > G.Z0 + 0.002) & (z < G.Z1 - 0.002)
    mats = [m.name if m else "" for m in body.data.materials]
    mi = np.zeros(len(body.data.polygons), int)
    body.data.polygons.foreach_get("material_index", mi)
    tri = np.array([p.vertices[:] for p in body.data.polygons])
    brow = np.zeros(len(old), bool)
    if "Brow" in mats:
        brow[tri[mi == mats.index("Brow")].ravel()] = True
    new, report["flattened_verts"] = flatten_relief(U, tri, ok, brow, s, z, h, sdf_f, sdf_g, old)
    df = np.where(ok, U.sample(sdf_f, s, z), 1.0)
    dg = np.where(ok, U.sample(sdf_g, s, z), 1.0)
    report["pushed_behind_lens"], report["pushed_behind_eye_decal"] = clear_openings(new, ok & (df > 0) & (dg < 0), lenses, eyes)
    W = np.where(ok, 1.0 - G.smoothstep(0.0, KEY_FEATHER, dg), 0.0)
    out = keyed(keys, basis_name, old, new, W)
    changed = np.nonzero(np.any([np.abs(out[n] - keys[n]).max(1) > 1e-9 for n in keys], axis=0))[0]
    store = {"v": changed.tolist(), "keys": {n: keys[n][changed].ravel().tolist() for n in keys}}
    write_keys(body, out)
    report["key_verts_faded"] = int((W > 1e-3).sum())
    if mouth is not None and mouth.data.shape_keys:
        store["mouth"] = fix_mouth_keys(mouth, U, sdf_g)
    nmi, report["faces_to_skin"], report["faces_to_hood"], report["frame_faces_under_new_frame"] = \
        reassign_faces(body, U, new, tri, mi, mats, sdf_f)
    fch = np.nonzero(nmi != mi)[0]
    store["f"], store["mat"] = fch.tolist(), mi[fch].tolist()
    body.data.update()
    body.data[STORE] = store


# ---------------------------------------------------------------- main
def srgb_to_linear(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def body_arrays(body):
    me = body.data
    co = np.zeros((len(me.vertices), 3))
    (me.shape_keys.reference_key.data if me.shape_keys else me.vertices).foreach_get("co", co.ravel())
    M = np.array(body.matrix_world)
    co = co @ M[:3, :3].T + M[:3, 3]
    tri = np.array([p.vertices[:3] for p in me.polygons])
    uvl = np.zeros((len(me.loops), 2))
    me.uv_layers.active.data.foreach_get("uv", uvl.ravel())
    ls = np.zeros(len(me.polygons), int)
    me.polygons.foreach_get("loop_start", ls)
    return co, tri, uvl[ls[:, None] + np.arange(3)[None, :]]


def rest_pose(rig):
    state = (rig.animation_data.action if rig.animation_data else None,
             {pb.name: pb.matrix_basis.copy() for pb in rig.pose.bones})
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    return state


def restore_pose(rig, state):
    action, basis = state
    if rig.animation_data:
        rig.animation_data.action = action
    for pb in rig.pose.bones:
        pb.matrix_basis = basis[pb.name]


def debug_layout(U, V2, F2, path):
    from PIL import Image, ImageDraw
    img = Image.fromarray(np.clip(U.rgb, 0, 255).astype(np.uint8)[::-1]).convert("RGB")
    dr = ImageDraw.Draw(img)
    H = len(U.zs)
    px = lambda p: ((p[0] - U.ss[0]) / G.PX, H - 1 - (p[1] - U.zs[0]) / G.PX)  # noqa: E731
    for f in F2:
        pts = [px(V2[i]) for i in f]
        dr.line(pts + pts[:1], fill=(255, 220, 0), width=1)
    img.save(path)


def main():
    a = args_()
    if os.path.abspath(a.out) == os.path.abspath(bpy.data.filepath):
        sys.exit("--out must differ from the input .blend")
    rig = bpy.data.objects["Morfi_Rig"]
    body = bpy.data.objects["Morfi_Body"]
    mouth = bpy.data.objects.get("Mouth_Decal")
    state = rest_pose(rig)
    report = {"restored_previous_run": restore_body(body, mouth)}
    co, tri, uv = body_arrays(body)
    ths, zs, R, rgb = sample_head(co, tri, uv, load_texture(body))
    U = G.Unwrap(ths, zs, R, rgb)
    M = G.measure(U)
    outer, holes = G.outline(U, M, G.MARGIN - G.ROUND)
    holes = [G.convex_hole(h) for h in holes]
    V2, F2, report["layout"] = G.build_layout(outer, holes)
    S, F3, grooves = G.build_frame(U, M, V2, F2)
    old = bpy.data.objects.get("Glasses_Frame")
    if old is not None:
        me = old.data
        bpy.data.objects.remove(old)
        bpy.data.meshes.remove(me)
    dark = M["mask"] & (U.rgb.mean(-1) < 32)
    colour = srgb_to_linear(np.median(U.rgb[dark], 0))
    frame = make_object("Glasses_Frame", U.to3d(S[:, 0], S[:, 1], S[:, 2]), F3, frame_material(colour))
    parent_to_bone(frame, rig, "head")
    report["frame"] = {"verts": len(S), "quads": len(F3), "tris": 2 * len(F3), "colour_linear": np.round(colour, 4).tolist()}
    glass = bpy.data.materials.get("Lens_Glass")
    if glass is None:
        from build_look import glass_material
        glass = glass_material()
    tune_glass(glass, GLASS_GLOSS)
    lenses = []
    grooves.sort(key=lambda g: g[:, 0].mean())             # R (-s) first
    for side, gr in zip("RL", grooves):
        V, faces, info, nrm = G.build_lens(U, gr)
        lenses.append((replace_lens(f"Lens_{side}", V, faces, glass, rig), nrm))
        report[f"lens_{side}"] = info
    bpy.context.view_layer.update()
    walls = []
    for L in G.boundary_loops(F2):
        P = V2[L]
        walls.append(P + G.ROUND * G.loop_normals(P, 1.0))
    outer_k = int(np.argmax([abs(G.signed_area(w)) for w in walls]))
    sdf_f, sdf_g = G.footprint(U, walls, outer_k)
    eyes = [o for o in (bpy.data.objects.get("Eye_Decal_R"), bpy.data.objects.get("Eye_Decal_L")) if o]
    fix_body(body, mouth, U, sdf_f, sdf_g, lenses, eyes, report)
    if a.debug:
        os.makedirs(a.debug, exist_ok=True)
        debug_layout(U, V2, F2, os.path.join(a.debug, "layout.png"))
        np.savez_compressed(os.path.join(a.debug, "measure.npz"), ss=U.ss, zs=U.zs, R=U.R, Rs=U.Rs, H=M["H"],
                            mask=M["mask"], sdf_f=sdf_f, sdf_g=sdf_g)
        with open(os.path.join(a.debug, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
    restore_pose(rig, state)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("GLASSES", json.dumps(report))
    print("DONE", a.out)


if __name__ == "__main__":
    main()
