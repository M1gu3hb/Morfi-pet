"""Glasses, identity cubes ("pixels") and laptop."""
import math
import numpy as np
import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import meshutil as mu
from . import materials as mats
from . import sdf as S


# ---------------------------------------------------------------- glasses
def _glasses_params(cfg):
    g = cfg.get('glasses', {})
    d = dict(
        lens_cx=0.157, lens_cz=-0.031,
        outer_half=(0.125, 0.116), outer_r=0.070,
        rim=0.021, depth_half=0.0105, edge_r=0.0055,
        bridge_cz=0.012, bridge_half=(0.05, 0.0135, 0.0085),
        end_x=(0.268, 0.338), end_cz=0.010, end_half_z=0.033,
        temple_front=(0.329, 0.022), temple_back=(0.333, 0.125, -0.024),
        temple_w=0.026, temple_t=0.0115, wrap=0.012, clearance=0.004,
        top_flatten=0.006,
    )
    d.update(g)
    return d


def _bend(x, wrap, xr=0.28):
    return wrap * (np.abs(x) / xr) ** 2


def glasses_front_sdf(P, gp, yg):
    x, y, z = P
    yb = y - yg - _bend(x, gp['wrap'])
    d = None
    for side in (-1, 1):
        u = x - side * gp['lens_cx']
        v = z - gp['lens_cz']
        hw, hh = gp['outer_half']
        # slightly wider at the top (classic acetate square frames)
        hw_eff = hw + 0.004 * np.clip(v / hh, -1, 1)
        outer = S.rrect2d(u, v, hw_eff, hh, gp['outer_r'])
        inner = S.rrect2d(u, v, hw_eff - gp['rim'], hh - gp['rim'] * 0.95, gp['outer_r'] - gp['rim'] * 0.55)
        ring2 = np.maximum(outer, -inner)
        r3 = S.extrude(ring2, yb, gp['depth_half'], gp['edge_r'])
        d = r3 if d is None else np.minimum(d, r3)
    # bridge
    bh = gp['bridge_half']
    bridge = S.sd_round_box((x, yb, z), (0, 0, gp['bridge_cz']), (bh[0], bh[2], bh[1]), 0.006)
    d = S.smin(d, bridge, 0.006)
    # end pieces (hinge blocks)
    for side in (-1, 1):
        x0, x1 = gp['end_x']
        cx = side * (x0 + x1) / 2
        blk = S.sd_round_box((x, yb, z), (cx, 0.004, gp['end_cz']),
                             ((x1 - x0) / 2, gp['depth_half'] + 0.003, gp['end_half_z']), 0.0055)
        d = S.smin(d, blk, 0.008)
    return d


def temple_sdf(P, gp, yg, side):
    x, y, z = P
    fx, fz = gp['temple_front']
    bx, by, bz = gp['temple_back']
    a = np.array([side * fx, yg + 0.012 + _bend(np.array([fx]), gp['wrap'])[0], fz])
    b = np.array([side * bx, by, bz])
    # oriented rounded box along a->b
    ax = b - a
    L = np.linalg.norm(ax)
    ax /= L
    up = np.array([0, 0, 1.0])
    up = up - ax * (up @ ax)
    up /= np.linalg.norm(up)
    side_v = np.cross(ax, up)
    c = (a + b) / 2
    R = np.stack([side_v, ax, up], 1)  # local x=thickness, y=length, z=width
    return S.sd_round_box(P, c, (gp['temple_t'] / 2, L / 2, gp['temple_w'] / 2), 0.0055, R=R)


def build_glasses(cfg, shape, head, col, h=0.0013):
    gp = _glasses_params(cfg)
    # find frame plane: clear the face surface behind the rim footprint
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(head, dg)  # head-local space (object transform excluded)
    ys = []
    for side in (-1, 1):
        for ang in np.linspace(0, 2 * math.pi, 48, endpoint=False):
            for k in (0.82, 1.0):
                u = math.cos(ang) * gp['outer_half'][0] * k
                v = math.sin(ang) * gp['outer_half'][1] * k
                x = side * gp['lens_cx'] + u
                z = gp['lens_cz'] + v
                hit = bvh.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)))
                if hit[0] is not None:
                    ys.append(hit[0].y - _bend(np.array([x]), gp['wrap'])[0])
    y_back = min(ys) - gp['clearance']
    yg = y_back - gp['depth_half']
    # the lens plates must stay in front of the bulging eyeballs
    eye_front = min(shape.eye_centers[:, 1]) - shape.eye_R
    yg = min(yg, eye_front - 0.0045)
    gp['yg'] = yg
    frame_m = mats.flat('M_GlassesFrame', cfg['colors']['frame'], rough=0.42, coat=0.06, coat_rough=0.3, spec=0.35)
    lens_m = mats.glass('M_GlassesLens')
    # front frame
    bmin = (-0.36, yg - 0.03, -0.17)
    bmax = (0.36, yg + 0.05, 0.11)
    v, f = S.polygonize(lambda P: glasses_front_sdf(P, gp, yg), bmin, bmax, h)
    parts_v, parts_f = [v], [f]
    off = len(v)
    for side in (-1, 1):
        fx, fz = gp['temple_front']
        bx, by, bz = gp['temple_back']
        bmn = (min(side * fx, side * bx) - 0.02, yg - 0.01, min(fz, bz) - 0.03)
        bmx = (max(side * fx, side * bx) + 0.02, by + 0.02, max(fz, bz) + 0.03)
        tv, tf = S.polygonize(lambda P, s=side: temple_sdf(P, gp, yg, s), bmn, bmx, h)
        parts_v.append(tv)
        parts_f.append(tf + off)
        off += len(tv)
    ob = mu.fast_mesh_object('Glasses_Frame', np.vstack(parts_v), np.vstack(parts_f), collection=col, parent=head)
    mu.assign_material(ob, frame_m)
    # lenses: clean parametric plates (flat parallel faces -> no refraction blur)
    lenses = []
    for name, side in (('Glasses_Lens_R', -1), ('Glasses_Lens_L', 1)):
        lv, lf = lens_plate(gp, side, yg)
        lo = mu.mesh_object(name, lv, lf, collection=col, parent=head, smooth=False)
        mu.assign_material(lo, lens_m)
        lo.visible_shadow = False
        lenses.append(lo)
    return ob, lenses, gp


