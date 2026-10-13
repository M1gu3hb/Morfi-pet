"""360-degree turntable of the complete character.

    blender -b source/morfi_master.blend --python scripts/render_turntable.py -- \
        --frames 144 --fps 24 --res 600x720 --samples 10 --out work/turntable
then encode:  ffmpeg -framerate 24 -i work/turntable/f_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 renders/morfi_turntable.mp4

The camera and every studio light orbit together around Morfi (the floor is a
round shadow catcher and the world is uniform), which looks exactly like the
character spinning in front of fixed lights, but lets Cycles keep the scene in
memory between frames (persistent data) instead of rebuilding it every frame.
The eyes follow the viewer while the face is visible (same curve as the web
viewer); their per-frame turn is baked as keyframes on the eye objects.
"""
import argparse
import math
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from morfi import scene  # noqa: E402


def eye_follow(off):
    """Eye-follow amount for an angle (radians) between the face and the viewer."""
    if off < 0.7:
        return 1.0
    if off < 1.571:
        return 1 - 0.65 * (off - 0.7) / 0.871
    return max(0.0, 0.35 * (1 - (off - 1.571) / 0.5))


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', type=int, default=192)
    ap.add_argument('--fps', type=int, default=24)
    ap.add_argument('--res', default='720x864')
    ap.add_argument('--samples', type=int, default=16)
    ap.add_argument('--out', default=os.path.join(ROOT, 'work', 'turntable'))
    ap.add_argument('--no-eyes-follow', dest='eyes_follow', action='store_false')
    a = ap.parse_args(argv)
    sc = bpy.context.scene
    w, h = (int(v) for v in a.res.split('x'))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.cycles.samples = a.samples
    sc.cycles.adaptive_threshold = 0.04
    sc.render.fps = a.fps
    sc.render.use_persistent_data = True
    scene.set_transparent_output(False)
    lap = bpy.data.objects.get('Laptop')
    if lap:
        lap.hide_render = True
        for ch in lap.children_recursive:
            ch.hide_render = True
    rig = bpy.data.objects.get('Morfi_Rig')
    if rig and rig.animation_data:
        rig.animation_data.action = bpy.data.actions.get('Pose_Neutral')
    sc.frame_set(1)
    cam = bpy.data.objects['Cam_front']
    sc.camera = cam
    # orbit rig: camera + all lights
    pivot = bpy.data.objects.new('TT_Pivot', None)
    sc.collection.objects.link(pivot)
    movers = [cam] + [o for o in bpy.data.objects if o.type == 'LIGHT']
    bpy.context.view_layer.update()
    for ob in movers:
        mw = ob.matrix_world.copy()
        ob.parent = pivot
        ob.matrix_world = mw
    eyes = [bpy.data.objects.get('Eye_L'), bpy.data.objects.get('Eye_R')]
    eyes = [e for e in eyes if e is not None]
    for e in eyes:
        e.rotation_mode = 'QUATERNION'
    n = a.frames
    for i in range(n):
        ang = 2 * math.pi * i / n
        pivot.rotation_euler = (0, 0, -ang)
        pivot.keyframe_insert('rotation_euler', frame=i)
        bpy.context.view_layer.update()
        off = abs((ang + math.pi) % (2 * math.pi) - math.pi)
        restore = scene.eyes_look(cam.matrix_world.translation, eye_follow(off) if a.eyes_follow else 0.0)
        for e in eyes:
            e.keyframe_insert('location', frame=i)
            e.keyframe_insert('rotation_quaternion', frame=i)
        restore()
    for ob in [pivot] + eyes:
        ad = ob.animation_data
        if ad and ad.action:
            for fc in getattr(ad.action, 'fcurves', []):
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
    sc.frame_start, sc.frame_end = 0, n - 1
    os.makedirs(a.out, exist_ok=True)
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = os.path.join(a.out, 'f_')
    sc.render.use_file_extension = True
    bpy.ops.render.render(animation=True)
    print('[turntable] done', n)


if __name__ == '__main__':
    main()
