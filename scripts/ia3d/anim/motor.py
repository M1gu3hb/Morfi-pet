"""Morfi's motor: hand shapes, facial expressions and the reach / prop helpers.

Everything here writes Clip channels, so it layers with the rest of an action:

    c.hand("R", [(0, "relaxed"), (12, "point"), (40, "count2")])
    c.expr([(0, "neutral"), (10, "surprised"), (30, "joy")])
    c.reach("L", [(0, None), (10, (0.12, -0.24, 0.40)), (60, (0.12, -0.24, 0.40)), (70, None)])
    c.show("prop_tablet", [(0, 0), (8, 1)])

Hands have a thumb and three fingers (index, middle, ring), 3 phalanges each.
Finger values are degrees: + curls into the palm, - extends past straight.
"""
import numpy as np

from . import curves as C

FINGER_NAMES = ("index", "middle", "ring")

# per finger (base, middle, tip) curl; "fan" spreads the fingers apart (deg);
# thumb = (curl seg 1, 2, 3) and "thumb_out" swings it away from the palm (deg)
HAND_SHAPES = {
    "rest": {"index": (0, 0, 0), "middle": (0, 0, 0), "ring": (0, 0, 0), "thumb": (0, 0, 0)},
    "relaxed": {"index": (14, 18, 12), "middle": (16, 20, 14), "ring": (18, 22, 15), "thumb": (6, 10, 8)},
    "fist": {"index": (68, 78, 62), "middle": (68, 78, 62), "ring": (68, 78, 62), "thumb": (18, 38, 36)},
    "open": {"index": (-16, -18, -12), "middle": (-16, -18, -12), "ring": (-16, -18, -12), "thumb": (-24, -14, -6),
             "fan": 9, "thumb_out": 12},
    "stop": {"index": (-20, -20, -14), "middle": (-20, -20, -14), "ring": (-20, -20, -14), "thumb": (-14, -8, -4),
             "fan": 3},
    "point": {"index": (-22, -22, -16), "middle": (66, 78, 62), "ring": (66, 78, 62), "thumb": (20, 40, 34)},
    # poke: index nearly straight, the others tucked tight so they stay clear of the surface
    "tap": {"index": (-4, 4, 6), "middle": (78, 94, 72), "ring": (80, 96, 74), "thumb": (24, 46, 40)},
    "count1": {"index": (-24, -24, -18), "middle": (66, 78, 62), "ring": (66, 78, 62), "thumb": (22, 42, 36)},
    "count2": {"index": (-24, -24, -18), "middle": (-24, -24, -18), "ring": (66, 78, 62), "thumb": (22, 42, 36),
               "fan": 7},
    "count3": {"index": (-24, -24, -18), "middle": (-24, -24, -18), "ring": (-24, -24, -18), "thumb": (24, 44, 38),
               "fan": 7},
    "count4": {"index": (-24, -24, -18), "middle": (-24, -24, -18), "ring": (-24, -24, -18), "thumb": (-24, -14, -6),
               "fan": 8, "thumb_out": 12},
    "thumbs_up": {"index": (68, 78, 62), "middle": (68, 78, 62), "ring": (68, 78, 62), "thumb": (-26, -20, -10),
                  "thumb_out": 6},
    "grip": {"index": (44, 52, 40), "middle": (46, 54, 42), "ring": (48, 56, 44), "thumb": (8, 28, 26)},
    "pinch": {"index": (34, 46, 36), "middle": (52, 62, 48), "ring": (58, 68, 52), "thumb": (14, 30, 30)},
    # the rest pose already curls the fingers ~55 deg: a flat palm needs them opened
    "hold_flat": {"index": (-15, -17, -12), "middle": (-15, -17, -12), "ring": (-13, -15, -10), "thumb": (-12, -4, 0),
                  "fan": 3},
    "claw": {"index": (20, 50, 45), "middle": (22, 52, 46), "ring": (24, 54, 48), "thumb": (6, 22, 22),
             "fan": 10, "thumb_out": 10},
}

