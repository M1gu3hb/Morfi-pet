"""Full scenes for the lab: short performances with the official voice (Super VM), acted and cut
like a finished video. Six scenes; in three of them Morfi talks to himself (solo).

Pure numpy (no Blender), so the web exporter can rebuild the face curves from the same code:

    tl = timeline("susto")          # the voice lines placed on the scene timeline
    p = build("susto", tl)          # Performance: body, face, lip-sync, props, contacts
    clip = finish(p)                # Clip ready for rigmap.bake + the contact solvers
    meta(tl)                        # what the export / web player needs (title, audio, camera cues)

make_scenes.py composes the audio (web/public/voice/scenes/<key>.mp3 + <key>.json, the merged
alignment) and bakes each scene as the action Scene_<Key>.

The ElevenLabs alignment is loose: the first letter after a pause often swallows the silence
before it ("Tampoco" starts 0.4 s before the sound). Every word is snapped to the voiced frames
of its own audio before anything else uses it, so the mouth never moves in a silence. The audio
tags of the script ([laughs], [gasps], [yawns], [whispers]) become sounds the face acts too.

Signs follow rigmap.py: Morfi faces -Y, his left is +X, +rx leans forward, +ry tilts to his left,
+rz turns to his left.
"""
import json
import os
import re

import numpy as np

from . import curves as C
from .acting import Acting
from .clip import FPS, Clip
from .motor import HAND_SHAPES, PROP_REST, prop_world, rot_matrix
from .performance import CLOSED, NARROW, TALK_BASE, VOWEL, Performance


def exact(name):
    """A shape the hand layer keeps at its exact angles: the fingers that touch his skin must land."""
    return dict(HAND_SHAPES[name], _loose=0.05)


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
VOICE = os.path.join(REPO, "web", "public", "voice", "supervm")
OUT = os.path.join(REPO, "web", "public", "voice", "scenes")
SCRIPT = os.path.join(REPO, "voice", "scenes.json")

VOICED = 0.10            # envelope (0..~1.3, per 1/30 s) above which the voice is sounding
SNAP = 0.14              # a word may move this much (s) towards its own sound
CAM = np.array([0.0, -2.6, 0.72])           # the viewer (web camera straight ahead, eye height)

# ---------------------------------------------------------------- direction: when each line starts
# start time of every line (s) on the scene timeline, the hold after the last word, the sound
# effects (synthesised in make_scenes.py) and the camera cues for the web player
PLAN = {
    "presentacion": {"starts": [0.45, 2.75, 4.55, 8.85], "tail": 1.45, "sfx": [],
                     "cams": [[0.0, "medium"], [1.38, "close"], [2.6, "wide"], [4.5, "medium"],
                              [7.15, "wide"], [8.85, "close"]]},
    "calculadora": {"starts": [0.30, 3.55, 5.75, 8.25, 11.25], "tail": 1.10, "sfx": [["pop", 9.62]],
                    "cams": [[0.0, "medium"], [3.3, "wide"], [8.15, "close"], [9.35, "medium"],
                             [11.4, "close"], [13.0, "medium"]]},
    "idea": {"starts": [0.55, 3.35, 4.35, 7.15, 9.75], "tail": 1.10, "sfx": [],
             "cams": [[0.0, "medium"], [2.0, "close"], [6.6, "wide"], [8.1, "medium"], [9.7, "close"]]},
    "ventas": {"starts": [0.40, 2.30, 5.45, 8.15], "tail": 4.20, "sfx": [],
               "cams": [[0.0, "medium"], [2.2, "close"], [5.4, "medium"], [8.1, "close"],
                        [9.5, "wide"]]},
    "susto": {"starts": [0.75, 4.15, 6.40, 8.55], "tail": 1.10, "sfx": [["bell", 0.55], ["bell2", 5.85]],
              "cams": [[0.0, "medium"], [0.5, "wide"], [2.0, "medium"], [4.0, "close"], [5.8, "medium"],
                       [8.45, "close"]]},
    "sueno": {"starts": [0.45, 3.30, 7.75, 10.55], "tail": 1.30, "sfx": [["chime", 7.25]],
              "cams": [[0.0, "wide"], [2.2, "medium"], [4.6, "close"], [7.6, "wide"], [9.0, "medium"]]},
}
TAGS = {"laughs": "laugh", "gasps": "gasp", "yawns": "yawn", "whispers": "whisper", "excited": "excited"}


def script():
    return json.load(open(SCRIPT, encoding="utf-8"))


def scene_info(key):
    return next(s for s in script()["scenes"] if s["key"] == key)


def line_keys(key):
    return [ln for ln in script()["lines"] if ln["key"].startswith(f"sc_{key}_")]


# ---------------------------------------------------------------- alignment
def _voiced(env, t, thr=VOICED):
    i = int(t * FPS)
    return 0 <= i < len(env) and env[i] > thr


def _words(chars, t0, t1):
    """Letters grouped into words: [{w, i0, i1 (char index range), a, b (first/last letter time)}]."""
    out, cur = [], []
    for i, ch in enumerate(chars + " "):
        if ch.isspace():
            if cur:
                letters = [j for j in cur if re.match(r"\w", chars[j])]
                if letters:
                    out.append({"w": "".join(chars[j] for j in cur), "i0": cur[0], "i1": cur[-1],
                                "a": t0[letters[0]], "b": t1[letters[-1]]})
            cur = []
        else:
            cur.append(i)
    return out


def refine(chars, t0, t1, env):
    """Snap every word onto its own sound: its start to the first voiced frame near it, its end to
    the last one, and spread its letters over that span (order kept, words never overlap)."""
    t0, t1 = list(t0), list(t1)
    env = np.asarray(env, float)
    words = _words(chars, t0, t1)
    floor = 0.0
    for k, w in enumerate(words):
        nxt = words[k + 1]["a"] if k + 1 < len(words) else len(env) / FPS
        lo, hi = max(floor, w["a"] - SNAP), min(nxt, w["b"] + SNAP)
        fr = [i for i in range(int(lo * FPS), int(np.ceil(hi * FPS)) + 1) if 0 <= i < len(env)]
        if not fr:
            continue
        peak = max(env[i] for i in fr)
        thr = max(0.06, 0.2 * peak)
        on = [i for i in fr if env[i] > thr]
        if not on:
            continue
        # the voiced run that overlaps the word the most (a laugh before a word is not the word)
        runs, cur = [], [on[0], on[0]]
        for i in on[1:]:
            if i - cur[1] <= 3:
                cur[1] = i
            else:
                runs.append(cur)
                cur = [i, i]
        runs.append(cur)
        span = [r for r in runs if r[1] / FPS >= w["a"] - 0.05 and r[0] / FPS <= w["b"] + 0.05] or runs
        na = max(lo, min(r[0] for r in span) / FPS)
        nb = min(hi, (max(r[1] for r in span) + 1) / FPS)
        if nb - na < 0.06:
            continue
        a, b = w["a"], w["b"]
        scale = (nb - na) / max(b - a, 1e-3)
        for j in range(w["i0"], w["i1"] + 1):
            t0[j] = round(na + (min(max(t0[j], a), b) - a) * scale, 3)
            t1[j] = round(na + (min(max(t1[j], a), b) - a) * scale, 3)
        floor = nb
    return t0, t1


def _tags(text):
    return [TAGS[t] for t in re.findall(r"\[(\w+)\]", text) if t in TAGS]


def _sounds(words, env, tags):
    """Voiced stretches that belong to no word: the laugh, gasp or yawn of the line's tag."""
    kind = next((t for t in tags if t in ("laugh", "gasp", "yawn")), None)
    if kind is None:
        return []
    env = np.asarray(env, float)
    covered = np.zeros(len(env), bool)
    for w in words:
        covered[max(0, int(w["start_rel"] * FPS) - 1):int(w["end_rel"] * FPS) + 2] = True
    on = (env > (0.05 if kind == "gasp" else 0.08)) & ~covered
    out, s = [], None
    for i, v in enumerate(list(on) + [False]):
        if v and s is None:
            s = i
        if not v and s is not None:
            if i - s >= 2:
                out.append([s / FPS, i / FPS])
            s = None
    if not out:
        return []
    if kind == "gasp":                      # one short intake, the first one
        out = out[:1]
    else:                                   # one laugh / yawn: from the first to the last burst
        first_word = words[0]["start_rel"] if words else 1e9
        out = [x for x in out if x[1] <= first_word + 0.05] or out[:1]
        out = [[out[0][0], out[-1][1]]]
    return [{"kind": kind, "t0": round(a, 3), "t1": round(b, 3)} for a, b in out]


def load_line(key, voice_dir=VOICE):
    d = json.load(open(os.path.join(voice_dir, key + ".json"), encoding="utf-8"))
    chars = d["chars"] if isinstance(d["chars"], str) else "".join(d["chars"])
    t0, t1 = refine(chars, d["t0"], d["t1"], d["env"])
    return {"key": key, "dur": d["dur"], "chars": chars, "t0": t0, "t1": t1, "env": d["env"], "text": d["text"]}


def build_timeline(key, rows, starts, sfx, cams, info, tail, voice_dir=VOICE, min_dur=0.0, extra=None):
    """Voice lines placed on a timeline: rows = [{"key", "text"}] (text with the [audio tags]), starts =
    start second of each, sfx = [[kind, t], ...]. The shape Performance.speak / Acting.talk expect,
    plus duration, sounds and camera cues. `min_dur` keeps the take at least that long (s); `extra`
    adds keys to the result."""
    lines, sounds = [], []
    for row, st in zip(rows, starts):
        d = load_line(row["key"], voice_dir)
        ws = _words(d["chars"], d["t0"], d["t1"])
        words = [{"w": w["w"], "start": round(st + w["a"], 3), "end": round(st + w["b"], 3),
                  "start_rel": w["a"], "end_rel": w["b"]} for w in ws]
        tags = _tags(row["text"])
        stress = [w["start_rel"] for w in words
                  if re.search(r"[áéíóú]", w["w"].lower()) or len(re.sub(r"\W", "", w["w"])) >= 7]
        snd = _sounds(words, d["env"], tags)
        for s in snd:
            sounds.append({"kind": s["kind"], "t0": round(st + s["t0"], 3), "t1": round(st + s["t1"], 3),
                           "line": len(lines)})
        lines.append({"key": row["key"], "text": d["text"], "start": st, "dur": d["dur"], "chars": d["chars"],
                      "t0": d["t0"], "t1": d["t1"], "env": d["env"], "tags": tags, "question": "?" in d["text"],
                      "words": [{k: w[k] for k in ("w", "start", "end")} for w in words], "stress": stress,
                      "speech": (words[0]["start"], words[-1]["end"]) if words else (st, st)})
    for kind, t in sfx:
        sounds.append({"kind": kind, "t0": t, "t1": t + 0.6})
    end = max(max(ln["start"] + ln["dur"] for ln in lines), lines[-1]["speech"][1] + tail, min_dur)
    dur = round(end, 3)
    tl = {"key": key, "lines": lines, "sounds": sorted(sounds, key=lambda s: s["t0"]), "dur": dur,
          "frames": int(round(dur * FPS)), "cams": cams, "info": info, "voice_dir": voice_dir}
    tl.update(extra or {})
    return tl


def timeline(key):
    """The scene's lines on its timeline (see build_timeline) from PLAN and voice/scenes.json."""
    plan = PLAN[key]
    return build_timeline(key, line_keys(key), plan["starts"], plan["sfx"], plan["cams"], scene_info(key), plan["tail"])


# ---------------------------------------------------------------- performance tests (timeline JSON)
TEST_SCRIPTS = (os.path.join(REPO, "voice", "tests_day.json"), SCRIPT)   # where the lines' text (with tags) lives
SFX_KINDS = ("bell", "bell2", "chime", "pop")
SHOTS = ("wide", "medium", "close", "face")
VOICED_MIN = 0.06        # envelope above this = a sound (a yawn or a laugh counts, not only words)
MIN_GAP = 0.04           # lines may not sound closer than this (s)


class TimelineError(ValueError):
    """A timeline JSON the audio cannot be composed from (the message says what to change)."""


def line_text(key, scripts=TEST_SCRIPTS):
    """Text with audio tags of a voice line, from the script files (voice/tests_day.json, voice/scenes.json)."""
    for path in scripts:
        if os.path.exists(path):
            for ln in json.load(open(path, encoding="utf-8")).get("lines", []):
                if ln["key"] == key:
                    return ln["text"]
    return None


def voiced_span(start, env):
    """(first, last) second a line makes any sound at, from its envelope (a yawn is not a word)."""
    on = [i for i, v in enumerate(env) if v is not None and v > VOICED_MIN]
    return (start + on[0] / FPS, start + (on[-1] + 1) / FPS) if on else (start, start)


