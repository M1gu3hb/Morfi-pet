"""Topology report of an AI mesh: loose parts, open edges, non-manifold edges, UV islands.

blender -b --factory-startup --python scripts/ia3d/mesh_report.py -- --model work/ia3d/morfi_glb1.glb
"""
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_contact as rc  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    model = argv[argv.index("--model") + 1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rc.import_model(os.path.abspath(model))
    rc.normalise(0.0)
    for ob in [o for o in bpy.data.objects if o.type == "MESH"]:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        if "--weld" in argv:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        boundary = sum(1 for e in bm.edges if e.is_boundary)
        nonman = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
        # connected components
        seen, parts = set(), []
        for v in bm.verts:
            if v.index in seen:
                continue
            stack, size = [v], 0
            seen.add(v.index)
            while stack:
                cur = stack.pop()
                size += 1
                for e in cur.link_edges:
                    o = e.other_vert(cur)
                    if o.index not in seen:
                        seen.add(o.index)
                        stack.append(o)
            parts.append(size)
        parts.sort(reverse=True)
        tri = sum(1 for f in bm.faces if len(f.verts) == 3)
        print(f"MESH {ob.name}: verts {len(bm.verts)} faces {len(bm.faces)} (tris {tri}) "
              f"boundary_edges {boundary} nonmanifold_edges {nonman} loose_parts {len(parts)} sizes {parts[:12]}")
        bm.free()


main()
