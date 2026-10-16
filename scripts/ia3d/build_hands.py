"""Articulated hands for Morfi: thumb + 3 fingers, 3 phalanges each.

blender -b work/ia3d/morfi_ia_rig.blend --python scripts/ia3d/build_hands.py -- \
    --regions work/ia3d/regions/regions.npz --out work/ia3d/morfi_ia_rig.blend

The AI mesh has mitten hands (the three fingers are one fused block), which cannot point,
count or hold things. This replaces them, keeping the existing skeleton intact:
  * new hand meshes (Hand_L / Hand_R) are built as a smooth implicit surface (palm, thumb,
    index, middle, ring) sized and placed like the AI hands (measured: ~9.5 x 13.8 x 12.4 cm,
    sRGB 6/48/247), their wrists hidden inside the hoodie cuffs;
  * bones are ADDED under hand.<s>: index/middle/ring .01-.03 and thumb.02/.03; the existing
    `fingers.<s>` becomes the (non-deforming) parent of the three fingers at the knuckle line,
    and `thumb.<s>` is the thumb's first segment, so older actions keep working;
  * finger bones are rolled so that a positive local X rotation curls towards the palm;
  * the AI hand faces are deleted (vertices kept, so per-vertex data such as regions.npz
    stays valid).
"""
import argparse
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from skimage import measure

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SKIN_SRGB = (6, 48, 247)
FINGERS = {  # name: (offset across the palm towards the thumb, length, radius at base, radius at tip)
    # chunky cartoon fingers, like the AI mitten (thumb + 3 fingers)
    "index": (0.0290, 0.040, 0.0158, 0.0148),
    "middle": (0.0, 0.043, 0.0162, 0.0150),
    "ring": (-0.0290, 0.037, 0.0152, 0.0142),
}
PHALANX = (0.42, 0.32, 0.26)      # share of each segment in the finger length
KNUCKLE_D = 0.068                 # knuckle line, along the hand from the wrist
REST_CURL = (0.30, 0.36, 0.28)    # a relaxed bend modelled in, so fists and points need smaller turns


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--voxel", type=float, default=0.0013)
    return ap.parse_args(argv)


# ---------------------------------------------------------------- frame and layout
def hand_frame(rig, side):
    """Wrist origin, D along the hand, F towards the thumb (forward), N out of the palm."""
    hb = rig.data.bones[f"hand.{side}"]
    o = np.array(hb.head_local)
    D = np.array(hb.tail_local) - o
    D /= np.linalg.norm(D)
    F = np.array([0.0, -1.0, 0.0])
    F -= (F @ D) * D
    F /= np.linalg.norm(F)
    N = np.cross(D, F)
    if np.sign(N[0]) == (1 if side == "L" else -1):   # the palm faces the body
        N = -N
    return o, D, F, N


def chain_points(base, direction, length, curl_axis, curls):
    """Joint positions of a 3-segment digit bent by `curls` about `curl_axis`."""
    pts = [np.asarray(base, float)]
    d = np.asarray(direction, float)
    for share, c in zip(PHALANX, curls):
        d = rotate(d, curl_axis, c)
        pts.append(pts[-1] + d * length * share)
    return pts


def rotate(v, axis, ang):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    return (v * math.cos(ang) + np.cross(axis, v) * math.sin(ang) + axis * (axis @ v) * (1 - math.cos(ang)))


def layout(o, D, F, N, side):
    """Every digit as joints (world space) + radii; also the palm box."""
    digits = {}
    for name, (off, length, r0, r1) in FINGERS.items():
        base = o + D * KNUCKLE_D + F * off + N * 0.004
        # curl axis: a positive turn about it moves D towards +N (into the palm)
        axis = np.cross(D, N)
        digits[name] = {"pts": chain_points(base, D, length, axis, REST_CURL), "r": (r0, r1), "axis": axis}
    tb = o + D * 0.022 + F * 0.040 + N * 0.012
    tdir = D * 0.55 + F * 0.75 + N * 0.38
    tdir /= np.linalg.norm(tdir)
    tbend = N - F * 0.6 + D * 0.2                      # the thumb folds across the palm
    taxis = np.cross(tdir, tbend)
    taxis /= np.linalg.norm(taxis)
    digits["thumb"] = {"pts": chain_points(tb, tdir, 0.050, taxis, (0.12, 0.22, 0.22)), "r": (0.0180, 0.0158),
                       "axis": taxis, "bend": tbend / np.linalg.norm(tbend)}
    palm = {"c": o + D * 0.040 + N * 0.002, "half": np.array([0.036, 0.046, 0.0290]), "round": 0.020}
    return digits, palm


