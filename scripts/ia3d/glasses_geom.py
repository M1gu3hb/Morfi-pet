"""Geometry of Morfi's rebuilt glasses (pure numpy / scipy, no Blender): the unwrapped head map,
the frame outline, the quad layout of the front face, the frame shell and the lenses.
Used by fix_glasses.py.

Unwrapped map: s = arc length around the head (0 at the front, + toward Morfi's left, metres),
z = height; a point is the smooth skin at (s, z) pushed out by h along the horizontal radial
direction from the head axis (x = 0, y = CY).
"""
import math

import numpy as np
from scipy import ndimage as ndi
from scipy.interpolate import RectBivariateSpline

CY = 0.03                    # head axis (x = 0, y = CY): rays come in from outside toward it
TH_MAX = 1.95                # radians either side of the front (the temples end at ~1.85)
Z0, Z1 = 0.575, 0.865        # height band sampled
DTH, PX = 0.0018, 0.0004     # angular step of the rays / pixel of the unwrapped metric map
MARGIN = 0.0010              # the new frame covers the painted one by this much
ROUND = 0.0030               # rounded edge: the front face is inset by this, the walls go out by it
GROOVE_D, GROOVE_W = 0.0012, 0.0024
WALL_SINK = 0.0030           # walls go this far under the skin around them
LENS_SEG, LENS_RINGS, LENS_BULGE = 96, 8, 0.035


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class Unwrap:
    """Metric unwrapped map: s = arc length around the head (0 at the front, + toward Morfi's left),
    z = height. 3D: radius Rs(theta, z) of the smooth skin + h, along the horizontal radial direction."""

    def __init__(self, ths, zs, R, rgb):
        col = np.nanmedian(R, axis=0)
        col = ndi.gaussian_filter1d(np.nan_to_num(col, nan=np.nanmedian(col)), 0.05 / DTH)
        ds = np.sqrt(col ** 2 + np.gradient(col, DTH) ** 2) * DTH
        s = np.concatenate([[0.0], np.cumsum(0.5 * (ds[1:] + ds[:-1]))])
        s -= np.interp(0.0, ths, s)
        self.th_tab, self.s_tab = ths, s
        self.ss = np.arange(s[0], s[-1], PX)
        self.zs = zs
        fi = np.interp(np.interp(self.ss, s, ths), ths, np.arange(len(ths)))
        rows = np.arange(len(zs))[:, None] * np.ones((1, len(self.ss)))
        cols = np.ones((len(zs), 1)) * fi[None, :]
        Rf = np.where(np.isnan(R), np.nanmedian(R), R)
        self.R = ndi.map_coordinates(Rf, [rows, cols], order=1)
        self.rgb = np.stack([ndi.map_coordinates(rgb[..., k].astype(float), [rows, cols], order=1)
                             for k in range(3)], -1)
        self.Rs = None

    def ij(self, s, z):
        return (np.asarray(z) - self.zs[0]) / PX, (np.asarray(s) - self.ss[0]) / PX

    def sample(self, field, s, z, order=1):
        j, i = self.ij(s, z)
        return ndi.map_coordinates(field, [np.atleast_1d(j), np.atleast_1d(i)], order=order, mode="nearest")

    def set_skin(self, Rs):
        self.Rs = Rs
        self.spline = RectBivariateSpline(self.zs, self.ss, Rs, kx=3, ky=3)

    def theta(self, s):
        return np.interp(s, self.s_tab, self.th_tab)

    def to3d(self, s, z, h):
        s, z, h = np.broadcast_arrays(np.asarray(s, float), np.asarray(z, float), np.asarray(h, float))
        th = self.theta(s)
        r = self.spline.ev(z, s) + h
        return np.stack([r * np.sin(th), CY - r * np.cos(th), z], -1)

    def from3d(self, P):
        """(s, z, h) of 3D points (h relative to the smooth skin)."""
        P = np.asarray(P, float)
        th = np.arctan2(P[:, 0], CY - P[:, 1])
        s = np.interp(th, self.th_tab, self.s_tab)
        r = np.hypot(P[:, 0], P[:, 1] - CY)
        return s, P[:, 2], r - self.spline.ev(P[:, 2], s)


