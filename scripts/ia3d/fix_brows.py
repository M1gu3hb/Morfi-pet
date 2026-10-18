"""Smooth skin around Morfi's brows: no more visible triangles when the brows move.

blender -b work/ia3d/morfi_ia_look5.blend --python scripts/ia3d/fix_brows.py -- \
    --out work/ia3d/morfi_ia_look6.blend [--features work/ia3d/face/face_features.json]

The Brow_* / Brow_In_* keys (build_face.brow_keys) lift a 72 x 40 mm ellipse by 26 mm and let the
lift die out over only 20-36 mm of coarse, uneven triangles (edges 4-55 mm), and the glasses frame
(6 mm under the brows) takes it away over 4 mm: the skin stretches up to 6.5x in a few slivers.
This post step (run after fix_glasses.py / fix_body.py):
  * splits the long edges of the skin around the brows (rest shape unchanged: flat midpoints, so
    every other key, UV, weight and colour attribute is interpolated and nothing moves);
  * rebuilds the four brow keys with the same lift and the same brow: every vertex on the painted
    brows (+ 3 mm) and next to the glasses frame keeps its old delta, and the rest of the lift
    weight is a biharmonic (thin-plate) surface over the mesh between those and a ring about twice
    as far as before, so the stretch spreads over many small triangles instead of a few long ones.
Idempotent: a body already fixed (mesh property `brows_fix`) is saved unchanged. --out must differ
from the input .blend.
"""
import argparse
import json
import os
import sys

import bmesh
import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MARK = "brows_fix"
FRAME_OLD = 0.004            # build_face: the key fades in over this distance from the glasses frame
FRAME_PIN = 0.0015           # skin this close to the frame keeps its old delta
INK_MARGIN = 0.003           # the painted brows (+ this) keep their old deltas
R_UP, R_DOWN = 1.9, 1.15     # ellipse radius (build_face units) where the lift is zero again (old: 1.0)
TARGET_NEAR, TARGET_FAR = 0.0035, 0.0060      # wanted edge length (m) inside / outside the ellipse r < R_UP
REGION = R_UP + 0.15         # triangles are refined inside this radius


def args_():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--features", default=os.path.join(ROOT, "work", "ia3d", "face", "face_features.json"))
    ap.add_argument("--lift", type=float, default=0.026)
    return ap.parse_args(argv)


def smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def face_maps(co, feats, face_dir):
    """Per vertex: distance (m) to the painted glasses frame and, per side, "on the painted brow"."""
    from PIL import Image
    from scipy import ndimage as ndi
    meta = feats["meta"]
    img = np.asarray(Image.open(os.path.join(face_dir, "face_albedo.png")).convert("RGB")).astype(float)
    navy = (img[..., 2] > img[..., 0] + 25) & (img.mean(-1) < 70)
    lab, n = ndi.label(navy)
    frame_id = 1 + int(np.argmax(ndi.sum(navy, lab, range(1, n + 1))))
    frame = ndi.binary_dilation(lab == frame_id, iterations=int(0.004 / meta["mpp"]))
    dist = ndi.distance_transform_edt(~frame) * meta["mpp"]
    u = ((co[:, 0] - meta["x0"]) / meta["mpp"]).round().astype(int).clip(0, frame.shape[1] - 1)
    v = ((meta["z1"] - co[:, 2]) / meta["mpp"]).round().astype(int).clip(0, frame.shape[0] - 1)
    ink = {}
    for side, b in feats["brows"].items():
        x0, z0, x1, z1 = b["bbox"]
        c0, c1 = int((x0 - meta["x0"]) / meta["mpp"]), int((x1 - meta["x0"]) / meta["mpp"])
        r0, r1 = int((meta["z1"] - z1) / meta["mpp"]), int((meta["z1"] - z0) / meta["mpp"])
        ids = lab[r0:r1 + 1, c0:c1 + 1]
        ids = ids[(ids > 0) & (ids != frame_id)]
        blob = np.isin(lab, np.unique(ids))
        blob = ndi.binary_dilation(blob, iterations=int(INK_MARGIN / meta["mpp"]))
        ink[side] = blob[v, u] & (co[:, 1] < 0)
    return dist[v, u], ink


def brow_geometry(feats, side):
    x0, z0, x1, z1 = feats["brows"][side]["bbox"]
    return (x0 + x1) / 2, (z0 + z1) / 2 + 0.004, (x1 - x0) / 2


