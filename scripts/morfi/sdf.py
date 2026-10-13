"""Vectorized signed-distance-field toolkit + marching cubes.

Points are passed as a tuple of three float arrays (x, y, z) of identical shape.
All primitives return signed distances (negative inside). Smooth boolean
operators follow Inigo Quilez's polynomial formulation.
"""
import numpy as np
from skimage import measure


# ----------------------------------------------------------------- helpers
def vec(*a):
    return np.asarray(a, dtype=np.float64)


def length(x, y, z):
    return np.sqrt(x * x + y * y + z * z)


def clamp(v, a, b):
    return np.minimum(np.maximum(v, a), b)


def smoothstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def rot_matrix(rx=0.0, ry=0.0, rz=0.0):
    """XYZ euler (degrees) -> 3x3 rotation matrix (R = Rz @ Ry @ Rx)."""
    rx, ry, rz = np.radians([rx, ry, rz])
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def to_local(P, center, R=None):
    """World points -> local frame of an object at `center` with rotation R."""
    x, y, z = P[0] - center[0], P[1] - center[1], P[2] - center[2]
    if R is None:
        return x, y, z
    Rt = np.asarray(R).T
    return (Rt[0, 0] * x + Rt[0, 1] * y + Rt[0, 2] * z,
            Rt[1, 0] * x + Rt[1, 1] * y + Rt[1, 2] * z,
            Rt[2, 0] * x + Rt[2, 1] * y + Rt[2, 2] * z)


# ----------------------------------------------------------------- booleans
def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def ssub(a, b, k):
    """Smooth subtraction: a minus b."""
    return smax(a, -b, k)


# ----------------------------------------------------------------- primitives
def sd_sphere(P, c, r):
    return length(P[0] - c[0], P[1] - c[1], P[2] - c[2]) - r


def sd_ellipsoid(P, c, radii, R=None):
    x, y, z = to_local(P, c, R)
    rx, ry, rz = radii
    k0 = np.sqrt((x / rx) ** 2 + (y / ry) ** 2 + (z / rz) ** 2)
    k1 = np.sqrt((x / rx ** 2) ** 2 + (y / ry ** 2) ** 2 + (z / rz ** 2) ** 2)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def sd_round_box(P, c, half, r, R=None):
    x, y, z = to_local(P, c, R)
    qx = np.abs(x) - (half[0] - r)
    qy = np.abs(y) - (half[1] - r)
    qz = np.abs(z) - (half[2] - r)
    outside = length(np.maximum(qx, 0), np.maximum(qy, 0), np.maximum(qz, 0))
    inside = np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0)
    return outside + inside - r


def sd_capsule(P, a, b, r):
    return sd_round_cone(P, a, b, r, r)


