"""Turn the shading measured against the reference photos (work/look/raw.json,
from web/scripts/capture-look.mjs) into the matcap atlas of the web viewer.

    python3 scripts/build_look.py   ->  web/public/look/matcaps.png, look.json
                                        renders/comparisons/look_matcaps.png (preview)

Per material the capture gives, on a 64x64 grid of view-space normals, the mean
log2 ratio photo / albedo. Empty cells (normals no photo shows) are filled by
normalized convolution at growing scales, the result is lightly smoothed and
stored log2-encoded in one tile of the atlas.
"""
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LO, HI = -6.0, 4.0
MIN_SAMPLES = 1500
COLS = 6
# the eye mixes white sclera, blue iris and black pupil under one material and
# its iris always faces the camera: its measured ratio is blotchy and coloured
# (rainbow fringes on the sclera). It keeps only the smooth part, in grey.
SMOOTH_GREY = {'M_Eye'}


def fill(G, w):
    """Normalized convolution: fill empty cells from their neighbours."""
    out = G.copy()
    have = w > 0
    for s in (1.0, 2.0, 4.0, 8.0, 16.0):
        num = np.stack([ndi.gaussian_filter(G[..., c] * w, s, mode='nearest') for c in range(3)], -1)
        den = ndi.gaussian_filter(w, s, mode='nearest')[..., None]
        est = num / np.maximum(den, 1e-9)
        ok = (den[..., 0] > 1e-3) & ~have
        out[ok] = est[ok]
        have = have | ok
    return out


def sh_basis(n):
    """Real spherical harmonics up to band 3 (16 functions) of unit normals (M, 3)."""
    x, y, z = n[:, 0], n[:, 1], n[:, 2]
    return np.stack([np.ones_like(x), y, z, x, x * y, y * z, 3 * z * z - 1, x * z, x * x - y * y,
                     y * (3 * x * x - y * y), x * y * z, y * (5 * z * z - 1), z * (5 * z * z - 3),
                     x * (5 * z * z - 1), z * (x * x - y * y), x * (x * x - 3 * y * y)], 1)


def smooth_fit(G, n, N, residual=True):
    """Lighting of a product shot is smooth over the normals: least-squares
    spherical harmonics (band 3) in log space, plus the measured residual where
    the photos give many samples (keeps sharper features such as highlights)."""
    yy, xx = np.mgrid[0:N, 0:N]
    u = ((xx + 0.5) / N - 0.5) / 0.495
    v = ((yy + 0.5) / N - 0.5) / 0.495
    r = np.minimum(np.hypot(u, v), 0.999)
    sc = np.where(np.hypot(u, v) > 0.999, 0.999 / np.maximum(np.hypot(u, v), 1e-9), 1.0)
    nrm = np.stack([u * sc, v * sc, np.sqrt(1 - r ** 2)], -1).reshape(-1, 3)
    B = sh_basis(nrm)
    w = np.minimum(n / 20.0, 1.0).ravel() * (np.hypot(u, v).ravel() < 1.0)
    sel = w > 0
    Wb = B[sel] * w[sel, None]
    A = Wb.T @ B[sel] + 1e-2 * np.eye(B.shape[1])
    out = np.zeros((N * N, 3))
    for c in range(3):
        coef = np.linalg.solve(A, Wb.T @ G.reshape(-1, 3)[sel, c])
        out[:, c] = B @ coef
    F = out.reshape(N, N, 3)
    if not residual:
        return F
    res = np.where((n > 0)[..., None], G - F, 0.0)
    num = np.stack([ndi.gaussian_filter(res[..., c] * np.minimum(n / 20.0, 1.0), 2.0) for c in range(3)], -1)
    den = ndi.gaussian_filter(np.minimum(n / 20.0, 1.0), 2.0)[..., None]
    conf = np.clip(den / 0.6, 0, 1)
    return F + conf * num / np.maximum(den, 1e-6)


def main():
    raw = json.load(open(os.path.join(ROOT, 'work', 'look', 'raw.json')))
    N = raw['size']
    yy, xx = np.mgrid[0:N, 0:N]
    r = np.hypot((xx + 0.5) / N - 0.5, (yy + 0.5) / N - 0.5) / 0.495
    tiles, info = [], {}
    for name, m in sorted(raw['materials'].items()):
        n = np.array(m['n'], float).reshape(N, N)
        if n.sum() < MIN_SAMPLES:
            print(f'{name:16s} {int(n.sum()):8d} samples  (too few, kept physically shaded)')
            continue
        G = np.clip(np.array(m['mean'], float).reshape(N, N, 3), LO, HI)
        if name in SMOOTH_GREY:
            F = smooth_fit(G, n, N, residual=False)
            F = np.clip(np.repeat(F.mean(-1, keepdims=True), 3, -1), LO, HI)
        else:
            F = np.clip(smooth_fit(G, n, N), LO, HI)
        enc = np.clip((F - LO) / (HI - LO), 0, 1)
        tiles.append((name, (enc[::-1] * 255 + 0.5).astype(np.uint8)))  # image rows top-down
        info[name] = {'tile': len(tiles) - 1, 'samples': int(n.sum())}
        lin = 2 ** F[N // 2, N // 2]
        print(f'{name:16s} {int(n.sum()):8d} samples  centre ratio {np.round(lin, 2)}')
    rows = (len(tiles) + COLS - 1) // COLS
    atlas = np.zeros((rows * N, COLS * N, 3), np.uint8)
    for k, (_, t) in enumerate(tiles):
        r0, c0 = (k // COLS) * N, (k % COLS) * N
        atlas[r0:r0 + N, c0:c0 + N] = t
    out = os.path.join(ROOT, 'web', 'public', 'look')
    os.makedirs(out, exist_ok=True)
    Image.fromarray(atlas).save(os.path.join(out, 'matcaps.png'))
    json.dump({'size': N, 'cols': COLS, 'log2': [LO, HI], 'materials': info, 'shadow': 0.55, 'exposure': 1.0},
              open(os.path.join(out, 'look.json'), 'w'), indent=1)
    # preview: each matcap applied to a mid-grey albedo, on a sphere
    prev = np.full((rows * 140, COLS * 140, 3), 250, np.uint8)
    for k, (name, t) in enumerate(tiles):
        L = t.astype(float) / 255 * (HI - LO) + LO
        rgb = np.clip(0.18 * 2 ** L, 0, 1) ** (1 / 2.2)
        img = Image.fromarray((rgb * 255).astype(np.uint8)).resize((128, 128), Image.BILINEAR)
        mask = Image.new('L', (128, 128), 0)
        from PIL import ImageDraw
        ImageDraw.Draw(mask).ellipse((1, 1, 126, 126), fill=255)
        canvas = Image.fromarray(prev)
        canvas.paste(img, ((k % COLS) * 140 + 6, (k // COLS) * 140 + 6), mask)
        ImageDraw.Draw(canvas).text(((k % COLS) * 140 + 6, (k // COLS) * 140 + 128), name, fill=(30, 30, 30))
        prev = np.asarray(canvas)
    Image.fromarray(prev).save(os.path.join(ROOT, 'renders', 'comparisons', 'look_matcaps.png'))
    print('atlas', atlas.shape, '->', out)


if __name__ == '__main__':
    main()
