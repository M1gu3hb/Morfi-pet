"""Armature, skin weights and procedural animation for Morfi.

Skin weights are derived from the same signed-distance parts that build the
body: every vertex (body or garment) is softly assigned to the closest body
part (torso, arm, hand, leg) and then distributed along that part's bone
chain by projection. Garments therefore deform exactly like the skin they
cover. Rigid pieces (head + face + glasses + pixels, shoes) follow single
bones via bone parenting.
"""
import math
import numpy as np
import bpy
from mathutils import Vector, Quaternion, Euler, Matrix

from . import meshutil as mu
from . import sdf as S
from .body import BodySDF


def _v(a):
    return Vector((float(a[0]), float(a[1]), float(a[2])))


def joint_table(cfg):
    body = BodySDF(cfg)
    b = body.b
    J = {}
    J['root'] = ((0, 0, 0), (0, 0.12, 0))
    J['hips'] = ((0, 0.004, 0.205), (0, 0.004, 0.30))
    J['spine'] = ((0, 0.004, 0.30), (0, 0.006, 0.40))
    J['chest'] = ((0, 0.006, 0.40), (0, 0.010, 0.47))
    J['neck'] = ((0, 0.010, 0.47), (0, 0.016, 0.53))
    hc = cfg['head']['center']
    J['head'] = ((0, 0.016, 0.53), (0, hc[1], hc[2] + 0.2))
    J['pixels'] = ((-0.03, -0.01, 1.0), (-0.03, -0.01, 1.08))
    f = cfg['face']
    from .head import HeadShape
    hs = HeadShape(cfg)
    for (sx, sfx), E in zip(((-1, 'R'), (1, 'L')), hs.eye_centers):
        Ew = np.array(hc) + E
        J['eye.' + sfx] = (tuple(Ew), tuple(Ew + np.array([0, -0.08, 0])))
    for side, sfx in ((1, 'L'), (-1, 'R')):
        s = np.array([side, 1, 1])
        sh = np.array(b['shoulder']) * s
        el = np.array(b['elbow']) * s
        wr = np.array(b['wrist']) * s
        W, D, F, I = body.hand_frame(side)
        J['shoulder.' + sfx] = (tuple(np.array([0.045 * side, 0.006, 0.445])), tuple(sh))
        J['upper_arm.' + sfx] = (tuple(sh), tuple(el))
        J['forearm.' + sfx] = (tuple(el), tuple(wr))
        J['hand.' + sfx] = (tuple(wr), tuple(wr + D * 0.075))
        J['fingers.' + sfx] = (tuple(wr + D * 0.075), tuple(wr + D * 0.115 + I * 0.02))
        J['thumb.' + sfx] = (tuple(W + D * 0.03 + F * 0.04 + I * 0.02), tuple(W + D * 0.06 + F * 0.06 + I * 0.03))
        hp = np.array(b['hip']) * s
        kn = np.array(b['knee']) * s
        an = np.array(b['ankle']) * s
        fc = np.array(b['foot']['c']) * s
        J['thigh.' + sfx] = (tuple(hp), tuple(kn))
        J['shin.' + sfx] = (tuple(kn), tuple(an))
        J['foot.' + sfx] = (tuple(an), tuple(fc + np.array([0, -0.05, -0.01])))
        J['toe.' + sfx] = (tuple(fc + np.array([0, -0.05, -0.01])), tuple(fc + np.array([0, -0.12, -0.01])))
    return J


PARENTS = {
    'hips': 'root', 'spine': 'hips', 'chest': 'spine', 'neck': 'chest', 'head': 'neck',
    'pixels': 'head', 'eye.L': 'head', 'eye.R': 'head',
}
for _s in ('L', 'R'):
    PARENTS.update({
        'shoulder.' + _s: 'chest', 'upper_arm.' + _s: 'shoulder.' + _s, 'forearm.' + _s: 'upper_arm.' + _s,
        'hand.' + _s: 'forearm.' + _s, 'fingers.' + _s: 'hand.' + _s, 'thumb.' + _s: 'hand.' + _s,
        'thigh.' + _s: 'hips', 'shin.' + _s: 'thigh.' + _s, 'foot.' + _s: 'shin.' + _s, 'toe.' + _s: 'foot.' + _s,
    })
CONNECTED = {'upper_arm', 'forearm', 'hand', 'fingers', 'shin', 'foot', 'toe', 'spine', 'chest', 'neck', 'head'}


