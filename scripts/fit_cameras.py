"""Calibrate one camera per reference image from silhouettes.

The 15 references are independent AI renders: each one was "shot" with its own
camera (framing, distance, height and even lens differ slightly). Using a single
shared camera for every view leaves avoidable misalignment, so each view gets
the camera that best explains its silhouette:

    python3 scripts/fit_cameras.py            (needs numpy, scipy, pillow)

Inputs : work/calib/points_neutral.npz, work/calib/points_hero.npz
         (scripts/dump_points.py) and the reference PNGs.
Output : config/morfi.json -> "camera_views" {view: az, height, distance, lens,
         target, roll}, docs/camera_fit.json (IoU before/after), and
         renders/comparisons/camfit_<view>.png overlays.

The silhouette of the model is rendered by splatting a dense surface point
cloud (vertices + triangle centroids + edge midpoints) and closing the holes,
which is fast enough to run thousands of evaluations with Powell's method.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.optimize import minimize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from make_comparisons import ref_mask  # noqa: E402

W, H = 1145, 1374
SC = 0.5                       # fit at half resolution
w, h = int(W * SC), int(H * SC)

VIEWS = {
    'front': ('02_Morfi_frente', 0.0, 'neutral'),
    'profile_left': ('03_Morfi_perfil_izquierdo', 90.0, 'neutral'),
    'back': ('04_Morfi_espalda', 180.0, 'neutral'),
    'profile_right': ('05_Morfi_perfil_derecho', -90.0, 'neutral'),
    'three_quarter_front': ('06_Morfi_tres_cuartos_frontal', 33.0, 'neutral'),
    'three_quarter_back': ('07_Morfi_tres_cuartos_posterior', -150.0, 'neutral'),
    'hero': ('00_Morfi_master_wordmark', -33.0, 'hero'),
}


def camera_basis(az, height, dist, target, roll):
    a = math.radians(az)
    t = np.asarray(target, float)
    pos = np.array([t[0] + dist * math.sin(a), t[1] - dist * math.cos(a), height])
    fd = t - pos
    fd /= np.linalg.norm(fd)
    rt = np.cross(fd, [0, 0, 1.0])
    rt /= np.linalg.norm(rt)
    up = np.cross(rt, fd)
    r = math.radians(roll)
    rt, up = rt * math.cos(r) + up * math.sin(r), up * math.cos(r) - rt * math.sin(r)
    return pos, fd, rt, up


def project(P, cam):
    pos, fd, rt, up = camera_basis(cam['az'], cam['height'], cam['distance'], cam['target'], cam.get('roll', 0.0))
    d = P - pos
    z = d @ fd
    f = cam['lens'] / 36.0 * H
    u = W / 2 + f * (d @ rt) / z
    v = H / 2 - f * (d @ up) / z
    return u, v


def splat(P, cam, sub=None, sc=SC):
    u, v = project(P if sub is None else P[sub], cam)
    ww, hh = int(W * sc), int(H * sc)
    x = np.round(u * sc).astype(int)
    y = np.round(v * sc).astype(int)
    ok = (x >= 0) & (x < ww) & (y >= 0) & (y < hh)
    m = np.zeros((hh, ww), bool)
    m[y[ok], x[ok]] = True
    m = ndi.binary_closing(m, iterations=2 if sc >= 0.5 else 1)
    return ndi.binary_fill_holes(m)


def pack(cam):
    return np.array([cam['az'], cam['height'], cam['distance'], cam['lens'], cam['target'][0], cam['target'][2], cam.get('roll', 0.0)])


def unpack(x, base):
    return dict(az=float(x[0]), height=float(x[1]), distance=float(x[2]), lens=float(x[3]),
                target=[float(x[4]), base['target'][1], float(x[5])], roll=float(x[6]))


def iou(a, b):
    return float((a & b).sum() / max((a | b).sum(), 1))


def main():
    cfg_p = os.path.join(ROOT, 'config', 'morfi.json')
    cfg = json.load(open(cfg_p))
    c = cfg['camera']
    pts = {k: np.load(os.path.join(ROOT, 'work', 'calib', f'points_{k}.npz'))['points'] for k in ('neutral', 'hero')}
    rng = np.random.default_rng(0)
    # a random subset keeps each evaluation fast; the final check uses all points
    subs = {k: rng.choice(len(v), min(len(v), 700000), replace=False) for k, v in pts.items()}
    out = {}
    report = {}
    for view, (ref, az0, pose) in VIEWS.items():
        R = ref_mask(os.path.join(ROOT, 'references', ref + '.png'), (w, h))
        if view == 'hero':
            # leave the wordmark out of the silhouette
            R[int(h * 0.86):] = False
            base = dict(az=az0, height=0.86, distance=2.30, lens=55.0, target=[0.0, 0.0, 0.465], roll=0.0)
        else:
            base = dict(az=az0, height=c['height'], distance=c['distance'], lens=c['lens'], target=list(c['target']), roll=0.0)
        P = pts[pose]
        R4 = ref_mask(os.path.join(ROOT, 'references', ref + '.png'), (w // 2, h // 2))
        if view == 'hero':
            R4[int(h // 2 * 0.86):] = False

        def make_loss(Rm, sc, sub, sigma):
            Rs = ndi.gaussian_filter(Rm.astype(float), sigma)

            def loss(x):
                cam = unpack(x, base)
                if not (1.2 < cam['distance'] < 9 and 25 < cam['lens'] < 220
                        and 0.3 < cam['height'] < 1.25 and abs(cam['roll']) < 3.0):
                    return 1.0
                M = ndi.gaussian_filter(splat(P, cam, sub, sc).astype(float), sigma)
                return 1.0 - np.minimum(M, Rs).sum() / max(np.maximum(M, Rs).sum(), 1e-6)
            return loss

        x0 = pack(base)
        before = iou(splat(P, base), R)
        step = np.diag([2.0, 0.05, 0.2, 2.0, 0.01, 0.01, 0.5])
        # coarse (quarter resolution, 250k points), then fine (half resolution)
        best = minimize(make_loss(R4, SC / 2, subs[pose][:250000], 1.0), x0, method='Powell',
                        options=dict(xtol=1e-3, ftol=1e-5, maxfev=2500, direc=step))
        best = minimize(make_loss(R, SC, subs[pose], 1.5), best.x, method='Powell',
                        options=dict(xtol=1e-3, ftol=1e-6, maxfev=400, direc=step * 0.3))
        cam = unpack(best.x, base)
        after = iou(splat(P, cam), R)
        out[view] = {k: (round(v, 5) if isinstance(v, float) else [round(t, 5) for t in v]) for k, v in cam.items()}
        report[view] = dict(reference=ref + '.png', iou_shared_camera=round(before, 4), iou_fitted_camera=round(after, 4),
                            camera=out[view])
        print(f'{view:20s} IoU {before:.4f} -> {after:.4f}  {out[view]}', flush=True)
        # overlay for inspection
        M = splat(P, cam)
        o = np.full((h, w, 3), 255, np.uint8)
        o[R & M] = (160, 160, 160)
        o[R & ~M] = (225, 45, 45)
        o[~R & M] = (40, 175, 60)
        os.makedirs(os.path.join(ROOT, 'renders', 'comparisons'), exist_ok=True)
        Image.fromarray(o).save(os.path.join(ROOT, 'renders', 'comparisons', f'camfit_{view}.png'))
    cfg = json.load(open(cfg_p))  # re-read: the config may have changed while fitting
    cfg['camera_views'] = out
    cfg['camera_views']['_doc'] = ('Camara calibrada por vista contra la silueta de cada referencia '
                                  '(scripts/fit_cameras.py). Las referencias son renders independientes con encuadres distintos.')
    open(cfg_p, 'w').write(json.dumps(cfg, indent=1, ensure_ascii=False) + '\n')
    json.dump(report, open(os.path.join(ROOT, 'docs', 'camera_fit.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
