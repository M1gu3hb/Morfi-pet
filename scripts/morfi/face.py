"""Blender-side builders for the head, eyes, eyelids and brows."""
import math
import os
import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

from . import meshutil as mu
from . import materials as mats
from .head import HeadShape, eye_texture


def build_head(cfg, col, tex_dir, parent=None, tex_size=4096, lines=None):
    shape = HeadShape(cfg)
    verts, quads, uvs = shape.build_mesh()
    ob = mu.mesh_object('Head', verts, quads, collection=col, uvs=uvs, parent=parent)
    ob.location = shape.center
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=2e-6)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.shade_smooth()
    # textures
    os.makedirs(tex_dir, exist_ok=True)
    base_p = os.path.join(tex_dir, 'head_basecolor.png')
    rough_p = os.path.join(tex_dir, 'head_roughness.png')
    img, rough = shape.bake_textures(tex_size, lines=lines,
                                     line_dark=-cfg.get('textures', {}).get('skin', {}).get('gain', -0.10))
    mu.save_image(base_p, img)
    mu.save_image(rough_p, np.repeat(rough[..., None], 3, axis=2))
    bimg = mu.load_image(base_p, 'sRGB', 'T_Head_BaseColor')
    rimg = mu.load_image(rough_p, 'Non-Color', 'T_Head_Roughness')
    # second UV set for the tiling velvet normal map (box projection)
    uv_atlas = ob.data.uv_layers['UVMap']
    tile = ob.data.uv_layers.new(name='UVTile')
    ob.data.uv_layers.active = tile
    mu.cube_project_uv(ob, 2.5)
    ob.data.uv_layers.active = uv_atlas
    uv_atlas.active_render = True
    m = mats.skin('M_Head', cfg['colors']['skin'], base_img=bimg, rough_img=rimg, tile_uv='UVTile')
    mu.assign_material(ob, m)
    return ob, shape


def _eyeball_mesh(R, seg=72, rings=48):
    verts = [(0.0, -R, 0.0)]
    for i in range(1, rings):
        th = math.pi * i / rings
        for j in range(seg):
            ph = 2 * math.pi * j / seg
            verts.append((R * math.sin(th) * math.cos(ph), -R * math.cos(th), R * math.sin(th) * math.sin(ph)))
    verts.append((0.0, R, 0.0))
    faces = []
    for j in range(seg):
        faces.append((0, 1 + (j + 1) % seg, 1 + j))
    for i in range(rings - 2):
        a0 = 1 + i * seg
        b0 = 1 + (i + 1) * seg
        for j in range(seg):
            j1 = (j + 1) % seg
            faces.append((a0 + j, a0 + j1, b0 + j1, b0 + j))
    last = len(verts) - 1
    lb = 1 + (rings - 2) * seg
    for j in range(seg):
        faces.append((lb + j, lb + (j + 1) % seg, last))
    v = np.array(verts)
    uvs = []
    for f in faces:
        for vi in f:
            x, _, z = v[vi]
            uvs.append((0.5 + x / (2 * R), 0.5 + z / (2 * R)))
    return v, faces, np.array(uvs)


def build_eyes(cfg, shape, head, col, tex_dir):
    f = cfg['face']
    R = shape.eye_R
    img = eye_texture(cfg, 1024)
    p = os.path.join(tex_dir, 'eye_basecolor.png')
    mu.save_image(p, img)
    eimg = mu.load_image(p, 'sRGB', 'T_Eye_BaseColor')
    m = mats.eye('M_Eye', eimg)
    cmat = mats.cornea('M_Cornea')
    eyes = []
    target = shape.center + np.array(f['eye_look_target'])
    for name, c in (('Eye_R', shape.eye_centers[0]), ('Eye_L', shape.eye_centers[1])):
        # Eye_R = character's right eye (world -X)
        v, faces, uvs = _eyeball_mesh(R)
        ob = mu.mesh_object(name, v, faces, collection=col, uvs=uvs, parent=head)
        ob.location = c  # head-local (head is parent at head center)
        d = Vector(target - (shape.center + c))
        ob.rotation_mode = 'QUATERNION'
        ob.rotation_quaternion = d.to_track_quat('-Y', 'Z')
        mu.assign_material(ob, m)
        eyes.append(ob)
        # cornea: thin clear cap over the front of the eyeball
        cv, cfc, _ = _eyeball_mesh(R + 0.0016, seg=72, rings=48)
        keep = cv[:, 1] < -(R + 0.0016) * 0.80
        idx = np.nonzero(keep)[0]
        remap = -np.ones(len(cv), int)
        remap[idx] = np.arange(len(idx))
        faces_c = [tuple(remap[i] for i in fc) for fc in cfc if all(keep[i] for i in fc)]
        co = mu.mesh_object(name.replace('Eye', 'Cornea'), cv[idx], faces_c, collection=col, parent=ob)
        mu.assign_material(co, cmat)
        co.visible_shadow = False
    return eyes


def _bvh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    return BVHTree.FromObject(ob, dg), ob.matrix_world.copy()


