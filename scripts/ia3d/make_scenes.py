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
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from anim import audiomix as AM  # noqa: E402
from anim import scenes as S  # noqa: E402

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
    ap.add_argument("--fk-passes", action="store_true", help="also the FK sleeve / contact / body passes (make_actions.py)")
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
def audio(a):
    """Scene audio: the lines with their pauses + the effects, levelled (anim/audiomix.py, shared with
    compose_audio.py)."""
    os.makedirs(S.OUT, exist_ok=True)
    for key in keys_of(a):
        tl = S.timeline(key)
        mp3 = os.path.join(S.OUT, key + ".mp3")
        _, st = AM.mix(tl, mp3, os.path.join(S.OUT, key + ".json"))
        print(f"AUDIO {key}: {tl['dur']:.2f} s, {len(tl['lines'])} lines, {st['lufs']:.1f} LUFS (lines "
              f"{st['lines_lufs']:.1f}), peak {st['true_peak']:.1f} dBTP -> {mp3}")


# ================================================================ Blender side
def _bpy():
    import bpy  # noqa: F401  (only inside Blender)
    return bpy


def bake_scene(key, fast=False, fk_passes=False):
    """One scene -> action Scene_<Key>, with the video pipeline's contact passes (anim/bakeclip.py,
    shared with bake_perf.py; as make_actions.py and videos/morfi-pos/tools/scene.py): bake -> reach cap
    -> hands out of the body -> smooth_ik -> touches (contacts.solve) -> smooth_touches -> hands out of
    the body again -> reach cap -> smooth_ik -> a wide smooth_touches (one resting place per touch) ->
    rest_on_skin -> smooth_ik; then the arms are rebaked to FK with a volume-kept stretch
    (contacts.rebake_arms), a held prop rides in the final hand (hold_prop, last) and everything is
    verified. fk_passes adds the FK sleeve / contact / body passes of make_actions.py (off for the
    lab's scenes, as they were baked)."""
    bpy = _bpy()
    from anim import bakeclip
    tl = S.timeline(key)
    p = S.build(key, tl)
    clip = S.finish(p)
    rig = bpy.data.objects["Morfi_Rig"]
    return bakeclip.bake_clip(rig, action_name(key), clip, meta=S.meta(tl), fast=fast, fk_passes=fk_passes)


def bake(a):
    bpy = _bpy()
    from anim import rigmap
    if os.path.abspath(a.out) == os.path.abspath(bpy.data.filepath):
        sys.exit("--out must differ from the input .blend")
    keys = keys_of(a)
    for key in keys:
        bake_scene(key, a.fast, a.fk_passes)
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
    the touches (KD-tree, like check_clearance.py), and the hands' jitter (anim/checks.py)."""
    bpy = _bpy()
    from anim import checks
    ck = checks.Checker()
    out = {}
    for key in keys_of(a):
        act = bpy.data.actions.get(action_name(key))
        if act is None:
            continue
        res = ck.run(act, a.step)
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
        bake_scene(key, a.fast, a.fk_passes)
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
