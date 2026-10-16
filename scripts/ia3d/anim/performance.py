"""A long performance for videos: Morfi talks (lip-sync from the real voice) and gestures on cue.

The single actions (`actions*.py`) are 2-7 s clips that start and end at rest. A video needs one
long, continuous take: the always-on life layer for the whole length, the mouth driven by the
voice, and gestures dropped in at the frame of the word they belong to.

    p = Performance(n_frames)
    p.speak(lines)                          # lip-sync + speech body language from the voiceover
    p.c.arm_raise("R", [(f0, 0), ...])      # FK gestures: additive channel keys that start and end at 0
    p.hand("R", [(f, "point"), ...])        # hand shapes: one key list per hand (never summed)
    p.reach("R", [(f, point | None, w)])    # IK wrist targets (prop space), one list per hand
    p.orient("R", [(f, fingers, palm)])     # IK hand orientation (world directions)
    p.look([(f, point | None)])             # head + eyes towards points
    p.expr([(f, "happy"), ...])             # facial expression keys (one list)
    p.show("prop_tablet", [(f, 0), ...])    # props
    p.contacts / p.supports                 # as in anim/contacts.py, in performance frames
    clip = p.build()                        # a Clip ready for rigmap.bake + contacts.solve

Every per-hand / per-face list is applied ONCE at build time: Clip channels add up, so two calls
on the same channel would sum (a hand shape would curl twice as much).

Lines (from the ElevenLabs alignment, placed on the video timeline, see the video's timing.json):
    {"start": s, "chars": [...], "t0": [...], "t1": [...], "env": [rms per frame], "question": bool,
     "stress": [word start seconds from the line start, ...]}
"""
import numpy as np

from . import curves as C
from .clip import FPS, Clip
from .motor import WRIST_REST, orient_keys, prop_space

# mouth shapes per letter: (open 0..1, round 0..1, smile -1..1)
VOWEL = {"a": (1.0, 0.0, 0.10), "á": (1.0, 0.0, 0.10), "e": (0.70, 0.0, 0.20), "é": (0.75, 0.0, 0.20),
         "i": (0.42, 0.0, 0.32), "í": (0.48, 0.0, 0.32), "o": (0.78, 0.62, 0.0), "ó": (0.82, 0.62, 0.0),
         "u": (0.50, 0.88, 0.0), "ú": (0.55, 0.88, 0.0), "y": (0.40, 0.0, 0.25)}
CLOSED = set("mbp")                      # lips meet
NARROW = set("fv")                       # lip to teeth
TALK_BASE = -0.30                        # mouth between syllables while talking (relative)