def disk(r_px):
    r = int(math.ceil(r_px))
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r_px * r_px


def frame_mask(U):
    """The painted frame: the largest very dark navy region, thin painted lines inside the openings
    cut off, highlight streaks and pinholes filled."""
    rgb = U.rgb
    lum = rgb.mean(-1)
    dark = (lum < 32) & (rgb[..., 2] > rgb[..., 0] + 8)
    lab, n = ndi.label(dark)
    m = lab == 1 + int(np.argmax(ndi.sum(dark, lab, range(1, n + 1))))
    m = ndi.binary_opening(m, structure=disk(0.002 / PX))
    lab, n = ndi.label(m)
    m = lab == 1 + int(np.argmax(ndi.sum(m, lab, range(1, n + 1))))
    m = ndi.binary_closing(np.pad(m, 20), structure=disk(0.002 / PX))[20:-20, 20:-20]
    holes = ndi.binary_fill_holes(m) & ~m
    lab, n = ndi.label(holes)
    size = ndi.sum(holes, lab, range(1, n + 1))
    keep = np.argsort(-size)[:2] + 1                     # the two lens openings
    return m | (holes & ~np.isin(lab, keep))


def masked_smooth(A, m, sigma_px):
    m = m.astype(float)
    return ndi.gaussian_filter(A * m, sigma_px) / np.maximum(ndi.gaussian_filter(m, sigma_px), 1e-6)


def measure(U):
    """Frame mask, smooth skin radius under everything, sculpted frame height and the signed
    distance to the outline (metres, + outside the frame)."""
    fm = frame_mask(U)
    lum = U.rgb.mean(-1)
    paint = (lum < 70) & (U.rgb[..., 2] > U.rgb[..., 0] + 25)          # frame, brows, painted lines
    skin = ~ndi.binary_dilation(paint | fm, structure=disk(0.002 / PX))
    Rs = masked_smooth(U.R, skin, 0.008 / PX)
    skin &= U.R - Rs < 0.003                              # sculpted lens edges are not skin either
    Rs = masked_smooth(U.R, skin, 0.008 / PX)
    U.set_skin(Rs)
    rel = U.R - Rs
    core = ndi.binary_erosion(fm, structure=disk(0.0025 / PX))
    Hf = masked_smooth(rel, core, 0.005 / PX)
    inside = ndi.distance_transform_edt(fm)
    outside = ndi.distance_transform_edt(~fm)
    sdf = ndi.gaussian_filter((outside - inside) * PX, 0.0016 / PX)
    return {"mask": fm, "rel": rel, "H": Hf, "sdf": sdf, "skin": skin}


# ---------------------------------------------------------------- outline curves
_EDGES = {1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)], 6: [(0, 2)], 7: [(3, 2)], 8: [(2, 3)],
          9: [(2, 0)], 11: [(2, 1)], 12: [(1, 3)], 13: [(1, 0)], 14: [(0, 3)]}


def iso_loops(F, level):
    """Closed iso-lines F = level (marching squares), as (n, 2) arrays of (col, row) pixel coords."""
    A = np.pad(F - level, 1, constant_values=-1.0)
    Hh, W = A.shape
    a, b, c, d = A[:-1, :-1], A[:-1, 1:], A[1:, 1:], A[1:, :-1]
    case = (a > 0) * 1 + (b > 0) * 2 + (c > 0) * 4 + (d > 0) * 8
    centre = (a + b + c + d) > 0
    segs = []
    for cv in range(1, 15):
        jj, ii = np.nonzero(case == cv)
        for j, i in zip(jj, ii):
            if cv in (5, 10):
                cut_ac = (cv == 5) != bool(centre[j, i])      # cut off corners a and c
                pairs = [(3, 0), (1, 2)] if cut_ac else [(0, 1), (2, 3)]
            else:
                pairs = _EDGES[cv]
            for e1, e2 in pairs:
                segs.append((j, i, e1, e2))
    def edge(j, i, e):
        if e == 0:
            return ("h", j, i), (i + A[j, i] / (A[j, i] - A[j, i + 1]), j)
        if e == 1:
            return ("v", j, i + 1), (i + 1, j + A[j, i + 1] / (A[j, i + 1] - A[j + 1, i + 1]))
        if e == 2:
            return ("h", j + 1, i), (i + A[j + 1, i] / (A[j + 1, i] - A[j + 1, i + 1]), j + 1)
        return ("v", j, i), (i, j + A[j, i] / (A[j, i] - A[j + 1, i]))
    nb, pos = {}, {}
    for j, i, e1, e2 in segs:
        k1, p1 = edge(j, i, e1)
        k2, p2 = edge(j, i, e2)
        pos[k1], pos[k2] = p1, p2
        nb.setdefault(k1, []).append(k2)
        nb.setdefault(k2, []).append(k1)
    loops, seen = [], set()
    for start in nb:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [k for k in nb[cur] if k != prev and (k not in seen or k == start)]
            if not nxt or nxt[0] == start:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        loops.append(np.array([pos[k] for k in loop]) - 1.0)      # undo the padding
    return loops


