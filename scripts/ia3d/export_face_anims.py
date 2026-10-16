"""Face curves of every action (blink, gaze, mouth, brows...) as JSON for the web viewer.

python scripts/ia3d/export_face_anims.py --out work/ia3d/web/morfi_live_anims.json

glTF has no channel for the rig's custom properties, so the same curves that
make_actions.py bakes into Blender are written here, one value per frame (30 fps).
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim.actions import ACTIONS  # noqa: E402
from anim.clip import FACE_PROPS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = {"fps": 30, "props": list(FACE_PROPS), "actions": {}}
    for name, make in ACTIONS.items():
        clip = make()
        props = {}
        for k, default in FACE_PROPS.items():
            v = clip.ch.get(f"prop.{k}")
            v = np.full(clip.n, default) if v is None else np.asarray(v)
            props[k] = [round(float(x), 3) for x in v]
        out["actions"][name] = {"frames": clip.n, "loop": bool(clip.loop), "props": props}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print("DONE", args.out, os.path.getsize(args.out) // 1024, "KB")


if __name__ == "__main__":
    main()
