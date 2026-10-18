"""Morfi's motor: hand shapes, facial expressions and the reach / prop helpers.

Everything here writes Clip channels, so it layers with the rest of an action:

    c.hand("R", [(0, "relaxed"), (12, "point"), (40, "count2")])
    c.expr([(0, "neutral"), (10, "surprised"), (30, "joy")])
    c.reach("L", [(0, None), (10, (0.12, -0.24, 0.40)), (60, (0.12, -0.24, 0.40)), (70, None)])
    c.show("prop_tablet", [(0, 0), (8, 1)])

Hands have a thumb and three fingers (index, middle, ring), 3 phalanges each.
Finger values are degrees: + curls into the palm, - extends past straight.
"""
import numpy as np

from . import curves as C

FINGER_NAMES = ("index", "middle", "ring")

# per finger (base, middle, tip) curl; "fan" spreads the fingers apart (deg);
# thumb = (curl seg 1, 2, 3) and "thumb_out" swings it away from the palm (deg)
HAND_SHAPES = {
    "rest": {"index": (0, 0, 0), "middle": (0, 0, 0), "ring": (0, 0, 0), "thumb": (0, 0, 0)},
    # a hand at rest: the rest pose is already a soft curl, so "relaxed" opens it a little with a gradient
    # (index least, ring most), gaps between the fingers and the thumb beside the index, not folded over
    "relaxed": {"index": (-6, -6, -4), "middle": (4, 6, 4), "ring": (14, 16, 10), "thumb": (6, 12, 8),
                "fan": 15, "thumb_out": -20},
    "fist": {"index": (68, 78, 62), "middle": (68, 78, 62), "ring": (68, 78, 62), "thumb": (18, 38, 36)},
    "open": {"index": (-16, -18, -12), "middle": (-16, -18, -12), "ring": (-16, -18, -12), "thumb": (-24, -14, -6),
             "fan": 9, "thumb_out": 12},
    "stop": {"index": (-20, -20, -14), "middle": (-20, -20, -14), "ring": (-20, -20, -14), "thumb": (-14, -8, -4),
             "fan": 3},
    "point": {"index": (-22, -22, -16), "middle": (66, 78, 62), "ring": (66, 78, 62), "thumb": (20, 40, 34)},
    # poke: index nearly straight, the others tucked tight so they stay clear of the surface
    "tap": {"index": (-4, 4, 6), "middle": (78, 94, 72), "ring": (80, 96, 74), "thumb": (12, 30, 28),
            "thumb_out": -8},                                  # thumb laid along the fist, not pointing back
    "count1": {"index": (-24, -24, -18), "middle": (66, 78, 62), "ring": (66, 78, 62), "thumb": (22, 42, 36)},
    "count2": {"index": (-24, -24, -18), "middle": (-24, -24, -18), "ring": (66, 78, 62), "thumb": (22, 42, 36),
               "fan": 7},
    "count3": {"index": (-24, -24, -18), "middle": (-24, -24, -18), "ring": (-24, -24, -18), "thumb": (24, 44, 38),
               "fan": 7},
    "count4": {"index": (-24, -24, -18), "middle": (-24, -24, -18), "ring": (-24, -24, -18), "thumb": (-24, -14, -6),
               "fan": 8, "thumb_out": 12},
    "thumbs_up": {"index": (68, 78, 62), "middle": (68, 78, 62), "ring": (68, 78, 62), "thumb": (-26, -20, -10),
                  "thumb_out": 6},
    "grip": {"index": (44, 52, 40), "middle": (46, 54, 42), "ring": (48, 56, 44), "thumb": (8, 28, 26)},
    "pinch": {"index": (34, 46, 36), "middle": (52, 62, 48), "ring": (58, 68, 52), "thumb": (14, 30, 30)},
    # the rest pose already curls the fingers ~55 deg: a flat palm needs them opened
    "hold_flat": {"index": (-15, -17, -12), "middle": (-15, -17, -12), "ring": (-13, -15, -10), "thumb": (-12, -4, 0),
                  "fan": 3},
    "claw": {"index": (20, 50, 45), "middle": (22, 52, 46), "ring": (24, 54, 48), "thumb": (6, 22, 22),
             "fan": 10, "thumb_out": 10},
    # cartoon extras: a big jazz-hand spread, a soft half-open hand, fingertips together (a kiss),
    # bent fingertips to scratch with, an index that pops out past straight
    "spread": {"index": (-24, -22, -14), "middle": (-24, -22, -14), "ring": (-24, -22, -14), "thumb": (-28, -16, -8),
               "fan": 15, "thumb_out": 20},
    # an open palm held up: relaxed fingers, slightly curled and spread (a shrug, a "who knows")
    "palm_up": {"index": (-10, -8, -6), "middle": (0, 2, 0), "ring": (8, 10, 6), "thumb": (-14, -6, -2),
                "fan": 15, "thumb_out": 10},
    "soft": {"index": (-2, -2, 0), "middle": (3, 3, 2), "ring": (8, 8, 6), "thumb": (-2, 4, 2), "fan": 8,
             "thumb_out": -8},
    "kiss": {"index": (30, 36, 24), "middle": (34, 40, 28), "ring": (38, 44, 30), "thumb": (10, 24, 22),
             "thumb_out": -4},
    "scratch": {"index": (30, 62, 55), "middle": (32, 64, 56), "ring": (34, 66, 58), "thumb": (14, 32, 30),
                "fan": 6},
    "point_pop": {"index": (-30, -28, -20), "middle": (70, 82, 64), "ring": (70, 82, 64), "thumb": (22, 42, 36)},
}

