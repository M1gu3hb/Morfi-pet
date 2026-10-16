"""Tile frames of a preview into a grid with frame numbers (for reviewing motion).

python scripts/ia3d/make_strip.py work/ia3d/preview/Wave --every 6 --cols 9 --out work/ia3d/preview/Wave_strip.jpg
"""
import argparse
import glob
import os

from PIL import Image, ImageDraw, ImageFont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--every", type=int, default=6)
    ap.add_argument("--cols", type=int, default=9)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--crop", default="", help="x0,y0,x1,y1 fraction crop, e.g. 0.1,0,0.9,1")
    ap.add_argument("--frames", default="", help="explicit frame list, e.g. 0,10,20")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    files = sorted(glob.glob(os.path.join(args.folder, "f_*.png")))
    if args.frames:
        idx = [int(v) for v in args.frames.split(",")]
    else:
        idx = list(range(0, len(files), args.every))
    first = Image.open(files[0])
    W, H = first.size
    box = (0, 0, W, H)
    if args.crop:
        fx0, fy0, fx1, fy1 = (float(v) for v in args.crop.split(","))
        box = (int(fx0 * W), int(fy0 * H), int(fx1 * W), int(fy1 * H))
    tw, th = int((box[2] - box[0]) * args.scale), int((box[3] - box[1]) * args.scale)
    rows = (len(idx) + args.cols - 1) // args.cols
    sheet = Image.new("RGB", (tw * min(args.cols, len(idx)), th * rows), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for k, i in enumerate(idx):
        im = Image.open(files[i]).convert("RGB").crop(box).resize((tw, th), Image.LANCZOS)
        x, y = (k % args.cols) * tw, (k // args.cols) * th
        sheet.paste(im, (x, y))
        draw.text((x + 6, y + 4), str(i), fill=(200, 0, 0), font=font)
    sheet.save(args.out, quality=86)
    print(args.out, sheet.size)


if __name__ == "__main__":
    main()
