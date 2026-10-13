"""Blender mesh / object helpers shared by the Morfi builders."""
import bpy
import bmesh
import numpy as np


def hex_to_linear(h, alpha=1.0):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (*lin, alpha)


def hex_to_srgb01(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def get_collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def mesh_object(name, verts, faces, collection=None, smooth=True, uvs=None, parent=None):
    """Create an object from numpy verts (N,3) and faces (list or (M,k) array).

    uvs: optional per-loop UV array (L,2) in face-corner order.
    """
    me = bpy.data.meshes.new(name)
    verts = np.asarray(verts, dtype=np.float64)
    if isinstance(faces, np.ndarray):
        faces_l = faces.tolist()
    else:
        faces_l = faces
    me.from_pydata(verts.tolist(), [], faces_l)
    me.validate(clean_customdata=False)
    me.update()
    if smooth:
        me.shade_smooth()
    if uvs is not None:
        uvl = me.uv_layers.new(name='UVMap')
        uvl.data.foreach_set('uv', np.asarray(uvs, np.float32).ravel())
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


def fast_mesh_object(name, verts, tris, collection=None, parent=None):
    """Triangle mesh creation via foreach_set (much faster for big meshes)."""
    verts = np.asarray(verts, np.float32)
    tris = np.asarray(tris, np.int32)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set('co', verts.ravel())
    me.loops.add(tris.size)
    me.loops.foreach_set('vertex_index', tris.ravel())
    me.polygons.add(len(tris))
    me.polygons.foreach_set('loop_start', np.arange(0, tris.size, 3, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


def empty(name, collection=None, parent=None, location=(0, 0, 0)):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_size = 0.05
    ob.location = location
    (collection or bpy.context.scene.collection).objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


def get_verts(ob):
    n = len(ob.data.vertices)
    co = np.empty(n * 3, np.float32)
    ob.data.vertices.foreach_get('co', co)
    return co.reshape(-1, 3).astype(np.float64)


def set_verts(ob, verts):
    ob.data.vertices.foreach_set('co', np.asarray(verts, np.float32).ravel())
    ob.data.update()


def smooth_mesh(ob, factor=0.5, iterations=2):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for _ in range(iterations):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=factor,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def apply_modifier(ob, mod):
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                   selected_editable_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def decimate(ob, ratio):
    mod = ob.modifiers.new('Decimate', 'DECIMATE')
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    apply_modifier(ob, mod)


def smart_uv(ob, angle=66.0, margin=0.004):
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                   selected_editable_objects=[ob]):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=np.radians(angle), island_margin=margin,
                                 scale_to_bounds=False)
        bpy.ops.object.mode_set(mode='OBJECT')


def cube_project_uv(ob, scale=1.0):
    """Box-projection UVs from object coordinates (per-face dominant axis)."""
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name='UVMap')
    uvl = me.uv_layers.active
    nl = len(me.loops)
    vidx = np.empty(nl, np.int32)
    me.loops.foreach_get('vertex_index', vidx)
    co = get_verts(ob)[vidx]
    npoly = len(me.polygons)
    pn = np.empty(npoly * 3, np.float32)
    me.polygons.foreach_get('normal', pn)
    pn = pn.reshape(-1, 3)
    ls = np.empty(npoly, np.int32)
    me.polygons.foreach_get('loop_start', ls)
    lt = np.empty(npoly, np.int32)
    me.polygons.foreach_get('loop_total', lt)
    loop_poly = np.repeat(np.arange(npoly), lt)
    n = np.abs(pn[loop_poly])
    ax = np.argmax(n, axis=1)
    uv = np.zeros((nl, 2))
    m = ax == 0
    uv[m] = co[m][:, [1, 2]]
    m = ax == 1
    uv[m] = co[m][:, [0, 2]]
    m = ax == 2
    uv[m] = co[m][:, [0, 1]]
    uvl.data.foreach_set('uv', (uv * scale).astype(np.float32).ravel())


def assign_material(ob, mat, slot=None):
    if slot is None:
        ob.data.materials.clear()
        ob.data.materials.append(mat)
    else:
        while len(ob.data.materials) <= slot:
            ob.data.materials.append(mat)
        ob.data.materials[slot] = mat


def set_face_materials(ob, mat_index_per_face):
    ob.data.polygons.foreach_set('material_index', np.asarray(mat_index_per_face, np.int32))
    ob.data.update()


def face_centers(ob):
    me = ob.data
    n = len(me.polygons)
    c = np.empty(n * 3, np.float32)
    me.polygons.foreach_get('center', c)
    return c.reshape(-1, 3).astype(np.float64)


def save_image(path, rgba, is_data=False):
    """Save float RGBA (H, W, 4) in [0,1] (row 0 = top) as 8-bit PNG via PIL."""
    from PIL import Image
    a = np.clip(np.asarray(rgba) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    mode = 'RGBA' if a.shape[2] == 4 else 'RGB'
    Image.fromarray(a, mode).save(path, optimize=False)
    return path


def load_image(path, colorspace='sRGB', name=None):
    img = bpy.data.images.load(path, check_existing=False)
    if name:
        img.name = name
    img.colorspace_settings.name = colorspace
    return img