# facial expressions as rig face properties (anything not listed stays at its default).
# Pushed to cartoon level (brows that fly, big pupils, open smiles) but every value stays inside
# the range the face rig and the web viewer clamp to, so no expression ever breaks the face.
EXPRESSIONS = {
    "neutral": {},
    "happy": {"smile": 0.85, "mouth_open": 0.1, "squint": 0.35, "brow_L": 0.3, "brow_R": 0.3, "pupil": 0.15},
    "joy": {"smile": 1.0, "mouth_open": 0.8, "teeth": 0.85, "squint": 0.6, "brow_L": 0.65, "brow_R": 0.65,
            "pupil": 0.35},
    "laugh": {"smile": 1.0, "mouth_open": 1.0, "teeth": 0.9, "blink_L": 1.0, "blink_R": 1.0, "brow_L": 0.75,
              "brow_R": 0.75},
    "sad": {"smile": -1.0, "mouth_open": -0.6, "brow_in_L": 1.0, "brow_in_R": 1.0, "brow_L": -0.25, "brow_R": -0.25,
            "lid_drop": 0.3, "lid_angle": -0.75, "gaze_y": -0.45, "pupil": 0.3},
    "angry": {"smile": -0.85, "mouth_open": -0.4, "brow_in_L": -1.0, "brow_in_R": -1.0, "brow_L": -0.75,
              "brow_R": -0.75, "lid_drop": 0.28, "lid_angle": 0.9, "pupil": -0.45, "squint": 0.2},
    "scared": {"smile": -0.7, "mouth_open": 0.55, "mouth_round": 0.55, "brow_L": 1.0, "brow_R": 1.0, "brow_in_L": 1.0,
               "brow_in_R": 1.0, "pupil": -1.0},
    "surprised": {"mouth_open": 0.95, "mouth_round": 1.0, "brow_L": 1.0, "brow_R": 1.0, "pupil": -0.6},
    "calm": {"blink_L": 1.0, "blink_R": 1.0, "eye_calm": 1.0, "smile": 0.55, "brow_in_L": 0.2, "brow_in_R": 0.2},
    "thinking": {"mouth_side": 0.8, "mouth_open": -0.8, "smile": 0.1, "brow_L": 0.8, "brow_R": -0.35, "gaze_x": 0.5,
                 "gaze_y": 0.65, "lid_drop": 0.12, "squint": 0.15},
    "skeptical": {"brow_L": 0.85, "brow_R": -0.65, "brow_in_R": -0.55, "mouth_side": -0.85, "mouth_open": -0.85,
                  "smile": -0.25, "lid_drop": 0.38, "gaze_x": -0.45, "squint": 0.2},
    "smug": {"lid_drop": 0.45, "smile": 0.75, "mouth_side": 0.55, "mouth_open": -0.55, "brow_L": 0.45, "brow_R": 0.1},
    "love": {"blink_L": 1.0, "blink_R": 1.0, "smile": 1.0, "brow_in_L": 0.6, "brow_in_R": 0.6, "brow_L": 0.3,
             "brow_R": 0.3, "pupil": 1.0},
    "wink": {"blink_L": 1.0, "smile": 1.0, "mouth_open": 0.1, "squint": 0.45, "mouth_side": 0.45, "brow_R": 0.65},
    "determined": {"brow_in_L": -0.85, "brow_in_R": -0.85, "lid_angle": 0.5, "lid_drop": 0.18, "smile": 0.35,
                   "mouth_open": -0.7, "mouth_side": 0.2},
    "confused": {"brow_L": 0.95, "brow_R": -0.35, "brow_in_R": 0.5, "mouth_side": -0.65, "mouth_round": 0.5,
                 "smile": -0.3},
    "shy": {"smile": 0.6, "mouth_open": -0.55, "brow_in_L": 0.75, "brow_in_R": 0.75, "gaze_y": -0.6, "gaze_x": 0.4,
            "squint": 0.3, "pupil": 0.4},
    "sleepy": {"lid_drop": 0.7, "brow_in_L": 0.3, "brow_in_R": 0.3, "brow_L": -0.2, "brow_R": -0.2, "mouth_open": -0.3},
}

