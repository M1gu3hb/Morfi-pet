"""Per-vertex colour of the AI mesh, a first material segmentation and a slice profile.

python scripts/ia3d/analyze_regions.py --mesh work/ia3d/mesh.npz --tex work/ia3d/tex/glb1_1_Image_0.jpg \
    --out work/ia3d/regions

Writes regions.npz (vertex colour, label), label previews (front / side point plots)
and a text profile of width/depth per height, used to place the joints.
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

# sRGB prototypes measured on the references (docs/art-direction.md §5)
PROTOS = {
    "skin": (1, 78, 240),
    "face": (137, 186, 249),
    "hoodie": (28, 29, 33),
    "shirt": (226, 223, 223),
    "shoe": (240, 240, 237),
    "metal": (190, 194, 200),
    "mouth": (90, 30, 30),
}
COLORS = {"skin": (20, 80, 240), "face": (140, 190, 250), "hoodie": (30, 30, 30), "shirt": (200, 200, 200),
          "shoe": (250, 250, 250), "metal": (240, 160, 0), "mouth": (200, 40, 40)}


def srgb_to_lab(rgb):
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def vertex_colours(mesh, tex):
    img = np.asarray(Image.open(tex).convert("RGB"))
    h, w = img.shape[:2]
    uv = mesh["loop_uv"].reshape(-1, 2)
    x = np.clip((uv[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(int)
    y = np.clip((1 - uv[:, 1] % 1.0) * (h - 1), 0, h - 1).astype(int)
    col = img[y, x].astype(np.float64)
    vid = mesh["faces"].reshape(-1)
    n = len(mesh["verts"])
    acc = np.zeros((n, 3))
    cnt = np.zeros(n)
    np.add.at(acc, vid, col)
    np.add.at(cnt, vid, 1)
    return acc / np.maximum(cnt, 1)[:, None]


def plot(points, colours, axes, size=900, flip_x=False):
    a, b = axes
    P = points[:, [a, b]]
    lo, hi = P.min(0), P.max(0)
    s = (size - 20) / (hi - lo).max()
    img = np.full((size, size, 3), 255, np.uint8)
    u = ((P[:, 0] - lo[0]) * s + 10).astype(int)
    if flip_x:
        u = size - 1 - u
    v = (size - 10 - (P[:, 1] - lo[1]) * s).astype(int)
    img[np.clip(v, 0, size - 1), np.clip(u, 0, size - 1)] = colours
    return Image.fromarray(img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--tex", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    mesh = dict(np.load(args.mesh))
    V = mesh["verts"]
    col = vertex_colours(mesh, args.tex)
    lab = srgb_to_lab(col)
    names = list(PROTOS)
    plab = srgb_to_lab(np.array([PROTOS[k] for k in names], float))
    d = np.linalg.norm(lab[:, None, :] - plab[None], axis=2)
    label = d.argmin(1)
    np.savez_compressed(os.path.join(args.out, "regions.npz"), colour=col, label=label, names=np.array(names))
    pal = np.array([COLORS[k] for k in names], np.uint8)
    front = plot(V, pal[label], (0, 2), flip_x=False)
    side = plot(V, pal[label], (1, 2), flip_x=True)
    true_front = plot(V, col.astype(np.uint8), (0, 2))
    sheet = Image.new("RGB", (2700, 900), "white")
    for i, im in enumerate((true_front, front, side)):
        sheet.paste(im, (i * 900, 0))
    sheet.save(os.path.join(args.out, "labels.png"))

    counts = {k: int((label == i).sum()) for i, k in enumerate(names)}
    # slice profile: width (x) and depth (y) of each label per height band
    prof = []
    for z0 in np.arange(0.0, 1.15, 0.02):
        sel = (V[:, 2] >= z0) & (V[:, 2] < z0 + 0.02)
        row = {"z": round(float(z0), 2), "n": int(sel.sum())}
        if sel.any():
            row["x"] = [round(float(V[sel, 0].min()), 3), round(float(V[sel, 0].max()), 3)]
            row["y"] = [round(float(V[sel, 1].min()), 3), round(float(V[sel, 1].max()), 3)]
            row["labels"] = {k: int((label[sel] == i).sum()) for i, k in enumerate(names) if (label[sel] == i).any()}
        prof.append(row)
    with open(os.path.join(args.out, "profile.json"), "w", encoding="utf-8") as fh:
        json.dump({"counts": counts, "profile": prof}, fh, indent=1)
    print(json.dumps(counts))
    for r in prof:
        print(r)


if __name__ == "__main__":
    main()
