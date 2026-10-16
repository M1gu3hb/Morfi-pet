"""Quick deformation test of a rigged GLB: put a few poses on it and render them.

blender -b --factory-startup --python scripts/ia3d/pose_test.py -- \
    --glb work/ia3d/morfi_esqueleto.glb --out work/ia3d/posetest --tag meshy [--blend file.blend]

Poses are applied as world-space rotations around each bone's head, so they mean
the same thing whatever the bone roll of the rig is. Bone roles are looked up in
ROLE_MAPS (Meshy "SmartRig" names, or the names of our own rig).
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from morfi.scene import place_camera  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "scripts", "ia3d"))
import render_contact as rc  # noqa: E402

MESHY = {
    "hips": "Bone_000", "spine": "Bone_001", "spine1": "Bone_004", "chest": "Bone_003",
    "neck": "Bone_002", "head": "Bone_022",
    "upper_arm.L": "Bone_016", "forearm.L": "Bone_015", "hand.L": "Bone_014",
    "upper_arm.R": "Bone_020", "forearm.R": "Bone_019", "hand.R": "Bone_018",
    "thigh.L": "Bone_012", "shin.L": "Bone_011", "foot.L": "Bone_010",
    "thigh.R": "Bone_008", "shin.R": "Bone_007", "foot.R": "Bone_006",
}

# (role, world axis, degrees). Morfi faces -Y, his left is +X, Z is up.
POSES = {
    # chibi wave: upper arm a bit above horizontal, forearm up and out, so the hand stays
    # outside the big head (+36 deg about +Y brings Morfi's right arm to horizontal)
    "saludo": [("upper_arm.R", (0, 1, 0), 52), ("upper_arm.R", (1, 0, 0), -12), ("forearm.R", (0, 1, 0), 62),
               ("hand.R", (0, 1, 0), 10), ("head", (0, 1, 0), -6), ("chest", (0, 1, 0), 3)],
    "paso": [("thigh.L", (1, 0, 0), 32), ("shin.L", (1, 0, 0), -40), ("thigh.R", (1, 0, 0), -22),
             ("shin.R", (1, 0, 0), -15), ("upper_arm.L", (1, 0, 0), -25), ("upper_arm.R", (1, 0, 0), 25),
             ("spine", (0, 0, 1), 6)],
    "cabeza": [("head", (0, 0, 1), 28), ("head", (0, 1, 0), 10), ("neck", (1, 0, 0), 8)],
    "agacharse": [("spine", (1, 0, 0), 14), ("chest", (1, 0, 0), 10), ("thigh.L", (1, 0, 0), 30),
                  ("thigh.R", (1, 0, 0), 30), ("shin.L", (1, 0, 0), -55), ("shin.R", (1, 0, 0), -55)],
    "brazos_fuera": [("upper_arm.L", (0, 1, 0), -40), ("upper_arm.R", (0, 1, 0), 40),
                     ("forearm.L", (0, 1, 0), -20), ("forearm.R", (0, 1, 0), 20)],
    "abrazo": [("upper_arm.L", (1, 0, 0), -70), ("upper_arm.R", (1, 0, 0), -70),
               ("upper_arm.L", (0, 0, 1), 25), ("upper_arm.R", (0, 0, 1), -25),
               ("forearm.L", (0, 0, 1), 40), ("forearm.R", (0, 0, 1), -40)],
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb")
    ap.add_argument("--blend")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--poses", default=",".join(POSES))
    ap.add_argument("--views", default="front,three_quarter_front")
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--res", type=float, default=0.5)
    ap.add_argument("--map", default="meshy")
    return ap.parse_args(argv)


def rotate_world(arm, pb, axis, deg):
    """Rotate a pose bone about a world axis through its head (armature space == world here)."""
    bpy.context.view_layer.update()
    M = arm.matrix_world.inverted() @ Matrix.Rotation(math.radians(deg), 4, Vector(axis)) @ arm.matrix_world
    head = pb.matrix.translation.copy()
    R = Matrix.Translation(head) @ M.to_3x3().to_4x4() @ Matrix.Translation(-head)
    pb.matrix = R @ pb.matrix
    bpy.context.view_layer.update()


def main():
    args = parse_args()
    if args.blend:
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.blend))
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.abspath(args.glb))
    for ob in list(bpy.data.objects):
        if ob.type == "MESH" and ob.name.startswith("Icosphere"):
            bpy.data.objects.remove(ob, do_unlink=True)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    roles = MESHY if args.map == "meshy" else {r: r for r in MESHY}
    if not args.blend:
        rc.normalise(0.0)  # feet on the floor, height with cubes 1.143, like the contact sheet
    cam, rig = rc.setup_scene(args.samples)
    sc = bpy.context.scene
    sc.render.resolution_percentage = int(args.res * 100)
    cfg = json.load(open(os.path.join(ROOT, "config", "morfi.json"), encoding="utf-8"))
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    for pose in ["reposo"] + args.poses.split(","):
        for pb in arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        for role, axis, deg in POSES.get(pose, []):
            name = roles.get(role)
            if name and name in arm.pose.bones:
                rotate_world(arm, arm.pose.bones[name], axis, deg)
        for view in args.views.split(","):
            c = cfg["camera_views"][view]
            place_camera(cam, c)
            rig.rotation_euler = (0, 0, math.radians(c["az"]))
            sc.render.filepath = os.path.join(out, f"{args.tag}_{pose}_{view}.png")
            bpy.ops.render.render(write_still=True)
    print("DONE")


main()
