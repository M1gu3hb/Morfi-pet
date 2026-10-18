"""Morfi's actions, authored as curves (30 fps).

Every action starts and ends near the relaxed idle pose, so they chain without pops.
Principles used throughout: anticipation before big moves, eyes lead the head and the
head leads the body, arcs (heads dip when they turn), overlap (hands and cubes lag),
fast-in / slow-out hits that overshoot and settle, the weight always over a foot (knees
that give), squash & stretch on the head and neck (clip.squash / clip.hop) and the
always-on life layer (breathing, micro head motion, blinks).

He is a cartoon: poses are pushed until they read from across the room, then held.
"""
import numpy as np

from . import curves as C
from .clip import Clip
from . import motor


def idle():
    """Relaxed standing loop: breathing, the weight from one foot to the other, glances (5 s)."""
    n = 150
    c = Clip(n, loop=True)
    c.life(seed=3, blinks=[38, 112, 121])
    # weight shift: over his left foot, then his right, each with a small overshoot and a knee give
    c.weight(C.keys(n, [(0, -0.55), (12, 0.62), (17, 0.5), (70, 0.48), (87, -0.62), (92, -0.5), (148, -0.55)],
                    loop=True))
    c.dip(14, depth=0.006, chest=1.2, dur=14)
    c.dip(89, depth=0.006, chest=1.2, dur=14)
    c.add("hips.lz", -0.004)
    # breathing you can see: the chest swells (volume kept) and the head rides on it
    breath = C.sine(n, n / 2, 1.0, phase=0.1)
    c.sy("chest", 1.0 + 0.012 * breath)
    c.sy("neck", 1.0 + 0.01 * C.delay(breath, 4, loop=True))
    for s, ph in (("L", 0.25), ("R", 0.75)):
        c.arm_fwd(s, C.delay(C.sine(n, n, 2.0, phase=ph), 6, loop=True))
        c.arm_raise(s, C.delay(C.sine(n, n, 1.2 * (1 if s == "L" else -1)), 8, loop=True))
    # glances: the eyes go first and quick, the head follows on an arc with a small overshoot,
    # a curious tilt while it holds
    c.prop("gaze_x", [(0, 0.0), (44, 0.0), (46, 0.42), (78, 0.38), (80, 0.0), (128, 0.0), (130, -0.3),
                      (142, -0.28), (145, 0.0)], )
    c.prop("gaze_y", [(0, 0.0), (44, 0.0), (46, 0.1), (78, 0.08), (80, 0.0)])
    c.add("head.rz", [(0, 0), (45, 0), (49, -1.2), (58, 8.5), (63, 7.0), (78, 7.0), (84, 8.0), (94, -1.0), (100, 0),
                      (130, 0), (133, 1.0), (139, -5.0), (143, -4.0), (149, 0)])
    c.add("head.rx", [(0, 0), (48, 0), (53, 2.0), (60, -1.0), (80, -1.0), (88, 1.5), (96, 0)])
    c.add("head.ry", [(0, 0), (50, 0), (60, 5.0), (78, 4.0), (92, 0), (149, 0)])
    c.add("chest.rz", [(0, 0), (52, 0), (64, 2.5), (80, 2.5), (98, 0)])
    c.prop("brow_L", [(0, 0), (44, 0), (47, 0.35), (78, 0.25), (84, 0), (128, 0), (131, 0.2), (144, 0)])
    c.prop("brow_R", [(0, 0), (44, 0), (47, 0.2), (78, 0.15), (84, 0), (128, 0), (131, 0.3), (144, 0)])
    c.prop("smile", [(0, 0.4), (50, 0.55), (80, 0.5), (110, 0.4)])
    # the fingers fidget once
    c.curl("L", C.pulse(n, 100, [(-4, 0), (2, 14), (8, -6), (14, 0)], loop=True))
    c.secondary()
    return c


