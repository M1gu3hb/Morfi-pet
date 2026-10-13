"""Render each garment / accessory on its own (the exact objects used in the assembly).

    blender -b source/morfi_master.blend --python scripts/render_parts.py -- --out renders/parts --samples 96
"""
import argparse
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from morfi import scene  # noqa: E402

PARTS = {
    'sudadera': (['Hoodie', 'Hoodie_Hem', 'Hoodie_Cuff_L', 'Hoodie_Cuff_R', 'Hoodie_Zipper', 'Hoodie_Drawstrings'], 25, 12),
    'playera': (['Tshirt', 'Tshirt_Collar', 'Tshirt_Logo'], 20, 10),
    'tenis': (['Shoe_L', 'Shoe_R'], 35, 22),
    'lentes': (['Glasses_Frame', 'Glasses_Lens_L', 'Glasses_Lens_R'], 32, 12),
    'cubos': (['Pixel_01', 'Pixel_02', 'Pixel_03'], 20, 8),
    'laptop': (['Laptop'], 30, 35),
    'cuerpo_base': (['Body_Base', 'Head', 'Eye_L', 'Eye_R', 'Cornea_L', 'Cornea_R', 'Brow_L', 'Brow_R'], 0, 2),
}


def visible_set(names):
    keep = set(names)
    for ob in bpy.data.objects:
        if ob.type in ('MESH', 'CURVE'):
            ob.hide_render = ob.name not in keep and not ob.name.startswith('Studio')


def bbox(names):
    pts = []
    dg = bpy.context.evaluated_depsgraph_get()
    for n in names:
        ob = bpy.data.objects.get(n)
        if ob is None:
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.array([ev.matrix_world @ v.co for v in me.vertices])
        ev.to_mesh_clear()
        if len(co):
            pts.append(co)
    P = np.vstack(pts)
    return P.min(0), P.max(0)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'renders', 'parts'))
    ap.add_argument('--samples', type=int, default=96)
    ap.add_argument('--res', type=int, default=1400)
    ap.add_argument('--only', default='')
    a = ap.parse_args(argv)
    sc = bpy.context.scene
    sc.cycles.samples = a.samples
    sc.render.resolution_x = sc.render.resolution_y = a.res
    sc.render.resolution_percentage = 100
    rig = bpy.data.objects.get('Morfi_Rig')
    if rig and rig.animation_data:
        rig.animation_data.action = bpy.data.actions.get('Pose_Neutral')
    lap = bpy.data.objects.get('Laptop')
    if lap:
        lap.hide_render = False
    cd = bpy.data.cameras.new('Cam_part')
    cd.lens = 70
    cd.sensor_fit = 'HORIZONTAL'
    cam = bpy.data.objects.new('Cam_part', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(os.path.join(a.out, 'transparent'), exist_ok=True)
    for key, (names, az, el) in PARTS.items():
        if a.only and key not in a.only.split(','):
            continue
        visible_set(names)
        lo, hi = bbox(names)
        c = Vector(((lo + hi) / 2).tolist())
        r = float(np.linalg.norm(hi - lo)) / 2
        d = r / math.tan(math.atan(18.0 / 70.0)) * 1.12
        az_r, el_r = math.radians(az), math.radians(el)
        cam.location = c + Vector((d * math.sin(az_r) * math.cos(el_r), -d * math.cos(az_r) * math.cos(el_r), d * math.sin(el_r)))
        cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
        for transparent in (False, True):
            scene.set_transparent_output(transparent)
            sub = 'transparent' if transparent else ''
            sc.render.filepath = os.path.join(a.out, sub, f'{key}.png')
            bpy.ops.render.render(write_still=True)
            print('[parts]', key, transparent)


if __name__ == '__main__':
    main()
