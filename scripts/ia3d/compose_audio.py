"""Compose the audio of a performance from a timeline JSON (plain Python + ffmpeg, no Blender).

    python scripts/ia3d/compose_audio.py --timeline D:/tmp/morfi/opus/timeline.json [--check]

    {"voice": "supervm",
     "lines": [["td_01", 0.6], ["td_02", 4.1], ...],      # [voice line key, start second]
     "sfx": [["bell", 31.2]],                              # optional: bell, bell2, chime, pop
     "tail": 1.2,                                          # optional: silence after the last word (s)
     "dur": 120.0}                                         # optional: the take lasts at least this long (s)

The voice lines are web/public/voice/<voice>/<key>.mp3 + .json (ElevenLabs audio with its per-letter
alignment and envelope). Writes next to the timeline (or where --out-mp3 / --out-json say):
  <name>.mp3         the composed track, the same loudness and format as the scene audio
                     (anim/audiomix.py: lines levelled to their own loudness, 96 kbps mono mp3)
  <name>.align.json  the merged alignment in the format make_scenes.py writes for the scenes
                     (chars, t0, t1, env per 1/30 s, lines, sounds, loudness)
The performance module gets the same lines as Python data with
anim.scenes.timeline_from_file(path, META) (the lip-sync, the words' times), see bake_perf.py.

Errors say what to change: a missing voice line, a line used twice, two lines that sound at the same
time. --check validates without writing anything. Exit code 2 = the timeline needs changes.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from anim import scenes as S  # noqa: E402

DEFAULT_SCRIPT = os.path.join(S.REPO, "voice", "tests_day.json")


def load_spec(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"ERROR: no timeline file {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: {path} is not valid JSON ({e})")


def script_report(spec, script):
    """Notes about the lines of the script that the timeline leaves out or plays out of order."""
    if not os.path.exists(script):
        return []
    want = [ln["key"] for ln in json.load(open(script, encoding="utf-8")).get("lines", [])]
    used = [it[0] for it in spec.get("lines", []) if isinstance(it, list) and it]
    if not any(k in want for k in used):
        return []
    notes = []
    missing = [k for k in want if k not in used]
    if missing:
        notes.append(f"lines of {os.path.basename(script)} not used: {', '.join(missing)}")
    order = [k for k in used if k in want]
    if order != sorted(order, key=want.index):
        notes.append("lines are not in the script's story order")
    return notes


def report(tl, spans, stats=None):
    print(f"TIMELINE {tl['key']}: {tl['dur']:.2f} s = {tl['frames']} frames at {S.FPS} fps, {len(tl['lines'])} lines")
    print(f"  {'line':8} {'start':>7} {'sounds':>15} {'ends':>7}  text")
    prev_end = None
    for ln, (_, v0, v1, f1) in zip(tl["lines"], spans):
        gap = "" if prev_end is None else f"  (gap {v0 - prev_end:+.2f} s)"
        print(f"  {ln['key']:8} {ln['start']:7.2f} {v0:7.2f}-{v1:<7.2f} {f1:7.2f}  {ln['text'][:48]}{gap}")
        prev_end = v1
    for s in tl["sounds"]:
        if s["kind"] in ("bell", "bell2", "chime", "pop"):
            print(f"  sfx {s['kind']} at {s['t0']:.2f} s")
    if stats:
        print(f"  loudness {stats['lufs']:.1f} LUFS (lines {stats['lines_lufs']:.1f}), true peak {stats['true_peak']:.1f} dBTP")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--timeline", required=True, help="timeline JSON: {\"voice\": \"supervm\", \"lines\": [[key, start_s], ...]}")
    ap.add_argument("--out-mp3", default="", help="default: <timeline>.mp3 next to the timeline")
    ap.add_argument("--out-json", default="", help="default: <timeline>.align.json")
    ap.add_argument("--script", default=DEFAULT_SCRIPT, help="script whose lines should all be used (a note, not an error)")
    ap.add_argument("--strict", action="store_true", help="a script line left out is an error")
    ap.add_argument("--check", action="store_true", help="only validate, write nothing")
    a = ap.parse_args(argv)
    spec = load_spec(a.timeline)
    try:
        _, _, _, spans = S.check_spec(spec)
        base = os.path.splitext(a.timeline)[0]
        tl = S.timeline_from_spec(spec, os.path.basename(base))
    except S.TimelineError as e:
        print(f"ERROR: {a.timeline}: {e}")
        return 2
    notes = script_report(spec, a.script)
    for (k0, _, v1, f1), (k1, w0, _, _) in zip(spans, spans[1:]):
        if w0 < f1 - 1e-6:
            notes.append(f"{k0} and {k1}: the files overlap by {f1 - w0:.2f} s but only in silence (no overlapping sound)")
    for n in notes:
        print(("ERROR: " if a.strict and n.startswith("lines of") else "NOTE: ") + n)
    if a.strict and any(n.startswith("lines of") for n in notes):
        return 2
    if a.check:
        report(tl, spans)
        print("OK: the timeline is valid (nothing written)")
        return 0
    from anim import audiomix as AM
    mp3 = a.out_mp3 or base + ".mp3"
    js = a.out_json or base + ".align.json"
    tl["audio"], tl["align"] = os.path.basename(mp3), os.path.basename(js)     # as the record of this track
    _, stats = AM.mix(tl, mp3, js)
    report(tl, spans, stats)
    print(f"MP3 {mp3} ({os.path.getsize(mp3) // 1024} KB)\nALIGN {js}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
