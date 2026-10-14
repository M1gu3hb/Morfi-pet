"""Calibrate the camera of each product sheet (08-14) from its silhouette.

The part sheets are product photos: each garment / accessory is shot alone,
with its own camera and, for loose items, its own arrangement (the two shoes
are staggered, the three cubes float apart). To compare like with like, every
part render is taken with the camera that best explains the sheet's
silhouette, the same way scripts/fit_cameras.py does for the full views:

    blender -b source/morfi_master.blend --python scripts/dump_points.py -- \
        --pose neutral --keep-laptop --out work/calib/points_parts.npz
    python3 scripts/fit_part_cameras.py [--only tenis,cubos]

Parameters: azimuth, elevation, distance, lens, target offset (x, z), roll;
for the shoes also a floor placement (dx, dy, yaw) per shoe and for the cubes
an offset per cube. Writes config/morfi.json -> "part_cameras" (used by
scripts/render_parts.py), docs/part_camera_fit.json and
renders/comparisons/partfit_<part>.png overlays.
"""
import argparse
import json
import math
import os

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.optimize import minimize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HOODIE = ['Hoodie_Product', 'Hoodie_Hem', 'Hoodie_Cuff_L', 'Hoodie_Cuff_R', 'Hoodie_Zipper', 'Hoodie_Drawstrings']
PARTS = {
    # key: (sheet, objects, movable objects, rigid mode)
    'sudadera': ('08_Morfi_sudadera', HOODIE, [], None),
    'playera': ('09_Morfi_playera', ['Tshirt', 'Tshirt_Collar', 'Tshirt_Logo'], [], None),
    'tenis': ('10_Morfi_tenis', ['Shoe_L', 'Shoe_R'], ['Shoe_L', 'Shoe_R'], 'floor'),
    'lentes': ('11_Morfi_lentes', ['Glasses_Frame', 'Glasses_Lens_L', 'Glasses_Lens_R'], [], None),
    'cubos': ('12_Morfi_tres_cubos', ['Pixel_01', 'Pixel_02', 'Pixel_03'], ['Pixel_01', 'Pixel_02', 'Pixel_03'], 'shift'),
    'laptop': ('13_Morfi_laptop', ['Laptop', 'Laptop_Logo'], [], None),
    'cuerpo_base': ('14_Morfi_cuerpo_base', ['Body_Base', 'Head', 'Eye_L', 'Eye_R', 'Brow_L', 'Brow_R'], [], None),
}
# garments are hollow without the body: a high camera would look into them, so
# their elevation is capped near the sheets' near-frontal view
EL_MAX = {'playera': 18.0, 'sudadera': 20.0}
EL_MIN = {'sudadera': 8.0}  # the sheet looks slightly down into the raised hood
# parts whose sheet shows their front (logo, face, zipper): their outline is
# nearly the same from behind, so the camera stays in the front half
FRONT_ONLY = {'playera', 'sudadera', 'cuerpo_base', 'lentes'}
AZ_GRID = list(range(-180, 180, 30))
EL_GRID = (5.0, 20.0, 40.0)


def basis(az, el, dist, target, roll):
    a, e = math.radians(az), math.radians(el)
    t = np.asarray(target, float)
    pos = t + dist * np.array([math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)])
    fd = t - pos
    fd /= np.linalg.norm(fd)
    rt = np.cross(fd, [0, 0, 1.0])
    rt /= np.linalg.norm(rt)
    up = np.cross(rt, fd)
    r = math.radians(roll)
    rt, up = rt * math.cos(r) + up * math.sin(r), up * math.cos(r) - rt * math.sin(r)
    return pos, fd, rt, up


def splat(P, cam, W, H, sc):
    pos, fd, rt, up = basis(cam['az'], cam['el'], cam['distance'], cam['target'], cam['roll'])
    d = P - pos
    z = d @ fd
    f = cam['lens'] / 36.0 * W  # horizontal sensor fit, 36 mm
    u = W / 2 + f * (d @ rt) / np.maximum(z, 1e-3)
    v = H / 2 - f * (d @ up) / np.maximum(z, 1e-3)
    ww, hh = int(W * sc), int(H * sc)
    x = np.round(u * sc).astype(int)
    y = np.round(v * sc).astype(int)
    ok = (x >= 0) & (x < ww) & (y >= 0) & (y < hh) & (z > 0)
    m = np.zeros((hh, ww), bool)
    m[y[ok], x[ok]] = True
    m = ndi.binary_closing(m, iterations=2)
    return ndi.binary_fill_holes(m)


