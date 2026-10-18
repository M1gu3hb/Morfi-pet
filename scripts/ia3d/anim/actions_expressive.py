"""Expressive actions built with the motor (hands, face, IK reach, stretch), from the
reference shots in /shoots: counting, thumbs up, pointing, idea, thinking, laughing,
surprise, sadness, anger, fear, calm, celebration, shrug and running.

Contact poses (hand on chin, hands on cheeks, hand on belly) were placed with
pose_probe.py and are verified frame by frame with check_props.py / check_clearance.py.
IK targets sit inside the reach cap (contacts.MAX_REACH, or the clip's max_reach): a target
beyond it is pulled back and an overshoot keyed past it would be flattened, so the hits and
overshoots of a reaching hand come from the body (lean, shoulder) or stay inside the reach.
After the bake every arm is rebaked to FK with a volume-kept stretch (contacts.rebake_arms).
"""
import numpy as np

from . import curves as C
from .clip import Clip
from .motor import orient_keys

UP, FRONT = (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)
SHOULDER = {"L": np.array([0.154, 0.057, 0.449]), "R": np.array([-0.154, 0.057, 0.449])}
ARM = 0.196                                       # upper arm + forearm rest length (m)


def within(side, point, frac=1.0):
    """The wrist target moved towards the shoulder (at rest) until it is at most `frac` arm
    lengths away: authored poses stay reachable, so their overshoots survive the reach cap."""
    p = np.asarray(point, float)
    d = p - SHOULDER[side]
    k = min(1.0, frac * ARM / np.linalg.norm(d))
    return tuple(SHOULDER[side] + d * k)


def _speak_pulses(n, frames, amp=0.75):
    """Mouth opening on given beats (counting out loud), closed in between."""
    pts = [(0, -0.2)]
    for f in frames:
        pts += [(f - 2, -0.3), (f + 2, amp), (f + 7, amp * 0.4), (f + 11, -0.4)]
    pts.append((n - 1, -0.1))
    return C.spring(C.keys(n, sorted(pts)), freq=7, damping=0.8)


