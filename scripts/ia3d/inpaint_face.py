"""Erase the painted eyes and mouth from the AI texture (the decals redraw them, animated).

python scripts/ia3d/inpaint_face.py --mesh work/ia3d/mesh.npz --tex work/ia3d/tex/glb1_1_Image_0.jpg \
    --face work/ia3d/face --out work/ia3d/tex/base_color_clean.jpg

The texture atlas is cut in hundreds of islands, so inpainting it directly would bleed
unrelated islands into the face. Instead the face is inpainted on the flat front view
(face_ortho.py, continuous), and every texel of the atlas whose surface point falls in
the erased area takes the inpainted front-view colour back (UV rasterisation of the
front-facing face triangles).
"""
import argparse
import json
import os

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def ellipse_mask(shape, meta, e, grow):
    H, W = shape
    gy, gx = np.mgrid[0:H, 0:W]
    x = meta["x0"] + gx * meta["mpp"]
    z = meta["z1"] - gy * meta["mpp"]
    cx, cz = e["center"]
    a, b = e["radii"][0] + grow, e["radii"][1] + grow
    t = np.radians(-e["angle"])
    xr = (x - cx) * np.cos(t) + (z - cz) * np.sin(t)
    zr = (z - cz) * np.cos(t) - (x - cx) * np.sin(t)
    return (xr / a) ** 2 + (zr / b) ** 2 < 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--tex", required=True)
    ap.add_argument("--face", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    meta = json.load(open(os.path.join(args.face, "face_ortho.json")))
    outline = json.load(open(os.path.join(args.face, "eye_outline.json")))
    ortho = np.asarray(Image.open(os.path.join(args.face, "face_albedo.png")).convert("RGB"))
    H, W = ortho.shape[:2]
    mpp = meta["mpp"]

    # 1. what to erase, on the front view: both painted eyes (outer outline + 2.5 mm) and the mouth.
    # Each hole is filled with a smooth quadratic fitted to the skin around it (inside the lens
    # the skin is an even celeste; Telea inpainting dragged the black frame into the holes).
    rgb = ortho.astype(float)
    lum = rgb.mean(-1)
    skinlike = (lum > 95) & (lum < 215) & (rgb[..., 2] > rgb[..., 0] + 60)
    regions = [ellipse_mask((H, W), meta, outline[s]["outer"], 0.0025) for s in ("R", "L")]
    red = (rgb[..., 0] > rgb[..., 1] + 25) & (rgb[..., 0] > rgb[..., 2] - 20)
    n, lab = cv2.connectedComponents(red.astype(np.uint8))
    sizes = np.bincount(lab.ravel())[1:]
    mouth = lab == (1 + int(np.argmax(sizes)))
    mouth = cv2.dilate(mouth.astype(np.uint8), np.ones((5, 5), np.uint8), iterations=6) > 0
    regions.append(mouth)
    clean = rgb.copy()
    mask = np.zeros((H, W), bool)
    gy, gx = np.mgrid[0:H, 0:W]
    bright = skinlike & (lum > 140)        # lens celeste, not the darker glass-rim lines
    for k, m in enumerate(regions):
        ring = (cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8), iterations=12) > 0) & ~m
        ring &= bright if k < 2 else skinlike
        xs, ys = gx[ring] / W, gy[ring] / H
        A = np.stack([np.ones_like(xs), xs, ys, xs * xs, xs * ys, ys * ys], 1)
        coef = np.linalg.lstsq(A, rgb[ring], rcond=None)[0]
        mx, my = gx[m] / W, gy[m] / H
        Am = np.stack([np.ones_like(mx), mx, my, mx * mx, mx * my, my * my], 1)
        clean[m] = Am @ coef
        mask |= m
    # feather the borders so the fill melts into the original
    soft = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 2.5)[..., None]
    clean = rgb * (1 - soft) + clean * soft
    # a whisper of the original grain so the fill is not plastic-flat
    grain = rgb - cv2.GaussianBlur(rgb, (0, 0), 6)
    clean = np.clip(clean + grain * 0.0 + np.random.default_rng(1).normal(0, 1.2, clean.shape) * soft, 0, 255)
    clean = clean.astype(np.uint8)
    mask = soft[..., 0] > 0.02
    Image.fromarray(clean).save(os.path.join(args.face, "face_albedo_clean.png"))
    Image.fromarray((mask * 255).astype(np.uint8)).save(os.path.join(args.face, "face_erase_mask.png"))

    # 2. push the inpainted colours back into the atlas
    mesh = np.load(args.mesh)
    V, F, LUV = mesh["verts"], mesh["faces"], mesh["loop_uv"]
    tex = np.array(Image.open(args.tex).convert("RGB"))
    th, tw = tex.shape[:2]
    P = V[F]                                              # (F,3,3)
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    cen = P.mean(1)
    box = (cen[:, 2] > meta["z1"] - H * mpp) & (cen[:, 2] < meta["z1"]) & \
          (cen[:, 0] > meta["x0"]) & (cen[:, 0] < meta["x0"] + W * mpp) & (n[:, 1] < 0) & (cen[:, 1] < -0.05)
    # keep faces that touch the erase mask
    u = ((P[..., 0] - meta["x0"]) / mpp).round().astype(int).clip(0, W - 1)
    v = ((meta["z1"] - P[..., 2]) / mpp).round().astype(int).clip(0, H - 1)
    grow = cv2.dilate(mask.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
    hit = box & grow[v, u].any(1)
    changed = 0
    for fi in np.nonzero(hit)[0]:
        uv = LUV[fi] * [tw, th]
        uv[:, 1] = th - uv[:, 1]
        x0, y0 = np.floor(uv.min(0)).astype(int)
        x1, y1 = np.ceil(uv.max(0)).astype(int)
        if x1 - x0 > 600 or y1 - y0 > 600:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        pts = np.stack([gx.ravel() + 0.5, gy.ravel() + 0.5], 1)
        a, b, c = uv
        T = np.array([[b[0] - a[0], c[0] - a[0]], [b[1] - a[1], c[1] - a[1]]])
        if abs(np.linalg.det(T)) < 1e-9:
            continue
        l12 = np.linalg.solve(T, (pts - a).T).T
        l0 = 1 - l12.sum(1)
        inside = (l0 >= -0.02) & (l12[:, 0] >= -0.02) & (l12[:, 1] >= -0.02)
        if not inside.any():
            continue
        bary = np.stack([l0, l12[:, 0], l12[:, 1]], 1)[inside]
        X = bary @ P[fi]
        pu = ((X[:, 0] - meta["x0"]) / mpp).round().astype(int).clip(0, W - 1)
        pv = ((meta["z1"] - X[:, 2]) / mpp).round().astype(int).clip(0, H - 1)
        sel = mask[pv, pu]
        if not sel.any():
            continue
        tx = gx.ravel()[inside][sel].clip(0, tw - 1)
        ty = gy.ravel()[inside][sel].clip(0, th - 1)
        tex[ty, tx] = clean[pv[sel], pu[sel]]
        changed += int(sel.sum())
    Image.fromarray(tex).save(args.out, quality=95)
    print("DONE", args.out, "texels changed", changed, "faces", int(hit.sum()))


if __name__ == "__main__":
    main()
