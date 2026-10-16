"""Review sheets of a rendered showcase: one row of evenly spaced frames per segment.

python scripts/ia3d/review_showcase.py --dir work/ia3d/showcase_draft --out work/ia3d/showcase_draft/review.jpg
"""
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per", type=int, default=8)
    ap.add_argument("--width", type=int, default=230)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    meta = json.load(open(os.path.join(args.dir, "showcase.json"), encoding="utf-8"))
    frames_dir = os.path.join(args.dir, "frames")
    have = sorted(int(f[2:7]) for f in os.listdir(frames_dir) if f.endswith(".png"))
    segs = [s for s in meta["segments"] if not args.only or s["action"] in args.only.split(",")]
    sample = Image.open(os.path.join(frames_dir, f"f_{have[0]:05d}.png"))
    tw = args.width
    th = int(tw * sample.height / sample.width)
    label_h = 22
    sheet = Image.new("RGB", (tw * args.per, (th + label_h) * len(segs)), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    for r, s in enumerate(segs):
        y = r * (th + label_h)
        draw.text((6, y + 3), f'{s["action"]}  {s["start"]}-{s["end"]}  {s["caption"]}', fill=(0, 0, 0), font=font)
        span = [f for f in have if s["start"] <= f < s["end"]]
        if not span:
            continue
        for k in range(args.per):
            f = span[min(len(span) - 1, round(k * (len(span) - 1) / max(1, args.per - 1)))]
            im = Image.open(os.path.join(frames_dir, f"f_{f:05d}.png")).convert("RGB").resize((tw, th))
            sheet.paste(im, (k * tw, y + label_h))
            draw.text((k * tw + 4, y + label_h + 2), str(f), fill=(220, 0, 0), font=font)
    sheet.save(args.out, quality=86)
    print(args.out, sheet.size)


if __name__ == "__main__":
    main()
