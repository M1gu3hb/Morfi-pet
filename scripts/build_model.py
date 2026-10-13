"""Build the complete Morfi master scene from scratch.

    blender -b --python scripts/build_model.py -- [--out source/morfi_master.blend]
                                                   [--quality draft|final] [--skip clothes,...]

Everything is generated procedurally from config/morfi.json: geometry,
textures (written to textures/master), materials, studio, cameras.
"""
import argparse
import json
import os
import sys
import time

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
for _m in [k for k in sys.modules if k.startswith('morfi')]:
    del sys.modules[_m]
from morfi import meshutil as mu  # noqa: E402
from morfi import face, accessories, scene, materials as mats  # noqa: E402
from morfi import assemble  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'source', 'morfi_master.blend'))
    ap.add_argument('--quality', default='final', choices=['draft', 'final'])
    ap.add_argument('--skip', default='')
    a = ap.parse_args(argv)
    skip = set(filter(None, a.skip.split(',')))
    cfg = json.load(open(os.path.join(ROOT, 'config', 'morfi.json')))
    q = a.quality
    t0 = time.time()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    tex = os.path.join(ROOT, 'textures', 'master')
    os.makedirs(tex, exist_ok=True)

    morfi = mu.get_collection('Morfi')
    c_body = mu.get_collection('Body', morfi)
    c_head = mu.get_collection('Head', morfi)
    c_cloth = mu.get_collection('Clothing', morfi)
    c_acc = mu.get_collection('Accessories', morfi)
    root = mu.empty('Morfi_Root', collection=morfi)
    grp_face = mu.empty('Face_Details', collection=c_head, parent=root)
    grp_cloth = mu.empty('Clothing', collection=c_cloth, parent=root)
    grp_acc = mu.empty('Accessories', collection=c_acc, parent=root)

    from morfi import textures
    tsize = 1024 if q == 'final' else 512
    mats.load_tiles(textures.generate_all(tex, tsize, cfg['colors']))
    skin = mats.skin('M_Skin', cfg['colors']['skin'])
    # ---------------------------------------------------------------- head
    head, shape = face.build_head(cfg, c_head, tex, parent=root, tex_size=4096 if q == 'final' else 2048,
                                  lines=textures.skin_lines(tsize))
    bpy.context.view_layer.update()
    grp_face.parent = head
    grp_face.location = (0, 0, 0)
    eyes = face.build_eyes(cfg, shape, head, c_head, tex)
    brows = face.build_brows(cfg, shape, head, c_head)
    for ob in eyes + brows:
        ob.parent = grp_face
    print(f'[build] head {time.time() - t0:.1f}s')
    bpy.context.view_layer.update()
    glasses, lenses, gp = accessories.build_glasses(cfg, shape, head, c_acc, h=0.0013 if q == 'final' else 0.002)
    for ob in [glasses] + lenses:
        ob.parent = head
    grp_pix, pixels = accessories.build_cubes(cfg, shape.center, c_acc, head, skin)
    print(f'[build] glasses+pixels {time.time() - t0:.1f}s')
    # ---------------------------------------------------------------- body & clothes
    res = 0.0022 if q == 'final' else 0.0035
    body = assemble.build_body(cfg, c_body, root, skin, h=res)
    print(f'[build] body {time.time() - t0:.1f}s')
    parts = {'Body_Base': body, 'Head': head}
    if 'clothes' not in skip:
        parts.update(assemble.build_clothes(cfg, c_cloth, grp_cloth, tex, h=res, quality=q))
        print(f'[build] clothes {time.time() - t0:.1f}s')
    if 'shoes' not in skip:
        parts.update(assemble.build_shoes(cfg, c_cloth, grp_cloth, tex, h=res * 0.8, quality=q))
        print(f'[build] shoes {time.time() - t0:.1f}s')
    if 'laptop' not in skip:
        parts.update(assemble.build_laptop(cfg, c_acc, grp_acc, quality=q))
        print(f'[build] laptop {time.time() - t0:.1f}s')
    # ---------------------------------------------------------------- budgets
    # marching-cubes meshes are heavily oversampled; collapse-decimate them to
    # per-object triangle budgets (shape is preserved, files stay manageable)
    budgets = cfg.get('master_tris', {
        'Body_Base': 90000, 'Hoodie': 140000, 'Hoodie_Hem': 24000, 'Hoodie_Cuff_L': 12000, 'Hoodie_Cuff_R': 12000,
        'Tshirt': 50000, 'Tshirt_Collar': 8000, 'Tshirt_Logo': 6000, 'Shoe_L': 70000, 'Shoe_R': 70000,
        'Glasses_Frame': 50000, 'Laptop': 30000})
    for name, target in budgets.items():
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        ob.data.calc_loop_triangles()
        n = len(ob.data.loop_triangles)
        if n > target:
            mu.decimate(ob, target / n)
            ob.data.shade_smooth()
            print(f'[build] decimated {name}: {n} -> {len(ob.data.polygons)}')
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and not ob.data.uv_layers:
            mu.cube_project_uv(ob, 4.0)
    # ---------------------------------------------------------------- studio
    studio = mu.get_collection('Studio')
    scene.build_studio(cfg, studio)
    for name, v in scene.VIEWS.items():
        scene.make_camera('Cam_' + name, v['az'], cfg, studio)
    sc.camera = bpy.data.objects['Cam_front']
    scene.setup_render(samples=128, res=(1145, 1374))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    bpy.ops.file.pack_all() if False else None
    bpy.ops.wm.save_as_mainfile(filepath=a.out, relative_remap=True, compress=True)
    print(f'[build] saved {a.out} in {time.time() - t0:.1f}s')


if __name__ == '__main__':
    main()