# rest position of each wrist (hand bone head) in the project frame; IK targets are
# given as absolute points and turned into offsets of the hand_ik bones
WRIST_REST = {"L": np.array([0.283, 0.039, 0.315]), "R": np.array([-0.283, 0.039, 0.315])}
PROP_REST = np.array([0.0, -0.20, 0.36])
SGN = {"L": 1.0, "R": -1.0}


def _shape(name_or_dict):
    if isinstance(name_or_dict, dict):
        base = dict(HAND_SHAPES["rest"])
        base.update(name_or_dict)
        return base
    return HAND_SHAPES[name_or_dict]


# ---------------------------------------------------------------- the hand layer
# How "loose" a shape is: 1 = a relaxed hand that may vary and drift freely, 0 = a pose the
# clip needs exactly (a fingertip that taps, a palm that carries a prop).
LOOSE = {"rest": 1.0, "relaxed": 1.0, "soft": 1.0, "palm_up": 0.9, "open": 0.85, "spread": 0.7, "stop": 0.7, "fist": 0.5,
         "claw": 0.5, "kiss": 0.4, "scratch": 0.3, "point": 0.35, "point_pop": 0.3, "count1": 0.35, "count2": 0.35,
         "count3": 0.35, "count4": 0.4, "thumbs_up": 0.35, "grip": 0.2, "pinch": 0.2, "hold_flat": 0.2, "tap": 0.08}
MIN_GAP = 4                      # two different hand shapes closer than this read as a snap
# spring of each finger (Hz, damping): the lead finger is quick, the ring finger and the thumb lag and
# overshoot a little more; the tip phalanx is slower than the base
FINGER_SPRING = {"index": (3.5, 0.55), "middle": (3.1, 0.58), "ring": (2.8, 0.6), "thumb": (2.5, 0.5)}
SEG_SLOW = (1.0, 0.93, 0.86)
# a hand that closes starts with the outer fingers, one that opens starts with the index (frames of lag)
LAG_CLOSE = {"ring": 0.0, "middle": 0.8, "index": 1.6, "thumb": 2.4}
LAG_OPEN = {"index": 0.0, "middle": 0.8, "ring": 1.6, "thumb": 1.0}
CURL_BIAS = {"index": -3.0, "middle": 0.0, "ring": 4.0}      # index straightest .. ring most curled
# anatomical limits (deg): no hyper-extension, no impossible curl, fingers never cross
CURL_LIMITS = {"index": [(-32, 98), (-30, 104), (-24, 90)], "middle": [(-32, 98), (-30, 104), (-24, 90)],
               "ring": [(-32, 98), (-30, 104), (-24, 90)], "thumb": [(-32, 60), (-26, 62), (-16, 56)]}
FAN_LIMITS = (-2.0, 19.0)
THUMB_OUT_LIMITS = (-30.0, 26.0)


def _snap_free(shapes):
    """Keys of different shapes at least MIN_GAP frames apart (later keys move later, never earlier)."""
    out, prev = [], None
    for f, s in shapes:
        if prev is not None:
            gap = MIN_GAP if s is not prev[1] else 0
            f = max(f, prev[0] + gap)
        out.append((f, s))
        prev = (f, s)
    return out


def finger_shifts(n, loop, seed, amp=14.0):
    """A finger that moves on its own now and then: every 2-4 s it eases into a slightly different
    curl (+- amp deg), holds a moment and drifts back. Calm, never a twitch."""
    r = np.random.default_rng(seed)
    out = np.zeros(n)
    t = r.uniform(0, 40)
    while True:
        rise, hold, back = r.uniform(8, 14), r.uniform(10, 30), r.uniform(20, 40)
        end = t + rise + hold + back
        if end >= n - 2:
            break
        a = r.uniform(0.5, 1.0) * amp * (1 if r.random() < 0.5 else -1)
        pts = [(t, 0.0), (t + rise, a), (t + rise + hold, 0.85 * a), (end, 0.0)]
        if not loop:
            pts = [(0, 0.0)] + pts + [(n - 1, 0.0)]
        out += C.keys(n, sorted(set(pts)), loop=loop)
        t = end + r.uniform(0, 28)
    return out


