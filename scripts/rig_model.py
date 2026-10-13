"""Rig, skin and animate the built Morfi scene.

    blender -b source/morfi_master.blend --python scripts/rig_model.py -- [--out same.blend]

Adds 'Morfi_Rig' (armature), skin weights for the body and every garment,
bone parenting for rigid parts and these actions:
    Pose_Neutral, Pose_Hero, Idle, Walk, Run, Wave
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector, Quaternion, Euler, Matrix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
for _m in [k for k in sys.modules if k.startswith('morfi')]:
    del sys.modules[_m]
from morfi import rig as R  # noqa: E402

SKINNED = ['Body_Base', 'Tshirt', 'Tshirt_Collar', 'Tshirt_Logo', 'Hoodie', 'Hoodie_Hem',
           'Hoodie_Cuff_L', 'Hoodie_Cuff_R', 'Hoodie_Zipper', 'Hoodie_Drawstrings']
FPS = 24


def P(rig, name):
    return rig.pose.bones[name]


def qa(axis, deg):
    return Quaternion(Vector(axis), math.radians(deg))


def set_rot(rig, name, *rots):
    """Set a bone rotation from world-space (axis, degrees) pairs at rest."""
    pb = P(rig, name)
    M = (rig.matrix_world @ pb.bone.matrix_local).to_3x3()
    q = Quaternion()
    for axis, deg in rots:
        ax = (M.inverted() @ Vector(axis)).normalized()
        q = q @ Quaternion(ax, math.radians(deg))
    pb.rotation_quaternion = q


def aim(rig, name, direction, twist=0.0):
    """Point a pose bone (its +Y axis) along a world-space direction,
    taking the parent's current pose into account."""
    pb = P(rig, name)
    pb.rotation_quaternion = (1, 0, 0, 0)
    bpy.context.view_layer.update()
    M = (rig.matrix_world @ pb.matrix).to_3x3().normalized()
    cur = (M @ Vector((0, 1, 0))).normalized()
    q_world = cur.rotation_difference(Vector(direction).normalized())
    q_local = (M.inverted() @ q_world.to_matrix() @ M).to_quaternion()
    if twist:
        q_local = q_local @ Quaternion(Vector((0, 1, 0)), math.radians(twist))
    pb.rotation_quaternion = q_local
    bpy.context.view_layer.update()


def new_action(rig, name):
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = act
    return act


def key_all(rig, frame, bones=None):
    for pb in rig.pose.bones:
        if bones and pb.name not in bones:
            continue
        pb.keyframe_insert('rotation_quaternion', frame=frame)
        pb.keyframe_insert('location', frame=frame)


def make_cyclic(act):
    for fc in getattr(act, 'fcurves', []):
        fc.modifiers.new('CYCLES')
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'


def pose_hero(rig):
    """Master-image pose: laptop tucked under the right arm, left fist on the hip."""
    R.reset_pose(rig)
    bpy.context.view_layer.update()
    set_rot(rig, 'hips', ((0, 0, 1), -4.0), ((0, 1, 0), 1.5))
    set_rot(rig, 'spine', ((0, 1, 0), -1.5))
    bpy.context.view_layer.update()
    # head turned toward the hero camera (-33 deg) and tilted, as in the master image
    set_rot(rig, 'head', ((0, 0, 1), -22.0), ((0, 1, 0), -8.0))
    # right arm hugs the laptop against the body
    aim(rig, 'upper_arm.R', (-0.42, 0.10, -1.0))
    aim(rig, 'forearm.R', (-0.10, -0.85, -0.55), twist=-20)
    aim(rig, 'hand.R', (0.05, -0.55, 0.85))
    aim(rig, 'fingers.R', (0.25, -0.2, 1.0))
    # left fist resting on the front of the hoodie (visible from the hero camera)
    aim(rig, 'upper_arm.L', (0.62, -0.48, -0.62))
    aim(rig, 'forearm.L', (-0.72, -0.62, -0.30))
    aim(rig, 'hand.L', (-0.35, -0.55, -0.75))
    aim(rig, 'fingers.L', (-0.1, 0.35, -0.8))
    # stance: left foot turned out a little
    set_rot(rig, 'thigh.L', ((0, 0, 1), 10.0), ((0, 1, 0), 2.0))
    set_rot(rig, 'thigh.R', ((0, 0, 1), -4.0))


def anim_idle(rig, length=48):
    new_action(rig, 'Idle')
    for f in range(0, length + 1, 6):
        t = f / length * 2 * math.pi
        R.reset_pose(rig)
        set_rot(rig, 'spine', ((1, 0, 0), 1.5 * math.sin(t)))
        set_rot(rig, 'chest', ((1, 0, 0), 1.2 * math.sin(t + 0.4)))
        set_rot(rig, 'head', ((1, 0, 0), -1.8 * math.sin(t + 0.8)), ((0, 1, 0), 2.0 * math.sin(t * 0.5)))
        set_rot(rig, 'upper_arm.L', ((0, 1, 0), -2.5 * math.sin(t)))
        set_rot(rig, 'upper_arm.R', ((0, 1, 0), 2.5 * math.sin(t)))
        P(rig, 'pixels').location = Vector((0, 0.006 + 0.006 * math.sin(t * 2), 0))
        P(rig, 'hips').location = Vector((0, 0.003 * math.sin(t) - 0.003, 0))
        key_all(rig, f + 1)


