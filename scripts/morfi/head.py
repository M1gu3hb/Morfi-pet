"""Morfi head: parametric 'inflated box' surface, facial relief, baked face texture.

The head surface is a cube-sphere whose vertices are pushed radially onto a
superquadric with direction-dependent exponents (boxier at the bottom, rounder
on top / in profile, as measured on the references). Facial relief (muzzle,
nose, eye sockets, mouth cavity) is displacement evaluated from analytic 2D
feature fields in front projection. The same fields are evaluated per texel
(through the exact UV -> surface mapping) to bake the base-colour texture, so
the celeste face mask, mouth and lid lines align with the geometry with no
decals and no z-fighting.
"""
import math
import numpy as np

from .sdf import smoothstep, rrect2d

FACES = {
    #        cube point from (u, v)
    'front': lambda u, v: (u, -np.ones_like(u), v),
    'back': lambda u, v: (-u, np.ones_like(u), v),
    'right': lambda u, v: (np.ones_like(u), u, v),
    'left': lambda u, v: (-np.ones_like(u), -u, v),
    'top': lambda u, v: (u, v, np.ones_like(u)),
    'bottom': lambda u, v: (u, -v, -np.ones_like(u)),
}
# UV tiles in a square atlas: (u0, v0, size)
TILES = {
    'front': (0.0, 0.5, 0.5),
    'top': (0.5, 0.75, 0.25),
    'bottom': (0.75, 0.75, 0.25),
    'right': (0.5, 0.5, 0.25),
    'left': (0.75, 0.5, 0.25),
    'back': (0.0, 0.25, 0.25),
}
INSET = 0.012


def _hexrgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