def hand_channels(clip, side, keys):
    """keys: [(frame, shape name or dict), ...] -> finger channels, alive:
    - keys of different shapes closer than MIN_GAP frames are spread out (no snaps);
    - every finger moves on its own clock: the lead finger first, the others 1-2 frames later, the tip
      phalanx after its base, the thumb on its own timing (opening starts with the index, closing
      with the outer fingers); every transition draws its own small lag;
    - each finger follows its curve through a spring: it lags and overshoots a little and settles;
    - loose shapes (relaxed, soft, open...) never repeat exactly: a small random offset per key, a curl
      gradient (index straightest, ring most curled) and slow asynchronous drift per finger;
    - everything stays inside the anatomical limits."""
    # a custom dict may carry its own "_loose" (0 = exactly these angles, 1 = a free hand)
    rows = sorted(((f, _shape(s), LOOSE.get(s, 0.6) if isinstance(s, str) else s.get("_loose", 0.6))
                   for f, s in keys), key=lambda r: r[0])
    shapes = _snap_free([(r[0], r[1]) for r in rows])
    loose = [r[2] for r in rows]
    n, loop, fps = clip.n, clip.loop, clip.fps
    seed = int(getattr(clip, "seed", 0)) * 977 + (13 if side == "L" else 0)
    rng = np.random.default_rng(seed + 5)
    lo_curve = np.clip(clip.arr([(f, l) for (f, _), l in zip(shapes, loose)]), 0, 1)
    # a shape the clip needs exactly (loose <= 0.05: a fingertip on his chin) gets no drift, shift or drag at all
    free = np.clip((lo_curve - 0.05) / 0.1, 0, 1)
    if not hasattr(clip, "hand_meta"):
        clip.hand_meta = {}
    clip.hand_meta[side] = {"loose": lo_curve, "free": free}
    last = len(shapes) - 1
    cid = [0]
    # this hand's own character (left and right never match): a little more or less curl per finger, a
    # thumb that rests a bit in or out, a different spread. Fixed shapes (touches, props) keep their angles.
    prng = np.random.default_rng(seed + 31)
    pw = np.clip((np.array(loose) - 0.2) / 0.5, 0, 1)                 # one weight per key
    pers = {f: prng.uniform(-1, 1) for f in FINGER_NAMES + ("thumb", "thumb_out", "fan_i", "fan_r", "thumb_c")}
    # fist / grip tighten and loosen with effort (a slow squeeze), only for the middling shapes
    eff_w = np.clip((lo_curve - 0.3) / 0.2, 0, 1) * np.clip((0.95 - lo_curve) / 0.3, 0, 1)
    eff = C.noise(n, prng.uniform(26, 44), 1.0, seed + 33, loop) * eff_w

    def build(vals, lags, amp, lim, spring_key, seg):
        """one channel: keys -> lagged, perturbed, sprung, drifting, limited."""
        pts, t_prev = [], None
        for i, ((f, _), v) in enumerate(zip(shapes, vals)):
            t = f + (lags[i] if 0 < i < last else 0.0)
            if t_prev is not None:
                t = max(t, t_prev + 1.0)
            pts.append((t, v + amp[i]))
            t_prev = t
        x = clip.arr(pts)
        fr, dm = FINGER_SPRING[spring_key]
        x = C.spring(x, freq=fr * SEG_SLOW[seg], damping=dm, fps=fps, loop=loop)
        cid[0] += 1
        x = x + C.noise(n, rng.uniform(38, 80), 5.0, seed + 100 + cid[0], loop) * lo_curve * free
        return np.clip(x, *lim)

    for fi, fname in enumerate(FINGER_NAMES):
        tot = [sum(s[fname]) for _, s in shapes]
        jit = [rng.uniform(0.0, 0.8) for _ in shapes]
        shift = finger_shifts(n, loop, seed + 400 + 10 * fi) * lo_curve * free      # one slow shift every 2-4 s
        shared = [rng.uniform(-1, 1) for _ in shapes]
        lag = [0.0] + [0.0 if abs(tot[i] - tot[i - 1]) < 8 else
                       (LAG_CLOSE if tot[i] > tot[i - 1] else LAG_OPEN)[fname] + jit[i] for i in range(1, len(shapes))]
        for seg in range(3):
            vals = [s[fname][seg] for _, s in shapes]
            amp = [5.0 * l * shared[i] * (0.6, 1.0, 0.7)[seg] + CURL_BIAS[fname] * l * (1.0, 1.15, 0.8)[seg]
                   + rng.uniform(-1, 1) * 1.5 * l
                   + 7.0 * pers[fname] * pw[i] * (0.7, 1.0, 0.8)[seg] for i, l in enumerate(loose)]
            lags = [lg + (0.7 * seg if lg else 0.0) for lg in lag]
            x = build(vals, lags, amp, CURL_LIMITS[fname][seg], fname, seg)
            x = x + (shift + 4.0 * eff * (0.8 + 0.4 * pers[fname])) * (0.7, 1.0, 0.8)[seg]
            clip.add(f"{fname}.{seg + 1:02d}.{side}.cx", np.clip(x, *CURL_LIMITS[fname][seg]))
    # fan: index towards the thumb, ring away from it (mirrored per side)
    for fname, sgn in (("index", SGN[side]), ("ring", -SGN[side])):
        vals = [s.get("fan", 0.0) for _, s in shapes]
        amp = [rng.uniform(-1, 1) * 2.0 * l + 0.8 * l + 2.0 * pers["fan_i" if fname == "index" else "fan_r"] * pw[i]
               for i, l in enumerate(loose)]
        lags = [0.0] + [rng.uniform(0.5, 2.0) for _ in shapes[1:]]
        # the gap to the next finger breathes a little too
        fan = build(vals, lags, amp, FAN_LIMITS, fname, 0)
        fan = fan + C.noise(n, rng.uniform(60, 110), 1.8, seed + 520 + len(fname), loop) * lo_curve * free
        clip.add(f"{fname}.01.{side}.cz", np.clip(fan, *FAN_LIMITS), sgn)
    tot = [sum(s["thumb"]) for _, s in shapes]
    tlag = [0.0] + [0.0 if abs(tot[i] - tot[i - 1]) < 8 else
                    (LAG_CLOSE if tot[i] > tot[i - 1] else LAG_OPEN)["thumb"] + rng.uniform(0, 0.8)
                    for i in range(1, len(shapes))]
    for seg, bname in enumerate((f"thumb.{side}", f"thumb.02.{side}", f"thumb.03.{side}")):
        amp = [rng.uniform(-1, 1) * 3.0 * l + 8.0 * pers["thumb_c"] * pw[i] * (1.0, 0.8, 0.6)[seg]
               for i, l in enumerate(loose)]
        clip.add(f"{bname}.cx", build([s["thumb"][seg] for _, s in shapes], [t + (0.6 * seg if t else 0.0) for t in tlag],
                                      amp, CURL_LIMITS["thumb"][seg], "thumb", seg))
    amp = [rng.uniform(-1, 1) * 2.5 * l + 6.0 * pers["thumb_out"] * pw[i] for i, l in enumerate(loose)]
    clip.add(f"thumb.{side}.cz", build([s.get("thumb_out", 0.0) for _, s in shapes], tlag, amp,
                                       THUMB_OUT_LIMITS, "thumb", 0), SGN[side])