def resample_loop(P, step):
    """Closed polyline -> evenly spaced points (spacing ~step)."""
    Q = np.vstack([P, P[:1]])
    seg = np.linalg.norm(np.diff(Q, axis=0), axis=1)
    t = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(8, int(round(t[-1] / step)))
    u = np.linspace(0, t[-1], n, endpoint=False)
    return np.stack([np.interp(u, t, Q[:, 0]), np.interp(u, t, Q[:, 1])], 1)


def signed_area(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


def outline(U, M, level):
    """Outer loop and the two hole loops (R = image left, -s) of the frame at sdf = level, in metres,
    each counter-clockwise in (s, z)."""
    loops = [np.stack([U.ss[0] + L[:, 0] * PX, U.zs[0] + L[:, 1] * PX], 1)
             for L in iso_loops(-M["sdf"], -level) if len(L) > 50]
    loops.sort(key=lambda L: -abs(signed_area(L)))
    outer = loops[0]
    holes = sorted(loops[1:3], key=lambda L: L[:, 0].mean())
    fix = lambda L: L if signed_area(L) > 0 else L[::-1]  # noqa: E731
    return fix(resample_loop(outer, 0.0005)), [fix(resample_loop(h, 0.0005)) for h in holes]


def loop_normals(P, smooth=6):
    """Unit normals to the right of the direction of travel (outside a counter-clockwise loop)."""
    T = ndi.gaussian_filter1d(np.roll(P, -1, 0) - np.roll(P, 1, 0), smooth, axis=0, mode="wrap")
    N = np.stack([T[:, 1], -T[:, 0]], 1)
    return N / np.linalg.norm(N, axis=1, keepdims=True)


def convex_hole(P):
    """Lens opening = convex hull of the painted one (painted reflections intrude into it), rounded."""
    from scipy.spatial import ConvexHull
    hull = P[ConvexHull(P).vertices]
    Q = resample_loop(hull if signed_area(hull) > 0 else hull[::-1], 0.0005)
    return resample_loop(ndi.gaussian_filter1d(Q, 6, axis=0, mode="wrap"), 0.0005)


def ray_hit(p, d, loops, tmin=0.0005):
    """Distance along the rays p + t d to the first crossing with any loop (inf if none)."""
    A = np.vstack([L for L in loops])
    B = np.vstack([np.roll(L, -1, 0) for L in loops])
    E = B - A
    best = np.full(len(p), np.inf)
    for k in range(0, len(p), 256):
        pp, dd = p[k:k + 256, None, :], d[k:k + 256, None, :]
        den = dd[..., 0] * E[None, :, 1] - dd[..., 1] * E[None, :, 0]
        q = A[None] - pp
        t = (q[..., 0] * E[None, :, 1] - q[..., 1] * E[None, :, 0]) / np.where(den == 0, 1e-12, den)
        u = (q[..., 0] * dd[..., 1] - q[..., 1] * dd[..., 0]) / np.where(den == 0, 1e-12, den)
        t = np.where((den != 0) & (u >= 0) & (u <= 1) & (t > tmin), t, np.inf)
        best[k:k + 256] = t.min(1)
    return best


def runs(flag):
    """Contiguous True runs of a periodic boolean array: list of (start, end) indices, end inclusive."""
    n = len(flag)
    if flag.all() or not flag.any():
        return []
    k0 = int(np.argmin(flag))                            # start the scan on a False sample
    out, start = [], None
    for k in range(n + 1):
        i = (k0 + k) % n
        if flag[i] and start is None:
            start = i
        elif not flag[i] and start is not None:
            out.append((start, (i - 1) % n))
            start = None
    return out


def rim_band(hole, outer, other):
    """Inner edge, outward directions and band width along a lens opening. Where the band runs into
    the bridge or an arm (junction) the width is bridged smoothly; junction runs are returned."""
    n = loop_normals(hole, 10)
    w = ray_hit(hole, n, [outer, other])
    wc = np.minimum(w, 0.2)
    base = ndi.grey_opening(wc, size=121, mode="wrap")      # band width without peaks < 6 cm wide
    core = wc - base > 0.008
    slope = np.abs(np.gradient(wc)) / 0.0005
    junc = core.copy()
    for _ in range(16):                                   # grow over the fillets (fast widening)
        grow = (np.roll(junc, 1) | np.roll(junc, -1)) & (slope > 0.4)
        if not (grow & ~junc).any():
            break
        junc |= grow
    gap = 30                                              # one junction, not pieces 15 mm apart
    grown = np.any([np.roll(junc, k) for k in range(-gap, gap + 1)], axis=0)
    junc |= np.all([np.roll(grown, k) for k in range(-gap, gap + 1)], axis=0)
    wf = w.copy()
    for a, b in runs(junc):                              # cubic Hermite across each junction
        ia, ib = (a - 1) % len(w), (b + 1) % len(w)
        m = (b - a) % len(w) + 2
        ta = (w[ia] - w[(ia - 4) % len(w)]) / 4 * m
        tb = (w[(ib + 4) % len(w)] - w[ib]) / 4 * m
        t = np.arange(1, m) / m
        h = [2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2]
        val = h[0] * w[ia] + h[1] * ta + h[2] * w[ib] + h[3] * tb
        wf[(a + np.arange(m - 1)) % len(w)] = val
    return n, wf, runs(junc)


# ---------------------------------------------------------------- front face layout (2D, quads)
ROWS = 3                     # quads across a rim band
SP_MIN, SP_MAX, SP_ARM = 0.0028, 0.0070, 0.0080


def lerp_loop(A, f):
    """Values of a periodic sampled array at fractional indices."""
    n = len(A)
    i0 = np.floor(f).astype(int) % n
    t = (f - np.floor(f))[:, None] if A.ndim > 1 else f - np.floor(f)
    return A[i0] * (1 - t) + A[(i0 + 1) % n] * t


def rim_positions(hole, juncs, counts):
    """Fractional loop indices of a rim's vertices: curvature-adaptive spacing between junctions,
    exactly counts[i] segments across junction i (which starts and ends on real outline points)."""
    n = len(hole)
    T = np.roll(hole, -1, 0) - np.roll(hole, 1, 0)
    ang = np.unwrap(np.arctan2(T[:, 1], T[:, 0]))
    kappa = np.abs(np.gradient(ndi.gaussian_filter1d(ang, 4, mode="nearest"))) / 0.0005
    sp = np.clip(SP_MAX / (1.0 + 0.025 * kappa), SP_MIN, SP_MAX)
    dens = 0.0005 / sp
    spans = sorted(((a - 1) % n, (b + 1) % n, c) for (a, b), c in zip(juncs, counts))
    if not spans:
        g = np.cumsum(dens)
        m = max(8, int(round(g[-1])))
        return np.interp(np.arange(m) * g[-1] / m, g, np.arange(n))
    pos = []
    for k, (a, b, c) in enumerate(spans):
        la = (b - a) % n
        pos += list(a + la * np.arange(c) / c)            # junction: uniform, end excluded
        na = spans[(k + 1) % len(spans)][0]
        lr = (na - b) % n
        g = np.cumsum(np.r_[0.0, dens[(b + np.arange(lr)) % n]])
        m = max(1, int(round(g[-1])))
        pos += list(b + np.interp(np.arange(m) * g[-1] / m, g, np.arange(lr + 1)))
    return np.array(pos) % n


def path_on_loop(L, p_from, p_to):
    """Shorter way along the closed loop L between the points nearest p_from and p_to."""
    n = len(L)
    i = int(np.argmin(np.linalg.norm(L - p_from, axis=1)))
    j = int(np.argmin(np.linalg.norm(L - p_to, axis=1)))
    fwd, bwd = (j - i) % n, (i - j) % n
    idx = (i + np.arange(fwd + 1)) % n if fwd <= bwd else (i - np.arange(bwd + 1)) % n
    P = L[idx].copy()
    P[0], P[-1] = p_from, p_to
    return P


def resample_open(P, count):
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    t = np.concatenate([[0.0], np.cumsum(seg)])
    u = np.linspace(0, t[-1], count + 1)
    return np.stack([np.interp(u, t, P[:, 0]), np.interp(u, t, P[:, 1])], 1)


def path_len(P):
    return float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1)))


