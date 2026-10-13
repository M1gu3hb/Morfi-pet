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


def band_noise(n, f0, bw=0.25, seed=0):
    """Periodic narrow-band noise (ring spectrum around f0 cycles/tile), unit std."""
    rng = np.random.default_rng(seed)
    k = np.fft.fftfreq(n) * n
    KX, KY = np.meshgrid(k, k)
    K = np.sqrt(KX ** 2 + KY ** 2)
    amp = np.exp(-((K - f0) / (bw * f0)) ** 2)
    f = np.real(np.fft.ifft2(amp * np.exp(1j * rng.uniform(0, 2 * np.pi, (n, n)))))
    return f / f.std()


def squiggle(n, f0, width=0.07, seed=0):
    """Labyrinth of thin meandering lines (zero set of band noise), 1 on the lines.

    This is the fine "worm" relief visible on Morfi's skin, hoodie and t-shirt
    in the references. width is the line half-width as a fraction of the period.
    """
    a = band_noise(n, f0, 0.25, seed)
    gx = (np.roll(a, -1, 1) - np.roll(a, 1, 1)) * 0.5
    gy = (np.roll(a, -1, 0) - np.roll(a, 1, 0)) * 0.5
    dist = np.abs(a) / (np.sqrt(gx * gx + gy * gy) + 1e-6)
    return np.exp(-(dist / (width * n / f0)) ** 2)


def modulated(L, f0, lo, seed=0):
    """Vary the strength of a line mask over the tile (lo..1).

    The references' felt shows the lines everywhere, but with a contrast that
    comes and goes over a few line spacings (some loops crisp, others almost
    gone), not the uniform maze a plain zero set gives."""
    n = L.shape[0]
    m = fourier_noise(n, 1.5, seed + 7, fmin=4, fmax=f0 / 1.5)
    m = (m - m.mean()) / m.std()
    t = np.clip((m + 1.2) / 2.2, 0, 1)
    return L * (lo + (1 - lo) * t * t * (3 - 2 * t))


def sample_wrap(img, u, v):
    """Bilinear sample of a periodic (H, W[, C]) array at UV (v up, row 0 = top)."""
    H, W = img.shape[:2]
    x = (np.asarray(u) % 1.0) * W - 0.5
    y = ((1.0 - np.asarray(v)) % 1.0) * H - 0.5
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx = x - x0
    fy = y - y0
    if img.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    g = lambda yy, xx: img[yy % H, xx % W]
    return (g(y0, x0) * (1 - fx) * (1 - fy) + g(y0, x0 + 1) * fx * (1 - fy)
            + g(y0 + 1, x0) * (1 - fx) * fy + g(y0 + 1, x0 + 1) * fx * fy)


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


def _srgb(hexstr):
    h = hexstr.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


# Labyrinth parameters, matched to the references by measuring the micro-relief
# of flat patches (high-pass luminance: line spacing and contrast) on 02_frente.
# The UV tiles span 0.4 (skin), 0.286 (hoodie) and 0.2 (t-shirt) units.
#   f0     ring frequency of the band noise, in cycles per tile
#   width  line half-width as a fraction of the period
#   gain   colour change on the lines (+ lighter, - darker)
#   relief sign/weight of the lines in the height map (+ raised ridge)
TEX = {
    'skin': dict(f0=56.0, width=0.055, gain=0.07, relief=0.75, fine=0.25),
    'hoodie': dict(f0=24.0, width=0.065, gain=0.45, relief=0.55),
    'tshirt': dict(f0=44.0, width=0.05, gain=-0.06, relief=0.5),
}
CACHE = {}


def configure(cfg_tex):
    """Override TEX from config['textures'] (if present)."""
    for k, v in (cfg_tex or {}).items():
        if k in TEX:
            TEX[k].update(v)