def hand_follow(clip):
    """Follow-through of the hand from the arm's motion (called by Clip.secondary):
    - the wrist trails the forearm: it lags behind the arm angle through a spring, so a quick arm move
      bends the wrist back and it overshoots when the arm stops;
    - fingers drag: the faster the arm moves (angles, or the IK target) the more the fingers trail
      (tips extend a little, the spread opens), delayed through a spring so they settle after;
    - a hand nobody keyed gets a relaxed, living hand;
    - the final anatomical clamp over every finger channel (curl() and gestures add on top)."""
    n, fps, loop = clip.n, clip.fps, clip.loop
    for s in ("L", "R"):
        if s not in getattr(clip, "hand_meta", {}):
            hand_channels(clip, s, [(0, "relaxed")])
    for s in ("L", "R"):
        speed = np.zeros(n)
        for ax, gain in (("rx", 0.6), ("ry", 0.35), ("rz", 0.6)):
            ang = clip.get(f"upper_arm.{s}.{ax}") + clip.get(f"forearm.{s}.{ax}")
            lag = C.spring(ang, freq=2.4, damping=0.36, fps=fps, loop=loop)
            clip.add(f"hand.{s}.{ax}", np.clip(gain * (lag - ang), -14, 14))
            speed += np.abs(np.gradient(ang))
        ik = np.clip(clip.get(f"ik.{s}"), 0, 1)
        for ax in "xyz":
            speed += ik * np.abs(np.gradient(clip.get(f"hand_ik.{s}.l{ax}"))) * 250.0
        sp = C.spring(np.clip(speed, 0, 12), freq=3.2, damping=0.6, fps=fps, loop=loop)
        w = clip.hand_meta[s]["loose"]
        drag = (0.4 + 0.6 * w) * clip.hand_meta[s]["free"]          # an exact fingertip is never dragged off
        for fname in FINGER_NAMES:
            for seg, k in enumerate((0.35, 0.6, 0.85)):
                clip.add(f"{fname}.{seg + 1:02d}.{s}.cx", -np.clip(k * sp, 0, 8) * drag)
        clip.add(f"index.01.{s}.cz", np.clip(0.3 * sp, 0, 3) * w, SGN[s])
        clip.add(f"ring.01.{s}.cz", np.clip(0.3 * sp, 0, 3) * w, -SGN[s])
    # a loose hand also lives in the wrist: it sways slowly with the breathing and the weight shifts,
    # a little different on each side (a free, relaxed hand most, a hand with a job none)
    seed = int(getattr(clip, "seed", 0))
    breath = clip.get("chest.rx") / 1.3
    shift = clip.get("hips.ry") / 4.0
    for k, s in enumerate(("L", "R")):
        w = np.clip((clip.hand_meta[s]["loose"] - 0.5) / 0.4, 0, 1)
        clip.add(f"hand.{s}.rx", w * (1.6 * breath + C.noise(n, 64, 3.0, seed + 31 + k, loop)))
        clip.add(f"hand.{s}.ry", w * (1.5 * shift + C.noise(n, 82, 3.0, seed + 33 + k, loop)))
        clip.add(f"hand.{s}.rz", w * C.noise(n, 95, 3.0, seed + 35 + k, loop))
        clip.add(f"hand.{s}.tw", w * C.noise(n, 110, 4.0, seed + 37 + k, loop))
    for s in ("L", "R"):
        for fname in FINGER_NAMES:
            for seg in range(3):
                key = f"{fname}.{seg + 1:02d}.{s}.cx"
                clip.ch[key] = np.clip(clip.get(key), *CURL_LIMITS[fname][seg])
        for bname, seg in ((f"thumb.{s}", 0), (f"thumb.02.{s}", 1), (f"thumb.03.{s}", 2)):
            clip.ch[f"{bname}.cx"] = np.clip(clip.get(f"{bname}.cx"), *CURL_LIMITS["thumb"][seg])
        for fname, sgn in (("index", SGN[s]), ("ring", -SGN[s])):
            key = f"{fname}.01.{s}.cz"
            clip.ch[key] = sgn * np.clip(sgn * clip.get(key), *FAN_LIMITS)


