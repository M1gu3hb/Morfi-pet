"""Movement clips (group "moves"): spins, hops, a second dance, a bow, a yawn, a victory fist,
waving with both arms, peeking, shivering, sneaking, dozing off, foot tapping, scratching his
head, '¡ay, no!', a blown kiss.

Same rules as the rest (anticipation, overshoot and settle, squash & stretch, weight over a foot)
and each one ends near the idle pose, so the viewer's crossfade back to Idle is invisible.
Hands that touch his own head (Scratch_Head, Facepalm, Blow_Kiss) are contacts solved on the
deformed skin; the arm stretches a little to get there (clip.max_reach, rebaked as a stretch that
keeps the volume).
"""
import numpy as np

from . import curves as C
from .clip import Clip
from . import motor
from .motor import orient_keys


def spin():
    """'¡Giro!': winds up, hops and spins all the way round (the head spots the viewer and whips
    round last), lands squashed and opens his arms: '¡ta-da!' (3 s)."""
    n = 90
    c = Clip(n)
    c.life(seed=401, blinks=[70], hands=False, sway=0.5)
    t0, t1 = 16, 32
    root = C.keys(n, [(0, 0), (8, -10), (15, -32), (t0, -30), (t0 + 3, 20), (t1 - 3, 330), (t1, 362), (t1 + 4, 370),
                      (t1 + 10, 358), (t1 + 16, 360), (n - 1, 360)])
    c.add("root.rz", root)
    spot = C.keys(n, [(0, 0), (t0 + 2, -8), (t0 + 6, 40), (t0 + 10, 300), (t1, 362), (t1 + 6, 360), (n - 1, 360)])
    rel = np.clip(spot - root, -45, 45)
    c.add("head.rz", 0.75 * rel)
    c.add("neck.rz", 0.25 * rel)
    c.add("chest.rz", C.keys(n, [(0, 0), (12, -10), (t0, -12), (t0 + 4, 12), (t1, 6), (t1 + 8, -4), (t1 + 16, 0)]))
    c.add("hips.rz", C.keys(n, [(0, 0), (12, -6), (t0, -8), (t0 + 4, 8), (t1, 0)]))
    c.hop(t0, t1, height=0.10, crouch=0.04, stretch=0.09)
    c.add("hips.lz", -0.004)
    for s in ("L", "R"):
        c.foot(s, z=C.arc(n, t0 + 2, t1 - 2, 0.025))
        # tucked in for the spin, flung open on the landing: '¡ta-da!'
        c.arm_raise(s, [(0, 0), (10, 8), (15, -4), (t0 + 2, -6), (t1 - 2, -4), (t1 + 4, 50), (t1 + 8, 42),
                        (t1 + 12, 46), (70, 44), (84, 0), (89, 0)])
        c.elbow(s, [(0, 0), (12, 40), (t0 + 2, 96), (t1 - 3, 96), (t1 + 4, 10), (t1 + 10, 18), (70, 16), (84, 0)])
        c.arm_fwd(s, [(0, 0), (t0, 10), (t1 - 3, 16), (t1 + 4, 0), (84, 0)])
        c.forearm_lift(s, [(0, 0), (t1, 0), (t1 + 5, 26), (70, 22), (84, 0)])
        c.palm(s, [(0, 0), (t1, 0), (t1 + 5, 70), (70, 66), (84, 0)])
        c.stretch(s, [(0, 1.0), (t1 + 1, 1.0), (t1 + 5, 1.07), (t1 + 12, 1.04), (70, 1.04), (82, 1.0)])
        c.hand(s, [(0, "relaxed"), (10, "fist"), (t1 - 4, "fist"), (t1 + 4, "spread"), (72, "spread"), (84, "relaxed")])
    c.dip(t1 + 18, depth=0.008)
    c.expr([(0, "happy", 0.6), (10, "determined", 0.6), (t0 + 2, "joy"), (t1 - 2, "joy"), (t1 + 3, "laugh"),
            (t1 + 14, "joy"), (n - 1, "happy")])
    c.prop("mouth_open", [(0, 0), (t0, -0.3), (t0 + 3, 0.4), (t1 + 4, 0.5), (60, 0.1), (n - 1, 0)])
    c.secondary()
    return c


def hop_steps():
    """'Saltitos': four little bouncy hops in place, swaying side to side, arms flapping like a
    happy kid; every landing squashes the head (3 s)."""
    n = 90
    c = Clip(n)
    c.life(seed=411, breath=0.3, sway=0.3, hands=False)
    hops = [(10, 20), (25, 35), (40, 50), (55, 66)]
    for k, (a, b) in enumerate(hops):
        side = 1 if k % 2 == 0 else -1
        c.add("root.lz", C.arc(n, a, b, 0.045 if k < 3 else 0.06))
        c.add("hips.lz", C.pulse(n, a, [(-5, 0.0), (-1, -0.018), (1, 0.0), (b - a - 1, 0.0), (b - a + 2, -0.016),
                                        (b - a + 5, 0.0)]))
        c.squash(a - 1, -0.05, "head", dur=4)
        c.squash(a + 1, 0.06, "head", dur=b - a)
        c.squash(b + 1, -0.07, "head", dur=8)
        c.add("hips.lx", C.pulse(n, a, [(-4, 0.0), (3, 0.010 * side), (b - a + 3, 0.010 * side), (b - a + 8, 0.0)]))
        c.add("head.ry", C.pulse(n, a, [(-2, 0.0), (4, 6.0 * side), (b - a + 2, 4.0 * side), (b - a + 8, 0.0)]))
        c.add("chest.ry", C.pulse(n, a, [(-2, 0.0), (5, -3.0 * side), (b - a + 4, 0.0)]))
        for s, sg in (("L", 1), ("R", -1)):
            tuck = 0.035 if side == sg else 0.018                          # one knee higher each hop
            c.foot(s, z=C.arc(n, a + 1, b - 1, tuck),
                   pitch=C.pulse(n, a, [(-3, 0), (0, 14), (3, 20), (b - a - 2, -4), (b - a, 0)]))
            c.arm_raise(s, C.pulse(n, a, [(-3, 0.0), (2, 24.0), (b - a - 2, 14.0), (b - a + 3, 4.0),
                                          (b - a + 6, 0.0)]))
            c.wrist(s, side=C.pulse(n, a, [(0, 0.0), (4, -20.0), (b - a, 14.0), (b - a + 6, 0.0)]))
    for s in ("L", "R"):
        c.arm_raise(s, [(0, 0), (8, 10), (72, 10), (84, 0)])
        c.elbow(s, [(0, 0), (8, 40), (72, 40), (84, 0)])
        c.palm(s, [(0, 0), (8, 40), (72, 40), (84, 0)])
        c.hand(s, [(0, "relaxed"), (8, "spread"), (72, "spread"), (84, "relaxed")])
    c.add("hips.lz", -0.004)
    c.expr([(0, "happy"), (8, "joy"), (70, "joy"), (n - 1, "happy")])
    c.prop("mouth_open", C.keys(n, [(0, 0), (10, 0.3), (70, 0.3), (n - 1, 0)]))
    c.secondary()
    return c


