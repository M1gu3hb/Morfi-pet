"""Morfi's actions, authored as curves (30 fps).

Every action starts and ends on the relaxed idle pose, so they chain without pops.
Principles used throughout: anticipation before big moves, eyes lead the head and the
head leads the body, arcs (heads dip when they turn), overlap (hands and cubes lag),
settles with a small overshoot, and the always-on life layer (breathing, micro head
motion, blinks).
"""
import numpy as np

from . import curves as C
from .clip import Clip


def idle():
    """Relaxed standing loop: breathing, weight shift, glances, blinks (5 s)."""
    n = 150
    c = Clip(n, loop=True)
    c.life(seed=3, blinks=[38, 112, 121])
    # weight shift over the whole loop: hips over the left foot, then the right
    c.add("hips.lx", C.sine(n, n, 0.006))
    c.add("hips.lz", C.sine(n, n / 2, 0.0012, phase=0.25) - 0.004)   # knees a little soft
    c.add("hips.ry", C.sine(n, n, 1.0, phase=0.02))
    c.add("hips.rz", C.sine(n, n, 1.6, phase=0.20))
    c.add("spine.ry", C.sine(n, n, -1.4, phase=0.05))
    c.add("chest.ry", C.sine(n, n, -0.6, phase=0.08))
    c.add("chest.rz", C.sine(n, n, -1.0, phase=0.28))
    c.add("neck.ry", C.sine(n, n, 0.8, phase=0.14))
    for s, ph in (("L", 0.25), ("R", 0.75)):
        c.arm_fwd(s, C.delay(C.sine(n, n, 1.3, phase=ph), 6, loop=True))
        c.arm_raise(s, C.delay(C.sine(n, n, 0.8 * (1 if s == "L" else -1)), 8, loop=True))
    # glances: the eyes move first, quick, and hold
    c.prop("gaze_x", [(0, 0.0), (44, 0.0), (47, 0.28), (78, 0.28), (81, 0.0), (128, 0.0), (131, -0.18),
                      (142, -0.18), (146, 0.0)])
    c.prop("gaze_y", [(0, 0.0), (44, 0.0), (47, 0.05), (78, 0.05), (81, 0.0)])
    c.add("head.rz", [(0, 0), (47, 0), (60, 4.0), (78, 4.0), (92, 0), (131, 0), (140, -2.5), (148, 0)])
    c.prop("smile", 0.35)
    c.secondary()
    return c


def wave():
    """Friendly wave with the right hand (3.5 s).

    Morfi's arms are 23 cm long and his head 60 cm wide: a raised hand would go into
    the head (measured with check_clearance.py / search_wave.py). The wave keeps the
    elbow at shoulder height and the forearm on a diagonal, so the hand waves beside
    the lower corner of the head with 2-4 cm to spare, and the wrist does the flapping.
    """
    n = 105
    c = Clip(n)
    c.life(seed=11, blinks=[90])
    s = "R"
    f = np.arange(n)
    # anticipation: tiny dip and the arm drops back before rising
    c.add("hips.lz", [(0, -0.004), (6, -0.009), (14, -0.002), (22, -0.004), (90, -0.004), (104, -0.004)])
    c.arm_raise(s, [(0, 0), (6, -4), (16, 48), (21, 41), (25, 44), (80, 44), (91, -6), (98, 1), (104, 0)])
    c.arm_swing(s, [(0, 0), (8, 0), (16, 24), (80, 24), (92, 0), (104, 0)])
    c.forearm_lift(s, [(0, 0), (9, 0), (18, 39), (24, 32), (80, 32), (90, 0), (104, 0)])
    c.elbow(s, [(0, 0), (12, 0), (20, 6), (80, 6), (92, 0), (104, 0)])
    # the wave: forearm rocks about the elbow, the hand flaps a little later and wider
    env = C.keys(n, [(0, 0), (22, 0), (28, 1), (74, 1), (82, 0), (104, 0)])
    w = np.sin(2 * np.pi * (f - 22) / 15.0) * env
    c.forearm_lift(s, -np.where(w < 0, 8.0, 12.0) * w)    # swings wider away from the head
    c.wrist(s, side=C.delay(-18.0 * w, 3), flex=[(0, 0), (16, 0), (22, -6), (80, -6), (92, 0), (104, 0)])
    c.curl(s, [(0, 0), (14, 0), (20, -12), (80, -12), (92, 0)])
    c.palm(s, [(0, 0), (12, 0), (20, 72), (80, 72), (91, 0), (104, 0)])   # palm to the viewer
    # the body answers: chest opens to the camera, head tilts a touch away from the hand,
    # a little bounce on every wave
    c.add("spine.ry", [(0, 0), (8, 0.8), (22, 2.0), (80, 2.0), (96, 0), (104, 0)])
    c.add("head.ry", [(0, 0), (12, 0), (24, 4), (80, 3), (96, 0), (104, 0)])
    c.add("head.rx", [(0, 0), (8, 2.5), (20, -3), (80, -2), (96, 0), (104, 0)])
    c.add("hips.lz", 0.002 * np.maximum(0, np.sin(2 * np.pi * (f - 22) / 15.0)) * env)
    c.add("chest.rz", [(0, 0), (20, -4), (80, -4), (96, 0)])
    c.prop("smile", [(0, 0.35), (16, 0.9), (84, 0.9), (104, 0.4)])
    c.prop("brow_L", [(0, 0), (14, 0.6), (30, 0.4), (84, 0.4), (100, 0)])
    c.prop("brow_R", [(0, 0), (14, 0.6), (30, 0.4), (84, 0.4), (100, 0)])
    c.secondary()
    return c