def wave_drive(n, f0, f1, period=13.0, seed=0, phase=0.0, loop=False):
    """-1..1 drive of a wave (a hand greeting): the period drifts and every swing has its own size,
    it builds in over ~5 frames and dies out over ~8 (a person never waves like a metronome)."""
    per = period * (1.0 + 0.10 * C.noise(n, 38, 1.0, seed, loop))
    ph = np.cumsum(1.0 / per)
    ph = ph - ph[min(n - 1, int(f0))] + phase
    env = C.keys(n, [(0, 0), (f0, 0), (f0 + 5, 1), (f1 - 8, 1), (f1, 0), (n - 1, 0)])
    amp = 1.0 + 0.14 * C.noise(n, 14, 1.0, seed + 1, loop)
    return np.sin(2 * np.pi * ph) * env * amp


def finger_roll(clip, side, drive, amp=9.0, lag=1.4):
    """A rolling cascade through the fingers (waving, wiggling, a hand that flutters): `drive` is a
    -1..1 wave; each finger and phalanx follows `lag` frames after the one before it, the thumb
    answers a little against it."""
    drive = clip.arr(drive)
    for i, fname in enumerate(FINGER_NAMES):
        for seg in range(3):
            d = C.delay(drive, lag * (0.8 * i + 0.7 * seg), loop=clip.loop)
            clip.add(f"{fname}.{seg + 1:02d}.{side}.cx", d * amp * (0.8 + 0.2 * seg))
    for seg, bname in enumerate((f"thumb.{side}", f"thumb.02.{side}", f"thumb.03.{side}")):
        clip.add(f"{bname}.cx", -C.delay(drive, lag * (2.2 + 0.6 * seg), loop=clip.loop) * amp * 0.3)


def hand_flutter(clip, side, strength=1.0, when=None):
    """A nervous flutter: every finger trembles on its own fast rhythm (a hand that shakes with fear or
    cold). `when` (array or keys, 0..1) says when; strength 1 ~ 3 deg per phalanx."""
    e = clip.arr(1.0 if when is None else when)
    seed = int(getattr(clip, "seed", 0)) * 977 + (13 if side == "L" else 0) + 700
    r = np.random.default_rng(seed)
    for fname in FINGER_NAMES + ("thumb",):
        for seg in range(3):
            per = r.uniform(3.0, 6.0)
            d = C.noise(clip.n, per, 3.0 * strength, int(r.integers(1, 10**6)), clip.loop) * e
            key = f"{fname}.{seg + 1:02d}.{side}.cx" if fname != "thumb" else (
                f"thumb.{side}.cx", f"thumb.02.{side}.cx", f"thumb.03.{side}.cx")[seg]
            clip.add(key, d * (0.6 if fname == "thumb" else 1.0))


