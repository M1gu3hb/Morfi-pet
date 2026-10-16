"""Dump the armature and skin weights of an AI-generated GLB (Blender, headless).

blender -b --factory-startup --python scripts/ia3d/inspect_rig.py -- --glb work/ia3d/morfi_esqueleto.glb --out work/ia3d/rig.json
"""
import argparse
import json
import sys

import bpy
import numpy as np


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.glb)

    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    report = {"objects": [(o.name, o.type, list(o.dimensions), list(o.location),
                           list(o.rotation_euler), list(o.scale)) for o in bpy.data.objects]}

    if arm is not None:
        mw = arm.matrix_world
        bones = []
        for b in arm.data.bones:
            bones.append({
                "name": b.name,
                "parent": b.parent.name if b.parent else None,
                "head": [round(v, 4) for v in (mw @ b.head_local)],
                "tail": [round(v, 4) for v in (mw @ b.tail_local)],
                "length": round(b.length, 4),
                "children": [c.name for c in b.children],
            })
        report["bones"] = bones

    for ob in meshes:
        me = ob.data
        nv = len(me.vertices)
        co = np.empty(nv * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        world = np.array(ob.matrix_world)
        co_w = co @ world[:3, :3].T + world[:3, 3]
        groups = {g.index: g.name for g in ob.vertex_groups}
        per_group = {name: {"count": 0, "sum": 0.0, "bbox_min": None, "bbox_max": None, "pts": []}
                     for name in groups.values()}
        unweighted = 0
        max_influences = 0
        for v in me.vertices:
            infl = [(g.group, g.weight) for g in v.groups if g.weight > 1e-4]
            max_influences = max(max_influences, len(infl))
            if not infl:
                unweighted += 1
            for gi, w in infl:
                if w >= 0.5:
                    per_group[groups[gi]]["pts"].append(v.index)
                per_group[groups[gi]]["count"] += 1
                per_group[groups[gi]]["sum"] += w
        stats = {}
        for name, d in per_group.items():
            pts = co_w[d.pop("pts")] if d["count"] else np.zeros((0, 3))
            stats[name] = {
                "verts_any": d["count"],
                "weight_sum": round(d["sum"], 1),
                "dominant_verts": int(len(pts)),
                "dominant_bbox": ([round(float(x), 3) for x in pts.min(0)],
                                  [round(float(x), 3) for x in pts.max(0)]) if len(pts) else None,
            }
        report.setdefault("meshes", []).append({
            "name": ob.name,
            "verts": nv,
            "polys": len(me.polygons),
            "bbox_world": [[round(float(x), 3) for x in co_w.min(0)], [round(float(x), 3) for x in co_w.max(0)]],
            "unweighted_verts": unweighted,
            "max_influences": max_influences,
            "groups": stats,
            "uv_layers": [uv.name for uv in me.uv_layers],
            "materials": [m.name for m in me.materials if m],
            "loose_parts_hint": None,
        })

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print("WROTE", args.out)


main()