def relax(P, iters=600):
    """Harmonic smoothing of a patch grid's interior, boundary kept (untangles Coons folds); the
    two directions are weighted by their spacing so long thin cells stay as they are."""
    hx = np.mean(np.linalg.norm(np.diff(P[:, [0, -1]], axis=0), axis=-1))
    hy = np.mean(np.linalg.norm(np.diff(P[[0, -1]], axis=1), axis=-1))
    a, b = 1.0 / hx ** 2, 1.0 / hy ** 2
    P = P.copy()
    for _ in range(iters):
        P[1:-1, 1:-1] = (a * (P[2:, 1:-1] + P[:-2, 1:-1]) + b * (P[1:-1, 2:] + P[1:-1, :-2])) / (2 * (a + b))
    return P


def coons(left, right, bottom, top):
    """Transfinite grid (M+1, N+1, 2): left/right run bottom->top, bottom/top run left->right."""
    M, N = len(bottom) - 1, len(left) - 1
    u = np.linspace(0, 1, M + 1)[:, None, None]
    v = np.linspace(0, 1, N + 1)[None, :, None]
    return ((1 - u) * left[None] + u * right[None] + (1 - v) * bottom[:, None] + v * top[:, None]
            - ((1 - u) * (1 - v) * left[0] + u * (1 - v) * right[0] + (1 - u) * v * left[-1] + u * v * right[-1]))


