"""Bake, check and preview ANY performance module with the production passes of the lab's scenes.

Run it from plain Python (it starts Blender itself, temp files on D:); every command takes the
module file, the action name Test_<Id> and the .blend paths you choose:

    python scripts/ia3d/bake_perf.py check   --module D:/tmp/morfi/opus/perf.py --action Test_Opus
    python scripts/ia3d/bake_perf.py bake    --module D:/tmp/morfi/opus/perf.py --action Test_Opus --out D:/tmp/morfi/opus/perf.blend [--fast] [--no-fk-passes]
    python scripts/ia3d/bake_perf.py verify  --blend D:/tmp/morfi/opus/perf.blend --action Test_Opus [--step 2] [--sleeves] [--json out.json]
    python scripts/ia3d/bake_perf.py preview --blend D:/tmp/morfi/opus/perf.blend --action Test_Opus --out D:/tmp/morfi/opus/prev
                                             [--res 0.35] [--step 2] [--view cues|wide|medium|close|face|hands|handL|handR|side]
                                             [--range 10:25] [--frames 120,300] [--audio x.mp3] [--sheet 24] [--no-follow]

The module (a .py file anywhere; its folder is on sys.path, so it may import its own helpers)
defines
    META  = {"title": "Un día de ventas de Morfi",       # Spanish (Mexico), shown in the lab
             "timeline": "timeline.json",                 # the compose_audio.py input (path relative to the module)
             "camera": [[0.0, "wide"], [8.5, "medium"], ...],   # [second, wide|medium|close|face]
             "solo": False,                               # he talks to himself, not to the camera
             "audio": "voice/tests/opus.mp3"}             # optional: where the lab will find it (default: from the action name)
    def build(tl):  # or build() with no argument
        ...return the Performance (anim.performance / anim.scenes.Scene.finish()) or a finished Clip

`tl` is anim.scenes.timeline_from_file(META["timeline"], META): the voice lines on the timeline (words,
lip-sync data) in the shape anim.scenes.Scene, Performance.speak and Acting.talk expect.

bake  = the passes of make_scenes.py (anim/bakeclip.py): bake, reach cap, hands out of the body,
        touches solved and smoothed, rest on the skin, IK -> FK arm rebake with the volume-kept stretch,
        held props, contact check; plus (default on, --no-fk-passes to skip) the FK passes of
        make_actions.py: sleeve swivel, contact refine and FK body pass. --fast = no contact solvers.
verify = contacts, the hands against head and torso on every frame outside the touches, jitter, arm
        stretch; --sleeves adds check_sleeves.py (hand / forearm against the cuff) on the final look.
preview = Eevee frames, an mp4 with the audio, a contact sheet; --view hands is a close-up that follows
        the hands. Opens the final look (morfi_ia_look7.blend) and appends the action from --blend.
"""
import argparse
import importlib.util
import inspect
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from anim import launch  # noqa: E402

FK_PASSES_DEFAULT = True         # the FK sleeve / contact / body passes of make_actions.py (the scenes lack them)
ARM_STRETCH_MAX = 1.15           # an arm stretched more than this reads as rubber (the lab's scenes reach 1.146; docs/motor.md §7)
VIEWS = ("cues", "wide", "medium", "close", "face", "hands", "handL", "handR", "side")


