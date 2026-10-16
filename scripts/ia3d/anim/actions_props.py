"""Actions with props: a tablet tutorial and a calculator.

The props hang from the `prop` bone (in front of the chest, see build_controls.py) and so do
both IK hand targets: a hand holding a prop stays on it whatever the prop does. Poses are
written in the world frame (Morfi faces -Y, his left is +X) and converted to prop space.

Morfi's arms are short: a wrist reaches ~20 cm from the shoulder, i.e. 3-6 cm in front of
his belly. So a prop rests on his left palm a little left of centre, in front of the belly,
and the right index reaches across to it. The exact contacts are not hand-tuned: each press
and each support is declared (clip.contacts / clip.supports) and anim/contacts.py moves the
wrist after baking until the fingertip pad lands on the screen / key and the palm touches
the prop's back, then checks every frame for overlaps (check_props.py).
"""
import numpy as np

from .clip import Clip
from .motor import WRIST_REST, _rest_hand_frame, orient_keys, prop_space, prop_world, rot_matrix

TAP_D = 0.100           # wrist -> index tip with the "tap" shape (m), for the starting path
PALM_D = 0.045          # wrist -> palm centre (m)
# right index poke: a steep finger (forward-down-left) with the palm down towards him, so the
# curled fingers stay above the surface and only the index pad meets it. (Thumb on top would
# put the curled fingers under the index.)
TAP_FINGERS = (0.55, -0.45, -0.70)
TAP_PALM = (0.25, 0.45, -0.85)
# left palm up under the prop's left edge, fingers to his right (a waiter's carry): the
# wrist and the thick sleeve cuff stay outside the prop, beside it
HOLD_FINGERS = (-0.85, -0.5, 0.0)
SHOULDER_FWD = 24
ELBOW_DROP = -0.30      # pole target lowered while tapping (m)       # shoulders forward (deg) while holding: ~5 cm more reach
# nodding swings the big head's chin down onto the hands: look down mostly with the eyes
NOD = 0


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def _plane(rot):
    """Prop axes in the world: across (local +x), away (local +z), screen normal (local -y)."""
    R = rot_matrix(*rot)
    return R @ [1, 0, 0], R @ [0, 0, 1], R @ [0, -1, 0]


def _hold(c, side, prop, loc, rot, palm_at, fingers, frames, half_t, shape="hold_flat"):
    """Prop resting on a palm: wrist placed from the palm centre (prop-local x, z), the fingers
    along `fingers` (world, in the prop plane); contacts.solve() closes the last millimetres."""
    across, away, normal = _plane(rot)
    D = _unit(fingers)
    centre = prop_world((palm_at[0], half_t + 0.013, palm_at[1]), loc, rot)
    wrist = centre - PALM_D * D
    p = prop_space(wrist, loc, rot)
    a, b = frames
    c.reach(side, [(a, p), (b, p)])
    rx, ry, rz = orient_keys(side, [(a, D, normal)], prop_rot=rot)
    c.reach_rot(side, rx, ry, rz)
    c.hand(side, [(a, shape), (b, shape)])
    c.supports.append({"side": side, "prop": prop, "frames": (a, b)})
    return p


