"""Rig the AI mesh with our own skeleton and region-aware skin weights.

blender -b --factory-startup --python scripts/ia3d/build_rig.py -- \
    --glb work/ia3d/morfi_esqueleto.glb --regions work/ia3d/regions/regions.npz --out work/ia3d/morfi_ia_rig.blend

Why not the AI's own rig: its weights let the right upper-arm bone move 23k vertices
(the face included), the spine bones own no vertex at all and the lower hoodie follows
the thighs (docs/ia3d.md). Here:
  * the mesh is normalised to the project frame (feet on z = 0, height with cubes 1.143,
    facing -Y) and welded at the UV seams (it is watertight once welded);
  * the bones keep the project's names (scripts/morfi/rig.py), so the viewer and the
    existing tools understand them, placed on the AI mesh's own landmarks;
  * body and limbs get Blender's heat weights, then rigid or semi-rigid zones are
    overridden: head (glasses and face included) on one bone, the cubes on `pixels`
    (for a little follow-through), the hood on `hood`, shoes on foot/toe, and the
    hood collar never follows the head.
"""
import argparse
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_contact as rc  # noqa: E402

# (head, tail) in the project frame, measured on the AI mesh (scripts/ia3d/dump_mesh.py:
# the AI rig's joints, the hood/head boundary at z 0.525 and the slice profile).
JOINTS = {
    "root": ((0, 0.0, 0.0), (0, 0.12, 0.0)),
    "hips": ((0, 0.050, 0.205), (0, 0.050, 0.285)),
    "spine": ((0, 0.050, 0.285), (0, 0.052, 0.365)),
    "chest": ((0, 0.052, 0.365), (0, 0.058, 0.445)),
    "neck": ((0, 0.058, 0.445), (0, 0.060, 0.515)),
    "head": ((0, 0.060, 0.515), (0, 0.050, 0.86)),
    "pixels": ((-0.045, -0.03, 0.99), (-0.045, -0.03, 1.08)),
    "hood": ((0, 0.205, 0.50), (0, 0.245, 0.38)),
}
SIDE_JOINTS = {  # left side (+X); the right side is mirrored
    "shoulder": ((0.045, 0.058, 0.44), (0.154, 0.057, 0.449)),
    "upper_arm": ((0.154, 0.057, 0.449), (0.234, 0.070, 0.391)),
    "forearm": ((0.234, 0.070, 0.391), (0.283, 0.039, 0.315)),
    "hand": ((0.283, 0.039, 0.315), (0.322, 0.042, 0.262)),
    "fingers": ((0.322, 0.042, 0.262), (0.300, 0.030, 0.205)),
    "thumb": ((0.283, -0.001, 0.301), (0.270, -0.046, 0.257)),
    "thigh": ((0.098, 0.055, 0.270), (0.105, 0.052, 0.181)),
    "shin": ((0.105, 0.052, 0.181), (0.105, 0.052, 0.100)),
    "foot": ((0.105, 0.052, 0.100), (0.141, -0.030, 0.035)),
    "toe": ((0.141, -0.030, 0.035), (0.165, -0.110, 0.030)),
}
PARENTS = {"hips": "root", "spine": "hips", "chest": "spine", "neck": "chest", "head": "neck",
           "pixels": "head", "hood": "chest"}
for _s in ("L", "R"):
    PARENTS.update({f"shoulder.{_s}": "chest", f"upper_arm.{_s}": f"shoulder.{_s}",
                    f"forearm.{_s}": f"upper_arm.{_s}", f"hand.{_s}": f"forearm.{_s}",
                    f"fingers.{_s}": f"hand.{_s}", f"thumb.{_s}": f"hand.{_s}",
                    f"thigh.{_s}": "hips", f"shin.{_s}": f"thigh.{_s}", f"foot.{_s}": f"shin.{_s}",
                    f"toe.{_s}": f"foot.{_s}"})
CONNECTED = {"spine", "chest", "neck", "head", "upper_arm", "forearm", "hand", "fingers", "shin", "foot", "toe"}

