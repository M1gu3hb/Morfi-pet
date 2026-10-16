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
    """Explaining something to the viewer: speech, beat gestures, nods, brows (6 s)."""
    n = 180
    c = Clip(n)
    c.life(seed=51, blinks=[47, 118, 166])
    mouth, rnd, starts, stress = _speech(n, 6, n - 10, seed=7)
    c.prop("mouth_open", mouth)
    c.prop("mouth_round", rnd)
    c.prop("smile", 0.45)
    # hands come up into the gesture space and stay there, palms half up
    for s, lag in (("R", 0), ("L", 4)):
        c.elbow(s, [(0, 0), (8 + lag, 0), (20 + lag, 52), (n - 22, 52), (n - 8, 0), (n - 1, 0)])
        c.forearm_in(s, [(0, 0), (12, 0), (24, 14), (n - 22, 14), (n - 8, 0)])
        c.arm_fwd(s, [(0, 0), (10, 0), (22, 12), (n - 22, 12), (n - 8, 0)])
        c.arm_raise(s, [(0, 0), (12, 0), (24, 6), (n - 22, 6), (n - 8, 0)])
        c.palm(s, [(0, 0), (14, 0), (26, 35), (n - 22, 35), (n - 8, 0)])
        c.curl(s, [(0, 0), (14, 0), (24, -8), (n - 22, -8), (n - 8, 0)])
    # beats: on stressed syllables a hand dips and rises (alternating), the head nods
    beat_r, beat_l, nod = np.zeros(n), np.zeros(n), np.zeros(n)
    f = np.arange(n)
    for k, t0 in enumerate(stress):
        if t0 < 24 or t0 > n - 26:
            continue
        pulse = np.exp(-((f - t0 - 3) / 3.5) ** 2) - 0.45 * np.exp(-((f - t0 - 9) / 4.0) ** 2)
        (beat_r if k % 2 == 0 else beat_l)[:] += pulse
        nod += pulse * (1.0 if k % 3 else 1.6)
    c.elbow("R", beat_r * 9.0)
    c.elbow("L", beat_l * 9.0)
    c.wrist("R", flex=C.delay(beat_r * 7.0, 2))
    c.wrist("L", flex=C.delay(beat_l * 7.0, 2))
    c.add("head.rx", C.delay(nod * 3.2, 1))
    # each phrase gets its own head attitude and a brow lift at its start
    tilt_pts, turn_pts, brow_pts = [(0, 0)], [(0, 0)], [(0, 0)]
    rng = np.random.default_rng(3)
    for t0 in starts:
        tilt_pts.append((t0 + 6, rng.uniform(-5, 5)))
        turn_pts.append((t0 + 8, rng.uniform(-6, 6)))
        brow_pts += [(t0, 0.1), (t0 + 5, rng.uniform(0.35, 0.7)), (t0 + 22, 0.15)]
    tilt_pts.append((n - 1, 0))
    turn_pts.append((n - 1, 0))
    brow_pts.append((n - 1, 0))
    c.add("head.ry", tilt_pts)
    c.add("head.rz", turn_pts)
    c.add("chest.rz", C.delay(C.keys(n, turn_pts) * 0.35, 4))
    c.prop("brow_L", brow_pts)
    c.prop("brow_R", [(t, v * 0.9) for t, v in brow_pts])
    # a glance up while "thinking" in a pause, then back to the viewer
    c.prop("gaze_x", [(0, 0), (80, 0), (83, 0.25), (96, 0.25), (99, 0), (n - 1, 0)])
    c.prop("gaze_y", [(0, 0), (80, 0), (83, 0.35), (96, 0.35), (99, 0), (n - 1, 0)])
    c.add("hips.lx", C.sine(n, n, 0.004))
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def present():
    """'Mira esto': opens the left arm towards something beside him, looks at it, then
    back at the viewer with a smile (4 s)."""
    n = 120
    c = Clip(n)
    c.life(seed=61, blinks=[58, 110])
    s = "L"
    c.prop("gaze_x", [(0, 0), (6, 0), (9, 0.7), (40, 0.7), (43, 0.0), (n - 1, 0)])
    c.add("head.rz", [(0, 0), (8, 0), (20, 24), (40, 22), (52, 4), (n - 18, 4), (n - 1, 0)])
    c.add("head.ry", [(0, 0), (20, 0), (30, 5), (52, -3), (n - 18, -3), (n - 1, 0)])
    c.add("head.rx", [(0, 0), (10, 2), (20, -2), (44, 0), (50, 3), (58, -1), (n - 1, 0)])
    c.add("chest.rz", [(0, 0), (10, 0), (24, 9), (44, 9), (60, 4), (n - 16, 4), (n - 1, 0)])
    c.add("spine.ry", [(0, 0), (12, 0), (26, -2), (n - 16, -2), (n - 1, 0)])
    c.arm_raise(s, [(0, 0), (8, -3), (22, 40), (28, 36), (n - 22, 36), (n - 8, 0), (n - 1, 0)])
    c.arm_swing(s, [(0, 0), (10, 0), (22, 34), (n - 22, 34), (n - 8, 0)])
    c.elbow(s, [(0, 0), (12, 0), (22, 26), (28, 18), (n - 22, 18), (n - 8, 0)])
    c.palm(s, [(0, 0), (12, 0), (24, -55), (n - 22, -55), (n - 8, 0)])   # palm turns up
    c.wrist(s, flex=[(0, 0), (16, 0), (26, -14), (n - 22, -14), (n - 8, 0)])
    c.curl(s, [(0, 0), (16, 0), (24, -14), (n - 22, -14), (n - 8, 0)])
    # the other hand rests on the belly
    c.elbow("R", [(0, 0), (20, 0), (34, 38), (n - 22, 38), (n - 8, 0)])
    c.forearm_in("R", [(0, 0), (20, 0), (34, 22), (n - 22, 22), (n - 8, 0)])
    c.prop("smile", [(0, 0.4), (20, 0.6), (48, 1.0), (n - 12, 0.9), (n - 1, 0.45)])
    c.prop("mouth_open", [(0, 0), (20, 0.2), (46, 0.5), (60, 0.1), (n - 1, 0)])
    c.prop("brow_L", [(0, 0), (16, 0.6), (40, 0.4), (54, 0.7), (70, 0.2), (n - 1, 0)])
    c.prop("brow_R", [(0, 0), (16, 0.5), (40, 0.3), (54, 0.6), (70, 0.2), (n - 1, 0)])
    c.prop("squint", [(0, 0), (46, 0), (56, 0.35), (n - 14, 0.3), (n - 1, 0)])
    c.add("hips.lx", [(0, 0), (20, -0.006), (n - 16, -0.006), (n - 1, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def nod_yes():
    """Two warm nods with a smile (1.5 s)."""
    n = 45
    c = Clip(n)
    c.life(seed=71)
    c.add("head.rx", [(0, 0), (4, -2), (10, 9), (16, 1), (22, 8), (29, 0), (36, -1), (44, 0)])
    c.add("neck.rx", [(0, 0), (10, 3), (16, 0), (22, 3), (30, 0)])
    c.prop("squint", [(0, 0), (8, 0.35), (34, 0.3), (44, 0.1)])
    c.prop("smile", [(0, 0.4), (8, 0.9), (44, 0.7)])
    c.prop("brow_L", [(0, 0), (6, 0.3), (36, 0.2), (44, 0)])
    c.prop("brow_R", [(0, 0), (6, 0.3), (36, 0.2), (44, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def shake_no():
    """Gentle 'no': head shakes twice, brows knit a little (1.7 s)."""
    n = 50
    c = Clip(n)
    c.life(seed=81)
    turns = [(0, 0), (6, -13), (14, 12), (22, -10), (30, 6), (37, -1), (44, 0)]
    c.prop("gaze_x", [(0, 0), (4, 0), (6, -0.25), (14, 0.25), (22, -0.2), (30, 0.1), (36, 0)])
    c.add("head.rz", turns)
    c.add("head.rx", [(0, 0), (6, 2), (30, 2), (44, 0)])
    c.add("chest.rz", C.delay(C.keys(n, turns) * 0.15, 3))
    c.prop("brow_L", [(0, 0), (6, -0.35), (34, -0.3), (49, 0)])
    c.prop("brow_R", [(0, 0), (6, -0.35), (34, -0.3), (49, 0)])
    c.prop("smile", [(0, 0.35), (8, 0.1), (40, 0.15), (49, 0.35)])
    c.prop("mouth_open", [(0, 0), (8, -0.6), (40, -0.5), (49, 0)])
    c.add("hips.lz", -0.004)
    c.secondary()
    return c


def dance():
    """Happy little dance on the beat (120 bpm, 4 beats = 2 s, loops)."""
    n = 60
    c = Clip(n, loop=True)
    c.life(seed=91, breath=0.3, sway=0.3)
    beat = 15
    f = np.arange(n)
    ph = (f % beat) / beat
    bounce = -0.014 * np.exp(-((ph - 0.05) / 0.16) ** 2) - 0.014 * np.exp(-((ph - 1.05) / 0.16) ** 2)
    c.add("hips.lz", bounce - 0.006)
    c.add("hips.lx", C.sine(n, 2 * beat, 0.016))
    c.add("hips.rz", C.sine(n, 2 * beat, 7.0, phase=0.1))
    c.add("spine.ry", C.sine(n, 2 * beat, -3.0, phase=0.05))
    c.add("chest.rz", C.sine(n, 2 * beat, -6.0, phase=0.2))
    c.add("head.ry", C.delay(C.sine(n, 2 * beat, 5.0), 3, loop=True))
    c.add("head.rx", C.delay(C.sine(n, beat, 3.0, phase=0.25), 2, loop=True))
    for s, phs in (("L", 0.0), ("R", 0.5)):
        c.elbow(s, 56)
        c.arm_raise(s, 14 + C.sine(n, 2 * beat, 8, phase=phs))
        c.arm_fwd(s, C.sine(n, 2 * beat, 12, phase=phs) - 4)
        c.forearm_lift(s, C.delay(C.sine(n, 2 * beat, 10, phase=phs + 0.25), 2, loop=True))
        c.curl(s, 25)
        c.foot(s, z=np.maximum(0, C.sine(n, 2 * beat, 0.018, phase=phs + 0.25)))
    c.prop("smile", 1.0)
    c.prop("squint", 0.45)
    c.prop("mouth_open", C.sine(n, 2 * beat, 0.3, phase=0.1) + 0.2)
    c.prop("brow_L", C.sine(n, beat, 0.25) + 0.3)
    c.prop("brow_R", C.sine(n, beat, 0.25) + 0.3)
    c.secondary()
    return c


SOCIAL = {
    "Talk": talk,
    "Present": present,
    "Nod_Yes": nod_yes,
    "Shake_No": shake_no,
    "Dance": dance,
}
