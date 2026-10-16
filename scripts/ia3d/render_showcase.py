"""One continuous performance of Morfi's actions, crossfaded in the NLA, in the studio.

blender -b work/ia3d/morfi_ia_look.blend --python scripts/ia3d/render_showcase.py -- \
    --out work/ia3d/showcase [--start 0 --end 9999] [--samples 40] [--percent 100] [--setup-only]

Writes frames f_00000.png ... and showcase.json (segments and captions, for ffmpeg).
Re-running skips frames already on disk, so long renders can be resumed.
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import studio  # noqa: E402

BLEND = 10                       # crossfade frames between actions
# action, repeats, caption, camera (azimuth deg, distance m, camera height, target height, lens)
SEGMENTS = [
    ("Idle", 1, "Reposo: respira, cambia el peso y mira", (-18, 3.1, 0.80, 0.55, 50)),
    ("Wave", 1, "Saludo", (-12, 2.8, 0.75, 0.56, 50)),
    ("Talk", 1, "Hablando (modo chatbot)", (-6, 1.9, 0.72, 0.62, 55)),
    ("Nod_Yes", 1, "Sí", (-6, 1.9, 0.72, 0.64, 55)),
    ("Look_Around", 1, "Curioso", (8, 2.3, 0.74, 0.62, 50)),
    ("Present", 1, "Presentando un producto", (30, 2.6, 0.72, 0.55, 50)),
    ("Jump_Happy", 1, "¡Feliz!", (-20, 3.3, 0.70, 0.62, 45)),
    ("Walk", 4, "Caminando", (-35, 3.4, 0.70, 0.52, 45)),
    ("Dance", 2, "Bailando", (-10, 3.0, 0.72, 0.56, 45)),
    ("Shake_No", 1, "No", (-6, 2.0, 0.72, 0.64, 55)),
    ("Wave", 1, "¡Adiós!", (-14, 2.9, 0.74, 0.56, 50)),
    ("Idle", 1, "", (-14, 3.2, 0.78, 0.55, 50)),
]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=99999)
    ap.add_argument("--samples", type=int, default=40)
    ap.add_argument("--percent", type=int, default=100)
    ap.add_argument("--res", default="1280,720")
    ap.add_argument("--engine", default="cycles")
    ap.add_argument("--setup-only", action="store_true")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--draft", action="store_true", help="no motion blur (quick previews)")
    return ap.parse_args(argv)


def action_len(act):
    return int(round(act.frame_end - act.frame_start))


def build_nla(rig):
    ad = rig.animation_data or rig.animation_data_create()
    ad.action = None
    for tr in list(ad.nla_tracks):
        ad.nla_tracks.remove(tr)
    tracks = [ad.nla_tracks.new(), ad.nla_tracks.new()]
    t = 0
    segs = []
    for i, (name, reps, caption, cam) in enumerate(SEGMENTS):
        act = bpy.data.actions[name]
        length = action_len(act) * reps
        strip = tracks[i % 2].strips.new(f"{i:02d}_{name}", t, act)
        if hasattr(strip, "action_slot") and getattr(act, "slots", None):
            strip.action_slot = act.slots[0]
        strip.repeat = reps
        strip.extrapolation = "NOTHING"
        strip.blend_type = "REPLACE"
        strip.blend_in = 0 if i == 0 else BLEND
        strip.blend_out = 0 if i == len(SEGMENTS) - 1 else BLEND
        segs.append({"action": name, "start": t, "end": t + length, "caption": caption, "camera": cam,
                     "stride": float(act.get("stride", 0.0))})
        t += length - BLEND
    return segs, segs[-1]["end"]


def mover_path(segs):
    """Root travel: Morfi walks towards the camera during the walk segment (feet planted)."""
    keys = [(0, 0.0)]
    y = 0.0
    for s in segs:
        if s["action"] == "Walk":
            speed = 2 * s["stride"] / 16.0                 # in-place cycle: 2 strides per 16 frames
            a, b = s["start"], s["end"]
            ramp = BLEND
            keys += [(a, y), (a + ramp, y - speed * ramp / 2)]
            y_end = y - speed * ((b - a) - ramp)
            keys += [(b - ramp, y_end + speed * ramp / 2), (b, y_end)]
            y = y_end
    return keys, y


def build_mover(rig, segs):
    mover = bpy.data.objects.new("Mover", None)
    bpy.context.scene.collection.objects.link(mover)
    rig.parent = mover
    keys, _ = mover_path(segs)
    for f, y in keys:
        mover.location = (0, y, 0)
        mover.keyframe_insert("location", index=1, frame=f)
    fc = mover.animation_data.action.fcurves.find("location", index=1) if mover.animation_data.action.fcurves \
        else None
    if fc:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    return mover


def mover_y(mover, frame):
    fc = mover.animation_data.action.fcurves.find("location", index=1)
    return fc.evaluate(frame) if fc else 0.0


def build_camera(cam, mover, segs):
    tgt = bpy.data.objects.new("CamTarget", None)
    bpy.context.scene.collection.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis, con.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    cam.data.dof.focus_object = tgt
    for s in segs:
        az, dist, h, tz, lens = s["camera"]
        for f in (s["start"] + BLEND, s["end"] - BLEND):
            my = mover_y(mover, f)
            a = math.radians(az)
            cam.location = (dist * math.sin(a), my - dist * math.cos(a), h)
            tgt.location = (0, my, tz)
            cam.data.lens = lens
            cam.keyframe_insert("location", frame=f)
            tgt.keyframe_insert("location", frame=f)
            cam.data.keyframe_insert("lens", frame=f)
    # a breath of hand-held drift so the camera is never dead still
    for i, fc in enumerate(cam.animation_data.action.fcurves):
        if fc.data_path == "location":
            mod = fc.modifiers.new("NOISE")
            mod.scale, mod.strength, mod.phase = 70.0, 0.010, 11.0 * (i + 1)
    return tgt


def main():
    args = parse_args()
    sc = bpy.context.scene
    res = tuple(int(v) for v in args.res.split(","))
    cam, _ = studio.setup(sc, args.engine, args.samples, res, args.percent)
    rig = bpy.data.objects["Morfi_Rig"]
    segs, total = build_nla(rig)
    mover = build_mover(rig, segs)
    build_camera(cam, mover, segs)
    sc.frame_start, sc.frame_end = 0, total - 1
    if args.engine == "cycles" and not args.draft:
        sc.render.use_motion_blur = True
        sc.render.motion_blur_shutter = 0.45
        sc.render.use_persistent_data = True
        sc.cycles.use_adaptive_sampling = True
        sc.cycles.adaptive_threshold = 0.02
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "showcase.json"), "w", encoding="utf-8") as fh:
        json.dump({"fps": 30, "frames": total, "segments": segs}, fh, indent=1, ensure_ascii=False)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "showcase.blend"))
    print("SHOWCASE", total, "frames")
    if args.setup_only:
        return
    for f in range(max(0, args.start), min(total, args.end + 1), args.step):
        path = os.path.join(out, "frames", f"f_{f:05d}.png")
        if os.path.exists(path):
            continue
        sc.frame_set(f)
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
    print("DONE")


main()
