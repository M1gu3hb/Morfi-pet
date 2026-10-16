"""Search the wave arm pose: highest, most visible hand that stays clear of the head
through the whole wave swing.

blender -b work/ia3d/morfi_ia_anim.blend --python scripts/ia3d/search_wave.py -- [--side R]
"""
import itertools
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_clearance as cc  # noqa: E402  (module-level main() is guarded below)
from anim import rigmap  # noqa: E402
from anim.clip import Clip  # noqa: E402


def pose_clip(side, raise_, swing, lift, elbow):
    c = Clip(1)
    c.arm_raise(side, raise_)
    c.arm_swing(side, swing)
    c.forearm_lift(side, lift)
    c.elbow(side, elbow)
    return c


def main():
    side = "R"
    if "--side" in sys.argv:
        side = sys.argv[sys.argv.index("--side") + 1]
    rig = bpy.data.objects["Morfi_Rig"]
    ob = bpy.data.objects["Morfi_Body"]
    rig.animation_data_clear()
    head = cc.groups_mask(ob, {"head"}, 0.95)
    hand = cc.groups_mask(ob, {f"hand.{side}", f"fingers.{side}", f"thumb.{side}"}, 0.5)
    sub = hand & (np.arange(len(hand)) % 3 == 0)
    results = []
    grid = itertools.product([44, 52, 60], [20], [45, 55, 65], [0])
    for r, w, fl, e in grid:
        gaps, tops = [], []
        for d in (-12, 0, 12):
            c = pose_clip(side, r, w, fl + d, e)
            act = rigmap.bake(rig, "_probe", c.channels(), 1)
            rigmap.assign(rig, act)
            bpy.context.scene.frame_set(0)
            P, N = cc.evaluated_coords(ob)
            gaps.append(cc.signed_gap(P, N, head, sub))
            tops.append(P[hand].mean(0))
        hc = tops[1]
        results.append((min(gaps), hc[2], abs(hc[0]), hc[1], r, w, fl, e))
        print(f"ALL {r} {w} {fl} {e} gaps " + " ".join(f"{g * 100:5.1f}" for g in gaps) + f" hand z {hc[2]:.3f} x {hc[0]:.3f} y {hc[1]:.3f}")
    ok = [x for x in results if x[0] >= 0.02]
    ok.sort(key=lambda x: (-x[1]))
    print("CANDIDATES gap_cm z x y | raise swing lift elbow")
    for g, z, x, y, r, w, fl, e in ok[:15]:
        print(f"CAND {g * 100:5.1f} {z:.3f} {x:.3f} {y:+.3f} | {r} {w} {fl} {e}")
    print("DONE", len(ok), "of", len(results))


main()