# ---------------------------------------------------------------- implicit surface
def sd_capsule(P, a, b, ra, rb):
    pa, ba = P - a, b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0, 1)
    return np.linalg.norm(pa - np.outer(h, ba), axis=1) - (ra + (rb - ra) * h)


def sd_round_box(Q, half, r):
    q = np.abs(Q) - (half - r)
    return np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(1), 0) - r


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def parts_sdf(P, o, D, F, N, digits, palm):
    """Signed distance of each part (list) at points P (world)."""
    R = np.stack([D, F, N], 1)                       # world -> hand frame
    Q = (P - palm["c"]) @ R
    parts = {"palm": sd_round_box(Q, palm["half"], palm["round"])}
    # wrist: hidden inside the cuff
    parts["wrist"] = sd_capsule(P, o - D * 0.035, o + D * 0.02, 0.029, 0.031)
    for name, dg in digits.items():
        pts, (r0, r1) = dg["pts"], dg["r"]
        for i in range(3):
            ra = r0 + (r1 - r0) * i / 3
            rb = r0 + (r1 - r0) * (i + 1) / 3
            parts[f"{name}.{i + 1:02d}"] = sd_capsule(P, pts[i], pts[i + 1], ra, rb)
    return parts


def mesh_hand(o, D, F, N, digits, palm, voxel):
    corners = [palm["c"]] + [p for dg in digits.values() for p in dg["pts"]] + [o - D * 0.04]
    lo = np.min(corners, 0) - 0.03
    hi = np.max(corners, 0) + 0.03
    xs, ys, zs = (np.arange(lo[i], hi[i], voxel) for i in range(3))
    G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
    parts = parts_sdf(G, o, D, F, N, digits, palm)
    d = smin(parts["palm"], parts["wrist"], 0.012)
    for name in digits:
        # each digit is one smooth tube; fingers meet the palm with a soft web
        dig = parts[f"{name}.01"]
        for i in (2, 3):
            dig = smin(dig, parts[f"{name}.{i:02d}"], 0.004)
        d = smin(d, dig, 0.010 if name == "thumb" else 0.007)
    vol = d.reshape(len(xs), len(ys), len(zs))
    verts, faces, _n, _v = measure.marching_cubes(vol, 0.0, spacing=(voxel, voxel, voxel))
    verts = verts + lo
    return verts, faces[:, ::-1]


def skin_weights(V, o, D, F, N, digits, palm, bone_of):
    parts = parts_sdf(V, o, D, F, N, digits, palm)
    names = list(parts)
    Dm = np.stack([parts[n] for n in names], 1)
    W = np.exp(-(Dm - Dm.min(1, keepdims=True)) / 0.0022)
    keep = np.argsort(Dm, 1)[:, :2]                    # a joint blends its two segments only
    mask = np.zeros_like(W, bool)
    np.put_along_axis(mask, keep, True, 1)
    W = np.where(mask, W, 0.0)
    W /= W.sum(1, keepdims=True)
    out = {}
    for j, n in enumerate(names):
        b = bone_of(n)
        out[b] = out.get(b, 0) + W[:, j]
    return out


# ---------------------------------------------------------------- bones
def add_bones(rig, side, digits, o, D, N):
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    eb = rig.data.edit_bones
    hand = eb[f"hand.{side}"]
    # fingers.<s>: control at the knuckle line (no deform), parent of the three fingers
    fc = eb[f"fingers.{side}"]
    knuck = np.mean([digits[n]["pts"][0] for n in FINGERS], 0)
    fc.use_connect = False
    fc.parent = hand
    fc.head = Vector(knuck)
    fc.tail = Vector(knuck + D * 0.03)
    fc.align_roll(Vector(N))
    fc.use_deform = False
    for name in FINGERS:
        pts = digits[name]["pts"]
        prev = fc
        for i in range(3):
            b = eb.new(f"{name}.{i + 1:02d}.{side}")
            b.head, b.tail = Vector(pts[i]), Vector(pts[i + 1])
            b.align_roll(Vector(N))                      # local Z out of the palm
            b.parent = prev
            b.use_connect = i > 0
            prev = b
    th = digits["thumb"]["pts"]
    t1 = eb[f"thumb.{side}"]
    t1.use_connect = False
    t1.parent = hand
    t1.head, t1.tail = Vector(th[0]), Vector(th[1])
    t_bend = digits["thumb"]["bend"]                     # local Z towards the bend: +X turn folds it
    t1.align_roll(Vector(t_bend))
    prev = t1
    for i in (1, 2):
        b = eb.new(f"thumb.{i + 1:02d}.{side}")
        b.head, b.tail = Vector(th[i]), Vector(th[i + 1])
        b.align_roll(Vector(t_bend))
        b.parent = prev
        b.use_connect = True
        prev = b
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"