def check_spec(spec, scripts=TEST_SCRIPTS):
    """Validate a timeline spec {"voice": "supervm", "lines": [["td_01", 0.6], ...], "sfx": [[kind, t]], "tail": s,
    "dur": s}; raises TimelineError listing every problem. Returns (voice_dir, rows, starts, spans)."""
    bad = []
    if not isinstance(spec, dict):
        raise TimelineError("the timeline must be a JSON object {\"voice\": ..., \"lines\": [[key, start_s], ...]}")
    voice = spec.get("voice", "supervm")
    voice_dir = os.path.join(REPO, "web", "public", "voice", str(voice))
    if not os.path.isdir(voice_dir):
        bad.append(f"voice {voice!r}: no folder {voice_dir}")
    items = spec.get("lines")
    if not isinstance(items, list) or not items:
        raise TimelineError("\"lines\" must be a non-empty list of [line key, start in seconds]")
    rows, starts, spans, seen = [], [], [], set()
    for n, it in enumerate(items):
        if not (isinstance(it, (list, tuple)) and len(it) == 2 and isinstance(it[0], str)
                and isinstance(it[1], (int, float)) and not isinstance(it[1], bool)):
            bad.append(f"lines[{n}] = {it!r}: expected [\"td_01\", 0.6] (line key, start second)")
            continue
        key, st = it
        if st < 0:
            bad.append(f"{key}: start {st} s is negative")
        if key in seen:
            bad.append(f"{key}: used twice (each line plays once)")
        seen.add(key)
        mp3, js = os.path.join(voice_dir, key + ".mp3"), os.path.join(voice_dir, key + ".json")
        if not (os.path.exists(mp3) and os.path.exists(js)):
            bad.append(f"{key}: no voice line {key}.mp3 / {key}.json in {voice_dir}")
            continue
        data = json.load(open(js, encoding="utf-8"))
        text = line_text(key, scripts)
        rows.append({"key": key, "text": data["text"] if text is None else text})   # no tags known: plain text
        starts.append(float(st))
        v0, v1 = voiced_span(float(st), data["env"])
        spans.append((key, v0, min(v1, float(st) + data["dur"]), float(st) + data["dur"]))
    for kind_t in spec.get("sfx", []):
        if not (isinstance(kind_t, (list, tuple)) and len(kind_t) == 2 and kind_t[0] in SFX_KINDS):
            bad.append(f"sfx {kind_t!r}: expected [kind, second] with kind in {SFX_KINDS}")
    order = sorted(spans, key=lambda s: s[1])
    for a, b in zip(order, order[1:]):
        if b[1] < a[2] + MIN_GAP:
            bad.append(f"{a[0]} and {b[0]} overlap: {a[0]} sounds until {a[2]:.2f} s and {b[0]} starts sounding at "
                       f"{b[1]:.2f} s (leave at least {MIN_GAP} s between lines)")
    if bad:
        raise TimelineError("timeline problems:\n  - " + "\n  - ".join(bad))
    return voice_dir, rows, starts, spans


def timeline_from_spec(spec, key, meta=None, scripts=TEST_SCRIPTS):
    """tl of a performance test: the same dict as timeline() builds for the scenes. `meta` is the
    module's META: title, solo, camera cues [[t, shot], ...] and the public path of the audio."""
    meta = meta or {}
    voice_dir, rows, starts, _ = check_spec(spec, scripts)
    cams = [[float(t), s] for t, s in meta.get("camera", [[0.0, "medium"]])]
    for t, s in cams:
        if s not in SHOTS:
            raise TimelineError(f"camera cue [{t}, {s!r}]: shot must be one of {SHOTS}")
    info = {"title": meta.get("title", key), "solo": bool(meta.get("solo", False))}
    extra = {"voice": spec.get("voice", "supervm")}
    if meta.get("audio"):
        extra["audio"] = meta["audio"]
    return build_timeline(key, rows, starts, [list(x) for x in spec.get("sfx", [])], cams, info,
                          float(spec.get("tail", 1.2)), voice_dir, float(spec.get("dur", 0.0)), extra)


def timeline_from_file(path, meta=None, key=None):
    """Read a timeline JSON (the compose_audio.py input) and build its tl. `key`: the performance id."""
    spec = json.load(open(path, encoding="utf-8"))
    return timeline_from_spec(spec, key or os.path.splitext(os.path.basename(path))[0], meta)


class Words:
    """W(i, "word") -> start (s) of a word of line i (0-based index, or its key: W("td_05", "hola"));
    W.end(i, "word"); W.line(i)."""

    def __init__(self, tl):
        self.tl = tl

    def _line(self, i):
        if isinstance(i, str):
            hits = [ln for ln in self.tl["lines"] if ln["key"] == i]
            if not hits:
                raise KeyError(f"line {i!r} is not in this timeline: {[ln['key'] for ln in self.tl['lines']]}")
            return hits[0]
        return self.tl["lines"][i]

    def _hit(self, i, word, k):
        ln = self._line(i)
        hits = [w for w in ln["words"] if w["w"].lower().strip("¿?¡!.,:;").startswith(word.lower())]
        if not hits:
            raise KeyError(f"{word!r} not in line {i}: {ln['text']}")
        return hits[k]

    def __call__(self, i, word, k=0):
        return self._hit(i, word, k)["start"]

    def end(self, i, word, k=0):
        return self._hit(i, word, k)["end"]

    def line(self, i):
        return self._line(i)["speech"]

    def sound(self, kind, k=0):
        hits = [s for s in self.tl["sounds"] if s["kind"] == kind]
        return hits[k]["t0"], hits[k]["t1"]


def meta(tl):
    """JSON stored on the baked action (and next to the audio) for the export and the web player."""
    info = tl["info"]
    return {"key": tl["key"], "title": info["title"], "solo": bool(info["solo"]),
            "audio": tl.get("audio", f"voice/scenes/{tl['key']}.mp3"),
            "align": tl.get("align", f"voice/scenes/{tl['key']}.json"),
            "voice": tl.get("voice", "supervm"), "fps": FPS, "frames": tl["frames"], "dur": tl["dur"],
            "camera": tl["cams"],
            "lines": [{"key": ln["key"], "text": ln["text"], "start": ln["start"],
                       "t0": ln["speech"][0], "t1": ln["speech"][1]} for ln in tl["lines"]]}


def merged_alignment(tl, env):
    """One alignment for the whole scene (line offsets applied), env = voice envelope per 1/30 s."""
    chars, t0, t1 = "", [], []
    for ln in tl["lines"]:
        if chars:
            last = t1[-1] if t1 else 0.0
            chars += " "
            t0.append(round(last, 3))
            t1.append(round(max(last, ln["start"] + (ln["t0"][0] if ln["t0"] else 0.0)), 3))
        chars += ln["chars"]
        t0 += [round(ln["start"] + v, 3) for v in ln["t0"]]
        t1 += [round(ln["start"] + v, 3) for v in ln["t1"]]
    m = meta(tl)
    m.update({"text": " ".join(ln["text"] for ln in tl["lines"]), "chars": chars, "t0": t0, "t1": t1,
              "env": [round(float(v), 3) for v in env], "sounds": tl["sounds"]})
    return m


# ================================================================ performance helpers
def speak(p, tl, lead=0.05):
    """Lip-sync from the voice (as Performance.speak) with what the scenes need on top: the mouth
    rests between words instead of hanging half open through a pause, whispers stay small,
    and the tagged sounds move the face too (a laugh opens it in bursts, a gasp is a quick 'o')."""
    n, fps = p.n, p.fps
    t = np.arange(n) / fps
    open_, round_, smile = np.zeros(n), np.zeros(n), np.zeros(n)
    talking, gain = np.zeros(n), np.ones(n)
    extra, extra_round = np.zeros(n), np.zeros(n)
    for ln in tl["lines"]:
        st = ln["start"]
        k = 0.55 if "whisper" in ln["tags"] else 1.0
        for ch, a0, a1 in zip(ln["chars"], ln["t0"], ln["t1"]):
            c = ch.lower()
            a, b = st + a0 - lead, st + a1 - lead
            m = (t >= a) & (t < max(b, a + 1.0 / fps))
            if c in VOWEL:
                o, r, s = VOWEL[c]
                open_[m] = np.maximum(open_[m], o * k)
                round_[m] = np.maximum(round_[m], r)
                smile[m] = s
            elif c in CLOSED:
                open_[m] = np.minimum(open_[m], -0.35)
            elif c in NARROW:
                open_[m] = np.minimum(open_[m], 0.12)
        for w in ln["words"]:
            a, b = p.f(w["start"] - lead - 0.05), p.f(w["end"] + 0.06)
            talking[max(0, a):min(n, b + 1)] = 1.0
        env = np.nan_to_num(np.asarray(ln["env"], float))
        f0 = p.f(st - lead)
        idx = np.arange(len(env)) + f0
        ok = (idx >= 0) & (idx < n)
        gain[idx[ok]] = np.clip(0.30 + 0.85 * env[ok], 0.25, 1.25) * k
        end = p.f(ln["speech"][1]) + 3                  # a blink in the pause after a line
        if end < n:
            p.blinks.append(end)
    for snd in tl["sounds"]:
        a, b = p.f(snd["t0"] - lead), p.f(snd["t1"])
        if snd["kind"] == "laugh":                      # 'ja-ja': the mouth follows the bursts
            ln = tl["lines"][snd["line"]]
            env = np.asarray(ln["env"], float)
            for f in range(max(0, a), min(n, b + 2)):
                i = f - p.f(ln["start"] - lead)
                if 0 <= i < len(env):
                    extra[f] = max(extra[f], -0.1 + 0.9 * env[i])
        elif snd["kind"] == "gasp":                     # a quick intake: an 'o'
            seg = _bump(n, a, max(a + 3, b), 3, 6)
            extra = np.maximum(extra, 0.55 * seg)
            extra_round = np.maximum(extra_round, 0.8 * seg)
    target = np.where(talking > 0, TALK_BASE + 1.15 * np.clip(open_ * gain, -0.5, 1.0), 0.0)
    target = np.maximum(target, extra)
    p.talk_mask = np.clip(C.spring(talking, freq=4.0, damping=0.9, fps=fps), 0, 1)
    p.c.prop("mouth_open", C.spring(target, freq=9.0, damping=0.62, fps=fps))
    rnd = np.maximum(round_ * (talking > 0), extra_round)
    p.c.prop("mouth_round", np.clip(C.spring(rnd, freq=8.0, damping=0.7, fps=fps), 0, 1))
    p.c.prop("smile", 0.25 * C.spring(smile, freq=6.0, damping=0.8, fps=fps))
    # the head and brows talk too: nods on stressed words, brows up on questions and emphasis
    rng = np.random.default_rng(p.seed)
    nod, brow = np.zeros(n), np.zeros(n)
    for ln in tl["lines"]:
        k = 0.5 if "whisper" in ln["tags"] else 1.0
        for ws in ln["stress"]:
            f0 = p.f(ln["start"] + ws)
            if 0 <= f0 < n:
                nod[f0] += rng.uniform(1.6, 2.8) * k
                brow[f0] += rng.uniform(0.25, 0.45)
        if ln["question"]:
            a, b = p.f(ln["speech"][0]), p.f(ln["speech"][1])
            brow[a:b] += 0.03
    p.speak_nod = C.spring(nod, freq=4.0, damping=0.45, fps=fps) * 2.2
    p.c.add("head.rx", p.speak_nod)
    br = np.clip(C.spring(brow, freq=4.5, damping=0.55, fps=fps) * 2.4, -0.2, 0.8)
    p.c.prop("brow_L", br)
    p.c.prop("brow_R", br * 0.9)


def _bump(n, a, b, rise, fall):
    """0 -> 1 from a - rise to a, held to b, back to 0 by b + fall (frames)."""
    return C.keys(n, [(a - rise - 1, 0.0), (a - rise, 0.0), (a, 1.0), (b, 1.0), (b + fall, 0.0),
                      (b + fall + 1, 0.0)])


def _look_angles(point):
    from .motor import EYES
    d = np.asarray(point, float) - EYES
    # something low and close (in his hands) is mostly a look down: with his big head the turn
    # would otherwise swing half round towards it
    fwd = max(-d[1], (0.8 if d[2] < 0 else 0.3) * abs(d[2]), 0.05)
    yaw = float(np.clip(np.degrees(np.arctan2(d[0], fwd)), -62, 62))
    pitch = float(np.degrees(np.arctan2(d[2], np.hypot(d[0], d[1]))))
    return yaw, pitch


