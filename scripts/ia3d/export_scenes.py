"""Export the full scenes (long performances with voice) for the web lab, apart from the main GLB.

blender -b work/ia3d/<final look>.blend --python scripts/ia3d/export_scenes.py -- \
    --scenes work/ia3d/morfi_ia_scenes.blend \
    --pos "D:/MIS PROYECTOS/MORFI PET/MORFI PET/videos/morfi-pos/blender/pos_video.blend" \
    --pos-audio "D:/MIS PROYECTOS/MORFI PET/MORFI PET/videos/morfi-pos/audio/mix.wav" \
    --out work/ia3d/web/morfi_live_scenes.glb --json work/ia3d/web/morfi_live_scenes.json \
    --audio-dir web/public/voice/scenes

The scenes are minutes of animation that most visitors never play, so they travel in an
animation-only GLB (just the rig's bone nodes, same names as morfi_live.glb) that the viewer loads
when someone opens "Escenas". Their face curves (the rig's custom properties: glTF has no channel
for them) go to a JSON with the title, the audio file and the camera cues of each scene:

  {"fps": 30, "scenes": {"<Action>": {"title", "group": "scene" | "video", "frames", "audio", "solo",
                                      "props": {<18 FACE_PROPS>: [per frame]}, "camera": [[t, shot], ...]}}}

Scene_* actions come from make_scenes.py (their metadata is a JSON string custom property on the action);
POS_Video is the approved POS tutorial performance, taken as it is from the video project (its camera
becomes coarse camera cues for the viewer's cinema camera).
"""
import argparse
import json
import math
import os
import subprocess
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from anim.clip import FACE_PROPS  # noqa: E402

POS = "POS_Video"
POS_META = {"title": "Tutorial del punto de venta", "group": "video", "solo": False}
EYES_Z = 0.705                                   # eye height (m), what the cinema camera frames


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", default="")
    ap.add_argument("--pos", default="")
    ap.add_argument("--pos-audio", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--audio-dir", required=True)
    return ap.parse_args(argv)


def fcurves(act):
    """Every fcurve of an action (layered actions of Blender 4.4+ and the legacy list)."""
    out = list(getattr(act, "fcurves", []) or [])
    if out:
        return out
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out


def append_actions(path, wanted):
    """Append the actions of another .blend whose name passes `wanted` (the file is only read)."""
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        names = [n for n in src.actions if wanted(n)]
        dst.actions = list(names)      # a copy: Blender may rewrite the list it is given
    for name, act in zip(names, dst.actions):
        if act is not None and act.name != name:
            # Blender gave it a '.001' because a same-named action is already here: that one goes
            old = bpy.data.actions.get(name)
            if old is not None:
                bpy.data.actions.remove(old)
            act.name = name
    return [a for a in dst.actions if a is not None]


def meta_of(act):
    """The scene metadata stored by make_scenes.py: any JSON-object string property with a title."""
    for k in act.keys():
        v = act[k]
        if isinstance(v, str) and v.lstrip().startswith("{"):
            try:
                d = json.loads(v)
            except ValueError:
                continue
            if isinstance(d, dict) and "title" in d:
                return d
    return {}


def face_curves(act, n):
    f0 = int(round(act.frame_range[0]))
    by_path = {fc.data_path: fc for fc in fcurves(act)}
    props = {}
    for k, default in FACE_PROPS.items():
        fc = by_path.get(f'["{k}"]')
        props[k] = [round(float(fc.evaluate(f0 + i)), 3) if fc else default for i in range(n)]
    return props


def camera_cues(path, n):
    """Coarse shots (wide / medium / close / face) from the video's camera, for the web cinema camera."""
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [o for o in src.objects if o == "Cam"]
    cam = next((o for o in dst.objects if o is not None), None)
    if cam is None:
        return []
    sc = bpy.context.scene
    sc.collection.objects.link(cam)
    cues, last = [], None
    for f in range(0, n, 15):
        sc.frame_set(f)
        loc = cam.matrix_world.translation
        dist = math.dist((loc.x, loc.y, loc.z), (0.0, 0.0, EYES_Z))
        eq = dist * 50.0 / max(cam.data.lens, 1.0)  # distance as seen through a 50 mm lens
        shot = "wide" if eq > 3.2 else "medium" if eq > 2.2 else "close" if eq > 1.45 else "face"
        if shot != last and (not cues or f / 30 - cues[-1][0] >= 1.5):
            cues.append([round(f / 30, 2), shot])
            last = shot
    sc.collection.objects.unlink(cam)
    sc.frame_set(0)
    return cues


def encode_audio(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "96k", dst],
                   check=True)


def main():
    a = parse_args()
    rig = bpy.data.objects["Morfi_Rig"]
    keep = []
    if a.scenes:
        keep += append_actions(a.scenes, lambda n: n.startswith("Scene_"))
    if a.pos:
        keep += append_actions(a.pos, lambda n: n == POS)
    if not keep:
        sys.exit("no scenes to export")
    names = {act.name for act in keep}
    for act in list(bpy.data.actions):
        if act.name not in names:
            bpy.data.actions.remove(act)
    out = {"fps": 30, "scenes": {}}
    for act in keep:
        n = int(round(act.frame_range[1] - act.frame_range[0])) + 1
        if act.name == POS:
            meta = dict(POS_META, audio="voice/scenes/pos_video.mp3", camera=camera_cues(a.pos, n))
            if a.pos_audio:
                encode_audio(a.pos_audio, os.path.join(a.audio_dir, "pos_video.mp3"))
        else:
            meta = meta_of(act)
            meta.setdefault("title", act.name.replace("Scene_", ""))
            meta.setdefault("group", "scene")
            meta.setdefault("solo", False)
            meta.setdefault("camera", [])
        out["scenes"][act.name] = {**{k: meta[k] for k in ("title", "group", "solo", "camera") if k in meta},
                                   "audio": meta.get("audio", ""), "frames": n, "props": face_curves(act, n)}
        print("SCENE", act.name, n, "frames", out["scenes"][act.name]["title"], meta.get("audio"))
    public = os.path.dirname(os.path.dirname(os.path.abspath(a.audio_dir)))   # web/public
    missing = [s["audio"] for s in out["scenes"].values() if not os.path.exists(os.path.join(public, s["audio"]))]
    if missing:
        sys.exit(f"missing audio files: {missing}")
    # bind each action's slot to the rig (Blender 4.4+ only exports used slots), rest pose, export bones only
    rig.animation_data_create()
    for act in keep:
        rig.animation_data.action = act
        if hasattr(rig.animation_data, "action_slot") and getattr(act, "slots", None):
            rig.animation_data.action_slot = act.slots[0]
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.context.scene.render.fps = 30
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=os.path.abspath(a.out), export_format="GLB", use_selection=True, export_yup=True,
        export_apply=False, export_materials="NONE", export_skins=True, export_morph=False,
        export_animations=True, export_animation_mode="ACTIONS", export_force_sampling=True, export_frame_step=1,
        export_anim_single_armature=True, export_reset_pose_bones=True, export_optimize_animation_size=False,
        export_cameras=False, export_lights=False, export_extras=False,
    )
    with open(os.path.abspath(a.json), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("DONE", a.out, round(os.path.getsize(a.out) / 1e6, 2), "MB;", a.json, os.path.getsize(a.json) // 1024, "KB")


main()
