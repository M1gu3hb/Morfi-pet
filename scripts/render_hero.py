"""Hero render replicating the master image (laptop under the right arm,
left fist on the hip, slight head tilt), plus the wordmark composite.

    blender -b source/morfi_master.blend --python scripts/render_hero.py -- \
        --out renders --samples 256 [--scale 1.0]

Writes renders/hero.png, renders/hero_wordmark.png and
renders/transparent/hero.png. The wordmark is a separate composition layer
cut cleanly from references/00_Morfi_master_wordmark.png (not geometry).
"""
import argparse
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector, Matrix, Quaternion

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from morfi import scene  # noqa: E402


def place_laptop(rig):
    lap = bpy.data.objects['Laptop']
    lap.hide_render = False
    lap.hide_set(False)
    bpy.context.view_layer.update()
    pb = rig.pose.bones['hand.R']
    W = rig.matrix_world @ pb.matrix
    wrist = W.translation.copy()
    # orientation: lid faces out to Morfi's right and a bit forward,
    # long side runs front-back, short side vertical
    n = Vector((-0.80, -0.56, 0.06)).normalized()       # local +Z (lid normal)
    up = Vector((0.10, 0.30, 1.0))
    xa = up.cross(n).normalized()                        # local +X (width) roughly horizontal
    ya = n.cross(xa).normalized()                        # local +Y (depth) roughly vertical
    R = Matrix((xa, ya, n)).transposed().to_4x4()
    # bottom edge resting in the hand, laptop body just outside the arm
    p = lap.data
    c = wrist + Vector((-0.030, -0.060, 0.112))
    M = Matrix.Translation(c) @ R @ Matrix.Translation(Vector((0, 0, -0.009)))
    lap.parent = None
    lap.matrix_world = M
    # keep it attached to the hand for animation previews
    mw = lap.matrix_world.copy()
    lap.parent = rig
    lap.parent_type = 'BONE'
    lap.parent_bone = 'hand.R'
    bpy.context.view_layer.update()
    lap.matrix_world = mw
    return lap


def wordmark_rgba():
    from PIL import Image
    im = np.asarray(Image.open(os.path.join(ROOT, 'references', '00_Morfi_master_wordmark.png')).convert('RGB')).astype(float) / 255
    crop = im[1200:1330, 370:800]
    bg = np.array([0.995, 0.993, 0.98])
    # alpha from distance to the paper colour (text is navy/blue, high contrast)
    d = np.clip((bg[None, None, :] - crop).max(-1) / 0.55, 0, 1)
    alpha = np.clip((d - 0.04) / 0.9, 0, 1)
    # un-premultiply the colour against white
    a = np.maximum(alpha[..., None], 1e-3)
    col = np.clip((crop - bg[None, None, :] * (1 - a)) / a, 0, 1)
    return np.concatenate([col, alpha[..., None]], -1)


def composite_wordmark(src, dst, width_frac=0.34, center_y_frac=0.917, transparent=False):
    from PIL import Image
    base = Image.open(src).convert('RGBA')
    W, H = base.size
    wm = wordmark_rgba()
    wm_img = Image.fromarray((wm * 255).astype(np.uint8), 'RGBA')
    tw = int(W * width_frac)
    th = int(wm_img.size[1] * tw / wm_img.size[0])
    wm_img = wm_img.resize((tw, th), Image.LANCZOS)
    x = (W - tw) // 2
    y = int(H * center_y_frac - th / 2)
    base.alpha_composite(wm_img, (x, y))
    if not transparent:
        base = base.convert('RGB')
    base.save(dst)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'renders'))
    ap.add_argument('--samples', type=int, default=256)
    ap.add_argument('--scale', type=float, default=1.0)
    a = ap.parse_args(argv)
    sc = bpy.context.scene
    rig = bpy.data.objects['Morfi_Rig']
    rig.animation_data.action = bpy.data.actions['Pose_Hero']
    sc.frame_set(1)
    bpy.context.view_layer.update()
    place_laptop(rig)
    import json
    cfg = json.load(open(os.path.join(ROOT, 'config', 'morfi.json')))
    studio = bpy.data.collections['Studio']
    cam = bpy.data.objects.get('Cam_hero') or scene.make_camera(
        'Cam_hero', -33.0, cfg, studio, target=(0.0, 0.0, 0.43), dist=2.30, height=0.86, lens=55.0)
    sc.camera = cam
    sc.cycles.samples = a.samples
    sc.render.resolution_percentage = int(round(100 * a.scale))
    os.makedirs(os.path.join(a.out, 'transparent'), exist_ok=True)
    scene.set_transparent_output(False)
    sc.render.filepath = os.path.join(a.out, 'hero.png')
    bpy.ops.render.render(write_still=True)
    composite_wordmark(sc.render.filepath, os.path.join(a.out, 'hero_wordmark.png'))
    scene.set_transparent_output(True)
    sc.render.filepath = os.path.join(a.out, 'transparent', 'hero.png')
    bpy.ops.render.render(write_still=True)
    composite_wordmark(sc.render.filepath, os.path.join(a.out, 'transparent', 'hero_wordmark.png'), transparent=True)
    print('[hero] done')


if __name__ == '__main__':
    main()
