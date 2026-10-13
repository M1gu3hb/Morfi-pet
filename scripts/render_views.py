"""Render camera views of the master scene.

    blender -b source/morfi_master.blend --python scripts/render_views.py -- \
        --views front,profile_left --out renders/views --samples 128 [--transparent] [--scale 1.0]
"""
import argparse
import os
import sys
import time

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from morfi import scene  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--views', default=','.join(scene.VIEWS))
    ap.add_argument('--out', default=os.path.join(ROOT, 'renders', 'views'))
    ap.add_argument('--samples', type=int, default=128)
    ap.add_argument('--scale', type=float, default=1.0)
    ap.add_argument('--transparent', action='store_true')
    ap.add_argument('--hide', default='', help='comma separated object/collection names to hide')
    ap.add_argument('--suffix', default='')
    ap.add_argument('--eye-look', default='', help='JSON {view: k} overriding scene.EYE_LOOK (tests)')
    ap.add_argument('--engine', default='CYCLES', choices=['CYCLES', 'WORKBENCH', 'EEVEE'])
    ap.add_argument('--res', default='', help='WxH override')
    ap.add_argument('--shared-camera', dest='calibrated', action='store_false',
                    help='use the single estimated camera instead of the per-view calibrated ones')
    ap.add_argument('--no-eyes-follow', dest='eyes_follow', action='store_false',
                    help='keep the modelled forward gaze instead of looking at each camera')
    ap.add_argument('--world-lights', dest='camera_lights', action='store_false',
                    help='keep the light rig fixed in the world instead of turning it with each camera')
    a = ap.parse_args(argv)
    sc = bpy.context.scene
    sc.cycles.samples = a.samples
    sc.render.resolution_percentage = int(round(100 * a.scale))
    scene.set_transparent_output(a.transparent)
    if a.res:
        w, h = a.res.split('x')
        sc.render.resolution_x, sc.render.resolution_y = int(w), int(h)
    if a.engine == 'WORKBENCH':
        sc.render.engine = 'BLENDER_WORKBENCH'
        sh = sc.display.shading
        sh.light = 'STUDIO'
        sh.color_type = 'MATERIAL'
        sh.show_cavity = True
        sh.cavity_type = 'WORLD'
        sh.show_shadows = False
        sc.render.film_transparent = True
        fl = bpy.data.objects.get('Studio_Floor')
        if fl:
            fl.hide_render = True
    elif a.engine == 'EEVEE':
        sc.render.engine = 'BLENDER_EEVEE_NEXT'
        sc.eevee.taa_render_samples = a.samples
    for name in filter(None, a.hide.split(',')):
        ob = bpy.data.objects.get(name)
        if ob:
            ob.hide_render = True
            for ch in ob.children_recursive:
                ch.hide_render = True
        c = bpy.data.collections.get(name)
        if c:
            c.hide_render = True
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    import json
    cfg = json.load(open(os.path.join(ROOT, 'config', 'morfi.json')))
    for v in a.views.split(','):
        cam = scene.view_camera(v, cfg) if a.calibrated else bpy.data.objects.get('Cam_' + v)
        if cam is None:
            print('no camera', v)
            continue
        sc.camera = cam
        rig = bpy.data.objects.get('Morfi_Rig')
        if rig and rig.animation_data:
            # each reference shot has its own fitted pose (Ref_<view>), else neutral
            ref_act = bpy.data.actions.get('Ref_' + v) if a.calibrated else None
            rig.animation_data.action = ref_act or bpy.data.actions.get('Pose_Neutral')
            sc.frame_set(1)
            bpy.context.view_layer.update()
        sc.render.filepath = os.path.join(a.out, v + a.suffix + '.png')
        gaze = cfg.get('view_gaze', {}).get(v) if (a.calibrated and a.eyes_follow) else None
        look = dict(scene.EYE_LOOK, **(json.loads(a.eye_look) if a.eye_look else {}))
        restore = scene.eyes_look(cam.matrix_world.translation, look.get(v, 1.0) if a.eyes_follow else 0.0,
                                  gaze=gaze)
        # light rig turns with the camera, as in the reference shots
        cv = cfg.get('camera_views', {})
        az = cv[v]['az'] - cv.get('front', {}).get('az', 0.0) if (a.calibrated and a.camera_lights and v in cv) else 0.0
        unturn = scene.turn_lights(az) if az else (lambda: None)
        bpy.ops.render.render(write_still=True)
        unturn()
        restore()
        print(f'[render] {v} {time.time() - t0:.1f}s -> {sc.render.filepath}')


if __name__ == '__main__':
    main()