def build_armature(cfg, col, parent=None):
    J = joint_table(cfg)
    arm = bpy.data.armatures.new('Morfi_Rig')
    arm.display_type = 'OCTAHEDRAL'
    ob = bpy.data.objects.new('Morfi_Rig', arm)
    col.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    bpy.context.view_layer.objects.active = ob
    with bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob]):
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.edit_bones
        for name, (h, t) in J.items():
            b = eb.new(name)
            b.head = _v(h)
            b.tail = _v(t)
            b.roll = 0.0
        for name, par in PARENTS.items():
            eb[name].parent = eb[par]
            base = name.split('.')[0]
            if base in CONNECTED and (eb[name].head - eb[par].tail).length < 1e-4:
                eb[name].use_connect = True
        # deform flags
        for name in ('root', 'pixels', 'eye.L', 'eye.R'):
            eb[name].use_deform = False
        bpy.ops.object.mode_set(mode='OBJECT')
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    return ob


# ------------------------------------------------------------------ weights
def _seg_param(P, a, b):
    a = np.asarray(a)
    b = np.asarray(b)
    ab = b - a
    t = ((P - a) @ ab) / (ab @ ab)
    return t


def _chain_weights(P, chain, J, blend=0.18):
    """Distribute weight along a chain of bones by projection parameter."""
    n = len(chain)
    W = np.zeros((len(P), n))
    # projection onto each segment, choose the closest segment, blend near joints
    dists = []
    ts = []
    for i, bn in enumerate(chain):
        a, b = np.array(J[bn][0]), np.array(J[bn][1])
        t = _seg_param(P, a, b)
        tc = np.clip(t, 0, 1)
        q = a + (b - a) * tc[:, None]
        dists.append(np.linalg.norm(P - q, axis=1))
        ts.append(t)
    dists = np.stack(dists, 1)
    ts = np.stack(ts, 1)
    # soft assignment by distance to segment, sharpened
    sig = 0.012
    dmin = dists.min(1, keepdims=True)
    W = np.exp(-((dists - dmin) / sig) ** 2)
    # extra smoothing across joints using the projection parameter
    for i in range(n - 1):
        ti = ts[:, i]
        tn = ts[:, i + 1]
        near = (ti > 1 - blend) & (tn < blend)
        f = np.clip((ti - (1 - blend)) / (2 * blend) + 0.0, 0, 1)
        W[near, i] = np.maximum(W[near, i], 1 - f[near])
        W[near, i + 1] = np.maximum(W[near, i + 1], f[near])
    W /= W.sum(1, keepdims=True)
    return W


def compute_weights(P, cfg, J):
    """Return dict bone -> weight array for points P (N,3) in world space."""
    body = BodySDF(cfg)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    PP = (x, y, z)
    parts = {
        'torso': body.torso(PP),
        'arm.L': body._arm(PP, 1), 'arm.R': body._arm(PP, -1),
        'hand.L': body._hand(PP, 1), 'hand.R': body._hand(PP, -1),
        'leg.L': body._leg(PP, 1), 'leg.R': body._leg(PP, -1),
    }
    names = list(parts)
    D = np.stack([parts[k] for k in names], 1)
    tau = 0.008
    A = np.exp(-(D - D.min(1, keepdims=True)) / tau)
    A /= A.sum(1, keepdims=True)
    out = {}

    def add(bone, w):
        out[bone] = out.get(bone, 0) + w

    # torso chain by height (smooth piecewise linear)
    zt = z
    tor = A[:, names.index('torso')]
    keys = [(0.17, 'hips'), (0.30, 'spine'), (0.41, 'chest'), (0.49, 'neck'), (0.56, 'head')]
    zs = np.array([k[0] for k in keys])
    for i, (zk, bn) in enumerate(keys):
        left = zs[i - 1] if i > 0 else -10
        right = zs[i + 1] if i < len(keys) - 1 else 10
        w = np.where(zt <= zk, np.clip((zt - left) / max(zk - left, 1e-6), 0, 1), np.clip((right - zt) / max(right - zk, 1e-6), 0, 1))
        if i == 0:
            w = np.where(zt <= zk, 1.0, w)
        if i == len(keys) - 1:
            w = np.where(zt >= zk, 1.0, w)
        add(bn, tor * w)
    for side, sfx in ((1, 'L'), (-1, 'R')):
        aw = A[:, names.index('arm.' + sfx)]
        cw = _chain_weights(P, ['shoulder.' + sfx, 'upper_arm.' + sfx, 'forearm.' + sfx, 'hand.' + sfx], J)
        for i, bn in enumerate(['shoulder.' + sfx, 'upper_arm.' + sfx, 'forearm.' + sfx, 'hand.' + sfx]):
            add(bn, aw * cw[:, i])
        hw = A[:, names.index('hand.' + sfx)]
        # fingers vs thumb vs palm
        hand_parts = {
            'hand.' + sfx: S.sd_ellipsoid(PP, np.array(J['hand.' + sfx][0]) * 0 + (np.array(J['hand.' + sfx][0]) + np.array(J['hand.' + sfx][1])) / 2, (0.045, 0.055, 0.05)),
        }
        fa, fb = np.array(J['fingers.' + sfx][0]), np.array(J['fingers.' + sfx][1])
        ta, tb = np.array(J['thumb.' + sfx][0]), np.array(J['thumb.' + sfx][1])
        df = S.sd_capsule(PP, fa - (fb - fa) * 0.3, fb, 0.03)
        dt = S.sd_capsule(PP, ta, tb, 0.022)
        dh = hand_parts['hand.' + sfx]
        HD = np.stack([dh, df, dt], 1)
        HA = np.exp(-(HD - HD.min(1, keepdims=True)) / 0.006)
        HA /= HA.sum(1, keepdims=True)
        add('hand.' + sfx, hw * HA[:, 0])
        add('fingers.' + sfx, hw * HA[:, 1])
        add('thumb.' + sfx, hw * HA[:, 2])
        lw = A[:, names.index('leg.' + sfx)]
        cw = _chain_weights(P, ['thigh.' + sfx, 'shin.' + sfx, 'foot.' + sfx, 'toe.' + sfx], J)
        for i, bn in enumerate(['thigh.' + sfx, 'shin.' + sfx, 'foot.' + sfx, 'toe.' + sfx]):
            add(bn, lw * cw[:, i])
    return out