class Front:
    """The front face as a 2D quad mesh in (s, z)."""

    def __init__(self):
        self.v, self.f = [], []

    def add(self, pts):
        i0 = len(self.v)
        self.v += [tuple(p) for p in pts]
        return np.arange(i0, i0 + len(pts))

    def grid(self, ids):
        """Quads of an id grid (cols, rows)."""
        for i in range(ids.shape[0] - 1):
            for j in range(ids.shape[1] - 1):
                self.f.append([ids[i, j], ids[i + 1, j], ids[i + 1, j + 1], ids[i, j + 1]])

    def finish(self):
        V, F = np.array(self.v), np.array(self.f)
        P = V[F]
        area = 0.5 * np.sum(P[:, :, 0] * np.roll(P[:, :, 1], -1, 1) - np.roll(P[:, :, 0], -1, 1) * P[:, :, 1], 1)
        F[area < 0] = F[area < 0][:, ::-1]                 # counter-clockwise seen from outside
        return V, F


def junction_kinds(bands):
    kinds = []
    for k, (n, w, juncs) in enumerate(bands):
        side = -1.0 if k == 0 else 1.0                    # the R rim is on the -s side
        kk = []
        for a, b in juncs:
            idx = (a + np.arange((b - a) % len(w) + 1)) % len(w)
            ns = n[idx, 0].mean() * side
            kk.append("bridge" if ns < -0.5 else "arm" if ns > 0.5 else "other")
        kinds.append(kk)
    return kinds