def argv_of():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, module=False, blend=False):
        p.add_argument("--action", required=True, help="Test_<Id>, e.g. Test_Opus")
        if module:
            p.add_argument("--module", required=True, help="the performance .py file (build() + META)")
        if blend:
            p.add_argument("--blend", required=True, help="the .blend that bake wrote (it holds the action)")

    c = sub.add_parser("check", help="build the module in plain Python (no Blender): META, frames, NaN, ranges")
    common(c, module=True)
    b = sub.add_parser("bake", help="bake the module into --out with the production passes")
    common(b, module=True)
    b.add_argument("--out", required=True, help="the .blend to write (not the input)")
    b.add_argument("--base", default=launch.FACE3, help="input .blend (default morfi_ia_face3.blend)")
    b.add_argument("--fast", action="store_true", help="no contact solvers: a quick pose check")
    b.add_argument("--no-fk-passes", action="store_true", help="skip the FK sleeve / contact / body passes")
    v = sub.add_parser("verify", help="measure the baked action")
    common(v, blend=True)
    v.add_argument("--step", type=int, default=2, help="check every Nth frame")
    v.add_argument("--json", default="", help="write the numbers here")
    v.add_argument("--sleeves", action="store_true", help="also check_sleeves.py on the final look")
    v.add_argument("--sleeves-step", type=int, default=4)
    v.add_argument("--look", default=launch.LOOK7, help="the .blend with materials (for --sleeves)")
    p = sub.add_parser("preview", help="Eevee frames + mp4 with audio + contact sheet")
    common(p, blend=True)
    p.add_argument("--out", required=True, help="folder for frames, the mp4 and sheet.jpg")
    p.add_argument("--look", default=launch.LOOK7, help="the .blend with materials (default morfi_ia_look7.blend)")
    p.add_argument("--res", type=float, default=0.35, help="resolution as a fraction of 1280x720")
    p.add_argument("--step", type=int, default=2, help="render every Nth frame (the mp4 plays in real time)")
    p.add_argument("--view", default="cues", choices=VIEWS, help="cues = the lab's camera cuts; hands = close-up of the hands")
    p.add_argument("--range", default="", help="seconds to render, e.g. 10:25")
    p.add_argument("--frames", default="", help="only these frames (comma separated); no mp4")
    p.add_argument("--audio", default="", help="mp3 for the mp4 (default: the one the action was baked with)")
    p.add_argument("--sheet", type=int, default=24, help="thumbnails in sheet.jpg (0 = none)")
    p.add_argument("--samples", type=int, default=8)
    p.add_argument("--az", type=float, default=-12.0, help="camera azimuth (deg, + = his left)")
    p.add_argument("--no-follow", action="store_true", help="the camera does not follow the root")
    p.add_argument("--no-label", action="store_true", help="no frame number / time on the mp4")
    return ap.parse_args(argv)


