"""T-shirt and open zip hoodie as real thick garments (SDF shells).

All garments are separate meshes with fabric thickness and clearance from the
body, so each one can be hidden without exposing holes:

Tshirt               heather jersey shell + crew-neck rib + puff-print "M"
Hoodie               fleece shell: body, sleeves, hood, pockets (open front)
Hoodie_Cuff_L/R      ribbed cuffs (own local frame: Z = arm axis)
Hoodie_Hem           ribbed waistband (open at the front)
Hoodie_Zipper        two rows of metal teeth, stops, slider and pull
Hoodie_Drawstrings   cords + metal aglets + eyelets
"""
import math
import numpy as np
import bpy
from mathutils import Matrix, Vector

from . import meshutil as mu
from . import materials as mats
from . import sdf as S
from .body import BodySDF
from .accessories import rounded_cube_mesh

DEFAULT = {
    "shirt_offset": 0.010, "shirt_thick": 0.005, "shirt_hem_z": 0.236,
    "shirt_collar": {"c": [0.0, 0.016, 0.494], "R": 0.100, "r": 0.0085, "tilt": 9.0},
    "shirt_sleeve_frac": 0.5,
    "hood_offset": 0.046, "hood_thick": 0.011,
    "box": {"c": [0.0, -0.010, 0.343], "half": [0.222, 0.176, 0.157], "p_h": 2.7, "q_top": 2.7, "q_bot": 6.0},
    "hem": {"z0": 0.190, "z1": 0.238, "inset": 0.004, "thick": 0.013},
    "open_x_top": 0.072, "open_x_bot": 0.081,
    "sleeve_start": [0.168, 0.004, 0.432], "sleeve_r": [0.066, 0.066, 0.062], "sleeve_bunch": 0.006,
    "cuff_len": 0.046, "cuff_r": [0.058, 0.055], "cuff_inner": 0.043,
    "hood": {"c": [0.0, 0.168, 0.432], "r": [0.200, 0.068, 0.100], "tip_z": 0.348, "slope": 0.60, "rx": 12.0},
    "collar": {"c": [0.0, 0.040, 0.472], "R": [0.130, 0.120], "r": 0.036, "tilt": 12.0},
    "pocket": {"cx": 0.143, "cz": 0.290, "hw": 0.048, "hh": 0.049, "raise": 0.0022, "r_in": 0.035},
    "zip_z": [0.186, 0.466], "zip_pitch": 0.0058, "zip_tooth": [0.0052, 0.0042, 0.0025],
    "slider_z": 0.200,
    "cord": {"x": 0.100, "z_top": 0.468, "z_knot": 0.436, "z_tip": 0.398, "r": 0.0042, "aglet_r": 0.0068},
    "logo": {"cz": 0.407, "w": 0.060, "h": 0.039, "stroke": 0.0062, "v_depth": 0.6},
}


