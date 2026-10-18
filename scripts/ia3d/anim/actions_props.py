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

from . import curves as C
from .clip import Clip
from .motor import WRIST_REST, _rest_hand_frame, orient_keys, prop_space, prop_world, rot_matrix

TAP_D = 0.100           # wrist -> index tip with the "tap" shape (m), for the starting path
PALM_D = 0.045          # wrist -> palm centre (m)
# right index poke: a steep finger (forward-down-left) with the palm down towards him, so the
# curled fingers stay above the surface and only the index pad meets it. (Thumb on top would
# put the curled fingers under the index.)
TAP_FINGERS = (0.60, -0.55, -0.58)
TAP_PALM = (0.25, 0.45, -0.85)
# left palm up under the prop's left edge, fingers to his right (a waiter's carry): the
# wrist and the thick sleeve cuff stay outside the prop, beside it
HOLD_FINGERS = (-0.85, -0.5, 0.0)
# the calculator sits lower and more to his right: fingers further across keep the wrist inside its
# limit (fix_wrists.py) all the way through the typing
CALC_FINGERS = (-0.95, -0.3, 0.0)
SHOULDER_FWD = 24
ELBOW_DROP = -0.30      # pole target lowered while tapping (m)       # shoulders forward (deg) while holding: ~5 cm more reach
# nodding swings the big head's chin down onto the tapping hand: a small nod, a tilt and a turn
# towards the prop, and the eyes do the rest
NOD_WORK = 3.5
TILT_WORK = 5.0


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def _plane(rot):
    """Prop axes in the world: across (local +x), away (local +z), screen normal (local -y)."""
    R = rot_matrix(*rot)
    return R @ [1, 0, 0], R @ [0, 0, 1], R @ [0, -1, 0]


GROW = 12               # frames the prop takes to grow in / shrink out (the palm support is checked in between)
SAG = 0.0               # extra mm the palm hangs below the back face before the support solver lifts it (m)
FADE = 14               # frames the held arm takes to come from / go back to the idle pose


def _prop_scale(hold, n):
    """Prop scale: grows from nothing over GROW frames (with an ease) once the hand is under its
    place, and shrinks away over GROW frames before the hand leaves, so the hand never crosses a
    visible prop and the clip starts and ends without the prop (no pop on the viewer's crossfade)."""
    a, b = hold
    return [(0, 0.0), (a, 0.0), (a + GROW, 1.0), (b - GROW, 1.0), (b, 0.0), (n - 1, 0.0)]


def _hold(c, side, prop, loc, rot, palm_at, fingers, frames, half_t, shape="hold_flat"):
    """Prop resting on a palm: wrist placed from the palm centre (prop-local x, z), the fingers
    along `fingers` (world, in the prop plane); contacts.solve() closes the last millimetres.
    The arm is on IK only from FADE frames before `frames` to FADE frames after it (idle pose
    outside), so the clip starts and ends where the viewer's crossfade from / to Idle needs it."""
    across, away, normal = _plane(rot)
    D = _unit(fingers)
    # the palm is placed a few mm below the contact: the support solver lifts it onto the back face
    # inside its window, and outside it (the prop growing / shrinking) the hand never touches the prop
    centre = prop_world((palm_at[0], half_t + 0.013 + SAG, palm_at[1]), loc, rot)
    wrist = centre - PALM_D * D
    p = prop_space(wrist, loc, rot)
    a, b = frames
    c.reach(side, [(0, None), (a - FADE, None), (a, p), (b, p), (b + FADE, None)])
    rx, ry, rz = orient_keys(side, [(a, D, normal)], prop_rot=rot)
    c.reach_rot(side, rx, ry, rz)
    c.hand(side, [(0, "relaxed"), (a - 6, "relaxed"), (a, shape), (b, shape), (b + FADE - 4, "relaxed")])
    # the support is checked and solved at full size (the prop grows / shrinks around its centre, so a
    # smaller one would not cover the palm); the solved offset is applied over the whole hold, so the
    # hand sits at the same height while the prop grows in and the two never overlap
    c.supports.append({"side": side, "prop": prop, "frames": (a + GROW, b - GROW), "apply": (a, b + 1)})
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