def hand_beat(clip, side, frames, strength=1.0):
    """An emphasis beat: on each frame the fingers open and spread a little (the index leads, the
    others follow) and settle; the thumb swings out."""
    n, lp = clip.n, clip.loop
    for f0 in frames:
        for i, fname in enumerate(FINGER_NAMES):
            for seg in range(3):
                clip.add(f"{fname}.{seg + 1:02d}.{side}.cx", C.pulse(
                    n, f0, [(-3, 0.0), (1 + i, -9.0 * strength), (5 + i, 2.0 * strength), (10 + i, 0.0)], loop=lp))
        clip.add(f"index.01.{side}.cz", C.pulse(n, f0, [(-2, 0.0), (2, 5.0 * strength), (9, 0.0)], loop=lp), SGN[side])
        clip.add(f"ring.01.{side}.cz", C.pulse(n, f0, [(-2, 0.0), (3, 5.0 * strength), (10, 0.0)], loop=lp), -SGN[side])
        clip.add(f"thumb.{side}.cz", C.pulse(n, f0, [(-2, 0.0), (3, 8.0 * strength), (11, 0.0)], loop=lp), SGN[side])


def expr_channels(clip, keys, scale=1.0):
    """keys: [(frame, expression name or dict[, weight]), ...] -> face property channels."""
    rows = []
    for k in keys:
        f, e = k[0], k[1]
        w = k[2] if len(k) > 2 else 1.0
        rows.append((f, EXPRESSIONS[e] if isinstance(e, str) else e, w))
    props = sorted({p for _, e, _ in rows for p in e})
    for p in props:
        clip.prop(p, [(f, e.get(p, 0.0) * w) for f, e, w in rows], scale)


def reach_channels(clip, side, keys, ramp=None):
    """IK reach. keys: [(frame, point or None[, weight]), ...]; point = wrist target in the
    project frame (where the hand bone's head should go, prop at rest); None = FK.
    The IK weight eases between keys like everything else."""
    pts, ws = [], []
    last = WRIST_REST[side]
    for k in keys:
        f, p = k[0], k[1]
        w = (k[2] if len(k) > 2 else 1.0) if p is not None else 0.0
        if p is not None:
            last = np.asarray(p, float)
        pts.append((f, last - WRIST_REST[side]))
        ws.append((f, w))
    for i, ax in enumerate("xyz"):
        clip.add(f"hand_ik.{side}.l{ax}", [(f, d[i]) for f, d in pts])
    clip.add(f"ik.{side}", ws)


def reach_rot(clip, side, rx=None, ry=None, rz=None):
    """Orientation of the hand while on IK (world rest axes, degrees, like the body)."""
    for ax, v in (("rx", rx), ("ry", ry), ("rz", rz)):
        if v is not None:
            clip.add(f"hand_ik.{side}.{ax}", v)


def stretch_channels(clip, side, keys):
    """Cartoon reach: arm segments up to ~12 % longer (1.0 = rest)."""
    clip.add(f"upper_arm.{side}.sy", keys)
    clip.add(f"forearm.{side}.sy", keys)


def show_prop(clip, bone, keys):
    clip.add(f"{bone}.s", keys)


def place_prop(clip, loc=None, rot=None):
    """Prop bone offset from its rest spot in front of the chest (m) and rotation (deg)."""
    if loc is not None:
        for i, ax in enumerate("xyz"):
            clip.add(f"prop.l{ax}", [(f, v[i]) for f, v in loc])
    if rot is not None:
        for i, ax in enumerate(("rx", "ry", "rz")):
            clip.add(f"prop.{ax}", [(f, v[i]) for f, v in rot])


def _rest_hand_frame(side):
    """Rest direction of the fingers (D) and of the palm (N) of each hand (see build_hands.py)."""
    sx = SGN[side]
    D = np.array([0.592 * sx, 0.046, -0.805])
    D /= np.linalg.norm(D)
    F = np.array([0.0, -1.0, 0.0])
    F -= (F @ D) * D
    F /= np.linalg.norm(F)
    N = np.cross(D, F)
    if np.sign(N[0]) == sx:
        N = -N
    return D, N


def rot_matrix(rx, ry, rz):
    """Rotation of a (rx, ry, rz) world-rest-axes channel triple (degrees): Rz Rx Ry."""
    a, b, g = np.radians([rx, ry, rz])
    Rx = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    Ry = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
    Rz = np.array([[np.cos(g), -np.sin(g), 0], [np.sin(g), np.cos(g), 0], [0, 0, 1]])
    return Rz @ Rx @ Ry


def _angles(R):
    a = np.arcsin(np.clip(R[2, 1], -1, 1))
    b = np.arctan2(-R[2, 0], R[2, 2])
    g = np.arctan2(-R[0, 1], R[1, 1])
    return tuple(float(np.degrees(v)) for v in (a, b, g))


def _closest(r, prev):
    """Of the two angle triples giving the same rotation (and their 360 turns), the one
    nearest the previous key, so interpolated keys turn the short way."""
    if prev is None:
        return r
    a, b, g = r
    best = None
    for cand in ((a, b, g), (180 - a, b + 180, g + 180)):
        c = tuple(v + 360 * round((p - v) / 360) for v, p in zip(cand, prev))
        dist = sum((v - p) ** 2 for v, p in zip(c, prev))
        if best is None or dist < best[0]:
            best = (dist, c)
    return best[1]


