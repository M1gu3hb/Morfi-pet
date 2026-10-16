"""Arm IK with a little stretch, a prop rig and Morfi's props (tablet, calculator).

blender -b work/ia3d/morfi_ia_rig_hands.blend --python scripts/ia3d/build_controls.py -- \
    --out work/ia3d/morfi_ia_rig.blend

Adds, without touching the existing bones:
  * `prop` (child of chest): where held objects live, in front of the chest;
  * `hand_ik.<s>` (children of `prop`) and `elbow_pole.<s>` (children of chest): a 2-bone IK on
    each arm, OFF by default (constraint influence 0). Actions switch it on with the channel
    "forearm.<s>.ik" and then place the wrist in prop space, so hands stay on a held object
    while the body moves. The hand then copies the target's rotation.
    upper_arm / forearm may stretch up to 12 % when a target is out of reach (cartoon reach,
    never a rubber arm);
  * props, each on its own bone (`prop_tablet`, `prop_calc`) and hidden (scale 0) unless an
    action shows it (channel "prop_tablet.s").
"""
import argparse
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PROP_HEAD = (0.0, -0.20, 0.36)
IK_STRETCH = 0.12
# sized for Morfi's short arms (the wrist reaches ~20 cm from the shoulder): a handheld POS
# tablet and a pocket calculator, so they fit between his belly and his hands
TABLET = {"w": 0.150, "h": 0.105, "t": 0.008, "r": 0.012, "bezel": 0.008}
CALC = {"w": 0.085, "h": 0.125, "t": 0.016, "r": 0.010}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--props-only", action="store_true", help="rebuild the prop meshes, keep the rig")
    return ap.parse_args(argv)


def srgb(c):
    return tuple(((v / 255 + 0.055) / 1.055) ** 2.4 if v / 255 > 0.04045 else v / 255 / 12.92 for v in c) + (1.0,)


# ---------------------------------------------------------------- bones and constraints
def add_bones(rig):
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    eb = rig.data.edit_bones
    prop = eb.new("prop")
    prop.head = Vector(PROP_HEAD)
    prop.tail = Vector(PROP_HEAD) + Vector((0, 0, 0.08))
    prop.parent = eb["chest"]
    prop.use_deform = False
    for name in ("prop_tablet", "prop_calc"):
        b = eb.new(name)
        b.head, b.tail = prop.head.copy(), prop.tail.copy()
        b.parent = prop
        b.use_deform = False
    for s, sx in (("L", 1), ("R", -1)):
        hand = eb[f"hand.{s}"]
        ik = eb.new(f"hand_ik.{s}")
        ik.head, ik.tail, ik.roll = hand.head.copy(), hand.tail.copy(), hand.roll
        ik.parent = prop
        ik.use_deform = False
        elbow = eb[f"forearm.{s}"].head
        pole = eb.new(f"elbow_pole.{s}")
        pole.head = elbow + Vector((sx * 0.10, 0.30, -0.02))
        pole.tail = pole.head + Vector((0, 0.05, 0))
        pole.parent = eb["chest"]
        pole.use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"


def add_constraints(rig):
    for s in ("L", "R"):
        fa = rig.pose.bones[f"forearm.{s}"]
        c = fa.constraints.new("IK")
        c.name = "ArmIK"
        c.target, c.subtarget = rig, f"hand_ik.{s}"
        c.pole_target, c.pole_subtarget = rig, f"elbow_pole.{s}"
        c.chain_count = 2
        c.use_stretch = True
        c.influence = 1.0
        for b in (f"upper_arm.{s}", f"forearm.{s}"):
            rig.pose.bones[b].ik_stretch = IK_STRETCH
        # pole angle that leaves the rest pose untouched
        bpy.context.view_layer.update()
        rest = {n: np.array(rig.data.bones[n].matrix_local) for n in (f"upper_arm.{s}", f"forearm.{s}")}
        best = None
        for deg in range(-180, 180, 2):
            c.pole_angle = math.radians(deg)
            bpy.context.view_layer.update()
            err = sum(float(np.abs(np.array(rig.pose.bones[n].matrix) - rest[n]).sum()) for n in rest)
            if best is None or err < best[0]:
                best = (err, deg)
        c.pole_angle = math.radians(best[1])
        c.influence = 0.0                                   # FK unless an action asks for IK
        cr = rig.pose.bones[f"hand.{s}"].constraints.new("COPY_ROTATION")
        cr.name = "HandIK"
        cr.target, cr.subtarget = rig, f"hand_ik.{s}"
        cr.influence = 0.0
        print(f"arm IK {s}: pole {best[1]} deg, rest error {best[0]:.4f}")


