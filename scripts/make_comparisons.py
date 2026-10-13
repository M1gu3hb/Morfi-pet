"""Side-by-side comparisons + silhouette overlays + IoU and colour metrics.

    python3 scripts/make_comparisons.py [--before DIR]   (needs numpy, pillow, scipy, scikit-image)

Writes renders/comparisons/*.png and docs/metrics.json. Overlays are
diagnostic only (red = reference only, green = render only, grey = both);
final renders are never modified.

Metrics per view: silhouette IoU (render alpha vs. the reference mask from
scripts/ref_masks.py) and the colour difference in CIELAB (Delta E 1976)
inside the region where both silhouettes agree, measured at quarter resolution
after a light blur so a few pixels of misalignment count less than shading or
colour. --before DIR adds before_after_<view>.png sheets (reference | DIR | now).
"""
import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, 'references')
VIEWS = os.path.join(ROOT, 'renders', 'views')
TRANS = os.path.join(ROOT, 'renders', 'transparent')
OUT = os.path.join(ROOT, 'renders', 'comparisons')

PAIRS = [
    ('front', '02_Morfi_frente'),
    ('profile_left', '03_Morfi_perfil_izquierdo'),
    ('back', '04_Morfi_espalda'),
    ('profile_right', '05_Morfi_perfil_derecho'),
    ('three_quarter_front', '06_Morfi_tres_cuartos_frontal'),
    ('three_quarter_back', '07_Morfi_tres_cuartos_posterior'),
]


def ref_mask(path, size):
    """Silhouette of a reference: the segmentation from scripts/ref_masks.py if
    available (accurate on white sneakers / floor shadows), else a colour threshold."""
    mp = os.path.join(ROOT, 'references_masks', os.path.basename(path))
    if os.path.exists(mp):
        m = Image.open(mp).convert('L')
        if m.size != size:
            m = m.resize(size, Image.BILINEAR)
        return np.asarray(m) > 128
    im = Image.open(path).convert('RGB')
    if im.size != size:
        im = im.resize(size)
    rgb = np.asarray(im).astype(int)
    bg = np.median(np.concatenate([rgb[:20, :20].reshape(-1, 3), rgb[:20, -20:].reshape(-1, 3)]), axis=0)
    d = np.sqrt(((rgb - bg) ** 2).sum(-1))
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    lum = rgb.mean(-1)
    m = np.where((sat < 0.12) & (lum > 175), d > 40, d > 26)
    m = ndi.binary_opening(m, iterations=1)
    m = ndi.binary_closing(m, iterations=3)
    m = ndi.binary_fill_holes(m)
    lab, n = ndi.label(m)
    if n > 1:
        sizes = ndi.sum(m, lab, range(1, n + 1))
        m = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > 400])
    return m


def alpha_mask(path, size):
    im = Image.open(path).convert('RGBA')
    if im.size != size:
        im = im.resize(size)
    return np.asarray(im)[..., 3] > 128


def delta_e(ref_rgb, out_rgb, mask):
    """Median and mean CIELAB Delta E (1976) inside mask, quarter resolution, light blur."""
    from skimage.color import rgb2lab
    size = (ref_rgb.width // 4, ref_rgb.height // 4)
    m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(size, Image.BILINEAR)) > 200

    def lab(im):
        a = np.asarray(im.resize(size, Image.LANCZOS)).astype(float) / 255
        return rgb2lab(np.clip(ndi.gaussian_filter(a, (1.5, 1.5, 0)), 0, 1))
    d = np.sqrt(((lab(out_rgb) - lab(ref_rgb)) ** 2).sum(-1))[m]
    return float(np.median(d)), float(d.mean())


