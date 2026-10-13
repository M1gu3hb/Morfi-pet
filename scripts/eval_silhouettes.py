"""Silhouette IoU of a point-cloud dump against the reference masks, using the
calibrated cameras (no refitting). Used to check shape edits quickly.

    python3 scripts/eval_silhouettes.py work/calib/points_neutral.npz [prefix]
"""
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import fit_cameras as F  # noqa: E402


def main():
    pts = np.load(sys.argv[1])['points']
    prefix = sys.argv[2] if len(sys.argv) > 2 else ''
    cv = json.load(open(os.path.join(ROOT, 'config', 'morfi.json')))['camera_views']
    out = {}
    for view, (ref, az, pose) in F.VIEWS.items():
        if pose != 'neutral':
            continue
        R = np.asarray(Image.open(os.path.join(ROOT, 'references_masks', ref + '.png')).convert('L').resize((F.w, F.h))) > 128
        M = F.splat(pts, cv[view])
        out[view] = round(F.iou(M, R), 4)
        if prefix:
            o = np.full((F.h, F.w, 3), 255, np.uint8)
            o[R & M] = (160, 160, 160)
            o[R & ~M] = (225, 45, 45)
            o[~R & M] = (40, 175, 60)
            Image.fromarray(o).save(f'{prefix}{view}.png')
    print(json.dumps(out), 'mean', round(float(np.mean(list(out.values()))), 4))


if __name__ == '__main__':
    main()