# ================================================================ the module
def load_module(path):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        sys.exit(f"ERROR: no module file {path}")
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("perf_module_" + os.path.splitext(os.path.basename(path))[0], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for need in ("build", "META"):
        if not hasattr(mod, need):
            sys.exit(f"ERROR: {path} must define {need} (see the docstring of bake_perf.py)")
    return mod


def full_meta(mod, action, path):
    """META of the module with the defaults filled in (audio path from the action name, timeline resolved)."""
    meta = dict(mod.META)
    pid = launch.action_id(action)
    problems = []
    if not str(meta.get("title", "")).strip():
        problems.append("META['title'] is missing")
    tpath = meta.get("timeline")
    if not tpath:
        problems.append("META['timeline'] is missing: the timeline JSON that compose_audio.py reads")
    else:
        meta["timeline"] = tpath if os.path.isabs(tpath) else os.path.join(os.path.dirname(os.path.abspath(path)), tpath)
        if not os.path.exists(meta["timeline"]):
            problems.append(f"timeline file {meta['timeline']} does not exist")
    meta.setdefault("audio", f"voice/tests/{pid}.mp3")
    meta.setdefault("solo", False)
    cams = meta.get("camera")
    if not cams:
        problems.append("META['camera'] is empty: give at least [[0.0, 'medium']]")
    else:
        ts = [c[0] for c in cams]
        if ts != sorted(ts) or ts[0] > 0.01:
            problems.append("META['camera'] must be sorted by time and start at 0.0")
    if problems:
        sys.exit("ERROR: " + "; ".join(problems))
    return meta, pid


def build_clip(path, action):
    """(clip, tl, meta, module): the module's build() run on its timeline."""
    from anim import scenes as S
    mod = load_module(path)
    meta, pid = full_meta(mod, action, path)
    try:
        tl = S.timeline_from_file(meta["timeline"], meta, key=pid)
    except S.TimelineError as e:
        sys.exit(f"ERROR: {meta['timeline']}: {e}")
    wants_tl = any(p.default is inspect.Parameter.empty for p in inspect.signature(mod.build).parameters.values())
    out = mod.build(tl) if wants_tl else mod.build()
    if hasattr(out, "channels") and hasattr(out, "ch"):
        clip = out
    elif hasattr(out, "build") and hasattr(out, "c"):
        clip = S.finish(out)
    else:
        sys.exit("ERROR: build() must return the Performance (e.g. Scene.finish()) or a finished Clip, got "
                 f"{type(out).__name__}")
    if clip.n != tl["frames"]:
        sys.exit(f"ERROR: the performance has {clip.n} frames but the timeline is {tl['frames']} frames "
                 f"({tl['dur']:.2f} s): build it with Scene(tl, ...) / Performance(tl['frames'])")
    return clip, tl, meta, mod


def audio_source(meta):
    """The composed mp3 next to the timeline (compose_audio.py default), or META['audio_file']."""
    own = meta.get("audio_file")
    if own:
        return own if os.path.isabs(own) else os.path.join(os.path.dirname(meta["timeline"]), own)
    return os.path.splitext(meta["timeline"])[0] + ".mp3"


# ================================================================ check (plain Python)
def cmd_check(a):
    import numpy as np
    clip, tl, meta, mod = build_clip(a.module, a.action)
    bad, notes = [], []
    for k, v in clip.ch.items():
        arr = np.asarray(v, float)
        if not np.all(np.isfinite(arr)):
            bad.append(f"channel {k} has NaN / infinite values at frames {np.where(~np.isfinite(arr))[0][:5].tolist()}")
    for k in ("upper_arm.L.sy", "upper_arm.R.sy", "forearm.L.sy", "forearm.R.sy"):
        if k in clip.ch and np.max(clip.ch[k]) > ARM_STRETCH_MAX + 0.02:
            notes.append(f"{k} reaches {np.max(clip.ch[k]):.2f} (> {ARM_STRETCH_MAX}: the arm reads as rubber)")
    for spec in list(clip.contacts) + list(clip.supports):
        f0, f1 = spec["frames"]
        if not (0 <= f0 <= f1 < clip.n):
            bad.append(f"a contact {spec} lies outside the {clip.n} frames")
    audio = audio_source(meta)
    if not os.path.exists(audio):
        notes.append(f"the composed audio {audio} does not exist yet: run compose_audio.py")
    ts = [c[0] for c in meta["camera"]]
    if ts and ts[-1] > tl["dur"]:
        notes.append(f"the last camera cue at {ts[-1]} s is after the end ({tl['dur']:.1f} s)")
    print(f"CHECK {a.action}: {clip.n} frames = {tl['dur']:.2f} s, {len(tl['lines'])} voice lines, "
          f"{len(clip.ch)} channels, {len(clip.contacts)} contacts, {len(clip.supports)} supports, "
          f"max_reach {getattr(clip, 'max_reach', None)}")
    print(f"  title {meta['title']!r}, solo {meta['solo']}, camera cues {len(meta['camera'])}, audio -> {meta['audio']}")
    for n in notes:
        print("  NOTE:", n)
    for b in bad:
        print("  ERROR:", b)
    print("CHECK", "FAILED" if bad else "OK")
    return 1 if bad else 0


# ================================================================ bake (Blender)
def cmd_bake(a):
    import bpy
    from anim import bakeclip, rigmap
    from anim import scenes as S
    launch.action_id(a.action)
    if os.path.abspath(a.out) == os.path.abspath(bpy.data.filepath):
        sys.exit("ERROR: --out must differ from the input .blend")
    clip, tl, meta, mod = build_clip(a.module, a.action)
    rig = bpy.data.objects["Morfi_Rig"]
    sc = S.meta(tl)
    sc.update(module=os.path.abspath(a.module), action=a.action, audio_src=audio_source(meta))
    t0 = time.time()
    act = bakeclip.bake_clip(rig, a.action, clip, meta=sc, fast=a.fast, fk_passes=not a.no_fk_passes and not a.fast and FK_PASSES_DEFAULT)
    act.use_fake_user = True
    rigmap.assign(rig, act)
    bpy.context.scene.render.fps = 30
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print(f"DONE bake {a.action}: {clip.n} frames in {time.time() - t0:.0f} s -> {a.out}")


# ================================================================ verify (Blender)
def bake_lines(act):
    """The bake report stored on the action as a few readable lines, and the issues it implies."""
    rep = json.loads(act.get("bake_report", "{}") or "{}")
    lines, issues = [], []
    if not rep:
        return ["  (the action has no bake report)"], issues
    lines.append(f"  bake: {rep.get('frames')} frames in {rep.get('seconds')} s, reach pulled {rep.get('reach_pulled')}, "
                 f"body pushed {rep.get('body_pushed')}/{rep.get('body_after')}, contacts_ok={rep.get('contacts_ok')}")
    for side, st in (rep.get("rebake") or {}).items():
        lines.append(f"  arm {side}: stretch {st.get('stretch')}, wrist error {st.get('wrist_mm')} mm, direction {st.get('dir_deg')} deg")
        if st.get("stretch", 1.0) > ARM_STRETCH_MAX:
            issues.append(f"arm {side} stretches to {st['stretch']} (> {ARM_STRETCH_MAX}): rubber arm, bring the hand closer")
    for k in ("sleeves", "refine", "body_fk"):
        if rep.get(k):
            lines.append(f"  {k}: " + ", ".join(f"{s} {v[0]} frames, gap {v[1]} -> {v[2]} mm" for s, v in rep[k].items()))
    return lines, issues


def cmd_verify(a):
    import bpy
    from anim import checks
    act = bpy.data.actions.get(a.action)
    if act is None:
        sys.exit(f"ERROR: no action {a.action} in {bpy.data.filepath}: {[x.name for x in bpy.data.actions]}")
    fps = 30
    res = checks.Checker().run(act, a.step)
    issues = checks.issues_of(res, fps)
    n = int(act.frame_end) + 1
    print(f"VERIFY {a.action}: {n} frames = {n / fps:.1f} s, every {a.step}th frame checked in {res['seconds']} s")
    print(f"  contacts: ok={res['contacts_ok']} overlap {res['overlap_mm']} mm, press {res['press_mm']} mm, "
          f"support {res['support_mm']} mm, touch {res['touch_mm']} mm")
    for t in res["touches"]:
        print(f"  touch {t['side']} on the {t['touch']}: frames {t['frames'][0]}-{t['frames'][1]}, worst {t['worst_mm']} mm "
              f"at {t['at']}, mean {t['mean_mm']} mm")
    print("  closest to the skin outside the touches: " + " | ".join(
        f"{k} {res[k]['min_mm_free']} mm" for k in ("L_head", "L_torso", "R_head", "R_torso")))
    print("  hand jitter (buzz = reverses 3 samples in a row; waves reverse slower): " + " | ".join(
        f"{s} buzz {res[f'jitter_{s}']['buzz_frames']}, zig {res[f'jitter_{s}']['zig_frames']}" for s in ("L", "R")))
    lines, more = bake_lines(act)
    print("\n".join(lines))
    issues += more
    print(f"VERIFY ISSUES: {len(issues)}")
    for i in issues:
        print("  -", i)
    res["issues"] = issues
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)) or ".", exist_ok=True)
        json.dump(res, open(a.json, "w", encoding="utf-8"), indent=1)


