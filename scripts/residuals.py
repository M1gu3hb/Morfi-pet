"""Which part of Morfi causes each silhouette difference, view by view.

    blender -b source/morfi_master.blend --python scripts/dump_skin.py -- --out work/calib/skin.npz
    python3 scripts/residuals.py [--skin work/calib/skin.npz] [--overlays]

Poses the rigged surface with each view's fitted pose (config "view_poses",
linear blend skinning of the real weights), projects it with the calibrated
camera ("camera_views") and compares it with the reference mask. Every pixel
that only the model covers (green) is attributed to the nearest visible part;
every pixel only the reference covers (red) to the closest model part. The
table lists, per view, the IoU and the share of the union lost per part, so
shape work goes where the error is.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial.transform import Rotation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import fit_cameras as F  # noqa: E402
from fit_view_poses import Skin  # noqa: E402

BONE_GROUP = {'hand': 'manos', 'fingers': 'manos', 'thumb': 'manos', 'upper_arm': 'brazos', 'forearm': 'brazos',
              'shoulder': 'brazos', 'thigh': 'piernas', 'shin': 'piernas', 'foot': 'piernas', 'toe': 'piernas'}


def group_of(obj, bone):
    if obj.startswith('Pixel'):
        return 'cubos'
    if obj.startswith(('Head', 'Eye', 'Brow', 'Glasses', 'Cornea')):
        return 'cabeza'
    if obj.startswith('Hoodie'):
        return 'sudadera'
    if obj.startswith('Tshirt'):
        return 'playera'
    if obj.startswith('Shoe'):
        return 'tenis'
    return BONE_GROUP.get(bone.split('.')[0], 'cuerpo')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skin', default=os.path.join(ROOT, 'work', 'calib', 'skin.npz'))
    ap.add_argument('--overlays', action='store_true')
    ap.add_argument('--json', default='')
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, 'config', 'morfi.json')))
    sk = Skin(a.skin)
    d = np.load(a.skin)
    labels, names = d['labels'], list(d['names'])
    P, I, W = sk.full
    groups = ['cabeza', 'cubos', 'sudadera', 'playera', 'brazos', 'manos', 'cuerpo', 'piernas', 'tenis']
    gid = {g: i for i, g in enumerate(groups)}
    pt_group = np.array([gid[group_of(names[l], sk.bones[b])] for l, b in zip(labels, I[:, 0])], np.int16)
    out = {}
    print(f'{"vista":20s} {"IoU":>6s}  ' + '  '.join(f'{g[:8]:>8s}' for g in groups))
    for view, (ref, _, pose) in F.VIEWS.items():
        if pose != 'neutral':
            continue
        cam = cfg['camera_views'][view]
        vp = cfg.get('view_poses', {}).get(view, {})
        rots = {b: Rotation.from_euler('XYZ', ang, degrees=True).as_matrix() for b, ang in vp.items()}
        Q = sk.pose(rots, full=True)
        u, v = F.project(Q, cam)
        pos = F.camera_basis(cam['az'], cam['height'], cam['distance'], cam['target'], cam.get('roll', 0.0))
        depth = (Q - pos[0]) @ pos[1]
        x = np.round(u * F.SC).astype(int)
        y = np.round(v * F.SC).astype(int)
        ok = (x >= 0) & (x < F.w) & (y >= 0) & (y < F.h)
        o = np.argsort(-depth[ok])  # far first: the nearest point is written last
        lab = np.full((F.h, F.w), -1, np.int16)
        lab[y[ok][o], x[ok][o]] = pt_group[ok][o]
        M = F.splat(Q, cam)
        _, (iy, ix) = ndi.distance_transform_edt(lab < 0, return_indices=True)
        lab = lab[iy, ix]
        R = np.asarray(Image.open(os.path.join(ROOT, 'references_masks', ref + '.png')).convert('L').resize((F.w, F.h))) > 128
        union = max((R | M).sum(), 1)
        iou = float((R & M).sum() / union)
        green = M & ~R
        red = R & ~M
        row = {}
        for g in groups:
            row[g] = dict(solo_3d=round(100 * float((green & (lab == gid[g])).sum()) / union, 2),
                          solo_ref=round(100 * float((red & (lab == gid[g])).sum()) / union, 2))
        out[view] = dict(iou=round(iou, 4), partes=row)
        print(f'{view:20s} {iou:6.4f}  ' + '  '.join(f'{row[g]["solo_3d"]:4.1f}/{row[g]["solo_ref"]:<3.1f}' for g in groups))
        if a.overlays:
            img = np.full((F.h, F.w, 3), 255, np.uint8)
            img[R & M] = (160, 160, 160)
            img[red] = (225, 45, 45)
            img[green] = (40, 175, 60)
            Image.fromarray(img).save(os.path.join(ROOT, 'renders', 'comparisons', f'resid_{view}.png'))
    print('(por parte: % de la union que solo cubre el 3D / solo la referencia)')
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