def walk(speed_steps=32):
    """In-place walk cycle, two steps per loop (~1.07 s). Root travel is added by the
    showcase (stride * 2 per cycle), so the feet stay planted on the floor."""
    n = speed_steps
    c = Clip(n, loop=True)
    c.life(seed=21, breath=0.4, sway=0.4)
    stride = 0.115                     # forward reach of each foot from its rest spot
    lift = 0.04
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
        pitch = np.where(stance, -14 * np.exp(-((ph - 0.0) / 0.06) ** 2) + 16 * np.exp(-((ph - 0.5) / 0.08) ** 2),
                         18 * np.exp(-((ph - 0.55) / 0.10) ** 2) - 12 * np.exp(-((ph - 0.98) / 0.06) ** 2))
        c.foot(s, y=y, z=z, pitch=pitch)
        # arms counter-swing (opposite arm goes forward with the leg)
        swing = -18 * np.cos(2 * np.pi * ph)
        c.arm_fwd("R" if s == "L" else "L", C.delay(swing, 2, loop=True))
    for s in ("L", "R"):
        fwd = c.get(f"upper_arm.{s}.rx") * -1
        c.elbow(s, 10 + 0.5 * np.maximum(fwd, 0))
        c.arm_raise(s, 2.0)
    # hips: low at each contact, high at passing; sway over the stance foot; pelvis twist
    c.add("hips.lz", C.sine(n, half, 0.006, phase=0.25) - 0.010)
    c.add("hips.lx", C.sine(n, n, 0.011, phase=0.25))
    c.add("hips.rz", C.sine(n, n, -5.0, phase=0.0))
    c.add("hips.ry", C.sine(n, n, 2.5, phase=0.25))
    c.add("spine.rx", 4.0)                                      # lean into the walk
    c.add("chest.rz", C.sine(n, n, 6.0, phase=0.0))             # shoulders counter the pelvis
    c.add("chest.ry", C.sine(n, n, -1.5, phase=0.25))
    c.add("head.rz", C.delay(C.sine(n, n, -1.5, phase=0.0), 2, loop=True))
    c.add("head.ry", C.delay(C.sine(n, n, -1.2, phase=0.25), 3, loop=True))
    c.add("head.rx", C.delay(C.sine(n, half, 1.2, phase=0.25), 3, loop=True) - 3.0)
    c.prop("smile", 0.5)
    c.secondary()
    c.stride = stride
    return c


