"""Arm / leg phase of the stepping clips, measured on the evaluated pose (world space).

blender -b work/ia3d/morfi_ia_anim8.blend --python scripts/ia3d/check_gait.py -- --actions Walk,Run [--out gait.json]

Per clip and side: forward position (-Y) of the wrist and of the ankle over the cycle.
For loops the first harmonic gives each signal's peak time (frames); the same-side
hand-vs-foot phase difference is ~0 deg when arm and leg move together (wrong) and ~180 deg
when they are contralateral (right). For one-shot clips only the Pearson correlation is given.
"""
import json
import math
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
names = argv[argv.index("--actions") + 1].split(",") if "--actions" in argv else ["Walk", "Run"]
out = argv[argv.index("--out") + 1] if "--out" in argv else None
rig = bpy.data.objects["Morfi_Rig"]
rig.animation_data_create()
LOOPS = {"Walk", "Run", "Sneak", "Dance", "Dance_2"}


def head(pb):
    return rig.matrix_world @ pb.head


def sample(action):
    rig.animation_data.action = action
    if hasattr(rig.animation_data, "action_slot") and action.slots:
        rig.animation_data_create().action_slot = action.slots[0]
    f0, f1 = int(action.frame_start), int(action.frame_end)
    n = f1 - f0 + (0 if action.get("loop") else 1)
    sig = {k: [] for k in ("hand_L", "hand_R", "foot_L", "foot_R", "elbow_L", "elbow_R", "flex_L", "flex_R", "hips_z",
                           "hips_x", "pelvis_yaw", "shoulder_yaw", "knee_L", "knee_R")}
    for f in range(f0, f0 + n):
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = rig.evaluated_get(dg)
        pb = ev.pose.bones

        def hd(name):
            return ev.matrix_world @ pb[name].head

        def tl(name):
            return ev.matrix_world @ pb[name].tail
        for s in "LR":
            sig[f"hand_{s}"].append(-hd(f"hand.{s}").y)
            sig[f"foot_{s}"].append(-hd(f"foot.{s}").y)
            sig[f"elbow_{s}"].append(-hd(f"forearm.{s}").y)
            sig[f"knee_{s}"].append(-hd(f"shin.{s}").y)
            u = (tl(f"upper_arm.{s}") - hd(f"upper_arm.{s}")).normalized()
            fa = (tl(f"forearm.{s}") - hd(f"forearm.{s}")).normalized()
            sig[f"flex_{s}"].append(math.degrees(math.acos(max(-1, min(1, u.dot(fa))))))
        sig["hips_z"].append(hd("hips").z)
        sig["hips_x"].append(hd("hips").x)
        pv = hd("thigh.L") - hd("thigh.R")
        sh = hd("shoulder.L") - hd("shoulder.R")
        sig["pelvis_yaw"].append(math.degrees(math.atan2(pv.y, pv.x)))
        sig["shoulder_yaw"].append(math.degrees(math.atan2(sh.y, sh.x)))
    return n, {k: np.array(v) for k, v in sig.items()}


def harm(x, k=1):
    n = len(x)
    f = np.arange(n)
    return np.sum((x - x.mean()) * np.exp(-2j * np.pi * k * f / n))


def peak_t(x, k=1):
    """Frame (0..n/k) where the k-th harmonic peaks."""
    n = len(x)
    return (-np.angle(harm(x, k)) / (2 * np.pi) * n / k) % (n / k)


def dphi(a, b, k=1):
    """Phase of a minus phase of b (deg, -180..180) for the k-th harmonic."""
    d = np.degrees(np.angle(harm(a, k) / harm(b, k)))
    return (d + 180) % 360 - 180


def corr(a, b):
    return float(np.corrcoef(a, b)[0, 1])


res = {}
for name in names:
    n, sg = sample(bpy.data.actions[name])
    r = {"n": n}
    if name in LOOPS:
        r["same_side_hand_vs_foot_deg"] = {s: float(dphi(sg[f"hand_{s}"], sg[f"foot_{s}"])) for s in "LR"}
        r["opp_side_hand_vs_foot_deg"] = {s: float(dphi(sg[f"hand_{s}"], sg[f"foot_{'R' if s == 'L' else 'L'}"]))
                                          for s in "LR"}
        r["peak_frame"] = {k: float(peak_t(v)) for k, v in sg.items() if k not in ("hips_z",)}
        r["hips_z_peak_frame_k2"] = float(peak_t(sg["hips_z"], 2))
        r["hand_amp_cm"] = {s: float((sg[f"hand_{s}"].max() - sg[f"hand_{s}"].min()) * 50) for s in "LR"}
        r["foot_amp_cm"] = {s: float((sg[f"foot_{s}"].max() - sg[f"foot_{s}"].min()) * 50) for s in "LR"}
        r["elbow_flex_deg_range"] = {s: [float(sg[f"flex_{s}"].min()), float(sg[f"flex_{s}"].max())] for s in "LR"}
        r["flex_vs_hand_fwd_corr"] = {s: corr(sg[f"flex_{s}"], sg[f"hand_{s}"]) for s in "LR"}
        r["pelvis_vs_shoulder_yaw_deg"] = float(dphi(sg["pelvis_yaw"], sg["shoulder_yaw"]))
        r["pelvis_yaw_amp"] = float(sg["pelvis_yaw"].max() - sg["pelvis_yaw"].min())
        r["shoulder_yaw_amp"] = float(sg["shoulder_yaw"].max() - sg["shoulder_yaw"].min())
        # lag of the hand behind the opposite foot (positive = arm later), from the circular cross-correlation
        lag = {}
        for s in "LR":
            o = "R" if s == "L" else "L"
            h, ft = sg[f"hand_{s}"] - sg[f"hand_{s}"].mean(), sg[f"foot_{o}"] - sg[f"foot_{o}"].mean()
            cc = [np.dot(np.roll(ft, k), h) for k in range(n)]
            k = int(np.argmax(cc))
            lag[s] = k if k <= n // 2 else k - n
        r["hand_lag_behind_contra_foot_frames"] = lag
    r["corr_same_side_hand_foot"] = {s: corr(sg[f"hand_{s}"], sg[f"foot_{s}"]) for s in "LR"}
    r["corr_opp_side_hand_foot"] = {s: corr(sg[f"hand_{s}"], sg[f"foot_{'R' if s == 'L' else 'L'}"]) for s in "LR"}
    res[name] = r
    print("PHASE", name, json.dumps(r), flush=True)
if out:
    with open(out, "w") as fh:
        json.dump(res, fh, indent=1)
