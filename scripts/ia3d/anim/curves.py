"""Animation curves sampled per frame (pure numpy, no Blender).

A channel is a 1-D array with one value per frame. Keys are interpolated with
monotone cubic Hermite splines (no overshoot between keys, like Blender's
"auto clamped"), so every overshoot or settle in an action is a deliberate key.
"""
import math

import numpy as np


def keys(n, pts, loop=False):
    """Sample keys [(frame, value), ...] over n frames with monotone cubic interpolation.

    With loop=True the curve is periodic: value at frame n equals value at frame 0.
    """
    pts = sorted(pts)
    t = np.array([p[0] for p in pts], float)
    v = np.array([p[1] for p in pts], float)
    if loop:
        t = np.concatenate([t[-1:] - n, t, t[:1] + n])
        v = np.concatenate([v[-1:], v, v[:1]])
    if len(t) == 1:
        return np.full(n, v[0])
    d = np.diff(v) / np.diff(t)
    m = np.zeros_like(v)
    same = d[:-1] * d[1:] > 0             # harmonic mean of the slopes where they agree in sign
    m[1:-1][same] = 2 / (1 / d[:-1][same] + 1 / d[1:][same])
    m[0], m[-1] = (d[0] if loop else 0.0), (d[-1] if loop else 0.0)
    f = np.arange(n, dtype=float)
    out = np.empty(n)
    idx = np.clip(np.searchsorted(t, f, side="right") - 1, 0, len(t) - 2)
    t0, t1 = t[idx], t[idx + 1]
    h = t1 - t0
    s = np.clip((f - t0) / h, 0, 1)
    h00 = 2 * s**3 - 3 * s**2 + 1
    h10 = s**3 - 2 * s**2 + s
    h01 = -2 * s**3 + 3 * s**2
    h11 = s**3 - s**2
    out = h00 * v[idx] + h10 * h * m[idx] + h01 * v[idx + 1] + h11 * h * m[idx + 1]
    out = np.where(f < t[0], v[0], out)
    out = np.where(f > t[-1], v[-1], out)
    return out


def sine(n, period, amp, phase=0.0, offset=0.0):
    """Sine with a period in frames (choose n / period integer for seamless loops)."""
    f = np.arange(n, dtype=float)
    return offset + amp * np.sin(2 * math.pi * (f / period + phase))


def noise(n, period, amp, seed=0, loop=True):
    """Smooth value noise: random keys every `period` frames, monotone-interpolated."""
    rng = np.random.default_rng(seed)
    count = max(2, int(round(n / period)))
    pts = [(i * n / count, rng.uniform(-1, 1) * amp) for i in range(count)]
    if not loop:
        pts.append((n, rng.uniform(-1, 1) * amp))
    return keys(n, pts, loop=loop)


def delay(x, frames, loop=False):
    """Delay a channel by a (fractional) number of frames: overlapping action."""
    n = len(x)
    f = np.arange(n) - frames
    if loop:
        return np.interp(f % n, np.arange(n + 1), np.concatenate([x, x[:1]]))
    return np.interp(f, np.arange(n), x)


def spring(drive, freq=2.2, damping=0.28, fps=30, loop=False):
    """Damped spring response x'' = w^2 (drive - x) - 2 z w x'. Returns x.

    For looping clips the spring is run three times over and the last pass kept,
    so the settled state at the end matches the start.
    """
    w = 2 * math.pi * freq
    dt = 1.0 / fps
    passes = 3 if loop else 1
    x, v = float(drive[0]), 0.0
    out = np.empty(len(drive))
    for _ in range(passes):
        for i, target in enumerate(drive):
            # semi-implicit Euler with 4 substeps (stable for these frequencies)
            for _ in range(4):
                a = w * w * (target - x) - 2 * damping * w * v
                v += a * dt / 4
                x += v * dt / 4
            out[i] = x
    return out


def jiggle(accel, freq=3.0, damping=0.22, gain=1.0, fps=30, loop=False):
    """Secondary motion of a soft appendage driven by its parent's acceleration."""
    return spring(-gain * np.asarray(accel), freq, damping, fps, loop)


def accel(x, fps=30, loop=False):
    if loop:
        return (np.roll(x, -1) - 2 * x + np.roll(x, 1)) * fps * fps
    a = np.zeros_like(x)
    a[1:-1] = (x[2:] - 2 * x[1:-1] + x[:-2]) * fps * fps
    return a


def blink_track(n, times, close=3, hold=1, open_=5):
    """Blink curve (0 open .. 1 closed): fast close, short hold, slower open."""
    out = np.zeros(n)
    for t0 in times:
        pts = [(t0, 0.0), (t0 + close, 1.0), (t0 + close + hold, 1.0), (t0 + close + hold + open_, 0.0)]
        seg = keys(n, [(0, 0.0)] + pts + [(n, 0.0)])
        out = np.maximum(out, seg)
    return out
