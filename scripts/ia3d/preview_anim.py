"""Render a quick preview of an action (Eevee) to frames, an MP4 and a contact strip.

blender -b work/ia3d/morfi_ia_anim.blend --python scripts/ia3d/preview_anim.py -- \
    --action Wave --out work/ia3d/preview [--view three_quarter_front] [--res 0.45] [--step 1]
"""
import argparse
import json
import math
import os
import subprocess
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import render_contact as rc  # noqa: E402
from anim import rigmap  # noqa: E402
from morfi.scene import place_camera  # noqa: E402

FFMPEG = "ffmpeg"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--view", default="three_quarter_front")
    ap.add_argument("--res", type=float, default=0.45)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--engine", default="eevee")
    ap.add_argument("--zoom", type=float, default=1.25, help="camera distance factor (room for jumps)")
    ap.add_argument("--follow", action="store_true", help="camera follows the root (walks)")
    return ap.parse_args(argv)


def set_engine(name, samples=16):
    sc = bpy.context.scene
    if name == "eevee":
        for ident in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try:
                sc.render.engine = ident
                break
            except TypeError:
                continue
        sc.eevee.taa_render_samples = samples
        if hasattr(sc.eevee, "use_shadows"):
            sc.eevee.use_shadows = True
    else:
        sc.render.engine = "CYCLES"
        sc.cycles.samples = samples


def render_action(name, args, cam, rig, sc):
    action = bpy.data.actions[name]
    rigmap.assign(rig, action)
    out = os.path.abspath(os.path.join(args.out, name))
    os.makedirs(out, exist_ok=True)
    for old in os.listdir(out):
        if old.endswith(".png"):
            os.remove(os.path.join(out, old))
    frames = list(range(int(action.frame_start), int(action.frame_end) + 1, args.step))
    for i, f in enumerate(frames):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(out, f"f_{i:04d}.png")
        bpy.ops.render.render(write_still=True)
    mp4 = os.path.join(os.path.abspath(args.out), f"{name}.mp4")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-framerate", str(30 // args.step), "-i",
                    os.path.join(out, "f_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                    "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", mp4], check=True)
    print("DONE", mp4, len(frames))


def main():
    args = parse_args()
    rig = bpy.data.objects["Morfi_Rig"]
    cam, light_rig = rc.setup_scene(16)
    set_engine(args.engine)
    sc = bpy.context.scene
    sc.render.resolution_percentage = int(args.res * 100)
    sc.render.film_transparent = False
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.96, 0.96, 0.95, 1)
    cfg = json.load(open(os.path.join(ROOT, "config", "morfi.json"), encoding="utf-8"))
    c = dict(cfg["camera_views"][args.view])
    c["distance"] *= args.zoom
    c["target"] = [c["target"][0], c["target"][1], c["target"][2] + 0.03]
    place_camera(cam, c)
    light_rig.rotation_euler = (0, 0, math.radians(c["az"]))
    bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0))
    floor = bpy.context.active_object
    mat = bpy.data.materials.new("Floor")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.80, 0.82, 0.86, 1)
    mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    floor.data.materials.append(mat)
    if args.follow:                                   # walks: the camera rides on the root
        cam.parent = rig
        cam.parent_type = "BONE"
        cam.parent_bone = "root"
        cam.matrix_parent_inverse = (rig.matrix_world @ rig.pose.bones["root"].matrix).inverted()
    for name in args.action.split(","):
        render_action(name, args, cam, rig, sc)


main()