def build_layout(outer, holes):
    """Rims (bands around the openings), the bridge and the two arms (end piece + temple) as one
    connected quad mesh: 2D vertices, quads and info."""
    fr, rims, info = Front(), [], {}
    bands = [rim_band(holes[k], outer, holes[1 - k]) for k in (0, 1)]
    kinds = junction_kinds(bands)
    jlen = lambda a, b, L: ((b - a) % L + 2) * 0.0005  # noqa: E731
    lens = [jlen(a, b, len(bands[k][1])) for k in (0, 1) for (a, b), t in zip(bands[k][2], kinds[k]) if t == "bridge"]
    nb = max(3, int(round(np.mean(lens) / 0.004))) if lens else 3
    for k, (n, w, juncs) in enumerate(bands):
        counts = [nb if t == "bridge" else max(3, int(round(jlen(a, b, len(w)) / 0.0055)))
                  for (a, b), t in zip(juncs, kinds[k])]
        pos = rim_positions(holes[k], juncs, counts)
        p_in, nn, ww = lerp_loop(holes[k], pos), lerp_loop(n, pos), lerp_loop(w, pos)
        pts = np.stack([p_in + nn * (ww * r / ROWS)[:, None] for r in range(ROWS + 1)], 1)
        ids = fr.add(pts.reshape(-1, 2)).reshape(len(pos), ROWS + 1)
        fr.grid(np.vstack([ids, ids[:1]]))
        spans = []
        for (a, b), t in zip(juncs, kinds[k]):
            a1, b1 = (a - 1) % len(w), (b + 1) % len(w)
            near = lambda q: int(np.argmin(np.abs((pos - q + len(w) / 2) % len(w) - len(w) / 2)))  # noqa: E731
            ia, ib = near(a1), near(b1)
            spans.append((t, ids[(ia + np.arange((ib - ia) % len(pos) + 1)) % len(pos), ROWS]))
        rims.append(spans)
        info["rim_" + "RL"[k]] = {"verts": int(len(pos)), "junctions": [(t, int(len(c))) for t, c in spans],
                                  "band_mm": [round(float(np.min(w)) * 1e3, 1), round(float(np.median(w)) * 1e3, 1)]}
    V = np.array(fr.v)
    bottom_up = lambda col: col if V[col[0], 1] < V[col[-1], 1] else col[::-1]  # noqa: E731
    lc = [bottom_up(c) for t, c in rims[0] if t == "bridge"]
    rc = [bottom_up(c) for t, c in rims[1] if t == "bridge"]
    if lc and rc and len(lc[0]) == len(rc[0]):
        add_patch(fr, outer, lc[0], rc[0], 0.0045)
        info["bridge_rows"] = int(len(lc[0]))
    for k, sgn in ((0, -1.0), (1, 1.0)):
        col = [c for t, c in rims[k] if t == "arm"]
        if col:
            info["arm_" + "RL"[k]] = add_arm(fr, outer, bottom_up(col[0]), sgn)
    V, F = fr.finish()
    return V, F, info


def add_patch(fr, outer, lc, rc, step):
    V = np.array(fr.v)
    bot = path_on_loop(outer, V[lc[0]], V[rc[0]])
    top = path_on_loop(outer, V[lc[-1]], V[rc[-1]])
    m = max(2, int(round(0.5 * (path_len(bot) + path_len(top)) / step)))
    G = relax(coons(V[lc], V[rc], resample_open(bot, m), resample_open(top, m)))
    ids = np.zeros(G.shape[:2], int)
    ids[0], ids[-1] = lc, rc
    ids[1:-1] = fr.add(G[1:-1].reshape(-1, 2)).reshape(m - 1, len(lc))
    fr.grid(ids)


def add_arm(fr, outer, col, sgn):
    """End piece + temple: from the rim out to the rounded tip."""
    V = np.array(fr.v)
    s = outer[:, 0] * sgn
    ext = int(np.argmax(s))
    near = np.abs(s - (s[ext] - 0.03)) < 0.002
    r_tip = 0.5 * (outer[near, 1].max() - outer[near, 1].min())
    # the tip column covers the middle of the rounded end (corners of ~135 degrees, not flat)
    a, b = next((a, b) for a, b in runs(s > s[ext] - 0.3 * r_tip) if (ext - a) % len(s) <= (b - a) % len(s))
    ends = sorted([outer[a], outer[b]], key=lambda p: p[1])        # bottom, top
    right = resample_open(path_on_loop(outer, ends[0], ends[1]), len(col) - 1)
    bot = path_on_loop(outer, V[col[0]], ends[0])
    top = path_on_loop(outer, V[col[-1]], ends[1])
    m = max(2, int(round(0.5 * (path_len(bot) + path_len(top)) / SP_ARM)))
    G = relax(coons(V[col], right, resample_open(bot, m), resample_open(top, m)))
    ids = np.zeros(G.shape[:2], int)
    ids[0] = col
    ids[1:] = fr.add(G[1:].reshape(-1, 2)).reshape(m, len(col))
    fr.grid(ids)
    return {"cols": int(m), "rows": int(len(col)), "tip_r_mm": round(r_tip * 1e3, 1)}