def look(p, keys, head=0.48, neck=0.14, max_nod=6.0, lag=4):
    """Head and eyes towards points, with the eyes LEADING: they reach the new target first and
    the head follows `lag` frames later (the eyes give back what the head takes), plus a blink on
    big turns. keys: [(frame, point | None[, head weight])]: a weight < 1 keeps the head steadier
    and lets the eyes do more of the looking (a finger resting on the chin must not lose it)."""
    from .motor import GAZE_RANGE
    n = p.n
    keys = sorted(keys, key=lambda k: k[0])
    rows = [(k[0],) + ((0.0, 0.0) if k[1] is None else _look_angles(k[1])) for k in keys]
    hw = C.keys(n, [(k[0], k[2] if len(k) > 2 else 1.0) for k in keys])
    yaw = C.keys(n, [(f, y) for f, y, _ in rows])
    pitch = C.keys(n, [(f, q) for f, _, q in rows])
    nod = np.clip(-pitch * (head + neck), -max_nod, max_nod) * hw
    hy, hn = C.delay(yaw * hw, lag), C.delay(nod, lag)
    p.c.add("head.rz", hy * head)
    p.c.add("neck.rz", hy * neck)
    p.c.add("head.rx", hn * head / (head + neck))
    p.c.add("neck.rx", hn * neck / (head + neck))
    gx = np.clip((yaw - hy * (head + neck)) / GAZE_RANGE[0], -1, 1)
    gy = np.clip((pitch + hn) / GAZE_RANGE[1], -1, 1)
    p.c.prop("gaze_x", C.spring(gx, freq=7.0, damping=0.75, fps=p.fps))
    p.c.prop("gaze_y", C.spring(gy, freq=7.0, damping=0.75, fps=p.fps))
    for (f0, y0, _), (f1, y1, _) in zip(rows, rows[1:]):
        if abs(y1 - y0) > 25 and f1 - f0 < 20:
            p.blinks.append(max(0, f0))


HIGH = {"R": (-0.30, -0.07, 0.46), "L": (0.30, -0.07, 0.46)}   # a hand up beside the face (clear of it)
UP = {"R": (-0.10, -0.15, 1.0), "L": (0.10, -0.15, 1.0)}        # fingers up, forearm under them
FRONT = (0.0, -1.0, 0.12)                                       # palm to the viewer
SX = {"L": 1.0, "R": -1.0}