def hand_orient(side, fingers_dir, palm_dir, prop_rot=None):
    """World-rest-axes angles (rx, ry, rz, degrees) for hand_ik so the fingers point along
    `fingers_dir` with the palm facing `palm_dir` (project frame: -Y is Morfi's front).
    hand_ik bones are children of the prop bone: pass the prop's rotation when it is turned,
    the directions stay in the world frame."""
    D0, N0 = _rest_hand_frame(side)
    D = np.array(fingers_dir, float)
    D /= np.linalg.norm(D)
    N = np.array(palm_dir, float)
    N -= (N @ D) * D
    N /= np.linalg.norm(N)
    A = np.stack([D0, N0, np.cross(D0, N0)], 1)
    B = np.stack([D, N, np.cross(D, N)], 1)
    R = B @ A.T                                   # rest frame -> wanted frame
    if prop_rot is not None:
        R = rot_matrix(*prop_rot).T @ R
    return _angles(R)                             # R = Rz(g) Rx(a) Ry(b), as rigmap composes


def orient_keys(side, keys, prop_rot=None):
    """keys: [(frame, fingers_dir, palm_dir), ...] -> rx/ry/rz key lists for reach_rot."""
    rows, prev = [], None
    for f, d, n in keys:
        r = _closest(hand_orient(side, d, n, prop_rot), prev)
        rows.append((f, r))
        prev = r
    return ([(f, r[0]) for f, r in rows], [(f, r[1]) for f, r in rows], [(f, r[2]) for f, r in rows])


def prop_space(point, prop_loc=(0, 0, 0), prop_rot=(0, 0, 0)):
    """World point (prop placed with these channels) -> the 'prop at rest' point that
    reach() expects, so a hand target follows the prop if it moves later."""
    head = PROP_REST + np.asarray(prop_loc, float)
    return PROP_REST + rot_matrix(*prop_rot).T @ (np.asarray(point, float) - head)


def prop_world(local, prop_loc=(0, 0, 0), prop_rot=(0, 0, 0)):
    """Point in a prop object's own frame -> world (props are built at the prop bone head)."""
    return PROP_REST + np.asarray(prop_loc, float) + rot_matrix(*prop_rot) @ np.asarray(local, float)


EYES = np.array([0.0, -0.215, 0.705])     # between the eyes, at rest
GAZE_RANGE = (26.0, 20.0)                 # degrees of look the iris gives at gaze_x/y = +-1


def look_at(clip, keys, head=0.55, neck=0.15, max_nod=7.0):
    """Turn the head (and neck) towards world points and let the eyes do the rest.
    keys: [(frame, point or None), ...]; None = look ahead. The head takes `head` of the turn
    and the neck `neck` (a nod is capped at `max_nod` degrees: with Morfi's big head a deeper
    nod brings the chin onto his own hands); the eyes cover what is left, so he really looks at
    what he is touching even when the head cannot."""
    rows = []
    for f, p in keys:
        if p is None:
            rows.append((f, 0.0, 0.0))
            continue
        d = np.asarray(p, float) - EYES
        # something under his nose (a tablet at the belly) is a little "behind" the eyes: the turn
        # comes from the sideways offset only, never a half turn of the head
        fwd = max(-d[1], 0.3 * abs(d[2]), 0.05)
        yaw = float(np.clip(np.degrees(np.arctan2(d[0], fwd)), -60, 60))  # + = towards his left (+X)
        pitch = np.degrees(np.arctan2(d[2], np.hypot(d[0], d[1])))  # + = up
        rows.append((f, yaw, pitch))
    yaw_k = [(f, y) for f, y, _ in rows]
    nod_k = [(f, float(np.clip(-p * (head + neck), -max_nod, max_nod))) for f, _, p in rows]
    clip.add("head.rz", [(f, y * head) for f, y in yaw_k])
    clip.add("neck.rz", [(f, y * neck) for f, y in yaw_k])
    clip.add("head.rx", [(f, v * head / (head + neck)) for f, v in nod_k])
    clip.add("neck.rx", [(f, v * neck / (head + neck)) for f, v in nod_k])
    gx = [(f, float(np.clip(y * (1 - head - neck) / GAZE_RANGE[0], -1, 1))) for f, y in yaw_k]
    gy = [(f, float(np.clip((p + nod) / GAZE_RANGE[1], -1, 1))) for (f, _, p), (_, nod) in zip(rows, nod_k)]
    clip.prop("gaze_x", gx)
    clip.prop("gaze_y", gy)


def bounce_blink(n, times):
    return C.blink_track(n, times)
