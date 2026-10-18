"""Morfi's voice lines for the web lab: every phrase (or scene line) in every candidate voice.

    XI_KEY=<key> python voice/gen.py phrases [--voices thorthugo_grave,maskito] [--force]
    XI_KEY=<key> python voice/gen.py lines voice/scenes.json --voice thorthugo_grave

Output (served by the viewer): web/public/voice/<voice>/<key>.mp3 and web/public/voice/index.json
with, per clip, the duration, the character alignment (tags like [excited] removed) and the audio
envelope per 1/30 s, which drive the lip-sync (see web/src/live/voice.ts).

The ElevenLabs key only lives in the environment of the command (never in a file).
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "web", "public", "voice")
FPS = 30
SR = 44100


def load(name):
    return json.load(open(os.path.join(HERE, name), encoding="utf-8"))


def tts(voice_id, text, model, settings, seed):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128"
    body = {"text": text, "model_id": model, "language_code": "es", "voice_settings": settings, "seed": seed}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"xi-api-key": os.environ["XI_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def clean(al):
    """Drop audio tags ([excited] ...) from the alignment; keep (char, start, end)."""
    out, inside, skip = [], False, False
    for c, a, b in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if c == "[":
            inside = True
            continue
        if inside:
            if c == "]":
                inside, skip = False, True
            continue
        if skip and c == " ":
            skip = False
            continue
        skip = False
        out.append((c, round(a, 3), round(b, 3)))
    return out


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def envelope(x):
    hop = SR / FPS
    n = int(len(x) / hop) + 1
    env = np.array([np.sqrt(np.mean(x[int(i * hop):int((i + 1) * hop)] ** 2)) if int(i * hop) < len(x) else 0.0
                    for i in range(n)])
    ref = np.percentile(env[env > 1e-3], 95) if np.any(env > 1e-3) else 1.0
    return [round(float(v), 3) for v in np.clip(env / ref, 0, 1.3)]


def make_clip(voice, cfg, key, text, seed, force):
    vdir = os.path.join(OUT, voice["key"])
    os.makedirs(vdir, exist_ok=True)
    mp3 = os.path.join(vdir, key + ".mp3")
    meta = os.path.join(vdir, key + ".json")
    if os.path.exists(mp3) and os.path.exists(meta) and not force:
        return json.load(open(meta, encoding="utf-8"))
    res = tts(voice["id"], text, cfg["model"], cfg["settings"], seed)
    af = ["loudnorm=I=-16:TP=-1.5:LRA=11"]
    if voice.get("pitch"):
        # lower the voice without changing its length (the alignment stays valid) or its timbre
        af.insert(0, f"rubberband=pitch={2 ** (voice['pitch'] / 12):.5f}:formant=preserved")
    with tempfile.TemporaryDirectory() as tmp:          # the raw clip stays out of the served folder
        raw = os.path.join(tmp, key + ".raw.mp3")       # removed with tmp, even if ffmpeg fails
        with open(raw, "wb") as fh:
            fh.write(base64.b64decode(res["audio_base64"]))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", ",".join(af), "-ar", str(SR), "-c:a",
                        "libmp3lame", "-b:a", "96k", mp3], check=True)
    chars = clean(res.get("alignment") or res.get("normalized_alignment"))
    x = decode(mp3)
    data = {"text": "".join(c for c, _, _ in chars).strip(), "dur": round(len(x) / SR, 3),
            "chars": "".join(c for c, _, _ in chars), "t0": [a for _, a, _ in chars], "t1": [b for _, _, b in chars],
            "env": envelope(x)}
    json.dump(data, open(meta, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"  {voice['key']}/{key}: {data['dur']} s")
    return data


def write_index():
    cfg = load("voices.json")
    ph = load("phrases.json")
    index = {"default": cfg["default"], "voices": [{"key": v["key"], "name": v["name"], "note": v["note"]} for v in cfg["voices"]],
             "phrases": [{k: p[k] for k in ("key", "text", "mood", "gesture")} for p in ph["phrases"]], "clips": {}}
    for v in cfg["voices"]:
        vdir = os.path.join(OUT, v["key"])
        if not os.path.isdir(vdir):
            continue
        for f in sorted(os.listdir(vdir)):
            if f.endswith(".json"):
                d = json.load(open(os.path.join(vdir, f), encoding="utf-8"))
                index["clips"].setdefault(v["key"], {})[f[:-5]] = {"dur": d["dur"]}
    json.dump(index, open(os.path.join(OUT, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("index", os.path.join(OUT, "index.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["phrases", "lines", "index"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--voices", default="")
    ap.add_argument("--voice", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    cfg = load("voices.json")
    if a.cmd == "phrases":
        if not os.environ.get("XI_KEY"):
            sys.exit("XI_KEY is not set")
        keys = set(a.voices.split(",")) if a.voices else None
        for v in cfg["voices"]:
            if keys and v["key"] not in keys:
                continue
            for i, p in enumerate(load("phrases.json")["phrases"]):
                make_clip(v, cfg, p["key"], p["text"], 4000 + 31 * i, a.force)
    elif a.cmd == "lines":
        if not os.environ.get("XI_KEY"):
            sys.exit("XI_KEY is not set")
        voice = next(v for v in cfg["voices"] if v["key"] == (a.voice or cfg["default"]))
        spec = json.load(open(a.file, encoding="utf-8"))
        for i, ln in enumerate(spec["lines"]):
            make_clip(voice, cfg, ln["key"], ln["text"], 6000 + 17 * i, a.force)
    write_index()


if __name__ == "__main__":
    main()
