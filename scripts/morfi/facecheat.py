"""Profile face cheat: the face slides round the head toward the camera.

In the profile references (03, 05 and the profiles of the turnaround 01) the
head is drawn in pure profile (its outline is exactly that of the profile),
but the near eye, the lens, the brow, the mouth and the celeste cheek are seen
as if the face were turned toward the camera (lens width / height 0.48 and
0.39 against 1.12 from the front). No rigid head can do both; stylised
animation solves it with a per-shot "camera cheat", and so does this module:
every point of the face slides along the head surface (azimuth about the
head's vertical axis, measured from the front)

    phi' = phi + theta * (1 + cos(phi)) / 2

so the centre of the face moves by theta, the sides by theta / 2 and the back
of the head not at all. Points keep their height and their depth relative to
the surface, so the head outline seen from the side does not change: only
what is painted and modelled on it moves.

Every mesh of the face (head, brows, glasses, eyes with their corneas and
highlights) gets, at render time, a shape key "FaceCheat_<view>" with the
exact slide for that shot's theta (config "face_cheat"; blending a single key
would move points along chords and sink the outline). The eyes also get the
rigid transform that best follows their own slide (Kabsch fit), so their
origin stays at the eyeball centre for the gaze, and their key holds only the
small non-rigid rest: the eyeballs bend exactly like the sockets they sit in,
where the flat face wraps round the corner of the head. Nothing is stored in
the master file or the GLB: it is a camera cheat of the per-shot renders.
"""
import math

import numpy as np

FACE = ('Head', 'Brow_L', 'Brow_R', 'Glasses_Frame', 'Glasses_Lens_L', 'Glasses_Lens_R')
EYES = {'Eye_L': ('Cornea_L', 'EyeHighlight_L'), 'Eye_R': ('Cornea_R', 'EyeHighlight_R')}


def key_name(view):
    return 'FaceCheat_' + view


def delta(phi, theta):
    """Azimuth shift (radians) of a point at azimuth phi for a cheat of theta."""
    return theta * 0.5 * (1.0 + np.cos(phi))


def slide(P, shape, theta_deg, depth=1.0):
    """Head-local points (N,3), relative to the head centre -> slid points.
    depth < 1 also flattens the face toward the head surface (see apply)."""
    th = math.radians(theta_deg)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    phi = np.arctan2(x, -y)
    d = delta(phi, th)
    c, s = np.cos(d), np.sin(d)
    # rotate about the vertical axis: azimuth phi -> phi + d (toward +X for d > 0)
    Q = np.stack([x * c - y * s, x * s + y * c, z], 1)
    # keep the height over (or depth under) the surface, as a fraction of the
    # surface radius; scaled by depth on the face, untouched at the back
    S0 = np.linalg.norm(shape.surface(P), axis=1)
    S1 = np.linalg.norm(shape.surface(Q), axis=1)
    h = np.linalg.norm(P, axis=1) / np.maximum(S0, 1e-9) - 1.0
    h = h * (1.0 - (1.0 - depth) * 0.5 * (1.0 + np.cos(phi)))
    return Q * (S1 * (1.0 + h) / np.maximum(np.linalg.norm(Q, axis=1), 1e-9))[:, None]


def _basis(ob):
    me = ob.data
    co = np.empty(len(me.vertices) * 3)
    (me.shape_keys.reference_key.data if me.shape_keys else me.vertices).foreach_get('co', co)
    return co.reshape(-1, 3)


def _xf(M, P):
    return P @ M[:3, :3].T + M[:3, 3]


def _kabsch(P, Q):
    """Rigid 4x4 T with T @ p ~ q."""
    pm, qm = P.mean(0), Q.mean(0)
    U, _, Vt = np.linalg.svd((P - pm).T @ (Q - qm))
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    T = np.eye(4)
    T[:3, :3] = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    T[:3, 3] = qm - T[:3, :3] @ pm
    return T


def apply(view, theta, shape, depth=1.0):
    """Turn the face of this shot by theta degrees. With depth < 1 the relief of
    the face (glasses in front of it, eyeballs out of it) is also flattened
    toward the head surface, so that, as in the drawn profiles, the eye sits
    under its lens instead of peeking out behind the frame at that grazing
    angle. Call after the gaze is set (eyes_look): the eyes are slid as they
    look. The head object's origin is the head centre (build_head). Returns a
    restore() callable."""
    import bpy
    from mathutils import Matrix
    head = bpy.data.objects.get('Head')
    if head is None or not theta:
        return lambda: None
    bpy.context.view_layer.update()
    Hw = np.array(head.matrix_world)
    Hi = np.linalg.inv(Hw)
    name = key_name(view)
    keys = []

    def keyed(ob, T=np.eye(4)):
        """Key = the slide of the basis, in the object's space once moved by T (head frame)."""
        if ob is None or ob.type != 'MESH':
            return
        M = Hi @ np.array(ob.matrix_world)
        Q = slide(_xf(M, _basis(ob)), shape, theta, depth)
        if not ob.data.shape_keys:
            ob.shape_key_add(name='Basis', from_mix=False)
        kb = ob.data.shape_keys.key_blocks.get(name) or ob.shape_key_add(name=name, from_mix=False)
        kb.data.foreach_set('co', _xf(np.linalg.inv(T @ M), Q).ravel())
        keys.append((kb, kb.value))
        kb.value = 1.0

    for n in FACE:
        keyed(bpy.data.objects.get(n))
    undo = []
    for n, kids in EYES.items():
        e = bpy.data.objects.get(n)
        if e is None:
            continue
        M = Hi @ np.array(e.matrix_world)
        P = _xf(M, _basis(e))
        T = _kabsch(P, slide(P, shape, theta, depth))
        for ob in (e,) + tuple(bpy.data.objects.get(k) for k in kids):
            keyed(ob, T)
        undo.append((e, e.matrix_basis.copy()))
        e.matrix_world = Matrix((Hw @ T @ M).tolist())
    bpy.context.view_layer.update()

    def restore():
        for kb, v in keys:
            kb.value = v
        for e, mb in undo:
            e.matrix_basis = mb
        bpy.context.view_layer.update()
    return restore
