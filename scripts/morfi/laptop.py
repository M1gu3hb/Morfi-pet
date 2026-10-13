"""Closed silver laptop with the two-square mark (independent accessory).

Local frame: lid facing +Z, hinge along the back edge (+Y), front lip at -Y.
An empty 'Laptop_Grip' marks where the hero pose holds it under the arm.
"""
import math
import numpy as np

from . import meshutil as mu
from . import materials as mats
from . import sdf as S

DEFAULT = {"w": 0.236, "d": 0.176, "t_base": 0.0105, "t_lid": 0.0075, "r": 0.020, "gap": 0.0012,
           "logo_size": 0.022, "logo_r": 0.004, "logo_offset": 0.0125}


class LaptopSDF:
    def __init__(self, cfg):
        p = dict(DEFAULT)
        p.update(cfg.get('laptop', {}))
        self.p = p

    def slab(self, P, z0, z1, inset=0.0, edge=0.004):
        p = self.p
        x, y, z = P
        d2 = S.rrect2d(x, y, p['w'] / 2 - inset, p['d'] / 2 - inset, p['r'] - inset)
        return S.extrude(d2, z - (z0 + z1) / 2, (z1 - z0) / 2, edge)

    def base(self, P):
        p = self.p
        d = self.slab(P, 0.0, p['t_base'], edge=0.0045)
        x, y, z = P
        # front finger notch
        notch = S.sd_ellipsoid(P, (0, -p['d'] / 2 - 0.004, p['t_base']), (0.03, 0.009, 0.0035))
        d = S.smax(d, -notch, 0.0015)
        # side ports (USB-C + audio) on Morfi-left side (+X)
        port = S.sd_round_box(P, (p['w'] / 2, -0.035, p['t_base'] * 0.5), (0.004, 0.0045, 0.0016), 0.0015)
        jack = S.sd_capsule(P, (p['w'] / 2 + 0.003, -0.015, p['t_base'] * 0.5), (p['w'] / 2 - 0.004, -0.015, p['t_base'] * 0.5), 0.0016)
        d = np.maximum(d, -np.minimum(port, jack))
        return d

    def lid(self, P):
        p = self.p
        z0 = p['t_base'] + p['gap']
        d = self.slab(P, z0, z0 + p['t_lid'], edge=0.0038)
        # hinge barrel along the back edge
        x, y, z = P
        hinge = S.sd_capsule(P, (-p['w'] / 2 + 0.03, p['d'] / 2 - 0.004, z0), (p['w'] / 2 - 0.03, p['d'] / 2 - 0.004, z0), 0.0058)
        return S.smin(d, hinge, 0.002)

    def logo(self, P):
        p = self.p
        z_top = p['t_base'] + p['gap'] + p['t_lid']
        s, r, o = p['logo_size'] / 2, p['logo_r'], p['logo_offset']
        x, y, z = P
        d = None
        for cx, cy in ((-o, o), (o, -o)):
            d2 = S.rrect2d(x - cx, y - cy, s, s, r)
            dd = S.extrude(d2, z - z_top, 0.0004, 0.0002)
            d = dd if d is None else np.minimum(d, dd)
        return d


def build(cfg, col, parent, quality):
    lp = LaptopSDF(cfg)
    c = cfg['colors']
    m_al = mats.flat('M_Laptop', c['laptop'], rough=0.34, metal=1.0, spec=0.5)
    m_logo = mats.flat('M_LaptopLogo', c['laptop_logo'], rough=0.35, spec=0.5)
    m_dark = mats.flat('M_LaptopPort', '#1A1C20', rough=0.6)
    p = lp.p
    h = 0.0012 if quality == 'final' else 0.0018
    bmin = (-p['w'] / 2 - 0.01, -p['d'] / 2 - 0.01, -0.006)
    bmax = (p['w'] / 2 + 0.01, p['d'] / 2 + 0.01, 0.026)
    V, F, MI = [], [], []
    off = 0
    for k, (fn, hh) in enumerate(((lp.base, h), (lp.lid, h))):
        v, f = S.polygonize(fn, bmin, bmax, hh)
        V.append(v)
        F.append(f + off)
        MI += [0] * len(f)
        off += len(v)
    ob = mu.fast_mesh_object('Laptop', np.vstack(V), np.vstack(F), collection=col, parent=parent)
    ob.data.materials.append(m_al)
    mu.set_face_materials(ob, MI)
    mu.cube_project_uv(ob, 8.0)
    # the two blue squares: their own small exact mesh (never decimated, so they
    # cannot melt into the lid), slightly raised above the lid surface
    from .accessories import rounded_cube_mesh
    z_top = p['t_base'] + p['gap'] + p['t_lid']
    s, o = p['logo_size'] / 2, p['logo_offset']
    lv, lf = [], []
    for cx, cy in ((-o, o), (o, -o)):
        v, f = rounded_cube_mesh((s, s, 0.0008), e=4.0, N=10)
        lf.append(f + sum(len(x) for x in lv))
        lv.append(v + np.array([cx, cy, z_top + 0.0003]))
    logo = mu.mesh_object('Laptop_Logo', np.vstack(lv), np.vstack(lf), collection=col, parent=ob)
    mu.assign_material(logo, m_logo)
    mu.cube_project_uv(logo, 8.0)
    # neutral pose: resting beside Morfi's right foot (hidden in turnaround views)
    cfg_l = cfg.get('laptop_place', {})
    ob.location = cfg_l.get('loc', (-0.42, 0.02, 0.0))
    ob.rotation_euler = [math.radians(a) for a in cfg_l.get('rot', (0, 0, 0))]
    grip = mu.empty('Laptop_Grip', collection=col, parent=ob, location=(0, 0, p['t_base']))
    return {'Laptop': ob, 'Laptop_Grip': grip}
