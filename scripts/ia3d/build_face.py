"""Living face for the AI mesh: eye decals (gaze, blink, squint) and a mouth decal (talk).

blender -b work/ia3d/morfi_ia_rig.blend --python scripts/ia3d/build_face.py -- \
    --features work/ia3d/face/face_features.json --out work/ia3d/morfi_ia_face.blend

The AI painted the eyes flat on the lens surface (one layer, no eyeball behind). Each
eye gets a thin decal that follows that surface 0.8 mm in front, rigid on the head bone,
whose shader redraws the painted eye with the measured shapes and colours
(scripts/ia3d/measure_face.py) but lets the iris move inside the eye outline and the
lids close. The rig's custom properties (gaze_x/y, blink_L/R, squint, mouth_open, smile)
drive the shaders, so actions only key the rig.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nodeexpr import NodeExpr  # noqa: E402


def srgb(c):
    """sRGB 0-255 -> linear RGBA for node colour sockets."""
    out = []
    for v in c[:3]:
        v = v / 255.0
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


FACE_DIR = ""
COL = {
    "sclera": srgb((250, 251, 250)),
    "sclera_shade": srgb((205, 214, 228)),
    "iris_hi": srgb((6, 76, 214)),
    "iris_lo": srgb((4, 46, 138)),
    "iris_rim": srgb((3, 20, 56)),
    "pupil": srgb((14, 14, 16)),
    "outline": srgb((6, 22, 46)),
    "lid": srgb((86, 168, 250)),
    "lid_shade": srgb((62, 140, 230)),
    "highlight": srgb((255, 255, 255)),
    "mouth_in": srgb((66, 18, 16)),
    "mouth_lip": srgb((128, 56, 44)),
    "tongue": srgb((168, 78, 66)),
    "teeth": srgb((246, 246, 244)),
}


# ---------------------------------------------------------------- eye shader
def eye_group():
    ng = bpy.data.node_groups.new("MorfiEye", "ShaderNodeTree")
    E = NodeExpr(ng)
    uv = E.input("UV", "NodeSocketVector", None)
    A, B = E.input("A", default=0.076), E.input("B", default=0.068)
    ca, sa = E.input("InCos", default=1.0), E.input("InSin")
    ocx, ocy = E.input("OutCX"), E.input("OutCY")
    OA, OB = E.input("OutA", default=0.078), E.input("OutB", default=0.072)
    oca, osa = E.input("OutCos", default=1.0), E.input("OutSin")
    ix0, iy0 = E.input("IrisX"), E.input("IrisY")
    ir, pr = E.input("IrisR", default=0.061), E.input("PupilR", default=0.040)
    pdx, pdy = E.input("PupilDX"), E.input("PupilDY")
    hx, hy, hr = E.input("HlX"), E.input("HlY"), E.input("HlR", default=0.0107)
    gx, gy = E.input("GazeX"), E.input("GazeY")
    grx, gry = E.input("GazeRangeX", default=0.032), E.input("GazeRangeY", default=0.020)
    blink, squint = E.input("Blink"), E.input("Squint")
    aa = E.input("AA", default=0.0009)                       # edge softness (m)
    x, y, _ = E.sep(uv)                                       # metres from the eye centre

    # inner ellipse (the white, tilted like the painting) and the outline's outer edge
    xe = x * ca + y * sa
    ye = y * ca - x * sa
    q = E.length2(xe / A, ye / B)
    xo0, yo0 = x - ocx, y - ocy
    qo = E.length2((xo0 * oca + yo0 * osa) / OA, (yo0 * oca - xo0 * osa) / OB)
    inside = E.smoothstep(1.0 + aa / B, 1.0 - aa / B, q)      # eye area
    outer = E.smoothstep(1.0 + aa / OB, 1.0 - aa / OB, qo)    # eye + outline
    thick = E.max(OB - B, 0.002)                              # for the lids' lash line

    # iris follows the gaze, clipped by the eye
    icx = ix0 + gx * grx
    icy = iy0 + gy * gry
    di = E.length2(x - icx, y - icy)
    iris = E.smoothstep(ir + aa, ir - aa, di)
    dp = E.length2(x - icx - pdx, y - icy - pdy)
    pupil = E.smoothstep(pr + aa, pr - aa, dp)
    t_iris = ((di - pr) / (ir - pr)).clamp()
    iris_col = E.mix_color(COL["iris_hi"], COL["iris_lo"], E.smoothstep(0.25, 0.85, t_iris))
    iris_col = E.mix_color(iris_col, COL["iris_rim"], E.smoothstep(0.80, 1.0, t_iris))
    # highlight rides on the cornea: moves with the iris, a bit less
    dh = E.length2(x - (ix0 + gx * grx * 0.7 + hx), y - (iy0 + gy * gry * 0.7 + hy))
    hl = E.smoothstep(hr + aa * 0.8, hr - aa * 0.8, dh)
    hl2 = E.smoothstep(hr * 0.45 + aa * 0.6, hr * 0.45 - aa * 0.6,
                       E.length2(x - (ix0 + gx * grx * 0.7 - hx * 0.55), y - (iy0 + gy * gry * 0.7 - hy * 0.9)))
    # sclera: soft shadow under the upper lid and towards the rim -> reads as a ball
    shade = (E.smoothstep(0.80, 1.0, q) * 0.22 + E.smoothstep(0.35, 1.0, ye / B) * 0.30).clamp()
    col = E.mix_color(COL["sclera"], COL["sclera_shade"], shade)
    col = E.mix_color(col, iris_col, iris)
    col = E.mix_color(col, COL["pupil"], pupil)
    col = E.mix_color(col, COL["highlight"], (hl + hl2 * 0.0).clamp())

    # lids. Upper lid edge descends with blink; closed it rests as a soft arc ~35 % down.
    # lids move straight down in the face (not along the tilted eye axis)
    xn = x / A
    arc = (1.0 - xn * xn).clamp().sqrt()                       # ellipse top/bottom profile
    top_edge = arc * B
    closed_y = B * (-0.30 + 0.22 * (1.0 - xn * xn))            # closed: gentle downward-open arc
    lid_y = E.mix(top_edge + thick, closed_y, blink)
    bot_edge = -arc * B
    squint_y = B * (-0.62 + 0.25 * (1.0 - xn * xn))            # happy: lower lid rises
    low_open = E.mix(bot_edge - thick, squint_y, squint)
    low_y = E.mix(low_open, closed_y - 0.0015, blink)          # closed: lids meet
    upper_lid = E.smoothstep(lid_y - aa, lid_y + aa, y)
    lower_lid = E.smoothstep(low_y + aa, low_y - aa, y)
    lids = E.max(upper_lid, lower_lid)
    lash_w = 0.0030 + blink * 0.0022
    lash = E.smoothstep(lash_w + aa, lash_w - aa, (y - lid_y).abs()) * E.smoothstep(0.02, 0.15, blink + squint)
    lash2 = E.smoothstep(0.0022 + aa, 0.0022 - aa, (y - low_y).abs()) * E.smoothstep(0.02, 0.2, squint)
    # The lids are the body's own skin: the painted eye was erased from its texture
    # (inpaint_face.py), so where a lid covers the eye the decal is simply transparent.
    lash_a = E.max(lash, lash2) * inside
    ring = (outer - inside).clamp()
    # closing eyes lose the top of the outline (the lid covers it); the bottom stays as a lash line
    ring_vis = E.mix(1.0, E.smoothstep(0.15, -0.35, y / B), blink)
    ink = E.max(ring * ring_vis, lash_a)
    final = E.mix_color(col, COL["outline"], ink.clamp())
    alpha = E.max(inside * (1.0 - lids), ink)
    E.output("Color", final, "NodeSocketColor")
    E.output("Alpha", alpha.clamp())
    E.output("Lid", ink)
    return ng


def eye_material(name, rig, eye, side):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    grp = nt.nodes.new("ShaderNodeGroup")
    grp.node_tree = bpy.data.node_groups["MorfiEye"]
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "eye"
    nt.links.new(uvn.outputs["UV"], grp.inputs["UV"])
    cx, cz = eye["center"]
    inner, outer = eye["outline"]["inner"], eye["outline"]["outer"]
    ai, ao = math.radians(inner["angle_w"]), math.radians(outer["angle_w"])
    vals = {
        "A": inner["radii"][0], "B": inner["radii"][1], "InCos": math.cos(ai), "InSin": math.sin(ai),
        "OutCX": outer["center"][0] - cx, "OutCY": outer["center"][1] - cz,
        "OutA": outer["radii"][0], "OutB": outer["radii"][1], "OutCos": math.cos(ao), "OutSin": math.sin(ao),
        "IrisX": eye["iris_center"][0] - cx, "IrisY": eye["iris_center"][1] - cz,
        "IrisR": eye["iris_r"], "PupilR": eye["pupil_r"],
        "PupilDX": eye["pupil_center"][0] - eye["iris_center"][0],
        "PupilDY": eye["pupil_center"][1] - eye["iris_center"][1],
        "HlX": eye["highlights"][0][0] - eye["iris_center"][0],
        "HlY": eye["highlights"][0][1] - eye["iris_center"][1],
        "HlR": eye["highlights"][0][2],
    }
    for k, v in vals.items():
        grp.inputs[k].default_value = v
    # animated inputs are object attributes of the decal (driven from the rig, see
    # drive_props): changing them never recompiles the shader, unlike drivers on nodes
    for sock, prop in (("GazeX", "m_gaze_x"), ("GazeY", "m_gaze_y"), ("Blink", "m_blink"), ("Squint", "m_squint")):
        nt.links.new(attr_node(nt, prop), grp.inputs[sock])
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(grp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    # the lid is skin: rougher and with a touch of sheen
    rough = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(grp.outputs["Lid"], rough.inputs["Value"])
    rough.inputs["To Min"].default_value = 0.30
    rough.inputs["To Max"].default_value = 0.75
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    nt.links.new(grp.outputs["Alpha"], bsdf.inputs["Alpha"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    return mat


# ---------------------------------------------------------------- mouth shader
MOUTH = {"center": (-0.007, 0.6135), "half_width": 0.041, "corner_up": 0.006, "depth": 0.023,
         "skin": (105, 193, 253)}


def mouth_group():
    """Open smile like the painting at open=0.5; closed is a soft line, 1 is wide open."""
    ng = bpy.data.node_groups.new("MorfiMouth", "ShaderNodeTree")
    E = NodeExpr(ng)
    uv = E.input("UV", "NodeSocketVector", None)
    opn, smile, rnd = E.input("Open", default=0.5), E.input("Smile", default=0.8), E.input("Round")
    aa = E.input("AA", default=0.0008)
    x, y, _ = E.sep(uv)
    w = MOUTH["half_width"] * (1.0 + smile * 0.08 - rnd * 0.32)
    xn = x / w
    xx = (xn * xn).clamp()
    up = MOUTH["corner_up"] * (smile * 1.25 - rnd * 0.6)
    top = up * xx + rnd * 0.004
    depth = (opn * (2.0 * MOUTH["depth"]) + rnd * 0.006) * (1.0 - xx).clamp() ** E.mix(0.43, 0.75, rnd)
    bot = top - depth - 0.0024              # closed: a 2.4 mm dark line
    inside_x = E.smoothstep(1.0 + aa / w, 1.0 - aa / w, xn.abs())
    mouth = E.smoothstep(top + aa, top - aa, y) * E.smoothstep(bot - aa, bot + aa, y) * inside_x
    t = ((top - y) / E.max(top - bot, 0.001)).clamp()          # 0 top .. 1 bottom
    inner = E.mix_color(COL["mouth_in"], COL["mouth_lip"], E.smoothstep(0.15, 0.9, t) * E.smoothstep(0.004, 0.02, depth))
    dt = E.length2(x / (w * 0.55), (y - (bot + depth * 0.28)) / E.max(depth * 0.45, 0.002))
    tongue = E.smoothstep(1.05, 0.9, dt) * E.smoothstep(0.008, 0.02, depth) * (1.0 - rnd * 0.6)
    inner = E.mix_color(inner, COL["tongue"], tongue * 0.85)
    # the painted mouth was erased from the body texture: only the mouth itself is drawn
    E.output("Color", inner, "NodeSocketColor")
    E.output("Alpha", mouth)
    E.output("Mouth", mouth)
    return ng


def attr_node(nt, name):
    """Float custom property of the rendered object, read in the shader."""
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = "OBJECT"
    a.attribute_name = name
    return a.outputs["Fac"]


def drive_props(ob, rig, mapping):
    """ob[name] = expr(rig[prop]) through drivers, for {name: (prop, expr or None)}."""
    for name, (prop, expr) in mapping.items():
        ob[name] = 0.0
        fc = ob.driver_add(f'["{name}"]')
        drv = fc.driver
        var = drv.variables.new()
        var.name = "v"
        var.type = "SINGLE_PROP"
        var.targets[0].id = rig
        var.targets[0].data_path = f'["{prop}"]'
        if expr:
            drv.type = "SCRIPTED"
            drv.expression = expr
        else:
            drv.type = "AVERAGE"


MOUTH_PROPS = {"m_open": ("mouth_open", "max(0.0, 0.5 + 0.5 * v)"),
               "m_smile": ("smile", "min(1.0, 0.55 + 0.45 * v)"),
               "m_round": ("mouth_round", None)}


def mouth_material(rig):
    mat = bpy.data.materials.new("Mouth")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    grp = nt.nodes.new("ShaderNodeGroup")
    grp.node_tree = bpy.data.node_groups["MorfiMouth"]
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "eye"
    nt.links.new(uvn.outputs["UV"], grp.inputs["UV"])
    # rig props: mouth_open -1 closed .. 0 as painted .. 1 wide; smile 0..1; mouth_round 0..1
    nt.links.new(attr_node(nt, "m_open"), grp.inputs["Open"])
    nt.links.new(attr_node(nt, "m_smile"), grp.inputs["Smile"])
    nt.links.new(attr_node(nt, "m_round"), grp.inputs["Round"])
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(grp.outputs["Color"], bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(grp.outputs["Mouth"], rough.inputs["Value"])
    rough.inputs["To Min"].default_value = 0.75
    rough.inputs["To Max"].default_value = 0.45
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    nt.links.new(grp.outputs["Alpha"], bsdf.inputs["Alpha"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    return mat


# ---------------------------------------------------------------- decal geometry
def body_bvh(body):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    M = body.matrix_world
    verts = [M @ v.co for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons]
    tree = BVHTree.FromPolygons(verts, polys)
    ev.to_mesh_clear()
    return tree


def decal(name, tree, cx, cz, ra, rb, margin, res=56, offset=0.0008):
    """Grid over an ellipse, shrink-wrapped on the body along +Y, kept inside ellipse+margin."""
    xs = np.linspace(cx - ra - margin, cx + ra + margin, res)
    zs = np.linspace(cz - rb - margin, cz + rb + margin, res)
    verts, idx, uvs = [], {}, {}
    for j, z in enumerate(zs):
        for i, x in enumerate(xs):
            hit, nrm, _, _ = tree.ray_cast(Vector((x, -1.5, z)), Vector((0, 1, 0)))
            if hit is None:
                continue
            idx[(i, j)] = len(verts)
            verts.append(hit + nrm.normalized() * offset)
            uvs[(i, j)] = (x - cx, z - cz)
    faces = []
    for j in range(res - 1):
        for i in range(res - 1):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if not all(k in idx for k in q):
                continue
            mx = np.mean([xs[k[0]] for k in q]) - cx
            mz = np.mean([zs[k[1]] for k in q]) - cz
            if (mx / (ra + margin)) ** 2 + (mz / (rb + margin)) ** 2 > 1.0:
                continue
            faces.append([idx[k] for k in q])
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    uvl = me.uv_layers.new(name="eye")
    inv = {v: k for k, v in idx.items()}
    for loop in me.loops:
        uvl.data[loop.index].uv = uvs[inv[loop.vertex_index]]
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def parent_to_bone(ob, rig, bone):
    mw = ob.matrix_world.copy()
    ob.parent = rig
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    bpy.context.view_layer.update()
    ob.matrix_world = mw


def brow_keys(body, rig, feats, lift=0.010):
    """Shape keys that slide each painted brow (and the skin around it) up or down."""
    if body.data.shape_keys is None:
        body.shape_key_add(name="Basis", from_mix=False)
    co = np.array([v.co[:] for v in body.data.vertices])
    # the glasses frame sits 6 mm under the brows: find it on the front view and keep it still
    from PIL import Image
    from scipy import ndimage as ndi
    meta = feats["meta"]
    img = np.asarray(Image.open(os.path.join(FACE_DIR, "face_albedo.png")).convert("RGB")).astype(float)
    navy = (img[..., 2] > img[..., 0] + 25) & (img.mean(-1) < 70)
    lab, n = ndi.label(navy)
    frame = lab == (1 + int(np.argmax(ndi.sum(navy, lab, range(1, n + 1)))))
    frame = ndi.binary_dilation(frame, iterations=int(0.004 / meta["mpp"]))
    dist = ndi.distance_transform_edt(~frame) * meta["mpp"]
    u = ((co[:, 0] - meta["x0"]) / meta["mpp"]).round().astype(int).clip(0, frame.shape[1] - 1)
    v = ((meta["z1"] - co[:, 2]) / meta["mpp"]).round().astype(int).clip(0, frame.shape[0] - 1)
    frame_w = 1.0 - np.clip(dist[v, u] / 0.004, 0, 1)        # 1 on the frame, 0 four mm away
    for side, b in feats["brows"].items():
        x0, z0, x1, z1 = b["bbox"]
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2 + 0.004
        r = np.hypot((co[:, 0] - cx) / 0.072, (co[:, 2] - cz) / 0.040)
        t = np.clip((1.0 - r) / 0.5, 0, 1)
        w = t * t * (3 - 2 * t) * (co[:, 1] < 0.0) * (1.0 - frame_w)
        key = body.shape_key_add(name=f"Brow_{side}", from_mix=False)
        key.slider_min, key.slider_max = -1.0, 1.0
        moved = co.copy()
        moved[:, 2] += lift * w
        key.data.foreach_set("co", moved.ravel())
        fc = key.driver_add("value")
        var = fc.driver.variables.new()
        var.name, var.type = "v", "SINGLE_PROP"
        var.targets[0].id = rig
        var.targets[0].data_path = f'["brow_{side}"]'
        fc.driver.type = "AVERAGE"
        print(f"brow {side}: {int((w > 0.01).sum())} verts")


def mouth_fill_fit(body, cx=-0.007, cz=0.603):
    """Smooth surface y(x, z) over the sculpted mouth cavity, fitted on the skin around it."""
    co = np.array([v.co[:] for v in body.data.vertices])
    near = (np.abs(co[:, 0] - cx) < 0.075) & (np.abs(co[:, 2] - cz) < 0.05) & (co[:, 1] < -0.1)
    ring = near & ~((np.abs(co[:, 0] - cx) < 0.055) & (np.abs(co[:, 2] - cz) < 0.03))
    x, z = co[ring, 0] - cx, co[ring, 2] - cz
    A = np.stack([np.ones_like(x), x, z, x * x, x * z, z * z], 1)
    c = np.linalg.lstsq(A, co[ring, 1], rcond=None)[0]

    def surf(px, pz):
        px, pz = px - cx, pz - cz
        return np.stack([np.ones_like(px), px, pz, px * px, px * pz, pz * pz], 1) @ c
    return surf, near & ~ring


def drive_fill(key, rig):
    fc = key.driver_add("value")
    var = fc.driver.variables.new()
    var.name, var.type = "v", "SINGLE_PROP"
    var.targets[0].id = rig
    var.targets[0].data_path = '["mouth_open"]'
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = "min(1.0, max(0.0, -v))"     # -1 closed .. 0 as painted


def mouth_fill_keys(body, decal_ob, rig):
    """Closing the mouth fills the sculpted cavity, on the body and on the mouth decal."""
    surf, inner = mouth_fill_fit(body)
    for ob, offset in ((body, 0.0002), (decal_ob, 0.0010)):
        if ob.data.shape_keys is None:
            ob.shape_key_add(name="Basis", from_mix=False)
        co = np.array([v.co[:] for v in ob.data.vertices])
        target = surf(co[:, 0], co[:, 2]) - offset
        sel = (co[:, 1] > target) & ((inner if ob is body else np.ones(len(co), bool)))
        moved = co.copy()
        moved[sel, 1] = target[sel]
        key = ob.shape_key_add(name="Mouth_Fill", from_mix=False)
        key.data.foreach_set("co", moved.ravel())
        drive_fill(key, rig)
        print(f"mouth fill {ob.name}: {int(sel.sum())} verts")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    feats = json.load(open(args.features, encoding="utf-8"))
    global FACE_DIR
    FACE_DIR = os.path.dirname(os.path.abspath(args.features))
    outline = json.load(open(os.path.join(os.path.dirname(args.features), "eye_outline.json"), encoding="utf-8"))
    rig = bpy.data.objects["Morfi_Rig"]
    body = bpy.data.objects["Morfi_Body"]
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    for k in ("gaze_x", "gaze_y", "blink_L", "blink_R", "squint", "mouth_open", "smile"):
        if k not in rig:
            rig[k] = 0.0
    tree = body_bvh(body)
    clean = os.path.join(os.path.dirname(os.path.abspath(args.features)), "..", "tex", "base_color_clean.jpg")
    img = bpy.data.images.load(os.path.abspath(clean))
    img.name = "Morfi_BaseColor_clean"
    for node in body.data.materials[0].node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image and node.image.size[0] >= 8192:
            node.image = img
    eye_group()
    for side in ("R", "L"):
        eye = feats["eyes"][side]
        # painted outline: inner edge (white + clipped iris) and outer edge, both tilted
        # ellipses fitted on face_albedo.png (image angles -> world angles, z up)
        eye["outline"] = outline[side]
        for k in ("inner", "outer"):
            ang = -eye["outline"][k]["angle"]
            eye["outline"][k]["angle_w"] = (ang + 90.0) % 180.0 - 90.0
        eye["center"] = eye["outline"]["inner"]["center"]
        ra, rb = eye["outline"]["outer"]["radii"]
        oc = eye["outline"]["outer"]["center"]
        ob = decal(f"Eye_Decal_{side}", tree, *oc, max(ra, rb), max(ra, rb), margin=0.006)
        # the decal's UVs are measured from the inner centre
        dx, dz = oc[0] - eye["center"][0], oc[1] - eye["center"][1]
        for d in ob.data.uv_layers["eye"].data:
            d.uv = (d.uv[0] + dx, d.uv[1] + dz)
        ob.data.materials.append(eye_material(f"Eye_{side}", rig, eye, side))
        drive_props(ob, rig, {"m_gaze_x": ("gaze_x", None), "m_gaze_y": ("gaze_y", None),
                              "m_blink": (f"blink_{side}", None), "m_squint": ("squint", None)})
        parent_to_bone(ob, rig, "head")
        print(f"eye {side}: {len(ob.data.vertices)} verts")
    for k in ("brow_L", "brow_R"):
        if k not in rig:
            rig[k] = 0.0
    brow_keys(body, rig, feats)
    mouth_group()
    for k in ("mouth_round",):
        if k not in rig:
            rig[k] = 0.0
    mc = MOUTH["center"]
    mo = decal("Mouth_Decal", tree, mc[0], mc[1] - 0.006, 0.056, 0.034, margin=0.0, res=48)
    for d in mo.data.uv_layers["eye"].data:      # shader space: origin on the painted top lip
        d.uv = (d.uv[0], d.uv[1] - 0.006)
    mo.data.materials.append(mouth_material(rig))
    drive_props(mo, rig, MOUTH_PROPS)
    mouth_fill_keys(body, mo, rig)
    parent_to_bone(mo, rig, "head")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("DONE", args.out)


if __name__ == "__main__":
    main()