# ---------------------------------------------------------------- props
def rounded_slab(name, w, h, t, r, seg=8):
    """Rounded rectangle slab in the XZ plane (screen facing -Y), centred on the origin."""
    bm = bmesh.new()
    pts = []
    for cx, cz, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180),
                       (w / 2 - r, -h / 2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    front = [bm.verts.new((x, -t / 2, z)) for x, z in pts]
    back = [bm.verts.new((x, t / 2, z)) for x, z in pts]
    bm.faces.new(front[::-1])
    bm.faces.new(back)
    n = len(pts)
    for i in range(n):
        bm.faces.new((front[i], front[(i + 1) % n], back[(i + 1) % n], back[i]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bev = ob.modifiers.new("Bevel", "BEVEL")
    bev.width, bev.segments = min(t * 0.35, 0.004), 3
    with bpy.context.temp_override(object=ob, active_object=ob):
        bpy.ops.object.modifier_apply(modifier=bev.name)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def screen_plane(name, w, h, y, img):
    me = bpy.data.meshes.new(name)
    v = [(-w / 2, y, -h / 2), (w / 2, y, -h / 2), (w / 2, y, h / 2), (-w / 2, y, h / 2)]
    me.from_pydata(v, [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for loop, (u, vv) in zip(me.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[loop.index].uv = (u, vv)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 0.6
    b.inputs["Roughness"].default_value = 0.08
    b.inputs["Coat Weight"].default_value = 0.6
    me.materials.append(mat)
    return ob


def ui_image(name, w, h, draw_fn):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (246, 248, 252))
    draw_fn(ImageDraw.Draw(im), w, h)
    path = os.path.join(bpy.app.tempdir, f"{name}.png")
    im.save(path)
    img = bpy.data.images.load(path)
    img.pack()
    return img


def draw_tablet(d, w, h):
    blue, deep, soft = (7, 87, 245), (11, 30, 91), (205, 220, 252)
    d.rounded_rectangle((0, 0, w, int(h * 0.14)), 0, fill=deep)
    d.ellipse((int(w * 0.04), int(h * 0.03), int(w * 0.04) + int(h * 0.08), int(h * 0.11)), fill=blue)
    cols, rows = 4, 3
    gx, gy = w * 0.08, h * 0.22
    cw, ch = (w - 2 * gx) / cols, (h * 0.70) / rows
    for r in range(rows):
        for c in range(cols):
            x0, y0 = gx + c * cw + cw * 0.12, gy + r * ch + ch * 0.12
            d.rounded_rectangle((x0, y0, x0 + cw * 0.76, y0 + ch * 0.76), int(cw * 0.12),
                                fill=blue if (r + c) % 3 else soft)


def draw_calc(d, w, h):
    d.rectangle((0, 0, w, h), fill=(225, 236, 210))
    d.text((int(w * 0.70), int(h * 0.30)), "128.50", fill=(20, 30, 40))


def material(name, srgb_col, rough=0.4, metal=0.0, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(srgb_col)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    return mat


def parent_bone(ob, rig, bone):
    mw = ob.matrix_world.copy()
    ob.parent = rig
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    bpy.context.view_layer.update()
    ob.matrix_world = mw


def build_tablet(rig):
    T = TABLET
    body = rounded_slab("Prop_Tablet", T["w"], T["h"], T["t"], T["r"])
    body.data.materials.append(material("Tablet_Body", (40, 44, 54), rough=0.3, metal=0.6, coat=0.3))
    img = ui_image("tablet_ui", 840, 560, draw_tablet)
    scr = screen_plane("Prop_Tablet_Screen", T["w"] - 2 * T["bezel"], T["h"] - 2 * T["bezel"], -T["t"] / 2 - 0.0006, img)
    scr.parent = body
    head = Vector(rig.data.bones["prop_tablet"].head_local)
    body.matrix_world = Matrix.Translation(head)
    parent_bone(body, rig, "prop_tablet")
    return body


def build_calc(rig):
    C = CALC
    body = rounded_slab("Prop_Calc", C["w"], C["h"], C["t"], C["r"])
    body.data.materials.append(material("Calc_Body", (236, 238, 242), rough=0.45))
    img = ui_image("calc_display", 400, 120, draw_calc)
    disp = screen_plane("Prop_Calc_Display", C["w"] * 0.78, C["h"] * 0.18, -C["t"] / 2 - 0.0006, img)
    disp.location.z = C["h"] * 0.31
    disp.parent = body
    keys = material("Calc_Keys", (7, 87, 245), rough=0.35, coat=0.4)
    for r in range(4):
        for c in range(3):
            k = rounded_slab(f"Prop_Calc_Key_{r}{c}", C["w"] * 0.22, C["h"] * 0.12, 0.006, 0.006, seg=4)
            k.location = ((c - 1) * C["w"] * 0.28, -C["t"] / 2 - 0.002, C["h"] * 0.12 - r * C["h"] * 0.155)
            k.data.materials.append(keys)
            k.parent = body
    head = Vector(rig.data.bones["prop_calc"].head_local)
    body.matrix_world = Matrix.Translation(head)
    parent_bone(body, rig, "prop_calc")
    return body


def remove_props():
    for ob in [o for o in bpy.data.objects if o.name.startswith("Prop_")]:
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for d in [d for d in coll if d.users == 0]:
            coll.remove(d)


def main():
    args = parse_args()
    rig = bpy.data.objects["Morfi_Rig"]
    keep = rig.animation_data.action if rig.animation_data else None
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    if args.props_only:
        remove_props()
    else:
        add_bones(rig)
        add_constraints(rig)
    build_tablet(rig)
    build_calc(rig)
    # props hidden by default: their bones are scaled to 0 until an action shows them
    for b in ("prop_tablet", "prop_calc"):
        rig.pose.bones[b].scale = (0.0, 0.0, 0.0)
    if keep is not None:
        rig.animation_data.action = keep
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("DONE", args.out)


if __name__ == "__main__":
    main()