def _leg(rig, side, phase, swing, knee, lift):
    s = 'L' if side > 0 else 'R'
    set_rot(rig, 'thigh.' + s, ((1, 0, 0), swing * math.sin(phase)))
    kb = max(0.0, math.sin(phase + 1.6)) * knee
    set_rot(rig, 'shin.' + s, ((1, 0, 0), -kb))
    set_rot(rig, 'foot.' + s, ((1, 0, 0), 0.5 * kb - 0.4 * swing * math.sin(phase)))


def anim_cycle(rig, name, length, swing, knee, arm, lean, bob, run=False):
    new_action(rig, name)
    for f in range(0, length + 1, 2):
        t = f / length * 2 * math.pi
        R.reset_pose(rig)
        _leg(rig, 1, t, swing, knee, 0)
        _leg(rig, -1, t + math.pi, swing, knee, 0)
        set_rot(rig, 'spine', ((1, 0, 0), lean), ((0, 0, 1), 4 * math.sin(t)))
        set_rot(rig, 'head', ((1, 0, 0), -lean * 0.6), ((0, 0, 1), -3 * math.sin(t)))
        for side, s in ((1, 'L'), (-1, 'R')):
            ph = t + (math.pi if side > 0 else 0)
            set_rot(rig, 'upper_arm.' + s, ((1, 0, 0), arm * math.sin(ph)), ((0, 1, 0), side * (-18 if run else -8)))
            set_rot(rig, 'forearm.' + s, ((1, 0, 0), -((55 if run else 14) + (10 if run else 6) * math.sin(ph))))
        P(rig, 'hips').location = Vector((0, abs(math.sin(t)) * bob, 0))
        P(rig, 'pixels').location = Vector((0, 0.01 * abs(math.cos(t)), 0))
        key_all(rig, f + 1)


def anim_wave(rig, length=48):
    new_action(rig, 'Wave')
    for f in range(0, length + 1, 4):
        t = f / length * 2 * math.pi
        R.reset_pose(rig)
        bpy.context.view_layer.update()
        set_rot(rig, 'spine', ((0, 1, 0), 3.0))
        set_rot(rig, 'head', ((0, 1, 0), -4 + 3 * math.sin(t)))
        bpy.context.view_layer.update()
        aim(rig, 'upper_arm.R', (-0.92, -0.22, 0.38))
        sw = math.sin(t * 2)
        aim(rig, 'forearm.R', (-0.55 + 0.35 * sw, -0.30, 0.85))
        aim(rig, 'hand.R', (-0.45 + 0.45 * sw, -0.35, 0.9))
        key_all(rig, f + 1)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=bpy.data.filepath)
    a = ap.parse_args(argv)
    cfg = json.load(open(os.path.join(ROOT, 'config', 'morfi.json')))
    col = bpy.data.collections.get('Morfi') or bpy.context.scene.collection
    root = bpy.data.objects.get('Morfi_Root')
    old = bpy.data.objects.get('Morfi_Rig')
    if old:
        bpy.data.objects.remove(old)
    rig = R.build_armature(cfg, col, parent=root)
    J = R.joint_table(cfg)
    bpy.context.view_layer.update()
    for n in SKINNED:
        ob = bpy.data.objects.get(n)
        if ob is None:
            print('skip', n)
            continue
        R.skin_object(ob, rig, cfg, J)
        print('[rig] skinned', n, len(ob.data.vertices))
    # rigid followers
    R.bone_parent(bpy.data.objects['Head'], rig, 'head')
    for side in ('L', 'R'):
        R.bone_parent(bpy.data.objects['Shoe_' + side], rig, 'foot.' + side)
        e = bpy.data.objects.get('Eye_' + side)
        if e:
            R.bone_parent(e, rig, 'eye.' + side)
    pix = bpy.data.objects.get('Pixels')
    if pix:
        R.bone_parent(pix, rig, 'pixels')
    # actions
    sc = bpy.context.scene
    sc.render.fps = FPS
    new_action(rig, 'Pose_Neutral')
    R.reset_pose(rig)
    key_all(rig, 1)
    new_action(rig, 'Pose_Hero')
    pose_hero(rig)
    key_all(rig, 1)
    anim_idle(rig, 48)
    anim_cycle(rig, 'Walk', 24, swing=24, knee=38, arm=22, lean=4, bob=0.012)
    anim_cycle(rig, 'Run', 16, swing=40, knee=75, arm=45, lean=12, bob=0.03, run=True)
    anim_wave(rig, 48)
    for act in bpy.data.actions:
        if act.name in ('Idle', 'Walk', 'Run', 'Wave'):
            make_cyclic(act)
    # per-shot poses matched to each reference image (scripts/fit_view_poses.py)
    for view, vp in cfg.get('view_poses', {}).items():
        if view.startswith('_'):
            continue
        new_action(rig, 'Ref_' + view)
        R.reset_pose(rig)
        bpy.context.view_layer.update()
        for bone, ang in vp.items():
            if bone in rig.pose.bones:
                set_rot(rig, bone, ((1, 0, 0), ang[0]), ((0, 1, 0), ang[1]), ((0, 0, 1), ang[2]))
        key_all(rig, 1)
    # leave the rig in the neutral pose
    rig.animation_data.action = bpy.data.actions['Pose_Neutral']
    R.reset_pose(rig)
    sc.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=a.out, compress=True)
    print('[rig] saved', a.out)


if __name__ == '__main__':
    main()