def sleeves_report(a):
    """check_sleeves.py on the final look with the action appended: the hand / forearm against the cuff."""
    out = os.path.join(tempfile.gettempdir(), f"sleeves_{a.action}.json")
    args = ["--action", a.action, "--actions-from", os.path.abspath(a.blend), "--prefix", "Test_",
            "--step", a.sleeves_step, "--json", out]
    rc = launch.run_blender(a.look, os.path.join(HERE, "check_sleeves.py"), args)
    if rc or not os.path.exists(out):
        print("SLEEVES check_sleeves.py failed (exit code", rc, ")")
        return 1
    res = json.load(open(out, encoding="utf-8"))[a.action]
    issues = []
    for side, vals in res.items():
        for k, lim in (("out_hand", 10.0), ("out_skin", 3.0), ("cross_thumb", 3.0), ("cross_fingers", 3.0), ("cross_palm", 3.0)):
            mm, f = vals[k]
            if mm > lim:
                issues.append(f"sleeve {side} {k} {mm} mm at frame {f} ({f / 30:.2f} s) (limit {lim:g})")
    print(f"SLEEVES {a.action}: " + " | ".join(f"{s}: " + " ".join(f"{k} {v[k][0]}" for k in v) for s, v in res.items()) + " (mm)")
    print(f"SLEEVES ISSUES: {len(issues)}")
    for i in issues:
        print("  -", i)
    return 0


# ================================================================ preview (Blender)
def frame_list(a, n, fps=30):
    if a.frames:
        return [int(x) for x in a.frames.split(",")]
    f0, f1 = 0, n - 1
    if a.range:
        t0, _, t1 = a.range.partition(":")
        f0 = max(0, int(round(float(t0) * fps)))
        f1 = min(n - 1, int(round(float(t1) * fps))) if t1 else n - 1
    return list(range(f0, f1 + 1, max(1, a.step)))


