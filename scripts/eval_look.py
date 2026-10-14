"""Compare the web viewer's frames (web/scripts/look-eval.mjs) with the photos:
median CIELAB dE inside the figure (same measure as make_comparisons.py) for
each shader, and a sheet photo / physical / photo-look.

    python3 scripts/eval_look.py   ->  table + renders/comparisons/look_eval.png
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from make_comparisons import delta_e  # noqa: E402
from prep_web_refs import REFS  # noqa: E402

VIEWS = ['front', 'three_quarter_front', 'profile_left', 'profile_right', 'back', 'three_quarter_back']
BG = np.array([253, 253, 249])


def main():
    shaders = [s for s in ('pbr', 'ref') if os.path.isdir(os.path.join(ROOT, 'work', 'look', 'eval', s))]
    rows = []
    print('vista                 ' + '  '.join(f'{s:>6s}' for s in shaders))
    for v in VIEWS:
        ref = Image.open(os.path.join(ROOT, 'references', REFS[v] + '.png')).convert('RGB')
        rmask = np.asarray(Image.open(os.path.join(ROOT, 'references_masks', REFS[v] + '.png')).convert('L').resize(ref.size)) > 128
        line, ims = [], [ref]
        for s in shaders:
            out = Image.open(os.path.join(ROOT, 'work', 'look', 'eval', s, v + '.png')).convert('RGB').resize(ref.size)
            omask = np.abs(np.asarray(out).astype(int) - BG).sum(-1) > 18
            de = delta_e(ref, out, rmask & omask)[0]
            line.append(de)
            ims.append(out)
        print(f'{v:20s}  ' + '  '.join(f'{d:6.2f}' for d in line))
        rows.append(ims)
    w, h = 286, 343
    sheet = Image.new('RGB', (w * (1 + len(shaders)), h * len(rows) + 24), 'white')
    d = ImageDraw.Draw(sheet)
    for k, t in enumerate(['Referencia'] + [{'pbr': 'Visor: físico', 'ref': 'Visor: fiel a la foto'}[s] for s in shaders]):
        d.text((k * w + 6, 6), t, fill=(20, 20, 20))
    for r, ims in enumerate(rows):
        for k, im in enumerate(ims):
            sheet.paste(im.resize((w, h)), (k * w, 24 + r * h))
    sheet.save(os.path.join(ROOT, 'renders', 'comparisons', 'look_eval.png'))


if __name__ == '__main__':
    main()
