"""Reachability map: where can a hand go without stretching the arm too much and without the
hand or the sleeve going into the head or the torso?

blender -b work/ia3d/morfi_ia_anim3.blend --python scripts/ia3d/reach_map.py -- \
    --side L --orient palm_up --out work/ia3d/reach_L_palm_up.json [--shoulder 24] [--pole side]

Samples a grid of wrist positions (project frame: Morfi faces -Y, his left is +X), puts the
arm on IK there with the given hand orientation and measures, per point:
  ratio       shoulder->wrist distance / rest arm length (IK stretch above 1.0)
  arm_torso   signed gap sleeve (forearm + cuff) vs torso surface (m, negative = inside)
  arm_head    same against the head
  hand_torso, hand_head   the hand mesh against torso / head
Feasible points (ratio <= MAX_REACH, every gap >= 0) are printed as a compact table and all
points saved as JSON, so an action (or the future tutorial skill) can place props and hand
targets where Morfi really reaches.
"""
import argparse
import json
import os
import sys

import bpy
import numpy as np
from mathutils import Quaternion, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_clearance as cc  # noqa: E402
from anim import contacts, rigmap  # noqa: E402
from anim.motor import WRIST_REST, _rest_hand_frame, hand_orient  # noqa: E402

ORIENT = {   # (fingers, palm) in the world frame, per side (R mirrors x)
    "palm_up": ((-0.85, -0.5, 0.0), (0.0, 0.0, 1.0)),
    "palm_back": ((-0.1, -0.25, 0.96), (-0.55, -0.80, 0.25)),
    "tap": ((0.55, -0.45, -0.70), (0.25, 0.45, -0.85)),
    "rest": None,
}
POLE = {"back": (0.10, 0.30, -0.02), "side": (0.40, 0.05, -0.10), "down": (0.15, 0.10, -0.40)}


def mirror(v, side):
    return v if side == "L" else (-v[0], v[1], v[2])


def set_target(rig, side, wrist, orient, pole):
    pb = rig.pose.bones[f"hand_ik.{side}"]
    R = pb.bone.matrix_local.to_3x3()
    pb.location = R.inverted() @ Vector(np.asarray(wrist) - WRIST_REST[side])
    if orient is None:
        D, N = _rest_hand_frame(side)
    else:
        D, N = (mirror(np.array(v), side) for v in orient)
    rx, ry, rz = hand_orient(side, D, N)
    q = Quaternion((0, 0, 1), np.radians(rz)) @ Quaternion((1, 0, 0), np.radians(rx)) @ Quaternion((0, 1, 0), np.radians(ry))
    Rq = R.to_quaternion()
    pb.rotation_quaternion = Rq.inverted() @ q @ Rq
    pp = rig.pose.bones[f"elbow_pole.{side}"]
    offset = np.array(mirror(POLE[pole], side)) - np.array(mirror(POLE["back"], side))   # rest pole is "back"
    pp.location = pp.bone.matrix_local.to_3x3().inverted() @ Vector(offset)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", default="L")
    ap.add_argument("--orient", default="palm_up", choices=list(ORIENT))
    ap.add_argument("--pole", default="back", choices=list(POLE))
    ap.add_argument("--shoulder", type=float, default=24.0, help="shoulders forward (deg)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--step", type=float, default=0.025)
    args = ap.parse_args(argv)
    rig = bpy.data.objects["Morfi_Rig"]
    body = bpy.data.objects["Morfi_Body"]
    side = args.side
    hand = bpy.data.objects[f"Hand_{side}"]
    if rig.animation_data:
        rig.animation_data.action = None
    rigmap.reset_pose(rig)
    sh = rig.pose.bones[f"shoulder.{side}"]
    R = sh.bone.matrix_local.to_3x3()
    sx = 1 if side == "L" else -1
    q = Quaternion((0, 0, 1), np.radians(-args.shoulder * sx))
    sh.rotation_quaternion = R.to_quaternion().inverted() @ q @ R.to_quaternion()
    for c in (rig.pose.bones[f"forearm.{side}"].constraints["ArmIK"], rig.pose.bones[f"hand.{side}"].constraints["HandIK"]):
        c.influence = 1.0
    faced = contacts._faced(body)
    head = cc.groups_mask(body, {"head"}, 0.95)
    torso = cc.groups_mask(body, {"hips", "spine", "chest"}, 0.8)
    polys = {k: [tuple(p.vertices) for p in body.data.polygons if all(m[i] for i in p.vertices)]
             for k, m in (("head", head), ("torso", torso))}
    arm = np.flatnonzero(cc.groups_mask(body, {f"forearm.{side}", f"hand.{side}", f"upper_arm.{side}"}, 0.6) & faced)[::3]
    up = rig.pose.bones[f"upper_arm.{side}"]
    L0 = up.bone.length + rig.pose.bones[f"forearm.{side}"].bone.length
    xs = np.arange(0.0, 0.30, args.step) * sx
    ys = np.arange(-0.06, -0.24, -0.02)
    zs = np.arange(0.24, 0.50, 0.02)
    rows = []
    bpy.context.view_layer.update()
    for x in xs:
        for y in ys:
            for z in zs:
                set_target(rig, side, (x, y, z), ORIENT[args.orient], args.pole)
                bpy.context.view_layer.update()
                s = np.array(rig.matrix_world @ up.head)
                ratio = float(np.linalg.norm(np.array((x, y, z)) - s) / L0)
                if ratio > contacts.MAX_REACH + 0.15:
                    continue
                P, _ = cc.evaluated_coords(body)
                H, _ = cc.evaluated_coords(hand)
                trees = {k: BVHTree.FromPolygons([tuple(p) for p in P], pl) for k, pl in polys.items()}

                def gap(tree, Q):
                    best = 9.0
                    for qv in Q:
                        loc, nrm, _, d = tree.find_nearest(Vector(qv))
                        if loc is None:
                            continue
                        sgn = (Vector(qv) - loc).dot(nrm)
                        best = min(best, -d if (sgn < 0 and d < 0.02) else d)
                    return best
                r = {"wrist": [round(float(v), 3) for v in (x, y, z)], "ratio": round(ratio, 3),
                     "arm_torso": gap(trees["torso"], P[arm]), "arm_head": gap(trees["head"], P[arm]),
                     "hand_torso": gap(trees["torso"], H[::4]), "hand_head": gap(trees["head"], H[::4])}
                r["ok"] = r["ratio"] <= contacts.MAX_REACH and min(r[k] for k in ("arm_torso", "arm_head", "hand_torso", "hand_head")) >= 0.0
                rows.append(r)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump({"side": side, "orient": args.orient, "pole": args.pole, "shoulder": args.shoulder, "points": rows},
              open(os.path.abspath(args.out), "w"), indent=0)
    ok = [r for r in rows if r["ok"]]
    print(f"REACH {side} {args.orient} pole={args.pole}: {len(ok)} feasible of {len(rows)} sampled")
    for r in ok:
        print("OK", r["wrist"], r["ratio"], {k: round(r[k] * 100, 1) for k in ("arm_torso", "arm_head", "hand_torso", "hand_head")})


main()