class Scene:
    """Bookkeeping for one scene: the Performance and the per-hand / face / look key lists, in
    seconds, applied once at the end (Clip channels add up)."""

    def __init__(self, tl, seed, prop_loc=(0, 0, 0), prop_rot=(0, 0, 0)):
        self.tl, self.W = tl, Words(tl)
        self.p = Performance(tl["frames"], seed=seed, prop_loc=prop_loc, prop_rot=prop_rot)
        self.c, self.n, self.F = self.p.c, self.p.n, self.p.f
        self.a = Acting(self.p)
        self.t = np.arange(self.n) / FPS
        self.hands = {"L": [(0, "relaxed")], "R": [(0, "relaxed")]}
        self.reaches = {"L": [(0, None, 0.0)], "R": [(0, None, 0.0)]}
        self.orients = {"L": [], "R": []}
        self.looks, self.exprs, self.busy, self.poles = [], [], [], []
        self.windows = {"L": [], "R": []}
        self.steadies = []
        self.energy = 1.0
        speak(self.p, tl)

    # ------------------------------------------------------------ keys in seconds
    def k(self, pts):
        """Second keys -> frame keys; two keys rounding to one frame keep the later (curves.keys
        gives NaN on a repeated frame)."""
        return _dedup_keys([(self.F(t), v) for t, v in pts])

    def add(self, ch, pts):
        self.c.add(ch, self.k(pts))

    def hand(self, side, pts):
        self.hands[side] += [(self.F(t), s) for t, s in pts]

    def expr(self, pts):
        self.exprs += [(self.F(r[0]),) + tuple(r[1:]) for r in pts]

    def look(self, pts):
        self.looks += [(self.F(r[0]), CAM if (isinstance(r[1], str) and r[1] == "cam") else r[1]) + tuple(r[2:])
                       for r in pts]

    def steady(self, t0, t1, keep=0.25):
        """Head still from t0 to t1: the talking nods shrink to `keep` (a hand resting on the face)."""
        self.steadies.append((t0, t1, keep))

    def env(self, t0, t1, rise=0.12, fall=0.12):
        return C.keys(self.n, _dedup_keys(self.k([(t0 - rise, 0.0), (t0, 1.0), (t1, 1.0), (t1 + fall, 0.0)])))

    def ik(self, side, t0, t1, point, fingers, palm, ramp=0.32, pole=None):
        """Wrist on IK at `point` from t0 to t1 (eased in / out over `ramp`), hand oriented."""
        self.reaches[side] += [(self.F(t0 - ramp), None, 0.0), (self.F(t0), point, 1.0), (self.F(t1), point, 1.0),
                               (self.F(t1 + ramp), None, 0.0)]
        self.orients[side] += [(self.F(t0 - ramp), fingers, palm), (self.F(t1 + ramp), fingers, palm)]
        self.windows[side].append((t0 - ramp, t1 + ramp))
        if pole is not None:
            self.poles.append((side, t0 - ramp, t1 + ramp) + tuple(pole))

    # ------------------------------------------------------------ gestures
    def wave(self, side, t0, t1, period=0.4, lean=1.0, ramp=0.25):
        """Hand up beside his face, palm to the viewer, waving: on IK (his head is wider than his
        reach: an FK wave puts the hand into it), the hand wagging and the wrist swinging with it,
        the head tilting away from it."""
        sg = SX[side]
        self.ik(side, t0, t1, (0.305 * sg, -0.085, 0.47), UP[side], FRONT, ramp=ramp, pole=(0.06 * sg, -0.24))
        w = np.sin(2 * np.pi * (self.t - t0) / period) * self.env(t0 + 0.05, t1 - 0.1, 0.1, 0.12)
        self.c.add(f"hand_ik.{side}.ry", C.delay(-24.0 * sg * w, 2))
        self.c.add(f"hand_ik.{side}.lx", 0.010 * sg * w)
        self.c.shrug(side, self.k([(t0 - ramp, 0), (t0, 6), (t1, 5), (t1 + ramp, 0)]))
        self.add("chest.ry", [(t0 - 0.2, 0), (t0 + 0.05, -4 * sg * lean), (t1 - 0.2, -3 * sg * lean), (t1 + 0.05, 0)])
        self.add("head.ry", [(t0 - 0.1, 0), (t0 + 0.1, -6 * sg * lean), (t1 - 0.2, -4 * sg * lean), (t1 + 0.05, 0)])
        self.hand(side, [(t0 - ramp, "open"), (t1, "open"), (t1 + ramp, "relaxed")])

    def high(self, side, t0, t1, beats=(), shapes=()):
        """Hand up beside his face, forearm raised (counting, 'one moment'); beats lift it."""
        sg = SX[side]
        self.ik(side, t0, t1, HIGH[side], UP[side], FRONT, pole=(0.06 * sg, -0.24))
        self.c.shrug(side, self.k([(t0 - 0.3, 0), (t0, 5), (t1, 5), (t1 + 0.3, 0)]))
        lift = np.zeros(self.n)
        for tb in beats:
            lift += 0.016 * np.exp(-((np.arange(self.n) - self.F(tb) - 2) / 3.5) ** 2)
        self.c.add(f"hand_ik.{side}.lz", lift)
        self.hand(side, [(t0 - 0.3, "relaxed")] + list(shapes) + [(t1 + 0.3, "relaxed")])

    def belly(self, side, t0, t1, ramp=0.35):
        """Palm resting on his belly (a real touch: anim/contacts.py puts it on the skin)."""
        sg = SX[side]
        self.ik(side, t0, t1, (0.15 * sg, -0.12, 0.31), (-0.5 * sg, -0.2, 0.25), (-0.3 * sg, 0.9, 0.0), ramp=ramp)
        self.p.contacts.append({"side": side, "touch": "torso", "point": (0.12 * sg, -0.085, 0.30),
                                "frames": (self.F(t0 + 0.1), self.F(t1 - 0.05)), "ramp": 10,
                                "region": [f"hand.{side}", f"index.01.{side}", f"middle.01.{side}",
                                           f"ring.01.{side}"]})
        self.add(f"shoulder.{side}.rz", [(t0 - ramp + 0.1, 0), (t0, -15 * sg), (t1, -15 * sg), (t1 + ramp, 0)])
        self.hand(side, [(t0 - 0.2, exact("hold_flat")), (t1, exact("hold_flat")), (t1 + ramp, "relaxed")])

    def cheeks(self, t0, t1, ramp=0.3):
        """Both palms on his cheeks ('¡no puede ser!')."""
        for side in ("L", "R"):
            sg = SX[side]
            self.ik(side, t0, t1, (0.24 * sg, -0.14, 0.52), (0.32 * sg, -0.43, 0.84), (-0.5 * sg, 0.67, 0.55),
                    ramp=ramp)
            self.p.contacts.append({"side": side, "touch": "head", "point": (0.212 * sg, -0.138, 0.582),
                                    "frames": (self.F(t0 + 0.12), self.F(t1 - 0.05)), "ramp": 6,
                                    "region": [f"hand.{side}", f"index.01.{side}", f"middle.01.{side}"]})
            self.add(f"shoulder.{side}.rz", [(t0 - ramp, 0), (t0, -24 * sg), (t1, -24 * sg), (t1 + ramp, 0)])
            self.c.shrug(side, self.k([(t0 - ramp, 0), (t0 + 0.1, 10), (t1, 8), (t1 + ramp, 0)]))
            self.hand(side, [(t0 - ramp, "relaxed"), (t0, "open"), (t1, "open"), (t1 + ramp + 0.05, "relaxed")])

    def chin(self, t0, t1, taps=(), ramp=0.4):
        """Right index resting on the front of his chin (thinking: the arm stretches a little to get
        there); `taps` lift it for a tap at those times. The hand comes up in front of the chest."""
        wrist, fingers, palm = (-0.06, -0.16, 0.44), (0.12, -0.15, 1.0), (0.35, 0.9, 0.1)
        self.reaches["R"] += [(self.F(t0 - ramp), None, 0.0), (self.F(t0 - 0.16), (-0.17, -0.21, 0.37), 1.0),
                              (self.F(t0), wrist, 1.0), (self.F(t1), wrist, 1.0), (self.F(t1 + ramp), None, 0.0)]
        self.orients["R"] += [(self.F(t0 - ramp), fingers, palm), (self.F(t1 + ramp), fingers, palm)]
        self.windows["R"].append((t0 - ramp, t1 + ramp))
        spans, a = [], t0 + 0.12
        for tt in taps:                               # a tap: lifts off ~0.27 s (hover 1.5 cm) and back
            spans.append((a, tt - 0.15))
            a = tt + 0.12
        spans.append((a, t1 - 0.05))
        for a, b in spans:
            if b - a > 0.15:
                self.p.contacts.append({"side": "R", "touch": "head", "point": (-0.03, -0.15, 0.53),
                                        "frames": (self.F(a), self.F(b)), "ramp": 3,
                                        "region": ["index.02.R", "index.03.R"]})
        self.add("shoulder.R.rz", [(t0 - ramp, 0), (t0, 26), (t1, 26), (t1 + ramp, 0)])
        self.c.shrug("R", self.k([(t0 - ramp, 0), (t0, 8), (t1, 8), (t1 + ramp, 0)]))
        self.hand("R", [(t0 - ramp, "relaxed"), (t0 - 0.15, exact("point")), (t1, exact("point")), (t1 + ramp, "relaxed")])

    def present(self, side, t0, t1, raise_=40.0, swing=34.0, palm=-55.0):
        """Arm out to his side, palm up: 'look at this'."""
        c, k = self.c, self.k
        c.arm_raise(side, k([(t0 - 0.3, 0), (t0 - 0.22, -3), (t0, raise_), (t0 + 0.15, raise_ * 0.9),
                             (t1 - 0.25, raise_ * 0.9), (t1, 0)]))
        c.arm_swing(side, k([(t0 - 0.28, 0), (t0, swing), (t1 - 0.25, swing), (t1, 0)]))
        c.elbow(side, k([(t0 - 0.25, 0), (t0, 26), (t0 + 0.15, 18), (t1 - 0.25, 18), (t1, 0)]))
        c.palm(side, k([(t0 - 0.25, 0), (t0, palm), (t1 - 0.25, palm), (t1, 0)]))
        c.wrist(side, flex=k([(t0 - 0.2, 0), (t0 + 0.1, -14), (t1 - 0.25, -14), (t1, 0)]))
        self.hand(side, [(t0 - 0.2, "relaxed"), (t0, "open"), (t1 - 0.2, "open"), (t1 + 0.05, "relaxed")])

    def open_arms(self, t0, t1, raise_=24.0, elbow=50.0, palm=-75.0, sides=("L", "R")):
        """Both forearms up and open, palms up ('here I am', 'welcome')."""
        c, k = self.c, self.k
        for side in sides:
            c.arm_raise(side, k([(t0 - 0.3, 0), (t0, raise_), (t1 - 0.25, raise_ * 0.92), (t1, 0)]))
            c.elbow(side, k([(t0 - 0.3, 0), (t0, elbow), (t1 - 0.25, elbow * 0.96), (t1, 0)]))
            c.palm(side, k([(t0 - 0.3, 0), (t0, palm), (t1 - 0.25, palm * 0.94), (t1, 0)]))
            self.hand(side, [(t0 - 0.2, "relaxed"), (t0, "open"), (t1 - 0.2, "open"), (t1 + 0.05, "relaxed")])

    def arms_up(self, t0, t1, shape="open", raise_=58.0, lift=40.0, sides=("L", "R")):
        """Both arms thrown up in a V (celebration, a big stretch, a fright)."""
        c, k = self.c, self.k
        for side in sides:
            c.arm_raise(side, k([(t0 - 0.3, 0), (t0 - 0.2, -6), (t0, raise_), (t0 + 0.1, raise_ * 1.03),
                                 (t1 - 0.3, raise_ * 0.95), (t1, 0)]))
            c.arm_swing(side, k([(t0 - 0.3, 0), (t0, 4), (t1 - 0.3, 4), (t1, 0)]))
            c.forearm_lift(side, k([(t0 - 0.25, 0), (t0, lift), (t1 - 0.3, lift * 0.95), (t1, 0)]))
            self.hand(side, [(t0 - 0.25, "relaxed"), (t0 - 0.05, shape), (t1 - 0.25, shape), (t1 + 0.05, "relaxed")])

    def fist_pump(self, side, t, hold=0.45):
        """The fist punches up beside his face (IK, clear of the head) and bounces."""
        sg = SX[side]
        self.ik(side, t + 0.02, t + hold, (0.29 * sg, -0.09, 0.465), UP[side], (-sg, -0.3, 0.0), ramp=0.16,
                pole=(0.06 * sg, -0.24))
        bump = np.exp(-((self.t - t - 0.08) / 0.07) ** 2) - 0.4 * np.exp(-((self.t - t - 0.25) / 0.08) ** 2)
        self.c.add(f"hand_ik.{side}.lz", 0.018 * bump)
        self.c.shrug(side, self.k([(t - 0.15, 0), (t + 0.05, 7), (t + hold, 5), (t + hold + 0.2, 0)]))
        self.hand(side, [(t - 0.16, "fist"), (t + hold + 0.05, "fist"), (t + hold + 0.25, "relaxed")])

    def laugh(self, t0, t1, amp=1.0, rate=4.0):
        """'Ja, ja, ja': knees, chest, shoulders and head bounce with the laugh."""
        ha = np.maximum(0, np.sin(2 * np.pi * rate * (self.t - t0))) * self.env(t0, t1, 0.1, 0.25) * amp
        back = C.keys(self.n, self.k([(t0 - 0.2, 0), (t0 + 0.15, -8), (t1 - 0.1, -6), (t1 + 0.35, 0)])) * amp
        self.c.add("hips.lz", -0.007 * ha)
        self.c.add("chest.rx", -2.6 * ha)
        self.c.add("head.rx", C.delay(-5.0 * ha, 1) + back)
        self.c.add("head.rz", C.delay(3.0 * ha, 2) * np.sin(2 * np.pi * (self.t - t0) / 1.3))
        for side in ("L", "R"):
            self.c.shrug(side, 4.0 * ha)

    def shake(self, t0, t1, amp=12.0, rate=3.2):
        """Head shake ('no'): turns that decay, the eyes counter a little, the chest follows."""
        env = self.env(t0, t1 - 0.15, 0.08, 0.2)
        decay = np.clip(1.0 - (self.t - t0) / max(t1 - t0, 0.1) * 0.5, 0.4, 1.0)
        s = np.sin(2 * np.pi * rate * (self.t - t0)) * env * decay * amp
        self.c.add("head.rz", s)
        self.c.add("chest.rz", C.delay(0.15 * s, 3))
        self.c.prop("gaze_x", -0.012 * s)

    def tremble(self, t0, t1, amp=1.0, seed=5):
        env = self.env(t0, t1, 0.1, 0.3) * amp
        tr = C.noise(self.n, 3, 1.0, seed=seed, loop=False) * env
        self.c.add("head.rz", 1.6 * tr)
        self.c.add("hips.lx", 0.002 * tr)
        for side in ("L", "R"):
            self.c.add(f"hand_ik.{side}.lz", 0.003 * tr)
            self.c.add(f"forearm.{side}.rx", 1.5 * tr)

    def temple(self, t0, t1, taps=(), ramp=0.32):
        """Right index on the side of his head ('¡soy un genio!'): a touch that lifts for each tap."""
        self.ik("R", t0, t1, (-0.315, -0.07, 0.50), (0.35, -0.15, 1.0), (0.9, 0.25, -0.2), ramp=ramp,
                pole=(-0.06, -0.24))
        spans, a = [], t0 + 0.08
        for tt in taps:
            spans.append((a, tt - 0.15))
            a = tt + 0.12
        spans.append((a, t1 - 0.05))
        for a, b in spans:
            if b - a > 0.12:
                self.p.contacts.append({"side": "R", "touch": "head", "point": (-0.255, -0.08, 0.60),
                                        "frames": (self.F(a), self.F(b)), "ramp": 3,
                                        "region": ["index.02.R", "index.03.R"]})
        self.c.shrug("R", self.k([(t0 - ramp, 0), (t0, 8), (t1, 8), (t1 + ramp, 0)]))
        self.hand("R", [(t0 - ramp, "relaxed"), (t0 - 0.12, exact("point")), (t1, exact("point")), (t1 + ramp, "relaxed")])

    def fan(self, side, t0, t1, ramp=0.22):
        """Fans his face with an open hand ('¡qué calor, qué día!'), the palm towards it (IK)."""
        sg = SX[side]
        self.ik(side, t0, t1, (0.30 * sg, -0.13, 0.465), UP[side], (-0.75 * sg, -0.4, 0.3), ramp=ramp,
                pole=(0.06 * sg, -0.24))
        w = np.sin(2 * np.pi * 5.0 * (self.t - t0)) * self.env(t0 + 0.05, t1 - 0.1, 0.08, 0.1)
        self.c.add(f"hand_ik.{side}.rz", C.delay(26.0 * sg * w, 1))
        self.hand(side, [(t0 - ramp, "open"), (t1, "open"), (t1 + ramp, "relaxed")])

    def dance(self, t0, t1, beat=0.5):
        """Step-touch to each side on the beat, hips and head bouncing, arms pumping (FK)."""
        c, a, n = self.c, self.a, self.n
        env = self.env(t0 + 0.25, t1 - 0.1, 0.25, 0.3)
        ph = (self.t - t0) / beat
        hit = np.zeros(n)
        for tb in np.arange(t0 + beat * 0.5, t1, beat):          # knees on every beat: fast down, slow up
            hit += np.exp(-((self.t - tb - 0.03) / 0.07) ** 2)
        c.add("hips.lz", -0.014 * C.spring(hit, freq=5.0, damping=0.6, fps=FPS) * env)
        c.add("head.rx", 3.0 * C.delay(hit, 2) * env)
        a.shimmy(t0 + 0.2, t1, freq=1.0 / (2 * beat), amp=0.9)
        side = "L"
        for i, tb in enumerate(np.arange(t0 + beat * 0.5, t1 - beat, 2 * beat)):
            sx = 0.05 * SX[side]
            a.step(side, tb - 0.12, dx=sx, dy=0.0, dur=0.24, height=0.02, settle=False)
            a.step(side, tb + beat - 0.12, dx=-sx, dy=0.0, dur=0.24, height=0.02, settle=False)
            side = "R" if side == "L" else "L"
        for s_, phs in (("L", 0.0), ("R", 0.5)):
            pump = np.sin(2 * np.pi * (ph / 2 + phs)) * env
            c.elbow(s_, 64 * env)
            c.arm_raise(s_, (16 + 10 * pump) * env)
            c.arm_fwd(s_, 14 * pump)
            c.forearm_lift(s_, C.delay(10 * pump, 2))
        self.hand("L", [(t0, "fist"), (t1, "fist")])
        self.hand("R", [(t0, "fist"), (t1, "fist")])
        self.c.add("chest.rz", -6.0 * np.sin(np.pi * ph) * env)

    def lean(self, t0, t1, t2, amount, counter=0.85):
        """Lean in (+) or back (-) from t0 (reached at t1, held to t2), the head counter-turning so
        the eyes stay on what he is looking at."""
        keys = [(t0, 0), (t1, 1.0), (t2, 1.0), (t2 + 0.35, 0)]
        self.add("spine.rx", [(t, v * amount * 0.45) for t, v in keys])
        self.add("chest.rx", [(t, v * amount * 0.55) for t, v in keys])
        self.add("head.rx", [(t, -v * amount * counter) for t, v in keys])

    def crouch(self, t0, t1, depth=0.03, lean=-4.0, ramp=0.25):
        self.add("hips.lz", [(t0 - ramp, 0), (t0, -depth), (t1, -depth), (t1 + ramp, 0)])
        self.add("spine.rx", [(t0 - ramp, 0), (t0, lean), (t1, lean), (t1 + ramp, 0)])

    # ------------------------------------------------------------ finish
    def finish(self):
        p, c = self.p, self.c
        for side, ws in self.windows.items():           # one IK pose at a time per hand
            ws = sorted(ws)
            for (a0, a1), (b0, b1) in zip(ws, ws[1:]):
                if b0 < a1 - 0.02:
                    raise ValueError(f"{self.tl['key']}: IK windows of hand {side} overlap: "
                                     f"{a0:.2f}-{a1:.2f} and {b0:.2f}-{b1:.2f}")
        for side, t0, t1, lx, lz in self.poles:
            c.add(f"elbow_pole.{side}.lx", self.k([(t0, 0), (t0 + 0.3, lx), (t1 - 0.3, lx), (t1, 0)]))
            c.add(f"elbow_pole.{side}.lz", self.k([(t0, 0), (t0 + 0.3, lz), (t1 - 0.3, lz), (t1, 0)]))
        for side in ("L", "R"):
            p.reach(side, _dedup_keys(self.reaches[side]))
            if self.orients[side]:
                p.orient(side, _dedup_keys(self.orients[side]))
            p.hand(side, _dedup_keys(self.hands[side]))
        # expressions: while he talks their mouth shape gives way to the words (a 'thinking' mouth
        # pressed shut, or a 'joy' mouth held open, would swallow the lip-sync)
        tmp = Clip(self.n)
        tmp.expr(_dedup_keys(self.exprs))
        talk = getattr(p, "talk_mask", np.zeros(self.n))
        for k, v in tmp.ch.items():
            if k == "prop.mouth_open":
                v = v * (1.0 - 0.75 * talk)
            elif k == "prop.mouth_round":
                v = v * (1.0 - 0.6 * talk)
            c.add(k, v)
        if self.looks:
            look(p, _dedup_keys(self.looks))
        for t0, t1, keep in self.steadies:
            c.add("head.rx", -(1.0 - keep) * self.env(t0, t1, 0.2, 0.2) * p.speak_nod)
            self.busy.append((t0, t1))
        self.a.talk(self.tl["lines"], energy=self.energy, skip=self.busy)
        self.a.finish()
        return p


def _dedup_keys(keys):
    """Sorted by frame; of two keys on the same frame the later one in the list wins."""
    out = {}
    for k in keys:
        out[k[0]] = k
    return [out[f] for f in sorted(out)]


def finish(p):
    """Performance -> Clip, with the face kept in the ranges the web viewer can show (Blender would
    draw a mouth_open of 1.8 bigger than designed; the web clamps it)."""
    clip = p.build(sway=getattr(p, "life_sway", 1.0))
    lim = {"mouth_open": (-1.0, 1.1), "smile": (-1.0, 1.05), "mouth_round": (0.0, 1.0), "teeth": (0.0, 1.0),
           "blink_L": (0.0, 1.0), "blink_R": (0.0, 1.0), "gaze_x": (-1.0, 1.0), "gaze_y": (-1.0, 1.0),
           "brow_L": (-1.0, 1.0), "brow_R": (-1.0, 1.0), "brow_in_L": (-1.0, 1.0), "brow_in_R": (-1.0, 1.0),
           "squint": (0.0, 1.0), "lid_drop": (0.0, 1.0), "lid_angle": (-1.0, 1.0), "pupil": (-1.0, 1.0),
           "eye_calm": (0.0, 1.0), "mouth_side": (-1.0, 1.0)}
    for k, (lo, hi) in lim.items():
        if f"prop.{k}" in clip.ch:
            clip.ch[f"prop.{k}"] = np.clip(clip.ch[f"prop.{k}"], lo, hi)
    clip.max_reach = getattr(p, "max_reach", None)
    # a hand resting on his skin keeps its wrist still: the wrist's follow-through would tilt the palm
    # off the skin (a few mm), so it fades out over each touch and back in after it
    for c in p.contacts:
        if "touch" not in c:
            continue
        f0, f1 = c["frames"]
        r = int(c.get("ramp", 6))
        w = np.clip(np.minimum((np.arange(clip.n) - (f0 - r)) / max(r, 1), ((f1 + r) - np.arange(clip.n)) / max(r, 1)),
                    0.0, 1.0)
        for ax in ("rx", "ry", "rz"):
            key = f"hand.{c['side']}.{ax}"
            if key in clip.ch:
                clip.ch[key] = clip.ch[key] * (1.0 - w)
    return clip


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