def _taps(c, side, target, presses, loc, rot, fingers, palm, start, ik_in, ik_out, hold=5, ramp=7,
          shape="tap"):
    """Index presses at prop-local points [(frame, (x, z) or key object name), ...]. The arm
    switches to IK where it hangs (no visible jump), rises beside the head and comes over the
    prop from above, never through it; contacts.solve() then builds the hover-press-lift path
    and lands the pad exactly on each point. After the presses it goes back the same way.

    Returns the hand-shape keys up to the last press: the action appends what the hand does
    next and calls c.hand once (Clip channels add up, so two c.hand calls would sum)."""
    D, N = _unit(fingers), _unit(palm)
    across, away, normal = _plane(rot)
    D0, N0 = _rest_hand_frame(side)               # hanging hand: turns only once it rises
    rx, ry, rz = orient_keys(side, [(start + 5, D0, N0), (ik_in - 7, D, N), (ik_out - 6, D, N), (ik_out, D0, N0)],
                             prop_rot=rot)
    c.reach_rot(side, rx, ry, rz)
    pts = []
    for f, where in presses:
        obj, local = (where, None) if isinstance(where, str) else (target, where)
        c.contacts.append({"side": side, "tip": f"index.03.{side}", "target": obj, "local": local,
                           "frames": (f, f + hold), "ramp": ramp})
        pts.append(local if local is not None else (0.0, 0.0))
    first = prop_world((pts[0][0], -0.03, pts[0][1]), loc, rot) - TAP_D * D + normal * 0.02
    hang = WRIST_REST[side] + np.array([0.0, -0.02, 0.0])
    out = np.array([np.sign(hang[0]) * 0.03, -0.02, 0.0])   # rise beside the jaw, not under it
    mid = hang + 0.55 * (first - hang) + out
    mid[2] = max(first[2], hang[2])
    home, side_p, mid_p = (prop_space(p, loc, rot) for p in (first, hang, mid))
    c.reach(side, [(0, side_p, 0.0), (start, side_p, 0.0), (start + 5, side_p, 1.0), (ik_in - 7, mid_p, 1.0),
                   (ik_in, home, 1.0), (ik_out - 14, home, 1.0), (ik_out - 6, mid_p, 1.0), (ik_out, mid_p, 0.0)])
    # elbow down by the side while tapping: the forearm rises to the hand instead of lying
    # level under the chin
    c.add(f"elbow_pole.{side}.lz", [(0, 0.0), (start + 5, 0.0), (ik_in, ELBOW_DROP), (ik_out - 6, ELBOW_DROP),
                                    (ik_out, 0.0)])
    return [(0, "relaxed"), (ik_in - 8, shape), (ik_out - 8, shape)]