class HeadShape:
    def __init__(self, cfg):
        h = cfg['head']
        f = cfg['face']
        self.cfg = cfg
        self.center = np.array(h['center'], float)
        self.a = h['half_width']
        self.bf = h['half_depth_front']
        self.bb = h['half_depth_back']
        self.c = h['half_height']
        self.p = h['plan_exponent']
        self.qtf = h['q_top_front_section']
        self.qbf = h['q_bottom_front_section']
        self.qtp = h['q_top_profile']
        self.qtpf = h.get('q_top_profile_front', h['q_top_profile'])
        self.qbpf = h['q_bottom_profile_front']
        self.qbpb = h['q_bottom_profile_back']
        self.N = h['grid']
        self.f = f
        ex, ez = f['eye_center_x'], f['eye_center_z']
        self.eye_R = f['eye_radius']
        # eyeball centres are placed after the base surface is known
        y_front = self.front_y(np.array([ex]), np.array([ez]))[0]
        socket = f.get('socket_depth', 0.012)
        eye_front = y_front + socket - f['eye_protrusion']
        self.eye_centers = np.array([[-ex, eye_front + self.eye_R, ez],
                                     [ex, eye_front + self.eye_R, ez]])

    # ------------------------------------------------------------ base shape
    def surface(self, d):
        """Directions (N,3) (any length) -> points on the base surface."""
        x = d[:, 0] / self.a
        y = d[:, 1] / np.where(d[:, 1] < 0, self.bf, self.bb)
        z = d[:, 2] / self.c
        ax, ay, az = np.abs(x), np.abs(y), np.abs(z)
        p = self.p
        h = (ax ** p + ay ** p) ** (1.0 / p)
        w = ay ** 2 / (ax ** 2 + ay ** 2 + 1e-12)
        qtp = np.where(d[:, 1] < 0, self.qtpf, self.qtp)
        q_top = (1 - w) * self.qtf + w * qtp
        q_bot = (1 - w) * self.qbf + w * np.where(d[:, 1] < 0, self.qbpf, self.qbpb)
        s = smoothstep(-0.25, 0.25, z / np.sqrt(h * h + z * z + 1e-12))
        q = q_bot + (q_top - q_bot) * s
        F = h ** q + az ** q
        t = F ** (-1.0 / q)
        return d * t[:, None]

    def front_y(self, x, z):
        """y of the base front surface at local (x, z) (bisection)."""
        lo = np.full_like(x, -0.6)
        hi = np.zeros_like(x)
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            d = np.stack([x, mid, z], 1)
            r_surf = np.linalg.norm(self.surface(d), axis=1)
            outside = np.linalg.norm(d, axis=1) > r_surf
            lo = np.where(outside, mid, lo)
            hi = np.where(outside, hi, mid)
        return 0.5 * (lo + hi)

    def param_points(self, face, a, b):
        u = np.tan(a * math.pi / 4)
        v = np.tan(b * math.pi / 4)
        cx, cy, cz = FACES[face](u, v)
        d = np.stack([cx, cy, cz], 1)
        return self.surface(d)

    def param_points_normals(self, face, a, b, eps=1e-3):
        P = self.param_points(face, a, b)
        Pa = self.param_points(face, a + eps, b) - self.param_points(face, a - eps, b)
        Pb = self.param_points(face, a, b + eps) - self.param_points(face, a, b - eps)
        n = np.cross(Pa, Pb)
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        return P, n

    # ------------------------------------------------------------ features
    def eye_sdf(self, x, z, side):
        """Signed distance-ish of the eye opening in front projection."""
        f = self.f
        cx = side * f['eye_center_x']
        hx, hz = f['eye_open_half']
        e = f['eye_open_exponent']
        tilt = math.radians(f.get('eye_tilt_deg', 4.0)) * side
        dx, dz = x - cx, z - f['eye_center_z']
        rx = dx * math.cos(tilt) + dz * math.sin(tilt)
        rz = -dx * math.sin(tilt) + dz * math.cos(tilt)
        # slightly flatter top edge
        hz_eff = np.where(rz > 0, hz * 0.97, hz)
        k = (np.abs(rx / hx) ** e + np.abs(rz / hz_eff) ** e) ** (1.0 / e)
        return (k - 1.0) * min(hx, hz)

    def patch_sdf(self, x, z):
        f = self.f
        px = np.abs(x) - f['eye_center_x'] - f.get('patch_offset_x', -0.002)
        pz = z - (f['eye_center_z'] + f.get('patch_offset_z', 0.010))
        hw, hh = f.get('patch_half', [0.113, 0.106])
        return rrect2d(px, pz, hw, hh, f.get('patch_radius', 0.062))

    def nose_sdf(self, x, z):
        f = self.f
        top, bot = 0.09, f.get('nose_tip_z', -0.104)
        r = f.get('nose_half_width', 0.042)
        zc = np.clip(z, bot + r, top)
        return np.sqrt(x ** 2 + (z - zc) ** 2) - r

    def mouth_fields(self, x, z):
        f = self.f
        w = f['mouth_half_width']
        z0 = f['mouth_center_z']
        t = np.clip(x / w, -1.2, 1.2)
        k = np.clip(1.0 - t * t, 0.0, 1.0)
        z_top = z0 - f['mouth_top_sag'] * k
        z_bot = z0 - f['mouth_bottom_sag'] * k ** 0.62
        # approximate signed distance (negative inside)
        d_top = z - z_top
        d_bot = z_bot - z
        d_side = np.abs(x) - w
        d = np.maximum(np.maximum(d_top, d_bot), d_side)
        # soften the corners
        return d, z_top, z_bot

    def frontness_threshold(self, z):
        # how far the celeste muzzle wraps around the face corners
        t = smoothstep(-0.07, -0.235, z)
        return 0.80 - 0.38 * t

    def relief(self, P, N):
        """Displacement (scalar along normal) for base points/normals."""
        f = self.f
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        nf = np.clip(-N[:, 1], 0, 1)
        front = smoothstep(0.15, 0.6, nf)
        # muzzle / cheeks
        mx = x / f.get('muzzle_rx', 0.26)
        mz = (z - f.get('muzzle_cz', -0.15)) / f.get('muzzle_rz', 0.12)
        tm = (np.abs(mx) ** 3 + np.abs(mz) ** 2) ** 0.5
        muzzle = f.get('muzzle_amp', 0.020) * smoothstep(1.0, 0.15, tm) * front
        # nose relief
        nose = f.get('nose_amp', 0.010) * smoothstep(0.006, -0.03, self.nose_sdf(x, z)) * front
        nose *= smoothstep(0.06, 0.0, z)  # only the lower part of the wedge is raised
        # eye socket recess
        sock = f.get('socket_depth', 0.012) * smoothstep(0.02, -0.03, self.patch_sdf(x, z)) * front
        # mouth cavity
        md, _, _ = self.mouth_fields(x, z)
        mouth = f['mouth_depth'] * smoothstep(0.0025, -0.009, md) * front
        return muzzle + nose - sock - mouth

    def eye_blend(self, P):
        """Weight that pulls the head surface onto the eyeball (sockets)."""
        x, z = P[:, 0], P[:, 2]
        front = P[:, 1] < -0.05
        wL = smoothstep(0.003, -0.011, self.eye_sdf(x, z, -1)) * front
        wR = smoothstep(0.003, -0.011, self.eye_sdf(x, z, 1)) * front
        return wL, wR

    def final_points(self, P, N):
        disp = self.relief(P, N)
        Q = P + N * disp[:, None]
        wL, wR = self.eye_blend(P)
        for w, E in ((wL, self.eye_centers[0]), (wR, self.eye_centers[1])):
            m = w > 0
            if not np.any(m):
                continue
            v = Q[m] - E
            r = np.linalg.norm(v, axis=1, keepdims=True)
            onball = E + v / r * (self.eye_R - 0.004)
            Q[m] = Q[m] * (1 - w[m, None]) + onball * w[m, None]
        return Q

    # ------------------------------------------------------------ mesh
    def build_mesh(self):
        """Returns verts (local), quads, per-loop uvs (welded at seams later)."""
        N = self.N
        verts, quads, uvs = [], [], []
        base = 0
        g = np.linspace(-1, 1, N + 1)
        A, B = np.meshgrid(g, g, indexing='ij')
        a, b = A.ravel(), B.ravel()
        for face in FACES:
            P, n = self.param_points_normals(face, a, b)
            Q = self.final_points(P, n)
            verts.append(Q)
            idx = np.arange((N + 1) * (N + 1)).reshape(N + 1, N + 1) + base
            q = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], -1).reshape(-1, 4)
            quads.append(q)
            u0, v0, s = TILES[face]
            ua = u0 + s * (INSET + (1 - 2 * INSET) * (A + 1) / 2)
            vb = v0 + s * (INSET + (1 - 2 * INSET) * (B + 1) / 2)
            uvg = np.stack([ua, vb], -1)
            cu = np.stack([uvg[:-1, :-1], uvg[1:, :-1], uvg[1:, 1:], uvg[:-1, 1:]], 2).reshape(-1, 2)
            uvs.append(cu)
            base += (N + 1) * (N + 1)
        return np.concatenate(verts), np.concatenate(quads), np.concatenate(uvs)

    # ------------------------------------------------------------ textures
    def bake_textures(self, size=4096):
        """Base colour (RGB) + roughness (gray) atlases; row 0 = top."""
        cfg = self.cfg
        col = cfg['colors']
        skin = _hexrgb(col['skin'])
        cele = _hexrgb(col['celeste'])
        lid = _hexrgb(col['lid_line'])
        mouth_c = _hexrgb(col['mouth_interior'])
        tongue_c = _hexrgb(col['tongue'])
        img = np.ones((size, size, 3)) * skin
        rough = np.ones((size, size)) * 0.78
        f = self.f
        for face, (u0, v0, s) in TILES.items():
            px0 = int(round(u0 * size))
            npx = int(round(s * size))
            py0 = int(round((1 - v0 - s) * size))  # image row of tile top
            jj, ii = np.meshgrid(np.arange(npx), np.arange(npx), indexing='ij')
            # ii: column within tile, jj: row within tile (top = 0)
            uu = (ii + 0.5) / npx
            vv = 1.0 - (jj + 0.5) / npx
            a = ((uu - INSET) / (1 - 2 * INSET)) * 2 - 1
            b = ((vv - INSET) / (1 - 2 * INSET)) * 2 - 1
            P, n = self.param_points_normals(face, a.ravel(), b.ravel())
            x, y, z = P[:, 0], P[:, 1], P[:, 2]
            nf = np.clip(-n[:, 1], 0, 1)
            frontish = smoothstep(0.05, 0.25, nf)
            soft = f.get('mask_soft', 0.0045)
            patch = smoothstep(soft, -soft, self.patch_sdf(x, z))
            thr = self.frontness_threshold(z)
            lower = smoothstep(thr - 0.06, thr + 0.06, nf) * smoothstep(-0.045, -0.085, z)
            nose = smoothstep(-soft, soft, self.nose_sdf(x, z))
            cel = np.maximum(patch * frontish, lower) * nose
            c = skin[None, :] * (1 - cel[:, None]) + cele[None, :] * cel[:, None]
            # the nose wedge reads as a lighter mid-blue (between skin and celeste)
            nose_in = (1 - nose) * smoothstep(0.07, 0.035, z) * frontish
            nose_c = skin * (1 - f.get('nose_tint', 0.32)) + cele * f.get('nose_tint', 0.32)
            c = c * (1 - nose_in[:, None]) + nose_c[None, :] * nose_in[:, None]
            # upper lid lines
            for side in (-1, 1):
                es = self.eye_sdf(x, z, side)
                ang_ok = smoothstep(f['eye_center_z'] - 0.045, f['eye_center_z'] + 0.01, z)
                lb0, lb1 = f.get('lid_band', [-0.017, 0.004])
                band = smoothstep(lb1, lb1 - 0.003, es) * smoothstep(lb0, lb0 + 0.006, es) * ang_ok
                band *= frontish
                c = c * (1 - band[:, None]) + lid[None, :] * band[:, None]
                inner = smoothstep(0.0005, -0.004, es) * frontish
                c = c * (1 - inner[:, None]) + np.array([0.93, 0.95, 0.99])[None, :] * inner[:, None]
            # mouth
            md, z_top, z_bot = self.mouth_fields(x, z)
            inside = smoothstep(0.0006, -0.0016, md) * frontish
            tz = (z - (z_bot + 0.004)) / 0.012
            tx = x / (f['mouth_half_width'] * 0.55)
            tongue = smoothstep(1.0, 0.75, np.sqrt(tx * tx + tz * tz)) * inside
            mc = mouth_c[None, :] * (1 - tongue[:, None]) + tongue_c[None, :] * tongue[:, None]
            c = c * (1 - inside[:, None]) + mc * inside[:, None]
            # mouth corner dimples (short dark ticks curling upward)
            for side in (-1, 1):
                cx = side * (f['mouth_half_width'] + 0.002)
                cz = f['mouth_center_z'] + 0.004
                dx, dz = x - cx, z - cz
                tick = np.exp(-((dx * side - 0.003) / 0.004) ** 2 - ((dz - 0.002) / 0.0045) ** 2)
                tick = np.clip(tick * 0.55, 0, 0.55) * frontish
                c = c * (1 - tick[:, None]) + mouth_c[None, :] * tick[:, None]
            r = 0.78 * (1 - inside) + 0.42 * inside
            img[py0:py0 + npx, px0:px0 + npx] = c.reshape(npx, npx, 3)
            rough[py0:py0 + npx, px0:px0 + npx] = r.reshape(npx, npx)
        return img, rough

    # ------------------------------------------------------------ helpers
    def surface_point_front(self, x, z, mesh_bvh=None):
        y = self.front_y(np.atleast_1d(x), np.atleast_1d(z))
        return np.stack([np.atleast_1d(x), y, np.atleast_1d(z)], 1)


