"""Publish one model-comparison performance (Test_<Id>) to the web lab.

    python scripts/ia3d/export_test.py --perf D:/tmp/morfi/opus/perf.blend --action Test_Opus [--model "Claude Opus 5.5"]
                                       [--audio D:/tmp/morfi/opus/timeline.mp3] [--no-sync]

Run it from plain Python: it starts Blender on the final look (work/ia3d/morfi_ia_look7.blend, only
read), appends the action from --perf and writes, for the id (Test_Opus -> opus):

  work/ia3d/web/tests/<id>.glb          animation only, the rig's bone nodes with the same names as
                                        morfi_live.glb (raw; the next step compresses it)
  web/public/models/tests/<id>.json     the lab's scene entry: {fps, id, action, title, group "test", frames,
                                        audio, solo, camera, props (the 18 face curves per frame), model,
                                        costs {creation, review, publish, total}, changes}
  web/public/voice/tests/<id>.mp3       the composed audio, copied as it is

then (unless --no-sync) `node web/scripts/sync-tests.mjs <id>`, which resamples and meshopt-compresses the
GLB into web/public/models/tests/<id>.glb (what Vercel serves; `npm run sync-live` does the same for every
test it finds). Publishing again replaces the animation but keeps the model, costs and changes already in
the JSON (scripts/ia3d/test_costs.py writes them).

web/public/models/tests/index.json lists the entries the lab shows: [{"id": "opus", "label": "Opus"}, ...].
Look at it with `npx vite --port <yours> --strictPort` from web/ and open the "Prueba" section of Controles.
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from anim import launch  # noqa: E402

REPO = launch.REPO
TESTS_GLB = os.path.join(REPO, "work", "ia3d", "web", "tests")
PUBLIC = os.path.join(REPO, "web", "public")
COST_KEYS = ("creation", "review", "publish", "total")


def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--perf", required=True, help="the .blend that bake_perf.py bake wrote")
    ap.add_argument("--action", required=True, help="Test_<Id>")
    ap.add_argument("--audio", default="", help="the composed mp3 (default: the one the action was baked with)")
    ap.add_argument("--model", default="", help='label of the model, e.g. "Claude Opus 5.5" (default: what the JSON already has)')
    ap.add_argument("--look", default=launch.LOOK7, help="the final look .blend (default morfi_ia_look7.blend)")
    ap.add_argument("--no-sync", action="store_true", help="do not run the GLB compression afterwards")
    return ap.parse_args(argv)


def entry_for(act, pid, n, props, audio_rel, previous, model):
    """The scene entry: what the lab's player needs plus the model, costs and changes of the test."""
    import export_scenes as ES
    meta = ES.meta_of(act)
    costs = dict.fromkeys(COST_KEYS)
    costs.update({k: v for k, v in (previous.get("costs") or {}).items() if k in COST_KEYS})
    return {"fps": 30, "id": pid, "action": act.name, "title": meta.get("title") or pid, "group": "test",
            "frames": n, "audio": audio_rel, "solo": bool(meta.get("solo", False)),
            "camera": meta.get("camera") or [[0.0, "medium"]], "props": props,
            "model": model or previous.get("model"), "costs": costs, "changes": previous.get("changes"),
            "note": previous.get("note")}


def run_blender_side(a):
    import bpy
    import export_scenes as ES
    pid = launch.action_id(a.action)
    acts = ES.append_actions(os.path.abspath(a.perf), lambda n: n == a.action)
    if not acts:
        sys.exit(f"ERROR: no action {a.action} in {a.perf}")
    act = acts[0]
    for other in list(bpy.data.actions):
        if other.name != act.name:
            bpy.data.actions.remove(other)
    meta = ES.meta_of(act)
    audio = a.audio or meta.get("audio_src", "")
    if not audio or not os.path.exists(audio):
        sys.exit(f"ERROR: composed audio not found ({audio!r}): run compose_audio.py or pass --audio")
    n = int(round(act.frame_range[1] - act.frame_range[0])) + 1
    audio_rel = f"voice/tests/{pid}.mp3"
    out_json = os.path.join(PUBLIC, "models", "tests", pid + ".json")
    previous = json.load(open(out_json, encoding="utf-8")) if os.path.exists(out_json) else {}
    entry = entry_for(act, pid, n, ES.face_curves(act, n), audio_rel, previous, a.model)
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    os.makedirs(os.path.join(PUBLIC, "voice", "tests"), exist_ok=True)
    shutil.copyfile(audio, os.path.join(PUBLIC, audio_rel))
    ES.export_glb(bpy.data.objects["Morfi_Rig"], [act], os.path.join(TESTS_GLB, pid + ".glb"))
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(entry, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"EXPORTED {a.action}: {n} frames, {entry['title']!r}, glb {os.path.getsize(os.path.join(TESTS_GLB, pid + '.glb')) // 1024} KB, "
          f"json {os.path.getsize(out_json) // 1024} KB, audio {os.path.getsize(os.path.join(PUBLIC, audio_rel)) // 1024} KB")


def main():
    if launch.in_blender():
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
        run_blender_side(parse(argv))
        return 0
    a = parse(sys.argv[1:])
    pid = launch.action_id(a.action)
    rc = launch.run_blender(a.look, os.path.abspath(__file__), sys.argv[1:])
    if rc or a.no_sync:
        return rc
    sync = os.path.join(REPO, "web", "scripts", "sync-tests.mjs")
    rc = launch.run_node(sync, [pid], os.path.join(REPO, "web"))
    if rc == 0:
        print(f"PUBLISHED {pid}: web/public/models/tests/{pid}.json + .glb, web/public/voice/tests/{pid}.mp3")
    return rc


if __name__ == "__main__":
    sys.exit(main())
