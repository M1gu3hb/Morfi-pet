"""Morfi base body as a smooth signed-distance field (one continuous skin).

Torso (pear shape), short neck, short thick arms with mitten-like hands
(thumb + three fingers), short legs and rounded feet. Joint positions come
from config['body'] (estimated from the references through the fitted
camera; see docs/art-direction.md). The same joints drive the armature.
"""
import numpy as np
from . import sdf as S

DEFAULT_BODY = {
    "neck": [[0.0, 0.010, 0.43], [0.0, 0.016, 0.56], 0.092],
    "upper": {"c": [0.0, 0.008, 0.452], "r": [0.150, 0.100, 0.060]},
    "chest": {"c": [0.0, 0.004, 0.392], "r": [0.146, 0.106, 0.105]},
    "belly": {"c": [0.0, -0.008, 0.290], "r": [0.164, 0.126, 0.114]},
    "pelvis": {"c": [0.0, 0.004, 0.208], "r": [0.146, 0.110, 0.072]},
    "shoulder": [0.132, 0.004, 0.440],
    "elbow": [0.230, 0.004, 0.358],
    "wrist": [0.310, 0.000, 0.290],
    "arm_r": [0.043, 0.039, 0.038],
    "hip": [0.084, 0.004, 0.19],
    "knee": [0.110, 0.004, 0.115],
    "ankle": [0.142, 0.012, 0.064],
    "leg_r": [0.064, 0.058, 0.052],
    "foot": {"c": [0.152, -0.042, 0.044], "r": [0.068, 0.118, 0.050], "rz": -6.0},
    "hand": {
        "down": [0.22, 0.0, -1.0],
        "palm_c": 0.046, "palm_r": [0.036, 0.052, 0.048],
        "finger_r": 0.0205, "finger_base": 0.074, "seg1": 0.026, "seg2": 0.026,
        "finger_f": [-0.026, 0.0, 0.026], "finger_curl": 0.85,
        "thumb_base": [0.030, 0.040, 0.020], "thumb_dir": [0.7, 0.45, 0.35], "thumb_len": 0.042, "thumb_r": 0.0205
    },
    "blend": {"torso": 0.05, "limb": 0.03, "hand": 0.02, "finger": 0.007}
}


