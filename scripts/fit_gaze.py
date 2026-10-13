"""Fit where Morfi looks in each reference shot (per-eye gaze offsets).

    blender -b source/morfi_master.blend --python scripts/fit_gaze.py -- [--views front,three_quarter_front]

In the references the pupils are not exactly where "look at the camera" puts
them: in the front shot, for example, both eyes converge a little more toward
the nose. For every shot whose eyes are visible this script finds the black
pupils in the reference image, poses Morfi exactly as the render does (fitted
camera, Ref_<view> or hero pose, eyes turned to the camera) and solves, per
eye, the small yaw / pitch that puts the projected pupil centre on the
reference pupil (Gauss-Newton on the projection, no rendering needed). The
offsets go to config/morfi.json -> "view_gaze"; render_views.py and
render_hero.py apply them through scene.eyes_look. The hero shot is left out
by default: there the pupil offset comes from the head pose (it would need one
eye turned 20 degrees and the other 10, i.e. a squint).
"""
import argparse
import json
import os
import sys

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from morfi import scene  # noqa: E402

W, H = 1145, 1374
REFS = {'front': '02_Morfi_frente', 'three_quarter_front': '06_Morfi_tres_cuartos_frontal',
        'hero': '00_Morfi_master_wordmark'}


def ref_pupils(path):
    """Centroids of the two black pupil blobs (sorted left to right, pixels at W x H)."""
    from PIL import Image
    from scipy import ndimage as ndi
    a = np.asarray(Image.open(path).convert('RGB').resize((W, H), Image.LANCZOS)).astype(float)
    dark = a.mean(-1) < 28
    dark[int(H * 0.55):] = False
    dark = ndi.binary_opening(dark, iterations=2)
    lab, n = ndi.label(dark)
    blobs = []
    for i, sl in enumerate(ndi.find_objects(lab)):
        m = lab[sl] == i + 1
        area = int(m.sum())
        hh, ww = m.shape
        if area < 400 or area / float(hh * ww) < 0.55 or max(hh, ww) > 3 * min(hh, ww):
            continue
        ys, xs = np.nonzero(m)
        blobs.append((area, xs.mean() + sl[1].start, ys.mean() + sl[0].start))
    blobs = sorted(blobs, reverse=True)[:2]
    return sorted([(x, y) for _, x, y in blobs])


def pupil_px(sc, cam, eye, R):
    p = eye.matrix_world @ Vector((0.0, -R, 0.0))
    v = world_to_camera_view(sc, cam, p)
    return np.array([v.x * W, (1.0 - v.y) * H])


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--views', default='front,three_quarter_front')
    a = ap.parse_args(argv)
    cfg_p = os.path.join(ROOT, 'config', 'morfi.json')
    cfg = json.load(open(cfg_p))
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
    rig = bpy.data.objects['Morfi_Rig']
    eyes = {'L': bpy.data.objects['Eye_L'], 'R': bpy.data.objects['Eye_R']}
    R = max(v.co.length for v in eyes['L'].data.vertices) * eyes['L'].matrix_world.to_scale()[0]
    out, report = {}, {}
    for view in a.views.split(','):
        if view == 'hero':
            import render_hero
            rig.animation_data.action = bpy.data.actions['Pose_Hero']
            sc.frame_set(1)
            bpy.context.view_layer.update()
            render_hero.place_laptop(rig)
            cam = bpy.data.objects.get('Cam_hero') or scene.make_camera('Cam_hero', -33.0, cfg, sc.collection)
            scene.place_camera(cam, cfg['camera_views']['hero'])
        else:
            cam = scene.view_camera(view, cfg)
            rig.animation_data.action = bpy.data.actions.get('Ref_' + view) or bpy.data.actions['Pose_Neutral']
            sc.frame_set(1)
        sc.camera = cam
        bpy.context.view_layer.update()
        k = scene.EYE_LOOK.get(view, 1.0)
        target = ref_pupils(os.path.join(ROOT, 'references', REFS[view] + '.png'))
        if not target:
            print('[gaze]', view, 'pupils not found')
            continue

        def proj(g):
            restore = scene.eyes_look(cam.matrix_world.translation, k, gaze=g)
            p = {s: pupil_px(sc, cam, e, R) for s, e in eyes.items()}
            restore()
            return p
        p0 = proj(None)
        # match eyes to reference pupils by image x order (or the nearest eye when
        # only one pupil is clearly visible, e.g. the far eye in 3/4)
        if len(target) == 2:
            order = sorted(eyes.keys(), key=lambda s: p0[s][0])
            tgt = {s: np.array(target[i]) for i, s in enumerate(order)}
        else:
            s = min(eyes.keys(), key=lambda s: np.linalg.norm(p0[s] - np.array(target[0])))
            tgt = {s: np.array(target[0])}
        g = {'L': np.zeros(2), 'R': np.zeros(2)}
        for it in range(6):
            base = proj({s: list(v) for s, v in g.items()})
            for s in tgt:
                J = np.zeros((2, 2))
                for j in range(2):
                    gg = {t: list(v) for t, v in g.items()}
                    gg[s][j] += 0.5
                    J[:, j] = (proj(gg)[s] - base[s]) / 0.5
                step = np.linalg.lstsq(J, tgt[s] - base[s], rcond=None)[0]
                g[s] = np.clip(g[s] + step, -20, 20)
        final = proj({s: list(v) for s, v in g.items()})
        if len(tgt) == 1:  # the hidden eye follows the visible one
            other = 'L' if 'R' in tgt else 'R'
            g[other] = g[[*tgt][0]].copy()
            final = proj({s: list(v) for s, v in g.items()})
        out[view] = {s: [round(float(v), 3) for v in g[s]] for s in g}
        report[view] = {s: dict(reference_px=[round(float(t), 1) for t in tgt[s]] if s in tgt else None,
                                camera_look_px=[round(float(t), 1) for t in p0[s]],
                                fitted_px=[round(float(t), 1) for t in final[s]], yaw_pitch=out[view][s]) for s in g}
        print('[gaze]', view, report[view], flush=True)
    cfg = json.load(open(cfg_p))
    vg = cfg.get('view_gaze', {})
    vg.update(out)
    vg['_doc'] = ('Desvio de la mirada por toma y por ojo [giro, inclinacion] en grados, tras mirar a la camara; '
                  'ajustado a la posicion de las pupilas de cada referencia con scripts/fit_gaze.py '
                  '(la toma hero no se corrige: alli la diferencia viene de la pose de la cabeza)')
    cfg['view_gaze'] = vg
    open(cfg_p, 'w').write(json.dumps(cfg, indent=1, ensure_ascii=False) + '\n')
    json.dump(report, open(os.path.join(ROOT, 'docs', 'gaze_fit.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