def tablet():
    """Tutorial on a tablet resting on his left palm: looks at it, taps three spots explaining,
    then looks up at the viewer: '¿ves? así de fácil' (7 s)."""
    n = 210
    c = Clip(n)
    c.contacts, c.supports = [], []
    c.life(seed=301, blinks=[24, 128, 182], hands=False, sway=0.5)
    rot = (-99.8, 0.0, 180.0)                   # screen up to his eyes, a little to the viewer
    centre = np.array([0.012, -0.183, 0.347])
    loc = tuple(centre - np.array([0.0, -0.20, 0.36]))
    c.show("prop_tablet", [(0, 1.0), (n - 1, 1.0)])
    c.place_prop(loc=[(0, loc), (n - 1, loc)], rot=[(0, rot), (n - 1, rot)])
    for s, sx in (("L", 1), ("R", -1)):
        c.add(f"shoulder.{s}.rz", -SHOULDER_FWD * sx)
    # left palm under the tablet's left half, fingers to his right and away
    _hold(c, "L", "Prop_Tablet", loc, rot, palm_at=(-0.086, -0.015), fingers=HOLD_FINGERS,
          frames=(0, n - 1), half_t=0.004)
    # right index: three presses on the screen (prop-local x, z; +x is his right, +z away)
    hand_r = _taps(c, "R", "Prop_Tablet_Screen", [(46, (0.040, -0.020)), (82, (0.012, 0.004)), (116, (0.052, 0.014))],
                   loc, rot, fingers=TAP_FINGERS, palm=TAP_PALM, start=14, ik_in=34, ik_out=140)
    # FK right arm after the taps: open hand towards the tablet, "¿ves?"
    c.arm_fwd("R", [(0, 0), (140, 0), (158, 18), (n - 1, 15)])
    c.elbow("R", [(0, 0), (140, 0), (158, 48), (n - 1, 44)])
    c.palm("R", [(0, 0), (140, 0), (158, 55), (n - 1, 50)])
    c.hand("R", hand_r + [(144, "relaxed"), (158, "open"), (n - 1, "open")])
    # head and eyes on the screen while working, then to the viewer
    c.add("head.rx", [(0, NOD - 2), (24, NOD), (124, NOD), (144, 0), (n - 1, -2)])
    c.add("head.rz", [(0, 4), (24, 6), (124, 6), (144, 0), (n - 1, 0)])
    c.prop("gaze_y", [(0, -0.6), (24, -0.9), (124, -0.9), (142, 0.0), (n - 1, 0.0)])
    c.prop("gaze_x", [(0, 0.1), (40, 0.05), (78, 0.15), (112, 0.0), (130, 0.0)])
    for t in (46, 82, 116):
        c.add("head.ry", np.exp(-((np.arange(n) - t - 2) / 4.0) ** 2) * 2.5)
    c.prop("mouth_open", [(0, -0.3), (52, -0.3), (56, 0.4), (62, -0.1), (68, 0.35), (74, -0.3), (90, 0.4),
                          (96, -0.2), (104, 0.35), (112, -0.3), (150, -0.3), (156, 0.6), (164, 0.2),
                          (170, 0.55), (178, 0.1), (186, 0.4), (194, -0.2), (n - 1, -0.1)])
    c.expr([(0, "happy", 0.8), (30, "neutral"), (122, "happy"), (146, "joy"), (n - 1, "happy")])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def calculator():
    """Adds up on a pocket calculator in his left palm, key by key, then smiles at the viewer
    with a thumbs up (5.5 s)."""
    n = 165
    c = Clip(n)
    c.contacts, c.supports = [], []
    c.life(seed=311, blinks=[20, 120], hands=False, sway=0.5)
    rot = (-95.0, 0.0, 192.0)                   # keys up, turned a little towards the right hand
    centre = np.array([0.032, -0.197, 0.347])
    loc = tuple(centre - np.array([0.0, -0.20, 0.36]))
    c.show("prop_calc", [(0, 1.0), (n - 1, 1.0)])
    c.place_prop(loc=[(0, loc), (n - 1, loc)], rot=[(0, rot), (n - 1, rot)])
    for s, sx in (("L", 1), ("R", -1)):
        c.add(f"shoulder.{s}.rz", -SHOULDER_FWD * sx)
    _hold(c, "L", "Prop_Calc", loc, rot, palm_at=(-0.055, -0.025), fingers=HOLD_FINGERS,
          frames=(0, n - 1), half_t=0.008)
    keys = [(34, "Prop_Calc_Key_12"), (52, "Prop_Calc_Key_31"), (70, "Prop_Calc_Key_21"),
            (88, "Prop_Calc_Key_22"), (106, "Prop_Calc_Key_32")]
    hand_r = _taps(c, "R", None, keys, loc, rot, fingers=TAP_FINGERS, palm=TAP_PALM, start=8,
                   ik_in=24, ik_out=124, hold=4, ramp=6)
    # thumbs up (FK) after typing
    c.arm_raise("R", [(0, 0), (124, 0), (140, 12), (n - 1, 12)])
    c.elbow("R", [(0, 0), (124, 0), (140, 66), (n - 1, 62)])
    c.forearm_in("R", [(0, 0), (124, 0), (140, 18), (n - 1, 18)])
    c.palm("R", [(0, 0), (124, 0), (140, 60), (n - 1, 60)])
    c.hand("R", hand_r + [(126, "relaxed"), (138, "thumbs_up"), (n - 1, "thumbs_up")])
    c.add("head.rx", [(0, NOD - 2), (18, NOD - 6), (112, NOD - 6), (132, 0), (n - 1, -2)])   # chin up off the sleeve
    c.add("head.rz", [(0, 6), (18, 9), (112, 9), (132, 0), (n - 1, 0)])
    c.prop("gaze_y", [(0, -0.6), (18, -0.9), (112, -0.9), (130, 0.0), (n - 1, 0.0)])
    c.prop("gaze_x", [(0, 0.2), (18, 0.25), (112, 0.25), (130, 0.0)])
    for t, _ in keys:
        c.add("head.ry", np.exp(-((np.arange(n) - t - 2) / 3.0) ** 2) * 1.5)
    c.expr([(0, "neutral"), (16, "thinking", 0.6), (110, "thinking", 0.6), (128, "joy"), (n - 1, "happy")])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


PROPS_ACTIONS = {"Tablet": tablet, "Calculator": calculator}