# facial expressions as rig face properties (anything not listed stays at its default)
EXPRESSIONS = {
    "neutral": {},
    "happy": {"smile": 0.75, "squint": 0.3, "brow_L": 0.2, "brow_R": 0.2},
    "joy": {"smile": 1.0, "mouth_open": 0.6, "teeth": 0.7, "squint": 0.5, "brow_L": 0.45, "brow_R": 0.45,
            "pupil": 0.2},
    "laugh": {"smile": 1.0, "mouth_open": 1.0, "teeth": 0.8, "blink_L": 1.0, "blink_R": 1.0, "brow_L": 0.55,
              "brow_R": 0.55},
    "sad": {"smile": -0.8, "mouth_open": -0.55, "brow_in_L": 0.9, "brow_in_R": 0.9, "brow_L": -0.1, "brow_R": -0.1,
            "lid_drop": 0.18, "lid_angle": -0.45, "gaze_y": -0.35},
    "angry": {"smile": -0.6, "mouth_open": -0.35, "brow_in_L": -1.0, "brow_in_R": -1.0, "brow_L": -0.45,
              "brow_R": -0.45, "lid_drop": 0.16, "lid_angle": 0.55, "pupil": -0.25},
    "scared": {"smile": -0.5, "mouth_open": 0.35, "mouth_round": 0.45, "brow_L": 0.9, "brow_R": 0.9, "brow_in_L": 0.85,
               "brow_in_R": 0.85, "pupil": -0.9},
    "surprised": {"mouth_open": 0.75, "mouth_round": 1.0, "brow_L": 1.0, "brow_R": 1.0, "pupil": -0.45},
    "calm": {"blink_L": 1.0, "blink_R": 1.0, "eye_calm": 1.0, "smile": 0.45, "brow_in_L": 0.12, "brow_in_R": 0.12},
    "thinking": {"mouth_side": 0.6, "mouth_open": -0.75, "smile": 0.1, "brow_L": 0.6, "brow_R": -0.25, "gaze_x": 0.45,
                 "gaze_y": 0.55, "lid_drop": 0.08},
    "skeptical": {"brow_L": 0.7, "brow_R": -0.5, "brow_in_R": -0.4, "mouth_side": -0.7, "mouth_open": -0.8,
                  "smile": -0.15, "lid_drop": 0.3, "gaze_x": -0.4},
    "smug": {"lid_drop": 0.38, "smile": 0.6, "mouth_side": 0.4, "mouth_open": -0.5, "brow_L": 0.3, "brow_R": 0.1},
    "love": {"blink_L": 1.0, "blink_R": 1.0, "smile": 0.9, "brow_in_L": 0.5, "brow_in_R": 0.5, "pupil": 1.0},
    "wink": {"blink_L": 1.0, "smile": 0.9, "squint": 0.35, "mouth_side": 0.3, "brow_R": 0.45},
    "determined": {"brow_in_L": -0.7, "brow_in_R": -0.7, "lid_angle": 0.35, "lid_drop": 0.12, "smile": 0.3,
                   "mouth_open": -0.6},
    "confused": {"brow_L": 0.8, "brow_R": -0.2, "brow_in_R": 0.4, "mouth_side": -0.5, "mouth_round": 0.4,
                 "smile": -0.2},
    "shy": {"smile": 0.5, "mouth_open": -0.5, "brow_in_L": 0.6, "brow_in_R": 0.6, "gaze_y": -0.5, "gaze_x": 0.3,
            "squint": 0.2},
    "sleepy": {"lid_drop": 0.55, "brow_in_L": 0.2, "brow_in_R": 0.2, "mouth_open": -0.3},
}

# rest position of each wrist (hand bone head) in the project frame; IK targets are
# given as absolute points and turned into offsets of the hand_ik bones
WRIST_REST = {"L": np.array([0.283, 0.039, 0.315]), "R": np.array([-0.283, 0.039, 0.315])}
PROP_REST = np.array([0.0, -0.20, 0.36])
SGN = {"L": 1.0, "R": -1.0}


