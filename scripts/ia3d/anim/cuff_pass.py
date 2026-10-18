"""Keep the hand out of the cuff: where a bent wrist pushes the palm, thumb or fingers behind the
hoodie cuff (check_sleeves.py `cross_*`), the wrist bend is eased until the hand sits in the cuff
opening again (the twist about the forearm is kept: the palm still faces where the clip wants it).

Needs the materials of the look file (the Hoodie / Skin faces tell the sleeve from the skin), so it
runs on a look .blend with the baked actions read from another file and writes the corrected
actions to a third one; make_actions.py --merge puts them into the final file:

blender -b work/ia3d/morfi_ia_look5.blend --python scripts/ia3d/anim/cuff_pass.py -- \
    --from parts/a.blend --out parts/a_cuff.blend [--action Wave,Talk]

Frames that belong to a contact (touches, palm supports) are left alone: the contact solvers placed
that hand on purpose.
"""
import argparse
import os
import sys

import bpy
import numpy as np
from mathutils import Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from anim import contacts, rigmap  # noqa: E402
from anim.actions import ACTIONS  # noqa: E402
from check_sleeves import Side, evaluated  # noqa: E402

TOL = 0.010                       # a visible hand vertex may sit at most 10 mm behind the cuff plane (a hand
                                  # hanging at rest sits 4-5 mm behind it, and even a straight wrist keeps ~9 mm
                                  # when the palm is turned a lot)
# (share of the wrist bend kept, hand pushed out along the forearm in m), cheapest change first:
# the hand stretches out of the cuff a little ("que se estire un poquito la mano") and, if that is not
# enough, the wrist bends less
TRIES = ((1.0, 0.004), (1.0, 0.008), (0.8, 0.006), (0.65, 0.010), (0.5, 0.012), (0.35, 0.012))
CROSS = ("cross_thumb", "cross_fingers", "cross_palm")


def _swing_scaled(q, k):
    """Local rotation q (w, x, y, z; bone axis = local Y) = swing * twist: keep the twist, scale the swing."""
    q = Quaternion(q)
    tw = Quaternion((q.w, 0.0, q.y, 0.0))
    if tw.magnitude < 1e-9:
        tw = Quaternion((1.0, 0.0, 0.0, 0.0))
    tw.normalize()
    swing = q @ tw.inverted()
    if swing.w < 0:
        swing.negate()
    return Quaternion().slerp(swing, k) @ tw


def _worst(sd, body):
    P = evaluated(body)[0]
    r = sd.measure(P, evaluated(sd.hand)[0])
    return max(r[c] for c in CROSS)


def _skip_frames(clip, n):
    """Frames per side that a contact owns (the whole clip when a prop sits in the hand)."""
    out = {"L": set(), "R": set()}
    if getattr(clip, "supports", None):
        return {"L": set(range(n)), "R": set(range(n))}
    for spec in list(getattr(clip, "contacts", None) or []):
        a, b = spec["frames"]
        pad = max(int(spec.get("ramp", 0)), 6) + 4
        out[spec["side"]] |= set(range(max(0, a - pad), min(n, b + pad + 1)))
    return out


def _smooth(need, skip, n, loop, base, worse):
    """Per-frame value from the frames that asked for one: the worst ask over +-4 frames (`worse` is min or
    max), then blurred so the change eases in and out; frames of a contact keep `base`."""
    k = np.full(n, float(base))
    for f, v in need.items():
        k[f] = v
    pad = np.concatenate([k[-6:], k, k[:6]]) if loop else np.pad(k, 6, mode="edge")
    low = np.array([worse(pad[i:i + 9]) for i in range(n)])
    pad = np.concatenate([low[-6:], low, low[:6]]) if loop else np.pad(low, 6, mode="edge")
    k = np.array([pad[i + 3:i + 10].mean() for i in range(n)])
    for f in skip:
        k[f] = base
    return k


