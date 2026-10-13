"""White low-top sneakers (separate left/right objects).

Built in a local frame (toe toward -Y, ground at z=0), then placed per foot:
rubber sole with foxing groove and sidewall notches, padded upper with a
real foot cavity and collar, toe-cap seam, tongue, two wide elastic straps
through big eyelets, and a blue heel counter panel.
"""
import math
import numpy as np

from . import meshutil as mu
from . import materials as mats
from . import sdf as S

DEFAULT = {
    "half_len": 0.159, "w_fore": 0.100, "w_heel": 0.084, "p": 2.3,
    "sole_h": 0.050, "groove_z": 0.034, "toe_spring": 0.010,
    "upper_top": {"toe": 0.078, "instep": 0.118, "collar": 0.150},
    "opening": {"cy": 0.050, "rx": 0.060, "ry": 0.072, "z": 0.105},
    "blue_plane": {"y0": 0.080, "slope": 0.62},
    "straps_y": [-0.058, -0.016], "strap_w": 0.012, "strap_t": 0.0045,
    "place": {"x": 0.163, "y": -0.047, "toe_out_deg": 5.0},
}


class ShoeSDF:
    def __init__(self, cfg):
        p = dict(DEFAULT)
        p.update(cfg.get('shoes', {}))
        self.p = p

    def foot2d(self, x, y, grow=0.0):
        p = self.p
        L = p['half_len'] + grow
        t = np.clip((y + L) / (2 * L), 0, 1)  # 0 toe, 1 heel
        w = p['w_fore'] + (p['w_heel'] - p['w_fore']) * S.smoothstep(0.35, 1.0, t) + grow
        # slightly more pointed toe, rounder heel
        rho = (np.abs(x / w) ** p['p'] + np.abs(y / L) ** p['p']) ** (1 / p['p'])
        return (rho - 1.0) * min(w.min() if hasattr(w, 'min') else w, L) * 0.95

    def top_height(self, x, y):
        p = self.p['upper_top']
        L = self.p['half_len']
        t = np.clip((y + L) / (2 * L), 0, 1)
        hy = np.interp(t, [0.0, 0.12, 0.40, 0.62, 1.0], [p['toe'] * 0.85, p['toe'], p['instep'], p['collar'], p['collar']])
        w = self.p['w_fore']
        side = np.clip(np.abs(x) / w, 0, 1)
        return hy - 0.016 * side ** 2.2

    def sole(self, P):
        p = self.p
        x, y, z = P
        L = p['half_len']
        zb = p['toe_spring'] * S.smoothstep(-0.07, -L, y) ** 2
        d2 = self.foot2d(x, y, grow=0.004)
        d = S.extrude(d2, z - (p['sole_h'] + zb) / 2, (p['sole_h'] - zb) / 2, 0.010)
        # foxing groove around the sidewall
        gz = p['groove_z']
        groove = np.maximum(np.abs(z - gz) - 0.0013, -d - 0.0025)
        d = np.maximum(d, -groove)
        # vertical notches below the groove
        notch_y = np.arange(-0.14, 0.15, 0.042)
        nd = np.min(np.abs(y[..., None] - notch_y), axis=-1) if y.ndim else np.min(np.abs(y - notch_y))
        notch = np.maximum(np.maximum(nd - 0.0007, z - gz + 0.003), -d - 0.0010)
        notch = np.maximum(notch, 0.004 - z)
        if self.p.get('notches', False):
            d = np.maximum(d, -notch)
        return d

    def upper_outer(self, P):
        x, y, z = P
        d2 = self.foot2d(x, y, grow=-0.004)
        side = S.extrude(d2, z - 0.10, 0.10, 0.0)
        top = z - self.top_height(x, y)
        d = S.smax(side, top, 0.045)
        d = S.smax(d, 0.03 - z, 0.005)
        return d

    def cavity(self, P):
        x, y, z = P
        o = self.p['opening']
        cav = np.maximum(self.upper_outer(P) + 0.011, 0.040 - z)
        hole = S.sd_ellipsoid(P, (0, o['cy'], o['z'] + 0.06), (o['rx'], o['ry'], 0.075))
        return S.smin(cav, hole, 0.012), hole

    def collar(self, P):
        o = self.p['opening']
        x, y, z = P
        zc = self.p['upper_top']['collar'] - 0.010
        q = np.sqrt((x / (o['rx'] + 0.006)) ** 2 + ((y - o['cy']) / (o['ry'] + 0.006)) ** 2) * (o['rx'] + 0.006) - (o['rx'] + 0.006)
        return np.sqrt(q * q + (z - zc) ** 2) - 0.0085

    def upper(self, P):
        x, y, z = P
        d = self.upper_outer(P)
        cav, hole = self.cavity(P)
        d = S.smax(d, -cav, 0.010)
        # toe-cap seam groove
        ys = -0.092 - 0.035 * (x / 0.08) ** 2
        seam = np.maximum(np.abs(y - ys) - 0.0011, -d - 0.0018)
        seam = np.maximum(seam, 0.055 - z)
        d = np.maximum(d, -seam)
        # quarter panel seam (side line from instep to heel)
        zs = 0.085 + 0.02 * np.clip((y + 0.02) / 0.12, 0, 1)
        seam2 = np.maximum(np.abs(z - zs) - 0.001, -d - 0.0016)
        seam2 = np.maximum(seam2, np.maximum(-0.03 - y, y - 0.07))
        d = np.maximum(d, -seam2)
        return d

    def tongue(self, P):
        x, y, z = P
        uo = self.upper_outer(P)
        pad = np.maximum(uo - 0.0035, -(uo + 0.004))
        pad = S.smax(pad, np.abs(x) - 0.033, 0.006)
        pad = S.smax(pad, y - 0.006, 0.006)
        pad = S.smax(pad, -0.078 - y, 0.01)
        # upper end of the tongue standing in front of the shin
        R = S.rot_matrix(-25, 0, 0)
        top = S.sd_ellipsoid(P, (0.0, 0.002, 0.120), (0.033, 0.010, 0.024), R=R)
        return S.smin(pad, top, 0.012)

    def blue_panel(self, P):
        bp = self.p['blue_plane']
        x, y, z = P
        uo = self.upper_outer(P)
        d = np.maximum(uo - 0.0024, -(uo + 0.0003))
        plane = (bp['y0'] - y) + bp['slope'] * (z - self.p['sole_h'])
        d = S.smax(d, plane / math.sqrt(1 + bp['slope'] ** 2), 0.003)
        cav, hole = self.cavity(P)
        d = np.maximum(d, -hole)
        d = np.maximum(d, self.p['sole_h'] - 0.004 - z)
        return d

    def straps(self, P):
        """Wide elastic straps conforming to the vamp surface."""
        x, y, z = P
        p = self.p
        uo = np.minimum(self.upper_outer(P), self.tongue(P))
        shell = np.maximum(uo - 0.0040, -(uo + 0.0004))
        d = None
        for ys in p['straps_y']:
            band = np.maximum(shell, np.abs(y - ys) - p['strap_w'])
            band = np.maximum(band, np.abs(x) - 0.058)
            band = np.maximum(band, 0.06 - z)
            d = band if d is None else np.minimum(d, band)
        return d

    def eyelets(self, P):
        d = None
        for ys in self.p['straps_y']:
            for side in (-1, 1):
                c = (side * 0.066, ys, self.top_height(np.array([0.066]), np.array([ys]))[0] - 0.016)
                R = S.rot_matrix(0, 90 * side, 0)
                t = S.sd_torus(P, c, 0.0105, 0.0034, Rm=R)
                d = t if d is None else np.minimum(d, t)
        return d


