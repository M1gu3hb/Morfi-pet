"""Re-import the exported GLB into a clean Blender scene and render it, to prove
the exported asset (not the .blend) carries geometry, materials, textures,
skin and animations correctly.

    blender -b --factory-startup --python scripts/validate_assets.py -- [--glb exports/morfi_web.glb]

Writes renders/comparisons/reimport_<name>.png and docs/reimport_report.json.
(The Khronos validator runs separately: cd web && npm run validate)
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb', default=os.path.join(ROOT, 'exports', 'morfi_web.glb'))
    a = ap.parse_args(argv)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=a.glb)
    sc = bpy.context.scene
    meshes = [o for o in sc.objects if o.type == 'MESH']
    arms = [o for o in sc.objects if o.type == 'ARMATURE']
    tris = 0
    missing_tex = []
    for o in meshes:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    for img in bpy.data.images:
        if img.size[0] == 0:
            missing_tex.append(img.name)
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    dg = bpy.context.evaluated_depsgraph_get()
    for o in meshes:
        if o.name.startswith('Laptop'):
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        for v in me.vertices:
            w = ev.matrix_world @ v.co
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
        ev.to_mesh_clear()
    report = {
        'file': os.path.relpath(a.glb, ROOT), 'meshes': len(meshes), 'armatures': len(arms),
        'triangles': tris, 'materials': len(bpy.data.materials), 'images': len(bpy.data.images),
        'images_missing': missing_tex, 'actions': sorted(x.name for x in bpy.data.actions),
        'bbox_min': [round(v, 4) for v in lo], 'bbox_max': [round(v, 4) for v in hi],
        'height_without_pixels_expected': 1.0,
    }
    # quick studio render of the re-imported asset
    cd = bpy.data.cameras.new('C')
    cd.lens = 65.2
    cd.sensor_fit = 'VERTICAL'
    cd.sensor_height = 36
    cam = bpy.data.objects.new('C', cd)
    sc.collection.objects.link(cam)
    cam.location = (0, -2.5, 0.756)
    cam.rotation_euler = (Vector((0, 0, 0.52)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = cam
    w = bpy.data.worlds.new('W')
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.95, 0.95, 0.93, 1)
    w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8
    sc.world = w
    ld = bpy.data.lights.new('K', 'AREA')
    ld.size = 2.5
    ld.energy = 120
    lk = bpy.data.objects.new('K', ld)
    sc.collection.objects.link(lk)
    lk.location = (-2.2, -3.0, 2.9)
    lk.rotation_euler = (Vector((0, 0, 0.6)) - lk.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 24
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 573, 687
    sc.view_settings.view_transform = 'Standard'
    out = os.path.join(ROOT, 'renders', 'comparisons', 'reimport_' + os.path.splitext(os.path.basename(a.glb))[0] + '.png')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    report['render'] = os.path.relpath(out, ROOT)
    rp = os.path.join(ROOT, 'docs', 'reimport_report.json')
    allr = json.load(open(rp)) if os.path.exists(rp) else {}
    allr[report['file']] = report
    json.dump(allr, open(rp, 'w'), indent=1)
    print('[reimport]', json.dumps(report))


if __name__ == '__main__':
    main()