class BodySDF:
    def __init__(self, cfg):
        b = dict(DEFAULT_BODY)
        b.update(cfg.get('body', {}))
        self.b = b

    def _arm(self, P, side):
        b = self.b
        s = np.array([side, 1, 1])
        sh = np.array(b['shoulder']) * s
        el = np.array(b['elbow']) * s
        wr = np.array(b['wrist']) * s
        r = b['arm_r']
        d = S.sd_round_cone(P, sh, el, r[0], r[1])
        d = S.smin(d, S.sd_round_cone(P, el, wr, r[1], r[2]), 0.02)
        return d

    def hand_frame(self, side):
        """Wrist position and (down, forward, inward) unit axes for a hand."""
        b = self.b
        h = b['hand']
        W = np.array(b['wrist']) * np.array([side, 1, 1])
        D = np.array(b.get('hand_down', h['down'])) * np.array([side, 1, 1])
        D = D / np.linalg.norm(D)
        F = np.array([0.0, -1.0, 0.0])
        F = F - D * (F @ D)
        F /= np.linalg.norm(F)
        I = np.cross(D, F) * (-side)
        I = I - D * (I @ D) - F * (I @ F)
        I /= np.linalg.norm(I)
        if I[0] * side > 0:  # inward must point toward the body
            I = -I
        # pronation: turn the palm toward the back so the knuckles face the
        # front-outside and the thumb sits at the front-inside (as in the references)
        th = np.radians(b.get('hand_pronate_deg', 0.0))
        F, I = F * np.cos(th) + I * np.sin(th), I * np.cos(th) - F * np.sin(th)
        return W, D, F, I

    def _hand(self, P, side):
        b = self.b
        h = b['hand']
        W, D, F, I = self.hand_frame(side)
        pc = W + D * h['palm_c']
        R = np.stack([I, F, D], 1)  # local x=inward(thickness), y=forward(width), z=down(length)
        d = S.sd_ellipsoid(P, pc, h['palm_r'], R=R)
        d = S.smin(d, S.sd_round_cone(P, W - D * 0.01, pc, b['arm_r'][2], h['palm_r'][0] * 0.95), b['blend']['hand'])
        fr = h['finger_r']
        fd = None
        cu = h['finger_curl']
        for i, ff in enumerate(h['finger_f']):
            k = 1.0 - 0.10 * abs(i - 1) - (0.06 if i == 2 else 0.0)
            a = W + D * h['finger_base'] * (1.0 - 0.04 * abs(i - 1)) + F * ff + I * 0.004
            m = a + D * h['seg1'] * k + I * 0.006
            dir2 = D * (1 - cu) + I * cu
            dir2 /= np.linalg.norm(dir2)
            t = m + dir2 * h['seg2'] * k
            f1 = S.sd_round_cone(P, a - D * 0.012, m, fr * 1.04, fr)
            f1 = S.smin(f1, S.sd_round_cone(P, m, t, fr, fr * 0.94), 0.008)
            fd = f1 if fd is None else np.minimum(fd, f1)
        d = S.smin(d, fd, b['blend']['finger'] * b.get('finger_blend_mul', 2.2))
        tb = W + D * h['thumb_base'][0] + F * h['thumb_base'][1] + I * h['thumb_base'][2]
        td = D * h['thumb_dir'][0] + F * h['thumb_dir'][1] + I * h['thumb_dir'][2]
        td /= np.linalg.norm(td)
        tt = tb + td * h['thumb_len']
        th = S.sd_round_cone(P, tb - td * 0.015, tt, h['thumb_r'] * 1.12, h['thumb_r'])
        d = S.smin(d, th, b['blend']['finger'])
        return d

    def _leg(self, P, side):
        b = self.b
        s = np.array([side, 1, 1])
        hp = np.array(b['hip']) * s
        kn = np.array(b['knee']) * s
        an = np.array(b['ankle']) * s
        r = b['leg_r']
        d = S.sd_round_cone(P, hp, kn, r[0], r[1])
        d = S.smin(d, S.sd_round_cone(P, kn, an, r[1], r[2]), 0.02)
        f = b['foot']
        fc = np.array(f['c']) * s
        R = S.rot_matrix(0, 0, side * f.get('rz', 0.0))
        foot = S.sd_ellipsoid(P, fc, f['r'], R=R)
        d = S.smin(d, foot, 0.03)
        return d

    def torso(self, P):
        b = self.b
        d = S.sd_ellipsoid(P, b['chest']['c'], b['chest']['r'])
        d = S.smin(d, S.sd_ellipsoid(P, b['upper']['c'], b['upper']['r']), b['blend']['torso'])
        d = S.smin(d, S.sd_ellipsoid(P, b['belly']['c'], b['belly']['r']), b['blend']['torso'])
        d = S.smin(d, S.sd_ellipsoid(P, b['pelvis']['c'], b['pelvis']['r']), b['blend']['torso'])
        n0, n1, nr = b['neck']
        d = S.smin(d, S.sd_capsule(P, n0, n1, nr), 0.05)
        return d

    def __call__(self, P, parts=('torso', 'arms', 'hands', 'legs')):
        b = self.b
        d = self.torso(P)
        for side in (-1, 1):
            d = S.smin(d, self._arm(P, side), b['blend']['limb'])
            d = S.smin(d, self._hand(P, side), b['blend']['hand'])
            d = S.smin(d, self._leg(P, side), b['blend']['limb'])
        return d

    def bounds(self):
        return (-0.43, -0.22, -0.01), (0.43, 0.20, 0.60)
