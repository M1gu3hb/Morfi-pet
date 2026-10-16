"""Dump the normalised, welded AI mesh for analysis outside Blender.

blender -b --factory-startup --python scripts/ia3d/dump_mesh.py -- --model work/ia3d/morfi_esqueleto.glb --out work/ia3d/mesh.npz

Writes: verts (N,3) in the project frame, faces (F,3), loop_uv (F,3,2), loop_vert (F,3),
and the Meshy armature joints (name, head, tail, parent) in the same frame when present.
"""
import os
import sys

import bmesh
import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_contact as rc  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    model = argv[argv.index("--model") + 1]
    out = argv[argv.index("--out") + 1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rc.import_model(os.path.abspath(model))
    rc.normalise(0.0)
    ob = next(o for o in bpy.data.objects if o.type == "MESH")
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.transform(ob.matrix_world)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    uv = bm.loops.layers.uv.active
    verts = np.array([v.co[:] for v in bm.verts], np.float32)
    faces = np.array([[v.index for v in f.verts] for f in bm.faces], np.int32)
    loop_uv = np.array([[l[uv].uv[:] for l in f.loops] for f in bm.faces], np.float32)
    data = {"verts": verts, "faces": faces, "loop_uv": loop_uv}
    if arm is not None:
        mw = arm.matrix_world
        names, heads, tails, parents = [], [], [], []
        for b in arm.data.bones:
            names.append(b.name)
            heads.append((mw @ b.head_local)[:])
            tails.append((mw @ b.tail_local)[:])
            parents.append(b.parent.name if b.parent else "")
        data.update(joint_names=np.array(names), joint_heads=np.array(heads, np.float32),
                    joint_tails=np.array(tails, np.float32), joint_parents=np.array(parents))
    np.savez_compressed(os.path.abspath(out), **data)
    print("DONE", verts.shape, faces.shape)


main()
