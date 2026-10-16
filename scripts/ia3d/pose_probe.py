"""Render static test poses built with the motor (one frame each) and report contacts.

blender -b work/ia3d/morfi_ia_face2.blend --python scripts/ia3d/pose_probe.py -- \
    --poses contar3,pulgar --out work/ia3d/poses [--views front,three_quarter_front] [--res 0.35]

Poses live in POSES below (functions filling a 1-frame Clip). For each pose it prints the
signed hand-head and hand-torso distances (cm, negative = inside) so the pose can be fixed
before it goes into an action.
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))
import check_clearance as cc  # noqa: E402
import render_contact as rc  # noqa: E402
from anim import rigmap  # noqa: E402
from anim.clip import Clip  # noqa: E402
from anim.motor import orient_keys  # noqa: E402
from morfi.scene import place_camera  # noqa: E402


def _arms_down(c):
    for s in ("L", "R"):
        c.arm_raise(s, -4)
        c.elbow(s, 12)
        c.hand(s, [(0, "relaxed")])


def contar3(c):
    _arms_down(c)
    c.reach("R", [(0, (-0.19, -0.21, 0.47))])
    rx, ry, rz = orient_keys("R", [(0, (0.05, -0.15, 1.0), (0.0, -1.0, 0.0))])
    c.reach_rot("R", rx, ry, rz)
    c.hand("R", [(0, "count3")])
    c.expr([(0, "happy")])


def pulgar(c):
    _arms_down(c)
    c.reach("R", [(0, (-0.21, -0.22, 0.40))])
    rx, ry, rz = orient_keys("R", [(0, (0.0, -1.0, 0.25), (1.0, 0.0, 0.0))])
    c.reach_rot("R", rx, ry, rz)
    c.hand("R", [(0, "thumbs_up")])
    c.expr([(0, "joy")])


def senalar(c):
    _arms_down(c)
    c.reach("L", [(0, (0.37, -0.09, 0.47))])
    rx, ry, rz = orient_keys("L", [(0, (1.0, -0.25, 0.1), (0.0, 0.2, -1.0))])
    c.reach_rot("L", rx, ry, rz)
    c.hand("L", [(0, "point")])
    c.add("head.rz", 12)
    c.add("chest.rz", 6)
    c.prop("gaze_x", 0.6)
    c.expr([(0, "happy")])


def barbilla(c):
    _arms_down(c)
    c.add("chest.rx", 6)
    c.add("neck.rx", 4)
    c.add("head.rx", 6)
    c.add("head.ry", -5)
    c.reach("R", [(0, (-0.085, -0.24, 0.400))])
    rx, ry, rz = orient_keys("R", [(0, (0.15, -0.25, 1.0), (0.3, 1.0, 0.0))])
    c.reach_rot("R", rx, ry, rz)
    c.hand("R", [(0, "fist")])
    c.elbow("L", 70)
    c.forearm_in("L", 30)
    c.expr([(0, "thinking")])


def festejo(c):
    for s in ("L", "R"):
        c.arm_raise(s, 60)
        c.arm_swing(s, 4)
        c.forearm_lift(s, 40)
        c.hand(s, [(0, "fist")])
        c.stretch(s, [(0, 1.10)])
    c.add("hips.lz", 0.01)
    c.add("head.rx", -6)
    c.expr([(0, "joy")])


POSES = {"contar3": contar3, "pulgar": pulgar, "senalar": senalar, "barbilla": barbilla, "festejo": festejo}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", default=",".join(POSES))
    ap.add_argument("--out", required=True)
    ap.add_argument("--views", default="front,three_quarter_front")
    ap.add_argument("--res", type=float, default=0.35)
    args = ap.parse_args(argv)
    rig = bpy.data.objects["Morfi_Rig"]
    body = bpy.data.objects["Morfi_Body"]
    cam, light_rig = rc.setup_scene(16)
    sc = bpy.context.scene
    sc.render.resolution_percentage = int(args.res * 100)
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.dirname(HERE)), "config", "morfi.json"), encoding="utf-8"))
    head = cc.groups_mask(body, {"head"}, 0.95)
    torso = cc.groups_mask(body, {"hips", "spine", "chest"}, 0.8)
    hands = {s: bpy.data.objects[f"Hand_{s}"] for s in ("L", "R")}
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    for name in args.poses.split(","):
        c = Clip(1)
        POSES[name](c)
        act = rigmap.bake(rig, "_pose", c.channels(), 1)
        rigmap.assign(rig, act)
        sc.frame_set(0)
        P, N = cc.evaluated_coords(body)
        report = []
        for s, hob in hands.items():
            H, _ = cc.evaluated_coords(hob)
            allp = np.concatenate([P, H])
            alln = np.concatenate([N, np.zeros_like(H)])
            probe = np.zeros(len(allp), bool)
            probe[len(P):] = True
            hm = np.concatenate([head, np.zeros(len(H), bool)])
            tm = np.concatenate([torso, np.zeros(len(H), bool)])
            report.append(f"{s}: head {cc.signed_gap(allp, alln, hm, probe) * 100:5.1f} cm, "
                          f"torso {cc.signed_gap(allp, alln, tm, probe) * 100:5.1f} cm")
        print(f"POSE {name}: " + " | ".join(report))
        for view in args.views.split(","):
            cv = dict(cfg["camera_views"][view])
            cv["distance"] *= 1.05
            place_camera(cam, cv)
            light_rig.rotation_euler = (0, 0, math.radians(cv["az"]))
            sc.render.filepath = os.path.join(out, f"{name}_{view}.png")
            bpy.ops.render.render(write_still=True)
    print("DONE")


main()