def dance_2():
    """Second dance, with the arms (120 bpm, 4 beats = 2 s, loops): two beats of rolling forearms,
    then the disco point out to his side and down across the body (an arm raised higher would go
    into his big head: the bake's body pass keeps it beside it), hips swinging on every beat."""
    n = 60
    c = Clip(n, loop=True)
    c.life(seed=421, breath=0.3, sway=0.3, hands=False)
    beat = 15
    for b in range(4):
        t = b * beat
        c.add("hips.lz", C.pulse(n, t, [(-3, 0.0), (2, -0.022), (8, -0.004), (13, 0.0)], loop=True))
        c.sy("head", 1.0 + C.pulse(n, t, [(-2, 0.0), (2, -0.06), (6, 0.04), (10, 0.0)], loop=True))
    c.add("hips.lz", -0.008)
    w = C.keys(n, [(0, -1.0), (5, -0.8), (15, 1.0), (20, 0.8), (30, -1.0), (35, -0.8), (45, 1.0), (50, 0.8)],
               loop=True)
    c.weight(0.85 * w, heel=14.0)
    c.add("hips.rz", 10.0 * C.delay(w, 1, loop=True))
    c.add("chest.rz", -6.0 * C.delay(w, 3, loop=True))
    c.add("head.ry", 7.0 * C.delay(w, 4, loop=True))
    c.add("head.rx", C.delay(C.sine(n, beat, 4.0, phase=0.25), 2, loop=True))
    # beats 1-2: forearms roll round each other in front of the belly (90 degrees apart)
    roll = C.keys(n, [(0, 1.0), (26, 1.0), (30, 0.0), (56, 0.0), (59, 1.0)], loop=True)
    for s, ph in (("L", 0.0), ("R", 0.25)):
        c.elbow(s, roll * (55 + 12 * C.sine(n, beat / 2, 1.0, phase=ph)))
        c.arm_fwd(s, roll * (36 + 6 * C.sine(n, beat / 2, 1.0, phase=ph + 0.25)))
        c.forearm_in(s, roll * 24)
    # beats 3-4: the disco point: right arm up and out, then down across the body; left on the hip
    disco = 1.0 - roll
    c.arm_raise("R", disco * C.ease(n, [(0, 0), (29, 0), (31, 40), (37, 37), (45, -2), (52, 2), (59, 0)], loop=True))
    c.forearm_lift("R", disco * C.ease(n, [(0, 0), (29, 0), (31, 58), (37, 54), (45, 0), (59, 0)], loop=True))
    c.arm_swing("R", disco * C.ease(n, [(0, 0), (29, 0), (31, 10), (44, 10), (46, 34), (52, 30), (59, 0)], loop=True))
    c.elbow("R", disco * C.ease(n, [(0, 0), (29, 0), (31, 6), (44, 6), (46, 20), (59, 0)], loop=True))
    c.arm_raise("L", disco * 18)
    c.elbow("L", disco * 92)
    c.forearm_in("L", disco * -10)
    c.hand("R", [(0, "fist"), (26, "fist"), (31, "point_pop"), (36, "point"), (54, "point"), (59, "fist")])
    c.hand("L", [(0, "fist")])
    c.expr([(0, "joy")], scale=0.9)
    c.prop("mouth_open", C.sine(n, 2 * beat, 0.25, phase=0.1) + 0.15)
    c.prop("brow_L", C.sine(n, beat, 0.3) + 0.25)
    c.prop("brow_R", C.sine(n, beat, 0.3, phase=0.1) + 0.25)
    c.prop("gaze_x", 0.25 * C.delay(w, 2, loop=True))
    c.secondary()
    return c


def bow():
    """'Gracias': a hand to the belly, the other arm out, a foot back, a deep bow held with the eyes
    closed, then up with a bounce and a smile (3.5 s)."""
    n = 105
    c = Clip(n)
    c.life(seed=431, blinks=[96], hands=False, sway=0.5)
    bow_k = C.keys(n, [(0, 0), (10, -0.08), (16, 0.0), (32, 1.0), (36, 0.94), (58, 1.0), (72, -0.12), (78, 0.04),
                       (86, 0.0), (n - 1, 0)])
    c.add("spine.rx", 12 * bow_k)
    c.add("chest.rx", 10 * bow_k)
    c.add("neck.rx", 5 * C.delay(bow_k, 2))
    c.add("head.rx", 7 * C.delay(bow_k, 3))
    c.add("hips.ly", 0.012 * bow_k)                              # the hips go back to balance the bow
    c.add("hips.lz", -0.006 * bow_k - 0.004)
    # right hand to the belly, left arm swept out, palm up
    c.elbow("R", [(0, 0), (8, 20), (16, 64), (66, 64), (80, 0)])
    c.forearm_in("R", [(0, 0), (16, 30), (66, 30), (80, 0)])
    c.arm_fwd("R", [(0, 0), (16, 6), (66, 6), (80, 0)])
    c.palm("R", [(0, 0), (16, -20), (66, -20), (80, 0)])
    c.hand("R", [(0, "relaxed"), (14, "soft"), (66, "soft"), (80, "relaxed")])
    c.arm_raise("L", [(0, 0), (8, -4), (20, 36), (26, 30), (62, 32), (78, 0), (n - 1, 0)])
    c.arm_fwd("L", [(0, 0), (20, -8), (62, -8), (78, 0)])
    c.palm("L", [(0, 0), (20, -60), (62, -60), (78, 0)])
    c.elbow("L", [(0, 0), (20, 14), (62, 14), (78, 0)])
    c.hand("L", [(0, "relaxed"), (18, "open"), (62, "open"), (78, "relaxed")])
    # the right foot slides back, toe down
    c.foot("R", y=[(0, 0), (8, 0), (16, 0.045), (66, 0.045), (78, 0.0)],
           z=C.pulse(n, 8, [(0, 0.0), (4, 0.012), (8, 0.0)]) + C.pulse(n, 66, [(0, 0.0), (6, 0.012), (12, 0.0)]),
           pitch=[(0, 0), (16, 20), (66, 20), (78, 0)])
    c.weight([(0, 0), (10, 0.5), (66, 0.45), (80, 0), (n - 1, 0)], heel=0.0)
    c.squash(72, 0.06, "head", dur=14)
    c.expr([(0, "happy", 0.6), (16, "calm"), (58, "calm"), (68, "joy"), (n - 1, "happy")])
    c.prop("mouth_open", [(0, 0), (66, 0), (72, 0.4), (84, 0.1), (n - 1, 0)])
    c.secondary()
    return c