def _shape(name_or_dict):
    if isinstance(name_or_dict, dict):
        base = dict(HAND_SHAPES["rest"])
        base.update(name_or_dict)
        return base
    return HAND_SHAPES[name_or_dict]


def hand_channels(clip, side, keys):
    """keys: [(frame, shape name or dict), ...] -> finger channels (smoothly interpolated)."""
    shapes = [(f, _shape(s)) for f, s in keys]
    for fname in FINGER_NAMES:
        for seg in range(3):
            pts = [(f, s[fname][seg]) for f, s in shapes]
            clip.add(f"{fname}.{seg + 1:02d}.{side}.cx", pts)
    # fan: index towards the thumb, ring away from it (mirrored per side)
    fan = [(f, s.get("fan", 0.0)) for f, s in shapes]
    clip.add(f"index.01.{side}.cz", fan, SGN[side])
    clip.add(f"ring.01.{side}.cz", fan, -SGN[side])
    clip.add(f"middle.01.{side}.cz", [(f, 0.0) for f, _ in shapes])
    for seg, bname in enumerate((f"thumb.{side}", f"thumb.02.{side}", f"thumb.03.{side}")):
        clip.add(f"{bname}.cx", [(f, s["thumb"][seg]) for f, s in shapes])
    clip.add(f"thumb.{side}.cz", [(f, s.get("thumb_out", 0.0)) for f, s in shapes], SGN[side])


def expr_channels(clip, keys, scale=1.0):
    """keys: [(frame, expression name or dict[, weight]), ...] -> face property channels."""
    rows = []
    for k in keys:
        f, e = k[0], k[1]
        w = k[2] if len(k) > 2 else 1.0
        rows.append((f, EXPRESSIONS[e] if isinstance(e, str) else e, w))
    props = sorted({p for _, e, _ in rows for p in e})
    for p in props:
        clip.prop(p, [(f, e.get(p, 0.0) * w) for f, e, w in rows], scale)


def reach_channels(clip, side, keys, ramp=None):
    """IK reach. keys: [(frame, point or None[, weight]), ...]; point = wrist target in the
    project frame (where the hand bone's head should go, prop at rest); None = FK.
    The IK weight eases between keys like everything else."""
    pts, ws = [], []
    last = WRIST_REST[side]
    for k in keys:
        f, p = k[0], k[1]
        w = (k[2] if len(k) > 2 else 1.0) if p is not None else 0.0
        if p is not None:
            last = np.asarray(p, float)
        pts.append((f, last - WRIST_REST[side]))
        ws.append((f, w))
    for i, ax in enumerate("xyz"):
        clip.add(f"hand_ik.{side}.l{ax}", [(f, d[i]) for f, d in pts])
    clip.add(f"ik.{side}", ws)


def reach_rot(clip, side, rx=None, ry=None, rz=None):
    """Orientation of the hand while on IK (world rest axes, degrees, like the body)."""
    for ax, v in (("rx", rx), ("ry", ry), ("rz", rz)):
        if v is not None:
            clip.add(f"hand_ik.{side}.{ax}", v)


def stretch_channels(clip, side, keys):
    """Cartoon reach: arm segments up to ~12 % longer (1.0 = rest)."""
    clip.add(f"upper_arm.{side}.sy", keys)
    clip.add(f"forearm.{side}.sy", keys)


def show_prop(clip, bone, keys):
    clip.add(f"{bone}.s", keys)


def place_prop(clip, loc=None, rot=None):
    """Prop bone offset from its rest spot in front of the chest (m) and rotation (deg)."""
    if loc is not None:
        for i, ax in enumerate("xyz"):
            clip.add(f"prop.l{ax}", [(f, v[i]) for f, v in loc])
    if rot is not None:
        for i, ax in enumerate(("rx", "ry", "rz")):
            clip.add(f"prop.{ax}", [(f, v[i]) for f, v in rot])


