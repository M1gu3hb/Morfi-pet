"""Encode the showcase frames into an MP4 with a title and a caption per action.

python scripts/ia3d/encode_showcase.py --dir work/ia3d/showcase --out renders/ia3d/morfi_showcase.mp4 [--step 1]
"""
import argparse
import json
import os
import subprocess

FONT = "C\\:/Windows/Fonts/segoeuib.ttf"
FONT_LIGHT = "C\\:/Windows/Fonts/segoeui.ttf"


def esc(path):
    return path.replace("\\", "/").replace(":", "\\:")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--title", default="Morfi · Morphiq")
    args = ap.parse_args()
    meta = json.load(open(os.path.join(args.dir, "showcase.json"), encoding="utf-8"))
    fps = meta["fps"]
    txt_dir = os.path.join(args.dir, "captions")
    os.makedirs(txt_dir, exist_ok=True)
    filters = []
    # captions: lower third, fade in/out, kept clear of the crossfades
    for i, seg in enumerate(meta["segments"]):
        if not seg["caption"]:
            continue
        t0 = (seg["start"] + 12) / fps
        t1 = (seg["end"] - 14) / fps
        path = os.path.join(txt_dir, f"c{i:02d}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(seg["caption"])
        alpha = f"if(lt(t,{t0}+0.3),(t-{t0})/0.3,if(gt(t,{t1}-0.3),({t1}-t)/0.3,1))"
        filters.append(
            f"drawtext=fontfile='{FONT}':textfile='{esc(path)}':fontsize=h/24:fontcolor=white:"
            f"x=w*0.05:y=h*0.86:box=1:boxcolor=0x0B1E5B@0.55:boxborderw=18:"
            f"alpha='{alpha}':enable='between(t,{t0},{t1})'")
    # title card over the first seconds
    tpath = os.path.join(txt_dir, "title.txt")
    with open(tpath, "w", encoding="utf-8") as fh:
        fh.write(args.title)
    filters.insert(0,
        f"drawtext=fontfile='{FONT}':textfile='{esc(tpath)}':fontsize=h/12:fontcolor=white:"
        f"x=(w-text_w)/2:y=h*0.08:shadowcolor=0x0B1E5B@0.6:shadowx=3:shadowy=3:"
        f"alpha='if(lt(t,0.4),t/0.4,if(gt(t,2.6),(3.2-t)/0.6,1))':enable='between(t,0,3.2)'")
    total = meta["frames"] / fps
    filters.append(f"fade=t=in:st=0:d=0.5,fade=t=out:st={total - 0.8:.2f}:d=0.8")
    vf = ",".join(filters)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps // args.step),
           "-start_number", "0", "-i", os.path.join(args.dir, "frames", "f_%05d.png"),
           "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", args.out]
    if args.step > 1:
        # frames were rendered every `step`: renumber through a glob-free concat list
        lst = os.path.join(args.dir, "frames_list.txt")
        names = sorted(f for f in os.listdir(os.path.join(args.dir, "frames")) if f.endswith(".png"))
        with open(lst, "w", encoding="utf-8") as fh:
            for n in names:
                fh.write(f"file 'frames/{n}'\nduration {args.step / fps}\n")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-vf", vf,
               "-r", str(fps), "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", args.out]
    subprocess.run(cmd, check=True)
    print("DONE", args.out)


if __name__ == "__main__":
    main()
