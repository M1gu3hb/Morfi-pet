"""Turn per-frame channels into a Blender action on Morfi_Rig.

Channel names:
  "<bone>.rx|ry|rz"   rotation in degrees about the WORLD axes as they are at rest,
                      relative to the parent bone (composed Y first, then X, then Z).
                      Morfi faces -Y, his left is +X:  +rx leans/nods forward,
                      +ry tilts to his left, +rz turns to his left.
  "<bone>.tw"         twist in degrees about the bone's own axis (applied first).
  "<bone>.cx|cz"      rotation in degrees about the bone's own X / Z axes (fingers: +cx curls into
                      the palm, cz spreads), applied in the bone's local frame.
  "<bone>.s"          uniform scale (props: 0 hidden, 1 shown).
  "<bone>.sy"         stretch along the bone, volume kept (1.0 rest; arms may go to ~1.12).
  "ik.<side>"         arm IK on/off (0..1): blends FK with the hand_ik target (see build_controls.py).
  "<bone>.lx|ly|lz"   translation in metres along the world rest axes (root, hips, IK bones).
  "prop.<name>"       custom property on the rig object (blink, gaze, mouth...). The prop bone
                      is called "prop" too: "prop.rx", "prop.lx"... (a bone channel suffix) are
                      that bone's channels, anything else after "prop." is a face property.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from .clip import FACE_PROPS  # noqa: E402  (shared with the web exporter)


BONE_CH = {"rx", "ry", "rz", "tw", "cx", "cz", "s", "sy", "lx", "ly", "lz"}


def is_face(k):
    """Channel of a rig custom property (face), not of a bone."""
    return k.startswith("prop.") and k[5:] not in BONE_CH


def ensure_props(rig):
    for k, v in FACE_PROPS.items():
        if k not in rig:
            rig[k] = v
        ui = rig.id_properties_ui(k)
        ui.update(min=-1.0, max=1.0, soft_min=-1.0, soft_max=1.0)


def _quat_world(rx, ry, rz):
    q = Quaternion((0, 0, 1), math.radians(rz)) @ Quaternion((1, 0, 0), math.radians(rx)) @ \
        Quaternion((0, 1, 0), math.radians(ry))
    return q


def _fcurves(action, path, count, n, values, group):
    for i in range(count):
        fc = action.fcurves.find(path, index=i) or action.fcurves.new(path, index=i, action_group=group)
        fc.keyframe_points.clear()
        fc.keyframe_points.add(n)
        co = np.empty(2 * n)
        co[0::2] = np.arange(n, dtype=float)
        co[1::2] = values[:, i] if values.ndim == 2 else values
        fc.keyframe_points.foreach_set("co", co)
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        fc.update()


def bake(rig, name, channels, n, loop=False):
    """Write channels into a new action `name` (replacing an existing one)."""
    old = bpy.data.actions.get(name)
    if old is not None:
        bpy.data.actions.remove(old)
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    action.use_frame_range = True
    action.frame_start, action.frame_end = 0, n - 1 if not loop else n
    action["loop"] = int(loop)
    ensure_props(rig)
    # every action keys every bone and every face property (at rest when unused), so
    # actions crossfade cleanly in the NLA without channels snapping back to rest
    channels = dict(channels)
    for pb in rig.pose.bones:
        if not any(k.startswith(pb.name + ".") and not is_face(k) for k in channels):
            channels[f"{pb.name}.rx"] = np.zeros(n)
        if pb.name in ("root", "hips") or pb.name.startswith("foot_ik"):
            channels.setdefault(f"{pb.name}.lx", np.zeros(n))
    for k in FACE_PROPS:
        channels.setdefault(f"prop.{k}", np.full(n, FACE_PROPS[k]))
    for pb in rig.pose.bones:
        if pb.name.startswith("prop_"):
            channels.setdefault(f"{pb.name}.s", np.zeros(n))      # props hidden unless shown
        if pb.name in ("prop",) or pb.name.startswith("hand_ik"):
            channels.setdefault(f"{pb.name}.lx", np.zeros(n))
        # scale too: a bone an action does not scale would keep the stretch or squash the
        # previous action left on it (the bake, the solvers and the NLA all evaluate in a row)
        if f"{pb.name}.s" not in channels and f"{pb.name}.sy" not in channels:
            channels[f"{pb.name}.sy"] = np.ones(n)
    if "forearm.L" in rig.pose.bones and rig.pose.bones["forearm.L"].constraints.get("ArmIK"):
        for side in ("L", "R"):
            channels.setdefault(f"ik.{side}", np.zeros(n))
    bones = sorted({k.rsplit(".", 1)[0] for k in channels if not is_face(k) and not k.startswith("ik.")})
    for bname in bones:
        if bname not in rig.pose.bones:
            raise KeyError(f"unknown bone {bname!r} in action {name}")
        pb = rig.pose.bones[bname]
        R = pb.bone.matrix_local.to_3x3()
        Rinv = R.inverted()
        Rq, Rqi = R.to_quaternion(), R.inverted().to_quaternion()
        get = lambda c: channels.get(f"{bname}.{c}", np.zeros(n))  # noqa: E731
        rx, ry, rz, tw = get("rx"), get("ry"), get("rz"), get("tw")
        cx, cz = get("cx"), get("cz")
        if any(f"{bname}.{a}" in channels for a in ("rx", "ry", "rz", "tw", "cx", "cz")):
            qs = np.empty((n, 4))
            prev = None
            for f in range(n):
                ql = (Rqi @ _quat_world(rx[f], ry[f], rz[f]) @ Rq @ Quaternion((0, 0, 1), math.radians(cz[f]))
                      @ Quaternion((1, 0, 0), math.radians(cx[f])) @ Quaternion((0, 1, 0), math.radians(tw[f])))
                if prev is not None and ql.dot(prev) < 0:
                    ql.negate()
                qs[f] = ql[:]
                prev = ql
            _fcurves(action, f'pose.bones["{bname}"].rotation_quaternion', 4, n, qs, bname)
        if f"{bname}.s" in channels or f"{bname}.sy" in channels:
            us = np.asarray(channels.get(f"{bname}.s", np.ones(n)), float)
            sy = np.asarray(channels.get(f"{bname}.sy", np.ones(n)), float)
            side = 1.0 / np.sqrt(np.maximum(sy, 1e-3))
            sc = np.stack([us * side, us * sy, us * side], 1)
            _fcurves(action, f'pose.bones["{bname}"].scale', 3, n, sc, bname)
        if any(f"{bname}.l{a}" in channels for a in "xyz"):
            lx, ly, lz = get("lx"), get("ly"), get("lz")
            locs = np.array([(Rinv @ Vector((lx[f], ly[f], lz[f])))[:] for f in range(n)])
            _fcurves(action, f'pose.bones["{bname}"].location', 3, n, locs, bname)
    for k, v in channels.items():
        if is_face(k):
            _fcurves(action, f'["{k[5:]}"]', 1, n, np.asarray(v, float), "Face")
        elif k.startswith("ik."):
            s = k[3:]
            w = np.clip(np.asarray(v, float), 0, 1)
            _fcurves(action, f'pose.bones["forearm.{s}"].constraints["ArmIK"].influence', 1, n, w, "IK")
            _fcurves(action, f'pose.bones["hand.{s}"].constraints["HandIK"].influence', 1, n, w, "IK")
    return action


def assign(rig, action):
    rig.animation_data_create()
    rig.animation_data.action = action
    if hasattr(rig.animation_data, "action_slot") and action.slots:
        rig.animation_data.action_slot = action.slots[0]
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = int(action.frame_start), int(action.frame_end)


def reset_pose(rig):
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
