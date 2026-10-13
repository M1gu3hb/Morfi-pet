"""Pose Morfi for each reference shot (per-view pose + camera refinement).

The reference renders are not one rigid pose seen from six cameras: between
shots the head turns a few degrees and the arms move. Like posing a figure for
each photograph, every view gets its own small pose, found by matching the
silhouette with linear blend skinning of the real rig weights:

    blender -b source/morfi_master.blend --python scripts/dump_skin.py -- --out work/calib/skin.npz
    python3 scripts/fit_view_poses.py

Parameters per view: head (3 rotations), upper arms (2 each), forearms (1 each),
the turn of the pixel-cube cluster (1) and the camera (azimuth, height,
distance, target x/z, roll). The cube turn is the one "cheat" of the set: the
profile references show the three cubes laid out as seen from the front (a
camera-facing cheat, as in stylised animation), so the cluster may turn about
its bone; it starts from the best of a few quarter turns.

The match is semantic, not only the outline: both the reference and the model
are split into colour classes (blue skin, black hoodie / frame, white-grey
shirt / shoes / eye whites); for the model every pixel takes the class of the
nearest surface point (z-buffer), so a hand in front of the hoodie or the
glasses on a turned head count even when they are inside the silhouette.
The loss mixes the silhouette IoU with the mean per-class IoU (--outline-only
turns this off). Rotations are in
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
DOF = [('head', 'xyz'), ('upper_arm.L', 'xy'), ('upper_arm.R', 'xy'), ('forearm.L', 'x'), ('forearm.R', 'x'),
       ('pixels', 'z')]
LAMBDA = 2e-5  # regularisation per squared degree
LAMBDA_BONE = {'pixels': 1e-7, 'upper_arm.L': 6e-6, 'upper_arm.R': 6e-6}  # cube turn is free (camera-facing cheat); arms swing
ARM_SWINGS = (-35.0, -18.0, 0.0)  # starting forward swings tried for each arm (deg about world X, - = forward)
# starting adductions (deg about world Y, toward the body; mirrored for the right arm). In the
# profiles the arms hang along the body: from the side an arm still held out as at rest points at
# the camera, and the outline alone cannot tell (the arm moves along the line of sight)
ARM_ADDUCT = (0.0, 20.0, 38.0)
PIXEL_TURNS = (0.0, 90.0, -90.0, 180.0)
W_OUTLINE = 0.5  # share of the outline IoU in the semantic loss
# camera heights that the outline cannot pin down. In a profile the silhouette
# hardly changes with the camera height, and the fit drifted to 1.1 m for 05
# (looking down on the shoes, the far shoe appearing above the near one); in
# the reference the far shoe only peeks ~25 px above the near one, which with
# the feet 0.18 m apart at 2.5 m means a camera ~0.4 m high, the same as the
# fit gives for the other profile (03).
HEIGHT_FIX = {'profile_right': 0.40}
# bones whose pose is set by eye, not fitted: in the profiles the near arm hangs
# along the body with the hand forward (03, 05); held out as at rest it points
# at the camera and shows the open end of the cuff. Sleeve and body are both
# black, so neither the outline nor the colour zones can see the difference.
# Only the adduction is fixed; the forward swing and the elbow are still fitted.
POSE_FIX = {'profile_left': {('upper_arm.L', 'y'): 18.0},
            'profile_right': {('upper_arm.R', 'y'): -18.0}}
NCLS = 3         # 0 blue skin, 1 black (hoodie, frame, brows), 2 white / grey (shirt, shoes, eye whites)


def point_class(name):
    if name.startswith(('Glasses_Lens', 'Cornea')):
        return -1
    if name.startswith(('Head', 'Body_Base', 'Pixel')):
        return 0
    if name.startswith(('Hoodie_Zipper', 'Tshirt', 'Shoe', 'Eye')):
        return 2
    if name.startswith(('Hoodie', 'Glasses_Frame', 'Brow')):
        return 1
    return -1


def ref_classes(ref, size, mask):
    """Colour classes of a reference image (-1 = unclassified inside the figure)."""
    from scipy import ndimage as ndi
    a = np.asarray(Image.open(os.path.join(ROOT, 'references', ref + '.png')).convert('RGB').resize(size, Image.LANCZOS))
    a = ndi.gaussian_filter(a.astype(float) / 255, (0.8, 0.8, 0))
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = a.mean(-1)
    blue = (b > 0.55) & (b - r > 0.25)
    c = np.full(mask.shape, -1, np.int16)
    c[blue] = 0
    c[(lum < 0.30) & ~blue] = 1
    c[(lum > 0.60) & (b - r < 0.16) & ~blue] = 2
    c[~mask] = -2
    return c


def class_map(P, C, cam, sc, tol=0.015):
    """Z-buffered class image of the posed points (-2 = background).

    A point only counts if it is within tol of the nearest surface around its
    pixel (3x3 minimum depth), so sparse points of hidden parts (the far eye,
    the inside of the hoodie) cannot leak through the front surface."""
    from scipy import ndimage as ndi
    u, v = F.project(P, cam)
    pos, fd, _, _ = F.camera_basis(cam['az'], cam['height'], cam['distance'], cam['target'], cam.get('roll', 0.0))
    depth = (P - pos) @ fd
    ww, hh = int(F.W * sc), int(F.H * sc)
    x = np.round(u * sc).astype(int)
    y = np.round(v * sc).astype(int)
    ok = (x >= 0) & (x < ww) & (y >= 0) & (y < hh)
    D = np.full((hh, ww), np.inf)
    np.minimum.at(D, (y[ok], x[ok]), depth[ok])
    Dm = ndi.minimum_filter(D, size=3)
    vis = ok.copy()
    vis[ok] = depth[ok] <= Dm[y[ok], x[ok]] + tol
    vis &= C >= 0
    o = np.argsort(-depth[vis])
    lab = np.full((hh, ww), -1, np.int16)
    lab[y[vis][o], x[vis][o]] = C[vis][o]
    M = F.splat(P, cam, None, sc)
    if (lab >= 0).any():
        _, (iy, ix) = ndi.distance_transform_edt(lab < 0, return_indices=True)
        lab = lab[iy, ix]
    lab[~M] = -2
    return lab, M


class Skin:
    def __init__(self, path, n_sub=120000, seed=0):
        d = np.load(path)
        self.bones = list(d['bones'])
        self.heads = d['heads'].astype(float)
        self.parents = d['parents']
        P, I, W = d['points'].astype(float), d['idx'].astype(int), d['w'].astype(float)
        if 'labels' in d:
            names = list(d['names'])
            lut = np.array([point_class(n) for n in names], np.int16)
            C = lut[d['labels']]
        else:
            C = np.zeros(len(P), np.int16)
        rng = np.random.default_rng(seed)
        self.full = (P, I, W)
        self.cls_full = C
        s = rng.choice(len(P), min(n_sub, len(P)), replace=False)
        self.sub = (P[s], I[s], W[s])
        self.cls_sub = C[s]
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

    def classes(self, full=False):
        return self.cls_full if full else self.cls_sub

    def pose(self, rots, full=False):
        P, I, W = self.full if full else self.sub
        G = self.matrices(rots)
        out = np.zeros_like(P)
        for k in range(4):
            Gk = G[I[:, k]]
            pk = np.einsum('nij,nj->ni', Gk[:, :3, :3], P) + Gk[:, :3, 3]
            out += W[:, k:k + 1] * pk
        return out


def fix_index(key):
    """Index in the parameter vector of a (bone, axis) DOF."""
    j = 0
    for bone, axes in DOF:
        for a in axes:
            if (bone, a) == key:
                return j
            j += 1
    raise KeyError(key)


def rots_from(x):
    rots, j = {}, 0
    for bone, axes in DOF:
        ang = np.zeros(3)
        for a in axes:
            ang['xyz'.index(a)] = x[j]
            j += 1
        rots[bone] = Rotation.from_euler('XYZ', ang, degrees=True).as_matrix()  # = Rx Ry Rz, like rig_model.set_rot
    return rots, j


def semantic_iou(lab, RC):
    """Mean per-class IoU (reference pixels without a class are ignored)."""
    w = RC != -1
    out = []
    for k in range(NCLS):
        a, b = (lab == k) & w, (RC == k) & w
        u = (a | b).sum()
        if u:
            out.append((a & b).sum() / u)
    return float(np.mean(out)) if out else 0.0


def main():
    import argparse
    from scipy import ndimage as ndi
    ap = argparse.ArgumentParser()
    ap.add_argument('--views', default='')
    ap.add_argument('--outline-only', action='store_true')
    ap.add_argument('--skin', default=os.path.join(ROOT, 'work', 'calib', 'skin.npz'))
    ap.add_argument('--dry-run', action='store_true', help='do not write the config')
    args = ap.parse_args()
    semantic = not args.outline_only
    cfg_p = os.path.join(ROOT, 'config', 'morfi.json')
    cfg = json.load(open(cfg_p))
    skin = Skin(args.skin)
    npose = sum(len(a) for _, a in DOF)
    lam = np.array([LAMBDA_BONE.get(b, LAMBDA) for b, axes in DOF for _ in axes])
    jpix = sum(len(a) for b, a in DOF[:[b for b, _ in DOF].index('pixels')])
    poses, cams, report = {}, {}, {}
    for view, (ref, az0, pose) in F.VIEWS.items():
        if pose != 'neutral' or (args.views and view not in args.views.split(',')):
            continue
        R = np.asarray(Image.open(os.path.join(ROOT, 'references_masks', ref + '.png')).convert('L').resize((F.w, F.h))) > 128
        R4 = np.asarray(Image.open(os.path.join(ROOT, 'references_masks', ref + '.png')).convert('L').resize((F.w // 2, F.h // 2))) > 128
        RC = ref_classes(ref, (F.w, F.h), R)
        RC4 = ref_classes(ref, (F.w // 2, F.h // 2), R4)
        base = cfg['camera_views'][view]

        def unpack(x):
            x = np.array(x, float)
            for k, ang in POSE_FIX.get(view, {}).items():
                x[fix_index(k)] = ang
            rots, j = rots_from(x)
            c = dict(az=base['az'] + x[j], height=HEIGHT_FIX.get(view, base['height'] + x[j + 1]), distance=base['distance'] + x[j + 2],
                     lens=base['lens'], target=[base['target'][0] + x[j + 3], base['target'][1], base['target'][2] + x[j + 4]],
                     roll=base.get('roll', 0.0) + x[j + 5])
            return rots, c

        def make_loss(Rm, RCm, sc, sigma):
            Rs = ndi.gaussian_filter(Rm.astype(float), sigma)
            wt = (RCm != -1).astype(float)
            Rcs = [ndi.gaussian_filter((RCm == k).astype(float), sigma) for k in range(NCLS)]

            def loss(x):
                rots, c = unpack(x)
                if abs(c['roll']) > 3 or not (0.3 < c['height'] < 1.25):
                    return 1.0
                P = skin.pose(rots)
                if semantic:
                    lab, Mb = class_map(P, skin.classes(), c, sc)
                else:
                    Mb = F.splat(P, c, None, sc)
                M = ndi.gaussian_filter(Mb.astype(float), sigma)
                score = np.minimum(M, Rs).sum() / max(np.maximum(M, Rs).sum(), 1e-6)
                if semantic:
                    ci = []
                    for k in range(NCLS):
                        Mk = ndi.gaussian_filter((lab == k).astype(float), sigma)
                        den = (np.maximum(Mk, Rcs[k]) * wt).sum()
                        if den > 1e-6:
                            ci.append((np.minimum(Mk, Rcs[k]) * wt).sum() / den)
                    score = W_OUTLINE * score + (1 - W_OUTLINE) * float(np.mean(ci))
                return 1.0 - score + float(np.sum(lam * np.asarray(x[:npose]) ** 2))
            return loss

        x0 = np.zeros(npose + 6)
        r0, c0 = unpack(x0)
        P0 = skin.pose(r0, True)
        lab0, M0 = class_map(P0, skin.classes(True), c0, F.SC)
        before, sem_before = F.iou(M0, R), semantic_iou(lab0, RC)
        coarse = make_loss(R4, RC4, F.SC / 2, 1.0)
        fine = make_loss(R, RC, F.SC, 1.5)
        # cube turn: quarter turns plus "facing this camera" (= the view azimuth),
        # judged at half resolution (the cubes are only a few pixels at a quarter)
        turns = []
        for t in PIXEL_TURNS + (round(base['az'] - cfg['camera_views'].get('front', {}).get('az', 0.0), 1),):
            xt = x0.copy()
            xt[jpix] = t
            turns.append((fine(xt), t))
        x0[jpix] = min(turns)[1]
        # arms: start from the best of a few forward swings (a hand in front of the
        # body is inside the outline, so Powell from zero would not find it)
        jl = sum(len(a) for b, a in DOF[:[b for b, _ in DOF].index('upper_arm.L')])
        jr = sum(len(a) for b, a in DOF[:[b for b, _ in DOF].index('upper_arm.R')])
        swings = []
        for ad in ARM_ADDUCT:
            for sl in ARM_SWINGS:
                for sr in ARM_SWINGS:
                    xt = x0.copy()
                    xt[jl], xt[jr] = sl, sr
                    xt[jl + 1], xt[jr + 1] = ad, -ad
                    swings.append((coarse(xt), sl, sr, ad))
        _, x0[jl], x0[jr], ad = min(swings)
        x0[jl + 1], x0[jr + 1] = ad, -ad
        step = np.diag([4.0] * npose + [1.0, 0.03, 0.05, 0.005, 0.005, 0.3])
        res = minimize(coarse, x0, method='Powell',
                       options=dict(xtol=1e-2, ftol=1e-5, maxfev=2000, direc=step))
        res = minimize(fine, res.x, method='Powell',
                       options=dict(xtol=1e-2, ftol=1e-6, maxfev=600, direc=step * 0.3))
        # the cube turn has flat stretches where Powell stops: finish with a 1D scan
        xs = res.x.copy()
        scan = []
        for t in np.arange(-180.0, 180.0, 15.0):
            xs[jpix] = t
            scan.append((fine(xs), t))
        best_t = min(scan)[1]
        if fine(np.r_[res.x[:jpix], best_t, res.x[jpix + 1:]]) < res.fun:
            x1 = res.x.copy()
            x1[jpix] = best_t
            res = minimize(fine, x1, method='Powell',
                           options=dict(xtol=1e-2, ftol=1e-6, maxfev=300, direc=step * 0.3))
        rots, cam = unpack(res.x)
        P1 = skin.pose(rots, True)
        lab1, M1 = class_map(P1, skin.classes(True), cam, F.SC)
        after, sem_after = F.iou(M1, R), semantic_iou(lab1, RC)
        vp, j = {}, 0
        for bone, axes in DOF:
            ang = [0.0, 0.0, 0.0]
            for a in axes:
                ang['xyz'.index(a)] = round(float(res.x[j]), 3)
                j += 1
            vp[bone] = ang
        for (b, ax), ang in POSE_FIX.get(view, {}).items():
            vp[b]['xyz'.index(ax)] = ang
        poses[view] = vp
        cams[view] = {k: (round(v, 5) if isinstance(v, float) else [round(t, 5) for t in v]) for k, v in cam.items()}
        report[view] = dict(iou_before=round(before, 4), iou_after=round(after, 4),
                            class_iou_before=round(sem_before, 4), class_iou_after=round(sem_after, 4),
                            pose=vp, camera=cams[view])
        print(f'{view:20s} IoU {before:.4f} -> {after:.4f}  classes {sem_before:.4f} -> {sem_after:.4f}  pose {vp}', flush=True)
        pal = np.array([[30, 90, 240], [25, 25, 30], [225, 225, 220], [255, 140, 0]], np.uint8)
        side = np.full((F.h, F.w * 2, 3), 255, np.uint8)
        for k in range(NCLS):
            side[:, :F.w][RC == k] = pal[k]
            side[:, F.w:][lab1 == k] = pal[k]
        side[:, :F.w][RC == -1] = pal[3]
        Image.fromarray(side).save(os.path.join(ROOT, 'renders', 'comparisons', f'semfit_{view}.png'))
        M = M1
        o = np.full((F.h, F.w, 3), 255, np.uint8)
        o[R & M] = (160, 160, 160)
        o[R & ~M] = (225, 45, 45)
        o[~R & M] = (40, 175, 60)
        Image.fromarray(o).save(os.path.join(ROOT, 'renders', 'comparisons', f'posefit_{view}.png'))
    if args.dry_run:
        return
    cfg = json.load(open(cfg_p))
    old = {k: v for k, v in cfg.get('view_poses', {}).items() if k not in poses}
    cfg['view_poses'] = dict(old, **poses)
    cfg['view_poses']['_doc'] = ('Pose por toma (grados, ejes del mundo en la cabeza de cada hueso en reposo), '
                                 'ajustada a la silueta de cada referencia con scripts/fit_view_poses.py')
    for v, c in cams.items():
        cfg['camera_views'][v] = c
    open(cfg_p, 'w').write(json.dumps(cfg, indent=1, ensure_ascii=False) + '\n')
    rp = os.path.join(ROOT, 'docs', 'pose_fit.json')
    prev = json.load(open(rp)) if os.path.exists(rp) else {}
    prev.update(report)
    json.dump(prev, open(rp, 'w'), indent=1)


if __name__ == '__main__':
    main()