class Garments:
    def __init__(self, cfg):
        self.body = BodySDF(cfg)
        p = dict(DEFAULT)
        p.update(cfg.get('clothes', {}))
        self.p = p
        b = self.body.b
        self.b = b

    # ------------------------------------------------------------ geometry helpers
    def arm(self, side):
        b = self.b
        s = np.array([side, 1, 1])
        return (np.array(b['shoulder']) * s, np.array(b['elbow']) * s, np.array(b['wrist']) * s)

    def cuff_axis(self, side):
        sh, el, wr = self.arm(side)
        n = wr - el
        n /= np.linalg.norm(n)
        end = wr + n * 0.004
        start = end - n * self.p['cuff_len']
        return start, end, n

    def hem_z(self, key, y):
        """Waistband edge height: slightly higher at the back than at the front."""
        h = self.p['hem']
        t = np.clip((y - h.get('cy', 0.0)) / h.get('b', 0.16), -1, 1)
        return h[key] + h.get('tilt', 0.0) * t

    def open_x(self, z):
        p = self.p
        t = np.clip((0.47 - z) / 0.27, 0, 1)
        return p['open_x_top'] + (p['open_x_bot'] - p['open_x_top']) * t

    # ------------------------------------------------------------ t-shirt
    def shirt_outer(self, P):
        p = self.p
        b = self.b
        d = self.body.torso(P) - p['shirt_offset']
        for side in (-1, 1):
            sh, el, wr = self.arm(side)
            n = el - sh
            L = np.linalg.norm(n)
            n /= L
            end = sh + n * L * p['shirt_sleeve_frac']
            sl = S.sd_round_cone(P, sh - n * 0.01, end, b['arm_r'][0] + p['shirt_offset'] + 0.003, b['arm_r'][0] + p['shirt_offset'])
            sl = np.maximum(sl, (P[0] - end[0]) * n[0] + (P[1] - end[1]) * n[1] + (P[2] - end[2]) * n[2])
            d = S.smin(d, sl, 0.025)
        return d

    def shirt(self, P):
        p = self.p
        outer = self.shirt_outer(P)
        inner = outer + p['shirt_thick']
        d = np.maximum(outer, -inner)
        # hem
        d = np.maximum(d, p['shirt_hem_z'] - P[2])
        # neckline: tilted plane (front lower) + neck hole
        col = p['shirt_collar']
        tilt = math.tan(math.radians(col['tilt']))
        zc = col['c'][2] + (P[1] - col['c'][1]) * tilt
        d = np.maximum(d, P[2] - zc)
        return d

    def shirt_collar(self, P):
        col = self.p['shirt_collar']
        R = S.rot_matrix(col['tilt'], 0, 0)  # +X rotation: front edge lower, like the neckline
        return S.sd_torus(P, col['c'], col['R'], col['r'], Rm=R)

    def logo2d(self, u, v):
        """Rounded heavy 'M' in 2D (u right, v up); returns distance."""
        L = self.p['logo']
        w, h, r = L['w'] / 2 - L['stroke'], L['h'] / 2 - L['stroke'], L['stroke']
        pts = [(-w, -h), (-w, h), (0.0, h - (2 * h) * L['v_depth']), (w, h), (w, -h)]
        d = None
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            ax, ay = x1 - x0, y1 - y0
            t = np.clip(((u - x0) * ax + (v - y0) * ay) / (ax * ax + ay * ay), 0, 1)
            dd = np.sqrt((u - x0 - t * ax) ** 2 + (v - y0 - t * ay) ** 2)
            d = dd if d is None else np.minimum(d, dd)
        return d - r

    def logo(self, P):
        L = self.p['logo']
        so = self.shirt_outer(P)
        shell = np.maximum(-so - 0.0004, so - 0.0013)  # thin layer on the shirt surface
        d2 = self.logo2d(P[0], P[2] - L['cz'])
        return np.maximum(np.maximum(shell, d2), P[1] + 0.02)

    # ------------------------------------------------------------ hoodie
    def box(self, P):
        k = self.p['box']
        return S.sd_superquadric(P, k['c'], k['half'], k['p_h'], k['q_top'], k['q_bot'])

    def sleeve(self, P, side):
        p = self.p
        sh, el, wr = self.arm(side)
        cs, ce, n = self.cuff_axis(side)
        r = p['sleeve_r']
        st = np.array(p['sleeve_start']) * np.array([side, 1, 1])
        mid = (st + cs) / 2 + np.array([side * 0.004, 0, -0.004])
        d = S.sd_round_cone(P, st, mid, r[0], r[1])
        d = S.smin(d, S.sd_round_cone(P, mid, cs, r[1], r[2]), 0.02)
        # bunched folds above the cuff
        bu = p['sleeve_bunch']
        for k, t in enumerate((0.012, 0.034, 0.058)):
            c = cs - n * t
            d = S.smin(d, S.sd_sphere(P, c, r[2] + bu * (1.0 if k % 2 == 0 else 0.6)), 0.012)
        # soft horizontal fold rings along the forearm part of the sleeve
        fa = p.get('sleeve_folds', 0.0)
        if fa:
            ax = cs - el
            L = np.linalg.norm(ax)
            ax = ax / L
            t = ((P[0] - el[0]) * ax[0] + (P[1] - el[1]) * ax[1] + (P[2] - el[2]) * ax[2]) / L
            ring = np.where((t > 0.35) & (t < 0.98), np.cos(t * 2 * math.pi * 2.2 + 0.4), 0.0)
            d = d - fa * ring * S.smoothstep(0.35, 0.55, t)
        # flat end where the cuff starts
        d = np.maximum(d, (P[0] - cs[0]) * n[0] + (P[1] - cs[1]) * n[1] + (P[2] - cs[2]) * n[2] - 0.004)
        return d

    def hood_body(self, P):
        h = self.p['hood']
        d = S.sd_ellipsoid(P, h['c'], h['r'], R=S.rot_matrix(h.get('rx', 12.0), 0, 0))
        dv = (h['tip_z'] + h['slope'] * np.abs(P[0]) - P[2]) / math.sqrt(1 + h['slope'] ** 2)
        d = S.smax(d, dv, h.get('v_soft', 0.03))
        c = self.p['collar']
        Rm = S.rot_matrix(c['tilt'] * c.get('tilt_sign', -1.0), 0, 0)
        x, y, z = S.to_local(P, c['c'], Rm)
        q = np.sqrt((x / c['R'][0]) ** 2 + (y / c['R'][1]) ** 2) * min(c['R']) - min(c['R'])
        ring = np.sqrt(q * q + z * z) - c['r']
        d = S.smin(d, ring, 0.035)
        return d

    def hoodie_outer(self, P):
        p = self.p
        d = self.body.torso(P) - 0.030
        d = S.smin(d, self.box(P), 0.03)
        # fabric bloused over the gathered waistband
        z1 = self.hem_z('z1', P[1])
        roll = np.exp(-((P[2] - (z1 + 0.018)) / 0.016) ** 2)
        d = d - p.get('blouse', 0.0) * roll
        for side in (-1, 1):
            d = S.smin(d, self.sleeve(P, side), p.get('sleeve_blend', 0.035))
        return d

    def hoodie(self, P):
        p = self.p
        outer = self.hoodie_outer(P)
        d = np.maximum(outer, -(outer + p['hood_thick']))
        # hood (solid lump, kept off the neck)
        hb = self.hood_body(P)
        hb = np.maximum(hb, -(self.body.torso(P) - 0.012))
        # cut the neck opening & everything that would reach into the head
        neck_hole = np.sqrt(P[0] ** 2 + ((P[1] - 0.015) / 0.95) ** 2) - 0.104
        cut_neck = np.maximum(neck_hole, 0.42 - P[2])
        d = np.maximum(d, -cut_neck)
        d = S.smin(d, hb, 0.012)
        d = np.maximum(d, P[2] - 0.512)
        # front opening (both front panels end at the zipper edges)
        xo = self.open_x(P[2])
        cut_open = np.maximum(np.abs(P[0]) - xo, P[1] + 0.03)
        d = np.maximum(d, -cut_open)
        # hem: the ribbed waistband object covers below hem z1
        d = np.maximum(d, self.hem_z('z1', P[1]) - 0.006 - P[2])
        # pockets: slightly raised patches on the lower front panels
        pk = p['pocket']
        for side in (-1, 1):
            u = P[0] - side * pk['cx']
            v = P[2] - pk['cz']
            # opening edge slanted toward the zipper
            p2 = S.rrect2d(u, v, pk['hw'], pk['hh'], 0.012)
            # big rounded opening corner at the top, toward the zipper
            cxi = -side * (pk['hw'] - pk['r_in'])
            czi = pk['hh'] - pk['r_in']
            inner_corner = (u * side < -(pk['hw'] - pk['r_in'])) & (v > czi)
            rc = np.sqrt((u - cxi) ** 2 + (v - czi) ** 2) - pk['r_in']
            p2 = np.where(inner_corner, np.maximum(p2, rc), p2)
            patch = np.maximum(outer - pk['raise'], p2)
            patch = np.maximum(patch, P[1] + 0.06)
            patch = np.maximum(patch, -(outer + 0.004))
            d = np.minimum(d, patch)
        # centre-back seam groove (hood + back)
        groove = np.maximum(np.abs(P[0]) - 0.0016, -(np.minimum(outer, hb)) - 0.003)
        groove = np.maximum(groove, -P[1])
        d = np.maximum(d, -groove)
        return d

    # ------------------------------------------------------------ bands
    def hem_band(self, P):
        """Vertical ribbed waistband, gathered slightly toward the bottom."""
        h = self.p['hem']
        x, y, z = P
        z0 = self.hem_z('z0', y)
        z1 = self.hem_z('z1', y)
        t = np.clip((z1 - z) / (z1 - z0), 0, 1)
        a = h['a'] - h['inset'] * t
        b = h['b'] - h['inset'] * t
        rho = (np.abs(x / a) ** h['p'] + np.abs((y - h['cy']) / b) ** h['p']) ** (1 / h['p'])
        outer = (rho - 1.0) * np.minimum(a, b) - 0.003 * np.sin(t * math.pi)
        d = np.maximum(outer, -(outer + h['thick']))
        d = S.smax(d, z0 - z, 0.005)
        d = S.smax(d, z - z1, 0.003)
        xo = self.open_x(z)
        d = np.maximum(d, -np.maximum(np.abs(x) - xo, y + 0.03))
        return d

    def cuff_local(self, P):
        """Cuff in its local frame: axis = +Z from z=0 (sleeve side) to L."""
        p = self.p
        L = p['cuff_len']
        x, y, z = P
        rr = np.sqrt(x * x + y * y)
        R = p['cuff_r'][0] + (p['cuff_r'][1] - p['cuff_r'][0]) * np.clip(z / L, 0, 1)
        R = R + 0.003 * np.sin(np.clip(z / L, 0, 1) * math.pi)
        outer = rr - R
        inner = rr - p['cuff_inner']
        d = np.maximum(outer, -inner)
        d = S.smax(d, -z, 0.003)
        d = S.smax(d, z - L, 0.006)
        return d