# ================================================================ the scenes
UP_L, UP_R = (0.35, -1.0, 1.35), (-0.35, -1.0, 1.35)          # up to his left / right (thinking)
FLOOR_L, FLOOR_R = (0.75, -0.65, 0.0), (-0.75, -0.65, 0.0)     # the floor beside him
FAR_L, FAR_R = (2.0, -1.7, 0.75), (-2.0, -1.7, 0.75)           # far away to each side
DOWN = (0.0, -0.9, 0.05)


def presentacion(tl):
    """To the camera: '¡Hola, hola! ¡Soy Morfi! Soy el ayudante de Morphiq. Te ayudo a vender,
    a cobrar... ¡y a que tu negocio crezca! [ríe] ¿Empezamos?'"""
    s = Scene(tl, seed=401)
    W, a = s.W, s.a
    a.stance(knees=0.008, lean=2.0)
    T = tl["dur"]
    # he turns to us: eyes first, a dip before the hello
    s.look([(0.0, (0.45, -1.4, 0.4)), (0.14, "cam")])
    s.expr([(0.0, "neutral"), (0.18, "happy", 0.7)])
    a.bounce(0.30, depth=0.016, chest=-1.0)
    # ¡Hola, hola!: a hop and a big wave, weight away from the waving arm
    th = W(0, "hola")
    s.wave("R", th - 0.05, W.end(0, "hola", 1), period=0.36)
    a.hop(th - 0.04, height=0.035, crouch=0.02, air=0.26, arms=False)
    a.shift(th - 0.3, +1)
    s.busy.append((th - 0.45, th + 0.55))
    s.expr([(th - 0.15, "joy"), (W(0, "hola", 1) + 0.3, "happy")])
    # ¡Soy Morfi!: the right palm on his belly, chest up, the other hand opens to the side
    ts, tm, te = W(0, "soy"), W(0, "morfi"), W.end(0, "morfi")
    s.belly("R", ts + 0.2, te + 0.2, ramp=0.22)
    s.present("L", tm - 0.08, te + 0.45, raise_=26, swing=18, palm=-50)
    s.add("chest.rx", [(ts - 0.1, 0), (ts + 0.2, -4), (te, -3), (te + 0.4, 0)])
    s.add("head.rx", [(ts - 0.1, 0), (ts + 0.2, -3), (tm + 0.1, 2), (te + 0.4, 0)])
    s.add("head.ry", [(ts, 0), (ts + 0.25, -5), (te, -4), (te + 0.35, 0)])
    a.bounce(tm, depth=0.012)
    a.squash(tm + 0.02, 0.04, "head")
    s.expr([(ts, "happy"), (tm, "joy", 0.85), (te + 0.3, "happy")])
    # Soy el ayudante de Morphiq: a step towards us, both hands open; a proud nod on the name
    t1, ta, tq, tqe = W(1, "soy"), W(1, "ayudante"), W(1, "morphiq"), W.end(1, "morphiq")
    a.step("R", t1 - 0.3, dy=-0.045, dur=0.36)
    s.open_arms(ta - 0.05, tqe + 0.35, raise_=24, elbow=50, palm=-72)
    s.add("head.rx", [(tq - 0.1, 0), (tq + 0.12, 5), (tq + 0.35, -1), (tqe + 0.3, 0)])
    s.add("chest.rx", [(ta - 0.2, 0), (ta + 0.1, 3), (tqe, 2), (tqe + 0.4, 0)])
    s.expr([(t1, "happy"), (tq, "joy", 0.9), (tqe + 0.3, "happy")])
    # Te ayudo a vender, a cobrar...: counts on his fingers beside his face
    tv, tc, tce = W(2, "vender"), W(2, "cobrar"), W.end(2, "cobrar")
    a.beat("L", W(2, "ayudo"), amp=0.9)
    s.high("R", tv - 0.05, tce + 0.25, beats=(tv, tc),
           shapes=[(tv - 0.25, "fist"), (tv, "count1"), (tc - 0.1, "count1"), (tc + 0.02, "count2")])
    s.add("head.ry", [(tv - 0.1, 0), (tv + 0.15, -6), (tc + 0.15, 5), (tce + 0.4, 0)])
    s.add("chest.rx", [(tv - 0.3, 0), (tv, 4), (tce, 4), (tce + 0.4, 0)])
    a.shift(tv - 0.1, +1)
    a.shift(tc - 0.1, -1)
    s.expr([(tv, "happy"), (tv + 0.1, "joy", 0.7), (tc + 0.1, "joy", 0.8)])
    # ¡y a que tu negocio crezca!: gathers low on 'negocio', then grows: a big hop, arms up
    tn, tz, tze = W(2, "negocio"), W(2, "crezca"), W.end(2, "crezca")
    s.crouch(tn + 0.05, tz - 0.12, depth=0.014, lean=3.0, ramp=0.25)
    for side in ("L", "R"):
        s.c.elbow(side, s.k([(tn - 0.1, 0), (tn + 0.2, 40), (tz - 0.12, 46), (tz + 0.05, 0)]))
        s.c.arm_raise(side, s.k([(tn - 0.1, 0), (tn + 0.2, -6), (tz - 0.12, -8), (tz, 0)]))
    s.hand("L", [(tn, "fist"), (tz - 0.15, "fist")])
    s.hand("R", [(tn + 0.1, "fist"), (tz - 0.15, "fist")])
    s.add("head.rx", [(tn, 0), (tn + 0.3, -5), (tz - 0.1, -7), (tz + 0.1, -8), (tze + 0.3, -4), (tze + 0.7, 0)])
    a.squash(tn + 0.35, -0.04, "head", dur=0.4)
    s.arms_up(tz + 0.04, tze + 0.7, shape="open", raise_=58, lift=38)
    a.hop(tz - 0.06, height=0.075, crouch=0.024, air=0.40, arms=False)
    a.squash(tz + 0.02, 0.03, "head", dur=0.35)
    s.busy.append((tn - 0.2, tze + 0.6))
    s.expr([(tn, "determined", 0.8), (tz - 0.05, "joy"), (tze + 0.3, "joy")])
    # [ríe] ¿Empezamos?: laughs, then leans in with a hand offered to us, brows up
    l0, l1 = W.sound("laugh")
    s.laugh(l0 - 0.05, l1 + 0.1, amp=0.9)
    s.expr([(l0 - 0.05, "laugh"), (l1 + 0.1, "laugh", 0.6)])
    tp, tpe = W(3, "empezamos"), W.end(3, "empezamos")
    s.lean(tp - 0.35, tp, T + 1.0, 8.0, counter=1.1)
    s.add("head.ry", [(tp - 0.2, 0), (tp + 0.15, 7), (tpe + 0.5, 6), (T, 4)])
    s.c.arm_fwd("R", s.k([(tp - 0.3, 0), (tp, 30), (tpe + 0.3, 27), (T, 25)]))
    s.c.elbow("R", s.k([(tp - 0.3, 0), (tp, 48), (tpe + 0.3, 46), (T, 44)]))
    s.c.forearm_in("R", s.k([(tp - 0.3, 0), (tp, 12), (T, 10)]))
    s.c.palm("R", s.k([(tp - 0.3, 0), (tp, -70), (T, -66)]))
    s.hand("R", [(tp - 0.25, "relaxed"), (tp, "open"), (T, "open")])
    a.shift(tp - 0.2, -1)
    a.bounce(tp + 0.05, depth=0.01)
    s.add("head.rx", [(tpe + 0.4, 0), (tpe + 0.6, 4), (tpe + 0.85, 0)])          # a little nod: '¿sí?'
    s.expr([(tp - 0.15, "happy"), (tp + 0.1, "joy", 0.7), (tpe + 0.3, "happy"), (T, "happy")])
    s.looks.append((s.n - 1, CAM))
    return s.finish()