def yawn_stretch():
    """'¡Aaah!': a huge yawn with the arms stretched out and up, on tiptoe, the whole body long and
    trembling with the effort, then it all drops, a shake and a content smack (4 s)."""
    n = 120
    c = Clip(n)
    c.life(seed=441, breath=0.5, hands=False)
    st = C.keys(n, [(0, 0), (10, -0.15), (30, 1.0), (56, 1.0), (64, -0.2), (72, 0.05), (80, 0.0), (n - 1, 0)])
    pos = np.clip(st, 0, None)
    c.sy("spine", 1.0 + 0.025 * pos)
    c.sy("neck", 1.0 + 0.07 * pos)
    c.sy("head", 1.0 + 0.05 * C.delay(st, 2))
    c.add("head.rx", -12 * C.delay(st, 3))
    c.add("chest.rx", -6 * st)
    c.add("spine.rx", -3 * st)
    # on tiptoe: heels up, the hips rise with them
    for s in ("L", "R"):
        c.foot(s, pitch=20 * pos)
        c.arm_raise(s, 58 * pos + C.keys(n, [(0, 0), (60, 0), (66, -8), (74, 2), (82, 0)]))
        c.forearm_lift(s, 36 * C.delay(pos, 2))
        c.arm_fwd(s, C.keys(n, [(0, 0), (10, 8), (30, -6), (56, -6), (70, 0)]))
        c.elbow(s, C.keys(n, [(0, 0), (12, 30), (30, 0), (56, 0), (64, 20), (80, 0)]))
        c.stretch(s, 1.0 + 0.08 * pos)
        c.hand(s, [(0, "relaxed"), (14, "soft"), (30, "spread"), (54, "spread"), (62, "palm_up"), (74, "relaxed")])
    c.add("hips.lz", 0.014 * pos - 0.004 - 0.012 * np.clip(-st, 0, None))
    quiver = C.noise(n, 2, 1.0, seed=13, loop=False) * C.keys(n, [(0, 0), (30, 0), (34, 1), (54, 1), (58, 0)])
    c.add("chest.ry", 1.2 * quiver)
    c.add("head.rz", 1.5 * C.delay(quiver, 1))
    # the shake-out after the stretch
    shake = np.sin(2 * np.pi * np.arange(n) / 6.0) * C.keys(n, [(0, 0), (70, 0), (74, 1), (86, 1), (92, 0)])
    c.add("chest.ry", 4.0 * shake)
    c.add("head.ry", 3.0 * C.delay(shake, 2))
    for s in ("L", "R"):
        c.shrug(s, 5.0 * C.delay(shake, 1))
    yawn = {"blink_L": 1.0, "blink_R": 1.0, "brow_L": 0.5, "brow_R": 0.5, "brow_in_L": 0.6, "brow_in_R": 0.6}
    c.expr([(0, "neutral"), (10, "sleepy"), (20, "neutral"), (28, yawn), (56, yawn), (64, "sleepy", 0.6),
            (90, "happy"), (n - 1, "happy")])
    c.prop("mouth_open", [(0, 0), (12, 0.1), (28, 1.0), (54, 1.0), (62, -0.2), (96, -0.3), (100, 0.1), (104, -0.3),
                          (108, 0.05), (n - 1, 0)])                  # yawn, then a smack of the lips
    c.prop("mouth_round", [(0, 0), (20, 0.6), (50, 0.7), (60, 0.0)])
    c.secondary()
    return c


def victory():
    """'¡Vamos!': winds down into a crouch, punches a fist up beside his head with a little hop,
    then pulls it down hard with a knee up: '¡sí!' (3 s). The 'fist' gesture of the voice
    phrases."""
    n = 90
    c = Clip(n)
    c.life(seed=451, blinks=[80], hands=False)
    s = "R"
    t0, t1 = 16, 26
    c.hop(t0, t1, height=0.035, crouch=0.035, stretch=0.09)
    c.add("hips.lz", -0.004)
    c.arm_raise(s, [(0, 0), (8, -6), (14, -10), (19, 46), (23, 42), (27, 45), (40, 44), (46, 26), (50, 32), (70, 30),
                    (84, 0)])
    c.forearm_lift(s, [(0, 0), (14, -4), (19, 56), (24, 52), (40, 52), (46, 0), (84, 0)])
    c.elbow(s, [(0, 0), (8, 50), (14, 70), (19, 14), (24, 18), (40, 18), (46, 80), (50, 72), (70, 74), (84, 0)])
    c.arm_fwd(s, [(0, 0), (14, -16), (19, 2), (40, 2), (46, 30), (70, 28), (84, 0)])
    c.stretch(s, [(0, 1.0), (16, 1.0), (19, 1.06), (26, 1.04), (40, 1.03), (45, 1.0)])
    c.palm(s, [(0, 0), (14, 0), (19, 20), (40, 20), (46, 50), (70, 50), (84, 0)])
    c.hand(s, [(0, "relaxed"), (8, "fist"), (28, "grip"), (42, "grip"), (49, "fist"), (76, "fist"), (86, "relaxed")])
    c.hand("L", [(0, "relaxed"), (12, "fist"), (32, "grip"), (43, "grip"), (50, "fist"), (76, "fist"), (86, "relaxed")])
    c.elbow("L", [(0, 0), (12, 50), (19, 30), (46, 60), (70, 56), (84, 0)])
    c.arm_raise("L", [(0, 0), (19, 10), (46, 6), (84, 0)])
    # '¡sí!': the fist pulls down, the left knee comes up, the body crunches
    c.foot("L", z=C.pulse(n, 46, [(-4, 0.0), (2, 0.05), (14, 0.045), (22, 0.0)]),
           pitch=C.pulse(n, 46, [(-4, 0), (2, -10), (14, -8), (22, 0)]))
    c.weight([(0, 0), (10, 0.0), (40, 0.0), (44, -0.9), (66, -0.8), (80, 0), (n - 1, 0)])
    c.add("spine.rx", [(0, 0), (40, 0), (47, 9), (52, 6), (68, 6), (80, 0)])
    c.add("head.rx", [(0, 0), (40, -4), (47, 8), (52, 5), (68, 5), (80, 0)])
    c.add("chest.rz", [(0, 0), (12, 8), (19, -10), (40, -8), (47, 6), (70, 4), (84, 0)])
    c.squash(46, -0.08, "head", dur=10)
    c.expr([(0, "neutral"), (8, "determined"), (17, "joy"), (40, "joy"), (46, "determined"), (66, "joy"),
            (n - 1, "happy")])
    c.prop("mouth_open", [(0, 0), (14, -0.3), (19, 0.9), (30, 0.6), (40, 0.2), (46, 0.8), (56, 0.4), (68, 0.0),
                          (n - 1, 0)])
    c.prop("teeth", [(0, 0), (17, 0), (19, 0.6), (40, 0.4), (46, 0.7), (60, 0.0)])
    c.secondary()
    return c