# ---------------------------------------------------------------- materials
def fabric_materials(cfg):
    col = cfg['colors']
    hood = mats.flat('M_Hoodie', col['hoodie'], rough=0.95, sheen=0.18, spec=0.15,
                     bump=dict(scale=150.0, strength=0.45, distance=0.0018, fine=700.0),
                     tile_normal=('hoodie_n', 0.9) if 'hoodie_n' in mats.TILES else ('fleece_n', 0.9),
                     tile_color='hoodie_c' if 'hoodie_c' in mats.TILES else None)
    rib = mats.flat('M_HoodieRib', col['hoodie'], rough=0.93, sheen=0.3, spec=0.18, tile_normal=('rib_n', 1.0))
    hem = mats.flat('M_HoodieHem', col['hoodie'], rough=0.93, sheen=0.3, spec=0.18, tile_normal=('rib_n', 1.0))
    if not mats.TILES:
        _rib_bump(rib, radial=False)
        _rib_bump(hem, radial=True)
    shirt = mats.flat('M_Tshirt', col['tshirt'], rough=0.92, sheen=0.35, spec=0.3,
                      bump=dict(scale=320.0, strength=0.12, distance=0.0008, fine=1100.0),
                      tile_normal=('jersey_n', 0.6), tile_color='jersey_c')
    if not mats.TILES:
        _heather(shirt, col['tshirt'])
    logo = mats.flat('M_TshirtLogo', col['tshirt_logo'], rough=0.42, spec=0.5, coat=0.2, coat_rough=0.3)
    metal = mats.flat('M_Metal', col['metal'], rough=0.22, metal=1.0, spec=0.5)
    cord = mats.flat('M_Cord', col['cord'], rough=0.75, sheen=0.4, spec=0.3,
                     bump=dict(scale=900.0, strength=0.2, distance=0.0005, fine=2000.0),
                     tile_normal=('fleece_n', 0.6))
    return dict(hoodie=hood, rib=rib, hem=hem, shirt=shirt, logo=logo, metal=metal, cord=cord)


