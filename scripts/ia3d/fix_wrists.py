"""Wrists that bend like wrists (no hand poking out of the sleeve).

blender -b work/ia3d/morfi_ia_look2.blend --python scripts/ia3d/fix_wrists.py -- \
    --out work/ia3d/morfi_ia_look3.blend

The hands of build_hands.py end in a 5 cm wrist that filled the hoodie cuff and followed the hand
bone rigidly; the cuff (body faces skinned to hand.<s>) turned with the hand too. A raised hand
on a forward forearm bent the wrist ~90 degrees: the cuff turned its opening to the camera and the
wrist came out of the back of the sleeve. Now:
  * the back of the hand mesh (behind the wrist joint) follows the forearm, blending into the
    hand over 3 cm, so the wrist bends as skin instead of swinging as a block;
  * the cuff follows the forearm, with a little of the hand (cloth gives a bit at the wrist);
  * a Limit Rotation on hand.<s> (local, after its Copy Rotation from the IK target) keeps the
    wrist inside a human range whatever the animation asks for.
"""
import argparse
import os
import sys

import bpy
import numpy as np

WRIST_FRONT = 0.006      # along the hand from the wrist joint: in front of this the hand rules
WRIST_BACK = -0.024      # behind this the forearm rules
CUFF_HAND = 0.30         # share of the hand the cuff keeps
LIMIT = {"x": 62.0, "y": 70.0, "z": 48.0}   # degrees: bend (x), twist (y), side bend (z)


def args_():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def weights(ob, name):
    g = ob.vertex_groups.get(name)
    w = np.zeros(len(ob.data.vertices))
    if g is None:
        return w
    for v in ob.data.vertices:
        for e in v.groups:
            if e.group == g.index:
                w[v.index] = e.weight
    return w


def set_weights(ob, name, w):
    g = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
    g.remove(list(range(len(ob.data.vertices))))
    for i in np.nonzero(w > 1e-3)[0]:
        g.add([int(i)], float(w[i]), "REPLACE")


def fix_hand(rig, side):
    ob = bpy.data.objects[f"Hand_{side}"]
    hb = rig.data.bones[f"hand.{side}"]
    M = rig.matrix_world
    o = np.array(M @ hb.head_local)
    D = np.array(M @ hb.tail_local) - o
    D /= np.linalg.norm(D)
    Mo = ob.matrix_world
    co = np.array([(Mo @ v.co)[:] for v in ob.data.vertices])     # rest pose, world space
    t = (co - o) @ D
    f = smoothstep(WRIST_FRONT, WRIST_BACK, t)            # 1 behind the wrist, 0 in front
    hand = weights(ob, f"hand.{side}")
    moved = hand * f
    set_weights(ob, f"hand.{side}", hand - moved)
    set_weights(ob, f"forearm.{side}", weights(ob, f"forearm.{side}") + moved)
    print(f"hand {side}: {int((moved > 0.01).sum())} wrist vertices now bend with the forearm")


def fix_cuff(body, side):
    hand = weights(body, f"hand.{side}")
    keep = hand * CUFF_HAND
    set_weights(body, f"hand.{side}", keep)
    set_weights(body, f"forearm.{side}", weights(body, f"forearm.{side}") + hand - keep)
    print(f"cuff {side}: {int((hand > 0.01).sum())} vertices follow the forearm")


def limit_wrist(rig, side):
    pb = rig.pose.bones[f"hand.{side}"]
    for c in list(pb.constraints):
        if c.type == "LIMIT_ROTATION":
            pb.constraints.remove(c)
    c = pb.constraints.new("LIMIT_ROTATION")
    c.name = "Wrist"
    c.owner_space = "LOCAL"
    for ax, deg in LIMIT.items():
        setattr(c, f"use_limit_{ax}", True)
        setattr(c, f"min_{ax}", -np.radians(deg))
        setattr(c, f"max_{ax}", np.radians(deg))
    if hasattr(c, "euler_order"):
        c.euler_order = "YXZ"


def main():
    a = args_()
    rig = bpy.data.objects["Morfi_Rig"]
    body = bpy.data.objects["Morfi_Body"]
    for side in ("L", "R"):
        fix_hand(rig, side)
        fix_cuff(body, side)
        limit_wrist(rig, side)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("DONE", a.out)


if __name__ == "__main__":
    main()