def wave_both():
    """'¡Holaaa!': both arms up and waving out of step, bouncing on his toes (3.5 s)."""
    n = 105
    c = Clip(n)
    c.life(seed=461, blinks=[94], hands=False)
    f = np.arange(n)
    env = C.keys(n, [(0, 0), (20, 0), (26, 1), (76, 1), (84, 0), (104, 0)])
    for s, ph in (("L", 0.0), ("R", 0.5)):
        c.arm_raise(s, [(0, 0), (6, -6), (15, 45), (20, 39), (24, 42), (80, 42), (90, -6), (97, 1), (104, 0)])
        c.arm_swing(s, [(0, 0), (8, 0), (16, 22), (80, 22), (92, 0), (104, 0)])
        c.forearm_lift(s, [(0, 0), (9, -4), (17, 48), (22, 39), (26, 42), (80, 42), (90, 0), (104, 0)])
        c.elbow(s, [(0, 0), (6, 16), (17, 4), (80, 4), (92, 6), (104, 0)])
        c.stretch(s, [(0, 1.0), (10, 1.0), (16, 1.06), (24, 1.04), (80, 1.04), (90, 1.0)])
        w = motor.wave_drive(n, 20, 84, period=13.0, seed=471 + (0 if s == "L" else 9), phase=ph)
        c.forearm_lift(s, -np.where(w < 0, 15.0, 7.0) * w)
        c.elbow(s, 4.0 * C.delay(w, -2.0))
        c.wrist(s, side=C.delay(-24.0 * w, 3.5), flex=np.array(C.keys(n, [(0, 0), (16, -8), (80, -8), (92, 0)]))
                + 8.0 * C.delay(w, 6.0))
        c.palm(s, C.keys(n, [(0, 0), (10, 0), (18, 76), (80, 72), (91, 0), (104, 0)]) + 8.0 * C.delay(w, 2.0))
        c.finger_roll(s, C.delay(w, 3.0), amp=10.0, lag=1.5)
        c.hand(s, [(0, "relaxed"), (8, "soft"), (17, "open" if s == "L" else "spread"), (82, "open" if s == "L" else "spread"),
                   (94, "relaxed")])
    bounce = np.maximum(0, np.sin(2 * np.pi * (f - 20) / 6.5)) * env
    c.add("hips.lz", -0.006 * bounce - 0.004)
    for s in ("L", "R"):
        c.foot(s, pitch=10 * C.delay(bounce, 1))
    c.add("head.ry", 2.0 * np.sin(2 * np.pi * (f - 20) / 26.0) * env)
    c.add("head.rx", [(0, 0), (6, 4), (16, -6), (80, -4), (96, 0)])
    c.squash(6, -0.06, "head", dur=6)
    c.squash(15, 0.08, "head", dur=14)
    c.add("hips.lz", [(0, 0), (6, -0.014), (14, 0.0), (104, 0)])
    c.expr([(0, "happy", 0.6), (12, "joy"), (84, "joy"), (104, "happy")])
    c.prop("mouth_open", [(0, 0), (14, 0.3), (22, 0.8), (40, 0.4), (84, 0.3), (104, 0)])   # '¡holaaa!'
    c.secondary()
    return c


def peek():
    """'¿Qué hay ahí?': crouches, then leans way over to his left on one foot to peek round
    something, neck stretched, eyes wide; '¡oh!'; and back (3.5 s)."""
    n = 105
    c = Clip(n)
    c.life(seed=471, blinks=[52, 98], hands=False, sway=0.4)
    lean = C.keys(n, [(0, 0), (8, -0.15), (12, -0.12), (24, 1.0), (28, 0.9), (32, 0.95), (70, 0.95), (78, 1.02),
                      (88, -0.08), (94, 0.03), (100, 0), (n - 1, 0)])
    c.weight(np.clip(lean, -0.5, 1.0) * 1.0, heel=0.0)
    c.add("hips.lx", 0.012 * lean)
    c.add("spine.ry", 9 * lean)
    c.add("chest.ry", 8 * C.delay(lean, 1))
    c.add("neck.ry", 5 * C.delay(lean, 2))
    c.add("head.ry", 7 * C.delay(lean, 3))
    c.add("spine.rx", 4 * lean)
    c.sy("neck", 1.0 + 0.06 * np.clip(C.delay(lean, 3), 0, None))
    c.add("hips.lz", [(0, -0.004), (8, -0.016), (14, -0.006), (88, -0.006), (94, -0.012), (n - 1, -0.004)])
    # the free (right) leg floats out to balance the lean
    c.foot("R", x=-0.02 * np.clip(lean, 0, None), z=0.035 * np.clip(C.delay(lean, 2), 0, None) ** 2,
           pitch=-10 * np.clip(lean, 0, None))
    for s in ("L", "R"):                          # hands up at the chest like paws
        c.elbow(s, 60 * np.clip(C.delay(lean, 2), 0, None) + C.keys(n, [(0, 0), (8, 14), (14, 0)]))
        c.arm_fwd(s, 26 * np.clip(C.delay(lean, 2), 0, None))
        c.wrist(s, flex=-45 * np.clip(C.delay(lean, 4), 0, None))
        c.hand(s, [(0, "relaxed"), (18, "soft"), (84, "soft"), (96, "relaxed")])
    c.arm_raise("R", -12 * np.clip(lean, 0, None) + 26 * np.clip(C.delay(lean, 5), 0, None) * 0.5)
    c.prop("gaze_x", [(0, 0), (10, 0), (12, 0.8), (30, 0.7), (50, 0.75), (54, 0.5), (60, 0.8), (84, 0.7),
                      (88, 0), (n - 1, 0)])
    c.prop("gaze_y", [(0, 0), (12, 0.1), (84, 0.1), (88, 0)])
    c.squash(68, 0.06, "head", dur=10)
    c.expr([(0, "neutral"), (10, "neutral"), (16, "confused", 0.5), (56, "confused", 0.5), (66, "surprised"),
            (76, "joy"), (n - 1, "happy")])
    c.prop("pupil", [(0, 0), (16, 0.5), (60, 0.5), (66, -0.4), (76, 0.4), (n - 1, 0)])
    c.prop("mouth_round", [(0, 0), (20, 0.3), (60, 0.3), (66, 0.9), (76, 0), (n - 1, 0)])
    c.secondary()
    return c