def _rest_hand_frame(side):
    """Rest direction of the fingers (D) and of the palm (N) of each hand (see build_hands.py)."""
    sx = SGN[side]
    D = np.array([0.592 * sx, 0.046, -0.805])
    D /= np.linalg.norm(D)
    F = np.array([0.0, -1.0, 0.0])
    F -= (F @ D) * D
    F /= np.linalg.norm(F)
    N = np.cross(D, F)
    if np.sign(N[0]) == sx:
        N = -N
    return D, N


def rot_matrix(rx, ry, rz):
    """Rotation of a (rx, ry, rz) world-rest-axes channel triple (degrees): Rz Rx Ry."""
    a, b, g = np.radians([rx, ry, rz])
    Rx = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    Ry = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
    Rz = np.array([[np.cos(g), -np.sin(g), 0], [np.sin(g), np.cos(g), 0], [0, 0, 1]])
    return Rz @ Rx @ Ry


def _angles(R):
    a = np.arcsin(np.clip(R[2, 1], -1, 1))
    b = np.arctan2(-R[2, 0], R[2, 2])
    g = np.arctan2(-R[0, 1], R[1, 1])
    return tuple(float(np.degrees(v)) for v in (a, b, g))


def _closest(r, prev):
    """Of the two angle triples giving the same rotation (and their 360 turns), the one
    nearest the previous key, so interpolated keys turn the short way."""
    if prev is None:
        return r
    a, b, g = r
    best = None
    for cand in ((a, b, g), (180 - a, b + 180, g + 180)):
        c = tuple(v + 360 * round((p - v) / 360) for v, p in zip(cand, prev))
        dist = sum((v - p) ** 2 for v, p in zip(c, prev))
        if best is None or dist < best[0]:
            best = (dist, c)
    return best[1]


def hand_orient(side, fingers_dir, palm_dir, prop_rot=None):
    """World-rest-axes angles (rx, ry, rz, degrees) for hand_ik so the fingers point along
    `fingers_dir` with the palm facing `palm_dir` (project frame: -Y is Morfi's front).
    hand_ik bones are children of the prop bone: pass the prop's rotation when it is turned,
    the directions stay in the world frame."""
    D0, N0 = _rest_hand_frame(side)
    D = np.array(fingers_dir, float)
    D /= np.linalg.norm(D)
    N = np.array(palm_dir, float)
    N -= (N @ D) * D
    N /= np.linalg.norm(N)
    A = np.stack([D0, N0, np.cross(D0, N0)], 1)
    B = np.stack([D, N, np.cross(D, N)], 1)
    R = B @ A.T                                   # rest frame -> wanted frame
    if prop_rot is not None:
        R = rot_matrix(*prop_rot).T @ R
    return _angles(R)                             # R = Rz(g) Rx(a) Ry(b), as rigmap composes


def orient_keys(side, keys, prop_rot=None):
    """keys: [(frame, fingers_dir, palm_dir), ...] -> rx/ry/rz key lists for reach_rot."""
    rows, prev = [], None
    for f, d, n in keys:
        r = _closest(hand_orient(side, d, n, prop_rot), prev)
        rows.append((f, r))
        prev = r
    return ([(f, r[0]) for f, r in rows], [(f, r[1]) for f, r in rows], [(f, r[2]) for f, r in rows])


def prop_space(point, prop_loc=(0, 0, 0), prop_rot=(0, 0, 0)):
    """World point (prop placed with these channels) -> the 'prop at rest' point that
    reach() expects, so a hand target follows the prop if it moves later."""
    head = PROP_REST + np.asarray(prop_loc, float)
    return PROP_REST + rot_matrix(*prop_rot).T @ (np.asarray(point, float) - head)


def prop_world(local, prop_loc=(0, 0, 0), prop_rot=(0, 0, 0)):
    """Point in a prop object's own frame -> world (props are built at the prop bone head)."""
    return PROP_REST + np.asarray(prop_loc, float) + rot_matrix(*prop_rot) @ np.asarray(local, float)


def bounce_blink(n, times):
    return C.blink_track(n, times)