def sd_round_cone(P, a, b, ra, rb):
    """IQ round cone between points a (radius ra) and b (radius rb)."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    ba = b - a
    l2 = float(ba @ ba)
    rr = ra - rb
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    px, py, pz = P[0] - a[0], P[1] - a[1], P[2] - a[2]
    y = px * ba[0] + py * ba[1] + pz * ba[2]
    z = y - l2
    xx = (px * l2 - y * ba[0]) ** 2 + (py * l2 - y * ba[1]) ** 2 + (pz * l2 - y * ba[2]) ** 2
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * xx
    out = np.empty_like(px)
    m1 = np.sign(z) * a2 * z2 > k
    m2 = (~m1) & (np.sign(y) * a2 * y2 < k)
    m3 = ~(m1 | m2)
    out[m1] = np.sqrt(xx[m1] + z2[m1]) * il2 - rb
    out[m2] = np.sqrt(xx[m2] + y2[m2]) * il2 - ra
    out[m3] = (np.sqrt(xx[m3] * a2 * il2) + y[m3] * rr) * il2 - ra
    return out


def sd_tube(P, pts, radii, k=0.0):
    """Union of round cones along a polyline with per-point radii."""
    d = None
    for i in range(len(pts) - 1):
        di = sd_round_cone(P, pts[i], pts[i + 1], radii[i], radii[i + 1])
        d = di if d is None else smin(d, di, k)
    return d


def sd_torus(P, c, R, r, Rm=None):
    x, y, z = to_local(P, c, Rm)
    q = np.sqrt(x * x + y * y) - R
    return np.sqrt(q * q + z * z) - r


def sd_plane(P, n, offset):
    """Half space n.p <= offset is inside (negative)."""
    n = np.asarray(n, float)
    n = n / np.linalg.norm(n)
    return P[0] * n[0] + P[1] * n[1] + P[2] * n[2] - offset


def sd_superellipsoid(P, c, radii, e, R=None):
    """Approximate superellipsoid distance |x|^e+|y|^e+|z|^e=1 (scaled)."""
    x, y, z = to_local(P, c, R)
    rx, ry, rz = radii
    f = (np.abs(x / rx) ** e + np.abs(y / ry) ** e + np.abs(z / rz) ** e) ** (1.0 / e)
    return (f - 1.0) * min(radii)


def sd_superquadric(P, c, half, p_h=2.8, q_top=3.0, q_bot=4.0, R=None):
    """Approximate distance to a superquadric 'inflated box'.

    Horizontal section exponent p_h; vertical exponents differ above/below
    the centre (rounder top, flatter bottom).
    """
    x, y, z = to_local(P, c, R)
    ax, ay, az = np.abs(x / half[0]), np.abs(y / half[1]), np.abs(z / half[2])
    h = (ax ** p_h + ay ** p_h) ** (1.0 / p_h)
    t = smoothstep(-0.1, 0.1, z / half[2])
    q = q_bot + (q_top - q_bot) * t
    f = (h ** q + az ** q) ** (1.0 / q)
    return (f - 1.0) * min(half) * 0.9


def rrect2d(u, v, hu, hv, r):
    """2D rounded rectangle distance."""
    qx = np.abs(u) - (hu - r)
    qy = np.abs(v) - (hv - r)
    return np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - r


def extrude(d2, w, h, r=0.0):
    """Extrude 2D distance d2 along w with half-height h and edge radius r."""
    qx = d2 + r
    qy = np.abs(w) - h + r
    return np.minimum(np.maximum(qx, qy), 0) + np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) - r


# ----------------------------------------------------------------- meshing
def polygonize(fn, bmin, bmax, h, level=0.0, slab=48):
    """Evaluate fn on a grid and run marching cubes.

    fn takes (x, y, z) arrays and returns distances. Evaluation is chunked in
    z slabs to keep memory bounded. Returns (verts Nx3 float32, faces Mx3 int).
    """
    bmin = np.asarray(bmin, float)
    bmax = np.asarray(bmax, float)
    n = np.ceil((bmax - bmin) / h).astype(int) + 1
    xs = bmin[0] + np.arange(n[0]) * h
    ys = bmin[1] + np.arange(n[1]) * h
    zs = bmin[2] + np.arange(n[2]) * h
    vol = np.empty((n[0], n[1], n[2]), dtype=np.float32)
    X, Y = np.meshgrid(xs, ys, indexing='ij')
    for k0 in range(0, n[2], slab):
        k1 = min(n[2], k0 + slab)
        zz = zs[k0:k1]
        Xs = np.repeat(X[:, :, None], len(zz), axis=2)
        Ys = np.repeat(Y[:, :, None], len(zz), axis=2)
        Zs = np.broadcast_to(zz[None, None, :], Xs.shape).copy()
        vol[:, :, k0:k1] = fn((Xs, Ys, Zs)).astype(np.float32)
    # make sure the volume boundary is "outside" so surfaces close
    vol[0, :, :] = np.maximum(vol[0, :, :], h)
    vol[-1, :, :] = np.maximum(vol[-1, :, :], h)
    vol[:, 0, :] = np.maximum(vol[:, 0, :], h)
    vol[:, -1, :] = np.maximum(vol[:, -1, :], h)
    vol[:, :, 0] = np.maximum(vol[:, :, 0], h)
    vol[:, :, -1] = np.maximum(vol[:, :, -1], h)
    verts, faces, _n, _v = measure.marching_cubes(vol, level=level, spacing=(h, h, h),
                                                  allow_degenerate=False)
    verts = verts + bmin[None, :]
    # skimage winding yields inward normals for SDF (negative inside); flip
    faces = faces[:, ::-1]
    return verts.astype(np.float64), faces.astype(np.int64)


def sdf_gradient(fn, pts, eps=1e-4):
    """Central-difference gradient of fn at Nx3 points."""
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    gx = fn((x + eps, y, z)) - fn((x - eps, y, z))
    gy = fn((x, y + eps, z)) - fn((x, y - eps, z))
    gz = fn((x, y, z + eps)) - fn((x, y, z - eps))
    g = np.stack([gx, gy, gz], axis=1)
    return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)


def project_to_surface(fn, pts, iters=4):
    """Newton-project points onto the zero level set of fn."""
    p = np.array(pts, float)
    for _ in range(iters):
        d = fn((p[:, 0], p[:, 1], p[:, 2]))
        g = sdf_gradient(fn, p)
        p = p - g * d[:, None]
    return p


def raycast(fn, origins, dirs, tmax=1.0, steps=200):
    """Sphere-trace rays; returns hit points and a hit mask."""
    o = np.asarray(origins, float)
    dvec = np.asarray(dirs, float)
    dvec = dvec / np.linalg.norm(dvec, axis=1, keepdims=True)
    t = np.zeros(len(o))
    hit = np.zeros(len(o), bool)
    for _ in range(steps):
        p = o + dvec * t[:, None]
        d = fn((p[:, 0], p[:, 1], p[:, 2]))
        hit |= d < 1e-5
        t = np.where(hit, t, t + np.maximum(d, 1e-4) * 0.9)
        if np.all(hit | (t > tmax)):
            break
    return o + dvec * t[:, None], hit