def cylindrical_uv(ob, center, axis, u_repeat, v_scale):
    """UVs around an axis: u = angle (repeats u_repeat times), v = height * v_scale."""
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name='UVMap')
    uvl = me.uv_layers.active
    nl = len(me.loops)
    vidx = np.empty(nl, np.int32)
    me.loops.foreach_get('vertex_index', vidx)
    co = mu.get_verts(ob)
    M = np.array(ob.matrix_world)
    co = co @ M[:3, :3].T + M[:3, 3]
    a = np.asarray(axis, float)
    a /= np.linalg.norm(a)
    ref = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = ref - a * (ref @ a)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    d = co - np.asarray(center)
    ang = np.arctan2(d @ e2, d @ e1)
    h = d @ a
    uv = np.stack([(ang / (2 * math.pi) + 0.5) * u_repeat, h * v_scale], 1)[vidx]
    # fix the seam: per-face unwrap of the angle discontinuity
    npoly = len(me.polygons)
    ls = np.empty(npoly, np.int32)
    me.polygons.foreach_get('loop_start', ls)
    lt = np.empty(npoly, np.int32)
    me.polygons.foreach_get('loop_total', lt)
    for start, tot in zip(ls, lt):
        us = uv[start:start + tot, 0]
        if us.max() - us.min() > u_repeat * 0.5:
            us[us < u_repeat * 0.5] += u_repeat
            uv[start:start + tot, 0] = us
    uvl.data.foreach_set('uv', uv.astype(np.float32).ravel())


