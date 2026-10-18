"""Morfi's full scenes for the lab: audio, bake, merge, verification and previews.

    # 1. the scene audio from the existing voice lines (plain Python, ffmpeg on PATH)
    python scripts/ia3d/make_scenes.py audio [--only susto,sueno]
    # 2. bake each scene as the action Scene_<Key> on the rig (one Blender per scene can run at once)
    $B -b work/ia3d/morfi_ia_face3.blend --python scripts/ia3d/make_scenes.py -- bake --only susto \
        --out <dir>/scene_susto.blend [--fast]
    # 3. all the baked scenes into one file
    $B -b work/ia3d/morfi_ia_face3.blend --python scripts/ia3d/make_scenes.py -- merge \
        --parts <dir>/scene_*.blend --out work/ia3d/morfi_ia_scenes.blend
    # 4. checks and Eevee previews with the audio (look3 has the materials; the actions are appended)
    $B -b work/ia3d/morfi_ia_scenes.blend --python scripts/ia3d/make_scenes.py -- verify [--only susto]
    $B -b work/ia3d/morfi_ia_look3.blend --python scripts/ia3d/make_scenes.py -- preview \
        --src work/ia3d/morfi_ia_scenes.blend --only susto --out <dir>/preview [--res 50 --step 1]

Scene audio: web/public/voice/scenes/<key>.mp3 (96 kbps, the lines' loudness) and <key>.json (the
merged alignment for the lip-sync, see anim/scenes.py merged_alignment). Every action carries a
JSON string property "scene" (title, solo, audio, camera cues, lines).
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from anim import scenes as S  # noqa: E402

SR = 44100
SCENE_ACTION = "Scene_{}"


def action_name(key):
    return SCENE_ACTION.format(key[:1].upper() + key[1:])


def args_():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["audio", "bake", "merge", "verify", "preview", "sketch", "faces", "dump"])
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--parts", nargs="*", default=[])
    ap.add_argument("--src", default="")
    ap.add_argument("--fast", action="store_true", help="bake without the contact solvers (pose checks)")
    ap.add_argument("--res", type=int, default=50, help="preview resolution percent of 1280x720")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=-1)
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--cam", default="cues", help="cues (follow the camera cues) or a fixed cue name")
    ap.add_argument("--frames", default="", help="only these frames (comma separated), e.g. 270,300")
    ap.add_argument("--az", type=float, default=-12.0, help="preview camera azimuth (deg, + = his left)")
    return ap.parse_args(argv)


def keys_of(a):
    return [k for k in S.PLAN if not a.only or k in a.only.split(",")]


# ================================================================ audio
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


def audio(a):
    os.makedirs(S.OUT, exist_ok=True)
    for key in keys_of(a):
        tl = S.timeline(key)
        n = int(round(tl["dur"] * SR)) + 1
        voice = np.zeros(n, np.float32)
        lufs = []
        for ln in tl["lines"]:
            x = decode(os.path.join(S.VOICE, ln["key"] + ".mp3"))
            lufs.append(loudness(x)[0])
            f = int(0.004 * SR)                         # 4 ms fades: no clicks at the joins
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
        mp3 = os.path.join(S.OUT, key + ".mp3")
        for _ in range(3):                              # the encoder's low-pass costs a few tenths of a dB
            mix = (voice + fx) * gain
            # the lines were normalised to a -1.5 dBTP ceiling: a limiter keeps the scene under it
            p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                                "-af", "alimiter=limit=0.83:attack=4:release=60:level=false",
                                "-c:a", "libmp3lame", "-b:a", "96k", "-ar", str(SR), mp3],
                               input=mix.astype(np.float32).tobytes())
            if p.returncode:
                raise SystemExit(f"ffmpeg failed for {mp3}")
            out = decode(mp3)
            i_out, pk_out = loudness(out)
            if abs(i_out - target) < 0.15:
                break
            gain *= 10 ** ((target - i_out) / 20)
        al = S.merged_alignment(tl, envelope(voice * gain))
        al["loudness"] = {"lufs": round(i_out, 1), "true_peak": round(pk_out, 1), "lines_lufs": round(target, 1)}
        json.dump(al, open(os.path.join(S.OUT, key + ".json"), "w", encoding="utf-8"), ensure_ascii=False,
                  separators=(",", ":"))
        print(f"AUDIO {key}: {tl['dur']:.2f} s, {len(tl['lines'])} lines, {i_out:.1f} LUFS (lines {target:.1f}), "
              f"peak {pk_out:.1f} dBTP -> {mp3}")


# ================================================================ Blender side
def _bpy():
    import bpy  # noqa: F401  (only inside Blender)
    return bpy


def _reach(contacts, limit):
    """The reach cap for the next solves (contacts.set_max_reach when the motor has it)."""
    if hasattr(contacts, "set_max_reach"):
        contacts.set_max_reach(limit)
    else:
        contacts.MAX_REACH = limit or 1.08


class _keep_hands:
    """contacts.hands_keep_size when the motor has it (the hands do not inherit the IK stretch)."""

    def __init__(self, contacts, rig):
        self.cm = contacts.hands_keep_size(rig) if hasattr(contacts, "hands_keep_size") else None

    def __enter__(self):
        return self.cm.__enter__() if self.cm else self

    def __exit__(self, *exc):
        return self.cm.__exit__(*exc) if self.cm else False


REST_WIN = 15         # frames: one resting place on the skin for a hand held on his face
REST_TOL = (-0.0005, 0.0010)   # signed gap (m) a resting hand may keep: a hair in, a hair off


def rest_on_skin(contacts, rig, action, clip, reach=0.02, steps=12):
    """After the wide smoothing the resting place is an average of nearby contacts: on his round
    chin that sits a few mm inside (or off) the skin, and the per-frame re-contact can bounce
    between two fingers. Here each touch frame moves only along the skin's outward normal at the
    chosen spot, bisecting the signed gap to zero (moving out along it never brings the hand in).
    Returns (frames moved, worst |gap| after) in m."""
    moved, worst = 0, 0.0
    for spec in getattr(clip, "contacts", []):
        if "touch" not in spec:
            continue
        bone = f"hand_ik.{spec['side']}"
        fcs = contacts._loc_curves(action, bone)
        hand = bpy_objects()[f"Hand_{spec['side']}"]
        f0, f1 = spec["frames"]
        for f in range(f0, f1 + 1):
            contacts._frame(f)
            L0 = contacts._get_loc(fcs, f)
            sd = contacts._touch_error(spec, hand, step=2, slide_gain=0.0)[2]
            if REST_TOL[0] <= sd <= REST_TOL[1]:
                worst = max(worst, abs(sd))
                continue
            _, n = contacts._body_target(spec)
            dloc = np.linalg.solve(contacts._jacobian(rig, bone), n)    # 1 m along the normal

            def gap(t):
                contacts._set_loc(fcs, f, L0 + t * dloc)
                contacts._refresh(fcs)
                contacts._frame(f)
                return contacts._touch_error(spec, hand, step=2, slide_gain=0.0)[2]

            lo, hi = (0.0, reach) if sd < 0 else (-reach, 0.0)
            g_lo, g_hi = (sd, gap(hi)) if sd < 0 else (gap(lo), sd)
            if g_lo > 0 or g_hi < 0:                   # no zero in reach: keep the frame as it was
                gap(0.0)
                worst = max(worst, abs(sd))
                continue
            for _ in range(steps):
                mid = 0.5 * (lo + hi)
                g = gap(mid)
                if g < 0:
                    lo = mid
                else:
                    hi = mid
            g = gap(hi)                                # end just on / off the skin, never in it
            worst = max(worst, abs(g))
            moved += 1
    return moved, worst


def bpy_objects():
    return _bpy().data.objects


def bake_scene(key, fast=False):
    """One scene -> action Scene_<Key>, with the video pipeline's contact passes (as make_actions.py
    and videos/morfi-pos/tools/scene.py): bake -> reach cap -> hands out of the body -> smooth_ik
    -> touches (contacts.solve) -> smooth_touches -> hands out of the body again -> reach cap ->
    smooth_ik -> a wide smooth_touches (one resting place per touch) -> rest_on_skin -> smooth_ik;
    then the arms are rebaked to FK with a volume-kept stretch (contacts.rebake_arms), a held prop
    rides in the final hand (hold_prop, last) and everything is verified."""
    bpy = _bpy()
    from anim import contacts, rigmap
    t_start = time.time()
    tl = S.timeline(key)
    p = S.build(key, tl)
    clip = S.finish(p)
    rig = bpy.data.objects["Morfi_Rig"]
    rigmap.ensure_props(rig)
    name = action_name(key)
    act = rigmap.bake(rig, name, clip.channels(), clip.n)
    act["scene"] = json.dumps(S.meta(tl), ensure_ascii=False)
    print(f"BAKED {name}: {clip.n} frames, {len(clip.ch)} channels")
    held = list(clip.supports)
    clip.supports = []                                 # held props ride in the hand (hold_prop)
    touch_frames = [tuple(c["frames"]) for c in clip.contacts]
    report = {"key": key, "frames": clip.n, "max_reach": getattr(clip, "max_reach", None)}
    _reach(contacts, getattr(clip, "max_reach", None))  # a cartoon stretch the scene may ask for
    try:
        if not fast:
            with _keep_hands(contacts, rig):
                report["reach_pulled"] = contacts.clamp_reach(rig, act, clip.n)
                report["body_pushed"] = contacts.resolve_body(rig, act, clip.n, skip=touch_frames)
                contacts.smooth_ik(rig, act, clip)
                if clip.contacts:
                    contacts.solve(rig, act, clip)
                    contacts.smooth_touches(rig, act, clip)
                report["body_after"] = contacts.resolve_body(rig, act, clip.n, skip=touch_frames)
                report["reach_after"] = contacts.clamp_reach(rig, act, clip.n)
                contacts.smooth_ik(rig, act, clip, sigma=2.0, ramp=8)
                if clip.contacts:
                    # a hand held on his face for seconds while he talks: the per-frame solve can
                    # switch between fingers resting on the skin (the hand hops 2 cm sideways and
                    # back); one wide pass keeps one resting place, then the ramps are blended again
                    contacts.smooth_touches(rig, act, clip, win=REST_WIN)
                    report["rest_on_skin"] = rest_on_skin(contacts, rig, act, clip)
                    contacts.smooth_ik(rig, act, clip, sigma=2.0, ramp=8)
            if hasattr(contacts, "rebake_arms"):
                st = contacts.rebake_arms(rig, act, clip.n)
                report["rebake"] = st
                print("REBAKE " + ", ".join(f"{s_} stretch {v['stretch']:.3f} wrist {v['wrist_mm']:.2f} mm "
                                            f"dir {v['dir_deg']:.2f} deg" for s_, v in st.items()))
        # last: a held prop takes the hand's final path (anything that moved the hand after the
        # grip would leave the prop behind)
        for h in held:
            g0, g1 = contacts.hold_prop(rig, act, h["bone"], h["prop"], h["side"], h["frames"], h["ref"])
            report[f"held_{h['prop']}"] = [g0, g1]
            print(f"HELD {h['prop']}: palm gap {g0 * 1000 if g0 is not None else 'n/a'} mm -> "
                  f"{g1 * 1000 if g1 is not None else 'n/a'} mm")
        if not fast:
            clip.supports = [{"side": h["side"], "prop": h["prop"], "frames": h["frames"]} for h in held]
            ok, worst, _ = contacts.verify(rig, act, clip)
            report["contacts_ok"], report["worst"] = bool(ok), {k: float(v) for k, v in worst.items()}
            print(f"CONTACTS {name}: ok={ok} overlap {max(worst['pen'], 0) * 1000:.1f} mm press "
                  f"{worst['press'] * 1000:.1f} mm support {worst['support'] * 1000:.1f} mm "
                  f"touch {worst['touch'] * 1000:.1f} mm")
    finally:
        _reach(contacts, None)
    act["contacts"] = json.dumps({"contacts": clip.contacts, "supports": [
        {k: v for k, v in h.items()} for h in held]}, default=float)
    report["seconds"] = round(time.time() - t_start, 1)
    print(f"REPORT {json.dumps(report, default=float)}")
    return act


def bake(a):
    bpy = _bpy()
    from anim import rigmap
    if os.path.abspath(a.out) == os.path.abspath(bpy.data.filepath):
        sys.exit("--out must differ from the input .blend")
    keys = keys_of(a)
    for key in keys:
        bake_scene(key, a.fast)
    rig = bpy.data.objects["Morfi_Rig"]
    rigmap.assign(rig, bpy.data.actions[action_name(keys[0])])
    bpy.context.scene.render.fps = 30
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("DONE bake", a.out)


def refresh_alignment(tl):
    """The scene's metadata (camera cues, title, lines) in its <key>.json next to the audio, as on
    the action; the alignment and the envelope come from the audio and stay as they are."""
    path = os.path.join(S.OUT, tl["key"] + ".json")
    al = json.load(open(path, encoding="utf-8"))
    al.update(S.meta(tl))
    json.dump(al, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


def merge(a):
    """Scene actions from the per-scene files into the one the export reads."""
    bpy = _bpy()
    from anim import rigmap
    if os.path.abspath(a.out) == os.path.abspath(bpy.data.filepath):
        sys.exit("--out must differ from the input .blend")
    parts = []
    for pat in a.parts:
        parts += sorted(glob.glob(pat))
    if not parts:
        sys.exit(f"--parts: no file matches {' '.join(a.parts) or '(none given)'}")
    names = []
    for path in parts:
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.actions = [n for n in src.actions if n.startswith("Scene_")]
        for act in dst.actions:
            act.use_fake_user = True
            names.append(act.name)
            key = next(k for k in S.PLAN if action_name(k) == act.name)
            tl = S.timeline(key)
            if tl["frames"] != int(act.frame_end) + 1:
                raise SystemExit(f"{act.name}: baked {int(act.frame_end) + 1} frames, the timeline has "
                                 f"{tl['frames']}: bake it again")
            act["scene"] = json.dumps(S.meta(tl), ensure_ascii=False)     # camera cues may be newer
            refresh_alignment(tl)
            print("MERGED", act.name, "from", path)
    if not names:
        sys.exit("--parts: no Scene_ action in the files")
    for lib in list(bpy.data.libraries):
        bpy.data.libraries.remove(lib)
    rig = bpy.data.objects["Morfi_Rig"]
    rigmap.assign(rig, bpy.data.actions[sorted(names)[0]])
    bpy.context.scene.render.fps = 30
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print("DONE merge", len(names), a.out)


def verify(a):
    """Per scene: contacts.verify, the hands' signed gap to head and torso on every frame outside
    the touches (KD-tree, like check_clearance.py), and the hands' jitter (zig-zag acceleration)."""
    bpy = _bpy()
    from scipy.spatial import cKDTree
    from types import SimpleNamespace
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from anim import contacts, rigmap
    rig = bpy.data.objects["Morfi_Rig"]
    body = bpy.data.objects["Morfi_Body"]
    hands = {s: bpy.data.objects[f"Hand_{s}"] for s in ("L", "R")}

    def mask(ob, names, thr):
        idx = {g.index for g in ob.vertex_groups if g.name in names}
        m = np.zeros(len(ob.data.vertices), bool)
        for v in ob.data.vertices:
            m[v.index] = sum(g.weight for g in v.groups if g.group in idx) >= thr
        return m

    def coords(ob):
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, np.float32)
        no = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        me.vertices.foreach_get("normal", no)
        ev.to_mesh_clear()
        M = np.array(ob.matrix_world)
        return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3], no.reshape(-1, 3) @ M[:3, :3].T

    faced = contacts._faced(body)
    parts = {"head": mask(body, {"head"}, 0.95) & faced, "torso": mask(body, {"hips", "spine", "chest"}, 0.8) & faced}
    out = {}
    for key in keys_of(a):
        name = action_name(key)
        act = bpy.data.actions.get(name)
        if act is None:
            continue
        rigmap.assign(rig, act)
        spec = json.loads(act.get("contacts", "{}") or "{}")
        n = int(act.frame_end) + 1
        clip = SimpleNamespace(n=n, contacts=[dict(c, frames=tuple(c["frames"]), point=tuple(c["point"]))
                                              if "point" in c else dict(c, frames=tuple(c["frames"]))
                                              for c in spec.get("contacts", [])],
                               supports=[dict(s, frames=tuple(s["frames"])) for s in spec.get("supports", [])])
        t0 = time.time()
        ok, worst, rows = contacts.verify(rig, act, clip)
        touching = {s: np.zeros(n, bool) for s in ("L", "R")}
        for c in clip.contacts:
            if "touch" in c:
                f0, f1 = c["frames"]
                r = c.get("ramp", 6)
                touching[c["side"]][max(0, f0 - r):min(n, f1 + r + 1)] = True
        gaps = {f"{s}_{p}": [] for s in ("L", "R") for p in parts}
        tips = {s: [] for s in ("L", "R")}
        polys = contacts._body_parts(body)
        for f in range(0, n, a.step):
            contacts._frame(f)
            P, N = coords(body)
            trees = {k: BVHTree.FromPolygons([tuple(v) for v in P], polys[k]) for k in parts}
            for s, h in hands.items():
                H, _ = coords(h)
                H = H[::3]
                tips[s].append(np.array(rig.matrix_world @ rig.pose.bones[f"hand.{s}"].tail))
                for pname, m in parts.items():
                    # nearest vertex for the distance; for the points that come close, the side of the
                    # skin they are on from the nearest FACE (vertex normals lie a few cm away)
                    d, _ = cKDTree(P[m]).query(H)
                    g = float(d.min())
                    for q in H[d < 0.03]:
                        loc, nrm, _, dist = trees[pname].find_nearest(Vector(q), 0.03)
                        if loc is not None and (Vector(q) - loc).dot(nrm) < 0:
                            g = min(g, -dist)
                    gaps[f"{s}_{pname}"].append((f, g, bool(touching[s][f])))
        per = []                                          # each touch on its own: the worst gap and where
        for c in clip.contacts:
            if "touch" not in c:
                continue
            f0, f1 = c["frames"]
            hand = hands[c["side"]]
            gs = []
            for f in range(f0, f1 + 1, 2):
                contacts._frame(f)
                gs.append((abs(contacts._touch_error(c, hand, step=2)[2]), f))
            g, fw = max(gs)
            per.append({"side": c["side"], "touch": c["touch"], "frames": [f0, f1], "worst_mm": round(g * 1000, 1),
                        "at": fw, "mean_mm": round(float(np.mean([x for x, _ in gs])) * 1000, 1)})
        res = {"touches": per}
        res.update({"contacts_ok": bool(ok), "overlap_mm": round(max(worst["pen"], 0) * 1000, 2),
               "press_mm": round(worst["press"] * 1000, 2), "support_mm": round(worst["support"] * 1000, 2),
               "touch_mm": round(worst["touch"] * 1000, 2)})
        for k, rows_ in gaps.items():
            free = [g for f, g, t in rows_ if not t]
            inside = [(f, round(g * 1000, 1)) for f, g, t in rows_ if not t and g < -0.002]
            runs = []                                     # (first frame, last frame, deepest mm)
            for f, g in inside:
                if runs and f - runs[-1][1] <= a.step:
                    runs[-1] = [runs[-1][0], f, min(runs[-1][2], g)]
                else:
                    runs.append([f, f, g])
            res[k] = {"min_mm_free": round(min(free) * 1000, 1) if free else None, "inside_frames": len(inside),
                      "runs": runs}
        for s, P in tips.items():
            P = np.array(P)
            acc = np.linalg.norm(P[2:] - 2 * P[1:-1] + P[:-2], axis=1) * 1000
            d = np.diff(P, axis=0)
            flip = np.einsum("ij,ij->i", d[1:], d[:-1]) < 0
            res[f"jitter_{s}"] = {"max_acc_mm_f2": round(float(acc.max()), 1),
                                  "zig_frames": int((flip & (acc > 1.5)).sum())}
        res["seconds"] = round(time.time() - t0, 1)
        out[key] = res
        print(f"VERIFY {key} {json.dumps(res)}")
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)