def wave():
    """Big friendly wave with the right hand: '¡Hola!' (3.5 s).

    Morfi's arms are 20 cm long and his head 60 cm wide: a raised hand would go into the head
    (check_clearance.py / search_wave.py). The wave keeps the elbow at shoulder height and the
    forearm on a diagonal out to the side, so the hand waves beside the lower corner of the head;
    the arm stretches a little on the way up (FK, volume kept) and the wrist drags behind the
    forearm like a flag.
    """
    n = 105
    c = Clip(n)
    c.life(seed=11, blinks=[92], hands=False)
    s = "R"
    f = np.arange(n)
    # anticipation: the weight goes to the other foot, the arm drops and cocks back before it rises
    c.weight([(0, 0), (6, 0.45), (14, 0.9), (20, 0.75), (84, 0.75), (96, -0.1), (104, 0)])
    c.add("hips.lz", [(0, -0.004), (7, -0.016), (14, -0.002), (20, -0.006), (88, -0.006), (98, -0.010),
                      (104, -0.004)])
    c.arm_raise(s, [(0, 0), (7, -8), (15, 48), (20, 41), (25, 44), (80, 44), (90, -8), (97, 2), (104, 0)])
    c.arm_fwd(s, [(0, 0), (7, -12), (15, 4), (80, 4), (90, 6), (104, 0)])
    c.arm_swing(s, [(0, 0), (8, 0), (16, 26), (80, 26), (92, 0), (104, 0)])
    c.forearm_lift(s, [(0, 0), (9, -6), (17, 48), (22, 38), (26, 41), (80, 41), (90, 0), (104, 0)])
    c.elbow(s, [(0, 0), (7, 18), (17, 4), (80, 4), (92, 8), (104, 0)])
    c.stretch(s, [(0, 1.0), (10, 1.0), (16, 1.06), (24, 1.03), (80, 1.03), (90, 1.0), (104, 1.0)])
    # the wave: forearm rocks about the elbow, the hand flags behind it, wider away from the head
    env = C.keys(n, [(0, 0), (22, 0), (27, 1), (76, 1), (84, 0), (104, 0)])
    w = motor.wave_drive(n, 22, 84, period=13.0, seed=5)
    # a wave rolls through the whole arm: the elbow leads, the forearm rocks, the wrist follows it
    # (side and flex a quarter turn apart so the hand draws a small ellipse), the palm turns a
    # little with every swing and the fingers cascade after the wrist
    c.forearm_lift(s, -np.where(w < 0, 15.0, 8.0) * w)
    c.elbow(s, 4.5 * C.delay(w, -2.0))
    c.arm_swing(s, 3.0 * C.delay(w, -1.0))
    c.wrist(s, side=C.delay(-26.0 * w, 3.5), flex=np.array(C.keys(n, [(0, 0), (8, 14), (16, -10), (22, -6), (80, -6),
                                                                     (90, 10), (98, 0), (104, 0)]))
            + 9.0 * C.delay(w, 6.0))
    c.palm(s, C.keys(n, [(0, 0), (10, 0), (18, 78), (80, 74), (91, 0), (104, 0)]) + 9.0 * C.delay(w, 2.0))
    c.finger_roll(s, C.delay(w, 3.0), amp=11.0, lag=1.5)
    c.hand(s, [(0, "relaxed"), (8, "soft"), (17, "open"), (82, "open"), (94, "relaxed"), (104, "relaxed")])
    c.hand("L", [(0, "relaxed"), (14, "soft"), (88, "soft"), (104, "relaxed")])
    c.arm_raise("L", [(0, 0), (14, 6), (88, 6), (104, 0)])
    # the body answers: leans away from the hand, opens the chest to the camera, bounces on every
    # wave; the head stretches up on the '¡hola!' and tilts towards the hand
    c.add("spine.ry", [(0, 0), (8, -2.0), (18, 4.5), (80, 4.0), (96, 0), (104, 0)])
    c.add("head.ry", [(0, 0), (10, -3), (22, 7), (80, 6), (96, 0), (104, 0)])
    c.add("head.rx", [(0, 0), (7, 4.5), (16, -6), (22, -3), (80, -3), (96, 1), (104, 0)])
    c.add("chest.rz", [(0, 0), (16, -6), (80, -5), (96, 0)])
    c.squash(8, -0.06, "head", dur=6)
    c.squash(15, 0.08, "head", dur=16)
    bounce = np.maximum(0, w)
    c.add("hips.lz", -0.004 * bounce)
    c.add("chest.rx", 1.5 * C.delay(bounce, 2))
    c.add("head.rx", -1.2 * C.delay(bounce, 3))
    c.expr([(0, "happy", 0.6), (12, "joy"), (40, "happy"), (84, "happy"), (104, "happy", 0.5)])
    c.prop("mouth_open", [(0, 0), (14, 0.2), (20, 0.5), (30, 0.1), (104, 0)])        # '¡hola!'
    c.prop("brow_L", [(0, 0), (6, -0.2), (14, 0.5), (30, 0.2), (84, 0.2), (100, 0)])
    c.prop("brow_R", [(0, 0), (6, -0.2), (14, 0.5), (30, 0.2), (84, 0.2), (100, 0)])
    c.secondary()
    return c


