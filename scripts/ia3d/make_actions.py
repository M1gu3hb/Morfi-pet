"""Bake Morfi's actions onto the rigged AI mesh.

blender -b work/ia3d/morfi_ia_rig.blend --python scripts/ia3d/make_actions.py -- \
    --out work/ia3d/morfi_ia_anim.blend [--only Idle,Wave]
"""
import argparse
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim import rigmap  # noqa: E402
from anim.actions import ACTIONS  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    args = ap.parse_args(argv)
    rig = bpy.data.objects["Morfi_Rig"]
    rigmap.ensure_props(rig)
    names = [n for n in ACTIONS if not args.only or n in args.only.split(",")]
    for name in names:
        clip = ACTIONS[name]()
        act = rigmap.bake(rig, name, clip.channels(), clip.n, loop=clip.loop)
        if hasattr(clip, "stride"):
            act["stride"] = clip.stride
        print(f"ACTION {name}: {clip.n} frames, loop={clip.loop}, channels={len(clip.ch)}")
    rigmap.assign(rig, bpy.data.actions[names[0]])
    bpy.context.scene.render.fps = 30
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("DONE", args.out)


main()