def happy_jump():
    """Celebration hop: crouch, jump with arms out, land soft, settle (2.3 s)."""
    n = 70
    c = Clip(n)
    c.life(seed=31, breath=0.5, blinks=[60])
    air = C.keys(n, [(0, 0), (16, 0), (24, 0.075), (30, 0.095), (36, 0.075), (43, 0), (n - 1, 0)])
    c.add("root.lz", air)
    c.add("hips.lz", [(0, -0.004), (12, -0.035), (17, 0.004), (24, 0.0), (36, 0.0), (43, -0.008),
                      (47, -0.032), (56, 0.003), (62, -0.005), (69, -0.004)])
    for s in ("L", "R"):
        c.foot(s, z=[(0, 0), (18, 0), (24, 0.025), (34, 0.03), (40, 0.0), (69, 0)],
               pitch=[(0, 0), (12, 0), (17, 18), (22, 8), (36, -6), (42, 0), (69, 0)])
        c.arm_fwd(s, [(0, 0), (12, -22), (17, 10), (24, 5), (36, 5), (46, -8), (56, 2), (69, 0)])
        # "yay": arms open wide and up to shoulder height (higher would hit the head)
        c.arm_raise(s, [(0, 0), (12, 2), (19, 40), (26, 46), (36, 42), (46, 18), (58, 2), (69, 0)])
        c.arm_swing(s, [(0, 0), (12, -4), (19, 12), (36, 12), (50, 0)])
        c.forearm_lift(s, [(0, 0), (16, 0), (22, 26), (34, 20), (46, 0), (69, 0)])
        c.elbow(s, [(0, 0), (12, 20), (20, 8), (36, 8), (48, 18), (69, 0)])
        c.palm(s, [(0, 0), (16, 0), (22, 65), (40, 65), (52, 0)])
        c.wrist(s, side=[(0, 0), (19, 0), (24, -14), (30, 8), (36, -6), (46, 0)])
        c.curl(s, [(0, 0), (12, 10), (18, -12), (40, -12), (50, 0)])
    c.add("spine.rx", [(0, 0), (12, 9), (17, -5), (26, -3), (40, 0), (47, 7), (57, -1.5), (64, 0)])
    c.add("chest.rx", [(0, 0), (12, 5), (17, -4), (26, -2), (40, 0), (47, 4), (57, -1), (64, 0)])
    c.add("head.rx", [(0, 0), (12, 6), (18, -8), (28, -6), (40, 2), (47, 6), (56, -2), (66, 0)])
    c.prop("smile", [(0, 0.4), (14, 0.6), (20, 1.0), (55, 1.0), (69, 0.7)])
    c.prop("squint", [(0, 0), (18, 0.0), (24, 0.5), (50, 0.5), (66, 0)])
    c.prop("brow_L", [(0, 0), (16, 0.8), (40, 0.6), (60, 0)])
    c.prop("brow_R", [(0, 0), (16, 0.8), (40, 0.6), (60, 0)])
    c.secondary()
    return c


def look_around():
    """Curious look to each side, eyes first, head on an arc, a tilt at each hold (5 s)."""
    n = 150
    c = Clip(n)
    c.life(seed=41, blinks=[40, 103, 140])
    c.prop("gaze_x", [(0, 0), (4, 0), (7, 0.65), (22, 0.35), (54, 0.35), (57, -0.65), (76, -0.35),
                      (108, -0.35), (111, 0.0), (149, 0)])
    c.prop("gaze_y", [(0, 0), (7, 0.05), (54, 0.1), (57, -0.05), (108, 0.0)])
    c.add("head.rz", [(0, 0), (6, 0), (22, 30), (26, 28), (54, 28), (60, 26), (78, -28), (82, -26),
                      (108, -26), (114, -24), (128, 1.5), (134, 0)])
    c.add("neck.rz", [(0, 0), (8, 0), (24, 8), (54, 8), (80, -8), (108, -8), (130, 0)])
    c.add("chest.rz", [(0, 0), (10, 0), (28, 5), (56, 5), (84, -5), (110, -5), (134, 0)])
    # arcs: the head dips as it passes the middle of a turn, and tilts while holding
    c.add("head.rx", [(0, 0), (12, 3), (22, -1), (54, -1), (66, 5), (78, -1), (108, -1), (118, 4), (130, 0)])
    c.add("head.ry", [(0, 0), (22, 0), (32, 9), (50, 7), (60, 0), (80, 0), (88, -7), (104, -6), (114, 0)])
    c.prop("brow_L", [(0, 0), (20, 0.5), (50, 0.4), (60, 0), (85, 0.3), (104, 0.2), (115, 0)])
    c.prop("brow_R", [(0, 0), (20, 0.3), (50, 0.2), (60, 0), (85, 0.5), (104, 0.4), (115, 0)])
    c.prop("smile", [(0, 0.35), (60, 0.2), (115, 0.2), (140, 0.45)])
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
