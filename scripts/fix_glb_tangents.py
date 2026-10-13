"""Repair zero-length TANGENT vectors in a GLB in place (glTF validator
ACCESSOR_VECTOR3_NON_UNIT). Zero tangents come from triangles with no UV
area; they are replaced by a unit vector perpendicular to the normal.

    python3 scripts/fix_glb_tangents.py exports/morfi_web.glb [...]
"""
import json
import struct
import sys

import numpy as np

COMP = {5126: np.float32}


def fix(path):
    data = bytearray(open(path, 'rb').read())
    magic, version, length = struct.unpack_from('<III', data, 0)
    assert magic == 0x46546C67
    jlen, jtype = struct.unpack_from('<II', data, 12)
    gltf = json.loads(data[20:20 + jlen])
    boff = 20 + jlen
    blen, btype = struct.unpack_from('<II', data, boff)
    bin_start = boff + 8
    fixed = 0

    def view(acc_idx):
        acc = gltf['accessors'][acc_idx]
        bv = gltf['bufferViews'][acc['bufferView']]
        ncomp = {'VEC3': 3, 'VEC4': 4}[acc['type']]
        start = bin_start + bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
        stride = bv.get('byteStride', 4 * ncomp)
        return start, stride, acc['count'], ncomp

    for mesh in gltf.get('meshes', []):
        for prim in mesh['primitives']:
            at = prim['attributes']
            if 'TANGENT' not in at or 'NORMAL' not in at:
                continue
            ts, tstride, n, _ = view(at['TANGENT'])
            ns, nstride, _, _ = view(at['NORMAL'])
            for i in range(n):
                tx, ty, tz, tw = struct.unpack_from('<4f', data, ts + i * tstride)
                if tx * tx + ty * ty + tz * tz > 1e-8:
                    continue
                nx, ny, nz = struct.unpack_from('<3f', data, ns + i * nstride)
                nrm = np.array([nx, ny, nz])
                ref = np.array([1.0, 0, 0]) if abs(nx) < 0.9 else np.array([0, 1.0, 0])
                t = ref - nrm * (ref @ nrm)
                t /= np.linalg.norm(t)
                struct.pack_into('<4f', data, ts + i * tstride, float(t[0]), float(t[1]), float(t[2]), 1.0)
                fixed += 1
    open(path, 'wb').write(data)
    return fixed


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(p, 'fixed tangents:', fix(p))