def radius(co, cx, cz):
    return np.hypot((co[:, 0] - cx) / 0.072, (co[:, 2] - cz) / 0.040)


def old_weight(co, cx, cz, dist):
    """build_face.brow_keys: smoothstep of the ellipse radius, taken away near the glasses frame."""
    t = np.clip((1.0 - radius(co, cx, cz)) / 0.5, 0, 1)
    return t * t * (3 - 2 * t) * (co[:, 1] < 0.0) * np.clip(dist / FRAME_OLD, 0, 1)


def old_inner(co, cx, half, nose):
    """2*inner-1 of build_face: -1 .. 1 along the brow, towards the nose."""
    return np.clip(nose * (co[:, 0] - cx) / half, -1.0, 1.0)


def tri_quality(a, b, c):
    """2*sqrt(3)*area / sum of squared edges: 1 for an equilateral triangle, 0 for a flat one."""
    area = 0.5 * (b - a).cross(c - a).length
    return 3.4641 * area / max((b - a).length_squared + (c - b).length_squared + (a - c).length_squared, 1e-18)


def connect(a, b):
    """Cut the polygon that has both vertices between them."""
    f = next(f for f in a.link_faces if len(f.verts) > 3 and b in f.verts)
    bmesh.utils.face_split(f, a, b)


def triangulate_split(f, cut):
    """Triangulate a triangle whose edges were split at the verts in `cut` (1 to 3 of them), with no
    flat triangle: the new verts are joined to each other / to the far corner."""
    v = list(f.verts)
    n = len(v)
    new = [i for i in range(n) if v[i] in cut]
    if len(new) == 1:                                       # quad A M B C: M to C
        connect(v[new[0]], v[(new[0] + 2) % n])
    elif len(new) == 2:                                     # pentagon: cut the corner off, then the better diagonal
        i, j = new
        connect(v[i], v[j])
        q = next(g for g in v[i].link_faces if len(g.verts) == 4 and v[j] in g.verts)
        w = list(q.verts)
        k = w.index(v[i])
        a, b = (w[k], w[(k + 2) % 4]), (w[(k + 1) % 4], w[(k + 3) % 4])
        qa = min(tri_quality(w[0].co, w[1].co, w[2].co), tri_quality(w[0].co, w[2].co, w[3].co))
        qb = min(tri_quality(w[1].co, w[2].co, w[3].co), tri_quality(w[1].co, w[3].co, w[0].co))
        connect(*(a if (k % 2 == 0) == (qa >= qb) else b))
    else:                                                   # hexagon: the middle triangle, then the corners
        m = [v[i] for i in new]
        for x, y in ((m[0], m[1]), (m[1], m[2]), (m[2], m[0])):
            connect(x, y)