def walk(speed_steps=32):
    """In-place walk cycle, two steps per loop (~1.07 s), bouncy. Root travel is added by the
    showcase (stride * 2 per cycle), so the feet stay planted on the floor."""
    n = speed_steps
    c = Clip(n, loop=True)
    c.life(seed=21, breath=0.4, sway=0.4)
    stride = 0.115                     # forward reach of each foot from its rest spot
    lift = 0.05
    half = n / 2
    f = np.arange(n)
    for s, off in (("L", 0.0), ("R", half)):
        ph = ((f - off) % n) / n                    # 0 = heel strike, 0..0.5 stance, 0.5..1 swing
        stance = ph < 0.5
        sw = np.clip((ph - 0.5) / 0.5, 0, 1)
        # planted: constant speed backwards (= the root travel); swing: eased forward
        y = np.where(stance, -stride + 2 * stride * (ph / 0.5), stride - 2 * stride * (0.5 - 0.5 * np.cos(np.pi * sw)))
        z = np.where(stance, 0.0, lift * np.sin(np.pi * sw) ** 1.4)
        # heel strike: toes up; push off: heel rises (toes down relative to the floor)
        pitch = np.where(stance, -16 * np.exp(-((ph - 0.0) / 0.06) ** 2) + 18 * np.exp(-((ph - 0.5) / 0.08) ** 2),
                         22 * np.exp(-((ph - 0.55) / 0.10) ** 2) - 14 * np.exp(-((ph - 0.98) / 0.06) ** 2))
        c.foot(s, y=y, z=z, pitch=pitch)
        # arms counter-swing (opposite arm goes forward with the leg), elbows and hands drag
        swing = -26 * np.cos(2 * np.pi * ph)
        o = "R" if s == "L" else "L"
        c.arm_fwd(o, C.delay(swing, 2, loop=True))
        c.elbow(o, 14 + 0.6 * np.maximum(C.delay(-swing, 4, loop=True), 0))
        c.wrist(o, flex=C.delay(0.35 * swing, 5, loop=True))
    for s in ("L", "R"):
        c.arm_raise(s, 3.0)
        c.hand(s, [(0, "soft")])
    # bouncy: low at each contact (knees take the weight), high at passing; sway over the stance
    # foot; pelvis twist; the head squashes a little on each contact and stretches on the pass
    down = C.sine(n, half, 1.0, phase=0.25)          # +1 at passing, -1 at contact
    c.add("hips.lz", 0.008 * down - 0.014)
    c.sy("head", 1.0 + 0.03 * C.delay(down, 2, loop=True))
    c.sy("neck", 1.0 + 0.02 * C.delay(down, 1, loop=True))
    c.add("hips.lx", C.sine(n, n, 0.013, phase=0.25))
    c.add("hips.rz", C.sine(n, n, -7.0, phase=0.0))
    c.add("hips.ry", C.sine(n, n, 3.5, phase=0.25))
    c.add("spine.rx", 5.0)                                      # lean into the walk
    c.add("chest.rz", C.sine(n, n, 8.0, phase=0.0))             # shoulders counter the pelvis
    c.add("chest.ry", C.sine(n, n, -2.0, phase=0.25))
    c.add("head.rz", C.delay(C.sine(n, n, -2.5, phase=0.0), 2, loop=True))
    c.add("head.ry", C.delay(C.sine(n, n, -2.5, phase=0.25), 3, loop=True))
    c.add("head.rx", C.delay(-2.0 * down, 3, loop=True) - 3.0)
    c.expr([(0, "happy")], scale=0.8)
    c.secondary()
    c.stride = stride
    return c