def shiver():
    """'¡Brrr!': shoulders up, arms tight with the fists up at his chest, the whole body trembling,
    teeth chattering, knees knocking; then he shakes it off (3.5 s)."""
    n = 105
    c = Clip(n)
    c.life(seed=481, blinks=[30, 60], hands=False, breath=0.5)
    env = C.keys(n, [(0, 0), (8, 0), (14, 1), (70, 1), (76, 0), (n - 1, 0)])
    tr = C.noise(n, 2, 1.0, seed=17, loop=False) * env
    chatter = np.sin(2 * np.pi * np.arange(n) / 5.0) * env
    c.add("hips.lx", 0.003 * tr)
    c.add("chest.rz", 2.0 * C.delay(tr, 1))
    c.add("head.rz", 2.5 * C.delay(tr, 2))
    c.add("head.rx", [(0, 0), (12, 6), (70, 5), (80, 0)])
    c.add("spine.rx", [(0, 0), (12, 5), (70, 4), (80, 0)])
    c.add("hips.lz", [(0, -0.004), (12, -0.014), (70, -0.012), (80, -0.004)])
    c.sy("neck", [(0, 1.0), (12, 1.0), (16, 0.95), (70, 0.955), (78, 1.0)])          # head sunk in the shoulders
    for s, sg in (("L", 1), ("R", -1)):
        c.shrug(s, [(0, 0), (12, 10), (70, 9), (78, 0)])
        c.elbow(s, [(0, 0), (12, 80), (70, 80), (80, 0)])
        c.arm_fwd(s, [(0, 0), (12, 20), (70, 20), (80, 0)])
        c.forearm_in(s, [(0, 0), (12, 26), (70, 26), (80, 0)])
        c.arm_raise(s, [(0, 0), (12, -4), (70, -4), (80, 0)])
        c.hand(s, [(0, "relaxed"), (10, "fist"), (72, "fist"), (82, "relaxed")])
        c.hand_flutter(s, 1.3, env)                                          # shivering fingers
        c.elbow(s, 4.0 * C.delay(tr, 1 + (s == "R")))
        c.foot(s, turn=-6.0 * sg * env + 4.0 * sg * chatter)                 # knees in, knocking
    c.prop("teeth", 0.8 * env)
    c.prop("mouth_open", 0.18 + 0.16 * chatter * env - 0.18 * (1 - env))
    c.prop("smile", 0.15 * env)
    # shaking it off
    shake = np.sin(2 * np.pi * np.arange(n) / 6.0) * C.keys(n, [(0, 0), (76, 0), (80, 1), (90, 1), (96, 0)])
    c.add("chest.ry", 5.0 * shake)
    c.add("head.ry", 4.0 * C.delay(shake, 2))
    c.add("hips.lx", 0.006 * C.delay(shake, 1))
    c.expr([(0, "neutral"), (10, "scared", 0.4), (70, "scared", 0.4), (80, "calm", 0.6), (92, "happy"),
            (n - 1, "happy")])
    c.prop("squint", [(0, 0), (12, 0.5), (70, 0.5), (78, 0)])
    c.secondary()
    return c


def sneak(steps=48):
    """Tiptoe sneaking cycle in place (loops, two steps in 1.6 s): crouched and leaning in, knees up
    high, each foot set down toe first, paws up, shifty eyes. The showcase adds the root travel."""
    n = steps
    c = Clip(n, loop=True)
    c.life(seed=491, breath=0.3, sway=0.3, hands=False)
    stride, lift = 0.05, 0.065
    half = n / 2
    f = np.arange(n)
    for s, off in (("L", 0.0), ("R", half)):
        ph = ((f - off) % n) / n
        stance = ph < 0.55
        sw = np.clip((ph - 0.55) / 0.45, 0, 1)
        y = np.where(stance, -stride + 2 * stride * (ph / 0.55), stride - 2 * stride * (0.5 - 0.5 * np.cos(np.pi * sw)))
        z = np.where(stance, 0.0, lift * np.sin(np.pi * sw) ** 0.8)
        pitch = np.where(stance, 22 * np.exp(-(ph / 0.08) ** 2) + 10 * np.exp(-((ph - 0.55) / 0.08) ** 2),
                         -6 + 28 * sw ** 2)                          # toes reach down before landing
        c.foot(s, y=y, z=z, pitch=pitch)
    down = C.sine(n, half, 1.0, phase=0.25)
    c.add("hips.lz", 0.006 * down - 0.026)
    c.add("hips.lx", C.sine(n, n, 0.012, phase=0.25))
    c.add("hips.rz", C.sine(n, n, -5.0))
    c.add("spine.rx", 10.0)
    c.add("chest.rx", 4.0)
    c.add("chest.rz", C.sine(n, n, 5.0))
    c.add("head.rx", -6.0 + C.delay(-1.5 * down, 3, loop=True))
    for s in ("L", "R"):                           # paws up in front, wrists dropped
        c.elbow(s, 96)
        c.arm_fwd(s, 26 + C.delay(C.sine(n, n, 4.0, phase=0.25 if s == "L" else 0.75), 3, loop=True))
        c.forearm_in(s, 10)
        c.wrist(s, flex=-55)
        c.hand(s, [(0, "relaxed")])
    # shifty: the eyes dart one way then the other, the head follows late
    look = C.keys(n, [(0, 0.0), (6, 0.7), (20, 0.7), (26, -0.7), (42, -0.7), (47, 0.0)], loop=True)
    c.prop("gaze_x", look)
    c.add("head.rz", 12.0 * C.delay(look, 4, loop=True))
    c.expr([(0, "smug")], scale=0.8)
    c.prop("mouth_open", -0.8)
    c.secondary()
    c.stride = stride
    return c