def _rib_bump(m, radial):
    """Knit ribbing: radial=True -> ribs around the body Z axis (waistband);
    False -> ribs around the object's local Z axis (cuffs)."""
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs['Vector'])
    at = nt.nodes.new('ShaderNodeMath')
    at.operation = 'ARCTAN2'
    nt.links.new(sep.outputs['Y'], at.inputs[0])
    nt.links.new(sep.outputs['X'], at.inputs[1])
    mul = nt.nodes.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    mul.inputs[1].default_value = 150.0 if radial else 46.0
    nt.links.new(at.outputs['Value'], mul.inputs[0])
    sn = nt.nodes.new('ShaderNodeMath')
    sn.operation = 'SINE'
    nt.links.new(mul.outputs['Value'], sn.inputs[0])
    ab = nt.nodes.new('ShaderNodeMath')
    ab.operation = 'ABSOLUTE'
    nt.links.new(sn.outputs['Value'], ab.inputs[0])
    noi = nt.nodes.new('ShaderNodeTexNoise')
    noi.inputs['Scale'].default_value = 700.0
    nt.links.new(tc.outputs['Object'], noi.inputs['Vector'])
    add = nt.nodes.new('ShaderNodeMath')
    add.operation = 'MULTIPLY_ADD'
    nt.links.new(noi.outputs['Fac'], add.inputs[0])
    add.inputs[1].default_value = 0.25
    nt.links.new(ab.outputs['Value'], add.inputs[2])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.55
    bump.inputs['Distance'].default_value = 0.0015
    nt.links.new(add.outputs['Value'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])


def _heather(m, base_hex):
    """Mottled heather-gray jersey: two-tone noise on base colour."""
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    noi = nt.nodes.new('ShaderNodeTexNoise')
    noi.inputs['Scale'].default_value = 260.0
    noi.inputs['Detail'].default_value = 6.0
    nt.links.new(tc.outputs['Object'], noi.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    c0 = mu.hex_to_linear(base_hex)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = tuple(v * 0.86 for v in c0[:3]) + (1,)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = tuple(min(1, v * 1.06) for v in c0[:3]) + (1,)
    nt.links.new(noi.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])


# ---------------------------------------------------------------- builder
def _place_local(ob, origin, zaxis):
    z = Vector(zaxis).normalized()
    q = z.to_track_quat('Z', 'Y')
    ob.matrix_world = Matrix.Translation(Vector(origin)) @ q.to_matrix().to_4x4()


def _tube_mesh(points, radius, n_ring=12, cap=True):
    pts = np.asarray(points, float)
    verts, faces = [], []
    m = len(pts)
    for i in range(m):
        T = pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]
        T /= np.linalg.norm(T)
        A = np.cross(T, [0, 0, 1.0]) if abs(T[2]) < 0.9 else np.cross(T, [1.0, 0, 0])
        A /= np.linalg.norm(A)
        B = np.cross(T, A)
        r = radius[i] if hasattr(radius, '__len__') else radius
        for k in range(n_ring):
            a = 2 * math.pi * k / n_ring
            verts.append(pts[i] + (A * math.cos(a) + B * math.sin(a)) * r)
    for i in range(m - 1):
        for k in range(n_ring):
            k1 = (k + 1) % n_ring
            faces.append((i * n_ring + k, i * n_ring + k1, (i + 1) * n_ring + k1, (i + 1) * n_ring + k))
    if cap:
        c0 = len(verts)
        verts.append(pts[0])
        verts.append(pts[-1])
        for k in range(n_ring):
            k1 = (k + 1) % n_ring
            faces.append((c0, k1, k))
            faces.append((c0 + 1, (m - 1) * n_ring + k, (m - 1) * n_ring + k1))
    return np.array(verts), faces


