"""Reference images for the web viewer: the photo of every calibrated shot
(for the compare overlay) and its colour-class map (for capture_look.mjs,
which measures the reference shading per material).

    python3 scripts/prep_web_refs.py      ->  web/public/refs/<view>.jpg, <view>_cls.png

Classes: 0 background, 1 blue skin, 2 celeste skin, 3 black / navy
(hoodie, frame, brows), 4 white / grey (shirt, shoes, eye whites),
255 inside the figure but unclassified (edges, highlights, mixed pixels).
"""
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFS = {'front': '02_Morfi_frente', 'profile_left': '03_Morfi_perfil_izquierdo',
        'back': '04_Morfi_espalda', 'profile_right': '05_Morfi_perfil_derecho',
        'three_quarter_front': '06_Morfi_tres_cuartos_frontal',
        'three_quarter_back': '07_Morfi_tres_cuartos_posterior',
        'hero': '00_Morfi_master_wordmark'}


def classes(rgb, mask):
    a = ndi.gaussian_filter(rgb.astype(float) / 255.0, (0.8, 0.8, 0))
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = a.mean(-1)
    blue = (b > 0.45) & (b - r > 0.22)
    # celeste keeps a red / blue ratio of ~0.55 even in shade; the skin blue ~0
    cel = blue & (r / np.maximum(b, 1e-3) > 0.32)
    c = np.full(mask.shape, 255, np.uint8)
    c[blue & ~cel] = 1
    c[cel] = 2
    c[(lum < 0.30) & ~blue] = 3
    c[(lum > 0.60) & (b - r < 0.16) & ~blue] = 4
    c[~mask] = 0
    return c


def main():
    out = os.path.join(ROOT, 'web', 'public', 'refs')
    os.makedirs(out, exist_ok=True)
    index = {}
    for view, ref in REFS.items():
        img = Image.open(os.path.join(ROOT, 'references', ref + '.png')).convert('RGB')
        img.save(os.path.join(out, view + '.jpg'), quality=88, optimize=True, progressive=True)
        # lossless copy for the look capture (not deployed)
        os.makedirs(os.path.join(ROOT, 'work', 'look', 'refs'), exist_ok=True)
        img.save(os.path.join(ROOT, 'work', 'look', 'refs', view + '.png'))
        mp = os.path.join(ROOT, 'references_masks', ref + '.png')
        mask = (np.asarray(Image.open(mp).convert('L').resize(img.size)) > 128) if os.path.exists(mp) else \
            (np.abs(np.asarray(img).astype(int) - [253, 253, 249]).sum(-1) > 18)
        c = classes(np.asarray(img), mask)
        Image.fromarray(c).save(os.path.join(out, view + '_cls.png'), optimize=True)
        index[view] = {'ref': ref, 'size': list(img.size)}
        print(view, {k: int((c == k).sum()) for k in (1, 2, 3, 4, 255)})
    json.dump(index, open(os.path.join(out, 'index.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
