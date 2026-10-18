"""Bake Morfi's actions onto the rigged AI mesh.

blender -b work/ia3d/morfi_ia_face3.blend --python scripts/ia3d/make_actions.py -- \
    --out work/ia3d/morfi_ia_anim4.blend [--only Idle,Wave] [--merge a.blend,b.blend]

The input must already have the wrist fix (fix_wrists.py: the Wrist limit and the cuff weights),
so the contacts are solved on the rig that will play them. Per action: bake -> reach cap ->
hands out of the body -> contacts (presses, palm supports, touches on his own skin) -> verify.
The hands keep their own size while the IK solves (they do not inherit the IK stretch), and at
the end every arm is rebaked to FK with a stretch that keeps its volume (contacts.rebake_arms),
an arm whose hand rests on his face swivels its elbow out until the sleeve leaves the head
(contacts.clear_sleeves_fk), the touches and palm supports are closed again on the FK arm
(contacts.refine_contacts_fk: the Wrist limit clamps a hand that the longer, thinner arm turned
a little), the FK arms are kept out
of the head and torso (contacts.resolve_body_fk) and the contacts are verified again on the final
action.

The full bake is long (the touches are solved per frame): bake groups of actions in parallel
with --only into separate files, then build the final file with --merge (the actions of those
files are loaded as they are, nothing is baked again):
    ... make_actions.py -- --only Think,Laugh --out parts/a.blend      (one per group, in parallel)
    ... make_actions.py -- --merge parts/a.blend,parts/b.blend@Think --out work/ia3d/morfi_ia_anim4.blend
"""
import argparse
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim import contacts, rigmap  # noqa: E402
from anim.actions import ACTIONS  # noqa: E402


def _report(name, worst, ok, tag="CONTACTS"):
    print(f"{tag} {name}: ok={ok} overlap {max(worst['pen'], 0) * 1000:.1f} mm, "
          f"press gap {worst['press'] * 1000:.1f} mm, support gap {worst['support'] * 1000:.1f} mm, "
          f"body touch gap {worst['touch'] * 1000:.1f} mm", flush=True)


def bake_one(rig, name, clip):
    """Bake one clip and solve its reach and contacts on IK (hands at their own size)."""
    t = time.time()
    contacts.set_max_reach(getattr(clip, "max_reach", None))
    act = rigmap.bake(rig, name, clip.channels(), clip.n, loop=clip.loop)
    if hasattr(clip, "stride"):
        act["stride"] = clip.stride
    uses_ik = any(k.startswith("ik.") for k in clip.ch)
    if uses_ik:
        pulled = contacts.clamp_reach(rig, act, clip.n)  # no rubber arms
        if pulled:
            print(f"REACH {name}: {pulled} IK frames pulled back within {contacts._REACH['limit']:.2f}x arm length")
    has_props = getattr(clip, "contacts", None) or getattr(clip, "supports", None)
    if uses_ik and not getattr(clip, "supports", None):
        pushed = contacts.resolve_body(rig, act, clip.n)  # the body is solid
        if pushed:
            print(f"BODY {name}: hands pushed out of the head / torso on {pushed} frame passes")
            contacts.clamp_reach(rig, act, clip.n)       # and still no rubber arm
    if has_props:
        contacts.solve(rig, act, clip)          # fingertips and palms onto the props / his own body
        contacts.clamp_reach(rig, act, clip.n)   # the hover / release path too: no rubber arm
        ok, worst, _ = contacts.verify(rig, act, clip)
        _report(name, worst, ok, "CONTACTS(IK)")
    contacts.set_max_reach(None)
    print(f"ACTION {name}: {clip.n} frames, loop={clip.loop}, channels={len(clip.ch)}, {time.time() - t:.0f} s",
          flush=True)
    return act


def _skip(clip):
    """Frames whose hand belongs to a contact (and its approach), per arm: the FK body pass
    leaves them. A clip with a held prop is left alone entirely: its tapping hand travels over
    the prop on the IK path the press solver built, and turning that arm would put it into the
    prop."""
    if getattr(clip, "supports", None):
        return {"L": [(0, clip.n)], "R": [(0, clip.n)]}
    out = {"L": [], "R": []}
    for spec in list(getattr(clip, "contacts", None) or []) + list(getattr(clip, "supports", None) or []):
        a, b = spec["frames"]
        pad = max(int(spec.get("ramp", 0)), contacts.LEAD)
        out[spec["side"]].append((a - pad, b + pad))
    return out