def relieve(rig, body, sides, name, step=1):
    act = bpy.data.actions[name]
    clip = ACTIONS[name]()
    n = int(act.frame_end) + 1                     # actions start at frame 0; a loop has its closing frame
    loop = bool(act.get("loop", 0))
    skip = _skip_frames(clip, n)
    rigmap.assign(rig, act)
    report = {}
    for s, sd in sides.items():
        pb = rig.pose.bones[f"hand.{s}"]
        fcs = contacts._curves(act, f"hand.{s}", "rotation_quaternion", 4, n, (1.0, 0.0, 0.0, 0.0))
        q0 = np.array([[fc.evaluate(f) for fc in fcs] for f in range(n)])
        loc = contacts._curves(act, f"hand.{s}", "location", 3, n, (0.0, 0.0, 0.0))
        l0 = np.array([[fc.evaluate(f) for fc in loc] for f in range(n)])
        need, before = {}, 0.0

        def pose(k, d, f):
            pb.rotation_quaternion = _swing_scaled(q0[f], k)
            pb.location = (l0[f, 0], l0[f, 1] + d, l0[f, 2])
            bpy.context.view_layer.update()

        for f in range(0, n, step):
            if f in skip[s]:
                continue
            bpy.context.scene.frame_set(f)
            w0 = _worst(sd, body)
            before = max(before, w0)
            if w0 <= TOL:
                continue
            best = (w0, (1.0, 0.0))
            for k, d in TRIES:
                pose(k, d, f)
                w = _worst(sd, body)
                if w < best[0]:
                    best = (w, (k, d))
                if w <= TOL:
                    break
            if best[0] > TOL and os.environ.get("CUFF_DEBUG"):
                print(f"  {name} {s} f{f}: {w0 * 1000:.1f} mm, best {best[0] * 1000:.1f} with {best[1]}", flush=True)
            need[f] = best[1]
            pose(1.0, 0.0, f)
            pb.rotation_quaternion = Quaternion(q0[f])
            pb.location = tuple(l0[f])
        if not need:
            report[s] = (0, before, before)
            continue
        kf = _smooth({f: v[0] for f, v in need.items()}, skip[s], n, loop, 1.0, np.min)
        df = _smooth({f: v[1] for f, v in need.items()}, skip[s], n, loop, 0.0, np.max)
        q1 = q0.copy()
        for f in range(n):
            if kf[f] < 0.999:
                q = _swing_scaled(q0[f], float(np.clip(kf[f], 0, 1)))
                q1[f] = q[:] if Quaternion(q0[f]).dot(q) >= 0 else (-q)[:]
        for i, fc in enumerate(fcs):
            for f in range(n):
                fc.keyframe_points[f].co[1] = q1[f, i]
            fc.update()
        for f in range(n):
            loc[1].keyframe_points[f].co[1] = l0[f, 1] + df[f]
        loc[1].update()
        # measure again on the corrected action
        after = 0.0
        for f in range(0, n, step):
            if f in skip[s]:
                continue
            bpy.context.scene.frame_set(f)
            after = max(after, _worst(sd, body))
        report[s] = (len(need), before, after)
    return report


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--action", default="")
    ap.add_argument("--step", type=int, default=1)
    a = ap.parse_args(argv)
    with bpy.data.libraries.load(os.path.abspath(a.src), link=False) as (src, dst):
        dst.actions = [x for x in src.actions if x in ACTIONS and (not a.action or x in a.action.split(","))]
    names = []
    for act in dst.actions:
        name = act.name.rsplit(".", 1)[0]
        old = bpy.data.actions.get(name)
        if old is not None and old != act:
            bpy.data.actions.remove(old)
        act.name = name
        act.use_fake_user = True
        names.append(name)
    rig, body = bpy.data.objects["Morfi_Rig"], bpy.data.objects["Morfi_Body"]
    sides = {s: Side(body, rig, bpy.data.objects[f"Hand_{s}"], s, 4) for s in ("L", "R")}
    rig.animation_data_create()
    rig.animation_data.action = None
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    P = evaluated(body)[0]
    for s, sd in sides.items():
        sd.snapshot((P, evaluated(sd.hand)[0]))
    rig.data.pose_position = "POSE"
    for name in names:
        rep = relieve(rig, body, sides, name, a.step)
        print("CUFF " + name + ": " + ", ".join(
            f"{s} {v[0]} frames, worst {v[1] * 1000:.1f} -> {v[2] * 1000:.1f} mm" for s, v in rep.items()), flush=True)
    rig.animation_data.action = None
    bpy.data.libraries.write(os.path.abspath(a.out), {bpy.data.actions[n] for n in names}, fake_user=True)
    print("DONE", a.out, len(names), "actions")


main()
