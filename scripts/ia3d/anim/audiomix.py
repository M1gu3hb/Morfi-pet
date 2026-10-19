"""Audio of a scene / performance: the voice lines placed on a timeline, a few synthesised effects,
levelled to the lines' loudness and encoded as one mp3 (plain Python + numpy, ffmpeg on PATH).

    tl = scenes.timeline("susto")           # or scenes.timeline_from_file(...) for a performance test
    al, stats = mix(tl, "out.mp3")          # al = merged alignment (the lip-sync / lab JSON)

Used by make_scenes.py (scene audio) and compose_audio.py (the model-comparison performances), so
both come out at the same loudness and format (96 kbps mono mp3, 44.1 kHz).
"""
import json
import os
import re
import subprocess

import numpy as np

from . import scenes as S

SR = 44100
BITRATE = "96k"


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def loudness(x):
    """Integrated loudness (LUFS) and true peak (dBTP) of a mono float signal (ffmpeg ebur128)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-af", "ebur128=peak=true", "-f", "null", "-"], input=x.astype(np.float32).tobytes(),
                       capture_output=True)
    log = p.stderr.decode("utf-8", "replace")
    tail = log[log.rfind("Summary:"):]
    i = float(re.search(r"I:\s+(-?[\d.]+) LUFS", tail).group(1))
    pk = float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail).group(1))
    return i, pk


def _bell(f0, dur=1.3, partials=((1.0, 1.0, 0.9), (2.32, 0.45, 0.42), (4.25, 0.22, 0.22), (6.63, 0.10, 0.12))):
    t = np.arange(int(dur * SR)) / SR
    x = np.zeros_like(t)
    for ratio, amp, tau in partials:
        f = f0 * ratio
        x += amp * (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 1.004 * t)) * np.exp(-t / tau)
    x *= np.minimum(1.0, t / 0.002)                     # 2 ms strike
    return x / np.abs(x).max()


def sfx(kind):
    """Small synthesised effects (no samples, no services): a counter bell, a door chime, a pop."""
    if kind == "bell":                                  # the cash register's bell: ding!
        return 0.32 * _bell(2093.0)
    if kind == "bell2":                                 # again, a little softer: ding-ding
        a = _bell(2093.0, 1.0)
        out = np.zeros(len(a) + int(0.16 * SR))
        out[:len(a)] += a
        out[int(0.16 * SR):] += 0.8 * a
        return 0.22 * out / np.abs(out).max()
    if kind == "chime":                                 # shop door chime: ding-dong
        soft = ((1.0, 1.0, 1.1), (2.0, 0.25, 0.5), (3.0, 0.08, 0.25))
        a, b = _bell(659.3, 1.4, soft), _bell(523.3, 1.6, soft)
        out = np.zeros(int(0.42 * SR) + len(b))
        out[:len(a)] += a
        out[int(0.42 * SR):] += b
        return 0.34 * out / np.abs(out).max()
    if kind == "pop":                                   # it appears: bloop + a sparkle
        t = np.arange(int(0.35 * SR)) / SR
        f = 260 + 900 * np.clip(t / 0.07, 0, 1)
        blo = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.05)
        spk = np.sin(2 * np.pi * 3136 * t) * np.exp(-np.maximum(t - 0.05, 0) / 0.09) * (t > 0.05)
        return 0.30 * blo + 0.10 * spk
    raise KeyError(kind)


def envelope(x, fps=30):
    hop = SR / fps
    n = int(len(x) / hop) + 1
    env = np.array([np.sqrt(np.mean(x[int(i * hop):int((i + 1) * hop)] ** 2)) if int(i * hop) < len(x) else 0.0
                    for i in range(n)])
    ref = np.percentile(env[env > 1e-3], 95) if np.any(env > 1e-3) else 1.0
    return np.clip(env / ref, 0, 1.3)


def mix(tl, mp3, json_path=None):
    """Place the lines (4 ms fades, no clicks at the joins) and the effects of `tl` on one track,
    level it to the lines' mean loudness under the -1.5 dBTP ceiling they were normalised to, and
    encode `mp3`. Returns (merged alignment dict with a "loudness" entry, stats); the alignment is
    also written to `json_path` when given."""
    voice_dir = tl.get("voice_dir", S.VOICE)
    n = int(round(tl["dur"] * SR)) + 1
    voice = np.zeros(n, np.float32)
    lufs = []
    for ln in tl["lines"]:
        x = decode(os.path.join(voice_dir, ln["key"] + ".mp3"))
        lufs.append(loudness(x)[0])
        f = int(0.004 * SR)
        x[:f] *= np.linspace(0, 1, f)
        x[-f:] *= np.linspace(1, 0, f)
        i0 = int(round(ln["start"] * SR))
        seg = x[:max(0, n - i0)]
        voice[i0:i0 + len(seg)] += seg
    fx = np.zeros(n, np.float32)
    for s in tl["sounds"]:
        if s["kind"] in ("bell", "bell2", "chime", "pop"):
            y = sfx(s["kind"])
            i0 = int(round(s["t0"] * SR))
            seg = y[:max(0, n - i0)]
            fx[i0:i0 + len(seg)] += seg
    target = float(np.mean(lufs))
    got, _ = loudness(voice)
    gain = 10 ** ((target - got) / 20)
    os.makedirs(os.path.dirname(os.path.abspath(mp3)), exist_ok=True)
    for _ in range(3):                                  # the encoder's low-pass costs a few tenths of a dB
        mix_ = (voice + fx) * gain
        # the lines were normalised to a -1.5 dBTP ceiling: a limiter keeps the scene under it
        p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                            "-af", "alimiter=limit=0.83:attack=4:release=60:level=false",
                            "-c:a", "libmp3lame", "-b:a", BITRATE, "-ar", str(SR), mp3],
                           input=mix_.astype(np.float32).tobytes())
        if p.returncode:
            raise SystemExit(f"ffmpeg failed for {mp3}")
        out = decode(mp3)
        i_out, pk_out = loudness(out)
        if abs(i_out - target) < 0.15:
            break
        gain *= 10 ** ((target - i_out) / 20)
    al = S.merged_alignment(tl, envelope(voice * gain))
    al["loudness"] = {"lufs": round(i_out, 1), "true_peak": round(pk_out, 1), "lines_lufs": round(target, 1)}
    if json_path:
        os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
        json.dump(al, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return al, {"lufs": i_out, "true_peak": pk_out, "lines_lufs": target}