def skin_lines(n=1024, seed=21):
    t = TEX['skin']
    key = ('skin', n, t['f0'], t['width'], t.get('mod_lo'))
    if key not in CACHE:
        L = squiggle(n, t['f0'], t['width'], seed)
        if t.get('mod_lo') is not None:
            L = modulated(L, t['f0'], t['mod_lo'], seed)
        CACHE[key] = L
    return CACHE[key]


def skin_tile(n=1024, color='#0757F5', seed=21):
    """Skin: velvet micro-noise + fine raised labyrinth ridges (colour + normal)."""
    t = TEX['skin']
    lines = skin_lines(n, seed)
    fine = fourier_noise(n, 1.2, seed + 1, fmin=60)
    h = t['fine'] * fine + t['relief'] * lines
    col = _srgb(color)[None, None, :] * (1.0 + t['gain'] * lines[..., None]) * (0.985 + 0.03 * fine[..., None])
    return np.clip(col, 0, 1), height_to_normal(h, 3.0)


def hoodie_tile(n=1024, color='#212227', seed=31):
    """Fleece with the raised labyrinth pattern (lighter lines)."""
    t = TEX['hoodie']
    lines = squiggle(n, t['f0'], t['width'], seed)
    if t.get('mod_lo') is not None:
        lines = modulated(lines, t['f0'], t['mod_lo'], seed)
    _, fl = fleece(n, seed + 1)
    h = (1 - t['relief']) * fl + t['relief'] * lines
    base = _srgb(color)
    col = base[None, None, :] * (1.0 + t['gain'] * lines[..., None]) * (0.96 + 0.08 * fl[..., None])
    return np.clip(col, 0, 1), height_to_normal(h, 4.0)


def tshirt_tile(n=1024, color='#D6D7DA', seed=41):
    """Heather jersey with a fine, soft embossed labyrinth."""
    t = TEX['tshirt']
    lines = squiggle(n, t['f0'], t['width'], seed)
    col, _ = jersey(n, base=tuple(_srgb(color)), seed=seed + 1)
    col = col * (1.0 + t['gain'] * lines[..., None])
    b = fourier_noise(n, 0.6, seed + 2, fmin=150)
    h = t['relief'] * lines + (1 - t['relief']) * b
    return np.clip(col, 0, 1), height_to_normal(h, 3.0)


def generate_all(out_dir, size=1024, colors=None):
    from .meshutil import save_image
    colors = colors or {}
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    nrm, _ = velvet(size)
    paths['velvet_n'] = save_image(os.path.join(out_dir, 'tile_velvet_normal.png'), nrm)
    nrm, _ = fleece(size)
    paths['fleece_n'] = save_image(os.path.join(out_dir, 'tile_fleece_normal.png'), nrm)
    nrm, _ = rib(512)
    paths['rib_n'] = save_image(os.path.join(out_dir, 'tile_rib_normal.png'), nrm)
    col, nrm = tshirt_tile(size, colors.get('tshirt', '#D6D7DA'))
    paths['jersey_c'] = save_image(os.path.join(out_dir, 'tile_jersey_basecolor.png'), col)
    paths['jersey_n'] = save_image(os.path.join(out_dir, 'tile_jersey_normal.png'), nrm)
    paths['leather_n'] = save_image(os.path.join(out_dir, 'tile_leather_normal.png'), leather(size))
    col, nrm = skin_tile(size, colors.get('skin', '#0757F5'))
    paths['skin_c'] = save_image(os.path.join(out_dir, 'tile_skin_basecolor.png'), col)
    paths['skin_n'] = save_image(os.path.join(out_dir, 'tile_skin_normal.png'), nrm)
    col, nrm = hoodie_tile(size, colors.get('hoodie', '#212227'))
    paths['hoodie_c'] = save_image(os.path.join(out_dir, 'tile_hoodie_basecolor.png'), col)
    paths['hoodie_n'] = save_image(os.path.join(out_dir, 'tile_hoodie_normal.png'), nrm)
    return paths
