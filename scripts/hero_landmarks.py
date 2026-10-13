"""Measure the head of the hero shot: lens centres, head outline, in pixels.

    python3 scripts/hero_landmarks.py references/00_Morfi_master_wordmark.png renders/hero_wordmark.png

The lens centres are the two largest holes of the dark glasses frame; the head
outline is the blue head region (left / right of the skin only, since the
temples stick out; top taken under the cubes). Used to set config
"hero_pose" (head turn / tilt / nod and spine lean): the hero pose was tuned
until the lenses of the render fall on those of the master image 00, and only
then were the pupils fitted (scripts/fit_gaze.py --views hero).
"""
import json, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
W, H = 1145, 1374
def measure(path):
    a = np.asarray(Image.open(path).convert('RGB').resize((W, H), Image.LANCZOS)).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = a.mean(-1)
    top = np.zeros((H, W), bool); top[:int(H * 0.56)] = True
    dark = (lum < 75) & (b >= r) & top
    lab, n = ndi.label(dark); s = ndi.sum(dark, lab, range(1, n + 1))
    frame = lab == np.argmax(s) + 1
    holes = ndi.binary_fill_holes(frame) & ~frame
    hl, hn = ndi.label(holes); hs = ndi.sum(holes, hl, range(1, hn + 1))
    lens = []
    for i in np.argsort(hs)[::-1][:2]:
        ys, xs = np.nonzero(hl == i + 1); lens.append((xs.mean(), ys.mean()))
    lens.sort()
    blue = (b > 120) & (b - r > 50) & top
    blue = ndi.binary_fill_holes(blue | frame | holes)
    lab, n = ndi.label(blue); s = ndi.sum(blue, lab, range(1, n + 1)); hm = lab == np.argmax(s) + 1
    rows = hm.sum(1); maxw = rows.max()
    yt = np.nonzero(rows > 0.6 * maxw)[0].min()   # head top under the cubes
    ys, xs = np.nonzero(hm)
    # left/right extents of the skin only (the glasses temples stick out)
    sk = hm & ~ndi.binary_dilation(frame, iterations=2)
    ys2, xs2 = np.nonzero(sk[yt:])
    return dict(lens=[list(map(float, l)) for l in lens], top=float(yt), bottom=float(ys.max()),
                left=float(xs2.min()), right=float(xs2.max()))
if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(p, json.dumps(measure(p)))