def rigid(P, L, movers, mode, x):
    """Apply per-object placements. floor: (dx, dy, yaw) about the object's centre;
    shift: (dx, dy, dz)."""
    if not movers:
        return P
    Q = P.copy()
    for k, (lab, c) in enumerate(movers):
        s = L == lab
        a, b, g = x[3 * k:3 * k + 3]
        if mode == 'floor':
            yaw = math.radians(g)
            cz, sz = math.cos(yaw), math.sin(yaw)
            q = Q[s] - c
            Q[s] = np.stack([c[0] + a + cz * q[:, 0] - sz * q[:, 1], c[1] + b + sz * q[:, 0] + cz * q[:, 1], Q[s][:, 2]], 1)
        else:
            Q[s] = Q[s] + np.array([a, b, g])
    return Q


def iou(a, b):
    return float((a & b).sum() / max((a | b).sum(), 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    a = ap.parse_args()
    d = np.load(os.path.join(ROOT, 'work', 'calib', 'points_parts.npz'))
    P_all, L_all, names = d['points'].astype(float), d['labels'], list(d['names'])
    cfg_p = os.path.join(ROOT, 'config', 'morfi.json')
    out, report = {}, {}
    rng = np.random.default_rng(0)
    for key, (sheet, objs, movable, mode) in PARTS.items():
        if a.only and key not in a.only.split(','):
            continue
        if key == 'sudadera' and 'Hoodie_Product_Cuff_L' in names:  # sleeves held out (product pose)
            objs = [o.replace('Hoodie_Cuff', 'Hoodie_Product_Cuff') for o in objs]
        if key == 'playera' and 'Tshirt_Product' in names:  # the T-shirt alone keeps its sleeves
            objs = ['Tshirt_Product'] + [o for o in objs if o != 'Tshirt']
            if 'Tshirt_Product_Collar' in names:
                objs = [o.replace('Tshirt_Collar', 'Tshirt_Product_Collar') for o in objs]
        labs = [names.index(o) for o in objs if o in names]
        sel = np.isin(L_all, labs)
        P, L = P_all[sel], L_all[sel]
        if len(P) > 400000:
            k = rng.choice(len(P), 400000, replace=False)
            P, L = P[k], L[k]
        movers = [(names.index(o), P[L == names.index(o)].mean(0)) for o in movable]
        ref = Image.open(os.path.join(ROOT, 'references_masks', sheet + '.png')).convert('L')
        W, H = ref.size
        R = np.asarray(ref.resize((W // 2, H // 2), Image.BILINEAR)) > 128
        R4 = np.asarray(ref.resize((W // 4, H // 4), Image.BILINEAR)) > 128
        lo, hi = P.min(0), P.max(0)
        c0 = (lo + hi) / 2
        rad = float(np.linalg.norm(hi - lo)) / 2
        nm = 3 * len(movers)

        def unpack(x):
            cam = dict(az=float(x[0]), el=float(x[1]), distance=float(x[2]), lens=float(x[3]),
                       target=[float(c0[0] + x[4]), float(c0[1]), float(c0[2] + x[5])], roll=float(x[6]))
            return cam, x[7:7 + nm]

        def make_loss(Rm, sc, sigma, sub):
            Rs = ndi.gaussian_filter(Rm.astype(float), sigma)

            def loss(x):
                cam, rx = unpack(x)
                if not (0.2 < cam['distance'] < 30 and 15 < cam['lens'] < 400 and EL_MIN.get(key, -10) < cam['el'] < EL_MAX.get(key, 85)
                        and (key not in FRONT_ONLY or abs(cam['az']) < 80)
                        and abs(cam['roll']) < 8):
                    return 1.0
                Q = rigid(P[sub], L[sub], movers, mode, rx)
                M = ndi.gaussian_filter(splat(Q, cam, W, H, sc).astype(float), sigma)
                reg = 1e-5 * float(np.sum(np.asarray(rx[2::3] if mode == 'floor' else []) ** 2))
                return 1.0 - np.minimum(M, Rs).sum() / max(np.maximum(M, Rs).sum(), 1e-6) + reg
            return loss

        lens0 = 70.0
        dist0 = rad / math.tan(math.atan(18.0 / lens0)) * 1.15
        sub_c = rng.choice(len(P), min(len(P), 60000), replace=False)
        step = np.diag([4.0, 3.0, 0.05 * dist0, 4.0, 0.01, 0.01, 0.5] + ([0.02, 0.02, 8.0] if mode == 'floor' else [0.01, 0.01, 0.01]) * len(movers))
        coarse = make_loss(R4, 0.25, 1.0, sub_c)
        cands = []
        for az in [a for a in AZ_GRID if key not in FRONT_ONLY or abs(a) < 80]:
            for el in [e for e in EL_GRID if EL_MIN.get(key, -10) < e < EL_MAX.get(key, 85)] or [EL_MAX[key] - 5]:
                x0 = np.array([az, el, dist0, lens0, 0.0, 0.0, 0.0] + [0.0] * nm)
                cands.append((coarse(x0), x0))
        cands.sort(key=lambda t: t[0])
        best = None
        for _, x0 in cands[:4]:
            r = minimize(coarse, x0, method='Powell', options=dict(xtol=1e-3, ftol=1e-5, maxfev=1500, direc=step))
            if best is None or r.fun < best.fun:
                best = r
        sub_f = rng.choice(len(P), min(len(P), 250000), replace=False)
        best = minimize(make_loss(R, 0.5, 1.5, sub_f), best.x, method='Powell',
                        options=dict(xtol=1e-3, ftol=1e-6, maxfev=800, direc=step * 0.3))
        cam, rx = unpack(best.x)
        Q = rigid(P, L, movers, mode, rx)
        M = splat(Q, cam, W, H, 0.5)
        score = iou(M, R)
        place = {}
        for k, o in enumerate(movable):
            v = [round(float(t), 5) for t in rx[3 * k:3 * k + 3]]
            place[o] = dict(mode=mode, value=v, center=[round(float(t), 5) for t in movers[k][1]])
        out[key] = dict(sheet=sheet + '.png', res=[W, H], az=round(cam['az'], 4), el=round(cam['el'], 4),
                        distance=round(cam['distance'], 5), lens=round(cam['lens'], 4),
                        target=[round(t, 5) for t in cam['target']], roll=round(cam['roll'], 4), place=place)
        report[key] = dict(iou=round(score, 4), **out[key])
        print(f'{key:12s} IoU {score:.4f}  az {cam["az"]:.1f} el {cam["el"]:.1f} lens {cam["lens"]:.1f} {place}', flush=True)
        o = np.full(R.shape + (3,), 255, np.uint8)
        o[R & M] = (160, 160, 160)
        o[R & ~M] = (225, 45, 45)
        o[~R & M] = (40, 175, 60)
        Image.fromarray(o).save(os.path.join(ROOT, 'renders', 'comparisons', f'partfit_{key}.png'))
    cfg = json.load(open(cfg_p))
    pc = cfg.get('part_cameras', {})
    pc.update(out)
    pc['_doc'] = ('Camara (y colocacion de piezas sueltas) por lamina de producto 08-14, ajustada a su silueta '
                  'con scripts/fit_part_cameras.py; la usa scripts/render_parts.py')
    cfg['part_cameras'] = pc
    open(cfg_p, 'w').write(json.dumps(cfg, indent=1, ensure_ascii=False) + '\n')
    rp = os.path.join(ROOT, 'docs', 'part_camera_fit.json')
    old = json.load(open(rp)) if os.path.exists(rp) else {}
    old.update(report)
    json.dump(old, open(rp, 'w'), indent=1)


if __name__ == '__main__':
    main()
