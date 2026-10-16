"""Measure the painted face features on the flat ortho view (face_ortho.py).

python scripts/ia3d/measure_face.py --dir work/ia3d/face

Writes face_features.json (world units, project frame) with, per eye: the eye outline
ellipse (sclera + iris), iris and pupil circles, highlight spot, outline thickness and
colours; the lens openings (inside the frame) as polygons; mouth and brow boxes;
and a debug overlay face_features.png.
"""
import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi


def ellipse_fit(mask):
    ys, xs = np.nonzero(mask)
    cx, cy = xs.mean(), ys.mean()
    cov = np.cov(np.stack([xs - cx, ys - cy]))
    evals, evecs = np.linalg.eigh(cov)
    # for a filled ellipse, variance along an axis = r^2 / 4
    r = 2 * np.sqrt(evals)
    ang = float(np.degrees(np.arctan2(evecs[1, 1], evecs[0, 1])))
    return float(cx), float(cy), float(r[1]), float(r[0]), ang


def fit_circle(xs, ys):
    A = np.stack([xs, ys, np.ones_like(xs)], 1).astype(float)
    bvec = -(xs.astype(float) ** 2 + ys.astype(float) ** 2)
    D, E, F = np.linalg.lstsq(A, bvec, rcond=None)[0]
    cx, cy = -D / 2, -E / 2
    return float(cx), float(cy), float(np.sqrt(cx * cx + cy * cy - F))


def fit_ellipse(xs, ys):
    """Least-squares conic fit -> centre, semi-axes (a >= b) and angle of a (degrees)."""
    x, y = xs.astype(float), ys.astype(float)
    mx, my = x.mean(), y.mean()
    x, y = x - mx, y - my
    D = np.stack([x * x, x * y, y * y, x, y], 1)
    coef = np.linalg.lstsq(D, np.ones_like(x), rcond=None)[0]
    A, B, C, Dd, E = coef
    F = -1.0
    M = np.array([[A, B / 2], [B / 2, C]])
    c = np.linalg.solve(2 * M, [-Dd, -E])
    k = -(F + Dd * c[0] / 2 + E * c[1] / 2)
    evals, evecs = np.linalg.eigh(M / k)
    axes = 1 / np.sqrt(np.abs(evals))
    i = int(np.argmax(axes))
    ang = float(np.degrees(np.arctan2(evecs[1, i], evecs[0, i])))
    return float(c[0] + mx), float(c[1] + my), float(axes[i]), float(axes[1 - i]), ang