# ---------------------------------------------------------------- previews
FRAMING = {   # camera cue -> (target z, distance, lens): what the web player's cue names mean
    "wide": (0.55, 3.5, 50), "medium": (0.58, 2.6, 50), "close": (0.66, 1.95, 50), "face": (0.72, 1.4, 50)}


def _cam_at(cues, t, az=-12.0, el=7.0):
    """Cut (with a 0.25 s ease) between cue framings; a slow push-in on each held shot."""
    idx = max(i for i, (tc, _) in enumerate(cues) if tc <= t + 1e-6)
    tc, name = cues[idx]
    z, dist, lens = FRAMING[name]
    hold = t - tc
    dist *= 1.0 - 0.025 * min(hold, 4.0) / 4.0
    if idx > 0 and hold < 0.25:                          # a quick ease from the previous framing
        pz, pd, _ = FRAMING[cues[idx - 1][1]]
        u = 0.5 - 0.5 * np.cos(np.pi * hold / 0.25)
        z, dist = pz + (z - pz) * u, pd + (dist - pd) * u
    a, e = np.radians(az + 3.0 * np.sin(t * 0.35)), np.radians(el)
    tgt = np.array([0.0, -0.05, z])
    pos = tgt + dist * np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])
    return pos, tgt, lens


def _studio(a):
    bpy = _bpy()
    import studio
    sc = bpy.context.scene
    cam, _ = studio.setup(sc, "eevee", a.samples, (1280, 720), a.res)
    ee = sc.eevee
    for attr, val in (("use_raytracing", False), ("use_fast_gi", False)):
        if hasattr(ee, attr):
            setattr(ee, attr, val)
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 88
    sc.render.use_motion_blur = False
    return cam


