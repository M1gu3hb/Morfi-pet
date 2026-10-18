"""Morfi's conversational actions (chatbot, point of sale): talk, present, yes, no, dance."""
import numpy as np

from . import curves as C
from .clip import Clip


def _speech(n, start, end, seed):
    """Mouth curve for speech: phrases of syllables (~5 per second) with short pauses.

    Returns (mouth_open, mouth_round, phrase_starts, stressed_frames).
    """
    rng = np.random.default_rng(seed)
    pts, rnd, starts, stress = [(0, -0.2)], [(0, 0.0)], [], []
    t = start
    while t < end - 12:
        length = int(rng.uniform(28, 46))
        starts.append(t)
        stress.append(t + 2)
        f = t
        syl = 0
        while f < min(t + length, end - 6):
            step = int(rng.integers(4, 8))
            closed = rng.random() < 0.18                      # m / b / p: lips meet
            amp = -0.95 if closed else rng.uniform(-0.25, 0.75) + (0.25 if syl == 0 else 0.0)
            pts += [(f, amp), (f + step * 0.55, amp * 0.85)]
            rnd.append((f, 0.8 if rng.random() < 0.15 else 0.0))
            if rng.random() < 0.12:
                stress.append(f)
            f += step
            syl += 1
        pts.append((f + 2, -0.55))
        rnd.append((f + 2, 0.0))
        t = f + int(rng.uniform(8, 16))                       # breath between phrases
    pts.append((n - 1, -0.1))
    rnd.append((n - 1, 0.0))
    # speech never fully settles between syllables: soften with a fast spring
    mouth = C.spring(C.keys(n, pts), freq=7.0, damping=0.75)
    return np.clip(mouth, -1, 1), np.clip(C.keys(n, rnd), 0, 1), starts, stress