def label(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.size[0], 34], fill=(255, 255, 255))
    d.text((10, 10), text, fill=(20, 30, 60))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--before', help='folder with earlier view renders for before/after sheets')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    metrics = {}
    for view, ref in PAIRS:
        rp = os.path.join(REF, ref + '.png')
        vp = os.path.join(VIEWS, view + '.png')
        tp = os.path.join(TRANS, view + '.png')
        if not (os.path.exists(vp) and os.path.exists(tp)):
            print('missing', view)
            continue
        r = Image.open(rp).convert('RGB')
        v = Image.open(vp).convert('RGB').resize(r.size)
        mr = ref_mask(rp, r.size)
        mv = alpha_mask(tp, r.size)
        iou = float((mr & mv).sum() / (mr | mv).sum())
        de_med, de_mean = delta_e(r, v, mr & mv)
        metrics[view] = {'reference': ref + '.png', 'silhouette_iou': round(iou, 4),
                         'color_delta_e_median': round(de_med, 2), 'color_delta_e_mean': round(de_mean, 2),
                         'note': 'reference mask from scripts/ref_masks.py (BiRefNet); camera and pose per view '
                                 'from config camera_views / view_poses; Delta E inside the shared silhouette'}
        o = np.full(mr.shape + (3,), 255, np.uint8)
        o[mr & mv] = (160, 160, 160)
        o[mr & ~mv] = (225, 45, 45)
        o[~mr & mv] = (40, 175, 60)
        W, H = r.size
        sheet = Image.new('RGB', (W * 3, H), 'white')
        sheet.paste(label(r.copy(), f'Referencia {ref}.png'), (0, 0))
        sheet.paste(label(v.copy(), f'Render 3D ({view})'), (W, 0))
        sheet.paste(label(Image.fromarray(o), f'Siluetas  IoU={iou:.3f}  rojo=solo ref  verde=solo 3D'), (2 * W, 0))
        sheet = sheet.resize((W * 3 // 2, H // 2), Image.LANCZOS)
        sheet.save(os.path.join(OUT, f'cmp_{view}.png'))
        print(view, 'IoU', round(iou, 4), 'dE median', round(de_med, 2), 'mean', round(de_mean, 2))
        bp = os.path.join(a.before, view + '.png') if a.before else None
        if bp and os.path.exists(bp):
            b = Image.open(bp).convert('RGB').resize(r.size)
            ba = Image.new('RGB', (W * 3, H), 'white')
            ba.paste(label(r.copy(), f'Referencia {ref}.png'), (0, 0))
            ba.paste(label(b, 'Antes'), (W, 0))
            ba.paste(label(v.copy(), 'Ahora'), (2 * W, 0))
            ba.resize((W * 3 // 2, H // 2), Image.LANCZOS).save(os.path.join(OUT, f'before_after_{view}.png'))
    hero = os.path.join(ROOT, 'renders', 'hero_wordmark.png')
    if os.path.exists(hero):
        r = Image.open(os.path.join(REF, '00_Morfi_master_wordmark.png')).convert('RGB')
        h = Image.open(hero).convert('RGB').resize(r.size)
        W, H = r.size
        sheet = Image.new('RGB', (W * 2, H), 'white')
        sheet.paste(label(r, 'Referencia maestra 00'), (0, 0))
        sheet.paste(label(h, 'Render hero + wordmark'), (W, 0))
        sheet.resize((W, H // 2), Image.LANCZOS).save(os.path.join(OUT, 'cmp_hero_master.png'))
    # each garment / accessory next to its reference sheet
    parts = [('sudadera', '08_Morfi_sudadera'), ('playera', '09_Morfi_playera'), ('tenis', '10_Morfi_tenis'),
             ('lentes', '11_Morfi_lentes'), ('cubos', '12_Morfi_tres_cubos'), ('laptop', '13_Morfi_laptop'),
             ('cuerpo_base', '14_Morfi_cuerpo_base')]
    for key, ref in parts:
        pp = os.path.join(ROOT, 'renders', 'parts', key + '.png')
        if not os.path.exists(pp):
            continue
        r = Image.open(os.path.join(REF, ref + '.png')).convert('RGB')
        p_ = Image.open(pp).convert('RGB')
        H = 700
        r = r.resize((int(r.width * H / r.height), H), Image.LANCZOS)
        p_ = p_.resize((int(p_.width * H / p_.height), H), Image.LANCZOS)
        sheet = Image.new('RGB', (r.width + p_.width, H), 'white')
        sheet.paste(label(r, f'Referencia {ref}.png'), (0, 0))
        sheet.paste(label(p_, f'Pieza 3D ({key})'), (r.width, 0))
        sheet.save(os.path.join(OUT, f'cmp_part_{key}.png'))
    with open(os.path.join(ROOT, 'docs', 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=1)


if __name__ == '__main__':
    main()