def calculadora(tl):
    """To himself: he looks everywhere for his calculator... it was in his hand all along."""
    rot = (-95.0, 0.0, 192.0)                          # the Calculator action's placement
    centre = np.array([0.032, -0.197, 0.347])
    loc = tuple(centre - PROP_REST)
    s = Scene(tl, seed=411, prop_loc=loc, prop_rot=rot)
    W, a = s.W, s.a
    a.stance(knees=0.008, lean=1.5)
    s.energy = 0.85
    T, n = tl["dur"], s.n
    # Mmm...: thinking, eyes up, the index tapping the air by his chin
    t0, t1 = 0.15, W(0, "dónde") - 0.1
    s.look([(0.0, DOWN), (0.2, UP_L), (t1, UP_L)])
    s.add("head.ry", [(t0, 0), (t0 + 0.35, 6), (t1, 5), (t1 + 0.3, 0)])
    s.ik("R", t0 + 0.2, t1, (-0.13, -0.24, 0.40), (0.25, -0.35, 1.0), (0.3, 0.9, 0.2), ramp=0.3)
    tap = np.sin(2 * np.pi * 2.5 * (s.t - t0)) * s.env(t0 + 0.3, t1 - 0.1, 0.1, 0.1)
    s.c.add("hand_ik.R.rx", 10.0 * tap)                # the finger taps the air: hmm...
    s.hand("R", [(t0, "point"), (t1, "point"), (t1 + 0.3, "relaxed")])
    s.expr([(0.0, "neutral"), (0.2, "thinking"), (t1, "thinking", 0.8)])
    a.shift(0.1, -1, amount=0.7)
    # ¿dónde dejé mi calculadora?: palms up, he looks around
    td, tce = W(0, "dónde"), W.end(0, "calculadora")
    for side in ("L", "R"):
        s.c.shrug(side, s.k([(td - 0.2, 0), (td + 0.1, 8), (tce, 7), (tce + 0.3, 0)]))
        s.c.arm_raise(side, s.k([(td - 0.2, 0), (td + 0.1, 26), (tce, 24), (tce + 0.35, 0)]))
        s.c.elbow(side, s.k([(td - 0.2, 0), (td + 0.1, 58), (tce, 55), (tce + 0.35, 0)]))
        s.c.palm(side, s.k([(td - 0.2, 0), (td + 0.1, -70), (tce, -66), (tce + 0.35, 0)]))
        s.hand(side, [(td - 0.1, "open"), (tce, "open"), (tce + 0.35, "relaxed")])
    s.look([(td, FAR_R), (W(0, "mi") - 0.1, FAR_L), (tce + 0.1, DOWN)])
    s.expr([(td, "confused"), (tce, "confused")])
    # ¿Aquí? No.: steps and bends down to his right to look at the floor; the head shakes
    tq, tno, tnoe = W(1, "aquí"), W(1, "no"), W.end(1, "no")
    a.step("R", tq - 0.55, dx=-0.04, dur=0.36)
    s.add("chest.rz", [(tq - 0.5, 0), (tq - 0.15, -16), (tno - 0.1, -14), (tnoe + 0.4, 0)])
    s.add("spine.rx", [(tq - 0.5, 0), (tq - 0.1, 9), (tno - 0.15, 8), (tnoe + 0.3, 1)])
    s.add("spine.ry", [(tq - 0.5, 0), (tq - 0.1, -6), (tno - 0.15, -5), (tnoe + 0.3, 0)])
    s.c.arm_fwd("R", s.k([(tq - 0.4, 0), (tq - 0.05, 30), (tno - 0.2, 28), (tno + 0.1, 0)]))
    s.c.elbow("R", s.k([(tq - 0.4, 0), (tq - 0.05, 30), (tno + 0.1, 0)]))
    s.c.palm("R", s.k([(tq - 0.4, 0), (tq - 0.05, 40), (tno + 0.1, 0)]))
    s.hand("R", [(tq - 0.3, "open"), (tno - 0.2, "open"), (tno + 0.1, "relaxed")])
    s.look([(tq - 0.45, FLOOR_R), (tq + 0.25, (-0.5, -0.9, 0.0)), (tq + 0.55, (-0.9, -0.3, 0.0)),
            (tno - 0.1, (-0.6, -0.8, 0.1))])
    s.shake(tno - 0.05, tnoe + 0.35, amp=11)
    s.expr([(tq - 0.4, "thinking", 0.6), (tq + 0.3, "skeptical", 0.7), (tno, "confused"),
            (tnoe + 0.4, "confused", 0.7)])
    # ¿Por allá? Tampoco.: back across and over to his left, on tiptoe, pointing far away
    tp, tpe, tt, tte = W(2, "por"), W.end(2, "allá"), W(2, "tampoco"), W.end(2, "tampoco")
    a.step("R", tp - 0.75, dx=0.04, dur=0.34)
    a.step("L", tp - 0.4, dx=0.035, dur=0.34)
    s.add("chest.rz", [(tp - 0.4, 0), (tp, 10), (tt - 0.1, 8), (tte + 0.3, 0)])
    s.add("spine.ry", [(tp - 0.4, 0), (tp, 5), (tt - 0.1, 4), (tte + 0.3, 0)])
    s.add("root.lz", [(tp - 0.25, 0), (tp + 0.05, 0.016), (tt - 0.15, 0.014), (tt + 0.1, 0)])
    for side in ("L", "R"):
        s.c.foot(side, pitch=s.k([(tp - 0.25, 0), (tp + 0.05, 16), (tt - 0.15, 14), (tt + 0.1, 0)]))
    s.c.arm_raise("L", s.k([(tp - 0.35, 0), (tp, 52), (tt - 0.2, 50), (tt + 0.1, 0)]))
    s.c.arm_fwd("L", s.k([(tp - 0.35, 0), (tp, 18), (tt - 0.2, 16), (tt + 0.1, 0)]))
    s.c.palm("L", s.k([(tp - 0.35, 0), (tp, 40), (tt + 0.1, 0)]))
    s.hand("L", [(tp - 0.25, "point"), (tt - 0.2, "point"), (tt + 0.1, "relaxed")])
    s.look([(tp - 0.35, FAR_L), (tpe + 0.3, (2.0, -0.4, 1.0)), (tt - 0.25, FAR_L), (tt, DOWN)])
    s.expr([(tp - 0.3, "surprised", 0.4), (tp + 0.2, "thinking", 0.7), (tt, "sad", 0.6), (tte + 0.2, "sad", 0.7)])
    for side in ("L", "R"):
        s.c.shrug(side, s.k([(tt, 0), (tt + 0.2, 9), (tte, 8), (tte + 0.35, -3), (tte + 0.7, -2)]))
        s.c.arm_raise(side, s.k([(tt, 0), (tt + 0.2, 18), (tte, 16), (tte + 0.4, -4)]))
        s.c.elbow(side, s.k([(tt, 0), (tt + 0.2, 45), (tte, 42), (tte + 0.4, 0)]))
        s.c.palm(side, s.k([(tt, 0), (tt + 0.2, -62), (tte, -58), (tte + 0.4, 0)]))
    s.hand("R", [(tt, "open"), (tte, "open"), (tte + 0.4, "relaxed")])
    s.hand("L", [(tt + 0.1, "open"), (tte, "open"), (tte + 0.4, "relaxed")])
    s.shake(tt + 0.1, tte + 0.2, amp=7, rate=2.2)
    a.step("L", tte + 0.1, dx=-0.035, dur=0.36)
    # a sigh... [gasp]: he freezes, eyes wide. ¡Ah!: the left hand comes up into view
    g0, _ = W.sound("gasp")
    th = W(3, "ah")
    s.add("head.rx", [(tte + 0.2, 0), (g0 - 0.2, 6), (g0, 4), (g0 + 0.15, -3), (th + 0.4, 0)])
    s.add("chest.rx", [(tte + 0.2, 0), (g0 - 0.2, 3), (g0 + 0.1, -2), (th + 0.4, 0)])
    a.squash(g0 + 0.02, 0.06, "head", dur=0.4)
    a.bounce(g0 - 0.05, depth=0.012, chest=-2.0)
    s.look([(g0 - 0.3, DOWN), (g0 + 0.05, (0.0, -1.6, 0.9))])
    s.expr([(g0 - 0.3, "sad", 0.5), (g0 + 0.02, "surprised")])
    # the calculator rides in his left palm from the moment it appears (hold_prop in the bake)
    D = _unit((-0.85, -0.5, 0.0))
    wrist = prop_world((-0.055, 0.008 + 0.013, -0.025), loc, rot) - 0.045 * D
    normal = rot_matrix(*rot) @ np.array([0.0, -1.0, 0.0])
    tpop = next(x["t0"] for x in tl["sounds"] if x["kind"] == "pop")
    up = np.array([0.0, -0.02, 0.035])             # he brings it up to look at it...
    lift = np.array([0.0, -0.035, 0.065])          # ...and higher still to show it: '¡en la mano!'
    tmo = W(3, "mano")
    s.reaches["L"] += [(s.F(th - 0.2), None, 0.0), (s.F(tpop - 0.3), (0.24, -0.17, 0.32), 0.9),
                       (s.F(tpop - 0.05), wrist + up, 1.0),
                       (s.F(tmo - 0.25), wrist + up, 1.0), (s.F(tmo + 0.05), wrist + lift, 1.0),
                       (s.F(tmo + 0.8), wrist + lift, 1.0), (s.F(tmo + 1.3), wrist + up, 1.0), (n - 1, wrist + up, 1.0)]
    s.orients["L"] += [(s.F(th - 0.2), D, normal), (n - 1, D, normal)]
    s.add("shoulder.L.rz", [(th - 0.2, 0), (tpop - 0.05, -24), (T + 1, -24)])
    s.hand("L", [(th - 0.15, "relaxed"), (tpop - 0.15, "hold_flat"), (T + 1, "hold_flat")])
    s.p.show("prop_calc", [(0, 0.0), (s.F(tpop - 0.04), 0.0), (s.F(tpop + 0.06), 1.1), (s.F(tpop + 0.16), 0.95),
                           (s.F(tpop + 0.26), 1.02), (s.F(tpop + 0.36), 1.0), (n - 1, 1.0)])
    s.p.supports.append({"side": "L", "prop": "Prop_Calc", "bone": "prop_calc",
                         "frames": (s.F(tpop - 0.04), n - 1), "ref": s.F(tpop + 0.5)})
    s.look([(th - 0.1, centre + np.array([0.05, -0.1, 0.05])), (tpop, centre + up), (tmo + 0.3, centre + lift)])
    a.bounce(th, depth=0.012, chest=2.0)
    a.squash(tpop + 0.03, 0.05, "head", dur=0.35)
    s.expr([(th - 0.05, "surprised"), (tpop + 0.1, "surprised"), (W(3, "traía"), "joy", 0.8)])
    # ¡La traía yo en la mano!: the right hand points at it, the head tilts
    tla = W(3, "la")
    s.c.arm_fwd("R", s.k([(tla - 0.25, 0), (tla, 22), (tmo + 0.5, 20), (tmo + 0.8, 0)]))
    s.c.elbow("R", s.k([(tla - 0.25, 0), (tla, 55), (tmo + 0.5, 52), (tmo + 0.8, 0)]))
    s.c.forearm_in("R", s.k([(tla - 0.25, 0), (tla, 30), (tmo + 0.5, 28), (tmo + 0.8, 0)]))
    s.hand("R", [(tla - 0.2, "point"), (tmo + 0.5, "point"), (tmo + 0.8, "relaxed")])
    s.add("head.ry", [(tla - 0.1, 0), (tla + 0.2, 6), (tmo + 0.4, 5), (tmo + 0.8, 0)])
    # [ríe] Ay, Morfi...: laughs at himself, a palm on his belly, the head shakes, a shy look at us
    l0, l1 = W.sound("laugh")
    ta_, tme = W(4, "ay"), W.end(4, "morfi")
    s.belly("R", l0 + 0.1, tme + 0.3)
    s.laugh(l0, l1 + 0.1, amp=0.9)
    s.shake(ta_ - 0.05, tme + 0.2, amp=8, rate=1.8)
    s.look([(l0, (0.25, -1.2, 1.2)), (ta_, centre), (tme + 0.35, "cam"), (tme + 0.9, centre)])
    s.expr([(l0 - 0.05, "laugh"), (l1, "laugh", 0.7), (ta_, "shy"), (tme + 0.3, "shy"), (tme + 0.8, "happy")])
    s.busy.append((g0 - 0.3, th + 0.6))
    return s.finish()


def idea(tl):
    """To himself: weighs 'café... pan...' with a finger on his chin, then the eureka: a jump."""
    s = Scene(tl, seed=421)
    s.p.max_reach = 1.12              # the arm stretches a little to reach his chin (a cartoon reach)
    s.p.life_sway = 0.6
    W, a = s.W, s.a
    a.stance(knees=0.008, lean=1.0)
    s.energy = 0.75
    T = tl["dur"]
    # thinking: the index on his chin, the other arm holding the elbow, eyes up, weighing
    c0, c1 = 0.4, W.end(2, "pan") + 0.15
    tc2 = W(2, "café")
    s.chin(c0, c1)
    s.steady(c0, c1)
    s.add("spine.rx", [(c0 - 0.3, 0), (c0, 3), (c1, 3), (c1 + 0.3, 0)])
    s.c.elbow("L", s.k([(c0 - 0.35, 0), (c0, 72), (c1, 72), (c1 + 0.35, 0)]))
    s.c.forearm_in("L", s.k([(c0 - 0.35, 0), (c0, 30), (c1, 30), (c1 + 0.35, 0)]))
    s.hand("L", [(c0 - 0.2, "relaxed"), (c0, "grip"), (c1, "grip"), (c1 + 0.3, "relaxed")])
    s.add("chest.rx", [(c0 - 0.3, 0), (c0, 4), (c1, 4), (c1 + 0.3, 0)])
    s.add("neck.rx", [(c0 - 0.3, 0), (c0, 2), (c1, 2), (c1 + 0.3, 0)])
    s.add("head.rx", [(c0 - 0.3, 0), (c0, 3), (c1, 3), (c1 + 0.3, 0)])
    cafe_l, pan_r = (0.9, -1.0, 1.15), (-0.9, -1.0, 1.15)
    hw = 0.10                                  # the finger stays on the chin: the eyes do the looking
    s.look([(0.0, DOWN), (0.3, UP_L, 0.6), (c0, UP_L, hw), (W(0, "ver", 1), (0.1, -1.0, 1.4), hw),
            (W(0, "café") - 0.12, cafe_l, hw), (W(1, "pan") - 0.12, pan_r, hw), (tc2 - 0.12, cafe_l, hw),
            (W.end(2, "café") + 0.3, (0.0, -1.0, 1.3), hw), (W(2, "pan") - 0.12, pan_r, hw),
            (c1, (0.0, -1.3, 1.2), hw), (c1 + 0.4, (0.0, -1.3, 1.2), 1.0)])
    for tw, sg in ((W(0, "café"), 1), (W(1, "pan"), -1), (tc2, 1), (W(2, "pan"), -1)):
        # weighing them: the whole body sways to each side (the weight shift), the head only a little
        s.add("head.ry", [(tw - 0.25, 0), (tw + 0.15, 2.5 * sg), (tw + 0.6, 2.2 * sg), (tw + 0.95, 0)])
        s.c.prop("mouth_side", s.k([(tw - 0.2, 0), (tw + 0.15, 0.45 * sg), (tw + 0.7, 0.35 * sg), (tw + 0.95, 0)]))
        s.c.prop("brow_L" if sg > 0 else "brow_R", s.k([(tw - 0.15, 0), (tw + 0.1, 0.45), (tw + 0.7, 0.3),
                                                        (tw + 1.0, 0)]))
        a.shift(tw - 0.15, sg, amount=0.8)
    s.expr([(0.0, "neutral"), (0.35, "thinking"), (c1 - 0.2, "thinking", 0.9)])
    # the idea arrives: the hand slides off the chin, the eyes open wide, he gathers for the jump
    ty, tye = W(3, "ya"), W.end(3, "sé")
    s.expr([(c1 + 0.15, "surprised", 0.5), (ty - 0.2, "surprised"), (ty + 0.12, "joy"), (tye + 0.3, "joy")])
    s.c.prop("pupil", s.k([(c1, 0), (ty - 0.25, 0.6), (ty + 0.2, 0.4), (tye + 0.6, 0)]))
    # ¡Ya sé!: a jump with the index up beside his face
    a.hop(ty - 0.06, height=0.085, crouch=0.026, air=0.42, arms=False)
    a.squash(ty + 0.03, 0.035, "head", dur=0.35)
    s.busy.append((ty - 0.5, tye + 0.5))
    s.high("R", ty, W(3, "café") - 0.2, beats=(ty,), shapes=[(ty - 0.22, "fist"), (ty - 0.02, "count1")])
    s.c.arm_raise("L", s.k([(ty - 0.2, 0), (ty + 0.05, 30), (tye + 0.15, 26), (tye + 0.45, 0)]))
    s.c.forearm_lift("L", s.k([(ty - 0.2, 0), (ty + 0.05, 30), (tye + 0.45, 0)]))
    s.hand("L", [(ty - 0.15, "fist"), (tye + 0.2, "fist"), (tye + 0.45, "relaxed")])
    s.look([(ty - 0.35, (0.0, -1.2, 1.5)), (tye + 0.2, (0.0, -1.6, 1.0))])
    # ¡Café con pan!: a palm up for each, then he weighs them together
    tc, tco, tp = W(3, "café"), W(3, "con"), W(3, "pan")
    s.present("L", tc + 0.02, W.end(3, "pan") + 0.7, raise_=34, swing=26, palm=-60)
    s.present("R", tp, W.end(3, "pan") + 0.7, raise_=34, swing=26, palm=-60)
    hand_l, hand_r = (0.36, -0.12, 0.40), (-0.36, -0.12, 0.40)
    s.look([(tc - 0.1, hand_l), (tco + 0.05, (0.0, -1.4, 0.9)), (tp - 0.1, hand_r), (W.end(3, "pan") + 0.3,
                                                                                    (0.0, -1.5, 1.05))])
    a.bounce(tc, depth=0.012)
    a.bounce(tp, depth=0.014)
    a.shift(tc - 0.1, 1)
    a.shift(tp - 0.1, -1)
    # ¡Soy un genio!: chin up, chest out, eyes closed, proud; the index taps his temple
    tg0, tg, tge = W(4, "soy"), W(4, "genio"), W.end(4, "genio")
    s.high("R", tg0 + 0.05, tge + 0.45, beats=(tg + 0.08,), shapes=[(tg0 - 0.2, "fist"), (tg0 + 0.05, "point")])
    s.c.add("hand_ik.R.lx", 0.008 * (np.exp(-((s.t - tg - 0.1) / 0.06) ** 2) +
                                     np.exp(-((s.t - tge - 0.05) / 0.06) ** 2)))
    s.lean(tg0 - 0.2, tg0 + 0.15, tge + 0.5, -5.0, counter=0.3)
    s.add("head.ry", [(tg0, 0), (tg0 + 0.3, -6), (tge + 0.6, -5), (T, -2)])
    s.c.arm_raise("L", s.k([(tg0 - 0.2, 0), (tg0 + 0.1, 14), (T, 12)]))
    s.c.elbow("L", s.k([(tg0 - 0.2, 0), (tg0 + 0.1, 78), (T, 74)]))
    s.c.forearm_in("L", s.k([(tg0 - 0.2, 0), (tg0 + 0.1, 12), (T, 10)]))
    s.hand("L", [(tg0 - 0.1, "fist"), (T, "fist")])
    s.look([(tg0, (0.3, -1.3, 1.35)), (tge + 0.6, (0.2, -1.5, 1.1))])
    s.expr([(tg0 - 0.1, "smug"), (tg + 0.1, {"blink_L": 1.0, "blink_R": 1.0, "eye_calm": 0.0, "smile": 1.0,
                                              "brow_L": 0.5, "brow_R": 0.5}),
            (tge + 0.5, "smug"), (T, "happy")])
    a.bounce(tg, depth=0.012, chest=-2.0)
    a.squash(tg + 0.02, 0.04, "head")
    return s.finish()