def talk():
    """Explaining something to the viewer: speech, the weight changes foot on every phrase, the
    knees and hands beat on the stressed words, a new hand idea per phrase (6 s)."""
    n = 180
    c = Clip(n)
    c.life(seed=51, blinks=[47, 118, 166], hands=False)
    mouth, rnd, starts, stress = _speech(n, 6, n - 10, seed=7)
    c.prop("mouth_open", mouth)
    c.prop("mouth_round", rnd)
    c.prop("smile", 0.5)
    # weight on one foot per phrase, the torso turns into it
    side, wk, turn = 1, [(0, 0)], [(0, 0)]
    for t0 in starts:
        wk += [(t0 - 3, wk[-1][1]), (t0 + 8, 0.8 * side), (t0 + 12, 0.65 * side)]
        turn += [(t0 + 2, turn[-1][1]), (t0 + 10, 5.0 * side)]
        side = -side
    wk += [(n - 14, wk[-1][1]), (n - 1, 0)]
    turn += [(n - 14, turn[-1][1]), (n - 1, 0)]
    c.weight(wk)
    c.add("chest.rz", turn)
    # hands come up into the gesture space; each phrase gets its own idea (open palms, a point,
    # a soft hand), and they beat on the stresses
    shapes = [("spread", "soft"), ("point", "soft"), ("open", "open"), ("soft", "spread")]
    hr, hl = [(0, "relaxed")], [(0, "relaxed")]
    for k, t0 in enumerate(starts):
        a, b = shapes[k % len(shapes)]
        hr += [(t0 - 2, hr[-1][1]), (t0 + 4, a)]
        hl += [(t0 + 1, hl[-1][1]), (t0 + 7, b)]
    hr += [(n - 16, hr[-1][1]), (n - 6, "relaxed")]
    hl += [(n - 14, hl[-1][1]), (n - 4, "relaxed")]
    c.hand("R", hr)
    c.hand("L", hl)
    for s, lag in (("R", 0), ("L", 4)):
        c.elbow(s, [(0, 0), (6 + lag, -6), (18 + lag, 58), (24 + lag, 50), (n - 22, 50), (n - 8, -4), (n - 1, 0)])
        c.forearm_in(s, [(0, 0), (12, 0), (24, 16), (n - 22, 16), (n - 8, 0)])
        c.arm_fwd(s, [(0, 0), (10, -4), (22, 14), (n - 22, 14), (n - 8, 0)])
        c.arm_raise(s, [(0, 0), (12, 0), (24, 8), (n - 22, 8), (n - 8, 0)])
        c.palm(s, [(0, 0), (14, 0), (26, 40), (n - 22, 40), (n - 8, 0)])
    # beats: on stressed syllables a hand dips and pops (alternating), the knees give, the head nods
    beat_r, beat_l, nod = np.zeros(n), np.zeros(n), np.zeros(n)
    f = np.arange(n)
    for k, t0 in enumerate(stress):
        if t0 < 24 or t0 > n - 26:
            continue
        pulse = np.exp(-((f - t0 - 3) / 3.0) ** 2) - 0.5 * np.exp(-((f - t0 - 9) / 3.5) ** 2)
        (beat_r if k % 2 == 0 else beat_l)[:] += pulse
        nod += pulse * (1.0 if k % 3 else 1.6)
        if k % 2 == 0:
            c.dip(t0, depth=0.009, chest=2.0, dur=12)
    c.elbow("R", beat_r * 14.0)
    c.elbow("L", beat_l * 14.0)
    c.arm_raise("R", beat_r * 5.0)
    c.arm_raise("L", beat_l * 5.0)
    c.wrist("R", flex=C.delay(beat_r * 14.0, 2))
    c.wrist("L", flex=C.delay(beat_l * 14.0, 2))
    c.add("head.rx", C.delay(nod * 4.5, 1))
    c.sy("head", 1.0 + 0.025 * C.delay(np.clip(nod, 0, None), 1))
    # each phrase gets its own head attitude and a brow lift at its start
    tilt_pts, turn_pts, brow_pts = [(0, 0)], [(0, 0)], [(0, 0)]
    rng = np.random.default_rng(3)
    for t0 in starts:
        tilt_pts.append((t0 + 6, rng.uniform(-8, 8)))
        turn_pts.append((t0 + 8, rng.uniform(-9, 9)))
        brow_pts += [(t0, 0.1), (t0 + 4, rng.uniform(0.5, 0.9)), (t0 + 22, 0.2)]
    tilt_pts.append((n - 1, 0))
    turn_pts.append((n - 1, 0))
    brow_pts.append((n - 1, 0))
    c.add("head.ry", tilt_pts)
    c.add("head.rz", turn_pts)
    c.prop("brow_L", brow_pts)
    c.prop("brow_R", [(t, v * 0.85) for t, v in brow_pts])
    c.prop("squint", [(0, 0.1), (n - 1, 0.1)])
    # a glance up while "thinking" in a pause, then back to the viewer
    c.prop("gaze_x", [(0, 0), (80, 0), (82, 0.35), (96, 0.3), (98, 0), (n - 1, 0)])
    c.prop("gaze_y", [(0, 0), (80, 0), (82, 0.45), (96, 0.4), (98, 0), (n - 1, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def present():
    """'¡Mira esto!': the left arm sweeps in, then opens wide towards something beside him (palm up,
    a little stretch), he looks at it, then a double take to the viewer with a big smile (4 s)."""
    n = 120
    c = Clip(n)
    c.life(seed=61, blinks=[58, 110], hands=False)
    s = "L"
    c.prop("gaze_x", [(0, 0), (12, 0), (14, 0.8), (38, 0.75), (41, -0.1), (44, 0.0), (n - 1, 0)])
    c.add("head.rz", [(0, 0), (6, -4), (14, -5), (24, 28), (28, 24), (38, 24), (44, -2), (48, 3), (54, 2),
                      (n - 18, 2), (n - 1, 0)])
    c.add("head.ry", [(0, 0), (20, 0), (30, 7), (42, 5), (48, -6), (56, -4), (n - 18, -4), (n - 1, 0)])
    c.add("head.rx", [(0, 0), (8, 3), (16, 4), (24, -3), (40, -1), (45, 3), (50, -2), (58, 0), (n - 1, 0)])
    c.add("chest.rz", [(0, 0), (8, -4), (14, -5), (26, 12), (44, 11), (60, 5), (n - 16, 5), (n - 1, 0)])
    c.add("spine.ry", [(0, 0), (12, 1), (26, -3), (n - 16, -3), (n - 1, 0)])
    # anticipation: the arm sweeps in across the belly, then flings out and up: "¡ta-da!"
    c.arm_raise(s, [(0, 0), (8, -6), (14, -4), (22, 46), (27, 38), (31, 41), (n - 22, 40), (n - 8, -4), (n - 1, 0)])
    c.arm_swing(s, [(0, 0), (6, 10), (14, 18), (22, 38), (27, 32), (n - 22, 32), (n - 8, 0)])
    c.elbow(s, [(0, 0), (8, 40), (14, 54), (22, 18), (28, 24), (n - 22, 24), (n - 8, 0)])
    c.forearm_in(s, [(0, 0), (8, 18), (14, 26), (22, 0), (n - 1, 0)])
    c.stretch(s, [(0, 1.0), (16, 1.0), (22, 1.08), (30, 1.05), (n - 22, 1.05), (n - 10, 1.0)])
    c.palm(s, [(0, 0), (12, 20), (24, -70), (n - 22, -66), (n - 8, 0)])   # palm turns up
    c.wrist(s, flex=[(0, 0), (12, 20), (22, -26), (28, -16), (n - 22, -16), (n - 8, 0)])
    c.hand(s, [(0, "relaxed"), (10, "soft"), (20, "spread"), (n - 22, "open"), (n - 8, "relaxed")])
    # the other hand rests on the belly, proud
    c.elbow("R", [(0, 0), (20, 0), (34, 42), (n - 22, 42), (n - 8, 0)])
    c.forearm_in("R", [(0, 0), (20, 0), (34, 24), (n - 22, 24), (n - 8, 0)])
    c.hand("R", [(0, "relaxed"), (30, "soft"), (n - 20, "soft"), (n - 6, "relaxed")])
    # the weight goes towards the side he presents, he leans in, then settles back for the double take
    c.weight([(0, 0), (10, -0.3), (16, -0.4), (26, 0.9), (32, 0.75), (44, 0.75), (54, 0.45), (n - 16, 0.45),
              (n - 1, 0)])
    c.add("spine.ry", [(0, 0), (24, 4), (44, 3), (54, 1), (n - 1, 0)])
    c.squash(22, 0.06, "head", dur=12)
    c.squash(44, 0.05, "head", dur=12)
    c.dip(44, depth=0.01, chest=1.5)
    c.expr([(0, "happy", 0.5), (14, "happy"), (24, "joy"), (40, "joy", 0.8), (46, "joy"), (n - 12, "happy"),
            (n - 1, "happy", 0.6)])
    c.prop("mouth_open", [(0, 0), (18, 0.0), (24, 0.35), (34, 0.1), (46, 0.45), (60, 0.1), (n - 1, 0)])
    c.prop("brow_L", [(0, 0), (12, 0.2), (22, 0.8), (40, 0.5), (46, 0.9), (70, 0.3), (n - 1, 0)])
    c.prop("brow_R", [(0, 0), (12, 0.2), (22, 0.7), (40, 0.4), (46, 0.85), (70, 0.3), (n - 1, 0)])
    c.prop("pupil", [(0, 0), (44, 0), (47, 0.5), (70, 0.2), (n - 1, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def nod_yes():
    """Two warm, bouncy nods with a smile: the chest and knees join in (1.7 s)."""
    n = 50
    c = Clip(n)
    c.life(seed=71, hands=False)
    c.hand("L", [(0, "relaxed")])
    c.hand("R", [(0, "relaxed")])
    c.add("head.rx", [(0, 0), (4, -5), (10, 13), (14, 9), (18, -1), (24, 12), (28, 8), (34, -2), (40, 1), (49, 0)])
    c.add("neck.rx", [(0, 0), (4, -2), (10, 4), (17, 0), (24, 4), (32, 0)])
    c.add("chest.rx", [(0, 0), (5, -2), (11, 4), (18, 0), (25, 3.5), (34, 0)])
    c.squash(10, -0.06, "head", dur=7)
    c.squash(24, -0.05, "head", dur=8)
    c.dip(9, depth=0.009, chest=1.0, dur=10)
    c.dip(23, depth=0.008, chest=1.0, dur=10)
    for s in ("L", "R"):
        c.shrug(s, C.pulse(n, 10, [(-4, 0), (1, 4), (6, 0)]) + C.pulse(n, 24, [(-4, 0), (1, 3.5), (6, 0)]))
    c.expr([(0, "happy", 0.6), (6, "joy", 0.7), (30, "happy"), (49, "happy", 0.8)])
    c.prop("squint", [(0, 0), (8, 0.45), (34, 0.35), (49, 0.15)])
    c.prop("blink_L", [(0, 0), (9, 0), (11, 0.7), (15, 0.0), (23, 0.0), (25, 0.6), (29, 0)])
    c.prop("blink_R", [(0, 0), (9, 0), (11, 0.7), (15, 0.0), (23, 0.0), (25, 0.6), (29, 0)])
    c.prop("brow_L", [(0, 0), (4, 0.5), (10, 0.2), (18, 0.4), (36, 0.2), (49, 0)])
    c.prop("brow_R", [(0, 0), (4, 0.5), (10, 0.2), (18, 0.4), (36, 0.2), (49, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def shake_no():
    """'No, no, no': a counter-turn, fast head shakes that decay, the body turning against them and
    a wagging index finger (1.8 s)."""
    n = 55
    c = Clip(n)
    c.life(seed=81, hands=False)
    turns = [(0, 0), (4, 3), (8, -17), (12, -13), (15, 15), (19, 11), (22, -12), (26, -8), (29, 7), (34, -2),
             (40, 0), (54, 0)]
    c.prop("gaze_x", [(0, 0), (3, 0), (5, -0.3), (12, 0.3), (19, -0.25), (26, 0.15), (32, 0)])
    c.add("head.rz", turns)
    c.add("head.rx", [(0, 0), (4, -2), (8, 3), (32, 3), (44, 0)])
    c.add("chest.rz", C.delay(C.keys(n, turns) * -0.18, 3))       # the body turns against the head
    c.add("hips.rz", C.delay(C.keys(n, turns) * 0.12, 4))
    # the finger wag: the right forearm comes up, index up, and wags against the head
    s = "R"
    c.elbow(s, [(0, 0), (6, 26), (12, 90), (16, 84), (40, 84), (50, 6), (54, 0)])
    c.arm_fwd(s, [(0, 0), (12, 32), (40, 32), (50, 0)])
    c.forearm_in(s, [(0, 0), (12, -6), (40, -6), (50, 0)])
    c.palm(s, [(0, 0), (12, 60), (40, 60), (50, 0)])
    c.arm_raise(s, [(0, 0), (12, 12), (40, 12), (50, 0)])
    c.hand(s, [(0, "relaxed"), (8, "fist"), (13, "point_pop"), (38, "point"), (48, "relaxed")])
    env = C.keys(n, [(0, 0), (13, 0), (16, 1), (34, 1), (40, 0), (54, 0)])
    wag = np.sin(2 * np.pi * (np.arange(n) - 13) / 7.0) * env
    c.forearm_lift(s, 10 * wag)
    c.wrist(s, side=C.delay(-16 * wag, 2))
    c.hand("L", [(0, "relaxed")])
    c.weight([(0, 0), (8, -0.5), (34, -0.45), (48, 0), (54, 0)])
    c.expr([(0, "neutral"), (6, "skeptical", 0.6), (40, "skeptical", 0.5), (54, "happy", 0.5)])
    c.prop("brow_in_L", [(0, 0), (6, -0.6), (36, -0.5), (54, 0)])
    c.prop("brow_in_R", [(0, 0), (6, -0.6), (36, -0.5), (54, 0)])
    c.prop("mouth_open", [(0, 0), (8, -0.7), (40, -0.6), (54, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def dance():
    """Happy little dance on the beat (120 bpm, 4 beats = 2 s, loops): pose-to-pose hits on the
    downbeats, arms trading places, a step-touch and a hop on the last beat."""
    n = 60
    c = Clip(n, loop=True)
    c.life(seed=91, breath=0.3, sway=0.3, hands=False)
    beat = 15
    # knees hit on every downbeat (fast in, slow out), the head squashes with them
    for b in range(4):
        t = b * beat
        if b == 3:
            continue                                         # beat 4 is the hop
        c.add("hips.lz", C.pulse(n, t, [(-3, 0.0), (2, -0.024), (7, -0.006), (12, 0.0)], loop=True))
        c.sy("head", 1.0 + C.pulse(n, t, [(-2, 0.0), (2, -0.07), (6, 0.05), (10, 0.0)], loop=True))
    # beat 4: a little hop (crouch, up, land on the loop's downbeat)
    c.add("root.lz", C.arc(n, 47, 58, 0.045))
    c.add("hips.lz", C.pulse(n, 45, [(-4, 0.0), (0, -0.026), (3, 0.0)], loop=True))
    c.sy("head", 1.0 + C.pulse(n, 46, [(-2, 0.0), (1, -0.05), (4, 0.08), (12, 0.0)], loop=True))
    for s in ("L", "R"):
        c.foot(s, z=C.arc(n, 48, 57, 0.02), pitch=C.pulse(n, 47, [(-2, 0), (1, 18), (9, -4), (12, 0)], loop=True))
    c.add("hips.lz", -0.008)
    # weight side to side per beat (step-touch), pelvis twist
    w = C.keys(n, [(0, 1.0), (4, 0.8), (15, -1.0), (19, -0.8), (30, 1.0), (34, 0.8), (45, 0.0), (50, 0.15)],
               loop=True)
    c.weight(0.8 * w, heel=12.0)
    c.foot("R", z=0.022 * np.clip(C.delay(w, 2, loop=True), 0, 1) ** 2)
    c.foot("L", z=0.022 * np.clip(-C.delay(w, 2, loop=True), 0, 1) ** 2)
    c.add("hips.rz", 8.0 * C.delay(w, 1, loop=True))
    c.add("chest.rz", -7.0 * C.delay(w, 3, loop=True))
    c.add("head.ry", 6.0 * C.delay(w, 4, loop=True))
    c.add("head.rx", C.delay(C.sine(n, beat, 3.5, phase=0.25), 2, loop=True))
    # arms: beat 1 right arm up-out pointing, left fist on the hip; beat 2 swap; beat 3 both pump
    # forward; beat 4 both fling out on the hop
    up = {"R": [(0, 44), (4, 40), (15, 10), (30, 18), (34, 14), (45, 36), (50, 42), (59, 44)],
          "L": [(0, 10), (15, 44), (19, 40), (30, 18), (34, 14), (45, 36), (50, 42), (59, 10)]}
    lift = {"R": [(0, 46), (15, 0), (30, 10), (45, 34), (59, 46)], "L": [(0, 0), (15, 46), (30, 10), (45, 34), (59, 0)]}
    elb = {"R": [(0, 10), (15, 80), (30, 70), (36, 90), (45, 20), (59, 10)],
           "L": [(0, 80), (15, 10), (30, 70), (36, 90), (45, 20), (59, 80)]}
    fwd = {"R": [(0, 6), (15, -8), (30, 30), (36, 10), (45, 6), (59, 6)],
           "L": [(0, -8), (15, 6), (30, 30), (36, 10), (45, 6), (59, -8)]}
    for s in ("L", "R"):
        c.arm_raise(s, C.ease(n, up[s], loop=True))
        c.forearm_lift(s, C.ease(n, lift[s], loop=True))
        c.elbow(s, C.ease(n, elb[s], loop=True))
        c.arm_fwd(s, C.ease(n, fwd[s], loop=True))
        c.wrist(s, side=C.delay(C.sine(n, beat, 10.0), 3, loop=True))
    c.hand("R", [(0, "point"), (12, "point"), (15, "fist"), (28, "fist"), (30, "fist"), (44, "fist"), (46, "spread"),
                 (57, "spread"), (59, "point")])
    c.hand("L", [(0, "fist"), (13, "fist"), (15, "point"), (28, "point"), (30, "fist"), (44, "fist"), (46, "spread"),
                 (57, "spread"), (59, "fist")])
    c.palm("R", [(0, 30), (15, 0), (45, 60), (59, 30)])
    c.palm("L", [(0, 0), (15, 30), (45, 60), (59, 0)])
    c.expr([(0, "joy")], scale=0.9)
    c.prop("mouth_open", C.sine(n, 2 * beat, 0.25, phase=0.1) + 0.1)
    c.prop("squint", C.sine(n, beat, 0.1) + 0.1)
    c.prop("brow_L", C.sine(n, beat, 0.25) + 0.2)
    c.prop("brow_R", C.sine(n, beat, 0.25, phase=0.1) + 0.2)
    c.secondary()
    return c


SOCIAL = {
    "Talk": talk,
    "Present": present,
    "Nod_Yes": nod_yes,
    "Shake_No": shake_no,
    "Dance": dance,
}