class Performance:
    def __init__(self, n, fps=FPS, seed=7, prop_loc=(0, 0, 0), prop_rot=(0, 0, 0)):
        self.n, self.fps, self.seed = n, fps, seed
        self.c = Clip(n, fps=fps)
        self.hands = {"L": [], "R": []}
        self.reaches = {"L": [], "R": []}
        self.orients = {"L": [], "R": []}
        self.looks = []
        self.exprs = []
        self.shows = {}
        self.contacts, self.supports = [], []
        self.blinks = []
        self.prop_loc, self.prop_rot = tuple(prop_loc), tuple(prop_rot)

    # ------------------------------------------------------------ helpers
    def f(self, seconds):
        return int(round(seconds * self.fps))

    def hand(self, side, keys):
        self.hands[side] += list(keys)

    def reach(self, side, keys):
        """keys: [(frame, world point or None, weight)]: points are converted to prop space. None
        means "where the arm hangs" (weight 0), so switching IK on or off never swings the target
        across from a far place."""
        hang = WRIST_REST[side] + np.array([0.0, -0.02, 0.0])
        for k in keys:
            f, p = k[0], k[1]
            w = k[2] if len(k) > 2 else (1.0 if p is not None else 0.0)
            q = prop_space(hang if p is None else p, self.prop_loc, self.prop_rot)
            self.reaches[side].append((f, q, w))

    def orient(self, side, keys):
        self.orients[side] += list(keys)

    def look(self, keys):
        self.looks += list(keys)

    def expr(self, keys):
        self.exprs += list(keys)

    def show(self, bone, keys):
        self.shows.setdefault(bone, []).extend(keys)

    # ------------------------------------------------------------ speech
    def speak(self, lines, lead=0.05):
        """Mouth from the voice: letters give the shape, the audio envelope gives how much.
        Plus what people do while talking: small nods on stressed words, brows that lift on
        questions and emphasis, blinks at the pauses."""
        n, fps = self.n, self.fps
        t = np.arange(n) / fps
        open_, round_, smile = np.zeros(n), np.zeros(n), np.zeros(n)
        talking = np.zeros(n)
        gain = np.ones(n)
        for ln in lines:
            st = ln["start"]
            for ch, t0, t1 in zip(ln["chars"], ln["t0"], ln["t1"]):
                c = ch.lower()
                a, b = st + t0 - lead, st + t1 - lead
                m = (t >= a) & (t < max(b, a + 1.0 / fps))
                if c in VOWEL:
                    o, r, s = VOWEL[c]
                    open_[m] = np.maximum(open_[m], o)
                    round_[m] = np.maximum(round_[m], r)
                    smile[m] = s
                elif c in CLOSED:
                    open_[m] = np.minimum(open_[m], -0.35)
                elif c in NARROW:
                    open_[m] = np.minimum(open_[m], 0.12)
            a = self.f(st + ln["t0"][0] - lead)
            b = self.f(st + ln["t1"][-1])
            talking[max(0, a):min(n, b + 1)] = 1.0
            env = np.nan_to_num(np.asarray(ln.get("env") or [], float))
            f0 = self.f(st - lead)
            k = np.arange(len(env)) + f0
            ok = (k >= 0) & (k < n)
            gain[k[ok]] = np.clip(0.45 + 0.75 * env[ok], 0.35, 1.25)
        target = np.where(talking > 0, TALK_BASE + 1.15 * np.clip(open_ * gain, -0.5, 1.0), 0.0)
        mouth = C.spring(target, freq=9.0, damping=0.62, fps=fps)         # a springy jaw, never snaps
        self.c.prop("mouth_open", mouth)
        self.c.prop("mouth_round", np.clip(C.spring(round_, freq=8.0, damping=0.7, fps=fps), 0, 1))
        self.c.prop("smile", 0.25 * C.spring(smile, freq=6.0, damping=0.8, fps=fps))
        # body language while talking
        rng = np.random.default_rng(self.seed)
        nod, brow = np.zeros(n), np.zeros(n)
        for ln in lines:
            for ws in ln.get("stress", []):
                f0 = self.f(ln["start"] + ws)
                if 0 <= f0 < n:
                    nod[f0] += rng.uniform(1.6, 2.8)
                    brow[f0] += rng.uniform(0.25, 0.45)
            if ln.get("question"):
                a = self.f(ln["start"])
                b = self.f(ln["start"] + ln["t1"][-1])
                brow[a:b] += 0.03
            end = self.f(ln["start"] + ln["t1"][-1]) + 3          # a blink in the pause after a line
            if end < n:
                self.blinks.append(end)
        self.c.add("head.rx", C.spring(nod, freq=4.0, damping=0.45, fps=fps) * 2.2)
        side = np.repeat(rng.choice([-1.0, 1.0], n // 20 + 1), 20)[:n]
        self.c.add("head.rz", C.spring(np.roll(nod, 3) * side, freq=3.0, damping=0.5, fps=fps))
        br = np.clip(C.spring(brow, freq=4.5, damping=0.55, fps=fps) * 2.4, -0.2, 0.8)
        self.c.prop("brow_L", br)
        self.c.prop("brow_R", br * 0.9)

    # ------------------------------------------------------------ build
    def build(self, life=True, sway=1.0):
        c = self.c
        if life:
            extra = list(range(int(self.fps * 2.4), self.n, int(self.fps * 3.3)))
            blinks = sorted(set(self.blinks + [b for b in extra if all(abs(b - x) > 30 for x in self.blinks)]))
            c.life(seed=self.seed, blinks=blinks, hands=False, sway=sway)
        if any(abs(v) > 1e-9 for v in self.prop_loc + self.prop_rot):
            c.place_prop(loc=[(0, self.prop_loc), (self.n - 1, self.prop_loc)],
                         rot=[(0, self.prop_rot), (self.n - 1, self.prop_rot)])
        for side in ("L", "R"):
            if self.reaches[side]:
                c.reach(side, sorted(self.reaches[side], key=lambda k: k[0]))
            if self.orients[side]:
                rx, ry, rz = orient_keys(side, sorted(self.orients[side], key=lambda k: k[0]), prop_rot=self.prop_rot)
                c.reach_rot(side, rx, ry, rz)
            if self.hands[side]:
                c.hand(side, sorted(self.hands[side], key=lambda k: k[0]))
        if self.looks:
            c.look_at(sorted(self.looks, key=lambda k: k[0]), head=0.45, neck=0.12, max_nod=6.0)
        if self.exprs:
            c.expr(sorted(self.exprs, key=lambda k: k[0]))
        for bone, keys in self.shows.items():
            c.show(bone, sorted(keys, key=lambda k: k[0]))
        c.contacts, c.supports = self.contacts, self.supports
        c.secondary()
        return c


__all__ = ["Performance"]
