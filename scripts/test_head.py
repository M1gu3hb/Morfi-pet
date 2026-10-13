"""Quick head-only build + preview renders (development aid).

blender -b --python scripts/test_head.py -- out_dir [samples]
"""
import sys
import os
import json
import time
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
for m in [k for k in sys.modules if k.startswith('morfi')]:
    del sys.modules[m]
from morfi import meshutil as mu, face, accessories, scene, materials as mats  # noqa

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
out = argv[0] if argv else os.path.join(ROOT, 'work', 'head_test')
samples = int(argv[1]) if len(argv) > 1 else 48
views = argv[2].split(',') if len(argv) > 2 else ['front', 'profile_left', 'three_quarter_front', 'back']
os.makedirs(out, exist_ok=True)
cfg = json.load(open(os.path.join(ROOT, 'config', 'morfi.json')))

bpy.ops.wm.read_factory_settings(use_empty=True)
t0 = time.time()
col = mu.get_collection('Morfi')
root = mu.empty('Morfi_Root', collection=col)
head, shape = face.build_head(cfg, col, os.path.join(ROOT, 'textures', 'master'), parent=root, tex_size=2048)
bpy.context.view_layer.update()
eyes = face.build_eyes(cfg, shape, head, col, os.path.join(ROOT, 'textures', 'master'))
brows = face.build_brows(cfg, shape, head, col)
bpy.context.view_layer.update()
gl, lenses, gp = accessories.build_glasses(cfg, shape, head, col)
skin = mats.skin('M_Skin', cfg['colors']['skin'])
accessories.build_cubes(cfg, shape.center, col, head, skin)
print('BUILD', time.time() - t0, 'glasses y', gp['yg'])
scol = mu.get_collection('Studio')
scene.build_studio(cfg, scol)
scene.setup_render(samples=samples, res=(1145, 1374))
for name, az in [(k, scene.VIEWS[k]['az']) for k in views]:
    cam = scene.make_camera('Cam_' + name, az, cfg, scol)
    bpy.context.scene.camera = cam
    bpy.context.scene.render.filepath = os.path.join(out, name + '.png')
    bpy.ops.render.render(write_still=True)
    print('RENDER', name, time.time() - t0)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, 'head_test.blend'))
