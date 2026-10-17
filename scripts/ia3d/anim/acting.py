"""Full-body acting: the body under the gestures, so Morfi never stands like a statue.

A gesture is two parts moving; a person moves everything: the weight goes from one foot to the
other on every phrase, the knees give on the stressed words, the chest leans in when he explains,
the head tilts into the gesture, a jump has a crouch before it and a squash after it. These helpers
write that layer onto a Performance (channels add up with the gestures):

    a = Acting(p)
    a.stance(knees=0.008, lean=2.5)            # soft knees, a little towards the camera
    a.talk(lines)                              # weight shifts per phrase + bounces on stresses
    a.shift(t, +1)                             # weight onto his left foot at t (s)
    a.bounce(t, depth=0.012)
    a.hop(t, height=0.05)                      # crouch, take-off stretch, air, landing squash
    a.step("R", t, dy=-0.05)                   # a real step: the foot lifts, travels, lands
    a.squash(t, -0.06, bone="head")            # cartoon squash (-) / stretch (+) with settle
    a.shimmy(t0, t1)                           # happy hip wiggle
    a.beat("R", t)                             # a small arm beat on a word (FK arm only)

Signs follow rigmap.py: Morfi faces -Y, his left is +X, +rx leans forward, +ry tilts to his left,
+rz turns to his left.
"""
import re

import numpy as np

from . import curves as C


def _pulse(n, f0, pts):
    """Keys relative to frame f0 (offsets in frames) -> full curve."""
    keyed = {}
    for df, v in [(-10 ** 6, 0.0)] + pts + [(10 ** 6, 0.0)]:
        keyed[f0 + df] = v                        # two keys on one frame: the later one wins
    return C.keys(n, sorted(keyed.items()))


