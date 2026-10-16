"""Inspect GLB files without Blender: meshes, triangles, materials, textures, skins, animations.

Usage: python scripts/inspect_glb.py file.glb [file2.glb ...] [--json out.json]
"""
import json
import struct
import sys
from pathlib import Path

COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    data = Path(path).read_bytes()
    magic, version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError(f"{path}: not a GLB file")
    offset, doc, binary = 12, None, b""
    while offset < len(data):
        chunk_len, chunk_type = struct.unpack_from("<I4s", data, offset)
        chunk = data[offset + 8: offset + 8 + chunk_len]
        if chunk_type == b"JSON":
            doc = json.loads(chunk)
        elif chunk_type == b"BIN\x00":
            binary = chunk
        offset += 8 + chunk_len
    return doc, binary, version


def image_size(blob):
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", blob[16:24])
        return "png", w, h
    if blob[:2] == b"\xff\xd8":
        i = 2
        while i < len(blob):
            marker, seg_len = blob[i + 1], struct.unpack(">H", blob[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", blob[i + 5:i + 9])
                return "jpeg", w, h
            i += 2 + seg_len
        return "jpeg", None, None
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp", None, None
    return "unknown", None, None


def summarize(path):
    doc, binary, version = read_glb(path)
    accessors = doc.get("accessors", [])
    meshes = []
    total_tris = total_verts = 0
    for mesh in doc.get("meshes", []):
        tris = verts = 0
        for prim in mesh["primitives"]:
            pos = accessors[prim["attributes"]["POSITION"]]
            verts += pos["count"]
            if "indices" in prim:
                tris += accessors[prim["indices"]]["count"] // 3
            else:
                tris += pos["count"] // 3
        meshes.append({
            "name": mesh.get("name"),
            "primitives": len(mesh["primitives"]),
            "triangles": tris,
            "vertices": verts,
            "attributes": sorted(mesh["primitives"][0]["attributes"].keys()),
            "morph_targets": len(mesh["primitives"][0].get("targets", [])),
        })
        total_tris += tris
        total_verts += verts

    views = doc.get("bufferViews", [])
    images = []
    for img in doc.get("images", []):
        entry = {"name": img.get("name"), "mime": img.get("mimeType")}
        if "bufferView" in img:
            bv = views[img["bufferView"]]
            start = bv.get("byteOffset", 0)
            blob = binary[start:start + bv["byteLength"]]
            kind, w, h = image_size(blob)
            entry.update({"bytes": bv["byteLength"], "format": kind, "width": w, "height": h})
        images.append(entry)

    materials = []
    for mat in doc.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        materials.append({
            "name": mat.get("name"),
            "baseColorFactor": pbr.get("baseColorFactor"),
            "baseColorTexture": pbr.get("baseColorTexture", {}).get("index"),
            "metallicRoughnessTexture": pbr.get("metallicRoughnessTexture", {}).get("index"),
            "normalTexture": mat.get("normalTexture", {}).get("index"),
            "metallic": pbr.get("metallicFactor"),
            "roughness": pbr.get("roughnessFactor"),
            "extensions": sorted(mat.get("extensions", {}).keys()),
        })

    nodes = doc.get("nodes", [])
    skins = []
    for skin in doc.get("skins", []):
        skins.append({
            "name": skin.get("name"),
            "joints": [nodes[j].get("name") for j in skin["joints"]],
        })

    animations = []
    for anim in doc.get("animations", []):
        duration = 0.0
        for sampler in anim["samplers"]:
            acc = accessors[sampler["input"]]
            if "max" in acc:
                duration = max(duration, acc["max"][0])
        animations.append({"name": anim.get("name"), "channels": len(anim["channels"]),
                           "duration_s": round(duration, 3)})

    # Bounding box of all POSITION accessors (local space, ignoring node transforms).
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for mesh in doc.get("meshes", []):
        for prim in mesh["primitives"]:
            acc = accessors[prim["attributes"]["POSITION"]]
            if "min" in acc:
                lo = [min(a, b) for a, b in zip(lo, acc["min"])]
                hi = [max(a, b) for a, b in zip(hi, acc["max"])]

    return {
        "file": str(path),
        "size_mb": round(Path(path).stat().st_size / 1e6, 1),
        "generator": doc.get("asset", {}).get("generator"),
        "extensions_used": doc.get("extensionsUsed", []),
        "scenes": len(doc.get("scenes", [])),
        "nodes": [{"name": n.get("name"), "mesh": n.get("mesh"), "skin": n.get("skin"),
                   "children": len(n.get("children", [])),
                   "rotation": n.get("rotation"), "scale": n.get("scale"),
                   "translation": n.get("translation")} for n in nodes if "mesh" in n or "skin" in n
                  or not n.get("children")][:40],
        "node_count": len(nodes),
        "meshes": meshes,
        "triangles": total_tris,
        "vertices": total_verts,
        "materials": materials,
        "images": images,
        "skins": skins,
        "animations": animations,
        "bbox_local": {"min": lo, "max": hi},
    }


def main(argv):
    out = None
    if "--json" in argv:
        i = argv.index("--json")
        out = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    reports = [summarize(p) for p in argv]
    text = json.dumps(reports, indent=1, ensure_ascii=False)
    if out:
        Path(out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