def build(cfg, col, parent, tex_dir, h, quality):
    g = Garments(cfg)
    p = g.p
    M = fabric_materials(cfg)
    out = {}
    hh = h * (0.85 if quality == 'final' else 1.0)

    # --- T-shirt
    ts = mu.fast_mesh_object('Tshirt', *S.polygonize(g.shirt, (-0.30, -0.20, 0.20), (0.30, 0.18, 0.53), hh),
                             collection=col, parent=parent)
    mu.assign_material(ts, M['shirt'])
    mu.cube_project_uv(ts, 5.0)
    collar = mu.fast_mesh_object('Tshirt_Collar', *S.polygonize(g.shirt_collar, (-0.13, -0.13, 0.44), (0.13, 0.15, 0.55), hh * 0.6),
                                 collection=col, parent=ts)
    mu.assign_material(collar, M['shirt'])
    logo = mu.fast_mesh_object('Tshirt_Logo', *S.polygonize(g.logo, (-0.05, -0.20, p['logo']['cz'] - 0.035), (0.05, -0.08, p['logo']['cz'] + 0.035), 0.0007),
                               collection=col, parent=ts)
    mu.assign_material(logo, M['logo'])
    out.update(Tshirt=ts, Tshirt_Collar=collar, Tshirt_Logo=logo)

    # --- Hoodie shell (+hood, pockets)
    hv, hf = S.polygonize(g.hoodie, (-0.40, -0.25, 0.17), (0.40, 0.26, 0.53), hh)
    hd = mu.fast_mesh_object('Hoodie', hv, hf, collection=col, parent=parent)
    mu.assign_material(hd, M['hoodie'])
    mu.cube_project_uv(hd, 3.5)
    out['Hoodie'] = hd

    # --- hem band
    hb = mu.fast_mesh_object('Hoodie_Hem', *S.polygonize(g.hem_band, (-0.26, -0.22, 0.165), (0.26, 0.21, 0.26), hh * 0.8),
                             collection=col, parent=hd)
    mu.assign_material(hb, M['hem'])
    cylindrical_uv(hb, (0, p['hem'].get('cy', -0.016), 0), (0, 0, 1), 7.0, 18.0)
    out['Hoodie_Hem'] = hb

    # --- cuffs (local frame)
    for name, side in (('Hoodie_Cuff_R', -1), ('Hoodie_Cuff_L', 1)):
        cs, ce, n = g.cuff_axis(side)
        L = p['cuff_len']
        cv, cf = S.polygonize(g.cuff_local, (-0.07, -0.07, -0.01), (0.07, 0.07, L + 0.01), hh * 0.7)
        cu = mu.fast_mesh_object(name, cv, cf, collection=col)
        _place_local(cu, cs, n)
        cu.parent = hd
        cu.matrix_parent_inverse = hd.matrix_world.inverted()
        mu.assign_material(cu, M['rib'])
        bpy.context.view_layer.update()
        cylindrical_uv(cu, cs, n, 2.0, 18.0)
        out[name] = cu

    # --- zipper
    zv, zf = [], []
    off = 0
    tooth_v, tooth_f = rounded_cube_mesh(tuple(p.get('zip_tooth', (0.0052, 0.0042, 0.0025))), e=2.6, N=4)
    zs = np.arange(p['zip_z'][0], p['zip_z'][1], p['zip_pitch'])
    for side in (-1, 1):
        xs = side * (g.open_x(zs) + 0.0008)
        origins = np.stack([xs, np.full_like(zs, -0.40), zs], 1)
        both = lambda P: np.minimum(g.hoodie(P), g.hem_band(P))
        hits, ok = S.raycast(both, origins, np.tile([0, 1.0, 0], (len(zs), 1)), tmax=0.5)
        for i, (hp, k) in enumerate(zip(hits, ok)):
            if not k or hp[1] > -0.06:
                continue
            stagger = 0.5 * p['zip_pitch'] if side > 0 else 0.0
            c = np.array([side * (g.open_x(hp[2]) - 0.0030), hp[1] + 0.0042, hp[2] + stagger])
            zv.append(tooth_v + c)
            zf.append(tooth_f + off)
            off += len(tooth_v)
    # slider + pull on Morfi's left panel (+X)
    zb = p['slider_z']
    xo = g.open_x(zb)
    hit, _ = S.raycast(both, np.array([[xo + 0.004, -0.4, zb]]), np.array([[0, 1.0, 0]]), tmax=0.5)
    yb = hit[0, 1]
    for half, c in (((0.0068, 0.0055, 0.0115), (xo - 0.002, yb - 0.001, zb)),
                    ((0.0048, 0.0018, 0.0125), (xo - 0.002, yb - 0.006, zb - 0.017))):
        v, f = rounded_cube_mesh(half, e=3.2, N=5)
        zv.append(v + np.array(c))
        zf.append(f + off)
        off += len(v)
    zip_ob = mu.mesh_object('Hoodie_Zipper', np.vstack(zv), np.vstack(zf), collection=col, parent=hd)
    mu.assign_material(zip_ob, M['metal'])
    out['Hoodie_Zipper'] = zip_ob

    # --- drawstrings
    cd = p['cord']
    cv_all, cf_all, mats_idx = [], [], []
    off = 0
    for side in (-1, 1):
        x = side * cd['x']
        zz = np.linspace(cd['z_top'], cd['z_tip'], 14)
        origins = np.stack([np.full_like(zz, x), np.full_like(zz, -0.40), zz], 1)
        hits, ok = S.raycast(g.hoodie, origins, np.tile([0, 1.0, 0], (len(zz), 1)), tmax=0.5)
        ys = hits[:, 1] - 0.0075
        ys[~ok] = ys[ok].min() if ok.any() else -0.18
        pts = np.stack([np.full_like(zz, x) + side * 0.004 * (zz - cd['z_top']) / (cd['z_tip'] - cd['z_top']), ys, zz], 1)
        # cord part (top -> knot)
        kmask = zz >= cd['z_knot']
        cordp = pts[kmask]
        v, f = _tube_mesh(cordp, cd['r'], 10)
        cv_all.append(v)
        cf_all += [tuple(i + off for i in fc) for fc in f]
        mats_idx += [0] * len(f)
        off += len(v)
        # aglet: metal capsule-like tube from knot to tip
        ag = pts[~kmask]
        ag = np.vstack([cordp[-1:], ag])
        rr = np.full(len(ag), cd['aglet_r'])
        rr[0] = cd['aglet_r'] * 0.8
        rr[-1] = cd['aglet_r'] * 0.75
        v, f = _tube_mesh(ag, rr, 14)
        cv_all.append(v)
        cf_all += [tuple(i + off for i in fc) for fc in f]
        mats_idx += [1] * len(f)
        off += len(v)
        # eyelet ring around the cord exit
        ring_c = pts[0] + np.array([0, -0.001, 0])
        th = np.linspace(0, 2 * math.pi, 25)
        ring = np.stack([ring_c[0] + 0.0075 * np.cos(th), np.full_like(th, ring_c[1]) + 0.002, ring_c[2] + 0.0075 * np.sin(th)], 1)
        v, f = _tube_mesh(ring, 0.0019, 8, cap=False)
        cv_all.append(v)
        cf_all += [tuple(i + off for i in fc) for fc in f]
        mats_idx += [1] * len(f)
        off += len(v)
    ds = mu.mesh_object('Hoodie_Drawstrings', np.vstack(cv_all), cf_all, collection=col, parent=hd)
    ds.data.materials.append(M['cord'])
    ds.data.materials.append(M['metal'])
    mu.set_face_materials(ds, mats_idx)
    out['Hoodie_Drawstrings'] = ds
    return out
