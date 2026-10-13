"""Accurate silhouettes of the reference images.

A plain colour threshold cannot separate the white sneakers from the
near-white studio background, and it picks up the floor shadows. Masks are
made with a dichotomous image segmentation network (rembg / BiRefNet), which
keeps the sneakers, drops the floor shadows and opens the gap between the
legs; a light clean-up removes specks and fills interior holes.

    pip install "rembg[cpu]"
    python3 scripts/ref_masks.py          -> references_masks/<ref>.png (255 = Morfi)
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'references_masks')


def refine(rgb, net):
    m = net > 128
    m = ndi.binary_opening(m, iterations=1)
    lab, n = ndi.label(m)
    if n > 1:  # drop specks (the cubes touch the head, the wordmark is cut later)
        sizes = ndi.sum(m, lab, range(1, n + 1))
        m = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > 1500])
    return ndi.binary_fill_holes(m)


def main(names=None):
    from rembg import new_session, remove
    os.makedirs(OUT, exist_ok=True)
    sess = new_session('birefnet-general-lite')
    refs = sorted(f for f in os.listdir(os.path.join(ROOT, 'references')) if f.endswith('.png'))
    for f in refs:
        if names and not any(f.startswith(n) for n in names):
            continue
        im = Image.open(os.path.join(ROOT, 'references', f)).convert('RGB')
        net = np.asarray(remove(im, session=sess, only_mask=True))
        m = refine(np.asarray(im), net)
        Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(OUT, f))
        print('[mask]', f, round(float(m.mean()), 4))


if __name__ == '__main__':
    main(sys.argv[1:] or None)
