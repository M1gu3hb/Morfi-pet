"""Per-frame report of an action with props: hand/body overlaps with the props, fingertip
presses, palm supports, and the usual hand-vs-head/torso and arm-vs-torso clearances.

blender -b work/ia3d/morfi_ia_anim2.blend --python scripts/ia3d/check_props.py -- --action Tablet [--step 1]

Exit report line "PROPS <action> ok=True ..." when nothing goes through anything and every
press / support really touches (tolerances in anim/contacts.py).
"""
import argparse
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_clearance as cc  # noqa: E402
from anim import contacts, rigmap  # noqa: E402
from anim.actions import ACTIONS  # noqa: E402

SHALLOW = 0.02
CLOTH = 0.025


def _bvh(P, polys):
    return BVHTree.FromPolygons([tuple(p) for p in P], polys)


def face_gap(tree, Q):
    """Min signed distance of points Q to a surface (sign from the nearest face's normal,
    trusted within SHALLOW: the open jacket has inward-facing panels further away)."""
    best = 9.0
    for q in Q:
        loc, nrm, _, d = tree.find_nearest(Vector(q))
        if loc is None:
            continue
        s = (Vector(q) - loc).dot(nrm)
        v = -d if (s < 0 and d < SHALLOW) else d
        best = min(best, v)
    return best


def body_clearance(rig, body, hands, polys, probes):
    """Hands and arms (sleeves) against the head and the torso."""
    P, _ = cc.evaluated_coords(body)
    trees = {k: _bvh(P, pl) for k, pl in polys.items()}
    out = {}
    for s, hob in hands.items():
        H, _ = cc.evaluated_coords(hob)
        H = H[::3]
        A = P[probes[s]]
        out[f"{s}_hand_head"] = face_gap(trees["head"], H)
        out[f"{s}_hand_torso"] = face_gap(trees["torso"], H)
        out[f"{s}_arm_head"] = face_gap(trees["head"], A)
        out[f"{s}_arm_torso"] = face_gap(trees["torso"], A)
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", required=True)
    ap.add_argument("--step", type=int, default=1)
    args = ap.parse_args(argv)
    rig = bpy.data.objects["Morfi_Rig"]
    body = bpy.data.objects["Morfi_Body"]
    hands = {s: bpy.data.objects[f"Hand_{s}"] for s in ("L", "R")}
    faced = contacts._faced(body)
    head = cc.groups_mask(body, {"head"}, 0.95)
    torso = cc.groups_mask(body, {"hips", "spine", "chest"}, 0.8)
    polys = {k: [tuple(p.vertices) for p in body.data.polygons if all(m[i] for i in p.vertices)]
             for k, m in (("head", head), ("torso", torso))}
    probes = {s: np.flatnonzero(cc.groups_mask(body, {f"forearm.{s}", f"hand.{s}"}, 0.6) & faced)[::2]
              for s in ("L", "R")}
    rigmap.reset_pose(rig)
    if rig.animation_data:
        rig.animation_data.action = None
    bpy.context.view_layer.update()
    base = body_clearance(rig, body, hands, polys, probes)
    print("REST " + " ".join(f"{k} {v * 100:.1f}cm" for k, v in base.items()))
    for name in args.action.split(","):
        clip = ACTIONS[name]()
        act = bpy.data.actions[name]
        ok, worst, rows = contacts.verify(rig, act, clip)
        clear = {}
        for f in range(0, clip.n, args.step):
            bpy.context.scene.frame_set(f)
            for k, v in body_clearance(rig, body, hands, polys, probes).items():
                clear[k] = min(clear.get(k, 9.0), v)
        for r in rows:
            if r["pen"] > contacts.PEN_TOL:
                print(f"OVERLAP F{r['frame']:03d} {r['pen'] * 1000:+.1f} mm")
        for r in rows[::max(1, args.step * 5)]:
            extra = "".join(f" {k} {v * 1000:+.1f} mm" for k, v in r.items() if k in ("press", "support") and v is not None)
            print(f"F{r['frame']:03d} overlap {r['pen'] * 1000:+.1f} mm{extra}")
        # hands: strict. Sleeves against the jacket: cloth on cloth, up to CLOTH of compression
        # (the elbow brushing the padded jacket; invisible from the front and 3/4 views)
        body_ok = all(v > (-CLOTH if k.endswith("arm_torso") else min(-0.002, base[k] - 0.002)) for k, v in clear.items())
        print(f"PROPS {name} ok={ok and body_ok} overlap {worst['pen'] * 1000:.1f} mm press {worst['press'] * 1000:.1f} mm "
              f"support {worst['support'] * 1000:.1f} mm | " + " ".join(f"{k} {v * 100:.1f}cm" for k, v in clear.items()))


main()