def merge(files):
    """Load the actions baked into other files (parallel --only runs) into this one. A file may
    name the actions to take from it: parts/a.blend@Think+Laugh (later files win)."""
    for item in files:
        path, _, pick = item.partition("@")
        pick = set(pick.split("+")) if pick else set(ACTIONS)
        with bpy.data.libraries.load(os.path.abspath(path), link=False) as (src, dst):
            dst.actions = [a for a in src.actions if a in ACTIONS and a in pick]
        for act in dst.actions:
            name = act.name.rsplit(".", 1)[0] if act.name not in ACTIONS else act.name
            old = bpy.data.actions.get(name)
            if old is not None and old != act:
                bpy.data.actions.remove(old)
            act.name = name
            act.use_fake_user = True
            print(f"MERGED {name} from {os.path.basename(path)}", flush=True)
    missing = [n for n in ACTIONS if n not in bpy.data.actions]
    if missing:
        print("MISSING " + ",".join(missing), flush=True)
    return [n for n in ACTIONS if n in bpy.data.actions]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--merge", default="")
    args = ap.parse_args(argv)
    if os.path.abspath(args.out) == os.path.abspath(bpy.data.filepath):
        sys.exit("--out must differ from the input .blend")
    rig = bpy.data.objects["Morfi_Rig"]
    rigmap.ensure_props(rig)
    if args.merge:
        names = merge(args.merge.split(","))
        if not names:
            sys.exit("--merge: no actions to merge")
        rigmap.assign(rig, bpy.data.actions[names[0]])
        bpy.context.scene.render.fps = 30
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
        print("DONE", args.out, len(names), "actions")
        return
    names = [n for n in ACTIONS if not args.only or n in args.only.split(",")]
    if not names:
        sys.exit(f"--only: no known action in '{args.only}'")
    clips = {}
    with contacts.hands_keep_size(rig):
        for name in names:
            clips[name] = ACTIONS[name]()
            bake_one(rig, name, clips[name])
    # arms to FK with a volume-kept stretch, hands at their own size; then the final check
    for name in names:
        clip, act = clips[name], bpy.data.actions[name]
        st = contacts.rebake_arms(rig, act, clip.n)
        print(f"REBAKE {name}: " + ", ".join(f"{s} stretch {v['stretch']:.3f} wrist {v['wrist_mm']:.2f} mm "
                                             f"dir {v['dir_deg']:.2f} deg shear {v['shear_deg']:.1f} deg"
                                             for s, v in st.items()), flush=True)
        t = time.time()
        sw = contacts.clear_sleeves_fk(rig, act, clip)
        if sw:
            print(f"SLEEVES {name}: " + ", ".join(f"{s} {v[0]} frames, worst gap {v[1] * 1000:.1f} -> {v[2] * 1000:.1f} mm"
                                                  for s, v in sw.items()), flush=True)
        ref = contacts.refine_contacts_fk(rig, act, clip)
        if ref:
            print(f"REFINE {name}: " + ", ".join(f"{s} {v[0]} frames, worst gap {v[1] * 1000:.1f} -> {v[2] * 1000:.1f} mm"
                                                 for s, v in ref.items()), flush=True)
        fk = contacts.resolve_body_fk(rig, act, clip.n, loop=clip.loop, skip=_skip(clip))
        print(f"BODYFK {name}: " + ", ".join(f"{s} {v[0]} frames, worst gap {v[1] * 1000:.1f} -> {v[2] * 1000:.1f} mm"
                                             for s, v in fk.items()) + f", {time.time() - t:.0f} s", flush=True)
        if getattr(clip, "contacts", None) or getattr(clip, "supports", None):
            ok, worst, _ = contacts.verify(rig, act, clip)
            _report(name, worst, ok)
    rigmap.assign(rig, bpy.data.actions[names[0]])
    bpy.context.scene.render.fps = 30
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("DONE", args.out)


main()
