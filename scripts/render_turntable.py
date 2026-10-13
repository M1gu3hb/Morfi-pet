"""360-degree turntable of the complete character (lights fixed, Morfi rotates).

    blender -b source/morfi_master.blend --python scripts/render_turntable.py -- \
        --frames 192 --fps 24 --res 720x864 --samples 16 --out renders/turntable
then encode:  ffmpeg -framerate 24 -i renders/turntable/f_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 renders/morfi_turntable.mp4
"""
import argparse
import math
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from morfi import scene  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', type=int, default=192)
    ap.add_argument('--fps', type=int, default=24)
    ap.add_argument('--res', default='720x864')
    ap.add_argument('--samples', type=int, default=16)
    ap.add_argument('--out', default=os.path.join(ROOT, 'renders', 'turntable'))
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--step', type=int, default=1)
    a = ap.parse_args(argv)
    sc = bpy.context.scene
    w, h = (int(v) for v in a.res.split('x'))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.cycles.samples = a.samples
    sc.cycles.adaptive_threshold = 0.04
    sc.render.fps = a.fps
    scene.set_transparent_output(False)
    lap = bpy.data.objects.get('Laptop')
    if lap:
        lap.hide_render = True
    rig = bpy.data.objects.get('Morfi_Rig')
    if rig and rig.animation_data:
        rig.animation_data.action = bpy.data.actions.get('Pose_Neutral')
    root = bpy.data.objects['Morfi_Root']
    sc.camera = bpy.data.objects['Cam_front']
    os.makedirs(a.out, exist_ok=True)
    for i in range(a.start, a.frames, a.step):
        path = os.path.join(a.out, f'f_{i:04d}.png')
        if os.path.exists(path):
            continue
        root.rotation_euler = (0, 0, 2 * math.pi * i / a.frames)
        bpy.context.view_layer.update()
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print('[turntable]', i)


if __name__ == '__main__':
    main()