def ventas(tl):
    """To the camera: '¡Uf! ¡Qué día! Cobramos, vendimos, sonreímos... ¡y la caja cuadró al
    centavo! ¡Esto merece un bailecito!' ... and he dances."""
    s = Scene(tl, seed=431)
    W, a = s.W, s.a
    a.stance(knees=0.008, lean=2.0)
    T = tl["dur"]
    # ¡Uf!: a big breath in, then he blows it out and deflates
    tu, tue = W(0, "uf"), W.end(0, "uf")
    s.look([(0.0, (0.3, -1.2, 1.25)), (0.45, (0.1, -1.4, 1.1)), (tue + 0.2, "cam")])
    for side in ("L", "R"):
        s.c.shrug(side, s.k([(0.0, 0), (tu - 0.1, 8), (tu + 0.15, -5), (tue + 0.3, -4), (tue + 0.6, 0)]))
        s.c.arm_raise(side, s.k([(tu - 0.1, 0), (tu + 0.15, -7), (tue + 0.5, -5), (tue + 0.8, 0)]))
    s.add("chest.rx", [(0.0, 0), (tu - 0.1, -4), (tu + 0.2, 6), (tue + 0.4, 4), (tue + 0.7, 0)])
    s.add("head.rx", [(0.0, 0), (tu - 0.1, -6), (tu + 0.2, 4), (tue + 0.4, 2), (tue + 0.7, 0)])
    s.add("hips.lz", [(tu - 0.05, 0), (tu + 0.2, -0.018), (tue + 0.4, -0.012), (tue + 0.7, 0)])
    a.squash(tu + 0.1, -0.05, "head", dur=0.5)
    tired = {"lid_drop": 0.45, "smile": 0.45, "brow_in_L": 0.35, "brow_in_R": 0.35, "mouth_round": 0.3}
    s.expr([(0.0, "happy", 0.6), (tu - 0.1, {"brow_L": 0.4, "brow_R": 0.4, "smile": 0.3}), (tu + 0.1, tired),
            (tue + 0.35, tired)])
    # ¡Qué día!: perks up, fans himself with the right hand, the head shakes: what a day
    tq, tqe = W(0, "qué"), W.end(0, "día")
    s.fan("R", tq - 0.1, tqe + 0.2)
    s.shake(tq, tqe + 0.3, amp=6, rate=2.0)
    s.expr([(tq - 0.05, "happy"), (tqe, "joy", 0.7), (tqe + 0.5, "happy")])
    a.shift(tq - 0.1, +1)
    # Cobramos, vendimos, sonreímos...: counts them off beside his face
    tco, tve, tso, tsoe = W(1, "cobramos"), W(1, "vendimos"), W(1, "sonreímos"), W.end(1, "sonreímos")
    s.high("R", tco - 0.05, tsoe + 0.3, beats=(tco, tve, tso),
           shapes=[(tco - 0.25, "fist"), (tco, "count1"), (tve - 0.1, "count1"), (tve + 0.02, "count2"),
                   (tso - 0.1, "count2"), (tso + 0.02, "count3")])
    for i, tb in enumerate((tco, tve, tso)):
        sg = 1 if i % 2 == 0 else -1
        a.shift(tb - 0.1, sg)
        s.add("head.ry", [(tb - 0.1, 0), (tb + 0.15, -6 * sg), (tb + 0.7, -4 * sg), (tb + 0.95, 0)])
    a.beat("L", tve, amp=0.8)
    s.lean(tco - 0.3, tco, tsoe, 5.0)
    s.expr([(tco, "happy"), (tve, "joy", 0.7), (tso, "joy"), (tsoe + 0.3, "joy", 0.9)])
    # ¡y la caja cuadró al centavo!: leans in, a fist pump and a hop; 'al centavo': a pinch, a wink
    tca, tcu, tce, tcee = W(2, "caja"), W(2, "cuadró"), W(2, "centavo"), W.end(2, "centavo")
    s.lean(tca - 0.3, tca, tcu - 0.1, 6.0)
    s.fist_pump("R", tcu, hold=0.4)
    a.hop(tcu - 0.05, height=0.045, crouch=0.02, air=0.28, arms=False)
    s.busy.append((tcu - 0.45, tcu + 0.5))
    s.high("L", tce - 0.05, tcee + 0.4, shapes=[(tce - 0.25, "relaxed"), (tce, "pinch")])
    s.add("head.ry", [(tce - 0.1, 0), (tce + 0.15, 6), (tcee + 0.4, 5), (tcee + 0.7, 0)])
    s.expr([(tca - 0.1, "joy"), (tcu + 0.3, "joy"), (tce, "wink"), (tcee + 0.35, "wink"), (tcee + 0.6, "happy")])
    # ¡Esto merece un bailecito!: a finger up, a cheeky look, he gets ready
    tes, tme, tba, tbae = W(3, "esto"), W(3, "merece"), W(3, "bailecito"), W.end(3, "bailecito")
    s.high("R", tes - 0.02, tme + 0.45, shapes=[(tes - 0.22, "fist"), (tes, "count1")])
    s.expr([(tes - 0.1, "smug", 0.8), (tba, "joy")])
    s.add("head.ry", [(tme - 0.1, 0), (tme + 0.2, -7), (tba, -5), (tba + 0.3, 0)])
    # the dance: step-touch side to side on a 0.5 s beat, arms pumping, hips and head on the beat
    d0, d1 = tbae - 0.25, T - 0.75
    s.dance(d0, d1 - 0.3, beat=0.5)
    s.expr([(d0, "joy"), (d0 + 1.5, "laugh", 0.8), (d0 + 2.4, "joy"), (d1, "joy")])
    s.look([(d0, "cam"), (d0 + 1.0, (0.4, -1.5, 1.0)), (d0 + 2.0, "cam"), (d0 + 3.0, (-0.4, -1.5, 1.0)),
            (d1 - 0.3, "cam"), (T, "cam")])
    # ta-da!
    s.open_arms(d1 + 0.05, T + 1.0, raise_=40, elbow=44, palm=-80)
    a.hop(d1 - 0.05, height=0.03, crouch=0.016, air=0.22, arms=False)
    s.busy.append((d0 - 0.2, T))
    return s.finish()


def susto(tl):
    """To himself: a bell rings out of nowhere: a jump, a peek, a whisper... it was the register."""
    s = Scene(tl, seed=441)
    s.p.max_reach = 1.12              # palms on the cheeks (as the Surprised action): a cartoon reach
    W, a = s.W, s.a
    a.stance(knees=0.008, lean=1.0)
    s.energy = 0.85
    T = tl["dur"]
    b0 = next(x["t0"] for x in tl["sounds"] if x["kind"] == "bell")
    b2 = next(x["t0"] for x in tl["sounds"] if x["kind"] == "bell2")
    g0, _ = W.sound("gasp")
    # calm, content, looking down at nothing in particular
    s.look([(0.0, (0.45, -0.9, 0.25)), (b0 + 0.12, (0.0, -1.5, 0.85))])
    content = {"smile": 0.55, "lid_drop": 0.25, "squint": 0.2}
    s.expr([(0.0, content), (b0 + 0.08, content), (b0 + 0.16, "surprised"), (g0 + 0.1, "scared")])
    s.p.blinks.append(s.F(b0 + 0.1))
    a.shift(0.0, +1, amount=0.5)
    # the bell -> the startle: a jump with a stretch, arms flung up, landing low
    tj = g0 - 0.02
    a.hop(tj, height=0.10, crouch=0.012, air=0.38, arms=False)
    a.squash(tj + 0.04, 0.035, "head", dur=0.32)
    s.arms_up(tj + 0.07, tj + 0.48, shape="claw", raise_=50, lift=30)
    land = tj + 0.38
    s.busy.append((tj - 0.4, land + 0.5))
    # ¡Ay! ¿Qué fue eso?: crouched, hands up in front of his chest, trembling, the head snapping round
    h0, h1 = land + 0.15, W(1, "hay") + 1.1
    s.crouch(land + 0.1, h1, depth=0.022, lean=2.0, ramp=0.2)
    for side in ("L", "R"):
        sg = SX[side]
        s.ik(side, h0, h1, (0.16 * sg, -0.15, 0.41), (-0.25 * sg, -0.55, 0.8), (0.0, -1.0, 0.1), ramp=0.22)
        s.c.shrug(side, s.k([(land, 0), (h0, 7), (h1, 6), (h1 + 0.3, 0)]))
        s.hand(side, [(h0 - 0.2, "claw"), (h1, "claw"), (h1 + 0.3, "relaxed")])
    s.tremble(h0, h1, amp=1.0)
    s.look([(W(0, "qué") - 0.15, FAR_L), (W(0, "fue") + 0.05, FAR_R), (W(0, "eso") + 0.15, (1.6, 0.5, 0.9)),
            (W.end(0, "eso") + 0.35, (0.0, -1.5, 0.8))])
    s.expr([(land, "scared"), (W.end(0, "eso") + 0.3, "scared", 0.85)])
    # ¿Hay alguien ahí? (whispered): low, leaning out to his right to peek, a sneaky step
    tw0, twe = W(1, "hay"), W.end(1, "ahí")
    a.step("R", tw0 - 0.7, dx=-0.03, dy=-0.02, dur=0.5)
    s.add("spine.ry", [(tw0 - 0.6, 0), (tw0 - 0.1, -7), (twe + 0.4, -6), (b2 + 0.1, 0)])
    s.add("chest.rz", [(tw0 - 0.6, 0), (tw0 - 0.1, -12), (twe + 0.4, -11), (b2 + 0.1, 0)])
    s.lean(tw0 - 0.6, tw0 - 0.1, twe + 0.4, 5.0)
    s.look([(tw0 - 0.45, (-1.2, -1.4, 0.6)), (W(1, "alguien"), (-0.9, -1.5, 0.5)), (W(1, "ahí"), (-1.3, -1.1, 0.7)),
            (twe + 0.35, (-0.9, -1.4, 0.6))])
    s.expr([(tw0 - 0.4, "scared", 0.8), (twe + 0.4, "scared", 0.8)])
    # ding-ding!: a flinch, both palms to the cheeks... Ah... era el timbre de la caja: relief
    tah, tti, tca = W(2, "ah"), W(2, "timbre"), W.end(2, "caja")
    a.squash(b2 + 0.1, -0.06, "head", dur=0.35)
    a.bounce(b2 + 0.08, depth=0.02, chest=-3.0)
    s.cheeks(b2 + 0.3, tah + 0.3, ramp=0.25)
    # (palms on the cheeks: the head stays square, a turned head takes the cheeks out of reach)
    s.look([(b2 + 0.05, (-0.5, -1.6, 0.8)), (b2 + 0.3, (0.0, -1.6, 0.75)), (tah + 0.35, (0.0, -1.6, 0.75)),
            (tah + 0.6, (-1.0, -0.9, 0.35)), (tti, (-0.9, -0.8, 0.3)), (tca + 0.3, (0.2, -1.3, 1.0))])
    s.expr([(b2 + 0.05, "scared"), (tah, "surprised", 0.7), (tti - 0.1, "calm", 0.6), (tti + 0.2, "happy", 0.8)])
    for side in ("L", "R"):
        s.c.shrug(side, s.k([(tah + 0.2, 0), (tah + 0.6, -5), (tca, -3), (tca + 0.5, 0)]))
    s.add("chest.rx", [(tah + 0.2, 0), (tah + 0.6, 4), (tca, 2), (tca + 0.5, 0)])
    s.add("head.ry", [(tti - 0.2, 0), (tti + 0.2, -6), (tca + 0.3, -4), (tca + 0.7, 0)])
    s.belly("R", tah + 1.0, W.end(3, "di") + 0.25, ramp=0.4)
    a.beat("L", tti + 0.05, amp=0.9)
    # [ríe] ¡Qué susto me di!: laughs at himself, the head shakes
    l0, l1 = W.sound("laugh")
    s.laugh(l0 - 0.05, W.end(3, "di") + 0.1, amp=0.9)
    s.shake(W(3, "susto") - 0.05, W.end(3, "di") + 0.2, amp=6, rate=2.0)
    s.look([(l0, (0.2, -1.2, 1.3)), (W(3, "qué"), (0.3, -1.5, 0.95)), (T, (0.2, -1.5, 0.9))])
    s.expr([(l0 - 0.05, "laugh"), (W(3, "qué"), "laugh", 0.6), (W.end(3, "di") + 0.2, "joy", 0.8), (T, "happy")])
    return s.finish()