def surface_hits(head, xz_world, y_from=-1.5):
    """Raycast +Y onto the head from the front; returns points & normals (world)."""
    bvh, M = _bvh(head)
    Mi = M.inverted()
    pts, nrm = [], []
    for x, z in xz_world:
        o = Mi @ Vector((x, y_from, z))
        d = (Mi.to_3x3() @ Vector((0, 1, 0))).normalized()
        hit = bvh.ray_cast(o, d)
        if hit[0] is None:
            raise RuntimeError(f'no head hit at {x},{z}')
        pts.append(np.array(M @ hit[0]))
        nrm.append(np.array((M.to_3x3() @ hit[1]).normalized()))
    return np.array(pts), np.array(nrm)


def build_brows(cfg, shape, head, col):
    f = cfg['face']
    m = mats.flat('M_Brow', cfg['colors']['brow'], rough=0.55, sheen=0.4,
                  bump=dict(scale=140.0, strength=0.05, distance=0.0008))
    L = f['brow_length']
    th = f['brow_thickness']
    hgt = f.get('brow_height', 0.0075)
    arch = f.get('brow_arch', 0.017)
    slope = f.get('brow_slope', 0.007)
    bx, bz = f['brow_center']
    n_seg = 40
    n_ring = 16
    brows = []
    for name, side in (('Brow_R', -1), ('Brow_L', 1)):
        t = np.linspace(-1, 1, n_seg)
        # t=-1 outer end, t=+1 inner end
        xs = side * (bx - t * L / 2)
        zs = bz + arch * (1 - t ** 2) - slope * (-t) - 0.003 * t ** 3
        xz = np.stack([xs, zs + shape.center[2]], 1)
        P, N = surface_hits(head, xz)
        verts = []
        for i in range(n_seg):
            T = P[min(i + 1, n_seg - 1)] - P[max(i - 1, 0)]
            T /= np.linalg.norm(T)
            Nn = N[i] - T * (N[i] @ T)
            Nn /= np.linalg.norm(Nn)
            B = np.cross(T, Nn)
            tt = abs(t[i])
            taper = (1 - tt ** 4) ** 0.3 * (1.0 - 0.15 * (t[i] > 0))
            w = th / 2 * max(taper, 0.05)
            h = hgt * max(taper, 0.05)
            C = P[i] + Nn * (h * 0.15)
            for k in range(n_ring):
                ph = 2 * math.pi * k / n_ring
                verts.append(C + B * math.cos(ph) * w + Nn * math.sin(ph) * h)
        verts = np.array(verts)
        faces = []
        for i in range(n_seg - 1):
            for k in range(n_ring):
                k1 = (k + 1) % n_ring
                a, b = i * n_ring + k, i * n_ring + k1
                c, d = (i + 1) * n_ring + k1, (i + 1) * n_ring + k
                faces.append((a, d, c, b))
        # end caps (fans to a centre vertex)
        c0 = len(verts)
        verts = np.vstack([verts, verts[:n_ring].mean(0), verts[-n_ring:].mean(0)])
        for k in range(n_ring):
            k1 = (k + 1) % n_ring
            faces.append((c0, k, k1))
            faces.append((c0 + 1, (n_seg - 1) * n_ring + k1, (n_seg - 1) * n_ring + k))
        # to head-local space
        verts = verts - shape.center
        ob = mu.mesh_object(name, verts, faces, collection=col, parent=head)
        mu.assign_material(ob, m)
        # fix winding if needed
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.shade_smooth()
        brows.append(ob)
    return brows


def build_eyelids(cfg, shape, head, col, skin_mat):
    """Upper eyelid shells (retracted inside the socket when open).

    Each lid is a spherical cap slightly larger than the eyeball, pivoting at
    the eye centre; rotate around local X (~+60 deg) to blink.
    """
    R = shape.eye_R + 0.0035
    lids = []
    for name, c in (('Eyelid_R', shape.eye_centers[0]), ('Eyelid_L', shape.eye_centers[1])):
        seg, rings = 48, 20
        verts, faces = [], []
        # cap from the top pole down to polar angle 75 deg, front hemisphere only
        th_max = math.radians(80)
        for i in range(rings + 1):
            th = th_max * i / rings
            for j in range(seg + 1):
                ph = math.pi * j / seg  # half circle: front half
                verts.append((R * math.sin(th) * math.cos(ph), -R * math.sin(th) * math.sin(ph), R * math.cos(th)))
        for i in range(rings):
            for j in range(seg):
                a = i * (seg + 1) + j
                faces.append((a, a + 1, a + seg + 2, a + seg + 1))
        ob = mu.mesh_object(name, np.array(verts), faces, collection=col, parent=head)
        ob.location = c
        ob.rotation_mode = 'XYZ'
        # retracted: rotate the cap back/up so it hides behind the socket rim
        ob.rotation_euler = (math.radians(-35), 0, 0)
        sol = ob.modifiers.new('Solidify', 'SOLIDIFY')
        sol.thickness = 0.002
        mu.assign_material(ob, skin_mat)
        lids.append(ob)
    return lids
