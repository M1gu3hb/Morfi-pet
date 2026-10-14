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


# head of the hero pose (degrees about world Z = turn, Y = tilt, X = nod); config "hero_pose" -> "head"
HERO_HEAD = {'turn': -22.0, 'tilt': -8.0, 'nod': 0.0}
HERO_SPINE_TILT = [-1.5]  # degrees about world Y; config "hero_pose" -> "spine_tilt"


def pose_hero(rig):
    """Master-image pose: laptop tucked under the right arm, left fist on the hip."""
    R.reset_pose(rig)
    bpy.context.view_layer.update()
    set_rot(rig, 'hips', ((0, 0, 1), -4.0), ((0, 1, 0), 1.5))
    set_rot(rig, 'spine', ((0, 1, 0), HERO_SPINE_TILT[0]))
    bpy.context.view_layer.update()
    # head turned toward the hero camera (-33 deg) and tilted, as in the master image
    set_rot(rig, 'head', ((1, 0, 0), HERO_HEAD['nod']), ((0, 0, 1), HERO_HEAD['turn']), ((0, 1, 0), HERO_HEAD['tilt']))
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
        # the head is 0.65 m wide and the arm short: the upper arm goes out to
        # the side and the forearm swings up and outward, so the waving hand
        # stays a hand's width outside the head (it went into its side)
        # (searched on the rig: over the whole cycle the hand stays at least
        # 1 cm outside the head; the earlier keys put it up to 3 cm inside)
        aim(rig, 'upper_arm.R', (-0.97, -0.12, 0.22))
        sw = math.sin(t * 2)
        aim(rig, 'forearm.R', (-0.85 + 0.12 * sw, -0.20, 0.55))
        aim(rig, 'hand.R', (-0.75 + 0.18 * sw, -0.25, 0.62))
        key_all(rig, f + 1)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=bpy.data.filepath)
    ap.add_argument('--hero', default='', help='JSON overriding config "hero_pose" (tests)')
    ap.add_argument('--poses', default='', help='JSON {view: {bone: [x, y, z]}} overriding config "view_poses" (tests)')
    a = ap.parse_args(argv)
    cfg = json.load(open(os.path.join(ROOT, 'config', 'morfi.json')))
    if a.hero:
        hp = cfg.setdefault('hero_pose', {})
        for k, v in json.loads(a.hero).items():
            if isinstance(v, dict):
                hp.setdefault(k, {}).update(v)
            else:
                hp[k] = v
    if a.poses:
        for view, bones in json.loads(a.poses).items():
            cfg.setdefault('view_poses', {}).setdefault(view, {}).update(bones)
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
    # rigid followers: parent them all, then put every one back where it was
    # (parenting one object re-evaluates the armature and could move a follower
    # parented just before, which turned one eye 90 degrees in partial builds)
    followers = [(bpy.data.objects.get('Head'), 'head'), (bpy.data.objects.get('Pixels'), 'pixels')]
    for side in ('L', 'R'):
        followers += [(bpy.data.objects.get('Shoe_' + side), 'foot.' + side),
                      (bpy.data.objects.get('Eye_' + side), 'eye.' + side)]
    followers = [(o, b) for o, b in followers if o is not None]  # partial builds (--skip shoes) lack some
    saved = [o.matrix_world.copy() for o, _ in followers]
    for o, b in followers:
        R.bone_parent(o, rig, b)
    bpy.context.view_layer.update()
    for (o, _), mw in zip(followers, saved):
        o.matrix_world = mw
    bpy.context.view_layer.update()
    # actions
    sc = bpy.context.scene
    sc.render.fps = FPS
    new_action(rig, 'Pose_Neutral')
    R.reset_pose(rig)
    key_all(rig, 1)
    new_action(rig, 'Pose_Hero')
    HERO_HEAD.update(cfg.get('hero_pose', {}).get('head', {}))
    HERO_SPINE_TILT[0] = cfg.get('hero_pose', {}).get('spine_tilt', HERO_SPINE_TILT[0])
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
