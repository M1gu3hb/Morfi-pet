"""Realistic materials, glass lenses and a soft studio for the animated AI Morfi.

blender -b work/ia3d/morfi_ia_anim.blend --python scripts/ia3d/build_look.py -- \
    --regions work/ia3d/regions/regions.npz --face work/ia3d/face --out work/ia3d/morfi_ia_look.blend

The AI texture has one flat material (its roughness map is ~0.9 everywhere, metal 0).
Each face is assigned a material from its texture colour and where it is on the body
(head / torso / shoes), and every material keeps the AI colour and normal maps but gets
its own surface response: velvet skin (sheen), cotton fleece hoodie, heather shirt,
polished metal zipper and aglets, leather-like shoes and glossy acetate frames. The
painted lenses get a real glass shell in front, so they catch reflections.
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_face import body_bvh, parent_to_bone  # noqa: E402  (pure helpers)

MATS = ["Skin", "Hoodie", "Shirt", "Metal", "Shoe", "Frame", "Brow"]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", required=True)
    ap.add_argument("--face", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


# ---------------------------------------------------------------- face classification
def classify(body, colours, brows):
    me = body.data
    co = np.array([v.co[:] for v in me.vertices])
    polys = [p.vertices[:] for p in me.polygons]
    tri = np.array([p[:3] for p in polys])
    c = colours[tri].mean(1)
    P = co[tri].mean(1)
    x, y, z = P.T
    lum = c.mean(1)
    sat = c.max(1) - c.min(1)
    blue = (c[:, 2] > c[:, 0] + 60)
    idx = np.zeros(len(polys), int)                       # Skin
    head = z > 0.525
    dark = lum < 65
    in_brow = np.zeros(len(polys), bool)
    for b in brows.values():
        x0, z0, x1, z1 = b["bbox"]
        in_brow |= (x > x0 - 0.01) & (x < x1 + 0.01) & (z > z0 - 0.012) & (z < z1 + 0.025) & (y < 0)
    idx[head & dark & ~in_brow] = MATS.index("Frame")
    idx[head & dark & in_brow] = MATS.index("Brow")
    torso = (z > 0.155) & ~head
    idx[torso & dark] = MATS.index("Hoodie")
    light = ~dark & ~blue & (sat < 45)
    idx[torso & light] = MATS.index("Shirt")
    # metal (zipper teeth, pullers, aglets) is light grey AND surrounded by the black hoodie;
    # the shirt's grey shadows are surrounded by shirt
    from scipy.spatial import cKDTree
    tree = cKDTree(P)
    cand = np.nonzero(torso & light & (lum > 110) & (lum < 230))[0]
    near = tree.query_ball_point(P[cand], r=0.012)
    frac = np.array([dark[nb].mean() if len(nb) else 0.0 for nb in near])
    idx[cand[frac > 0.40]] = MATS.index("Metal")
    # the blue M printed on the shirt front belongs to the shirt
    logo = torso & blue & (np.abs(x) < 0.07) & (y < -0.05) & (z > 0.3) & (z < 0.47)
    idx[logo] = MATS.index("Shirt")
    shoe = (z < 0.155) & (~blue | (z < 0.05) | ((c[:, 2] > 200) & (y > 0.05)))
    idx[shoe & (z < 0.155)] = MATS.index("Shoe")
    return idx


# ---------------------------------------------------------------- materials
def _fine_bump(nt, strength, scale, detail=4.0, distortion=0.0, kind="noise"):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale * 0.70, scale * 0.52, scale * 1.14)   # isotropic on the body
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    if kind == "noise":
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Detail"].default_value = detail
        tex.inputs["Distortion"].default_value = distortion
        out = tex.outputs["Fac"]
    else:
        tex = nt.nodes.new("ShaderNodeTexVoronoi")
        tex.feature = "DISTANCE_TO_EDGE"
        out = tex.outputs["Distance"]
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(out, bump.inputs["Height"])
    return bump


def make_material(name, base_img, normal_img, spec):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = base_img
    col = tex.outputs["Color"]
    if spec.get("tint"):
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        nt.links.new(col, mul.inputs[6])
        mul.inputs[7].default_value = spec["tint"]
        col = mul.outputs[2]
    if spec.get("value"):                                 # brighten / darken the albedo a little
        hsv = nt.nodes.new("ShaderNodeHueSaturation")
        hsv.inputs["Value"].default_value = spec["value"]
        hsv.inputs["Saturation"].default_value = spec.get("saturation", 1.0)
        nt.links.new(col, hsv.inputs["Color"])
        col = hsv.outputs["Color"]
    nt.links.new(col, bsdf.inputs["Base Color"])
    ntex = nt.nodes.new("ShaderNodeTexImage")
    ntex.image = normal_img
    ntex.image.colorspace_settings.name = "Non-Color"
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = spec.get("normal", 1.0)
    nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
    normal = nmap.outputs["Normal"]
    if spec.get("bump"):
        bump = _fine_bump(nt, *spec["bump"])
        nt.links.new(normal, bump.inputs["Normal"])
        normal = bump.outputs["Normal"]
    nt.links.new(normal, bsdf.inputs["Normal"])
    for k, v in spec.get("bsdf", {}).items():
        bsdf.inputs[k].default_value = v
    return mat


SPECS = {
    # velvet / flocked vinyl, like the references: soft sheen at grazing angles
    "Skin": {"bsdf": {"Roughness": 0.62, "Sheen Weight": 0.6, "Sheen Roughness": 0.35,
                      "Sheen Tint": (0.55, 0.72, 1.0, 1.0), "Specular IOR Level": 0.35},
             "bump": (0.10, 1400.0, 3.0), "normal": 0.8},
    "Hoodie": {"bsdf": {"Roughness": 0.9, "Sheen Weight": 0.7, "Sheen Roughness": 0.5,
                        "Sheen Tint": (0.7, 0.72, 0.78, 1.0), "Specular IOR Level": 0.2},
               "bump": (0.22, 900.0, 6.0, 0.4), "normal": 1.0},
    "Shirt": {"bsdf": {"Roughness": 0.92, "Sheen Weight": 0.45, "Sheen Roughness": 0.5,
                       "Specular IOR Level": 0.25},
              "bump": (0.12, 1600.0, 5.0), "normal": 0.8, "value": 0.9},
    "Metal": {"bsdf": {"Roughness": 0.24, "Metallic": 1.0, "Specular IOR Level": 0.6},
              "normal": 1.0, "value": 1.25, "saturation": 0.3},
    "Shoe": {"bsdf": {"Roughness": 0.45, "Specular IOR Level": 0.45, "Coat Weight": 0.15,
                      "Coat Roughness": 0.25},
             "bump": (0.05, 700.0, 4.0), "normal": 0.9, "value": 0.86},
    "Frame": {"bsdf": {"Roughness": 0.3, "Specular IOR Level": 0.4, "Coat Weight": 0.35,
                       "Coat Roughness": 0.12},
              "normal": 0.6},
    "Brow": {"bsdf": {"Roughness": 0.7, "Sheen Weight": 0.4, "Sheen Roughness": 0.4}, "normal": 0.8},
}


def assign_materials(body, idx):
    old = body.data.materials[0]
    base = next(n.image for n in old.node_tree.nodes if n.type == "TEX_IMAGE" and n.image.size[0] >= 8192)
    normal = next(n.image for n in old.node_tree.nodes if n.type == "TEX_IMAGE" and n.image.name.startswith("normal"))
    body.data.materials.clear()
    for name in MATS:
        body.data.materials.append(make_material(name, base, normal, SPECS[name]))
    body.data.polygons.foreach_set("material_index", idx)
    body.data.update()


# ---------------------------------------------------------------- glass lenses
def glass_material():
    mat = bpy.data.materials.new("Lens_Glass")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Roughness"].default_value = 0.03
    fres = nt.nodes.new("ShaderNodeFresnel")
    fres.inputs["IOR"].default_value = 1.5
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fres.outputs["Fac"], mix.inputs["Fac"])
    nt.links.new(transp.outputs["BSDF"], mix.inputs[1])
    nt.links.new(gloss.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = True
    return mat


def lenses(tree, face_dir, rig, forward=0.012, res=44):
    from PIL import Image
    from scipy import ndimage as ndi
    meta = json.load(open(os.path.join(face_dir, "face_ortho.json")))
    mat = glass_material()
    obs = []
    for side in ("R", "L"):
        m = np.asarray(Image.open(os.path.join(face_dir, f"lens_{side}.png"))) > 127
        m = ndi.binary_erosion(ndi.binary_fill_holes(m), iterations=6)
        ys, xs = np.nonzero(m)
        x0 = meta["x0"] + xs.min() * meta["mpp"]
        x1 = meta["x0"] + xs.max() * meta["mpp"]
        z1 = meta["z1"] - ys.min() * meta["mpp"]
        z0 = meta["z1"] - ys.max() * meta["mpp"]
        gx = np.linspace(x0, x1, res)
        gz = np.linspace(z0, z1, res)
        verts, idx = [], {}
        for j, z in enumerate(gz):
            for i, x in enumerate(gx):
                u = int((x - meta["x0"]) / meta["mpp"])
                v = int((meta["z1"] - z) / meta["mpp"])
                if not m[min(max(v, 0), m.shape[0] - 1), min(max(u, 0), m.shape[1] - 1)]:
                    continue
                hit, nrm, _, _ = tree.ray_cast(Vector((x, -1.5, z)), Vector((0, 1, 0)))
                if hit is None:
                    continue
                idx[(i, j)] = len(verts)
                verts.append((x, hit.y - forward, z))
        faces = []
        for j in range(res - 1):
            for i in range(res - 1):
                q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                if all(k in idx for k in q):
                    faces.append([idx[k] for k in q])
        me = bpy.data.meshes.new(f"Lens_{side}")
        me.from_pydata(verts, [], faces)
        # smooth the projected surface (it copies the painted relief otherwise)
        co = np.array(verts)
        for _ in range(8):
            nb = np.zeros_like(co)
            cnt = np.zeros(len(co))
            for f in faces:
                for a in range(4):
                    for b in (f[(a + 1) % 4], f[(a + 3) % 4]):
                        nb[f[a]] += co[b]
                        cnt[f[a]] += 1
            co[:, 1] = 0.5 * co[:, 1] + 0.5 * (nb[:, 1] / np.maximum(cnt, 1))
        me.vertices.foreach_set("co", co.ravel())
        for p in me.polygons:
            p.use_smooth = True
        me.update()
        ob = bpy.data.objects.new(f"Lens_{side}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(mat)
        parent_to_bone(ob, rig, "head")
        obs.append(ob)
    return obs


def main():
    args = parse_args()
    body = bpy.data.objects["Morfi_Body"]
    rig = bpy.data.objects["Morfi_Rig"]
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    regions = np.load(args.regions)
    feats = json.load(open(os.path.join(args.face, "face_features.json"), encoding="utf-8"))
    idx = classify(body, regions["colour"], feats["brows"])
    print("MATERIAL FACES", {MATS[i]: int((idx == i).sum()) for i in range(len(MATS))})
    assign_materials(body, idx)
    tree = body_bvh(body)
    for ob in lenses(tree, args.face, rig):
        print("lens", ob.name, len(ob.data.polygons))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("DONE", args.out)


if __name__ == "__main__":
    main()
