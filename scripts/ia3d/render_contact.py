"""Render an AI-generated model with the calibrated camera of each reference view.

The model is normalised to the project frame first (feet on z = 0, centred between
the feet, height with the cubes = 1.143, facing -Y), so the renders can be laid
next to the references and their silhouettes measured against references_masks/.

blender -b --factory-startup --python scripts/ia3d/render_contact.py -- \
    --model work/ia3d/morfi_glb1.glb --name glb1 --out work/ia3d/contact [--rotz 0] [--samples 32]
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from morfi.scene import place_camera  # noqa: E402

W, H = 1145, 1374
HEIGHT_WITH_CUBES = 1.143
VIEWS = ["front", "profile_left", "back", "profile_right", "three_quarter_front", "three_quarter_back"]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rotz", type=float, default=0.0, help="extra turn about Z (deg) so Morfi faces -Y")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--views", default=",".join(VIEWS))
    ap.add_argument("--orbit", action="store_true", help="frame the object itself (loose parts)")
    return ap.parse_args(argv)


def import_model(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path, forward_axis="NEGATIVE_Z", up_axis="Y")
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise ValueError(f"unsupported model: {path}")
    # Meshy exports carry a stray hidden helper sphere; drop meshes nobody would render.
    for ob in list(bpy.data.objects):
        if ob.type == "MESH" and (ob.hide_render or ob.hide_get() or ob.name.startswith("Icosphere")):
            bpy.data.objects.remove(ob, do_unlink=True)


def world_points():
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        M = np.array(ev.matrix_world)
        pts.append(co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3])
        ev.to_mesh_clear()
    return np.concatenate(pts)


def normalise(rotz):
    roots = [ob for ob in bpy.data.objects if ob.parent is None]
    pivot = bpy.data.objects.new("Norm", None)
    bpy.context.scene.collection.objects.link(pivot)
    for ob in roots:
        ob.parent = pivot
    pivot.rotation_euler = (0, 0, math.radians(rotz))
    bpy.context.view_layer.update()
    P = world_points()
    zmin, zmax = P[:, 2].min(), P[:, 2].max()
    s = HEIGHT_WITH_CUBES / (zmax - zmin)
    feet = P[P[:, 2] < zmin + 0.06 * (zmax - zmin)]
    cx, cy = feet[:, 0].mean(), feet[:, 1].mean()
    pivot.matrix_world = Matrix.Diagonal((s, s, s, 1)) @ Matrix.Translation((-cx, -cy, -zmin)) @ pivot.matrix_world
    bpy.context.view_layer.update()
    P = world_points()
    return {"scale": float(s), "bbox_min": P.min(0).round(4).tolist(), "bbox_max": P.max(0).round(4).tolist()}


def setup_scene(samples):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type == "CUDA"
        sc.cycles.device = "GPU"
    except Exception:  # no CUDA: CPU still works, just slower
        sc.cycles.device = "CPU"
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    world = bpy.data.worlds.new("Studio")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.9, 0.9, 0.9, 1)
    bg.inputs[1].default_value = 0.55
    sc.world = world
    rig = bpy.data.objects.new("LightRig", None)
    sc.collection.objects.link(rig)
    for name, energy, rot, size in (("Key", 3.2, (55, 0, -35), 8), ("Fill", 1.2, (65, 0, 50), 15),
                                    ("Rim", 2.0, (60, 0, 165), 5)):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy, ld.angle = energy, math.radians(size)
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = tuple(math.radians(a) for a in rot)
        lo.parent = rig
        sc.collection.objects.link(lo)
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam, rig


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_model(os.path.abspath(args.model))
    info = normalise(args.rotz)
    cam, rig = setup_scene(args.samples)
    cfg = json.load(open(os.path.join(ROOT, "config", "morfi.json"), encoding="utf-8"))
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    for view in args.views.split(","):
        c = cfg["camera_views"][view]
        if args.orbit:
            # loose garment: same azimuth as the view, framed on the object itself
            lo, hi = np.array(info["bbox_min"]), np.array(info["bbox_max"])
            mid = (lo + hi) / 2
            c = {"az": c["az"], "lens": 65.0, "roll": 0.0, "target": [0.0, 0.0, float(mid[2])],
                 "distance": float(1.9 * (hi[2] - lo[2]) / 1.143 * 2.5 / 1.9 * 1.15),
                 "height": float(mid[2] + 0.1 * (hi[2] - lo[2]))}
        place_camera(cam, c)
        rig.rotation_euler = (0, 0, math.radians(c["az"]))  # lights turn with the camera, as in the refs
        bpy.context.scene.render.filepath = os.path.join(args.out, f"{args.name}_{view}.png")
        bpy.ops.render.render(write_still=True)
    info["model"] = args.model
    with open(os.path.join(args.out, f"{args.name}_info.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    print("DONE", json.dumps(info))


if __name__ == "__main__":
    main()