def happy_jump():
    """'¡Feliz!': crouch, a big hop with arms flung up, legs tucked, land soft, wobble (2.5 s)."""
    n = 75
    c = Clip(n)
    c.life(seed=31, breath=0.5, blinks=[66], hands=False)
    t0, t1 = 18, 35                                   # take-off, landing
    c.hop(t0, t1, height=0.12, crouch=0.042, stretch=0.10)
    c.add("hips.lz", -0.004)
    c.add("chest.rx", [(0, 0), (14, 5), (19, -5), (30, -3), (37, 5), (48, -1), (56, 0)])
    for s in ("L", "R"):
        c.foot(s, z=C.arc(n, t0 + 3, t1 - 2, 0.03))                   # knees tuck at the top
        c.arm_fwd(s, [(0, 0), (8, 4), (15, -26), (20, 12), (27, 6), (34, 4), (40, -10), (50, 3), (60, 0)])
        # "¡yay!": arms fling wide and up beside the head (higher would hit it), a little stretch
        c.arm_raise(s, [(0, 0), (8, -2), (15, -6), (20, 42), (26, 48), (33, 44), (40, 20), (50, -4), (58, 2),
                        (66, 0)])
        c.arm_swing(s, [(0, 0), (14, -6), (20, 14), (34, 12), (48, 0)])
        c.forearm_lift(s, [(0, 0), (17, 0), (22, 36), (28, 30), (34, 30), (44, 0), (66, 0)])
        c.elbow(s, [(0, 0), (14, 26), (20, 6), (34, 10), (42, 24), (54, 6), (66, 0)])
        c.stretch(s, [(0, 1.0), (18, 1.0), (23, 1.07), (32, 1.05), (40, 1.0)])
        c.palm(s, [(0, 0), (16, 0), (22, 70), (38, 65), (50, 0)])
        c.wrist(s, side=[(0, 0), (19, 0), (24, -18), (29, 10), (34, -8), (40, 4), (46, 0)])
        c.hand(s, [(0, "relaxed"), (9, "fist"), (20, "spread"), (38, "spread"), (50, "soft"), (66, "relaxed")])
    # a happy wiggle of the head at the top
    c.add("head.ry", [(0, 0), (22, 0), (26, 6), (31, -5), (36, 2), (44, 0)])
    c.expr([(0, "happy", 0.6), (12, "happy"), (19, "joy"), (24, "laugh"), (34, "laugh"), (40, "joy"),
            (n - 1, "happy")])
    c.prop("mouth_open", [(0, 0), (16, -0.3), (20, 0.2), (50, 0.1), (n - 1, 0)])
    c.prop("brow_L", [(0, 0), (14, -0.3), (19, 0.4), (40, 0.3), (60, 0)])
    c.prop("brow_R", [(0, 0), (14, -0.3), (19, 0.4), (40, 0.3), (60, 0)])
    c.secondary()
    return c