def skin_object(ob, rig, cfg, J, prune=0.01):
    M = np.array(ob.matrix_world)
    P = mu.get_verts(ob)
    Pw = P @ M[:3, :3].T + M[:3, 3]
    W = compute_weights(Pw, cfg, J)
    names = list(W)
    Wm = np.stack([W[n] for n in names], 1)
    # keep the 4 strongest influences per vertex, normalised
    idx = np.argsort(-Wm, axis=1)[:, :4]
    keep = np.zeros_like(Wm, bool)
    np.put_along_axis(keep, idx, True, axis=1)
    Wm = np.where(keep & (Wm > prune), Wm, 0)
    Wm /= np.maximum(Wm.sum(1, keepdims=True), 1e-9)
    ob.vertex_groups.clear()
    for j, n in enumerate(names):
        vg = ob.vertex_groups.new(name=n)
        nz = np.nonzero(Wm[:, j])[0]
        # group by weight value for speed
        for i in nz:
            vg.add([int(i)], float(Wm[i, j]), 'REPLACE')
    mod = ob.modifiers.new('Armature', 'ARMATURE')
    mod.object = rig
    mod.use_deform_preserve_volume = True
    # glTF skins expect the armature as the mesh parent
    mw = ob.matrix_world.copy()
    ob.parent = rig
    ob.parent_type = 'OBJECT'
    ob.matrix_parent_inverse = rig.matrix_world.inverted()
    bpy.context.view_layer.update()
    ob.matrix_world = mw
    return ob


def bone_parent(ob, rig, bone):
    mw = ob.matrix_world.copy()
    ob.parent = rig
    ob.parent_type = 'BONE'
    ob.parent_bone = bone
    bpy.context.view_layer.update()
    ob.matrix_world = mw


# ------------------------------------------------------------------ posing helpers
def rot(pb, axis, deg):
    q = Quaternion(Vector(axis), math.radians(deg))
    pb.rotation_quaternion = q @ pb.rotation_quaternion


def reset_pose(rig):
    for pb in rig.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)


def key_pose(rig, frame):
    for pb in rig.pose.bones:
        pb.keyframe_insert('rotation_quaternion', frame=frame)
        pb.keyframe_insert('location', frame=frame)


def world_rot(rig, pb, axis_world, deg):
    """Rotate a pose bone about a world-space axis (rest-pose based)."""
    M = (rig.matrix_world @ pb.bone.matrix_local).to_3x3()
    ax_local = (M.inverted() @ Vector(axis_world)).normalized()
    q = Quaternion(ax_local, math.radians(deg))
    pb.rotation_quaternion = pb.rotation_quaternion @ q
