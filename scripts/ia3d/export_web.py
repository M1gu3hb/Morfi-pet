"""Export the animated Morfi for the web viewer (web/live.html).

blender -b work/ia3d/morfi_ia_look.blend --python scripts/ia3d/export_web.py -- \
    --out work/ia3d/web/morfi_live.glb --face-json work/ia3d/web/morfi_live_face.json

glTF cannot carry Blender's procedural shaders or rig custom properties, so:
  * body materials are rebuilt glTF-friendly (texture 4K + normal 2K + constant
    roughness / sheen / clearcoat, colour tweaks as baseColorFactor);
  * the eye, mouth and lens objects keep their geometry and UVs and get placeholder
    materials named MorfiEye_R / MorfiEye_L / MorfiMouth / MorfiLens: the viewer
    replaces them with GLSL ports of the Blender shaders (web/src/live/face.ts);
  * the eye and mouth shader constants go to a JSON next to the GLB;
  * the face curves (blink, gaze, mouth...) are exported by export_face_anims.py.
Bones are sampled every frame, so the leg IK and foot roll are baked in.
"""
import argparse
import json
import os
import sys

import bpy
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from anim.actions import ACTIONS  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
EYE_KEYS = ["A", "B", "InCos", "InSin", "OutCX", "OutCY", "OutA", "OutB", "OutCos", "OutSin", "IrisX", "IrisY",
            "IrisR", "PupilR", "PupilDX", "PupilDY", "HlX", "HlY", "HlR", "GazeRangeX", "GazeRangeY", "AA"]
BSDF_KEYS = ["Roughness", "Metallic", "Sheen Weight", "Sheen Roughness", "Sheen Tint", "Coat Weight",
             "Coat Roughness", "Specular IOR Level"]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--face-json", required=True)
    ap.add_argument("--tex", type=int, default=4096)
    ap.add_argument("--normal", type=int, default=2048)
    return ap.parse_args(argv)


def downscale(img, size, path, fmt):
    """Write a smaller copy of a Blender image (read from its file or packed data) with PIL."""
    src = bpy.path.abspath(img.filepath) if img.filepath else ""
    if src and os.path.exists(src):
        im = Image.open(src).convert("RGB")
    else:                                              # packed (e.g. from the GLB): read its pixels
        import numpy as np
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        arr = (np.clip(px.reshape(h, w, 4)[::-1, :, :3], 0, 1) * 255 + 0.5).astype(np.uint8)
        im = Image.fromarray(arr)
    im = im.resize((size, size), Image.LANCZOS)
    im.save(path, quality=88) if fmt == "JPEG" else im.save(path)
    out = bpy.data.images.load(path)
    return out


def web_body_materials(body, out_dir, tex_size, normal_size):
    first = body.data.materials[0]
    base = next(n.image for n in first.node_tree.nodes if n.type == "TEX_IMAGE" and n.image.size[0] >= 8192)
    normal = next(n.image for n in first.node_tree.nodes if n.type == "TEX_IMAGE" and n.image.name.startswith("normal"))
    base_web = downscale(base, tex_size, os.path.join(out_dir, "morfi_live_color.jpg"), "JPEG")
    normal_web = downscale(normal, normal_size, os.path.join(out_dir, "morfi_live_normal.jpg"), "JPEG")
    normal_web.colorspace_settings.name = "Non-Color"
    for i, old in enumerate(list(body.data.materials)):
        src = next(n for n in old.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        vals = {k: (tuple(src.inputs[k].default_value) if hasattr(src.inputs[k].default_value, "__len__")
                    else src.inputs[k].default_value) for k in BSDF_KEYS}
        hsv = next((n for n in old.node_tree.nodes if n.type == "HUE_SAT"), None)
        value = hsv.inputs["Value"].default_value if hsv else 1.0
        mat = bpy.data.materials.new(old.name)
        old.name = old.name + "_render"
        mat.name = old.name.replace("_render", "")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = base_web
        if abs(value - 1.0) > 1e-3:                       # exported as baseColorFactor
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            nt.links.new(tex.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (value, value, value, 1.0)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        ntex = nt.nodes.new("ShaderNodeTexImage")
        ntex.image = normal_web
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
        for k, v in vals.items():
            bsdf.inputs[k].default_value = v
        body.data.materials[i] = mat


def placeholder(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1, 0, 1, 1)
    return mat


def eye_params(side):
    mat = bpy.data.materials[f"Eye_{side}"]
    grp = next(n for n in mat.node_tree.nodes if n.type == "GROUP")
    return {k: float(grp.inputs[k].default_value) for k in EYE_KEYS}


def main():
    args = parse_args()
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    rig = bpy.data.objects["Morfi_Rig"]
    body = bpy.data.objects["Morfi_Body"]
    face = {"eyes": {s: eye_params(s) for s in ("R", "L")}}
    sys.path.insert(0, HERE)
    import build_face as bf
    face["mouth"] = bf.MOUTH
    face["colors"] = {k: [round(c, 5) for c in v[:3]] for k, v in bf.COL.items()}   # linear RGB
    # the viewer drives everything from the face curves: drop the Blender drivers
    for ob in [body] + [o for o in bpy.data.objects if o.name.startswith(("Eye_Decal", "Mouth_Decal"))]:
        ob.animation_data_clear()
        if ob.data.shape_keys:
            ob.data.shape_keys.animation_data_clear()
            for kb in ob.data.shape_keys.key_blocks[1:]:
                kb.value = 0.0
    web_body_materials(body, out_dir, args.tex, args.normal)
    for side in ("R", "L"):
        bpy.data.objects[f"Eye_Decal_{side}"].data.materials[0] = placeholder(f"MorfiEye_{side}")
        bpy.data.objects[f"Lens_{side}"].data.materials[0] = placeholder("MorfiLens")
    bpy.data.objects["Mouth_Decal"].data.materials[0] = placeholder("MorfiMouth")
    # only Morfi's actions, each exported as its own clip
    for act in list(bpy.data.actions):
        if act.name not in ACTIONS:
            bpy.data.actions.remove(act)
    # bind every action's slot to the rig once (Blender 4.4+ only exports actions whose
    # slot has been used by the object), then leave the rig in its rest pose
    rig.animation_data_create()
    for name in ACTIONS:
        act = bpy.data.actions[name]
        rig.animation_data.action = act
        if hasattr(rig.animation_data, "action_slot") and getattr(act, "slots", None):
            rig.animation_data.action_slot = act.slots[0]
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.ops.object.select_all(action="DESELECT")
    for ob in [rig] + list(rig.children_recursive):
        ob.select_set(ob.type in ("ARMATURE", "MESH"))
    bpy.context.view_layer.objects.active = rig
    bpy.context.scene.render.fps = 30
    bpy.ops.export_scene.gltf(
        filepath=os.path.abspath(args.out), export_format="GLB", use_selection=True,
        export_yup=True, export_apply=False, export_texcoords=True, export_normals=True,
        export_tangents=False, export_materials="EXPORT", export_image_format="AUTO",
        export_skins=True, export_morph=True, export_morph_normal=False, export_try_sparse_sk=True,
        export_animations=True, export_animation_mode="ACTIONS", export_force_sampling=True,
        export_frame_step=1, export_anim_single_armature=True, export_reset_pose_bones=True,
        export_optimize_animation_size=False, export_cameras=False, export_lights=False, export_extras=False,
    )
    with open(os.path.abspath(args.face_json), "w", encoding="utf-8") as fh:
        json.dump(face, fh, indent=1)
    print("DONE", args.out, os.path.getsize(args.out) / 1e6, "MB")


main()