def sueno(tl):
    """To himself: a huge yawn and stretch, 'cinco minutitos'... he nods off; the door chime wakes
    him with a jump: '¡Ya llegaron clientes! ¡Bienvenidos!'"""
    s = Scene(tl, seed=451)
    W, a = s.W, s.a
    a.stance(knees=0.01, lean=0.5)
    s.energy = 0.6
    T, n = tl["dur"], s.n
    sleepy = {"lid_drop": 0.75, "brow_in_L": 0.3, "brow_in_R": 0.3, "smile": 0.15}
    asleep = {"blink_L": 1.0, "blink_R": 1.0, "eye_calm": 1.0, "smile": 0.1, "mouth_open": 0.15}
    # the yawn and a big stretch: arms up, back arched, head back, up on his toes
    ya, yae = W(0, "aaay"), W.end(0, "aaay")
    s.look([(0.0, (0.2, -1.2, 0.7)), (ya - 0.2, (0.0, -1.0, 1.6)), (yae + 0.5, (0.3, -1.2, 0.6))])
    s.arms_up(ya - 0.05, yae + 0.55, shape="fist", raise_=56, lift=40)
    for side in ("L", "R"):
        s.c.arm_swing(side, s.k([(ya - 0.3, 0), (ya, -10), (yae + 0.3, -10), (yae + 0.6, 0)]))
    s.add("spine.rx", [(ya - 0.4, 0), (ya, -6), (yae + 0.2, -7), (yae + 0.55, 0)])
    s.add("chest.rx", [(ya - 0.4, 0), (ya, -6), (yae + 0.2, -7), (yae + 0.55, 0)])
    s.add("head.rx", [(ya - 0.4, 0), (ya, -10), (yae + 0.2, -12), (yae + 0.55, 2)])
    s.add("root.lz", [(ya - 0.3, 0), (ya, 0.018), (yae + 0.25, 0.02), (yae + 0.5, 0)])
    for side in ("L", "R"):
        s.c.foot(side, pitch=s.k([(ya - 0.3, 0), (ya, 14), (yae + 0.25, 15), (yae + 0.5, 0)]))
    a._sy("head", C.keys(n, s.k([(ya - 0.4, 0.0), (ya + 0.2, 0.07), (yae + 0.2, 0.07), (yae + 0.45, -0.04),
                                 (yae + 0.75, 0.0)])))
    a._sy("spine", C.keys(n, s.k([(ya - 0.4, 0.0), (ya + 0.2, 0.02), (yae + 0.2, 0.02), (yae + 0.5, 0.0)])))
    yawn = {"mouth_open": 0.9, "mouth_round": 0.35, "blink_L": 1.0, "blink_R": 1.0, "eye_calm": 0.4,
            "brow_in_L": 0.6, "brow_in_R": 0.6, "brow_L": 0.4, "brow_R": 0.4}
    s.expr([(0.0, sleepy), (ya - 0.2, sleepy), (ya, yawn), (yae + 0.15, yawn), (yae + 0.5, sleepy)])
    s.busy.append((ya - 0.4, yae + 0.6))
    for side in ("L", "R"):                       # the shiver after the stretch
        s.c.shrug(side, 3.0 * np.sin(2 * np.pi * 7 * (s.t - yae)) * s.env(yae + 0.45, yae + 0.8, 0.05, 0.15))
    # ¡qué sueño...: drooping, the head tilts
    tq, tse = W(0, "qué"), W.end(0, "sueño")
    s.add("head.ry", [(tq - 0.2, 0), (tq + 0.3, 8), (tse + 0.6, 7), (W(1, "cinco"), 2)])
    s.add("head.rx", [(tq - 0.2, 0), (tq + 0.3, 3), (tse + 0.6, 4), (W(1, "cinco"), 1)])
    s.expr([(tq, sleepy), (tse, {**sleepy, "lid_drop": 0.7})])
    # Cinco minutitos nada más...: a lazy finger up, the eyelids closing
    tc, tm, tna, tmae = W(1, "cinco"), W(1, "minutitos"), W(1, "nada"), W.end(1, "más")
    s.c.arm_fwd("R", s.k([(tc - 0.35, 0), (tc, 14), (tna, 10), (tmae + 0.3, 0)]))
    s.c.elbow("R", s.k([(tc - 0.35, 0), (tc, 70), (tna, 60), (tmae + 0.3, 0)]))
    s.c.forearm_in("R", s.k([(tc - 0.35, 0), (tc, 12), (tmae + 0.3, 0)]))
    s.c.palm("R", s.k([(tc - 0.35, 0), (tc, 30), (tmae + 0.3, 0)]))
    s.hand("R", [(tc - 0.25, "relaxed"), (tc - 0.02, "count1"), (tna, "count1"), (tmae + 0.25, "relaxed")])
    s.look([(tc - 0.2, (0.0, -1.3, 0.75)), (tmae, (0.0, -1.0, 0.3))])
    s.expr([(tc, {**sleepy, "lid_drop": 0.6, "smile": 0.35}), (tna, {**sleepy, "lid_drop": 0.85}),
            (tmae + 0.25, asleep)])
    # nodding off: the head sinks, the body sways; a jerk; deeper
    ch = next(x["t0"] for x in tl["sounds"] if x["kind"] == "chime")
    g0, _ = W.sound("gasp")
    z0, jerk = tmae + 0.2, tmae + 1.1
    s.add("head.rx", [(z0, 0), (z0 + 0.8, 8), (jerk, 10), (jerk + 0.1, 0), (jerk + 0.5, 3), (ch, 11),
                      (g0 - 0.05, 12), (g0 + 0.05, -4), (g0 + 0.5, 0)])
    s.add("neck.rx", [(z0, 0), (z0 + 0.8, 3), (jerk, 4), (jerk + 0.1, 0), (ch, 4), (g0 - 0.05, 4), (g0 + 0.1, 0)])
    s.add("chest.rx", [(z0, 0), (z0 + 0.8, 4), (g0 - 0.05, 5), (g0 + 0.1, -2), (g0 + 0.5, 0)])
    s.add("hips.lz", [(z0, 0), (z0 + 0.8, -0.012), (g0 - 0.05, -0.014), (g0 + 0.05, 0)])
    sway = np.sin(2 * np.pi * 0.28 * (s.t - z0)) * s.env(z0 + 0.6, g0 - 0.1, 0.5, 0.05)
    s.c.add("hips.ry", 3.0 * sway)
    s.c.add("head.ry", -2.5 * C.delay(sway, 6))
    breath = np.sin(2 * np.pi * 0.35 * (s.t - z0)) * s.env(z0 + 0.5, g0 - 0.1, 0.4, 0.05)
    s.c.add("chest.rx", 2.0 * breath)
    for side in ("L", "R"):
        s.c.shrug(side, 2.0 * breath)
        s.c.arm_raise(side, s.k([(z0, 0), (z0 + 0.8, -5), (g0 - 0.05, -6), (g0 + 0.1, 0)]))
    s.expr([(jerk - 0.05, asleep), (jerk + 0.05, {**sleepy, "lid_drop": 0.75}), (jerk + 0.45, asleep),
            (ch, asleep), (ch + 0.2, {**asleep, "brow_L": 0.2}), (g0 - 0.1, asleep)])
    # the chime: a twitch... the gasp: awake with a jump, arms up, eyes wide
    s.add("head.rz", [(ch + 0.12, 0), (ch + 0.22, 4), (ch + 0.45, 0)])
    tj = g0 - 0.03
    a.hop(tj, height=0.09, crouch=0.01, air=0.36, arms=False)
    a.squash(tj + 0.04, 0.035, "head", dur=0.32)
    s.arms_up(tj + 0.06, tj + 0.42, shape="open", raise_=48, lift=30)
    s.busy.append((tj - 0.4, tj + 0.9))
    s.look([(g0 - 0.05, (0.0, -1.5, 0.9)), (g0 + 0.25, FAR_L)])
    s.expr([(g0 - 0.05, "surprised"), (g0 + 0.3, "scared")])
    # ¡No, no, no!: palms on his cheeks, the head shaking
    tn0, tne = W(2, "no"), W.end(2, "no", 2)
    s.cheeks(tj + 0.62, tne + 0.12, ramp=0.25)
    s.shake(tn0, tne + 0.12, amp=6, rate=4.0)
    s.look([(tn0, (0.0, -1.5, 0.85))])
    # ¡Ya llegaron clientes!: he straightens up, a step to the door (to us), tidies his hoodie
    tya, tcl, tcle = W(2, "ya"), W(2, "clientes"), W.end(2, "clientes")
    a.step("L", tya - 0.05, dy=-0.035, dur=0.34)
    s.look([(tya - 0.1, "cam")])
    for side in ("L", "R"):
        s.c.arm_fwd(side, s.k([(tcl - 0.25, 0), (tcl, 16), (tcl + 0.25, 4), (tcle + 0.3, 0)]))
        s.c.elbow(side, s.k([(tcl - 0.25, 0), (tcl, 40), (tcl + 0.25, 14), (tcle + 0.3, 0)]))
        s.hand(side, [(tcl - 0.2, "fist"), (tcle + 0.1, "fist"), (tcle + 0.35, "relaxed")])
    s.add("chest.rx", [(tcl - 0.2, 0), (tcl + 0.25, -4), (tcle + 0.4, -2), (tcle + 0.8, 0)])
    s.expr([(tya - 0.05, "surprised", 0.7), (tcl, "determined", 0.6), (tcle + 0.2, "happy")])
    # ¡Bienvenidos!: arms open wide to us, a little hop, then he waves
    tb, tbe = W(3, "bienvenidos"), W.end(3, "bienvenidos")
    s.open_arms(tb - 0.05, tbe + 0.25, raise_=38, elbow=42, palm=-80)
    a.hop(tb - 0.1, height=0.035, crouch=0.018, air=0.25, arms=False)
    s.busy.append((tb - 0.5, tb + 0.4))
    s.wave("R", tbe + 0.3, T + 0.4, period=0.42)
    s.expr([(tb - 0.1, "joy"), (tbe + 0.2, "joy"), (T, "happy")])
    s.looks.append((n - 1, CAM))
    return s.finish()


SCENES = {"presentacion": presentacion, "calculadora": calculadora, "idea": idea, "ventas": ventas,
          "susto": susto, "sueno": sueno}


def build(key, tl=None):
    """The Performance of a scene (tl: its timeline, built here when not given)."""
    return SCENES[key](tl or timeline(key))
