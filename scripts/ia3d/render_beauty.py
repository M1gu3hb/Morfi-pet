"""Beauty stills of an action in the studio (quality check of materials and poses).

blender -b work/ia3d/morfi_ia_look.blend --python scripts/ia3d/render_beauty.py -- \
    --action Wave --frames 0,40 --out work/ia3d/beauty [--engine cycles] [--az -25] [--samples 96]
"""
import argparse
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import studio  # noqa: E402
from anim import rigmap  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default="cycles")
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--az", type=float, default=-22.0)
    ap.add_argument("--dist", type=float, default=2.6)
    ap.add_argument("--height", type=float, default=0.75)
    ap.add_argument("--target", default="0,0,0.55")
    ap.add_argument("--lens", type=float, default=50)
    ap.add_argument("--res", default="1080,1350")
    ap.add_argument("--percent", type=int, default=60)
    ap.add_argument("--tag", default="")
    args = ap.parse_args(argv)
    sc = bpy.context.scene
    res = tuple(int(v) for v in args.res.split(","))
    cam, _ = studio.setup(sc, args.engine, args.samples, res, args.percent)
    tgt = tuple(float(v) for v in args.target.split(","))
    studio.frame_camera(cam, args.az, args.dist, args.height, tgt, args.lens)
    rig = bpy.data.objects["Morfi_Rig"]
    rigmap.assign(rig, bpy.data.actions[args.action])
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    for f in (int(v) for v in args.frames.split(",")):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(out, f"{args.action}{args.tag}_{args.engine}_{f:03d}.png")
        bpy.ops.render.render(write_still=True)
    print("DONE")


main()
