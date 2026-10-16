"""Contact sheet of the AI models next to the references, with silhouette IoU.

python scripts/ia3d/make_contact_sheet.py --dir work/ia3d/contact --models glb1,esq,obj1 \
    --labels "GLB sin esqueleto,GLB con esqueleto,OBJ" --hoodie sudadera --out work/ia3d/hoja_contacto.jpg

IoU "cámara" = render with the calibrated camera of the view vs the reference mask.
IoU "alineado" = same, after matching the silhouettes' height and foot point
(removes framing differences between the independent AI renders).
"""
import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REFS = {
    "front": "02_Morfi_frente",
    "profile_left": "03_Morfi_perfil_izquierdo",
    "back": "04_Morfi_espalda",
    "profile_right": "05_Morfi_perfil_derecho",
    "three_quarter_front": "06_Morfi_tres_cuartos_frontal",
    "three_quarter_back": "07_Morfi_tres_cuartos_posterior",
}
TITLES = {"front": "Frente", "profile_left": "Perfil izq.", "back": "Espalda",
          "profile_right": "Perfil der.", "three_quarter_front": "3/4 frente",
          "three_quarter_back": "3/4 espalda"}
BG = (253, 253, 249)


def font(size):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def iou(a, b):
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def bbox(mask):
    ys, xs = np.nonzero(mask)
    return xs.min(), xs.max(), ys.min(), ys.max()


def aligned(render, ref):
    """Scale/translate the render mask so its height and bottom-centre match the reference."""
    rx0, rx1, ry0, ry1 = bbox(render)
    fx0, fx1, fy0, fy1 = bbox(ref)
    s = (fy1 - fy0) / max(ry1 - ry0, 1)
    im = Image.fromarray(render.astype(np.uint8) * 255)
    w, h = im.size
    im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.BILINEAR)
    out = Image.new("L", (w, h), 0)
    # bottom-centre of the render bbox -> bottom-centre of the reference bbox
    cx_r, by_r = (rx0 + rx1) / 2 * s, ry1 * s
    cx_f, by_f = (fx0 + fx1) / 2, fy1
    out.paste(im, (round(cx_f - cx_r), round(by_f - by_r)))
    return np.asarray(out) > 127


def on_bg(path):
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, BG + (255,))
    bg.alpha_composite(im)
    return bg.convert("RGB"), np.asarray(im)[..., 3] > 127


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--views", default="front,profile_left,back,three_quarter_front")
    ap.add_argument("--hoodie", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=0.32)
    args = ap.parse_args()

    views = args.views.split(",")
    models = args.models.split(",")
    labels = args.labels.split(",")
    tw, th = int(1145 * args.scale), int(1374 * args.scale)
    label_w, head_h = 230, 46
    rows = 1 + len(models) + (1 if args.hoodie else 0)
    sheet = Image.new("RGB", (label_w + tw * len(views), head_h + th * rows), BG)
    draw = ImageDraw.Draw(sheet)
    f_big, f_small = font(26), font(19)
    metrics = {}

    for j, v in enumerate(views):
        draw.text((label_w + j * tw + 12, 10), TITLES[v], fill=(30, 30, 30), font=f_big)
        ref = Image.open(os.path.join(ROOT, "references", REFS[v] + ".png")).convert("RGB")
        sheet.paste(ref.resize((tw, th), Image.LANCZOS), (label_w + j * tw, head_h))
    draw.text((14, head_h + th // 2 - 14), "Referencia", fill=(30, 30, 30), font=f_big)

    for i, (m, lab) in enumerate(zip(models, labels)):
        y = head_h + th * (i + 1)
        draw.text((14, y + th // 2 - 30), lab, fill=(30, 30, 30), font=f_big)
        metrics[m] = {}
        for j, v in enumerate(views):
            path = os.path.join(args.dir, f"{m}_{v}.png")
            if not os.path.exists(path):
                continue
            rgb, mask = on_bg(path)
            ref_mask = np.asarray(Image.open(os.path.join(ROOT, "references_masks", REFS[v] + ".png"))) > 127
            a, b = iou(mask, ref_mask), iou(aligned(mask, ref_mask), ref_mask)
            metrics[m][v] = {"iou_camera": round(a, 3), "iou_aligned": round(b, 3)}
            x = label_w + j * tw
            sheet.paste(rgb.resize((tw, th), Image.LANCZOS), (x, y))
            draw.text((x + 10, y + th - 30), f"IoU {a:.3f} · alineado {b:.3f}", fill=(60, 60, 60), font=f_small)

    if args.hoodie:
        y = head_h + th * (1 + len(models))
        draw.text((14, y + th // 2 - 30), "Sudadera\nsuelta", fill=(30, 30, 30), font=f_big)
        ref = Image.open(os.path.join(ROOT, "references", "08_Morfi_sudadera.png")).convert("RGB")
        for j, v in enumerate(views):
            path = os.path.join(args.dir, f"{args.hoodie}_{v}.png")
            if os.path.exists(path):
                rgb, _ = on_bg(path)
                sheet.paste(rgb.resize((tw, th), Image.LANCZOS), (label_w + j * tw, y))
        # the hoodie sheet reference, small, in the label column
        sheet.paste(ref.resize((label_w - 20, int((label_w - 20) * ref.height / ref.width))), (10, y + 70))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sheet.save(args.out, quality=88)
    with open(os.path.splitext(args.out)[0] + "_metrics.json", "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=1)
    print(json.dumps(metrics, indent=1))


if __name__ == "__main__":
    main()
