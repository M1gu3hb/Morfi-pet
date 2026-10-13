"""Pose Morfi for each reference shot (per-view pose + camera refinement).

The reference renders are not one rigid pose seen from six cameras: between
shots the head turns a few degrees and the arms move. Like posing a figure for
each photograph, every view gets its own small pose, found by matching the
silhouette with linear blend skinning of the real rig weights:

    blender -b source/morfi_master.blend --python scripts/dump_skin.py -- --out work/calib/skin.npz
    python3 scripts/fit_view_poses.py

Parameters per view: head (3 rotations), upper arms (2 each), forearms (1 each)
and the camera (azimuth, height, distance, target x/z, roll). Rotations are in
degrees about world axes at the bone's rest head, and are written to
config/morfi.json -> "view_poses"; rig_model.py turns them into "Ref_<view>"
actions and render_views.py uses them. Angles are regularised so the pose stays
natural (a 10 deg turn costs about as much as 0.2 % of IoU).
"""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import fit_cameras as F  # noqa: E402

# (bone, axes) driven by the optimiser; axes are world axes x, y, z
DOF = [('head', 'xyz'), ('upper_arm.L', 'xy'), ('upper_arm.R', 'xy'), ('forearm.L', 'x'), ('forearm.R', 'x')]
LAMBDA = 2e-5  # regularisation per squared degree


class Skin:
    def __init__(self, path, n_sub=160000, seed=0):
        d = np.load(path)
        self.bones = list(d['bones'])
        self.heads = d['heads'].astype(float)
        self.parents = d['parents']
        P, I, W = d['points'].astype(float), d['idx'].astype(int), d['w'].astype(float)
        rng = np.random.default_rng(seed)
        self.full = (P, I, W)
        s = rng.choice(len(P), min(n_sub, len(P)), replace=False)
        self.sub = (P[s], I[s], W[s])
        self.bi = {b: i for i, b in enumerate(self.bones)}

    def matrices(self, rots):
        """rots: {bone: (3,3) world rotation at the bone's rest head} -> (B,4,4) skinning matrices."""
        B = len(self.bones)
        G = [None] * B
        order = sorted(range(B), key=lambda i: self.depth(i))
        for i in order:
            R = rots.get(self.bones[i])
            L = np.eye(4)
            if R is not None:
                h = self.heads[i]
                L[:3, :3] = R
                L[:3, 3] = h - R @ h
            p = self.parents[i]
            G[i] = L if p < 0 else G[p] @ L
        return np.stack(G)

    def depth(self, i):
        d = 0
        while self.parents[i] >= 0:
            i = self.parents[i]
            d += 1
        return d

    def pose(self, rots, full=False):
        P, I, W = self.full if full else self.sub
        G = self.matrices(rots)
        out = np.zeros_like(P)
        for k in range(4):
            Gk = G[I[:, k]]
            pk = np.einsum('nij,nj->ni', Gk[:, :3, :3], P) + Gk[:, :3, 3]
            out += W[:, k:k + 1] * pk
        return out


def rots_from(x):
    rots, j = {}, 0
    for bone, axes in DOF:
        ang = np.zeros(3)
        for a in axes:
            ang['xyz'.index(a)] = x[j]
            j += 1
        rots[bone] = Rotation.from_euler('XYZ', ang, degrees=True).as_matrix()  # = Rx Ry Rz, like rig_model.set_rot
    return rots, j


def main():
    cfg_p = os.path.join(ROOT, 'config', 'morfi.json')
    cfg = json.load(open(cfg_p))
    skin = Skin(os.path.join(ROOT, 'work', 'calib', 'skin.npz'))
    npose = sum(len(a) for _, a in DOF)
    poses, cams, report = {}, {}, {}
    for view, (ref, az0, pose) in F.VIEWS.items():
        if pose != 'neutral':
            continue
        R = np.asarray(Image.open(os.path.join(ROOT, 'references_masks', ref + '.png')).convert('L').resize((F.w, F.h))) > 128
        R4 = np.asarray(Image.open(os.path.join(ROOT, 'references_masks', ref + '.png')).convert('L').resize((F.w // 2, F.h // 2))) > 128
        base = cfg['camera_views'][view]

        def unpack(x):
            rots, j = rots_from(x)
            c = dict(az=base['az'] + x[j], height=base['height'] + x[j + 1], distance=base['distance'] + x[j + 2],
                     lens=base['lens'], target=[base['target'][0] + x[j + 3], base['target'][1], base['target'][2] + x[j + 4]],
                     roll=base.get('roll', 0.0) + x[j + 5])
            return rots, c

        def make_loss(Rm, sc, sigma):
            from scipy import ndimage as ndi
            Rs = ndi.gaussian_filter(Rm.astype(float), sigma)

            def loss(x):
                rots, c = unpack(x)
                if abs(c['roll']) > 3 or not (0.3 < c['height'] < 1.25):
                    return 1.0
                P = skin.pose(rots)
                M = ndi.gaussian_filter(F.splat(P, c, None, sc).astype(float), sigma)
                iou = np.minimum(M, Rs).sum() / max(np.maximum(M, Rs).sum(), 1e-6)
                return 1.0 - iou + LAMBDA * float(np.sum(np.asarray(x[:npose]) ** 2))
            return loss

        x0 = np.zeros(npose + 6)
        r0, c0 = unpack(x0)
        before = F.iou(F.splat(skin.pose(r0, True), c0), R)
        step = np.diag([4.0] * npose + [1.0, 0.03, 0.05, 0.005, 0.005, 0.3])
        res = minimize(make_loss(R4, F.SC / 2, 1.0), x0, method='Powell',
                       options=dict(xtol=1e-2, ftol=1e-5, maxfev=3000, direc=step))
        res = minimize(make_loss(R, F.SC, 1.5), res.x, method='Powell',
                       options=dict(xtol=1e-2, ftol=1e-6, maxfev=600, direc=step * 0.3))
        rots, cam = unpack(res.x)
        after = F.iou(F.splat(skin.pose(rots, True), cam), R)
        vp, j = {}, 0
        for bone, axes in DOF:
            ang = [0.0, 0.0, 0.0]
            for a in axes:
                ang['xyz'.index(a)] = round(float(res.x[j]), 3)
                j += 1
            vp[bone] = ang
        poses[view] = vp
        cams[view] = {k: (round(v, 5) if isinstance(v, float) else [round(t, 5) for t in v]) for k, v in cam.items()}
        report[view] = dict(iou_before=round(before, 4), iou_after=round(after, 4), pose=vp, camera=cams[view])
        print(f'{view:20s} IoU {before:.4f} -> {after:.4f}  pose {vp}', flush=True)
        M = F.splat(skin.pose(rots, True), cam)
        o = np.full((F.h, F.w, 3), 255, np.uint8)
        o[R & M] = (160, 160, 160)
        o[R & ~M] = (225, 45, 45)
        o[~R & M] = (40, 175, 60)
        Image.fromarray(o).save(os.path.join(ROOT, 'renders', 'comparisons', f'posefit_{view}.png'))
    cfg = json.load(open(cfg_p))
    cfg['view_poses'] = poses
    cfg['view_poses']['_doc'] = ('Pose por toma (grados, ejes del mundo en la cabeza de cada hueso en reposo), '
                                 'ajustada a la silueta de cada referencia con scripts/fit_view_poses.py')
    for v, c in cams.items():
        cfg['camera_views'][v] = c
    open(cfg_p, 'w').write(json.dumps(cfg, indent=1, ensure_ascii=False) + '\n')
    json.dump(report, open(os.path.join(ROOT, 'docs', 'pose_fit.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