class Acting:
    def __init__(self, p):
        self.p, self.c, self.n, self.fps = p, p.c, p.n, p.fps
        self.shifts = []                        # weight shifts: -1 his right foot .. +1 his left foot
        self.busy = []                          # (f0, f1) windows owned by hops / steps

    def f(self, t):
        return int(round(t * self.fps))

    def _sy(self, bone, delta):
        key = f"{bone}.sy"
        if key not in self.c.ch:
            self.c.ch[key] = np.ones(self.n)
        self.c.ch[key] = self.c.ch[key] + delta

    def _free(self, f):
        return not any(a - 4 <= f <= b + 4 for a, b in self.busy)

    # ------------------------------------------------------------ stance and weight
    def stance(self, knees=0.008, lean=2.5):
        """Soft knees (so every bounce can go both ways) and a slight lean towards the viewer."""
        self.c.add("hips.lz", np.full(self.n, -knees))
        self.c.add("spine.rx", np.full(self.n, lean * 0.4))
        self.c.add("chest.rx", np.full(self.n, lean * 0.6))

    def shift(self, t, side, dur=0.45, amount=1.0):
        """Weight towards a foot from t on (side +1 his left, -1 his right, 0 centred): eased,
        with a small overshoot; it stays there until the next shift (applied in time order)."""
        self.shifts.append((t, side, dur, amount))

    def _weight_curve(self):
        seg = np.arange(self.n)
        w = np.zeros(self.n)
        for t, side, dur, amount in sorted(self.shifts):
            f0, f1 = self.f(t), self.f(t + dur)
            w0 = w[max(0, f0 - 1)]
            target = side * amount
            span = max(1, f1 - f0)
            u = np.clip((seg - f0) / span, 0, 1)
            u = u * u * (3 - 2 * u)
            over = 0.12 * np.sin(np.pi * np.clip((seg - f0) / (span * 1.6), 0, 1)) * (target - w0)
            w = np.where(seg >= f0, w0 + (target - w0) * u + over, w)
        return w

    def _apply_weight(self):
        w = C.spring(self._weight_curve(), freq=1.6, damping=0.75, fps=self.fps)
        c = self.c
        c.add("hips.lx", 0.018 * w)
        c.add("hips.ry", 4.0 * w)
        c.add("hips.rz", 2.5 * w)
        c.add("spine.ry", -2.4 * w)
        c.add("chest.ry", -1.6 * w)
        c.add("neck.ry", -0.8 * w)
        c.add("head.ry", 1.5 * w)                    # the head tilts with the weight: relaxed
        for s, sg in (("L", 1.0), ("R", -1.0)):      # the free leg's heel comes off the floor
            free = np.clip(-sg * w, 0, 1)
            c.foot(s, pitch=7.0 * free)

    # ------------------------------------------------------------ rhythm
    def bounce(self, t, depth=0.010, chest=2.5):
        """Knees give and rebound on a word; the chest pulses forward with it."""
        f0 = self.f(t)
        if not self._free(f0):
            return
        n = self.n
        self.c.add("hips.lz", _pulse(n, f0, [(-2, 0.0), (3, -depth), (8, 0.35 * depth), (13, 0.0)]))
        self.c.add("chest.rx", _pulse(n, f0, [(-2, 0.0), (3, chest), (10, -0.3 * chest), (16, 0.0)]))
        self.c.add("head.rx", _pulse(n, f0, [(0, 0.0), (5, 1.5 * chest), (12, -0.4 * chest), (18, 0.0)]))

    def talk(self, lines, energy=1.0, skip=()):
        """While he talks: the weight changes foot on every phrase, the knees and chest beat on
        the stressed words, the torso turns a little into each phrase."""
        side = 1
        for ln in lines:
            words = ln["words"]
            starts = [words[0]["start"]]
            for a, b in zip(words, words[1:]):
                if b["start"] - a["end"] > 0.16 or re.search(r"[,:;.!?]$", a["w"]):
                    starts.append(b["start"])
            for t in starts:
                if any(s0 <= t <= s1 for s0, s1 in skip):
                    continue
                self.shift(t - 0.12, side, amount=0.75 + 0.25 * energy)
                self.c.add("chest.rz", _pulse(self.n, self.f(t), [(-4, 0.0), (6, 3.0 * side * energy),
                                                                   (40, 2.0 * side * energy), (70, 0.0)]))
                side = -side
            for s in ln.get("stress", []):
                t = ln["start"] + s
                if any(s0 <= t <= s1 for s0, s1 in skip):
                    continue
                self.bounce(t - 0.04, depth=0.008 * energy, chest=2.2 * energy)

    # ------------------------------------------------------------ big moves
    def squash(self, t, amount, bone="head", dur=0.45):
        """Cartoon squash (amount < 0) or stretch (> 0) that settles with one wobble."""
        f0 = self.f(t)
        k = max(2, int(dur * self.fps))
        self._sy(bone, _pulse(self.n, f0, [(-3, 0.0), (2, amount), (int(k * 0.45), -0.45 * amount),
                                           (int(k * 0.75), 0.15 * amount), (k, 0.0)]))

    def hop(self, t, height=0.05, crouch=0.025, air=0.30, arms=True):
        """t = take-off. Crouch (anticipation), stretch on the way up, hang, squash on landing."""
        f0 = self.f(t)
        fa = self.f(air)
        n = self.n
        self.busy.append((f0 - 10, f0 + fa + 12))
        self.c.add("hips.lz", _pulse(n, f0, [(-10, 0.0), (-3, -crouch), (0, -crouch * 0.6), (3, 0.0),
                                             (fa + 1, 0.0), (fa + 4, -crouch * 0.8), (fa + 10, 0.004), (fa + 14, 0.0)]))
        self.c.add("root.lz", _pulse(n, f0, [(0, 0.0), (int(fa * 0.45), height), (int(fa * 0.6), height * 1.02),
                                             (fa, 0.0)]))
        self.c.add("spine.rx", _pulse(n, f0, [(-10, 0.0), (-3, 7.0), (2, -3.0), (fa, -1.0), (fa + 4, 6.0),
                                              (fa + 12, 0.0)]))
        for s in ("L", "R"):
            self.c.foot(s, z=_pulse(n, f0, [(0, 0.0), (3, height * 0.35), (int(fa * 0.5), height * 0.45),
                                            (fa, 0.0)]),
                        pitch=_pulse(n, f0, [(-8, 0.0), (-2, 14.0), (3, 6.0), (fa - 3, -4.0), (fa, 0.0)]))
        self.squash(t - 0.08, -0.05, "head", dur=0.25)
        self.squash(t + 0.03, 0.07, "head", dur=0.3)
        self.squash(t + air, -0.08, "head", dur=0.5)
        self.squash(t + air, -0.05, "spine", dur=0.4)
        if arms:                                       # arms swing up with the jump (FK arms)
            for s in ("L", "R"):
                self.c.arm_raise(s, _pulse(n, f0, [(-8, 0.0), (-3, -6.0), (4, 22.0), (fa, 12.0), (fa + 8, 0.0)]))

    def step(self, side, t, dx=0.0, dy=-0.04, dur=0.38, height=0.03, settle=True):
        """A real step: the foot peels off, travels on an arc and lands (heel first); the hips
        follow halfway so the weight ends between the feet. Offsets stay until another step."""
        f0, f1 = self.f(t), self.f(t + dur)
        n = self.n
        self.busy.append((f0, f1))
        frames = np.arange(n)
        u = np.clip((frames - f0) / max(1, f1 - f0), 0, 1)
        e = u * u * (3 - 2 * u)
        sg = 1.0 if side == "L" else -1.0
        self.c.foot(side, x=dx * e, y=dy * e, z=height * np.sin(np.pi * u) * (u < 1),
                    pitch=_pulse(n, f0, [(0, 0.0), (2, 10.0), (int((f1 - f0) * 0.6), -8.0), (f1 - f0, -10.0),
                                         (f1 - f0 + 4, 0.0)]))
        self.c.add("hips.lx", (dx * 0.5) * e)
        self.c.add("hips.ly", (dy * 0.5) * e)
        self.shift(t - 0.15, -sg, dur=0.25, amount=0.8)            # weight off the stepping foot first
        if settle:
            self.shift(t + dur, 0, dur=0.35)
            self.bounce(t + dur - 0.02, depth=0.007, chest=1.5)

    def shimmy(self, t0, t1, freq=3.2, amp=1.0):
        """Happy wiggle: hips side to side, shoulders against them, head bobbing."""
        f0, f1 = self.f(t0), self.f(t1)
        frames = np.arange(self.n)
        env = np.clip(np.minimum((frames - f0) / 6, (f1 - frames) / 6), 0, 1)
        s = np.sin(2 * np.pi * freq * (frames - f0) / self.fps) * env * amp
        self.c.add("hips.lx", 0.012 * s)
        self.c.add("hips.ry", 5.0 * s)
        self.c.add("chest.ry", -6.0 * s)
        self.c.add("head.ry", 3.0 * np.roll(s, 2))
        for side, sg in (("L", 1), ("R", -1)):
            self.c.shrug(side, 4.0 * np.clip(sg * s, 0, 1))

    def beat(self, side, t, amp=1.0):
        """A small 'hand beat' on a word with a free (FK) arm: forearm lifts, palm opens, settles."""
        f0 = self.f(t)
        n = self.n
        self.c.elbow(side, _pulse(n, f0, [(-4, 0.0), (3, 18.0 * amp), (9, 10.0 * amp), (18, 0.0)]))
        self.c.forearm_lift(side, _pulse(n, f0, [(-4, 0.0), (3, 10.0 * amp), (12, 0.0)]))
        self.c.palm(side, _pulse(n, f0, [(-2, 0.0), (4, -25.0 * amp), (16, 0.0)]))

    def finish(self):
        """Write the accumulated weight layer (call once, after every shift)."""
        self._apply_weight()