def largest(mask, k=1):
    lab, n = ndi.label(mask)
    if n == 0:
        return [np.zeros_like(mask)]
    sizes = ndi.sum(mask, lab, range(1, n + 1))
    order = np.argsort(-sizes)[:k]
    return [lab == (i + 1) for i in order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    meta = json.load(open(os.path.join(args.dir, "face_ortho.json")))
    im = np.asarray(Image.open(os.path.join(args.dir, "face_albedo.png")).convert("RGBA")).astype(float)
    rgb, alpha = im[..., :3], im[..., 3] > 127
    H, W = alpha.shape
    mpp, x0, z1 = meta["mpp"], meta["x0"], meta["z1"]
    to_w = lambda u, v: (x0 + u * mpp, z1 - v * mpp)  # noqa: E731
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = rgb.mean(-1)
    white = (lum > 215) & (np.abs(r - b) < 40) & alpha
    dark = (lum < 45) & alpha
    navy = (b > r + 25) & (lum < 70) & alpha          # frame and brows are very dark navy
    feats = {"meta": meta, "eyes": {}}
    overlay = Image.fromarray(np.uint8(np.where(alpha[..., None], rgb, 255)))
    dr = ImageDraw.Draw(overlay)

    for side, half in (("R", slice(0, W // 2)), ("L", slice(W // 2, W))):
        # Morfi's right eye is on the image left (camera looks at his face)
        sub = np.zeros_like(white)
        sub[:, half] = True
        sclera = largest(white & sub)[0]
        # eye outline: sclera boundary pixels next to the dark outline ring
        near_dark = ndi.binary_dilation(lum < 80, iterations=4)
        edge = sclera & ~ndi.binary_erosion(sclera, iterations=2) & near_dark
        bluish = (b > r + 60) & (lum < 150) & sub
        pupil = largest((lum < 30) & sub & ~ndi.binary_dilation(edge, iterations=12))[0]
        pcy, pcx = ndi.center_of_mass(pupil)
        pr = float(np.sqrt(pupil.sum() / np.pi))
        # iris: blue disc around the pupil; its visible boundary borders the sclera
        iris_zone = ndi.binary_dilation(pupil, iterations=int(pr * 0.9)) & (bluish | pupil)
        iris = largest(iris_zone | pupil)[0]
        ib = iris & ~ndi.binary_erosion(iris, iterations=2) & ndi.binary_dilation(sclera, iterations=3)
        ys, xs = np.nonzero(ib)
        icx, icy, ir = fit_circle(xs, ys)
        # the eye ellipse goes through the outline edge AND the iris arc that runs along it
        ys, xs = np.nonzero(edge)
        ecx, ecy, era, erb, eang = fit_ellipse(xs, ys)
        gy, gx = np.mgrid[0:H, 0:W]
        in_iris = np.hypot(gx - icx, gy - icy) < ir * 0.97
        pupil = largest((lum < 35) & in_iris)[0]
        pcy, pcx = ndi.center_of_mass(pupil)
        pr = float(np.sqrt(ndi.binary_fill_holes(pupil).sum() / np.pi))
        spots = []
        lab, n = ndi.label((lum > 200) & in_iris)
        for k in range(1, n + 1):
            m = lab == k
            if m.sum() > 40:
                cy_, cx_ = ndi.center_of_mass(m)
                spots.append((float(cx_), float(cy_), float(np.sqrt(m.sum() / np.pi))))
        ring = ndi.binary_dilation(sclera, iterations=14) & ~ndi.binary_fill_holes(sclera | iris) & (lum < 90)
        thick_top = ring[: int(ecy)].sum() / max(1.0, np.pi * era)
        thick_bot = ring[int(ecy):].sum() / max(1.0, np.pi * era)
        col = lambda m: [round(float(c)) for c in np.median(rgb[m], 0)] if m.any() else None  # noqa: E731
        iris_ring = iris & ~pupil
        iris_ring = in_iris & ~ndi.binary_fill_holes(pupil) & (lum < 200)
        inner = iris_ring & (np.hypot(gx - icx, gy - icy) < pr + (ir - pr) * 0.45)
        outer = iris_ring & ~inner
        ex, ez = to_w(ecx, ecy)
        ix, iz = to_w(icx, icy)
        px, pz = to_w(pcx, pcy)
        feats["eyes"][side] = {
            "center": [ex, ez], "radii": [era * mpp, erb * mpp], "angle_deg": eang,
            "iris_center": [ix, iz], "iris_r": ir * mpp,
            "pupil_center": [px, pz], "pupil_r": pr * mpp,
            "highlights": [[*to_w(sx, sy), sr * mpp] for sx, sy, sr in spots],
            "outline_top_m": thick_top * mpp, "outline_bottom_m": thick_bot * mpp,
            "colours": {"sclera": col(sclera), "iris_inner": col(inner), "iris_outer": col(outer),
                        "pupil": col(pupil), "outline": col(ring)},
        }
        t = np.linspace(0, 2 * np.pi, 200)
        ca, sa = np.cos(np.radians(eang)), np.sin(np.radians(eang))
        pts = [(ecx + era * np.cos(a) * ca - erb * np.sin(a) * sa, ecy + era * np.cos(a) * sa + erb * np.sin(a) * ca)
               for a in t]
        dr.line(pts + [pts[0]], fill=(255, 0, 0), width=3)
        dr.ellipse([icx - ir, icy - ir, icx + ir, icy + ir], outline=(0, 255, 0), width=3)
        dr.ellipse([pcx - pr, pcy - pr, pcx + pr, pcy + pr], outline=(255, 0, 255), width=3)
        for sx, sy, sr in spots:
            dr.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], outline=(255, 160, 0), width=3)

    # lens openings: non-frame regions enclosed by the frame
    frame = largest(navy, 1)[0]
    holes = ndi.binary_fill_holes(frame) & ~frame
    lenses = largest(holes, 2)
    feats["lenses"] = {}
    for m in lenses:
        cy, cx = ndi.center_of_mass(m)
        side = "R" if cx < W / 2 else "L"
        ys, xs = np.nonzero(m)
        feats["lenses"][side] = {
            "bbox": [*to_w(xs.min(), ys.max()), *to_w(xs.max(), ys.min())],
            "center": list(to_w(cx, cy)),
            "colour_median": [round(float(c)) for c in np.median(rgb[m & ~white & ~dark & ~navy], 0)],
        }
        Image.fromarray(np.uint8(m) * 255).save(os.path.join(args.dir, f"lens_{side}.png"))
        edge = m & ~ndi.binary_erosion(m, iterations=3)
        ov = np.asarray(overlay).copy()
        ov[edge] = (0, 200, 255)
        overlay = Image.fromarray(ov)
        dr = ImageDraw.Draw(overlay)
    # mouth: reddish dark region below the glasses
    mouth = largest((r > g + 40) & (r > b + 20) & alpha)[0]
    ys, xs = np.nonzero(mouth)
    feats["mouth"] = {"bbox": [*to_w(xs.min(), ys.max()), *to_w(xs.max(), ys.min())],
                      "center": list(to_w(xs.mean(), ys.mean())),
                      "colour": [round(float(c)) for c in np.median(rgb[mouth], 0)]}
    # brows: navy blobs above the frame
    top_frame = np.nonzero(frame.any(1))[0].min()
    brows = largest(navy & ~frame & (np.arange(H)[:, None] < top_frame), 2)
    feats["brows"] = {}
    for m in brows:
        ys, xs = np.nonzero(m)
        side = "R" if xs.mean() < W / 2 else "L"
        feats["brows"][side] = {"bbox": [*to_w(xs.min(), ys.max()), *to_w(xs.max(), ys.min())]}
    # skin colours around the eye (inside the lens, outside the eye outline)
    for side, L in feats["lenses"].items():
        m = np.asarray(Image.open(os.path.join(args.dir, f"lens_{side}.png"))) > 127
        e = feats["eyes"][side]
        skin = m & ~white & ~dark & ~navy & (lum > 90)
        L["skin_colour"] = [round(float(c)) for c in np.median(rgb[skin], 0)]
    overlay.save(os.path.join(args.dir, "face_features.png"))
    with open(os.path.join(args.dir, "face_features.json"), "w", encoding="utf-8") as fh:
        json.dump(feats, fh, indent=1)
    print(json.dumps(feats, indent=1))
    fit_outlines(args.dir)


def fit_outlines(face_dir):
    """Inner (white + clipped iris) and outer edge of each painted eye outline, as tilted
    ellipses (image angles) -> eye_outline.json, used by build_face.py and inpaint_face.py."""
    d = json.load(open(os.path.join(face_dir, "face_features.json")))
    m = d["meta"]
    img = np.asarray(Image.open(os.path.join(face_dir, "face_albedo.png")).convert("RGB")).astype(float)
    lum = img.mean(-1)
    H, W = lum.shape
    mpp = m["mpp"]
    w = lambda u, v: (m["x0"] + u * mpp, m["z1"] - v * mpp)  # noqa: E731
    gy, gx = np.mgrid[0:H, 0:W]
    res = {}
    for side, half in (("R", slice(0, W // 2)), ("L", slice(W // 2, W))):
        e = d["eyes"][side]
        sub = np.zeros_like(lum, bool)
        sub[:, half] = True
        sclera = largest((lum > 215) & sub)[0]
        icx = (e["iris_center"][0] - m["x0"]) / mpp
        icy = (m["z1"] - e["iris_center"][1]) / mpp
        iris = np.hypot(gx - icx, gy - icy) < e["iris_r"] / mpp
        eye = ndi.binary_fill_holes(sclera | (iris & ndi.binary_dilation(sclera, iterations=60)))
        eye = ndi.binary_opening(eye, iterations=3)
        ring = largest((lum < 95) & ndi.binary_dilation(eye, iterations=40) & ~eye)[0]
        full = ndi.binary_fill_holes(ring | eye)
        out = {}
        for key, region in (("outer", full), ("inner", eye)):
            ys, xs = np.nonzero(region & ~ndi.binary_erosion(region, iterations=2))
            cx, cy, a, b, ang = fit_ellipse(xs, ys)
            out[key] = {"center": list(w(cx, cy)), "radii": [a * mpp, b * mpp], "angle": ang}
        res[side] = out
    with open(os.path.join(face_dir, "eye_outline.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    return res


if __name__ == "__main__":
    main()