def refine(me, feats):
    """Split long edges around both brows until they are about TARGET long (flat: rest shape intact)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    sides = [brow_geometry(feats, s) for s in ("L", "R")]
    for rnd in range(5):
        pick = []
        for e in bm.edges:
            a, b = e.verts[0].co, e.verts[1].co
            m = (a + b) * 0.5
            if m.y > 0.0:
                continue
            r = min(np.hypot((m.x - cx) / 0.072, (m.z - cz) / 0.040) for cx, cz, _ in sides)
            if r > REGION:
                continue
            if (a - b).length > (TARGET_NEAR if r < R_UP else TARGET_FAR) * 1.4:
                pick.append(e)
        print(f"refine round {rnd}: {len(pick)} edges")
        if not pick:
            break
        cut = set()
        for e in pick:
            cut.add(bmesh.utils.edge_split(e, e.verts[0], 0.5)[1])
        faces = {f for v in cut for f in v.link_faces}
        for f in faces:
            if f.is_valid and len(f.verts) > 3:
                triangulate_split(f, cut)
    bm.to_mesh(me)
    bm.free()
    me.update()


def biharmonic(n, tris, co, pinned, values):
    """Smooth field over the mesh graph: minimises the squared Laplacian with `values` fixed on `pinned`."""
    import scipy.sparse as sp
    from scipy.sparse.linalg import spsolve
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e = np.unique(np.sort(e, 1), axis=0)
    wgt = 1.0 / np.maximum(np.linalg.norm(co[e[:, 0]] - co[e[:, 1]], axis=1), 1e-4)
    W = sp.coo_matrix((np.r_[wgt, wgt], (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    deg = np.asarray(W.sum(1)).ravel()
    L = sp.diags(1.0 / np.maximum(deg, 1e-9)) @ (sp.diags(deg) - W)          # random-walk Laplacian
    free = np.flatnonzero(~pinned)
    pin = np.flatnonzero(pinned)
    Lf = L[free][:, free].tocsr()
    Lp = L[free][:, pin].tocsr()
    A = (Lf.T @ Lf).tocsc()
    b = -(Lf.T @ (Lp @ values[pin]))
    out = values.copy()
    out[free] = spsolve(A, b)
    return out


def new_weights(co, tris, feats, dist, ink, side):
    cx, cz, _ = brow_geometry(feats, side)
    w_old = old_weight(co, cx, cz, dist)
    r = radius(co, cx, cz)
    up = smooth((co[:, 2] - cz) / 0.02 + 0.5)                   # 1 above the brow centre, 0 below
    r_zero = R_DOWN + (R_UP - R_DOWN) * up
    keep = ink[side] | ((dist < FRAME_PIN) & (r < r_zero))      # painted brow and the frame seam
    pinned = keep | (r >= r_zero) | (co[:, 1] >= 0.0)
    values = np.where(keep, w_old, 0.0)
    w = biharmonic(len(co), tris, co, pinned, values)
    free = ~pinned
    over = (w[free] > 1.0).sum(), (w[free] < 0.0).sum()
    print(f"brow {side}: pinned {int(keep.sum())} (ink {int(ink[side].sum())}), free {int(free.sum())}, "
          f"biharmonic overshoot above 1 / below 0: {over}, range {w.min():.3f} .. {w.max():.3f}")
    return np.clip(w, 0.0, 1.0)


def main():
    a = args_()
    if os.path.abspath(a.out) == os.path.abspath(bpy.data.filepath):
        sys.exit("--out must differ from the input .blend")
    body = bpy.data.objects["Morfi_Body"]
    me = body.data
    if me.get(MARK):
        print("brows already fixed: saved unchanged")
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
        return
    feats = json.load(open(a.features, encoding="utf-8"))
    face_dir = os.path.dirname(os.path.abspath(a.features))
    names = [f"Brow_{s}" for s in "LR"] + [f"Brow_In_{s}" for s in "LR"]
    sk = me.shape_keys
    for n in names:
        assert n in sk.key_blocks, f"missing shape key {n}"
    n0 = len(me.vertices)
    co0 = np.array([v.co[:] for v in me.vertices])
    dist0, _ = face_maps(co0, feats, face_dir)
    for s in "LR":                   # the formula must reproduce the keys as they are today
        cx, cz, half = brow_geometry(feats, s)
        nose = 1.0 if s == "R" else -1.0
        w = old_weight(co0, cx, cz, dist0)
        for name, fac in ((f"Brow_{s}", 1.0), (f"Brow_In_{s}", 0.9 * old_inner(co0, cx, half, nose))):
            buf = np.empty(n0 * 3)
            sk.key_blocks[name].data.foreach_get("co", buf)
            err = np.abs((buf.reshape(-1, 3) - co0)[:, 2] - a.lift * w * fac).max()
            print(f"{name}: formula vs stored delta, max error {err * 1000:.4f} mm")
            assert err < 5e-5, f"{name} differs from build_face.brow_keys"

    refine(me, feats)
    sk = me.shape_keys
    n1 = len(me.vertices)
    co = np.array([v.co[:] for v in me.vertices])
    assert np.abs(co[:n0] - co0).max() < 1e-9, "the refine step moved the rest shape"
    # fan-triangulated for the brow field only (fix_body adds quads)
    tris = np.array([(p.vertices[0], p.vertices[k], p.vertices[k + 1]) for p in me.polygons for k in range(1, len(p.vertices) - 1)])
    dist, ink = face_maps(co, feats, face_dir)
    for s in "LR":
        cx, cz, half = brow_geometry(feats, s)
        nose = 1.0 if s == "R" else -1.0
        w = new_weights(co, tris, feats, dist, ink, s)
        for name, fac in ((f"Brow_{s}", 1.0), (f"Brow_In_{s}", 0.9 * old_inner(co, cx, half, nose))):
            moved = co.copy()
            moved[:, 2] += a.lift * w * fac
            sk.key_blocks[name].data.foreach_set("co", moved.ravel())
    me[MARK] = 1
    print(f"vertices {n0} -> {n1}, faces {len(me.polygons)}")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("DONE", a.out)


main()