def sample_tracks(rig, frames, hands, stride=3):
    """World positions of the root and the hands every `stride` frames (a pass without rendering), smoothed:
    the preview camera follows them without jitter. Returns functions frame -> numpy vector."""
    import bpy
    import numpy as np
    from scipy.ndimage import uniform_filter1d
    sc = bpy.context.scene
    keys = sorted(set(frames[::stride]) | {frames[0], frames[-1]})
    rows = {"root": [], "hands": [], "sep": []}
    for f in keys:
        sc.frame_set(f)
        rows["root"].append(np.array(rig.matrix_world @ rig.pose.bones["root"].head))
        pts = []
        for s in hands:
            pb = rig.pose.bones[f"hand.{s}"]
            pts.append(np.array(rig.matrix_world @ ((pb.head + pb.tail) / 2)))
        rows["hands"].append(np.mean(pts, axis=0) if pts else np.zeros(3))
        rows["sep"].append(float(np.linalg.norm(pts[0] - pts[1])) if len(pts) == 2 else 0.0)
    k = np.array(keys, float)
    win = max(1, int(round(24 / stride)))

    def fn(name):
        arr = uniform_filter1d(np.array(rows[name]), win, axis=0, mode="nearest")
        return lambda f: np.array([np.interp(f, k, arr[:, i]) for i in range(arr.shape[1])]) if arr.ndim > 1 else float(np.interp(f, k, arr))
    return fn("root"), fn("hands"), fn("sep")


def camera_pose(a, MS, cues, t, f, tracks):
    import numpy as np
    root, hands, sep = tracks
    off = np.array([root(f)[0], root(f)[1], 0.0]) if not a.no_follow else np.zeros(3)
    if a.view in ("hands", "handL", "handR"):
        h = hands(f)
        dist = 0.62 if a.view != "hands" else float(np.clip(0.62 + 1.6 * sep(f), 0.62, 1.7))
        az, el = math.radians(a.az - 8.0), math.radians(12.0)
        tgt = np.array(h)
        pos = tgt + dist * np.array([math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)])
        return pos, tgt, 50
    if a.view == "side":
        pos, tgt, lens = MS._cam_at([[0.0, "medium"]], t, az=88.0)
    elif a.view == "cues":
        pos, tgt, lens = MS._cam_at(cues, t, az=a.az)
    else:
        pos, tgt, lens = MS._cam_at([[0.0, a.view]], t, az=a.az)
    return pos + off, tgt + off, lens


def label_filter(first, step, t0):
    """ffmpeg drawtext: the source frame number and the time in the take, bottom left (escapes as ffmpeg wants)."""
    font = r"C\:/Windows/Fonts/arial.ttf"
    text = r"f %{eif\:n*" + str(step) + "+" + str(first) + r"\:d}   t %{pts\:hms\:" + f"{t0:.3f}" + "}"
    return f"drawtext=fontfile='{font}':text='{text}':x=8:y=h-th-8:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.55"


def make_mp4(a, frames, out_dir, mp4, audio):
    """The rendered frames at real speed (every `step`th frame at 30/step fps) + the audio from the same second."""
    first, step = frames[0], max(1, a.step)
    lst = os.path.join(out_dir, "frames.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for f in frames:
            fh.write(f"file 'f_{f:05d}.jpg'\nduration {step / 30.0:.6f}\n")
        fh.write(f"file 'f_{frames[-1]:05d}.jpg'\n")
    vf = "pad=ceil(iw/2)*2:ceil(ih/2)*2"
    if not a.no_label:
        vf = label_filter(first, step, first / 30.0) + "," + vf
    has_audio = bool(audio) and os.path.exists(audio)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst]
    if has_audio:
        cmd += ["-ss", f"{first / 30.0:.3f}", "-i", audio]
    cmd += ["-vf", vf, "-r", f"{30 / step:g}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21"]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    r = subprocess.run(cmd + [mp4], capture_output=True)
    os.remove(lst)
    if r.returncode and not a.no_label:           # no font / drawtext on this machine: the same without the label
        a.no_label = True
        return make_mp4(a, frames, out_dir, mp4, audio)
    if r.returncode:
        print("ffmpeg failed:", r.stderr.decode("utf-8", "replace")[-400:])
        return False
    return True