def look_around():
    """Curious look to each side: eyes first, a small counter-turn, a snappy turn on an arc with an
    overshoot, the weight goes that way and the neck stretches to peer (5 s)."""
    n = 150
    c = Clip(n)
    c.life(seed=41, blinks=[40, 103, 140])
    c.prop("gaze_x", [(0, 0), (4, 0), (6, 0.75), (20, 0.4), (54, 0.4), (56, -0.75), (72, -0.4),
                      (108, -0.4), (110, 0.0), (149, 0)])
    c.prop("gaze_y", [(0, 0), (6, 0.08), (54, 0.12), (56, -0.05), (108, 0.0)])
    # counter-turn (anticipation), snap with overshoot, settle; dip through the middle of each turn
    c.add("head.rz", [(0, 0), (5, 0), (9, -4), (19, 37), (24, 31), (28, 33), (52, 31), (57, 36), (60, 33),
                      (72, -36), (77, -30), (81, -32), (106, -30), (110, -33), (124, 3), (130, -1), (136, 0)])
    c.add("neck.rz", [(0, 0), (9, -1), (20, 10), (52, 9), (74, -10), (108, -9), (128, 0)])
    c.add("chest.rz", [(0, 0), (11, -1), (24, 7), (54, 6), (78, -7), (110, -6), (132, 0)])
    c.add("head.rx", [(0, 0), (9, 1), (14, 5), (20, -2), (52, -2), (64, 6), (72, -2), (108, -2), (116, 5),
                      (126, -1), (134, 0)])
    c.add("head.ry", [(0, 0), (20, 0), (30, 11), (48, 8), (60, 0), (74, 0), (84, -10), (102, -8), (114, 0)])
    # the weight goes to the side he looks at and he leans in to peer, neck long
    c.weight([(0, 0), (12, 0), (24, 0.8), (54, 0.7), (64, 0), (76, -0.8), (108, -0.7), (124, 0.1), (134, 0)])
    c.add("spine.rx", [(0, 0), (20, 0), (30, 5), (52, 4), (64, 0), (82, 5), (104, 4), (120, 0)])
    c.sy("neck", [(0, 1.0), (22, 1.0), (32, 1.06), (50, 1.05), (62, 1.0), (82, 1.06), (102, 1.05), (116, 1.0)])
    c.squash(19, 0.035, "head", dur=10)
    c.squash(72, 0.035, "head", dur=10)
    c.prop("brow_L", [(0, 0), (6, 0.7), (20, 0.5), (50, 0.4), (60, 0), (74, 0.35), (104, 0.25), (115, 0)])
    c.prop("brow_R", [(0, 0), (6, 0.35), (20, 0.3), (50, 0.2), (60, 0), (74, 0.7), (104, 0.5), (115, 0)])
    c.prop("mouth_round", [(0, 0), (70, 0), (76, 0.45), (100, 0.35), (110, 0)])     # "¿mmh?"
    c.prop("mouth_open", [(0, 0), (70, 0), (76, -0.1), (110, 0)])
    c.prop("pupil", [(0, 0), (6, 0.3), (50, 0.2), (60, 0), (74, 0.3), (104, 0.2), (115, 0)])
    c.prop("smile", [(0, 0.35), (60, 0.25), (115, 0.25), (140, 0.55)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


ACTIONS = {
    "Idle": idle,
    "Wave": wave,
    "Walk": walk,
    "Jump_Happy": happy_jump,
    "Look_Around": look_around,
}

from .actions_social import SOCIAL  # noqa: E402

ACTIONS.update(SOCIAL)

from .actions_expressive import EXPRESSIVE  # noqa: E402

ACTIONS.update(EXPRESSIVE)
from .actions_props import PROPS_ACTIONS  # noqa: E402

ACTIONS.update(PROPS_ACTIONS)
from .actions_moves import MOVES  # noqa: E402

ACTIONS.update(MOVES)
