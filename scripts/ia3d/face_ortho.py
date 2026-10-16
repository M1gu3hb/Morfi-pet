"""Flat (unlit) orthographic front view of the face texture, for measuring the painted
eyes, mouth and brows in the project frame.

blender -b work/ia3d/morfi_ia_rig.blend --python scripts/ia3d/face_ortho.py -- --out work/ia3d/face

Writes face_albedo.png and face_ortho.json: pixel (u, v) <-> world x = x0 + u * mpp,
z = z1 - v * mpp (camera looks along +Y from the front).
"""
import json
import os
import sys

import bpy

X0, X1, Z0, Z1 = -0.33, 0.33, 0.50, 1.02
PX = 2200


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = os.path.abspath(argv[argv.index("--out") + 1])
    os.makedirs(out, exist_ok=True)
    body = bpy.data.objects["Morfi_Body"]
    rig = bpy.data.objects.get("Morfi_Rig")
    if rig and rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    mat = body.data.materials[0]
    nt = mat.node_tree
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image and n.image.size[0] >= 8192)
    out_node = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out_node.inputs["Surface"])
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    w = X1 - X0
    h = Z1 - Z0
    sc.render.resolution_x = PX
    sc.render.resolution_y = int(PX * h / w)
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.eevee.taa_render_samples = 8
    cd = bpy.data.cameras.new("Ortho")
    cd.type = "ORTHO"
    cd.ortho_scale = w
    cd.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("Ortho", cd)
    sc.collection.objects.link(cam)
    cam.location = ((X0 + X1) / 2, -2.0, (Z0 + Z1) / 2)
    cam.rotation_euler = (1.5707963, 0, 0)
    sc.camera = cam
    sc.render.filepath = os.path.join(out, "face_albedo.png")
    bpy.ops.render.render(write_still=True)
    meta = {"x0": X0, "z1": Z1, "mpp": w / PX, "width": PX, "height": sc.render.resolution_y}
    with open(os.path.join(out, "face_ortho.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print("DONE", meta)


main()