def smooth_on_mesh(me, W, iters=10):
    """Laplacian smoothing of the weights along the surface: soft joints, no creases."""
    names = list(W)
    M = np.stack([W[n] for n in names], 1)
    e = np.array([ed.vertices[:] for ed in me.edges])
    deg = np.bincount(e.ravel(), minlength=len(M)).astype(float)
    for _ in range(iters):
        acc = np.zeros_like(M)
        np.add.at(acc, e[:, 0], M[e[:, 1]])
        np.add.at(acc, e[:, 1], M[e[:, 0]])
        M = 0.5 * M + 0.5 * acc / np.maximum(deg, 1)[:, None]
    M /= M.sum(1, keepdims=True)
    return {n: M[:, j] for j, n in enumerate(names)}


def bone_name(side):
    def f(part):
        if part in ("palm", "wrist"):
            return f"hand.{side}"
        name, seg = part.split(".")
        if name == "thumb":
            return f"thumb.{side}" if seg == "01" else f"thumb.{seg}.{side}"
        return f"{name}.{seg}.{side}"
    return f


def skin_material():
    mat = bpy.data.materials.get("Skin_Hand") or bpy.data.materials.new("Skin_Hand")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    lin = [((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92 for c in SKIN_SRGB]
    b.inputs["Base Color"].default_value = (*lin, 1.0)
    b.inputs["Roughness"].default_value = 0.62
    b.inputs["Sheen Weight"].default_value = 0.6
    b.inputs["Sheen Roughness"].default_value = 0.35
    b.inputs["Sheen Tint"].default_value = (0.55, 0.72, 1.0, 1.0)
    b.inputs["Specular IOR Level"].default_value = 0.35
    return mat


def build_hand(rig, side, voxel):
    o, D, F, N = hand_frame(rig, side)
    digits, palm = layout(o, D, F, N, side)
    add_bones(rig, side, digits, o, D, N)
    V, Fc = mesh_hand(o, D, F, N, digits, palm, voxel)
    me = bpy.data.meshes.new(f"Hand_{side}")
    me.from_pydata([tuple(v) for v in V], [], [tuple(f) for f in Fc])
    me.update()
    ob = bpy.data.objects.new(f"Hand_{side}", me)
    bpy.context.scene.collection.objects.link(ob)
    # tidy: a light smooth and a decimation keep the shape and halve the triangles
    bpy.context.view_layer.objects.active = ob
    for mod_type, attrs in (("SMOOTH", {"factor": 0.5, "iterations": 4}), ("DECIMATE", {"ratio": 0.30})):
        mod = ob.modifiers.new(mod_type, mod_type)
        for k, v in attrs.items():
            setattr(mod, k, v)
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.materials.append(skin_material())
    P = np.array([v.co[:] for v in ob.data.vertices])
    W = skin_weights(P, o, D, F, N, digits, palm, bone_name(side))
    W = smooth_on_mesh(ob.data, W, iters=10)
    for bname, w in W.items():
        g = ob.vertex_groups.new(name=bname)
        for i in np.nonzero(w > 0.01)[0]:
            g.add([int(i)], float(w[i]), "REPLACE")
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    mod.use_deform_preserve_volume = True
    ob.parent = rig
    print(f"hand {side}: {len(ob.data.vertices)} verts, {len(ob.data.polygons)} faces, groups {list(W)}")
    return ob


def delete_ai_hands(body, regions):
    """Remove the AI mitten faces (keep the vertices: per-vertex data stays aligned)."""
    r = np.load(regions)
    col = r["colour"]
    co = np.array([v.co[:] for v in body.data.vertices])
    blue = col[:, 2] > col[:, 0] + 80
    hand = blue & (np.abs(co[:, 0]) > 0.225) & (co[:, 2] < 0.37) & (co[:, 2] > 0.15)
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    doomed = [f for f in bm.faces if all(hand[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=doomed, context="FACES_ONLY")
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    print(f"deleted {len(doomed)} AI hand faces")


def main():
    args = parse_args()
    rig = bpy.data.objects["Morfi_Rig"]
    body = bpy.data.objects["Morfi_Body"]
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    for side in ("L", "R"):
        build_hand(rig, side, args.voxel)
    delete_ai_hands(body, args.regions)
    # what is left of the body near the wrist (cuff) follows the hand, never the new digits
    for side in ("L", "R"):
        hand_g = body.vertex_groups[f"hand.{side}"]
        for old in (f"fingers.{side}", f"thumb.{side}"):
            g = body.vertex_groups.get(old)
            if g is None:
                continue
            for v in body.data.vertices:
                for e in v.groups:
                    if e.group == g.index and e.weight > 0:
                        hand_g.add([v.index], e.weight, "ADD")
            body.vertex_groups.remove(g)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("DONE", args.out)


if __name__ == "__main__":
    main()
