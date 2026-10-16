"""Foot contact check per action: shoes sinking into the floor and planted feet sliding.

blender -b work/ia3d/morfi_ia_anim.blend --python scripts/ia3d/check_feet.py -- [--actions Idle,Wave]

For each frame and shoe: lowest point (negative = under the floor) and, when the shoe is on
the floor (lowest point < 6 mm), how far its sole moved since the previous frame (mm).
The in-place Walk is reported against the root travel the showcase adds (feet should move
backwards at exactly that speed while planted).
"""
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_clearance as cc  # noqa: E402
from anim import rigmap  # noqa: E402
from anim.actions import ACTIONS  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = argv[argv.index("--actions") + 1].split(",") if "--actions" in argv else list(ACTIONS)
    rig = bpy.data.objects["Morfi_Rig"]
    ob = bpy.data.objects["Morfi_Body"]
    shoes = {s: cc.groups_mask(ob, {f"foot.{s}", f"toe.{s}"}, 0.9) for s in ("L", "R")}
    for name in names:
        act = bpy.data.actions[name]
        rigmap.assign(rig, act)
        stride = float(act.get("stride", 0.0))
        expected = 2 * stride / 16.0 * 1000 if stride else 0.0
        prev = {}
        worst_sink, slides = 0.0, []
        for f in range(int(act.frame_start), int(act.frame_end) + 1):
            bpy.context.scene.frame_set(f)
            P, _ = cc.evaluated_coords(ob)
            for s, m in shoes.items():
                idx = np.nonzero(m)[0]
                pts = P[idx]
                worst_sink = min(worst_sink, pts[:, 2].min())
                touching = set(idx[pts[:, 2] < 0.003].tolist())
                if s in prev:
                    both = sorted(touching & prev[s][1])
                    if both:
                        d = np.linalg.norm(P[both, :2] - prev[s][0][both, :2], axis=1)
                        slides.append(float(np.median(d)) * 1000)
                prev[s] = (P.copy(), touching)
        slides = np.array(slides) if slides else np.zeros(1)
        note = f" (expected planted speed for the walk: {expected:.1f} mm/frame)" if stride else ""
        print(f"FEET {name:12s} sink {worst_sink * 1000:6.1f} mm | contact slide median "
              f"{np.median(slides):5.2f} p95 {np.percentile(slides, 95):5.2f} max {slides.max():5.2f} mm/frame{note}")


main()
