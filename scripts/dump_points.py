"""Dump the evaluated surface of Morfi as a dense point cloud (for fast
silhouette fitting outside Blender).

    blender -b source/morfi_master.blend --python scripts/dump_points.py -- --pose neutral --out work/calib/points_neutral.npz
"""
import argparse
import os
import sys

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--pose', default='neutral', choices=['neutral', 'hero'])
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    sc = bpy.context.scene
    rig = bpy.data.objects.get('Morfi_Rig')
    lap = bpy.data.objects.get('Laptop')
    if rig is None or not rig.animation_data:
        pass  # unrigged build: rest pose == neutral pose
    elif a.pose == 'hero':
        import render_hero
        rig.animation_data.action = bpy.data.actions['Pose_Hero']
        sc.frame_set(1)
        bpy.context.view_layer.update()
        render_hero.place_laptop(rig)
    else:
        rig.animation_data.action = bpy.data.actions['Pose_Neutral']
        sc.frame_set(1)
    if lap is not None and a.pose == 'neutral':
        lap.hide_render = True
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts, labels, names = [], [], []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or ob.name.startswith('Studio') or ob.name.startswith('Cornea'):
            continue
        if a.pose == 'neutral' and ob.name.startswith('Laptop'):
            continue
        if ob.hide_render and not ob.name.startswith('Laptop'):
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        n = len(me.vertices)
        co = np.empty(n * 3, np.float32)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        tri = np.empty(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get('vertices', tri)
        tri = tri.reshape(-1, 3)
        M = np.array(ev.matrix_world)
        co = co @ M[:3, :3].T + M[:3, 3]
        # vertices + triangle centroids + edge midpoints: dense enough to splat
        cen = co[tri].mean(1)
        mid = (co[tri[:, 0]] + co[tri[:, 1]]) / 2
        P = np.vstack([co, cen, mid])
        pts.append(P)
        labels.append(np.full(len(P), len(names), np.int16))
        names.append(ob.name)
        ev.to_mesh_clear()
    P = np.vstack(pts).astype(np.float32)
    L = np.concatenate(labels)
    np.savez_compressed(a.out, points=P, labels=L, names=np.array(names))
    print('[points]', a.pose, len(P), names)


if __name__ == '__main__':
    main()
