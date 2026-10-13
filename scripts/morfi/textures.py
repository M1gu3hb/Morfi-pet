"""Tileable procedural textures (numpy) shared by Cycles and glTF.

All maps are periodic (built from Fourier noise / toroidal Voronoi) so they
tile seamlessly with box/cylindrical UVs. Normal maps are OpenGL-style
(+Y up) tangent-space, which is what glTF expects.
"""
import os
import numpy as np


def fourier_noise(n, beta=2.0, seed=0, fmin=1.0, fmax=None):
    """Periodic 1/f^beta noise in [0, 1]."""
    rng = np.random.default_rng(seed)
    kx = np.fft.fftfreq(n) * n
    ky = np.fft.fftfreq(n) * n
    KX, KY = np.meshgrid(kx, ky)
    k = np.sqrt(KX ** 2 + KY ** 2)
    amp = np.where(k >= fmin, 1.0 / np.maximum(k, 1e-6) ** (beta / 2), 0.0)
    if fmax:
        amp = amp * (k <= fmax)
    ph = rng.uniform(0, 2 * np.pi, (n, n))
    spec = amp * np.exp(1j * ph)
    f = np.real(np.fft.ifft2(spec))
    f -= f.min()
    f /= max(f.max(), 1e-9)
    return f


def voronoi_edges(n, cells, seed=0, jitter=1.0):
    """Toroidal jittered-grid Voronoi F2-F1 (distance to cell edge), 0..1."""
    rng = np.random.default_rng(seed)
    g = max(2, int(round(np.sqrt(cells))))
    off = 0.5 + (rng.random((g, g, 2)) - 0.5) * jitter  # point offset inside each cell
    yy, xx = np.meshgrid((np.arange(n) + 0.5) / n * g, (np.arange(n) + 0.5) / n * g, indexing='ij')
    ci = np.floor(yy).astype(int)
    cj = np.floor(xx).astype(int)
    f1 = np.full((n, n), 9.0)
    f2 = np.full((n, n), 9.0)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            ni = ci + di
            nj = cj + dj
            o = off[ni % g, nj % g]
            py = ni + o[..., 0]
            px = nj + o[..., 1]
            d = np.sqrt((yy - py) ** 2 + (xx - px) ** 2)
            f2 = np.where(d < f1, f1, np.minimum(f2, d))
            f1 = np.minimum(f1, d)
    e = f2 - f1
    return e / max(e.max(), 1e-9)


def height_to_normal(h, strength):
    """Periodic central differences -> RGB normal map (OpenGL +Y)."""
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    nx = -dx * strength
    ny = dy * strength  # image rows go down; flip for +Y up
    nz = np.ones_like(h)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / l * 0.5 + 0.5, ny / l * 0.5 + 0.5, nz / l * 0.5 + 0.5], -1)


def velvet(n=1024, seed=3):
    """Flocked-velvet skin: soft irregular cells + fine fibre noise."""
    e = voronoi_edges(n, 1600, seed, 0.9)
    cells = np.clip(e * 3.0, 0, 1) ** 0.6           # raised cell interiors, grooves at edges
    fine = fourier_noise(n, 1.2, seed + 1, fmin=60)
    h = 0.75 * cells + 0.25 * fine
    return height_to_normal(h, 3.0), h


def fleece(n=1024, seed=5):
    """Brushed cotton fleece: clumpy low-frequency + fibre noise."""
    a = fourier_noise(n, 2.2, seed, fmin=8)
    b = fourier_noise(n, 1.0, seed + 1, fmin=80)
    e = voronoi_edges(n, 900, seed + 2, 1.0)
    h = 0.45 * a + 0.35 * b + 0.2 * np.clip(e * 2.5, 0, 1)
    return height_to_normal(h, 4.0), h


def rib(n=512, ribs=32, seed=7):
    """Knit 1x1 rib: vertical rounded ridges with stitch noise (ribs along v)."""
    x = (np.arange(n) + 0.5) / n
    prof = np.abs(np.sin(np.pi * ribs * x)) ** 0.7
    h = np.tile(prof[None, :], (n, 1))
    st = fourier_noise(n, 1.0, seed, fmin=40)
    stitch = 0.5 + 0.5 * np.sin(2 * np.pi * ribs * 1.6 * ((np.arange(n) + 0.5) / n))[:, None]
    h = 0.8 * h + 0.12 * st + 0.08 * stitch * h
    return height_to_normal(h, 6.0), h


def jersey(n=1024, base=(0.77, 0.772, 0.785), seed=11):
    """Heather-gray jersey colour + fine knit normal."""
    a = fourier_noise(n, 1.4, seed, fmin=20)
    b = fourier_noise(n, 0.6, seed + 1, fmin=150)
    mott = 0.6 * a + 0.4 * b
    col = np.array(base)[None, None, :] * (0.90 + 0.16 * mott[..., None])
    yy, xx = np.meshgrid(np.arange(n), np.arange(n), indexing='ij')
    knit = (0.5 + 0.5 * np.sin(2 * np.pi * xx / n * 220)) * (0.5 + 0.5 * np.sin(2 * np.pi * yy / n * 160 + 1.3 * np.sin(2 * np.pi * xx / n * 220)))
    h = 0.6 * knit + 0.4 * b
    return np.clip(col, 0, 1), height_to_normal(h, 2.5)


def leather(n=1024, seed=13):
    e = voronoi_edges(n, 2500, seed, 1.0)
    f = fourier_noise(n, 1.5, seed + 1, fmin=30)
    h = 0.6 * np.clip(e * 3, 0, 1) ** 0.5 + 0.4 * f
    return height_to_normal(h, 1.6)


def generate_all(out_dir, size=1024):
    from .meshutil import save_image
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    nrm, _ = velvet(size)
    paths['velvet_n'] = save_image(os.path.join(out_dir, 'tile_velvet_normal.png'), nrm)
    nrm, _ = fleece(size)
    paths['fleece_n'] = save_image(os.path.join(out_dir, 'tile_fleece_normal.png'), nrm)
    nrm, _ = rib(512)
    paths['rib_n'] = save_image(os.path.join(out_dir, 'tile_rib_normal.png'), nrm)
    col, nrm = jersey(size)
    paths['jersey_c'] = save_image(os.path.join(out_dir, 'tile_jersey_basecolor.png'), col)
    paths['jersey_n'] = save_image(os.path.join(out_dir, 'tile_jersey_normal.png'), nrm)
    paths['leather_n'] = save_image(os.path.join(out_dir, 'tile_leather_normal.png'), leather(size))
    return paths