HEAD_CUT = (0.505, 0.535)       # neck -> head blend (hood ends at z 0.53)
PIXELS_CUT = (0.985, 1.0)        # head -> cubes
SHOE_TOP = 0.155
HEM_Z = 0.192                    # hoodie hem: below it only legs (and hands at the sides)
SPINE_KEYS = [(0.205, "hips"), (0.29, "spine"), (0.375, "chest"), (0.47, "neck")]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", required=True)
    ap.add_argument("--regions", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def joint_table():
    J = dict(JOINTS)
    for name, (h, t) in SIDE_JOINTS.items():
        J[f"{name}.L"] = (h, t)
        J[f"{name}.R"] = ((-h[0], h[1], h[2]), (-t[0], t[1], t[2]))
    return J


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def prepare_mesh():
    """Import, drop the AI rig, normalise, apply transforms and weld the UV seams."""
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    ob = next(o for o in bpy.data.objects if o.type == "MESH")
    rc.normalise(0.0)
    bpy.context.view_layer.update()
    mw = ob.matrix_world.copy()
    ob.modifiers.clear()
    ob.vertex_groups.clear()
    ob.parent = None
    ob.matrix_world = mw
    for o in list(bpy.data.objects):
        if o is not ob:
            bpy.data.objects.remove(o, do_unlink=True)
    me = ob.data
    me.transform(ob.matrix_world)
    ob.matrix_world.identity()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(me)
    bm.free()
    if me.has_custom_normals:
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for p in me.polygons:
        p.use_smooth = True
    ob.name = me.name = "Morfi_Body"
    del arm
    return ob


def build_armature(J):
    data = bpy.data.armatures.new("Morfi_Rig")
    rig = bpy.data.objects.new("Morfi_Rig", data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    eb = data.edit_bones
    for name, (h, t) in J.items():
        b = eb.new(name)
        b.head, b.tail, b.roll = Vector(h), Vector(t), 0.0
    for name, par in PARENTS.items():
        eb[name].parent = eb[par]
        if name.split(".")[0] in CONNECTED and (eb[name].head - eb[par].tail).length < 1e-4:
            eb[name].use_connect = True
    eb["root"].use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return rig


def heat_weights(ob, rig):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    mod = next(m for m in ob.modifiers if m.type == "ARMATURE")
    mod.use_deform_preserve_volume = True


def read_weights(ob):
    names = [g.name for g in ob.vertex_groups]
    W = np.zeros((len(ob.data.vertices), len(names)))
    for v in ob.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    return names, W


def write_weights(ob, names, W, prune=0.01, max_infl=4):
    idx = np.argsort(-W, axis=1)[:, :max_infl]
    keep = np.zeros_like(W, bool)
    np.put_along_axis(keep, idx, True, axis=1)
    W = np.where(keep & (W > prune), W, 0.0)
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    ob.vertex_groups.clear()
    groups = [ob.vertex_groups.new(name=n) for n in names]
    for j, g in enumerate(groups):
        nz = np.nonzero(W[:, j])[0]
        for i in nz:
            g.add([int(i)], float(W[i, j]), "REPLACE")
    return W


def vertex_labels(ob, regions):
    """Texture-colour label per vertex (analyze_regions.py ran on the same welded mesh)."""
    r = np.load(regions)
    label, names = r["label"], list(r["names"])
    if len(label) != len(ob.data.vertices):
        raise RuntimeError("regions.npz was made on a different mesh; rerun dump_mesh + analyze_regions")
    return label, names


def override(ob, names, W, label, lnames):
    P = np.array([v.co[:] for v in ob.data.vertices])
    x, y, z = P.T
    col = {n: j for j, n in enumerate(names)}

    def only(mask, bone, amount):
        """Blend vertices in `mask` towards 100 % `bone` by `amount` (0..1)."""
        a = amount[mask][:, None]
        target = np.zeros((mask.sum(), len(names)))
        target[:, col[bone]] = 1.0
        W[mask] = W[mask] * (1 - a) + target * a

    hoodie = label == lnames.index("hoodie")
    shoe = label == lnames.index("shoe")
    neck_col = np.hypot(x, y - 0.05) < 0.22

    # 0. torso: heat weighting hands a wide torso to the nearest limb bones (thighs own
    # the lower hoodie, shoulders the chest). Redistribute it along the spine by height,
    # keeping a little thigh near the hem and a little shoulder near the shoulders.
    owner = np.array(names)[W.argmax(1)]
    trunk_bones = {"hips", "spine", "chest", "neck", "shoulder.L", "shoulder.R", "thigh.L", "thigh.R"}
    torso = np.isin(owner, list(trunk_bones)) & (z > HEM_Z) & (z < HEAD_CUT[1])
    spine = np.zeros((len(z), len(names)))
    for i, (zk, bone) in enumerate(SPINE_KEYS):
        lo = SPINE_KEYS[i - 1][0] if i > 0 else -10.0
        hi = SPINE_KEYS[i + 1][0] if i < len(SPINE_KEYS) - 1 else 10.0
        up = np.clip((z - lo) / (zk - lo), 0, 1)
        down = np.clip((hi - z) / (hi - zk), 0, 1)
        w = np.where(z <= zk, up, down)
        if i == 0:
            w = np.where(z <= zk, 1.0, w)
        if i == len(SPINE_KEYS) - 1:
            w = np.where(z >= zk, 1.0, w)
        spine[:, col[bone]] = w
    for side in ("L", "R"):
        th = W[:, col[f"thigh.{side}"]] * (1 - smoothstep(HEM_Z, 0.27, z)) * 0.6
        sh = W[:, col[f"shoulder.{side}"]] * smoothstep(0.37, 0.43, z) * 0.7
        spine[:, col[f"thigh.{side}"]] = th
        spine[:, col[f"shoulder.{side}"]] = sh
    spine /= np.maximum(spine.sum(1, keepdims=True), 1e-9)
    W[torso] = spine[torso]

    # 1. the hood collar and hoodie never follow the head
    collar = hoodie & (z < HEAD_CUT[1] + 0.01) & neck_col
    W[collar, col["head"]] = 0.0
    # 2. head: rigid above the cut (face, glasses, temples included), blended through the neck
    hw = smoothstep(*HEAD_CUT, z)
    hw[collar] = 0.0
    only(z > HEAD_CUT[0], "head", hw)
    # 3. cubes on their own bone
    only(z > PIXELS_CUT[0] - 0.005, "pixels", smoothstep(*PIXELS_CUT, z))
    # 4. hood hanging on the back: follows `hood` (jiggle) away from the collar line
    back = hoodie & (y > 0.13) & (z > 0.33) & (z < HEAD_CUT[1]) & (np.abs(x) < 0.20)
    hood_amt = smoothstep(0.13, 0.20, y) * smoothstep(0.33, 0.40, z) * (1 - smoothstep(0.16, 0.20, np.abs(x)))
    only(back, "hood", hood_amt * 0.85)
    # 5. shoes: rigid on foot, the front part on toe
    for side, s in (("L", 1), ("R", -1)):
        m = (z < SHOE_TOP) & (x * s > 0.0) & (shoe | (z < 0.06))
        toe_amt = smoothstep(-0.02, -0.08, y)
        only(m, f"foot.{side}", np.ones(len(z)))
        only(m & (toe_amt > 0), f"toe.{side}", toe_amt)
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    return W


def smooth_weights(ob, names, W, iters=6, lock=None):
    """Laplacian smoothing of the weights on the mesh graph (skipping locked rigid zones)."""
    me = ob.data
    e = np.array([ed.vertices[:] for ed in me.edges])
    n = len(me.vertices)
    deg = np.bincount(e.ravel(), minlength=n).astype(float)
    for _ in range(iters):
        acc = np.zeros_like(W)
        np.add.at(acc, e[:, 0], W[e[:, 1]])
        np.add.at(acc, e[:, 1], W[e[:, 0]])
        avg = acc / np.maximum(deg, 1)[:, None]
        newW = 0.5 * W + 0.5 * avg
        if lock is not None:
            newW[lock] = W[lock]
        W = newW
    return W / np.maximum(W.sum(1, keepdims=True), 1e-9)


def add_leg_ik(rig, J):
    """Foot IK controls (feet stay planted while the hips move) and knee poles.

    foot_ik.<s> copies the foot bone (same rest orientation), parented to root, so
    the foot copies its rotation exactly; the shin's 2-bone IK reaches its head.
    """
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    eb = rig.data.edit_bones
    for s in ("L", "R"):
        foot = eb[f"foot.{s}"]
        ik = eb.new(f"foot_ik.{s}")
        ik.head, ik.tail, ik.roll = foot.head.copy(), foot.tail.copy(), foot.roll
        ik.parent = eb["root"]
        ik.use_deform = False
        knee = Vector(J[f"shin.{s}"][0])
        pole = eb.new(f"knee_pole.{s}")
        pole.head = knee + Vector((0, -0.30, 0))
        pole.tail = pole.head + Vector((0, -0.05, 0))
        pole.parent = eb["root"]
        pole.use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for s in ("L", "R"):
        pb = rig.pose.bones[f"foot_ik.{s}"]
        pb.rotation_mode = "QUATERNION"
        rig.pose.bones[f"knee_pole.{s}"].rotation_mode = "QUATERNION"
        shin = rig.pose.bones[f"shin.{s}"]
        c = shin.constraints.new("IK")
        c.name = "LegIK"
        c.target, c.subtarget = rig, f"foot_ik.{s}"
        c.pole_target, c.pole_subtarget = rig, f"knee_pole.{s}"
        c.chain_count = 2
        foot = rig.pose.bones[f"foot.{s}"]
        cr = foot.constraints.new("COPY_ROTATION")
        cr.name = "FootIK"
        cr.target, cr.subtarget = rig, f"foot_ik.{s}"
        # pick the pole angle that leaves the rest pose untouched
        bpy.context.view_layer.update()
        rest = {n: rig.data.bones[n].matrix_local.copy() for n in (f"thigh.{s}", f"shin.{s}")}
        best = None
        for deg in range(-180, 180, 5):
            c.pole_angle = np.radians(deg)
            bpy.context.view_layer.update()
            err = sum(float(np.abs(np.array(rig.pose.bones[n].matrix) - np.array(rest[n])).sum())
                      for n in rest)
            if best is None or err < best[0]:
                best = (err, deg)
        c.pole_angle = np.radians(best[1])
        print(f"leg IK {s}: pole angle {best[1]} deg, rest error {best[0]:.5f}")
    bpy.context.view_layer.update()


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rc.import_model(os.path.abspath(args.glb))
    ob = prepare_mesh()
    J = joint_table()
    rig = build_armature(J)
    add_leg_ik(rig, J)
    heat_weights(ob, rig)
    names, W = read_weights(ob)
    missing = [b.name for b in rig.data.bones if b.use_deform and b.name not in names]
    for m in missing:
        ob.vertex_groups.new(name=m)
    names, W = read_weights(ob)
    print("heat: bones without weights:", [n for j, n in enumerate(names) if W[:, j].max() < 0.05])
    label, lnames = vertex_labels(ob, args.regions)
    W = override(ob, names, W, label, lnames)
    z = np.array([v.co.z for v in ob.data.vertices])
    rigid = (z > HEAD_CUT[1] + 0.01) & (z < PIXELS_CUT[0] - 0.01)
    W = smooth_weights(ob, names, W, iters=4, lock=rigid)
    W = write_weights(ob, names, W)
    unweighted = int((W.sum(1) < 0.5).sum())
    print("WEIGHTS", {n: int((W[:, j] > 0.5).sum()) for j, n in enumerate(names)}, "unweighted", unweighted)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("DONE", args.out)


main()
