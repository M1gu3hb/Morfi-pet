"""Clearance between the waving hand (Body_Base vertices weighted to hand.R /
fingers.R / thumb.R) and the head over the Wave action; negative = inside.

    blender -b source/morfi_master.blend --python scripts/check_hand_head.py
"""
import bpy, sys
import numpy as np
from mathutils.bvhtree import BVHTree
dg = bpy.context.evaluated_depsgraph_get()
rig = bpy.data.objects['Morfi_Rig']
rig.animation_data.action = bpy.data.actions['Wave']
sc = bpy.context.scene
head = bpy.data.objects['Head']
body = bpy.data.objects['Body_Base']
vg = {g.index: g.name for g in body.vertex_groups}
idx = [v.index for v in body.data.vertices if any(vg[g.group] in ('hand.R', 'fingers.R', 'thumb.R') and g.weight > 0.5 for g in v.groups)]
for f in range(1, 50, 4):
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    hb = BVHTree.FromObject(head, dg)
    he = head.evaluated_get(dg)
    Mi = head.matrix_world.inverted()
    be = body.evaluated_get(dg)
    me = be.to_mesh()
    dmin = 9.0
    for i in idx:
        p = Mi @ (body.matrix_world @ me.vertices[i].co)
        hit = hb.find_nearest(p)
        if hit[0] is not None:
            d = hit[3]
            # inside the head? (ray along the normal)
            if (p - hit[0]).dot(hit[1]) < 0:
                d = -d
            dmin = min(dmin, d)
    be.to_mesh_clear()
    print(f'frame {f} min hand-head distance {dmin:.3f} m')
