"""Dump the rest-pose surface of the rigged character with its bone weights
(for pose fitting outside Blender with linear blend skinning).

    blender -b source/morfi_master.blend --python scripts/dump_skin.py -- --out work/calib/skin.npz

points (N,3) world, bones (B) names, heads (B,3) rest bone heads, parents (B),
idx (N,4) bone indices, w (N,4) weights, labels (N) object index into names.
"""
import argparse
import os
import sys

import bpy
import numpy as np


def owner_bone(ob):
    """Bone that drives a rigid object (walks up object parents)."""
    o = ob
    while o is not None:
        if o.parent_type == 'BONE' and o.parent is not None:
            return o.parent_bone
        o = o.parent
    return None


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    sc = bpy.context.scene
    rig = bpy.data.objects['Morfi_Rig']
    rig.animation_data.action = bpy.data.actions['Pose_Neutral']
    sc.frame_set(1)
    bpy.context.view_layer.update()
    bones = [b.name for b in rig.data.bones]
    bi = {n: i for i, n in enumerate(bones)}
    RW = np.array(rig.matrix_world)
    heads = np.array([(RW @ np.append(np.array(b.head_local), 1.0))[:3] for b in rig.data.bones])
    parents = np.array([bi[b.parent.name] if b.parent else -1 for b in rig.data.bones])
    dg = bpy.context.evaluated_depsgraph_get()
    P_all, I_all, W_all, L_all, names = [], [], [], [], []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or ob.name.startswith(('Studio', 'Cornea', 'Laptop')) or ob.hide_render:
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        n = len(me.vertices)
        co = np.empty(n * 3, np.float32)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        M = np.array(ev.matrix_world)
        co = co @ M[:3, :3].T + M[:3, 3]
        idx = np.zeros((n, 4), np.int16)
        w = np.zeros((n, 4), np.float32)
        if any(m.type == 'ARMATURE' for m in ob.modifiers) and ob.vertex_groups:
            gmap = {g.index: bi.get(g.name, -1) for g in ob.vertex_groups}
            src = ob.data  # vertex groups live on the original mesh (same topology)
            for v in src.vertices:
                gs = sorted(((g.weight, gmap[g.group]) for g in v.groups if gmap.get(g.group, -1) >= 0), reverse=True)[:4]
                s = sum(x[0] for x in gs) or 1.0
                for k, (wt, b) in enumerate(gs):
                    idx[v.index, k] = b
                    w[v.index, k] = wt / s
        else:
            b = owner_bone(ob)
            idx[:, 0] = bi[b] if b in bi else bi['root']
            w[:, 0] = 1.0
        tri = np.empty(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get('vertices', tri)
        tri = tri.reshape(-1, 3)
        cen = co[tri].mean(1)
        mid = (co[tri[:, 0]] + co[tri[:, 1]]) / 2
        P_all += [co, cen, mid]
        I_all += [idx, idx[tri[:, 0]], idx[tri[:, 0]]]
        W_all += [w, w[tri[:, 0]], w[tri[:, 0]]]
        L_all.append(np.full(n + 2 * len(tri), len(names), np.int16))
        names.append(ob.name)
        ev.to_mesh_clear()
        print('[skin]', ob.name, n)
    np.savez_compressed(a.out, points=np.vstack(P_all).astype(np.float32), idx=np.vstack(I_all), w=np.vstack(W_all),
                        bones=np.array(bones), heads=heads.astype(np.float32), parents=parents,
                        labels=np.concatenate(L_all), names=np.array(names))
    print('[skin] saved', a.out)


if __name__ == '__main__':
    main()