def count_123():
    """Counts one, two, three on his fingers: each finger pops up with a dip of the hand, a bounce
    of the knees and a stretch of the head, leaning into the hand (4.5 s)."""
    n = 135
    c = Clip(n)
    c.max_reach = 1.10
    c.life(seed=101, blinks=[110], hands=False)
    beats = [28, 52, 76]
    # beside the head, not in front of the face: the arm is short and the face is wide
    tgt = within("R", (-0.33, -0.10, 0.45), 1.0)
    low = within("R", (-0.27, -0.10, 0.36), 0.95)
    c.reach("R", [(0, None), (8, None), (16, low), (22, tgt), (102, tgt), (110, low), (120, None)])
    rx, ry, rz = orient_keys("R", [(0, (-0.15, -0.1, 1.0), FRONT)])
    c.reach_rot("R", rx, ry, rz)
    c.add("shoulder.R.rz", [(0, 0), (14, 0), (22, 12), (102, 12), (116, 0)])
    # each number: the hand dips, then pops up as the finger shoots out, and settles
    for b in beats:
        c.add("hand_ik.R.lz", C.pulse(n, b, [(-6, 0.0), (-2, -0.014), (2, 0.016), (6, 0.008), (10, 0.0)]))
    c.hand("R", [(0, "relaxed"), (12, "fist"), (beats[0] - 3, "fist"), (beats[0] + 1, "count1"), (beats[1] - 3, "count1"),
                 (beats[1] + 1, "count2"), (beats[2] - 3, "count2"), (beats[2] + 1, "count3"), (104, "count3"),
                 (116, "relaxed")])
    for b, fing in zip(beats, ("index", "middle", "ring")):       # the new finger overshoots straight
        for seg in (1, 2, 3):
            c.add(f"{fing}.{seg:02d}.R.cx", C.pulse(n, b, [(-1, 0.0), (2, -16.0), (6, 5.0), (10, 0.0)]))
    c.hand("L", [(0, "relaxed"), (20, "soft"), (100, "soft"), (120, "relaxed")])
    c.prop("mouth_open", _speak_pulses(n, beats))
    c.expr([(0, "happy", 0.5), (14, "happy"), (beats[2] - 2, "happy"), (beats[2] + 2, "joy"), (104, "joy"),
            (124, "happy")])
    for i, b in enumerate(beats):
        bump = C.pulse(n, b, [(-4, 0.0), (2, 1.0), (7, -0.25), (12, 0.0)])
        c.add("head.ry", bump * (6 if i % 2 else -6))
        c.add("head.rx", bump * -3)
        c.prop("brow_L", bump * 0.6)
        c.prop("brow_R", bump * 0.6)
        c.squash(b, 0.045 + 0.015 * i, "head", dur=12)
        c.dip(b, depth=0.009 + 0.003 * i, chest=1.5, dur=12)
    # he leans towards the counting hand, weight on that foot
    c.weight([(0, 0), (10, 0), (22, -0.7), (102, -0.6), (120, 0), (134, 0)])
    c.add("chest.rz", [(0, 0), (20, -6), (102, -6), (120, 0)])
    c.add("spine.ry", [(0, 0), (20, -3), (102, -3), (120, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def thumbs_up():
    """'¡Bien!': winds up, punches a thumbs up forward with the whole body, a little hop, a cheeky
    wink and two thumb pumps (3 s)."""
    n = 90
    c = Clip(n)
    c.max_reach = 1.10
    c.life(seed=111, hands=False)
    tgt = within("R", (-0.20, -0.20, 0.42), 1.0)
    back = within("R", (-0.24, -0.02, 0.36), 0.9)
    c.reach("R", [(0, None), (4, None), (10, back), (16, tgt), (72, tgt), (84, None)])
    rx, ry, rz = orient_keys("R", [(0, (0.0, -1.0, 0.25), (1.0, 0.0, 0.0))])
    c.reach_rot("R", rx, ry, rz)
    c.add("shoulder.R.rz", [(0, 0), (10, -6), (16, 18), (20, 14), (72, 14), (84, 0)])
    for t in (46, 56):                                           # thumb pumps
        c.add("hand_ik.R.lz", C.pulse(n, t, [(-4, 0.0), (-1, -0.012), (2, 0.012), (6, 0.0)]))
        c.add("hand_ik.R.ly", C.pulse(n, t, [(-4, 0.0), (2, -0.01), (6, 0.0)]))
    c.hand("R", [(0, "relaxed"), (8, "fist"), (13, "fist"), (17, "thumbs_up"), (72, "thumbs_up"), (84, "relaxed")])
    c.add("thumb.R.cx", C.pulse(n, 17, [(-1, 0), (2, -14), (6, 4), (9, 0)]))
    c.hand("L", [(0, "relaxed"), (14, "fist"), (70, "fist"), (84, "relaxed")])
    c.elbow("L", [(0, 0), (12, 30), (70, 28), (84, 0)])
    # the body throws the punch: coil back, then lean in with an overshoot
    c.add("chest.rz", [(0, 0), (10, 10), (16, -12), (21, -6), (26, -8), (72, -7), (86, 0)])
    c.add("spine.rx", [(0, 0), (10, -4), (16, 7), (22, 3), (72, 3), (86, 0)])
    c.weight([(0, 0), (10, 0.5), (16, -0.8), (22, -0.6), (72, -0.6), (86, 0)])
    c.hop(24, 33, height=0.03, crouch=0.02, stretch=0.06, feet=True)
    c.add("head.ry", [(0, 0), (16, -8), (40, -10), (46, -12), (72, -8), (86, 0)])
    c.expr([(0, "neutral"), (8, "determined", 0.6), (15, "joy"), (34, "joy"), (38, "wink"), (52, "wink"),
            (58, "happy"), (89, "happy")])
    c.prop("mouth_open", [(0, 0), (14, -0.3), (17, 0.4), (30, 0.2), (40, 0), (89, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def point_side():
    """'¡Mira ahí!': cocks the arm across his body, shoots it out pointing to his left (the viewer's
    right), leans after it, looks there, a double take at you, and points again (4 s)."""
    n = 120
    c = Clip(n)
    c.max_reach = 1.10
    c.life(seed=121, blinks=[62], hands=False)
    tgt = within("L", (0.37, -0.09, 0.47), 1.0)
    cock = (0.10, -0.22, 0.38)
    jab = within("L", (0.38, -0.12, 0.49), 1.06)
    c.reach("L", [(0, None), (6, None), (12, cock), (18, tgt), (62, tgt), (66, jab), (70, tgt), (96, tgt),
                  (110, None)])
    rx, ry, rz = orient_keys("L", [(0, (-1.0, -0.3, 0.2), (0.0, 0.2, -1.0)), (12, (-1.0, -0.3, 0.2), (0.0, 0.2, -1.0)),
                                   (17, (1.0, -0.25, 0.1), (0.0, 0.2, -1.0))])
    c.reach_rot("L", rx, ry, rz)
    c.add("shoulder.L.rz", [(0, 0), (12, 8), (18, -10), (96, -8), (110, 0)])
    c.hand("L", [(0, "relaxed"), (10, "fist"), (14, "fist"), (18, "point_pop"), (24, "point"), (62, "point"),
                 (66, "point_pop"), (72, "point"), (98, "point"), (110, "relaxed")])
    c.hand("R", [(0, "relaxed"), (16, "soft"), (100, "soft"), (112, "relaxed")])
    c.prop("gaze_x", [(0, 0), (8, 0), (10, -0.4), (16, 0.85), (40, 0.75), (42, -0.1), (56, -0.1), (58, 0.8),
                      (96, 0.7), (104, 0), (n - 1, 0)])
    c.add("head.rz", [(0, 0), (8, 0), (12, -6), (22, 22), (26, 17), (40, 18), (46, -2), (50, 2), (56, 0),
                      (62, 20), (66, 16), (98, 14), (112, 0)])
    c.add("head.ry", [(0, 0), (22, 6), (40, 4), (46, -6), (56, -4), (62, 5), (98, 4), (112, 0)])
    c.add("chest.rz", [(0, 0), (12, -8), (20, 14), (26, 10), (98, 9), (114, 0)])
    # the whole body follows the point: weight onto his left foot, a lean with an overshoot
    c.weight([(0, 0), (12, -0.5), (20, 0.95), (26, 0.75), (98, 0.7), (114, 0)])
    c.add("spine.ry", [(0, 0), (12, -2), (20, 6), (26, 4), (98, 3), (114, 0)])
    c.squash(18, 0.06, "head", dur=12)
    c.squash(46, 0.05, "head", dur=10)
    c.dip(66, depth=0.008)
    c.expr([(0, "neutral"), (10, "determined", 0.5), (18, "joy"), (40, "happy"), (46, "surprised", 0.5),
            (54, "joy"), (100, "happy"), (n - 1, "happy", 0.5)])
    c.prop("mouth_open", [(0, 0), (16, 0.0), (20, 0.5), (28, 0.2), (46, 0.4), (52, 0.1), (62, 0.5), (74, -0.2),
                          (n - 1, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def idea():
    """Thinks (eyes up, a finger tapping his cheek), then '¡ya sé!': a squash, a real hop with the
    head stretched, index up beside the head with a pop, brows and pupils flying (3.5 s)."""
    n = 105
    c = Clip(n)
    c.max_reach = 1.10
    c.life(seed=131, blinks=[20], hands=False)
    c.expr([(0, "neutral"), (8, "thinking"), (30, "thinking"), (34, "neutral"), (37, "surprised"), (46, "joy"),
            (90, "happy"), (104, "happy", 0.6)])
    c.prop("pupil", [(0, 0), (34, 0), (37, -0.4), (42, 0.6), (60, 0.3), (90, 0)])
    c.prop("brow_L", [(0, 0), (34, -0.2), (37, 0.6), (44, 0.3), (60, 0.2), (90, 0)])
    c.prop("brow_R", [(0, 0), (34, -0.2), (37, 0.6), (44, 0.3), (60, 0.2), (90, 0)])
    c.add("head.rx", [(0, 0), (10, -5), (30, -6), (34, 3), (38, -5), (46, -2), (60, 0)])
    c.add("head.ry", [(0, 0), (10, 7), (30, 8), (36, 0)])
    c.add("head.rz", [(0, 0), (10, 4), (30, 5), (36, 0)])
    # thinking: the right hand up at the chest, a finger tapping (FK), then the index flies up (IK)
    c.elbow("R", [(0, 0), (8, 70), (30, 70), (36, 40)])
    c.arm_fwd("R", [(0, 0), (8, 10), (30, 10), (36, 0)])
    c.forearm_in("R", [(0, 0), (8, 20), (30, 20), (36, 0)])
    c.add("index.01.R.cx", C.pulse(n, 14, [(-2, 0), (1, 25), (3, 0)]) + C.pulse(n, 20, [(-2, 0), (1, 25), (3, 0)])
          + C.pulse(n, 26, [(-2, 0), (1, 25), (3, 0)]))
    tgt = within("R", (-0.32, -0.08, 0.47), 1.0)
    c.reach("R", [(0, None), (32, None), (40, tgt), (88, tgt), (100, None)])
    c.add("hand_ik.R.lz", C.pulse(n, 40, [(-3, -0.01), (1, 0.016), (5, 0.006), (9, 0.0)]))
    rx, ry, rz = orient_keys("R", [(0, (-0.1, -0.1, 1.0), FRONT)])
    c.reach_rot("R", rx, ry, rz)
    c.add("shoulder.R.rz", [(0, 0), (34, 0), (40, 10), (88, 10), (100, 0)])
    c.hand("R", [(0, "relaxed"), (8, "soft"), (26, "soft"), (35, "fist"), (39, "point_pop"), (46, "count1"),
                 (90, "count1"), (100, "relaxed")])
    c.hand("L", [(0, "relaxed"), (36, "relaxed"), (42, "spread"), (60, "soft"), (90, "relaxed")])
    c.arm_raise("L", [(0, 0), (36, 0), (42, 24), (52, 14), (70, 6), (90, 0)])
    c.palm("L", [(0, 0), (36, 0), (42, 50), (70, 20), (90, 0)])
    c.weight([(0, 0), (8, 0.4), (30, 0.45), (36, 0.0), (60, -0.3), (90, -0.2), (104, 0)])
    c.hop(38, 48, height=0.05, crouch=0.03, stretch=0.10)
    c.squash(34, -0.06, "head", dur=4)
    c.prop("mouth_open", [(0, -0.4), (34, -0.4), (37, 0.8), (42, 0.6), (52, 0.3), (60, -0.1), (n - 1, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def think():
    """The classic thinker: the right fist under his chin (the head rests on it, tilted into the hand), the
    other fist on his hip, eyes rolling up and searching, the head weighing the idea with slow tilts and
    holds, three little taps of the knuckles on the chin. The arm stretches a little to reach (5 s)."""
    n = 150
    c = Clip(n)
    c.max_reach = 1.12
    c.contacts = []
    c.life(seed=141, blinks=[70, 122], hands=False, sway=0.4)
    c.add("chest.rx", [(0, 0), (16, 5), (130, 5), (146, 0)])
    c.add("neck.rx", [(0, 0), (16, 2), (130, 2), (146, 0)])
    # slow tilts with holds: weighing it one way (the head sinks into the fist), then the other while it
    # taps; the head holds still while the fist rests under the chin
    c.add("head.rx", [(0, 0), (16, 3), (130, 3), (146, 0)])
    c.add("head.ry", [(0, 0), (16, -9), (58, -9), (70, 2), (96, 4), (130, 4), (146, 0)])
    c.add("head.rz", [(0, 0), (20, 6), (58, 6), (70, -4), (96, -5), (130, -5), (146, 0)])
    c.add("shoulder.R.rz", [(0, 0), (16, 26), (132, 26), (146, 0)])   # shoulder forward and up to reach the chin
    c.shrug("R", [(0, 0), (16, 8), (132, 8), (146, 0)])
    near = (-0.08, -0.17, 0.46)                                        # the fist comes up in front, under the chin
    c.reach("R", [(0, None), (6, None), (18, near), (132, near), (144, None)])
    rx, ry, rz = orient_keys("R", [(0, (0.85, -0.3, 0.2), (0.0, 0.6, -0.8))])   # fingers across, knuckles up
    c.reach_rot("R", rx, ry, rz)
    c.hand("R", [(0, "relaxed"), (12, "grip"), (132, "grip"), (144, "relaxed")])
    chin = (-0.03, -0.15, 0.53)
    region = ["index.01.R", "middle.01.R", "ring.01.R", "index.02.R", "middle.02.R"]
    for f0, f1, ramp in ((24, 60, 8), (72, 74, 3), (81, 83, 3), (90, 92, 3), (102, 126, 6)):
        c.contacts.append({"side": "R", "touch": "head", "point": chin, "frames": (f0, f1), "ramp": ramp,
                           "region": region})
    # the other fist on his hip, elbow out (the pose of Tap_Foot, softer)
    c.arm_raise("L", [(0, 0), (6, -3), (20, 40), (24, 38), (130, 38), (144, 0)])
    c.forearm_lift("L", [(0, 0), (20, -42), (24, -40), (130, -40), (144, 0)])
    c.elbow("L", [(0, 0), (20, 22), (130, 22), (144, 0)])
    c.arm_fwd("L", [(0, 0), (20, -6), (130, -6), (144, 0)])
    c.palm("L", [(0, 0), (20, 18), (130, 18), (144, 0)])
    c.hand("L", [(0, "relaxed"), (22, "grip"), (130, "grip"), (144, "relaxed")])
    c.expr([(0, "neutral"), (16, "thinking"), (134, "thinking"), (148, "happy")])
    # eyes roll up and search: one side, the other, up
    c.prop("gaze_x", [(0, 0), (20, 0.45), (56, 0.45), (60, -0.5), (98, -0.5), (102, 0.1), (130, 0.1), (140, 0)],
           scale=0.7)
    c.prop("gaze_y", [(0, 0), (20, 0.3), (56, 0.2), (60, 0.45), (98, 0.35), (102, 0.5), (130, 0.4), (140, 0)],
           scale=0.6)
    c.prop("mouth_side", [(0, 0), (20, 0.9), (58, 0.9), (64, -0.7), (100, -0.7), (108, 0.8), (130, 0.8), (140, 0)],
           scale=0.6)
    c.prop("mouth_round", [(0, 0), (66, 0), (72, 0.5), (92, 0.5), (98, 0)])       # "mmm..."
    c.prop("brow_L", [(0, 0), (60, 0), (64, 0.4), (98, 0.3), (104, 0)])
    c.weight([(0, 0), (10, 0.3), (24, 0.6), (58, 0.55), (64, -0.3), (126, -0.25), (146, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def laugh():
    """Laughs: head back with the eyes shut, then doubles over holding his belly, then back again,
    bouncing on every 'ja' (4 s)."""
    n = 120
    c = Clip(n)
    c.max_reach = 1.12
    c.contacts = []
    c.life(seed=151, hands=False, breath=0.3)
    f = np.arange(n)
    env = C.keys(n, [(0, 0), (10, 0), (16, 1), (94, 1), (108, 0), (n - 1, 0)])
    ha = np.maximum(0, np.sin(2 * np.pi * f / 7.5)) * env            # 4 'ja' a second
    # back (head up, chest open) -> doubled over (forward) -> back again
    over = C.keys(n, [(0, 0), (12, -1), (34, -1), (46, 1), (66, 1), (78, -1), (96, -0.8), (110, 0)])
    # (the doubling over comes from the hips and spine: the hand on the belly rides with the chest,
    # the belly skin with the spine, so the chest itself barely bends against the spine)
    # (the torso barely bends: the hand rests on the belly and the arm is short; the laugh going
    # back and forth is the head, the neck and the chest)
    c.add("chest.rx", 3.0 * over - 1.5 * ha)
    c.add("neck.rx", 4.0 * over)
    c.add("head.rx", C.delay(-5 * ha, 1) + 6.0 * C.delay(over, 3) - 4.0)
    c.add("head.rz", C.delay(4 * ha, 2) * np.sin(2 * np.pi * f / 40))   # the laugh rolls the head a little
    c.sy("head", 1.0 + 0.035 * C.delay(ha, 1) - 0.01)
    c.add("hips.lz", -0.010 * ha - 0.006 + 0.008 * np.minimum(over, 0))
    for s in ("L", "R"):
        c.shrug(s, 5 * ha)
    c.prop("mouth_open", 0.35 * ha)
    c.expr([(0, "happy"), (10, "laugh"), (96, "laugh"), (110, "joy"), (n - 1, "happy")])
    c.prop("brow_in_L", 0.4 * C.delay(np.maximum(over, 0), 2))      # doubled over: almost crying laughing
    c.prop("brow_in_R", 0.4 * C.delay(np.maximum(over, 0), 2))
    near = (0.15, -0.12, 0.31)
    c.reach("L", [(0, None), (10, None), (20, near), (96, near), (110, None)])
    rx, ry, rz = orient_keys("L", [(0, (-0.5, -0.2, 0.25), (-0.3, 0.9, 0.0))])
    c.reach_rot("L", rx, ry, rz)
    c.add("shoulder.L.rz", [(0, 0), (16, -24), (96, -24), (112, 0)])
    c.contacts.append({"side": "L", "touch": "torso", "point": (0.12, -0.09, 0.325), "frames": (24, 94), "ramp": 8,
                       "region": ["hand.L", "index.01.L", "middle.01.L", "ring.01.L"]})
    c.hand("L", [(0, "relaxed"), (18, "hold_flat"), (98, "hold_flat"), (110, "relaxed")])
    c.hand("R", [(0, "relaxed"), (14, "spread"), (98, "spread"), (110, "relaxed")])
    # the free hand flaps with the laugh, up when he is back, down at the knee when doubled over
    c.arm_raise("R", C.keys(n, [(0, 0), (14, 30), (36, 30), (46, 8), (66, 8), (78, 30), (96, 28), (112, 0)]) + 8 * ha)
    c.elbow("R", C.keys(n, [(0, 0), (14, 46), (36, 46), (46, 10), (66, 10), (78, 46), (96, 40), (112, 0)]))
    c.palm("R", C.keys(n, [(0, 0), (14, 50), (96, 50), (112, 0)]))
    c.wrist("R", side=C.delay(-14 * ha, 2))
    c.weight([(0, 0), (12, -0.4), (40, 0.4), (70, 0.3), (80, -0.4), (100, -0.3), (116, 0)])
    c.secondary()
    return c


def surprised():
    """Startled, a classic take: squash, then a hop back with the head stretched tall, both palms
    fly to the cheeks (they really rest on the face; the arms stretch a little to get there), mouth
    'o', a wobble, '¡no puede ser!', then a relieved smile (3.5 s)."""
    n = 105
    c = Clip(n)
    c.max_reach = 1.12
    c.contacts = []
    c.life(seed=161, hands=False)
    # the take: a squash, a hop back with a stretch, a wobble that settles before the hands land
    c.squash(4, -0.08, "head", dur=4)
    c.add("hips.lz", [(0, -0.004), (4, -0.018), (7, 0.0), (13, -0.006), (16, -0.012), (24, -0.004)])
    c.add("root.lz", C.arc(n, 6, 13, 0.035))
    c.sy("head", 1.0 + C.pulse(n, 6, [(-1, 0.0), (2, 0.10), (6, -0.06), (10, 0.03), (14, -0.01), (18, 0.0)]))
    c.sy("neck", 1.0 + C.pulse(n, 6, [(-1, 0.0), (2, 0.05), (7, -0.02), (12, 0.0)]))
    for s in ("L", "R"):
        c.foot(s, z=C.arc(n, 7, 12, 0.012), pitch=C.pulse(n, 6, [(-2, 0), (1, 14), (6, -6), (9, 0)]))
    c.add("hips.ly", [(0, 0), (6, 0), (11, 0.03), (78, 0.022), (96, 0)])
    c.add("spine.rx", [(0, 0), (4, 3), (8, -8), (16, -4), (78, -2), (96, 0)])
    c.add("head.rx", [(0, 0), (4, 4), (8, -6), (18, -2), (78, -1), (96, 0)])
    c.add("head.ry", [(0, 0), (22, 0), (34, 5), (46, -5), (58, 4), (68, 0), (78, 0)])   # 'no puede ser'
    for s, sx in (("L", 1.0), ("R", -1.0)):
        c.add(f"shoulder.{s}.rz", [(0, 0), (10, -24 * sx), (80, -24 * sx), (96, 0)])
        c.shrug(s, [(0, 0), (6, 13), (12, 9), (80, 8), (96, 0)])        # shoulders up: a startle
        near = (0.24 * sx, -0.14, 0.52)                                # beside the jaw
        c.reach(s, [(0, None), (5, None), (14, near), (76, near), (90, None)])
        fingers, palm = (0.32 * sx, -0.43, 0.84), (-0.5 * sx, 0.67, 0.55)   # up the cheek, palm on it
        rx, ry, rz = orient_keys(s, [(0, fingers, palm)])
        c.reach_rot(s, rx, ry, rz)
        c.contacts.append({"side": s, "touch": "head", "point": (0.212 * sx, -0.138, 0.582), "frames": (18, 72),
                           "ramp": 6, "region": [f"hand.{s}", f"index.01.{s}", f"middle.01.{s}", f"ring.01.{s}",
                                                 f"index.02.{s}", f"middle.02.{s}", f"ring.02.{s}"]})
        c.hand(s, [(0, "relaxed"), (8, "spread"), (16, "open"), (74, "open"), (90, "relaxed")])
    c.expr([(0, "neutral"), (4, "scared", 0.5), (7, "surprised"), (60, "surprised"), (76, "joy"), (n - 1, "happy")])
    c.prop("pupil", [(0, 0), (6, -0.9), (20, -0.6), (60, -0.6), (76, 0.3), (n - 1, 0)])
    c.prop("blink_L", [(0, 0), (2, 0), (4, 1), (6, 0)])
    c.prop("blink_R", [(0, 0), (2, 0), (4, 1), (6, 0)])
    c.prop("mouth_open", [(0, 0), (7, 0.2), (12, 0.0), (60, 0.0), (66, -0.3), (76, 0.3), (n - 1, 0)])
    c.weight([(0, 0), (78, 0), (86, 0.4), (98, 0.2), (104, 0)])
    c.secondary()
    return c


def sad():
    """Sad: a big sigh, then he deflates (head sinks, shoulders and arms heavy), scuffs a foot, and
    slowly lifts his eyes at the end (4 s)."""
    n = 120
    c = Clip(n)
    c.life(seed=171, blinks=[50, 96], breath=0.6, hands=False)
    # the sigh: chest swells and lifts, then everything drops past where it was
    c.sy("chest", [(0, 1.0), (10, 1.0), (20, 1.025), (32, 0.98), (119, 0.985)])
    c.sy("spine", [(0, 1.0), (24, 1.0), (36, 0.98), (119, 0.982)])
    c.sy("neck", [(0, 1.0), (20, 1.03), (34, 0.94), (40, 0.955), (119, 0.955)])
    # the head hangs, but never so far that the face is lost behind the glasses
    c.add("head.rx", [(0, 0), (16, -4), (34, 10), (40, 8), (88, 9), (100, 3), (106, 4), (119, 4)])
    c.add("neck.rx", [(0, 0), (34, 4), (100, 3), (119, 3)])
    c.add("chest.rx", [(0, 0), (16, -4), (30, 6), (119, 5)])
    c.add("head.ry", [(0, 0), (30, 5), (119, 6)])
    for s in ("L", "R"):
        c.shrug(s, [(0, 0), (18, 6), (32, -7), (38, -5), (119, -6)])
        c.arm_raise(s, [(0, 0), (18, 3), (32, -6), (38, -4), (119, -5)])
        c.arm_fwd(s, [(0, 0), (32, 7), (119, 6)])
        c.elbow(s, [(0, 0), (32, -6), (119, -6)])
        c.hand(s, [(0, "relaxed"), (32, "rest"), (119, "rest")])
    c.add("hips.lz", [(0, -0.004), (32, -0.014), (119, -0.014)])
    # weight sinks onto one foot; the other foot scuffs the floor
    c.weight([(0, 0), (30, 0), (44, 0.6), (119, 0.55)])
    c.foot("R", y=C.pulse(n, 60, [(0, 0.0), (8, -0.025), (16, 0.012), (24, 0.0)]),
           z=C.pulse(n, 60, [(0, 0.0), (6, 0.006), (12, 0.0), (18, 0.004), (24, 0.0)]),
           pitch=C.pulse(n, 60, [(0, 0), (8, 12), (16, 6), (24, 0)]))
    c.expr([(0, "neutral"), (16, "sad", 0.6), (34, "sad"), (119, "sad")])
    c.prop("gaze_y", [(0, 0), (20, -0.3), (88, -0.35), (96, 0.3), (119, 0.25)])
    c.prop("mouth_open", [(0, 0), (12, -0.2), (20, 0.35), (30, -0.6), (119, -0.6)])
    c.prop("mouth_round", [(0, 0), (18, 0.5), (28, 0.0)])
    c.secondary()
    return c


def angry():
    """Angry: a slow wind-up (he sinks and rocks back, chest swelling, the open hands curl into fists
    that clench), a big stomp (knee way up, then the impact goes through the whole body), a huff with
    teeth and a trembling 'grr' with shaking fists, elbows wide so the silhouette reads (3.5 s)."""
    n = 105
    c = Clip(n)
    c.life(seed=181, hands=False, sway=0.4)
    c.weight([(0, 0), (8, 0.8), (16, 0.9), (24, 0.2), (n - 1, 0.1)])
    c.foot("R", z=[(0, 0), (6, 0), (16, 0.08), (19, 0.085), (23, 0.0), (n - 1, 0)],
           pitch=[(0, 0), (14, -10), (21, 4), (24, 0)])
    # anticipation: sink and rock back, then everything slams down on the stomp
    c.add("hips.lz", [(0, -0.004), (8, -0.018), (12, -0.006), (16, 0.004), (23, 0.0), (26, -0.036), (32, -0.012),
                      (40, -0.016), (n - 1, -0.012)])
    c.add("spine.rx", [(0, 0), (8, 3), (16, -8), (24, 12), (30, 8), (n - 1, 5)])
    c.add("chest.rx", [(0, 0), (16, -4), (24, 5), (30, 3), (n - 1, 2)])
    c.add("head.rx", [(0, 0), (8, 3), (16, -5), (24, 8), (30, 1), (n - 1, 0)])
    c.squash(24, -0.12, "head", dur=12)
    c.squash(24, -0.03, "spine", dur=10)
    c.sy("chest", [(0, 1.0), (12, 1.0), (18, 1.025), (24, 0.99), (30, 1.0), (n - 1, 1.0)])   # the chest swells, then drops
    f = np.arange(n)
    grr = np.sin(2 * np.pi * f / 4.0) * C.keys(n, [(0, 0), (44, 0), (48, 1), (78, 1), (86, 0), (n - 1, 0)])
    shake = C.noise(n, 2, 1.0, seed=9, loop=False) * C.keys(n, [(0, 0), (44, 0), (48, 1), (78, 1), (86, 0)])
    c.add("head.rz", 3.5 * grr)
    c.add("hips.lx", 0.002 * shake)
    c.add("chest.ry", 1.5 * shake)
    for s in ("L", "R"):
        # open claws at the wind-up, then the fists close and clench; elbows wide and the fists raised
        c.hand(s, [(0, "relaxed"), (8, "spread"), (14, "claw"), (18, "fist"), (n - 1, "fist")])
        c.curl(s, C.pulse(n, 26, [(-2, 0.0), (1, 6.0), (8, 0.0)]) + 5.0 * grr)               # clench on the impact
        c.elbow(s, [(0, 0), (16, 56), (26, 40), (n - 1, 44)])
        c.arm_raise(s, [(0, 0), (16, 26), (26, 16), (n - 1, 16)])
        c.arm_fwd(s, [(0, 0), (16, -14), (26, 6), (n - 1, 4)])
        c.shrug(s, [(0, 0), (20, 10), (26, 5), (n - 1, 8)])
        c.arm_raise(s, 5.0 * grr)
        c.elbow(s, 5.0 * shake)
    c.expr([(0, "neutral"), (10, "angry"), (n - 1, "angry")])
    c.prop("mouth_open", [(0, 0), (30, -0.3), (34, 0.6), (40, -0.5), (n - 1, -0.6)])   # the huff
    c.prop("teeth", [(0, 0), (30, 0), (34, 0.8), (40, 0.0), (46, 0.0), (50, 0.5), (78, 0.5), (84, 0)])
    c.prop("smile", C.keys(n, [(0, 0), (46, 0), (50, 0.5), (78, 0.5), (84, 0)]))   # grr: lips back over the teeth
    c.secondary()
    return c


def scared():
    """Scared: a jump take (up and back, head stretched), lands in a crouch, hands up trembling,
    knees knocking, eyes darting; then a relieved exhale (4 s)."""
    n = 120
    c = Clip(n)
    c.max_reach = 1.10
    c.life(seed=191, hands=False, breath=1.6)
    env = C.keys(n, [(0, 0), (14, 0), (18, 1), (82, 1), (94, 0), (n - 1, 0)])
    tremble = C.noise(n, 3, 1.0, seed=5, loop=False) * env
    knock = np.sin(2 * np.pi * np.arange(n) / 5.0) * env
    c.add("root.lz", C.arc(n, 5, 14, 0.05))
    c.squash(3, -0.06, "head", dur=3)
    c.sy("head", 1.0 + C.pulse(n, 5, [(-1, 0.0), (2, 0.11), (8, 0.02), (11, -0.08), (16, 0.02), (22, 0.0)]))
    for s in ("L", "R"):
        c.foot(s, z=C.arc(n, 6, 13, 0.02), pitch=C.pulse(n, 5, [(-2, 0), (1, 16), (7, -4), (9, 0)]))
    c.add("hips.ly", [(0, 0), (5, 0), (13, 0.02), (84, 0.016), (100, 0)])
    c.add("hips.lz", [(0, -0.004), (4, -0.016), (6, 0.0), (14, -0.006), (17, -0.034), (24, -0.028), (84, -0.026),
                      (100, -0.004)])
    c.add("hips.lz", 0.003 * knock)
    c.add("spine.rx", [(0, 0), (8, -6), (18, 5), (84, 4), (100, 0)])         # recoils, then cowers
    c.add("head.rx", [(0, 0), (8, -6), (18, 3), (84, 3), (100, 0)])
    c.add("head.rz", 2.4 * tremble)
    c.add("hips.lx", 0.003 * tremble)
    for s, x, sg in (("L", 0.16, 1), ("R", -0.16, -1)):
        tgt = within(s, (x, -0.15, 0.42), 1.0)                         # hands up in front of the chest
        c.reach(s, [(0, None), (5, None), (10, tgt), (84, tgt), (98, None)])
        rx, ry, rz = orient_keys(s, [(0, (-0.25 * np.sign(x), -0.55, 0.8), (0.0, -1.0, 0.1))])
        c.reach_rot(s, rx, ry, rz)
        c.add(f"hand_ik.{s}.lz", 0.006 * tremble)
        c.add(f"hand_ik.{s}.lx", 0.004 * C.delay(tremble, 1))
        c.hand(s, [(0, "relaxed"), (8, "spread"), (20, "claw"), (84, "claw"), (98, "relaxed")])
        c.hand_flutter(s, 1.0, env)                                    # the fingers tremble with the fear
        c.shrug(s, [(0, 0), (8, 12), (18, 8), (84, 7), (98, -2), (106, 0)])
        c.foot(s, turn=-6.0 * sg * env + 4.0 * sg * knock)             # knees in, knocking
    c.expr([(0, "neutral"), (4, "surprised"), (12, "scared"), (84, "scared"), (94, "calm"), (106, "happy"),
            (n - 1, "happy")])
    c.prop("gaze_x", [(0, 0), (20, 0.6), (28, -0.6), (36, 0.5), (50, -0.7), (62, 0.0), (84, 0.0)])
    c.prop("mouth_open", [(0, 0), (8, 0.5), (84, 0.35), (92, -0.2), (100, 0.4), (108, -0.3), (n - 1, 0)])
    c.prop("mouth_round", [(0, 0), (92, 0), (98, 0.6), (106, 0)])        # the relieved "fiuu"
    c.secondary()
    return c


def calm():
    """Calm: eyes closed, a slow deep breath (the chest really fills, the head rises), out through
    the mouth with a small overshoot, a gentle sway (5 s)."""
    n = 150
    c = Clip(n)
    c.life(seed=201, breath=0.0, sway=0.5, hands=False)
    breath = C.keys(n, [(0, 0), (20, 0), (64, 1), (80, 1), (120, -0.15), (134, 0), (n - 1, 0)])
    c.add("chest.rx", -5 * breath)
    c.add("spine.rx", -2.5 * breath)
    c.add("head.rx", -4 * breath)
    c.sy("chest", 1.0 + 0.03 * breath)
    c.sy("spine", 1.0 + 0.012 * breath)
    c.sy("neck", 1.0 + 0.04 * breath)
    c.add("hips.lz", -0.006 + 0.002 * breath)
    for s in ("L", "R"):
        c.shrug(s, 6 * breath)
        c.arm_raise(s, 9 * breath)
        c.palm(s, 25 * breath)
        c.hand(s, [(0, "relaxed"), (20, "soft"), (60, "spread"), (84, "spread"), (126, "soft"), (n - 1, "relaxed")])
    c.weight(C.sine(n, n, 0.35))
    c.add("head.ry", C.sine(n, n, 4.0, phase=0.1))
    c.expr([(0, "neutral"), (16, "calm"), (128, "calm"), (144, "happy")])
    c.prop("mouth_open", [(0, 0), (60, -0.3), (84, 0.3), (112, -0.4), (n - 1, 0)])   # breath out by the mouth
    c.prop("mouth_round", [(0, 0), (80, 0), (90, 0.75), (114, 0), (n - 1, 0)])
    c.secondary()
    return c


def celebrate():
    """Celebration: a big hop with fists up in a V beside the head (arms stretched), two fist pumps
    in the air, a hang at the top, a squashy landing (2.5 s)."""
    n = 75
    c = Clip(n)
    c.life(seed=211, breath=0.4, hands=False)
    t0, t1 = 15, 36
    c.hop(t0, t1, height=0.12, crouch=0.04, stretch=0.10)
    c.add("hips.lz", -0.004)
    for s in ("L", "R"):
        c.arm_raise(s, [(0, 0), (11, -8), (18, 50), (22, 45), (25, 50), (29, 45), (32, 49), (40, 47), (56, 10),
                        (68, 0)])
        c.arm_swing(s, [(0, 0), (16, 4), (44, 4), (60, 0)])
        c.arm_fwd(s, [(0, 0), (11, -14), (17, 4), (60, 0)])
        c.forearm_lift(s, [(0, 0), (16, 0), (20, 52), (42, 50), (58, 0)])
        c.elbow(s, [(0, 0), (11, 30), (18, 10), (22, 22), (25, 10), (29, 22), (32, 10), (56, 0)])  # fist pumps
        c.stretch(s, [(0, 1.0), (14, 1.0), (19, 1.07), (34, 1.05), (42, 1.04), (56, 1.0)])
        o = 0 if s == "L" else 1                       # the hands pump a frame apart
        c.hand(s, [(0, "relaxed"), (10, "fist"), (19 + o, "grip"), (23 + o, "fist"), (28 + o, "grip"), (33 + o, "fist"),
                   (44, "grip"), (56, "fist"), (68, "relaxed")])
    c.add("chest.rx", [(0, 0), (11, 5), (17, -6), (34, -4), (40, 4), (52, 0)])
    c.expr([(0, "happy"), (10, "determined", 0.5), (17, "joy"), (21, "laugh"), (40, "joy"), (n - 1, "happy")])
    c.prop("mouth_open", [(0, 0), (12, -0.4), (18, 0.3), (40, 0.2), (n - 1, 0)])
    c.secondary()
    return c


def shrug():
    """'No sé': shoulders shoot up (one a beat after the other), the head sinks between them, palms
    up and out, a head tilt, mouth to the side and an eye roll (2.5 s)."""
    n = 75
    c = Clip(n)
    c.life(seed=221, hands=False, sway=0.5)             # the hands are up beside the head
    for s, lag in (("L", 0), ("R", 3)):
        k = lambda pts: [(f + (lag if 8 < f < 70 else 0), v) for f, v in pts]  # noqa: E731
        c.shrug(s, k([(0, 0), (10, -2), (17, 11), (21, 8), (50, 8), (62, 0), (68, 1), (74, 0)]))
        c.arm_raise(s, k([(0, 0), (10, -3), (18, 24), (22, 20), (52, 20), (64, 0)]))
        c.elbow(s, k([(0, 0), (10, 8), (18, 66), (22, 60), (52, 60), (64, 0)]))
        c.forearm_lift(s, k([(0, 0), (12, 0), (20, 38), (52, 34), (64, 0)]))
        c.palm(s, k([(0, 0), (12, 0), (20, -78), (52, -74), (64, 0)]))
        c.hand(s, k([(0, "relaxed"), (14, "palm_up"), (34, "palm_up"), (52, "soft"), (66, "relaxed")]))
    c.sy("neck", [(0, 1.0), (12, 1.0), (19, 0.92), (24, 0.95), (50, 0.95), (62, 1.0)])
    c.add("head.ry", [(0, 0), (14, 0), (22, -4), (26, -3), (52, -3), (64, 0)])     # a tilt
    c.add("head.rx", [(0, 0), (12, 2), (20, -4), (52, -3), (64, 0)])
    c.dip(16, depth=0.008, chest=-1.0)
    c.expr([(0, "neutral"), (14, "confused"), (54, "confused"), (68, "happy")])
    c.prop("gaze_x", [(0, 0), (18, 0), (22, 0.35), (40, 0.35), (44, 0), (n - 1, 0)])
    c.prop("gaze_y", [(0, 0), (18, 0), (22, 0.55), (40, 0.5), (44, 0), (n - 1, 0)])          # the eye roll
    c.prop("mouth_side", [(0, 0), (16, 0), (20, -0.6), (52, -0.5), (64, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def run(n=20):
    """Run cycle in place (two strides per 0.67 s), leaning in, arms pumping; stretched in the air,
    squashed on each landing. The showcase adds the root travel."""
    c = Clip(n, loop=True)
    c.life(seed=231, breath=0.3, sway=0.3, hands=False)
    stride, lift = 0.15, 0.085
    f = np.arange(n)
    for s, off in (("L", 0.0), ("R", n / 2)):
        ph = ((f - off) % n) / n                    # 0..0.38 stance, 0.38..1 swing (flight in between)
        st = 0.38
        stance = ph < st
        sw = np.clip((ph - st) / (1 - st), 0, 1)
        y = np.where(stance, -stride + 2 * stride * (ph / st), stride - 2 * stride * (0.5 - 0.5 * np.cos(np.pi * sw)))
        z = np.where(stance, 0.0, lift * np.sin(np.pi * sw) ** 1.2)
        pitch = np.where(stance, -12 * np.exp(-(ph / 0.05) ** 2) + 26 * np.exp(-((ph - st) / 0.07) ** 2),
                         24 * np.exp(-((ph - st - 0.05) / 0.1) ** 2) - 12 * np.exp(-((ph - 0.98) / 0.05) ** 2))
        c.foot(s, y=y, z=z, pitch=pitch)
        pump = -40 * np.cos(2 * np.pi * ph)
        o = "R" if s == "L" else "L"
        c.arm_fwd(o, pump)
        c.elbow(o, 72 + 0.35 * np.maximum(C.delay(pump, 2, loop=True), 0))
        c.wrist(o, flex=C.delay(0.25 * pump, 3, loop=True))
        c.hand(o, [(0, "fist")])
    land = C.sine(n, n / 2, 1.0, phase=0.0)            # +1 in the air, -1 on the stance
    c.add("hips.lz", 0.010 * land - 0.010)
    c.sy("head", 1.0 + 0.04 * C.delay(land, 1, loop=True))
    c.sy("neck", 1.0 + 0.025 * C.delay(land, 1, loop=True))
    c.add("hips.rz", C.sine(n, n, -8.0))
    c.add("spine.rx", 13.0)
    c.add("chest.rz", C.sine(n, n, 10.0))
    c.add("head.rx", C.delay(C.sine(n, n / 2, 2.5, phase=0.25), 2, loop=True) - 9.0)
    c.expr([(0, "determined")], scale=0.6)
    c.prop("smile", 0.6)
    c.prop("mouth_open", 0.2)
    c.secondary()
    c.stride = stride
    c.stance = 0.38
    return c


EXPRESSIVE = {
    "Count_123": count_123,
    "Thumbs_Up": thumbs_up,
    "Point_Side": point_side,
    "Idea": idea,
    "Think": think,
    "Laugh": laugh,
    "Surprised": surprised,
    "Sad": sad,
    "Angry": angry,
    "Scared": scared,
    "Calm": calm,
    "Celebrate": celebrate,
    "Shrug": shrug,
    "Run": run,
}
