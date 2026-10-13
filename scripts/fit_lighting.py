"""Fit the studio lighting to the reference images (coarse inverse rendering).

    blender -b source/morfi_master.blend --python scripts/fit_lighting.py -- \
        [--views front,three_quarter_front,back] [--res 286x343] [--samples 12] [--maxfev 70]

For each evaluation the views are rendered small with the calibrated cameras
and compared with the references in CIELAB, inside the region where both
silhouettes agree, after a light blur (so a few pixels of misalignment do not
count, only shading and colour do). Nelder-Mead tunes the key light direction
and power plus the fill, rim, top and world intensities. The result is written
to config/morfi.json ("lights") and docs/lighting_fit.json.
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from morfi import scene  # noqa: E402

REFS = {'front': '02_Morfi_frente', 'three_quarter_front': '06_Morfi_tres_cuartos_frontal',
        'back': '04_Morfi_espalda', 'profile_left': '03_Morfi_perfil_izquierdo',
        'three_quarter_back': '07_Morfi_tres_cuartos_posterior', 'profile_right': '05_Morfi_perfil_derecho'}
TARGET = Vector((0.0, 0.0, 0.5))


def lab(img):
    from skimage.color import rgb2lab
    return rgb2lab(np.clip(img, 0, 1))


def load(path, size):
    from PIL import Image
    return np.asarray(Image.open(path).convert('RGB').resize(size, Image.LANCZOS)).astype(float) / 255


def main():
    from PIL import Image
    from scipy import ndimage as ndi
    from scipy.optimize import minimize
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--views', default='front,three_quarter_front,back')
    ap.add_argument('--res', default='286x343')
    ap.add_argument('--samples', type=int, default=12)
    ap.add_argument('--maxfev', type=int, default=70)
    a = ap.parse_args(argv)
    W, H = (int(v) for v in a.res.split('x'))
    cfg_p = os.path.join(ROOT, 'config', 'morfi.json')
    cfg = json.load(open(cfg_p))
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 100
    sc.cycles.samples = a.samples
    scene.set_transparent_output(False)
    for o in [bpy.data.objects['Laptop']] + list(bpy.data.objects['Laptop'].children_recursive):
        o.hide_render = True
    views = a.views.split(',')
    refs, masks = {}, {}
    for v in views:
        refs[v] = lab(ndi.gaussian_filter(load(os.path.join(ROOT, 'references', REFS[v] + '.png'), (W, H)), (1.5, 1.5, 0)))
        m = np.asarray(Image.open(os.path.join(ROOT, 'references_masks', REFS[v] + '.png')).convert('L').resize((W, H))) > 128
        masks[v] = m
    L = {n: bpy.data.objects[n] for n in ('Light_Key', 'Light_Fill', 'Light_Rim', 'Light_Top')}
    world = bpy.data.worlds['World'].node_tree.nodes['Background']
    k0 = L['Light_Key'].location - TARGET
    x0 = np.array([math.degrees(math.atan2(k0.x, -k0.y)), math.degrees(math.asin(k0.z / k0.length)),
                   math.log(L['Light_Key'].data.energy), math.log(L['Light_Fill'].data.energy),
                   math.log(L['Light_Rim'].data.energy), math.log(L['Light_Top'].data.energy),
                   math.log(world.inputs['Strength'].default_value)])
    rk = k0.length
    tmp = os.path.join(ROOT, 'work', 'lightfit')
    os.makedirs(tmp, exist_ok=True)
    cams = {v: scene.view_camera(v, cfg) for v in views}
    hist = []

    def apply(x):
        az, el = math.radians(x[0]), math.radians(x[1])
        kl = TARGET + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * rk
        L['Light_Key'].location = kl
        L['Light_Key'].rotation_euler = (TARGET - kl).to_track_quat('-Z', 'Y').to_euler()
        L['Light_Key'].data.energy = math.exp(x[2])
        L['Light_Fill'].data.energy = math.exp(x[3])
        L['Light_Rim'].data.energy = math.exp(x[4])
        L['Light_Top'].data.energy = math.exp(x[5])
        world.inputs['Strength'].default_value = math.exp(x[6])

    def loss(x, save=False):
        if not (-80 < x[0] < 80 and 0 < x[1] < 75):
            return 99.0
        apply(x)
        err = []
        for v in views:
            sc.camera = cams[v]
            restore = scene.eyes_look(cams[v].matrix_world.translation, scene.EYE_LOOK.get(v, 1.0))
            sc.render.filepath = os.path.join(tmp, f'{v}.png')
            bpy.ops.render.render(write_still=True)
            restore()
            img = lab(ndi.gaussian_filter(load(sc.render.filepath, (W, H)), (1.5, 1.5, 0)))
            alpha = None
            m = masks[v]
            d = np.sqrt(((img - refs[v]) ** 2).sum(-1))
            err.append(float(np.median(d[m])) * 0.5 + float(d[m].mean()) * 0.5)
        e = float(np.mean(err))
        hist.append((e, list(map(float, x)), err))
        print(f'[lightfit] {len(hist):3d} dE={e:.3f} {np.round(err, 2).tolist()} x={np.round(x, 3).tolist()}', flush=True)
        return e

    e0 = loss(x0)
    res = minimize(loss, x0, method='Nelder-Mead',
                   options=dict(maxfev=a.maxfev, xatol=0.5, fatol=0.02,
                                initial_simplex=np.vstack([x0] + [x0 + d for d in np.diag([12, 8, 0.35, 0.5, 0.5, 0.5, 0.35])])))
    best = min(hist, key=lambda h: h[0])
    x = np.array(best[1])
    apply(x)
    Lc = cfg.setdefault('lights', {})
    Lc['key_loc'] = [round(v, 4) for v in L['Light_Key'].location]
    Lc['key_target'] = list(TARGET)
    Lc['key_power'] = round(L['Light_Key'].data.energy, 3)
    Lc['fill_power'] = round(L['Light_Fill'].data.energy, 3)
    Lc['rim_power'] = round(L['Light_Rim'].data.energy, 3)
    Lc['top_power'] = round(L['Light_Top'].data.energy, 3)
    Lc['world'] = round(world.inputs['Strength'].default_value, 4)
    cfg2 = json.load(open(cfg_p))
    cfg2['lights'] = Lc
    open(cfg_p, 'w').write(json.dumps(cfg2, indent=1, ensure_ascii=False) + '\n')
    json.dump(dict(views=views, start_dE=e0, best_dE=best[0], per_view_best=best[2], lights=Lc, evaluations=len(hist)),
              open(os.path.join(ROOT, 'docs', 'lighting_fit.json'), 'w'), indent=1)
    print('[lightfit] done', e0, '->', best[0])


if __name__ == '__main__':
    main()
