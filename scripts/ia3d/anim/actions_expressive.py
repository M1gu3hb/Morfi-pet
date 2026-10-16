"""Expressive actions built with the motor (hands, face, IK reach, stretch), from the
reference shots in /shoots: counting, thumbs up, pointing, idea, thinking, laughing,
surprise, sadness, anger, fear, calm, celebration, shrug and running.

Contact poses (hand on chin, hands on cheeks, hand on belly) were placed with
pose_probe.py and are verified frame by frame with check_clearance.py.
"""
import numpy as np

from . import curves as C
from .clip import Clip
from .motor import orient_keys

UP, FRONT = (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)


def _rest_arms(c, sides=("L", "R"), until=None):
    for s in sides:
        c.hand(s, [(0, "relaxed")])


def _speak_pulses(n, frames, amp=0.65):
    """Mouth opening on given beats (counting out loud), closed in between."""
    pts = [(0, -0.2)]
    for f in frames:
        pts += [(f - 2, -0.3), (f + 2, amp), (f + 7, amp * 0.4), (f + 11, -0.4)]
    pts.append((n - 1, -0.1))
    return C.spring(C.keys(n, sorted(pts)), freq=7, damping=0.8)


def count_123():
    """Counts one, two, three on his fingers, a little bounce on every number (4.5 s)."""
    n = 135
    c = Clip(n)
    c.life(seed=101, blinks=[110], hands=False)
    beats = [26, 50, 74]
    # beside the head, not in front of the face: the arm is short and the face is wide
    tgt = (-0.335, -0.11, 0.44)
    c.reach("R", [(0, None), (8, None), (20, tgt), (100, tgt), (118, None)])
    # (no extra stretch: the IK reach is capped at contacts.MAX_REACH)
    rx, ry, rz = orient_keys("R", [(0, (-0.15, -0.1, 1.0), FRONT)])
    c.reach_rot("R", rx, ry, rz)
    # a small lift of the hand on each number
    lift = sum(0.018 * np.exp(-((np.arange(n) - b - 2) / 3.5) ** 2) for b in beats)
    c.add("hand_ik.R.lz", lift)
    c.hand("R", [(0, "relaxed"), (12, "fist"), (24, "count1"), (48, "count1"), (52, "count2"), (72, "count2"),
                 (76, "count3"), (104, "count3"), (116, "relaxed")])
    c.hand("L", [(0, "relaxed")])
    c.prop("mouth_open", _speak_pulses(n, beats))
    c.expr([(0, "neutral"), (14, "happy"), (100, "joy"), (124, "happy")])
    for i, b in enumerate(beats):
        bump = np.exp(-((np.arange(n) - b) / 4.0) ** 2)
        c.add("head.ry", bump * (4 if i % 2 else -4))
        c.add("head.rx", bump * 3)
        c.add("hips.lz", bump * 0.004)
        c.prop("brow_L", bump * 0.4)
        c.prop("brow_R", bump * 0.4)
    c.add("chest.rz", [(0, 0), (20, -5), (100, -5), (120, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def thumbs_up():
    """Thumbs up and a wink (3 s)."""
    n = 90
    c = Clip(n)
    c.life(seed=111, hands=False)
    c.reach("R", [(0, None), (6, None), (16, (-0.21, -0.22, 0.40)), (19, (-0.21, -0.225, 0.415)),
                  (24, (-0.21, -0.22, 0.40)), (70, (-0.21, -0.22, 0.40)), (84, None)])
    rx, ry, rz = orient_keys("R", [(0, (0.0, -1.0, 0.25), (1.0, 0.0, 0.0))])
    c.reach_rot("R", rx, ry, rz)
    c.hand("R", [(0, "relaxed"), (12, "fist"), (18, "thumbs_up"), (72, "thumbs_up"), (84, "relaxed")])
    c.hand("L", [(0, "relaxed")])
    c.expr([(0, "neutral"), (14, "joy"), (30, "wink"), (46, "wink"), (52, "happy"), (89, "happy")])
    c.add("head.ry", [(0, 0), (16, -6), (70, -5), (86, 0)])
    c.add("spine.rx", [(0, 0), (14, 3), (70, 3), (86, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def point_side():
    """'Mira aquí': points to his left (the viewer's right), looks there, then at you (4 s)."""
    n = 120
    c = Clip(n)
    c.life(seed=121, blinks=[62], hands=False)
    tgt = (0.37, -0.09, 0.47)
    c.reach("L", [(0, None), (8, None), (20, tgt), (23, (0.38, -0.095, 0.475)), (27, tgt), (96, tgt), (110, None)])
    rx, ry, rz = orient_keys("L", [(0, (1.0, -0.25, 0.1), (0.0, 0.2, -1.0))])
    c.reach_rot("L", rx, ry, rz)
    # (no extra stretch: the IK reach is capped at contacts.MAX_REACH)
    c.hand("L", [(0, "relaxed"), (14, "fist"), (22, "point"), (98, "point"), (110, "relaxed")])
    c.hand("R", [(0, "relaxed")])
    c.prop("gaze_x", [(0, 0), (6, 0), (9, 0.7), (40, 0.7), (44, 0.0), (n - 1, 0)])
    c.add("head.rz", [(0, 0), (8, 0), (22, 16), (42, 15), (54, 3), (100, 3), (112, 0)])
    c.add("chest.rz", [(0, 0), (10, 0), (26, 8), (100, 6), (114, 0)])
    c.expr([(0, "neutral"), (16, "happy"), (48, "joy"), (100, "happy"), (n - 1, "neutral")])
    c.prop("mouth_open", [(0, 0), (40, 0), (46, 0.5), (56, 0.2), (64, 0.45), (74, -0.2), (n - 1, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def idea():
    """Thinks for a beat, then 'ya sé': index up, brows up, a little hop (3.5 s)."""
    n = 105
    c = Clip(n)
    c.life(seed=131, blinks=[20], hands=False)
    c.expr([(0, "neutral"), (8, "thinking"), (30, "thinking"), (36, "surprised"), (46, "joy"), (90, "happy"),
            (104, "neutral")])
    c.add("head.rx", [(0, 0), (10, -4), (30, -5), (36, 3), (44, -2), (60, 0)])
    c.add("head.ry", [(0, 0), (10, 5), (30, 6), (40, 0)])
    tgt = (-0.34, -0.10, 0.465)
    c.reach("R", [(0, None), (30, None), (40, tgt), (43, (-0.345, -0.10, 0.48)), (47, tgt), (88, tgt), (100, None)])
    rx, ry, rz = orient_keys("R", [(0, (-0.1, -0.1, 1.0), FRONT)])
    c.reach_rot("R", rx, ry, rz)
    # (no extra stretch: the IK reach is capped at contacts.MAX_REACH)
    c.hand("R", [(0, "relaxed"), (34, "fist"), (42, "count1"), (90, "count1"), (100, "relaxed")])
    c.hand("L", [(0, "relaxed")])
    c.add("hips.lz", [(0, -0.004), (34, -0.012), (40, 0.006), (46, -0.006), (54, -0.004)])
    c.prop("mouth_open", [(0, -0.4), (36, 0.2), (40, 0.7), (50, 0.3), (60, -0.1), (n - 1, 0)])
    c.secondary()
    return c


def think():
    """Fist under the chin, the other arm holding the elbow, eyes searching (5 s)."""
    n = 150
    c = Clip(n)
    c.life(seed=141, blinks=[70, 122], hands=False, sway=0.4)
    c.add("chest.rx", [(0, 0), (16, 6), (130, 6), (146, 0)])
    c.add("neck.rx", [(0, 0), (16, 4), (130, 4), (146, 0)])
    c.add("head.rx", [(0, 0), (16, 5), (60, 4), (90, 6), (130, 5), (146, 0)])
    c.add("head.ry", [(0, 0), (16, -5), (60, -3), (90, -6), (130, -4), (146, 0)])
    chin = (-0.07, -0.20, 0.40)          # fist under the chin: resolve_body() sets the exact touch
    c.add("shoulder.R.rz", [(0, 0), (16, 18), (132, 18), (146, 0)])   # shoulder forward to reach the chin
    c.reach("R", [(0, None), (6, None), (18, chin), (132, chin), (144, None)])
    rx, ry, rz = orient_keys("R", [(0, (0.15, -0.25, 1.0), (0.3, 1.0, 0.0))])
    c.reach_rot("R", rx, ry, rz)
    c.hand("R", [(0, "relaxed"), (12, "fist"), (132, "fist"), (144, "relaxed")])
    c.elbow("L", [(0, 0), (14, 0), (26, 72), (130, 72), (144, 0)])
    c.forearm_in("L", [(0, 0), (14, 0), (26, 30), (130, 30), (144, 0)])
    c.hand("L", [(0, "relaxed"), (24, "grip"), (130, "grip"), (144, "relaxed")])
    c.expr([(0, "neutral"), (16, "thinking"), (134, "thinking"), (148, "happy")])
    c.prop("gaze_x", [(0, 0), (20, 0.45), (58, 0.45), (64, -0.4), (100, -0.4), (106, 0.3), (130, 0.3), (140, 0)],
           scale=0.6)
    c.prop("mouth_side", [(0, 0), (20, 0.6), (60, 0.6), (66, -0.4), (100, -0.4), (108, 0.5), (130, 0.5), (140, 0)],
           scale=0.4)
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def laugh():
    """Laughs: eyes shut, head back, bouncing 'ja ja ja', a hand on the belly (4 s)."""
    n = 120
    c = Clip(n)
    c.life(seed=151, hands=False, breath=0.3)
    f = np.arange(n)
    env = C.keys(n, [(0, 0), (10, 0), (18, 1), (92, 1), (108, 0), (n - 1, 0)])
    ha = np.maximum(0, np.sin(2 * np.pi * f / 7.5)) * env            # 4 'ja' a second
    c.add("hips.lz", -0.006 * ha - 0.004)
    c.add("chest.rx", -4 * ha * 0.6)
    c.add("head.rx", C.delay(-5 * ha, 1) + C.keys(n, [(0, 0), (14, -8), (96, -6), (112, 0)]))
    for s in ("L", "R"):
        c.shrug(s, 4 * ha)
    c.prop("mouth_open", 0.35 * ha)
    c.expr([(0, "happy"), (12, "laugh"), (96, "laugh"), (112, "joy"), (n - 1, "happy")])
    belly = (0.08, -0.16, 0.31)          # palm on the belly: resolve_body() keeps it on the surface
    c.reach("L", [(0, None), (10, None), (20, belly), (96, belly), (110, None)])
    rx, ry, rz = orient_keys("L", [(0, (-0.5, -0.2, 0.25), (0.0, 1.0, 0.0))])
    c.reach_rot("L", rx, ry, rz)
    c.hand("L", [(0, "relaxed"), (18, "hold_flat"), (98, "hold_flat"), (110, "relaxed")])
    c.hand("R", [(0, "relaxed"), (18, "open"), (98, "open"), (110, "relaxed")])
    c.arm_raise("R", C.keys(n, [(0, 0), (16, 22), (96, 22), (112, 0)]) + 6 * ha)
    c.elbow("R", C.keys(n, [(0, 0), (16, 40), (96, 40), (112, 0)]))
    c.secondary()
    return c


def surprised():
    """Startled: a little jump back, hands to the cheeks, mouth 'o', then a smile (3 s)."""
    n = 90
    c = Clip(n)
    c.life(seed=161, hands=False)
    c.add("hips.ly", [(0, 0), (6, 0), (11, 0.025), (70, 0.02), (86, 0)])
    c.add("hips.lz", [(0, -0.004), (5, -0.012), (10, 0.010), (16, -0.002), (70, -0.004)])
    c.add("spine.rx", [(0, 0), (8, -8), (16, -5), (70, -4), (86, 0)])
    c.add("head.rx", [(0, 0), (8, -6), (18, -3), (70, -2), (86, 0)])
    for s, x in (("L", 0.33), ("R", -0.33)):
        tgt = (x, -0.12, 0.505)
        c.reach(s, [(0, None), (6, None), (14, tgt), (68, tgt), (82, None)])
        rx, ry, rz = orient_keys(s, [(0, UP, (-np.sign(x), 0.0, 0.0))])
        c.reach_rot(s, rx, ry, rz)
        # (no extra stretch: the IK reach is capped at contacts.MAX_REACH)
        c.hand(s, [(0, "relaxed"), (12, "stop"), (70, "stop"), (82, "relaxed")])
    c.expr([(0, "neutral"), (6, "surprised"), (50, "surprised"), (66, "joy"), (n - 1, "happy")])
    c.prop("blink_L", [(0, 0), (3, 0), (5, 1), (7, 0)])
    c.prop("blink_R", [(0, 0), (3, 0), (5, 1), (7, 0)])
    c.secondary()
    return c


def sad():
    """Sad: shoulders and head drop, a sigh, a glance up at the end (4 s)."""
    n = 120
    c = Clip(n)
    c.life(seed=171, blinks=[50, 96], breath=0.6, hands=False)
    c.add("head.rx", [(0, 0), (24, 12), (90, 13), (100, 6), (119, 8)])
    c.add("neck.rx", [(0, 0), (24, 6), (100, 5), (119, 5)])
    c.add("chest.rx", [(0, 0), (24, 7), (119, 7)])
    c.add("head.ry", [(0, 0), (30, 4), (119, 5)])
    for s in ("L", "R"):
        c.shrug(s, [(0, 0), (20, 3), (32, -5), (119, -5)])          # the sigh, then they drop
        c.arm_raise(s, [(0, 0), (30, -9), (119, -9)])
        c.hand(s, [(0, "relaxed"), (30, "rest"), (119, "rest")])
    c.add("chest.rx", [(0, 0), (16, -3), (26, 2), (119, 0)])
    c.add("hips.lz", [(0, -0.004), (30, -0.008), (119, -0.008)])
    c.expr([(0, "neutral"), (18, "sad"), (119, "sad")])
    c.prop("gaze_y", [(0, 0), (20, -0.35), (88, -0.35), (96, 0.25), (119, 0.2)])
    c.prop("mouth_open", [(0, 0), (14, -0.2), (20, 0.2), (28, -0.6), (119, -0.6)])
    c.secondary()
    return c


def angry():
    """Angry: fists, a stomp, a huff and a 'grr' shake (3.5 s)."""
    n = 105
    c = Clip(n)
    c.life(seed=181, hands=False, sway=0.4)
    c.foot("R", z=[(0, 0), (10, 0), (18, 0.045), (24, 0.0), (n - 1, 0)], pitch=[(0, 0), (16, -8), (24, 0)])
    c.add("hips.lz", [(0, -0.004), (14, 0.004), (24, -0.016), (30, -0.008), (n - 1, -0.008)])
    c.add("hips.lx", [(0, 0), (12, 0.012), (24, 0.004), (n - 1, 0.0)])
    c.add("spine.rx", [(0, 0), (22, 6), (n - 1, 5)])
    c.add("head.rx", [(0, 0), (24, 6), (n - 1, 5)])
    f = np.arange(n)
    grr = np.sin(2 * np.pi * f / 5.0) * C.keys(n, [(0, 0), (44, 0), (50, 1), (76, 1), (84, 0), (n - 1, 0)])
    c.add("head.rz", 3.0 * grr)
    for s in ("L", "R"):
        c.hand(s, [(0, "relaxed"), (14, "fist"), (n - 1, "fist")])
        c.elbow(s, [(0, 0), (16, 28), (n - 1, 24)])
        c.arm_raise(s, [(0, 0), (16, 6), (n - 1, 4)])
        c.shrug(s, [(0, 0), (20, 5), (n - 1, 4)])
        c.arm_raise(s, 1.5 * grr)
    c.expr([(0, "neutral"), (12, "angry"), (n - 1, "angry")])
    c.prop("mouth_open", [(0, 0), (30, -0.3), (34, 0.5), (40, -0.5), (n - 1, -0.6)])   # the huff
    c.prop("teeth", [(0, 0), (30, 0), (34, 0.8), (40, 0.0)])
    c.secondary()
    return c


def scared():
    """Scared: flinches, hands up in front, trembles, eyes dart; then relief (4 s)."""
    n = 120
    c = Clip(n)
    c.life(seed=191, hands=False, breath=1.6)
    f = np.arange(n)
    env = C.keys(n, [(0, 0), (8, 0), (12, 1), (84, 1), (96, 0), (n - 1, 0)])
    tremble = (C.noise(n, 3, 1.0, seed=5, loop=False)) * env
    c.add("hips.lz", [(0, -0.004), (8, -0.03), (84, -0.026), (100, -0.004)])
    c.add("spine.rx", [(0, 0), (10, -4), (84, -3), (100, 0)])         # recoils backwards
    c.add("head.rx", [(0, 0), (10, -4), (84, -3), (100, 0)])
    c.add("head.rz", 1.6 * tremble)
    c.add("hips.lx", 0.002 * tremble)
    for s, x in (("L", 0.16), ("R", -0.16)):
        tgt = (x, -0.15, 0.41)                                        # hands up in front of the chest
        c.reach(s, [(0, None), (6, None), (12, tgt), (84, tgt), (98, None)])
        rx, ry, rz = orient_keys(s, [(0, (-0.25 * np.sign(x), -0.55, 0.8), (0.0, -1.0, 0.1))])
        c.reach_rot(s, rx, ry, rz)
        c.add(f"hand_ik.{s}.lz", 0.004 * tremble)
        c.hand(s, [(0, "relaxed"), (10, "open"), (86, "open"), (98, "relaxed")])
        c.shrug(s, [(0, 0), (10, 6), (84, 5), (98, 0)])
    c.expr([(0, "neutral"), (8, "scared"), (84, "scared"), (96, "calm"), (106, "happy"), (n - 1, "happy")])
    c.prop("gaze_x", [(0, 0), (14, 0.5), (24, -0.5), (34, 0.4), (48, -0.6), (60, 0.0), (84, 0.0)])
    c.prop("mouth_open", [(0, 0), (8, 0.4), (84, 0.3), (92, -0.2), (100, 0.4), (108, -0.3), (n - 1, 0)])
    c.secondary()
    return c


def calm():
    """Calm: eyes closed, a slow deep breath in and out, a gentle sway (5 s)."""
    n = 150
    c = Clip(n)
    c.life(seed=201, breath=0.0, sway=0.5, hands=False)
    breath = C.keys(n, [(0, 0), (20, 0), (64, 1), (80, 1), (126, 0), (n - 1, 0)])
    c.add("chest.rx", -4 * breath)
    c.add("spine.rx", -2 * breath)
    c.add("head.rx", -3 * breath)
    for s in ("L", "R"):
        c.shrug(s, 4 * breath)
        c.arm_raise(s, 5 * breath)
        c.hand(s, [(0, "relaxed"), (20, "open"), (80, "open"), (126, "relaxed")])
    c.add("hips.lx", C.sine(n, n, 0.004))
    c.add("head.ry", C.sine(n, n, 3.0, phase=0.1))
    c.expr([(0, "neutral"), (16, "calm"), (128, "calm"), (144, "happy")])
    c.prop("mouth_open", [(0, 0), (60, -0.3), (84, 0.25), (110, -0.4), (n - 1, 0)])   # breath out by the mouth
    c.prop("mouth_round", [(0, 0), (80, 0), (90, 0.6), (112, 0), (n - 1, 0)])
    c.secondary()
    return c


def celebrate():
    """Celebration hop with fists up in a V, beside the head (2.5 s)."""
    n = 75
    c = Clip(n)
    c.life(seed=211, breath=0.4, hands=False)
    air = C.keys(n, [(0, 0), (14, 0), (22, 0.08), (28, 0.10), (34, 0.08), (40, 0), (n - 1, 0)])
    c.add("root.lz", air)
    c.add("hips.lz", [(0, -0.004), (11, -0.034), (15, 0.004), (38, 0.0), (42, -0.03), (52, 0.004), (60, -0.004)])
    for s in ("L", "R"):
        c.foot(s, z=[(0, 0), (16, 0), (22, 0.025), (32, 0.03), (38, 0.0)], pitch=[(0, 0), (11, 0), (15, 16), (22, 6),
                                                                                  (36, -5), (40, 0)])
        c.arm_raise(s, [(0, 0), (10, -6), (18, 60), (40, 60), (56, 10), (68, 0)])
        c.arm_swing(s, [(0, 0), (16, 4), (44, 4), (60, 0)])
        c.forearm_lift(s, [(0, 0), (16, 0), (20, 40), (42, 40), (58, 0)])
        c.stretch(s, [(0, 1.0), (16, 1.0), (20, 1.06), (42, 1.06), (56, 1.0)])
        c.hand(s, [(0, "relaxed"), (12, "fist"), (56, "fist"), (68, "relaxed")])
    c.add("spine.rx", [(0, 0), (11, 8), (16, -5), (36, -3), (42, 6), (54, 0)])
    c.add("head.rx", [(0, 0), (11, 5), (18, -7), (36, -5), (44, 3), (56, 0)])
    c.expr([(0, "happy"), (12, "joy"), (20, "laugh"), (40, "joy"), (n - 1, "happy")])
    c.secondary()
    return c


def shrug():
    """'No sé': shoulders up, palms up and out, head tilt, mouth to the side (2.5 s)."""
    n = 75
    c = Clip(n)
    c.life(seed=221, hands=False)
    for s in ("L", "R"):
        c.shrug(s, [(0, 0), (12, 0), (20, 9), (50, 8), (64, 0)])
        c.arm_raise(s, [(0, 0), (12, 0), (20, 27), (52, 25), (66, 0)])
        c.elbow(s, [(0, 0), (12, 0), (20, 62), (52, 60), (66, 0)])
        c.forearm_lift(s, [(0, 0), (14, 0), (22, 22), (52, 20), (66, 0)])
        c.palm(s, [(0, 0), (14, 0), (22, -70), (52, -70), (66, 0)])
        c.hand(s, [(0, "relaxed"), (18, "open"), (54, "open"), (66, "relaxed")])
    c.add("head.ry", [(0, 0), (14, 0), (24, -6), (52, -5), (66, 0)])     # tilts away from the higher hand
    c.add("head.rx", [(0, 0), (20, -3), (52, -2), (66, 0)])
    c.expr([(0, "neutral"), (16, "confused"), (54, "confused"), (70, "happy")])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def run(n=20):
    """Run cycle in place (two strides per 0.67 s); the showcase adds the root travel."""
    c = Clip(n, loop=True)
    c.life(seed=231, breath=0.3, sway=0.3, hands=False)
    stride, lift = 0.15, 0.075
    f = np.arange(n)
    for s, off in (("L", 0.0), ("R", n / 2)):
        ph = ((f - off) % n) / n                    # 0..0.38 stance, 0.38..1 swing (flight in between)
        st = 0.38
        stance = ph < st
        sw = np.clip((ph - st) / (1 - st), 0, 1)
        y = np.where(stance, -stride + 2 * stride * (ph / st), stride - 2 * stride * (0.5 - 0.5 * np.cos(np.pi * sw)))
        z = np.where(stance, 0.0, lift * np.sin(np.pi * sw) ** 1.2)
        pitch = np.where(stance, -10 * np.exp(-(ph / 0.05) ** 2) + 22 * np.exp(-((ph - st) / 0.07) ** 2),
                         20 * np.exp(-((ph - st - 0.05) / 0.1) ** 2) - 10 * np.exp(-((ph - 0.98) / 0.05) ** 2))
        c.foot(s, y=y, z=z, pitch=pitch)
        pump = -32 * np.cos(2 * np.pi * ph)
        o = "R" if s == "L" else "L"
        c.arm_fwd(o, pump)
        c.elbow(o, 70 + 0.3 * np.maximum(pump, 0))
        c.hand(o, [(0, "fist")])
    c.add("hips.lz", C.sine(n, n / 2, 0.012, phase=0.0) - 0.006)
    c.add("hips.rz", C.sine(n, n, -6.0))
    c.add("spine.rx", 10.0)
    c.add("chest.rz", C.sine(n, n, 8.0))
    c.add("head.rx", C.delay(C.sine(n, n / 2, 2.0, phase=0.25), 2, loop=True) - 6.0)
    c.expr([(0, "determined")], scale=0.6)
    c.prop("smile", 0.5)
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