def sleepy():
    """Dozing off on his feet: the lids drop, the head sinks... a jerk awake with wide eyes, blinks,
    and it starts again; finally he shakes his head and wakes up (5 s)."""
    n = 150
    c = Clip(n)
    c.life(seed=501, breath=0.8, sway=0.6, hands=False)
    sink = C.keys(n, [(0, 0), (10, 0.05), (44, 1.0), (49, 1.05), (52, -0.25), (58, 0.0), (66, 0.0), (100, 0.75),
                      (108, 0.8), (112, -0.15), (118, 0.05), (128, 0.0), (n - 1, 0)])
    c.add("head.rx", 14 * sink)
    c.add("neck.rx", 5 * C.delay(sink, 2))
    c.add("chest.rx", 4 * C.delay(sink, 4))
    c.add("head.ry", 6 * np.clip(sink, 0, None))
    c.add("hips.lz", -0.008 * np.clip(sink, 0, None) - 0.004)
    for s in ("L", "R"):
        c.arm_raise(s, -5 * np.clip(sink, 0, None))
        c.shrug(s, -4 * np.clip(sink, 0, None) + C.pulse(n, 50, [(-2, 0), (2, 9), (8, 0)]))
        c.hand(s, [(0, "relaxed"), (40, "rest"), (50, "spread"), (60, "relaxed"), (100, "rest"), (112, "soft"),
                   (124, "relaxed")])
    # the jerk awake: a little hop of fright, head stretched
    c.add("root.lz", C.arc(n, 50, 56, 0.015))
    c.squash(51, 0.08, "head", dur=10)
    c.squash(111, 0.05, "head", dur=10)
    c.expr([(0, "neutral"), (12, "sleepy", 0.6), (44, "sleepy"), (49, "sleepy"), (51, "surprised"), (58, "neutral"),
            (70, "sleepy", 0.7), (104, "sleepy"), (111, "surprised", 0.6), (120, "neutral"), (136, "happy", 0.6),
            (n - 1, "happy", 0.5)])
    c.prop("lid_drop", [(0, 0), (30, 0.2), (46, 0.3), (50, 0.0), (90, 0.1), (106, 0.3), (110, 0)])
    c.prop("blink_L", [(0, 0), (40, 0.5), (48, 0.9), (51, 0.0), (58, 0), (60, 1), (63, 0), (66, 0), (68, 1), (71, 0),
                       (96, 0.5), (106, 0.85), (111, 0.0)])
    c.prop("blink_R", [(0, 0), (40, 0.5), (48, 0.9), (51, 0.0), (58, 0), (60, 1), (63, 0), (66, 0), (68, 1), (71, 0),
                       (96, 0.5), (106, 0.85), (111, 0.0)])
    c.prop("mouth_open", [(0, 0), (30, 0.1), (46, 0.25), (50, 0.5), (56, 0.0), (80, 0.0), (88, 0.6), (96, 0.1),
                          (106, 0.2), (112, 0.4), (120, 0.0), (n - 1, 0)])
    c.prop("mouth_round", [(0, 0), (80, 0), (88, 0.6), (96, 0)])                        # a small yawn
    shake = np.sin(2 * np.pi * np.arange(n) / 7.0) * C.keys(n, [(0, 0), (120, 0), (124, 1), (134, 1), (140, 0)])
    c.add("head.rz", 6.0 * shake)
    c.secondary()
    return c