def render_scene(key, a, cam):
    """Frames of Scene_<Key> with the camera cut on its cues (or one fixed framing), then an MP4
    with the scene audio when every frame was rendered."""
    bpy = _bpy()
    from mathutils import Vector
    from anim import rigmap
    rig = bpy.data.objects["Morfi_Rig"]
    sc = bpy.context.scene
    act = bpy.data.actions.get(action_name(key))
    if act is None:
        print("no action", key)
        return
    rigmap.assign(rig, act)
    m = json.loads(act["scene"])
    cues = m["camera"] if a.cam == "cues" else [[0.0, a.cam]]
    root = os.path.abspath(a.out)
    out = os.path.join(root, key + ("" if a.cam == "cues" else "_" + a.cam))
    os.makedirs(out, exist_ok=True)
    n = int(act.frame_end) + 1
    end = n - 1 if a.end < 0 else min(a.end, n - 1)
    t0 = time.time()
    frames = [int(x) for x in a.frames.split(",")] if a.frames else list(range(a.start, end + 1, a.step))
    for f in frames:
        sc.frame_set(f)
        pos, tgt, lens = _cam_at(cues, f / 30.0, az=a.az)
        cam.location = Vector(pos)
        cam.rotation_euler = (Vector(tgt) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = lens
        cam.data.dof.focus_distance = float(np.linalg.norm(np.array(tgt) - pos))
        sc.render.filepath = os.path.join(out, f"f_{f:04d}.jpg")
        bpy.ops.render.render(write_still=True)
    print(f"RENDERED {key}: {len(frames)} frames in {time.time() - t0:.0f} s")
    if not a.frames and a.step == 1 and a.start == 0 and end == n - 1:
        mp4 = os.path.join(root, f"{key}.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "30", "-i", os.path.join(out, "f_%04d.jpg"),
                        "-i", os.path.join(S.OUT, key + ".mp3"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-shortest", mp4], check=True)
        print("PREVIEW", mp4)


def preview(a):
    bpy = _bpy()
    if a.src:
        with bpy.data.libraries.load(os.path.abspath(a.src), link=False) as (src, dst):
            dst.actions = [n for n in src.actions if n.startswith("Scene_")]
    cam = _studio(a)
    for key in keys_of(a):
        render_scene(key, a, cam)


def sketch(a):
    """Bake in memory (on the file opened, e.g. look3, never saved) and render: quick pose checks."""
    cam = _studio(a)
    for key in keys_of(a):
        bake_scene(key, a.fast)
        render_scene(key, a, cam)


def faces(a):
    """Face curves of every scene in the shape of morfi_live_anims.json ({fps, props, actions:
    {Scene_X: {frames, loop, props: {name: [per frame]}}}}) plus each scene's meta, for the web
    export (plain Python: the face is not touched by the contact passes, so this matches the bake)."""
    from anim.clip import FACE_PROPS
    out = {"fps": 30, "props": list(FACE_PROPS), "actions": {}, "scenes": {}}
    for key in keys_of(a):
        tl = S.timeline(key)
        clip = S.finish(S.build(key, tl))
        name = action_name(key)
        props = {}
        for k, default in FACE_PROPS.items():
            v = clip.ch.get(f"prop.{k}")
            props[k] = [round(float(x), 3) for x in (v if v is not None else np.full(clip.n, default))]
        out["actions"][name] = {"frames": clip.n, "loop": False, "props": props}
        out["scenes"][name] = S.meta(tl)
    path = a.out or os.path.join(os.path.dirname(os.path.dirname(HERE)), "work", "ia3d", "web",
                                 "morfi_live_scenes.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("FACES", path, os.path.getsize(path), "bytes", list(out["actions"]))


def dump(a):
    """Face curves of the baked scene actions (what the web JSON needs), for checking."""
    bpy = _bpy()
    for key in keys_of(a):
        act = bpy.data.actions[action_name(key)]
        print(key, act.frame_range[:], json.loads(act["scene"])["title"],
              sorted(fc.data_path for fc in act.fcurves if fc.data_path.startswith('["'))[:4])


if __name__ == "__main__":
    A = args_()
    {"audio": audio, "bake": bake, "merge": merge, "verify": verify, "preview": preview, "sketch": sketch,
     "faces": faces, "dump": dump}[A.cmd](A)