def bpy_free_key(name, loc, rot):
    """World position of a calculator key (Prop_Calc_Key_<row><col>) without Blender."""
    r, col = int(name[-2]), int(name[-1])
    w, h = 0.085, 0.125                                              # build_controls.CALC
    return prop_world(((col - 1) * w * 0.28, -0.02, h * 0.12 - r * h * 0.155), loc, rot)


def tablet():
    """Tutorial on a tablet resting on his left palm: looks at it, taps three spots explaining (a
    nod and a knee bounce on every tap), then turns to the viewer, the free hand opening wide:
    '¿ves? ¡así de fácil!' (7 s)."""
    n = 210
    c = Clip(n)
    c.contacts, c.supports = [], []
    c.life(seed=301, blinks=[24, 128, 182], hands=False, sway=0.5)
    rot = (-99.8, 0.0, 180.0)                   # screen up to his eyes, a little to the viewer
    centre = np.array([0.012, -0.183, 0.347])
    loc = tuple(centre - np.array([0.0, -0.20, 0.36]))
    hold = (16, n - 26)                         # the tablet is in his hand only between these
    # it grows out of nothing while the hand comes up and shrinks away as the hand goes back down
    # (the clip starts and ends in the idle pose: no prop popping in or out on the crossfade)
    c.show("prop_tablet", _prop_scale(hold, n))
    c.place_prop(loc=[(0, loc), (n - 1, loc)], rot=[(0, rot), (n - 1, rot)])
    for s, sx in (("L", 1), ("R", -1)):
        c.add(f"shoulder.{s}.rz", C.keys(n, [(0, 0), (hold[0], -SHOULDER_FWD * sx), (hold[1], -SHOULDER_FWD * sx),
                                             (n - 1, 0)]))
    # left palm under the tablet's left half, fingers to his right and away
    _hold(c, "L", "Prop_Tablet", loc, rot, palm_at=(-0.086, -0.015), fingers=HOLD_FINGERS,
          frames=hold, half_t=0.004)
    # right index: three presses on the screen (prop-local x, z; +x is his right, +z away)
    taps = (46, 82, 116)
    hand_r = _taps(c, "R", "Prop_Tablet_Screen", [(taps[0], (0.045, 0.000)), (taps[1], (0.030, 0.008)),
                                                  (taps[2], (0.052, 0.018))],
                   loc, rot, fingers=TAP_FINGERS, palm=TAP_PALM, start=14, ik_in=34, ik_out=140)
    # FK right arm after the taps: it swings out wide, palm up, towards the tablet: "¿ves?"
    # and, with the tablet gone, the arm drops back to the idle pose over the last frames
    c.arm_fwd("R", [(0, 0), (140, 0), (150, 24), (156, 16), (162, 19), (hold[1] - 6, 17), (n - 1, 0)])
    c.arm_raise("R", [(0, 0), (140, 0), (152, 22), (158, 16), (hold[1] - 6, 15), (n - 1, 0)])
    c.elbow("R", [(0, 0), (140, 0), (150, 52), (156, 40), (162, 46), (hold[1] - 6, 44), (n - 1, 0)])
    c.palm("R", [(0, 0), (140, 0), (152, 60), (hold[1] - 6, 55), (n - 1, 0)])
    c.stretch("R", [(0, 1.0), (144, 1.0), (152, 1.06), (162, 1.03), (hold[1] - 6, 1.03), (n - 1, 1.0)])
    c.hand("R", hand_r + [(144, "relaxed"), (152, "spread"), (170, "open"), (hold[1] - 6, "open"), (n - 8, "relaxed")])
    # he looks at what he is doing: the screen, each spot as he taps it, then at the viewer
    spot = lambda x, z: prop_world((x, 0.0, z), loc, rot)  # noqa: E731
    c.look_at([(0, None), (16, centre), (40, spot(0.045, 0.000)), (76, spot(0.030, 0.008)),
               (110, spot(0.052, 0.018)), (126, centre), (144, None), (n - 1, None)], max_nod=NOD_WORK)
    c.add("head.ry", [(0, 0), (20, TILT_WORK), (124, TILT_WORK), (140, 0), (150, -7), (160, -5), (hold[1] - 6, -4),
                      (n - 1, 0)])
    c.add("chest.rx", [(0, 0), (20, 3), (124, 3), (144, -2), (160, 0)])            # leans into the work
    f = np.arange(n)
    for k, t in enumerate(taps):                 # each tap: a nod, a knee bounce, a tilt
        c.add("head.ry", np.exp(-((f - t - 2) / 4.0) ** 2) * (3.5 if k % 2 else -2.5))
        c.add("head.rx", C.pulse(n, t, [(-3, 0.0), (1, 2.5), (6, -0.5), (10, 0.0)]))
        c.dip(t, depth=0.006, chest=1.0, dur=12)
    # the weight wanders while he explains, then the presentation: lean back, squash and stretch
    # (the weight stays over his left foot through the taps: shifting it right swings the right shoulder
    # away and the reaching hand would sink its knuckles into the tablet)
    c.weight([(0, 0), (30, 0.35), (64, 0.3), (72, 0.1), (100, 0.15), (110, 0.3), (140, 0.3), (150, -0.6),
              (160, -0.45), (hold[1] - 6, -0.4), (n - 1, 0)])
    c.squash(146, -0.05, "head", dur=5)
    c.squash(151, 0.07, "head", dur=16)
    c.dip(162, depth=0.008)
    c.prop("mouth_open", [(0, -0.3), (52, -0.3), (56, 0.4), (62, -0.1), (68, 0.35), (74, -0.3), (90, 0.4),
                          (96, -0.2), (104, 0.35), (112, -0.3), (150, -0.3), (156, 0.6), (164, 0.2),
                          (170, 0.55), (178, 0.1), (186, 0.4), (194, -0.2), (n - 1, -0.1)])
    c.expr([(0, "happy", 0.8), (30, "neutral"), (122, "happy"), (146, "joy"), (n - 1, "happy")])
    c.prop("brow_L", [(0, 0), (40, 0.3), (50, 0.1), (76, 0.3), (86, 0.1), (110, 0.35), (120, 0.1), (148, 0.8),
                      (170, 0.4), (n - 1, 0.2)])
    c.prop("brow_R", [(0, 0), (148, 0.6), (170, 0.3), (n - 1, 0.2)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def calculator():
    """Adds up on a pocket calculator in his left palm, key by key with a head bob, checks the
    result ('¡ah!'), then a little hop and a thumbs up with a wink at the viewer (5.5 s)."""
    n = 165
    c = Clip(n)
    c.contacts, c.supports = [], []
    c.life(seed=311, blinks=[20, 120], hands=False, sway=0.5)
    rot = (-95.0, 0.0, 192.0)                   # keys up, turned a little towards the right hand
    centre = np.array([0.032, -0.197, 0.347])
    loc = tuple(centre - np.array([0.0, -0.20, 0.36]))
    hold = (16, 140)                            # in his hand only between these (grows in, shrinks away)
    c.show("prop_calc", _prop_scale(hold, n))
    c.place_prop(loc=[(0, loc), (n - 1, loc)], rot=[(0, rot), (n - 1, rot)])
    for s, sx in (("L", 1), ("R", -1)):
        c.add(f"shoulder.{s}.rz", C.keys(n, [(0, 0), (hold[0], -SHOULDER_FWD * sx), (hold[1], -SHOULDER_FWD * sx),
                                             (n - 1, 0)]))
    _hold(c, "L", "Prop_Calc", loc, rot, palm_at=(-0.055, -0.025), fingers=CALC_FINGERS,
          frames=hold, half_t=0.008)
    keys = [(34, "Prop_Calc_Key_12"), (52, "Prop_Calc_Key_31"), (70, "Prop_Calc_Key_21"),
            (88, "Prop_Calc_Key_22"), (106, "Prop_Calc_Key_32")]
    hand_r = _taps(c, "R", None, keys, loc, rot, fingers=TAP_FINGERS, palm=TAP_PALM, start=8,
                   ik_in=24, ik_out=124, hold=4, ramp=6)
    # thumbs up (FK) after typing: wound back first, then punched up with a little stretch
    # (held a little, then the arm goes back to the idle pose over the last frames)
    c.arm_raise("R", [(0, 0), (124, 0), (128, -4), (136, 16), (140, 11), (n - 24, 12), (n - 1, 0)])
    c.elbow("R", [(0, 0), (124, 0), (128, 20), (136, 74), (140, 62), (144, 66), (n - 24, 64), (n - 1, 0)])
    c.forearm_in("R", [(0, 0), (124, 0), (136, 18), (n - 24, 18), (n - 1, 0)])
    c.palm("R", [(0, 0), (124, 0), (136, 60), (n - 24, 60), (n - 1, 0)])
    c.stretch("R", [(0, 1.0), (130, 1.0), (136, 1.06), (144, 1.03), (n - 24, 1.03), (n - 1, 1.0)])
    c.hand("R", hand_r + [(126, "relaxed"), (130, "fist"), (133, "fist"), (137, "thumbs_up"), (n - 24, "thumbs_up"),
                          (n - 6, "relaxed")])
    c.add("thumb.R.cx", C.pulse(n, 137, [(-1, 0), (2, -14), (6, 4), (9, 0)]))
    # eyes on the keys he presses (head down as far as his chin allows), then at the viewer
    key_at = lambda k: np.array(bpy_free_key(k, loc, rot))  # noqa: E731
    c.look_at([(0, None), (14, centre)] + [(t - 2, key_at(k)) for t, k in keys] + [(112, centre), (130, None),
                                                                                   (n - 1, None)], max_nod=NOD_WORK)
    c.add("head.ry", [(0, 0), (18, TILT_WORK), (112, TILT_WORK), (132, 0), (142, -8), (n - 24, -6), (n - 1, 0)])
    c.add("chest.rx", [(0, 0), (18, 3), (112, 3), (132, 0)])            # leans into the work
    f = np.arange(n)
    for k, (t, _) in enumerate(keys):           # a little bob of the head with every key
        c.add("head.ry", np.exp(-((f - t - 2) / 3.0) ** 2) * (2.5 if k % 2 else -2.0))
        c.add("head.rx", C.pulse(n, t, [(-3, 0.0), (1, 2.0), (5, -0.5), (8, 0.0)]))
        c.dip(t, depth=0.004, chest=0.8, dur=10)
    c.weight([(0, 0), (30, 0.3), (110, 0.3), (122, 0.0), (140, -0.4), (n - 24, -0.35), (n - 1, 0)])
    c.hop(128, 137, height=0.025, crouch=0.018, stretch=0.06)
    c.squash(138, 0.025, "spine", dur=12)       # no spine squash on this landing: it would tilt the palm under the prop
    c.expr([(0, "neutral"), (16, "thinking", 0.6), (110, "thinking", 0.6), (114, "surprised", 0.6), (124, "joy"),
            (140, "joy"), (143, "wink"), (156, "wink"), (n - 1, "happy")])
    c.prop("mouth_open", [(0, 0), (112, 0), (115, 0.5), (120, 0.1), (n - 1, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


PROPS_ACTIONS = {"Tablet": tablet, "Calculator": calculator}
