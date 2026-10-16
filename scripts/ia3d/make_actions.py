"""Bake Morfi's actions onto the rigged AI mesh.

blender -b work/ia3d/morfi_ia_rig.blend --python scripts/ia3d/make_actions.py -- \
    --out work/ia3d/morfi_ia_anim.blend [--only Idle,Wave]
"""
import argparse
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim import contacts, rigmap  # noqa: E402
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
        if any(k.startswith("ik.") for k in clip.ch):
            pulled = contacts.clamp_reach(rig, act, clip.n)  # no rubber arms
            if pulled:
                print(f"REACH {name}: {pulled} IK frames pulled back within {contacts.MAX_REACH:.2f}x arm length")
        has_props = getattr(clip, "contacts", None) or getattr(clip, "supports", None)
        if any(k.startswith("ik.") for k in clip.ch) and not has_props:
            pushed = contacts.resolve_body(rig, act, clip.n)  # the body is solid
            if pushed:
                print(f"BODY {name}: hands pushed out of the head / torso on {pushed} frame passes")
                contacts.clamp_reach(rig, act, clip.n)       # and still no rubber arm
        if has_props:
            contacts.solve(rig, act, clip)          # fingertips and palms onto the props
            ok, worst, _ = contacts.verify(rig, act, clip)
            print(f"CONTACTS {name}: ok={ok} overlap {worst['pen'] * 1000:.1f} mm, "
                  f"press gap {worst['press'] * 1000:.1f} mm, support gap {worst['support'] * 1000:.1f} mm")
        print(f"ACTION {name}: {clip.n} frames, loop={clip.loop}, channels={len(clip.ch)}")
    rigmap.assign(rig, bpy.data.actions[names[0]])
    bpy.context.scene.render.fps = 30
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("DONE", args.out)


main()