def tap_foot():
    """Impatient: hands on his hips, weight on one leg, the other foot tapping, an eye roll and a
    big sigh, then two more taps (4 s)."""
    n = 120
    c = Clip(n)
    c.life(seed=511, blinks=[40, 96], hands=False, sway=0.5)
    for s, sg in (("L", 1), ("R", -1)):            # fists on the hips, elbows out to the sides
        c.arm_raise(s, [(0, 0), (6, -4), (14, 44), (18, 40), (104, 40), (116, 0)])
        c.forearm_lift(s, [(0, 0), (14, -46), (18, -42), (104, -42), (116, 0)])
        c.elbow(s, [(0, 0), (14, 24), (104, 24), (116, 0)])
        c.arm_fwd(s, [(0, 0), (14, -6), (104, -6), (116, 0)])
        c.palm(s, [(0, 0), (14, 20), (104, 20), (116, 0)])
        c.hand(s, [(0, "relaxed"), (12, "fist"), (106, "fist"), (116, "relaxed")])
    c.weight([(0, 0), (10, 0.7), (110, 0.65), (119, 0)], heel=0.0)
    taps = [18, 28, 38, 48, 86, 94]
    tap = sum(C.pulse(n, t, [(-4, 0.0), (0, 1.0), (3, 0.0)]) for t in taps)
    # toes up on the heel, the foot lifted a hair so the back of the shoe does not dig into the floor
    c.foot("R", pitch=-20 * tap, z=0.012 * tap, x=-0.015 * C.keys(n, [(0, 0), (12, 1), (104, 1), (116, 0)]))
    for t in taps:
        c.add("head.rx", C.pulse(n, t, [(-2, 0), (2, 1.5), (6, 0)]))
    c.add("head.ry", [(0, 0), (12, -7), (54, -6), (60, 4), (80, 5), (86, -6), (110, -5), (119, 0)])
    c.add("head.rz", [(0, 0), (12, 4), (54, 4), (62, -6), (80, -5), (88, 3), (110, 3), (119, 0)])
    # the sigh: chest up, everything drops, a puff of the cheeks
    c.sy("chest", [(0, 1.0), (56, 1.0), (64, 1.025), (74, 0.985), (84, 1.0)])
    for s in ("L", "R"):
        c.shrug(s, [(0, 0), (56, 0), (64, 8), (74, -3), (84, 0)])
    c.expr([(0, "neutral"), (10, "skeptical"), (56, "skeptical"), (62, "sleepy", 0.6), (78, "skeptical"),
            (110, "skeptical", 0.7), (n - 1, "neutral")])
    c.prop("gaze_y", [(0, 0), (56, 0), (60, 0.8), (70, 0.75), (76, 0), (n - 1, 0)])          # the eye roll
    c.prop("gaze_x", [(0, 0), (56, 0), (60, -0.3), (66, 0.3), (72, 0.2), (76, 0), (n - 1, 0)])
    c.prop("mouth_round", [(0, 0), (66, 0), (72, 0.6), (80, 0)])
    c.prop("mouth_open", [(0, 0), (66, -0.6), (72, 0.2), (80, -0.6), (n - 1, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def scratch_head():
    """'Mmm...': scratches the side of his head with his fingertips (they really touch it; the arm
    stretches a little to get there): the head tilts and turns into the hand, the elbow goes out to the
    side, the fingers scratch in short strokes, eyes up, mouth to the side (3.5 s)."""
    n = 105
    c = Clip(n)
    c.max_reach = 1.15
    c.contacts = []
    c.life(seed=521, blinks=[50, 96], hands=False, sway=0.5)
    s = "R"
    # the side of his big head comes down to meet the short arm: a tilt and a nod into the hand and a
    # turn towards it (a deeper tilt would drop the corner of the head onto the sleeve)
    tilt = C.keys(n, [(0, 0), (8, 0.1), (22, 1.0), (30, 0.9), (76, 1.0), (92, 0)])
    c.add("head.ry", -5 * tilt)
    c.add("neck.ry", -2 * tilt)
    c.add("head.rz", [(0, 0), (22, -12), (80, -10), (94, 0)])
    c.add("head.rx", [(0, 0), (22, 6), (80, 6), (94, 0)])
    c.shrug(s, [(0, 0), (12, 3), (22, 7), (80, 7), (92, 0)])
    c.add("shoulder.R.rz", [(0, 0), (22, 8), (80, 8), (92, 0)])
    # the wrist stays low and out beside the jaw (under the head's lower edge: the sleeve never meets
    # the skull) and the fingers stand up along the side of the head, leaning in
    wrist = (-0.345, -0.03, 0.415)
    c.reach(s, [(0, None), (6, None), (14, (-0.29, -0.04, 0.36)), (22, wrist), (82, wrist), (92, None)])
    rx, ry, rz = orient_keys(s, [(0, (0.5, -0.05, 1.0), (1.0, 0.0, -0.3))])           # fingers up and in, palm to the head
    c.reach_rot(s, rx, ry, rz)
    region = [f"index.03.{s}", f"middle.03.{s}", f"ring.03.{s}", f"index.02.{s}", f"middle.02.{s}"]
    # scratch, scratch: short strokes (the hand lifts a hair between them), back and forth along the skin
    for k, f0 in enumerate(range(28, 76, 10)):
        y, z = (0.0, 0.534) if k % 2 else (-0.07, 0.542)
        c.contacts.append({"side": s, "touch": "head", "point": (-0.283, y, z), "frames": (f0, f0 + 6), "ramp": 3,
                           "region": region})
    c.hand(s, [(0, "relaxed"), (14, "soft"), (22, "scratch"), (80, "scratch"), (92, "relaxed")])
    env = C.keys(n, [(0, 0), (28, 0), (32, 1), (74, 1), (78, 0), (n - 1, 0)])
    wiggle = np.sin(2 * np.pi * np.arange(n) / 6.0) * env                       # scratch scratch
    for fing in ("index", "middle", "ring"):
        for seg in (1, 2):
            c.add(f"{fing}.{seg:02d}.{s}.cx", 14.0 * wiggle)
    c.hand("L", [(0, "relaxed"), (20, "soft"), (80, "soft"), (94, "relaxed")])
    c.weight([(0, 0), (12, -0.5), (80, -0.45), (96, 0)])
    c.expr([(0, "neutral"), (14, "confused"), (80, "confused"), (96, "happy", 0.6), (n - 1, "happy", 0.5)])
    c.prop("gaze_x", [(0, 0), (18, 0.4), (50, 0.35), (54, -0.2), (78, -0.2), (86, 0)])
    c.prop("gaze_y", [(0, 0), (18, 0.6), (78, 0.55), (86, 0)])
    c.prop("mouth_side", [(0, 0), (20, -0.8), (50, -0.8), (56, 0.6), (78, 0.6), (88, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def facepalm():
    """'¡Ay, no!': realises, the head falls forward onto his chest and tilts into his palm, which comes up
    over his mouth and chin (the hand really rests on the face; the face of a head that low is the
    only part a 20 cm arm can cover), eyes shut, a slow head shake and a sigh; then he looks up with a
    sheepish smile (3.5 s)."""
    n = 105
    c = Clip(n)
    c.max_reach = 1.15
    c.contacts = []
    c.life(seed=531, blinks=[96], hands=False, sway=0.5)
    s = "R"
    drop = C.keys(n, [(0, 0), (6, -0.15), (10, -0.2), (22, 1.0), (26, 0.9), (78, 0.95), (90, -0.1), (96, 0.0),
                      (n - 1, 0)])
    # the head does most of the work: it falls forward and tilts to his right, into the hand
    top = {"head": (24.0, -8.0, -8.0), "neck": (8.0, 0.0, 0.0), "chest": (5.0, 0.0, 0.0), "spine": (5.0, 0.0, 0.0)}
    c.add("head.rx", top["head"][0] * drop)
    c.add("head.ry", top["head"][1] * drop)
    c.add("head.rz", top["head"][2] * drop)
    c.add("neck.rx", top["neck"][0] * drop)
    c.add("spine.rx", top["spine"][0] * drop)
    c.add("chest.rx", top["chest"][0] * C.delay(drop, 3))
    shake = np.sin(2 * np.pi * (np.arange(n) - 34) / 18.0) * C.keys(n, [(0, 0), (34, 0), (40, 1), (64, 1),
                                                                         (70, 0), (n - 1, 0)])
    c.add("head.ry", 2.5 * shake)
    c.add("shoulder.R.rz", [(0, 0), (12, 24), (80, 24), (92, 0)])      # the right shoulder hunches up and forward
    c.shrug(s, [(0, 0), (12, 8), (80, 8), (92, 0)])
    # the head comes down to the hand: the palm covers his mouth and chin, the fingers stand up the cheeks
    near = (-0.10, -0.19, 0.43)
    c.reach(s, [(0, None), (6, None), (14, (-0.12, -0.14, 0.42)), (24, near), (82, near), (94, None)])
    fingers, palm = (0.12, -0.15, 1.0), (0.35, 0.9, 0.1)
    rx, ry, rz = orient_keys(s, [(0, fingers, palm)])
    c.reach_rot(s, rx, ry, rz)
    c.contacts.append({"side": s, "touch": "head", "point": (-0.06, -0.19, 0.60), "frames": (26, 78), "ramp": 6,
                       "region": [f"hand.{s}", f"index.01.{s}", f"middle.01.{s}", f"ring.01.{s}", f"index.02.{s}",
                                  f"middle.02.{s}", f"ring.02.{s}"]})
    # the fingers that stand up his cheek are part of the touch: exact angles (the contact solver aims them)
    cheek = dict(motor.HAND_SHAPES["spread"], _loose=0.05)
    c.hand(s, [(0, "relaxed"), (14, cheek), (82, cheek), (92, "relaxed")])
    c.hand("L", [(0, "relaxed"), (24, "rest"), (80, "rest"), (94, "relaxed")])
    c.arm_raise("L", [(0, 0), (24, -6), (80, -6), (94, 0)])
    c.sy("chest", [(0, 1.0), (44, 1.0), (52, 1.02), (62, 0.985), (72, 1.0)])     # the sigh
    for side in ("L", "R"):
        c.shrug(side, C.pulse(n, 52, [(-8, 0), (0, 4), (10, -3), (20, 0)]))
    c.weight([(0, 0), (16, -0.4), (80, -0.35), (96, 0)])
    c.add("hips.lz", [(0, -0.004), (24, -0.016), (80, -0.016), (96, -0.004)])
    c.expr([(0, "neutral"), (4, "surprised", 0.5), (12, "sad", 0.4), (22, "calm"), (78, "calm"), (86, "shy"),
            (n - 1, "happy", 0.6)])
    c.prop("brow_in_L", [(0, 0), (20, 0.7), (78, 0.7), (88, 0.3), (n - 1, 0)])
    c.prop("brow_in_R", [(0, 0), (20, 0.7), (78, 0.7), (88, 0.3), (n - 1, 0)])
    c.prop("smile", [(0, 0), (20, -0.3), (78, -0.3), (88, 0.3), (n - 1, 0)])
    c.prop("mouth_open", [(0, 0), (4, 0.4), (10, 0.0), (50, -0.2), (56, 0.3), (66, -0.3), (n - 1, 0)])
    c.secondary()
    return c


def blow_kiss():
    """'¡Muak!': a flat hand to his mouth (lips puckered, eyes closed), then the hand sweeps out and
    forward with the palm open, as if flinging the kiss to the viewer, with a tiny hop; dreamy eyes, a
    happy tilt (3 s)."""
    n = 90
    c = Clip(n)
    c.max_reach = 1.12
    c.contacts = []
    c.life(seed=541, blinks=[80], hands=False, sway=0.5)
    s = "R"
    c.add("shoulder.R.rz", [(0, 0), (8, 24), (22, 24), (28, -4), (60, 0)])
    c.shrug(s, [(0, 0), (8, 8), (22, 8), (28, 2), (60, 0)])
    near = (-0.06, -0.16, 0.44)
    c.reach(s, [(0, None), (4, None), (10, near), (21, near), (27, None)])
    rx, ry, rz = orient_keys(s, [(0, (0.12, -0.15, 1.0), (0.35, 0.9, 0.1))])        # flat hand up, palm to his face
    c.reach_rot(s, rx, ry, rz)
    c.contacts.append({"side": s, "touch": "head", "point": (-0.03, -0.15, 0.53), "frames": (13, 19), "ramp": 3,
                       "region": [f"index.03.{s}", f"middle.03.{s}", f"ring.03.{s}"]})
    # the fling (FK under the IK until it lets go): the arm sweeps forward and up, palm open to the viewer
    c.arm_fwd(s, [(0, 0), (20, 30), (26, 52), (32, 44), (36, 48), (60, 40), (76, 0)])
    c.arm_raise(s, [(0, 0), (20, 10), (26, 34), (34, 44), (60, 36), (76, 0)])
    c.elbow(s, [(0, 0), (20, 90), (26, 22), (32, 34), (36, 30), (60, 34), (76, 0)])
    c.palm(s, [(0, 0), (20, 40), (26, -50), (60, -46), (76, 0)])
    c.wrist(s, flex=[(0, 0), (22, 0), (27, -22), (31, 12), (36, 0), (76, 0)])           # the flick
    c.stretch(s, [(0, 1.0), (22, 1.0), (26, 1.08), (32, 1.05), (60, 1.05), (72, 1.0)])
    flutter = np.sin(2 * np.pi * (np.arange(n) - 27) / 9.0) * C.keys(n, [(0, 0), (27, 0), (30, 1), (46, 0.5), (60, 0), (n - 1, 0)])
    c.finger_roll(s, flutter, amp=10.0, lag=1.5)
    c.hand(s, [(0, "relaxed"), (8, "hold_flat"), (21, "hold_flat"), (26, "spread"), (44, "open"), (62, "soft"), (76, "relaxed")])
    c.hand("L", [(0, "relaxed"), (24, "soft"), (60, "soft"), (76, "relaxed")])
    c.add("spine.rx", [(0, 0), (12, -2), (22, -2), (28, 5), (34, 3), (60, 2), (76, 0)])
    c.add("head.ry", [(0, 0), (10, 5), (22, 6), (30, -5), (60, -6), (76, 0)])
    c.weight([(0, 0), (12, 0.4), (22, 0.4), (28, -0.6), (60, -0.5), (78, 0)])
    c.hop(24, 32, height=0.02, crouch=0.01, stretch=0.04)                              # a tiny hop with the throw
    c.expr([(0, "happy", 0.6), (8, "love"), (22, "love"), (26, "joy"), (34, "love", 0.8), (62, "happy"),
            (n - 1, "happy", 0.6)])
    c.prop("mouth_round", [(0, 0), (8, 1.0), (22, 1.0), (25, 0.0)])                    # the pucker...
    c.prop("mouth_open", [(0, 0), (8, -0.4), (22, -0.4), (25, 0.5), (30, 0.2), (n - 1, 0)])  # ...'¡muak!'
    c.prop("smile", [(0, 0), (8, -0.5), (22, -0.5), (25, 0)])
    c.prop("pupil", [(0, 0), (30, 1.0), (60, 0.8), (n - 1, 0)])
    c.secondary()
    return c


MOVES = {
    "Spin": spin,
    "Hop_Steps": hop_steps,
    "Dance_2": dance_2,
    "Bow": bow,
    "Yawn_Stretch": yawn_stretch,
    "Victory": victory,
    "Wave_Both": wave_both,
    "Peek": peek,
    "Shiver": shiver,
    "Sneak": sneak,
    "Sleepy": sleepy,
    "Tap_Foot": tap_foot,
    # scratch_head is deliberately not registered: a 20 cm arm cannot reach the upper head, so it never read as scratching.
    "Facepalm": facepalm,
    "Blow_Kiss": blow_kiss,
}