def build(cfg, col, parent, tex_dir, h, quality):
    sh = ShoeSDF(cfg)
    c = cfg['colors']
    m_up = mats.flat('M_ShoeLeather', c['shoe_white'], rough=0.52, spec=0.45, sheen=0.1,
                     bump=dict(scale=420.0, strength=0.08, distance=0.0006, fine=1500.0))
    m_sole = mats.flat('M_ShoeSole', c['shoe_sole'], rough=0.62, spec=0.4,
                       bump=dict(scale=700.0, strength=0.04, distance=0.0004, fine=2000.0))
    m_blue = mats.flat('M_ShoeBlue', c['shoe_blue'], rough=0.48, spec=0.45,
                       bump=dict(scale=420.0, strength=0.08, distance=0.0006, fine=1500.0))
    m_strap = mats.flat('M_ShoeStrap', c['shoe_white'], rough=0.6, spec=0.35, sheen=0.3,
                        bump=dict(scale=900.0, strength=0.12, distance=0.0005, fine=2500.0))
    hh = h * 0.75
    bmin, bmax = (-0.12, -0.18, -0.01), (0.12, 0.18, 0.19)
    parts = [
        (sh.sole, m_sole, hh),
        (sh.upper, m_up, hh),
        (sh.tongue, m_up, hh),
        (sh.blue_panel, m_blue, hh * 0.8),
        (sh.straps, m_strap, hh * 0.8),
        (sh.eyelets, m_up, hh * 0.6),
    ]
    meshes = [S.polygonize(fn, bmin, bmax, r) for fn, _m, r in parts]
    out = {}
    pl = sh.p['place']
    for name, side in (('Shoe_R', -1), ('Shoe_L', 1)):
        V, F, MI = [], [], []
        off = 0
        mat_list = []
        for (fn, m, r), (v, f) in zip(parts, meshes):
            v = v.copy()
            if side < 0:
                v[:, 0] *= -1
                f = f[:, ::-1]
            if m not in mat_list:
                mat_list.append(m)
            V.append(v)
            F.append(f + off)
            MI += [mat_list.index(m)] * len(f)
            off += len(v)
        ob = mu.fast_mesh_object(name, np.vstack(V), np.vstack(F), collection=col, parent=parent)
        for m in mat_list:
            ob.data.materials.append(m)
        mu.set_face_materials(ob, MI)
        mu.cube_project_uv(ob, 6.0)
        ob.location = (side * pl['x'], pl['y'], 0.0)
        ob.rotation_euler = (0, 0, math.radians(side * pl['toe_out_deg']))
        out[name] = ob
    return out