def make_sheet(frames, out_dir, sheet, cols=6):
    from PIL import Image, ImageDraw
    count = max(1, min(sheet, len(frames)))
    pick = [frames[round(i * (len(frames) - 1) / max(1, count - 1))] for i in range(count)] if count > 1 else [frames[0]]
    rendered = {f: os.path.join(out_dir, f"f_{f:05d}.jpg") for f in pick}
    thumbs = []
    for f, p in rendered.items():
        im = Image.open(p).convert("RGB")
        w = 320
        im = im.resize((w, int(im.height * w / im.width)))
        ImageDraw.Draw(im).text((6, 4), f"f {f}  t {f / 30:.1f}s", fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        thumbs.append(im)
    rows = math.ceil(len(thumbs) / cols)
    tw, th = thumbs[0].size
    img = Image.new("RGB", (cols * tw, rows * th), (30, 34, 44))
    for i, t in enumerate(thumbs):
        img.paste(t, ((i % cols) * tw, (i // cols) * th))
    path = os.path.join(out_dir, "sheet.jpg")
    img.save(path, quality=88)
    return path


def cmd_preview(a):
    import bpy
    import numpy as np
    from mathutils import Vector
    from anim import rigmap
    import make_scenes as MS
    with bpy.data.libraries.load(os.path.abspath(a.blend), link=False) as (src, dst):
        dst.actions = [n for n in src.actions if n == a.action]
    act = bpy.data.actions.get(a.action)
    if act is None:
        sys.exit(f"ERROR: no action {a.action} in {a.blend}")
    act.use_fake_user = True
    rig = bpy.data.objects["Morfi_Rig"]
    sc = bpy.context.scene
    rigmap.assign(rig, act)
    meta = json.loads(act["scene"])
    n = int(act.frame_end) + 1
    frames = frame_list(a, n)
    if not frames:
        sys.exit("ERROR: no frames to render (check --range / --frames)")
    cam = MS._studio(SimpleNamespace(samples=a.samples, res=max(10, int(round(a.res * 100)))))
    tracks = sample_tracks(rig, frames, ("L", "R") if a.view not in ("handL", "handR") else (a.view[-1],) * 2)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    for old in os.listdir(out):
        if old.startswith("f_") and old.endswith(".jpg"):
            os.remove(os.path.join(out, old))
    t0 = time.time()
    for i, f in enumerate(frames):
        sc.frame_set(f)
        pos, tgt, lens = camera_pose(a, MS, meta["camera"], f / 30.0, f, tracks)
        cam.location = Vector(pos)
        cam.rotation_euler = (Vector(tgt) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = lens
        cam.data.dof.focus_distance = float(np.linalg.norm(np.array(tgt) - pos))
        sc.render.filepath = os.path.join(out, f"f_{f:05d}.jpg")
        bpy.ops.render.render(write_still=True)
        if i % 100 == 99:
            print(f"RENDERED {i + 1}/{len(frames)} frames, {time.time() - t0:.0f} s", flush=True)
    print(f"RENDERED {len(frames)} frames in {time.time() - t0:.0f} s -> {out} (f_<frame>.jpg)")
    if a.sheet:
        print("SHEET", make_sheet(frames, out, a.sheet))
    if not a.frames:                                         # a contiguous range: the video, with the audio
        audio = a.audio or meta.get("audio_src", "")
        mp4 = os.path.join(out, f"{a.action}_{a.view}.mp4")
        if make_mp4(a, frames, out, mp4, audio):
            print("PREVIEW", mp4, "(with audio)" if audio and os.path.exists(audio) else "(no audio found)")
    print("DONE preview")


# ================================================================ entry
def run_in_blender(a):
    {"bake": cmd_bake, "verify": cmd_verify, "preview": cmd_preview}[a.cmd](a)


def run_wrapper(a, argv):
    """Plain Python: start Blender on the right input .blend with this same command."""
    script = os.path.abspath(__file__)
    if a.cmd == "check":
        return cmd_check(a)
    blend = {"bake": lambda: a.base, "verify": lambda: a.blend, "preview": lambda: a.look}[a.cmd]()
    rc = launch.run_blender(blend, script, argv)
    if rc == 0 and a.cmd == "verify" and a.sleeves:
        rc = sleeves_report(a)
    return rc


if __name__ == "__main__":
    A = parse(argv_of())
    if launch.in_blender():
        if A.cmd == "check":
            sys.exit(cmd_check(A))
        run_in_blender(A)
    else:
        sys.exit(run_wrapper(A, sys.argv[1:]))