# ---------------------------------------------------------------- the frame in 3D
def boundary_loops(F):
    """Boundary loops of a counter-clockwise quad mesh, each walked with the faces on its left."""
    edges = set()
    for f in F:
        for k in range(len(f)):
            edges.add((int(f[k]), int(f[(k + 1) % len(f)])))
    nxt = {a: b for a, b in edges if (b, a) not in edges}
    loops, seen = [], set()
    for a in nxt:
        if a in seen:
            continue
        L, c = [a], nxt[a]
        seen.add(a)
        while c != a:
            L.append(c)
            seen.add(c)
            c = nxt[c]
        loops.append(np.array(L))
    return loops


def bezier_fillet(H, g, d):
    """Rounded edge from the front face (height H, slope g outward) to a wall d further out:
    (offset, height) of 3 points along a quadratic Bezier, tangent to both."""
    t = np.array([1 / 3, 2 / 3, 1.0])[:, None]
    B = np.stack([np.zeros_like(H), H], -1)
    Q = np.stack([np.full_like(H, d), H + g * d], -1)
    E = np.stack([np.full_like(H, d), H + g * d - d], -1)
    return (1 - t)[..., None] * (1 - t)[..., None] * B[None] + 2 * (t * (1 - t))[..., None] * Q[None] \
        + (t * t)[..., None] * E[None]


def build_frame(U, M, V2, F2):
    """Front face at the sculpted height, then walls with rounded edges along every boundary loop
    (the lens openings get a groove). Returns 3D verts, faces, the groove ring of each opening."""
    Hf, rel = M["H"], M["rel"]
    sH = lambda P: U.sample(Hf, P[:, 0], P[:, 1])  # noqa: E731
    verts = [np.c_[V2, sH(V2)]]                        # (s, z, h)
    faces = [F2]
    nv = len(V2)
    loops = boundary_loops(F2)
    areas = [signed_area(V2[L]) for L in loops]
    outer_k = int(np.argmax(np.abs(areas)))
    grooves = []
    for k, L in enumerate(loops):
        P = V2[L]
        n = loop_normals(P, 1.0)
        H = sH(P)
        g = np.clip((sH(P + 0.0005 * n) - sH(P - 0.0005 * n)) / 0.001, -0.6, 0.6)
        near = P + (ROUND + 0.0015) * n
        h_skin = np.minimum(U.sample(rel, near[:, 0], near[:, 1]), 0.001)
        h_bot = np.minimum(-WALL_SINK, h_skin - 0.002)
        prof = [(np.zeros_like(H), H)] + [(f[:, 0], f[:, 1]) for f in bezier_fillet(H, g, ROUND)]
        if k != outer_k:                                   # lens groove on the inner wall
            top = prof[-1][1]
            hg = np.minimum(0.5 * H, top - GROOVE_W / 2 - 0.0015)
            prof += [(np.full_like(H, ROUND), hg + GROOVE_W / 2), (np.full_like(H, ROUND - GROOVE_D), hg),
                     (np.full_like(H, ROUND), hg - GROOVE_W / 2)]
            gp = P + (ROUND - GROOVE_D / 2) * n
            grooves.append(np.c_[gp, hg])
        prof.append((np.full_like(H, ROUND), h_bot))
        ring_ids = [L]
        for off, h in prof[1:]:
            Q = P + off[:, None] * n
            verts.append(np.c_[Q, h])
            ring_ids.append(np.arange(nv, nv + len(L)))
            nv += len(L)
        R = np.array(ring_ids)                               # (profile, loop)
        a, b = R[:, :], np.roll(R, -1, axis=1)
        faces.append(np.stack([b[:-1], a[:-1], a[1:], b[1:]], -1).reshape(-1, 4))
    S = np.vstack(verts)
    return S, np.vstack(faces), grooves