def eye_texture(cfg, size=1024):
    """Planar-projected eyeball texture (sclera, iris, pupil)."""
    col = cfg['colors']
    f = cfg['face']
    scl = _hexrgb(col['sclera'])
    i_out = _hexrgb(col['iris_outer'])
    i_mid = _hexrgb(col['iris_mid'])
    i_in = _hexrgb(col['iris_inner'])
    pup = _hexrgb(col['pupil'])
    jj, ii = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    u = (ii + 0.5) / size * 2 - 1
    v = 1 - (jj + 0.5) / size * 2
    rho = np.sqrt(u * u + v * v)
    ang = np.arctan2(v, u)
    ri = math.sin(math.radians(f['iris_angle_deg']))
    rp = math.sin(math.radians(f['pupil_angle_deg']))
    rng = np.random.default_rng(7)
    # radial fibres: sum of angular sines with random phases
    fib = np.zeros_like(rho)
    for k, amp in ((23, 0.35), (41, 0.25), (67, 0.2), (97, 0.15), (131, 0.1)):
        fib += amp * np.sin(k * ang + rng.uniform(0, 6.28) + 3.0 * np.sin(5 * ang))
    fib = fib / 1.05
    t = np.clip((rho - rp) / (ri - rp), 0, 1)  # 0 at pupil edge, 1 at limbus
    base = np.where(t[..., None] < 0.55,
                    i_in[None, None, :] * (1 - t[..., None] / 0.55) + i_mid[None, None, :] * (t[..., None] / 0.55),
                    i_mid[None, None, :] * (1 - (t[..., None] - 0.55) / 0.45) + i_out[None, None, :] * ((t[..., None] - 0.55) / 0.45))
    # darker collarette right around the pupil
    coll = np.exp(-((t - 0.08) / 0.07) ** 2)[..., None] * 0.35
    base = base * (1 - coll) + i_out[None, None, :] * coll
    base = base * (1.0 + 0.18 * fib[..., None] * (0.3 + t[..., None]))
    # limbal ring
    limb = smoothstep(ri * 0.80, ri * 0.97, rho)[..., None]
    base = base * (1 - limb * 0.9) + i_out[None, None, :] * 0.5 * limb * 0.9
    iris_m = smoothstep(ri + 0.006, ri - 0.006, rho)[..., None]
    pupil_m = smoothstep(rp + 0.006, rp - 0.004, rho)[..., None]
    sclera = scl[None, None, :] * (1 - 0.06 * smoothstep(0.55, 1.0, rho))[..., None]
    c = sclera * (1 - iris_m) + base * iris_m
    c = c * (1 - pupil_m) + pup[None, None, :] * pupil_m
    return np.clip(c, 0, 1)