def lens_outline(gp, side, n=160, grow=0.004):
    """2D outline points (x, z) of a lens (rounded rect, slightly wider on top)."""
    hw, hh = gp['outer_half']
    r = gp['outer_r'] - gp['rim'] * 0.55
    ihw = hw - gp['rim'] + grow
    ihh = hh - gp['rim'] * 0.95 + grow
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        # superellipse-like rounded rectangle via corner arcs
        cx, cz = math.cos(t), math.sin(t)
        # find boundary along direction by bisection on the rrect sdf
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            u, v = cx * mid, cz * mid
            hw_eff = ihw + 0.004 * max(-1.0, min(1.0, v / hh))
            d = S.rrect2d(np.array([u]), np.array([v]), hw_eff, ihh, r)[0]
            if d < 0:
                lo = mid
            else:
                hi = mid
        pts.append((side * gp['lens_cx'] + cx * lo, gp['lens_cz'] + cz * lo))
    return np.array(pts)


def lens_plate(gp, side, yg, thick=0.0024):
    o = lens_outline(gp, side)
    n = len(o)
    c = o.mean(0)
    verts = []
    for yoff in (-thick / 2, thick / 2):
        for (x, z) in o:
            verts.append((x, yg + yoff + _bend(np.array([x]), gp['wrap'])[0], z))
        verts.append((c[0], yg + yoff + _bend(np.array([c[0]]), gp['wrap'])[0], c[1]))
    verts = np.array(verts)
    faces = []
    cf, cb = n, 2 * n + 1
    for k in range(n):
        k1 = (k + 1) % n
        faces.append((cf, k1, k))              # front (faces -Y)
        faces.append((cb, n + 1 + k, n + 1 + k1))  # back
        faces.append((k, k1, n + 1 + k1, n + 1 + k))  # rim
    return verts, faces


# ---------------------------------------------------------------- cubes
def rounded_cube_mesh(half, e=4.6, N=28, bulge=0.0):
    """Superellipsoid cube-sphere (quads) with optional face inflation."""
    from .head import FACES
    g = np.linspace(-1, 1, N + 1)
    A, B = np.meshgrid(g, g, indexing='ij')
    verts, quads = [], []
    base = 0
    for face, fn in FACES.items():
        u = np.tan(A.ravel() * math.pi / 4)
        v = np.tan(B.ravel() * math.pi / 4)
        cx, cy, cz = fn(u, v)
        d = np.stack([cx, cy, cz], 1)
        x, y, z = d[:, 0] / half[0], d[:, 1] / half[1], d[:, 2] / half[2]
        F = np.abs(x) ** e + np.abs(y) ** e + np.abs(z) ** e
        t = F ** (-1.0 / e)
        P = d * t[:, None]
        if bulge:
            n = P / np.array(half)
            P = P * (1 + bulge * (1 - np.max(np.abs(n), axis=1) ** 2)[:, None] * 0)
        verts.append(P)
        idx = np.arange((N + 1) ** 2).reshape(N + 1, N + 1) + base
        quads.append(np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], -1).reshape(-1, 4))
        base += (N + 1) ** 2
    return np.concatenate(verts), np.concatenate(quads)


def build_cubes(cfg, head_center, col, parent, skin_mat):
    cubes_cfg = cfg.get('pixels', [
        {"name": "Pixel_01", "center": [-0.083, -0.012, 1.049], "half": [0.0475, 0.044, 0.041], "rot": [0, -2.5, 0]},
        {"name": "Pixel_02", "center": [0.008, -0.010, 1.105], "half": [0.037, 0.035, 0.034], "rot": [0, 2.0, 0]},
        {"name": "Pixel_03", "center": [0.015, -0.012, 1.0335], "half": [0.0355, 0.034, 0.032], "rot": [0, 1.0, 0]},
    ])
    grp = mu.empty('Pixels', collection=col, parent=parent)
    grp.location = (0, 0, 0)
    out = []
    for c in cubes_cfg:
        v, q = rounded_cube_mesh(c['half'], e=c.get('e', 4.4), N=24)
        ob = mu.mesh_object(c['name'], v, q, collection=col, parent=grp)
        ob.location = np.array(c['center']) - np.array(head_center)
        ob.rotation_euler = [math.radians(a) for a in c['rot']]
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.shade_smooth()
        mu.assign_material(ob, skin_mat)
        mu.cube_project_uv(ob, scale=2.5)
        out.append(ob)
    return grp, out