# ---------------------------------------------------------------- lenses
def build_lens(U, groove):
    """Polar lens whose rim runs in the frame groove: the rim's depth extended harmonically over
    the disk plus a gentle dome (no face relief, no hole, no staircase)."""
    loop = groove[:, :2]
    hg = groove[:, 2]
    if signed_area(loop) < 0:
        loop, hg = loop[::-1], hg[::-1]
    Q2 = np.vstack([loop, loop[:1]])
    t = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(Q2, axis=0), axis=1))])
    u = np.linspace(0, t[-1], LENS_SEG, endpoint=False)
    rim2 = np.stack([np.interp(u, t, Q2[:, 0]), np.interp(u, t, Q2[:, 1])], 1)
    rim_h = np.interp(u, t, np.r_[hg, hg[:1]])
    rim2 = ndi.gaussian_filter1d(rim2, 1.0, axis=0, mode="wrap")
    rim_h = ndi.gaussian_filter1d(rim_h, 1.0, mode="wrap")
    Q = U.to3d(rim2[:, 0], rim2[:, 1], rim_h)
    C = Q.mean(0)
    _u, _s, vt = np.linalg.svd(Q - C)
    e1, e2, nrm = vt
    th = U.theta(np.array([loop[:, 0].mean()]))[0]
    if nrm @ np.array([math.sin(th), -math.cos(th), 0.0]) < 0:
        nrm, e2 = -nrm, -e2
    q = np.stack([(Q - C) @ e1, (Q - C) @ e2], 1)
    depth = (Q - C) @ nrm
    coef = np.fft.fft(depth)
    m = np.abs(np.fft.fftfreq(LENS_SEG, 1.0 / LENS_SEG))
    bulge = LENS_BULGE * np.mean(np.linalg.norm(q, axis=1))
    rings = np.sin(0.5 * np.pi * np.arange(1, LENS_RINGS + 1) / LENS_RINGS)
    verts = [C + (coef[0].real / LENS_SEG + bulge) * nrm]
    for r in rings:
        d = np.fft.ifft(coef * r ** m).real + bulge * (1 - r * r)
        verts += list(C + r * (q[:, :1] * e1 + q[:, 1:] * e2) + d[:, None] * nrm)
    faces = [[0, 1 + k, 1 + (k + 1) % LENS_SEG] for k in range(LENS_SEG)]
    for i in range(LENS_RINGS - 1):
        b0, b1 = 1 + i * LENS_SEG, 1 + (i + 1) * LENS_SEG
        faces += [[b0 + k, b1 + k, b1 + (k + 1) % LENS_SEG, b0 + (k + 1) % LENS_SEG] for k in range(LENS_SEG)]
    V = np.array(verts)
    fn = np.cross(V[faces[0][1]] - V[faces[0][0]], V[faces[0][2]] - V[faces[0][0]])
    if fn @ nrm < 0:                                       # face the camera
        faces = [f[::-1] for f in faces]
    return V, faces, {"bulge_mm": round(bulge * 1e3, 2), "rim_depth_range_mm": round(float(np.ptp(depth)) * 1e3, 1),
                      "tris": LENS_SEG * (2 * LENS_RINGS - 1)}, nrm


def raster(U, loops):
    """Even-odd fill of (s, z) polygons on the unwrapped grid."""
    from PIL import Image, ImageDraw
    img = Image.new("L", (len(U.ss), len(U.zs)), 0)
    dr = ImageDraw.Draw(img)
    for L in loops:
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon([((p[0] - U.ss[0]) / PX, (p[1] - U.zs[0]) / PX) for p in L], fill=255)
        img = Image.fromarray(np.asarray(img) ^ np.asarray(mask))
        dr = ImageDraw.Draw(img)
    del dr
    return np.asarray(img) > 0


def sdf_of(m):
    return (ndi.distance_transform_edt(~m) - ndi.distance_transform_edt(m)) * PX


def footprint(U, walls, outer_k):
    """Signed distances (+ outside) to the new frame and to the whole glasses (frame + openings)."""
    frame = raster(U, walls)
    glasses = raster(U, [walls[outer_k]])
    return sdf_of(frame), sdf_of(glasses)
