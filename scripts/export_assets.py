"""Export glTF binaries from the rigged master scene.

    blender -b source/morfi_master.blend --python scripts/export_assets.py -- [--only master,web,parts]

exports/morfi_master.glb   full-resolution meshes, skin + all actions, 2K-4K textures
exports/morfi_web.glb      decimated meshes (~150k tris), 1K-2K textures, skin + actions
exports/parts/*.glb        each piece on its own (static, rest pose)

Objects keep their Blender names so the viewer can toggle them
(Hoodie*, Tshirt*, Shoe_*, Glasses_*, Pixel_*, Laptop, Body_Base, Head ...).
"""
import argparse
import json
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'exports')

# web triangle budgets per object (approximate)
WEB_TRIS = {
    'Head': 40000, 'Body_Base': 20000, 'Hoodie': 36000, 'Hoodie_Hem': 6000,
    'Hoodie_Cuff_L': 3000, 'Hoodie_Cuff_R': 3000, 'Hoodie_Zipper': 8000, 'Hoodie_Drawstrings': 3000,
    'Tshirt': 6000, 'Tshirt_Collar': 2000, 'Tshirt_Logo': 1500,
    'Shoe_L': 14000, 'Shoe_R': 14000, 'Glasses_Frame': 12000, 'Laptop': 6000,
    'Brow_L': 1200, 'Brow_R': 1200,
}
MASTER_TRIS = {k: v * 4 for k, v in WEB_TRIS.items()}
MASTER_TRIS['Head'] = 400000

PARTS = {
    'hoodie': ['Hoodie', 'Hoodie_Hem', 'Hoodie_Cuff_L', 'Hoodie_Cuff_R', 'Hoodie_Zipper', 'Hoodie_Drawstrings'],
    'tshirt': ['Tshirt', 'Tshirt_Collar', 'Tshirt_Logo'],
    'shoes': ['Shoe_L', 'Shoe_R'],
    'glasses': ['Glasses_Frame', 'Glasses_Lens_L', 'Glasses_Lens_R'],
    'pixels': ['Pixel_01', 'Pixel_02', 'Pixel_03'],
    'laptop': ['Laptop', 'Laptop_Logo'],
    'body_base': ['Body_Base'],
    'head': ['Head', 'Eye_L', 'Eye_R', 'Cornea_L', 'Cornea_R', 'EyeHighlight_L', 'EyeHighlight_R', 'Brow_L', 'Brow_R'],
}


def tri_count(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def decimate_to(ob, target):
    n = tri_count(ob)
    if n <= target:
        return n
    ratio = target / n
    mod = ob.modifiers.new('DecimateExport', 'DECIMATE')
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    # decimate must run before the armature modifier
    ob.modifiers.move(ob.modifiers.find(mod.name), 0)
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                   selected_editable_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return tri_count(ob)


def attach_laptop_hero():
    """Bone-parent the laptop to hand.R with the hero-pose placement."""
    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
    import render_hero
    rig = bpy.data.objects.get('Morfi_Rig')
    if rig is None or bpy.data.objects.get('Laptop') is None:
        return
    rig.animation_data.action = bpy.data.actions['Pose_Hero']
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    render_hero.place_laptop(rig)
    rig.animation_data.action = bpy.data.actions['Pose_Neutral']
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()


def bake_shot_morphs():
    """Shape keys 'Shot_<view>' for the web viewer: what render_views.py does to
    the face at render time for each reference shot (eyes turned to that camera
    with the fitted gaze, and in the profiles the face cheat of facecheat.py),
    stored on the eyes / corneas / highlights and, for the profiles, on the head,
    brows and glasses. The viewer turns a shot's key on while its camera is
    aligned with that photo, so the comparison shows the same face."""
    import numpy as np
    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
    from morfi import facecheat as FC
    from morfi import scene as SC
    from morfi.head import HeadShape
    rig, head = bpy.data.objects.get('Morfi_Rig'), bpy.data.objects.get('Head')
    if rig is None or head is None or rig.animation_data is None:
        return []
    cfg = json.load(open(os.path.join(ROOT, 'config', 'morfi.json')))
    shape = HeadShape(cfg)
    fc = cfg.get('face_cheat', {})
    eyes = [n for e, kids in FC.EYES.items() for n in (e,) + kids if bpy.data.objects.get(n) is not None]
    sc = bpy.context.scene
    views = sorted(a.name[4:] for a in bpy.data.actions if a.name.startswith('Ref_'))
    baked = []
    for v in views:
        rig.animation_data.action = bpy.data.actions['Ref_' + v]
        sc.frame_set(1)
        bpy.context.view_layer.update()
        cam = SC.view_camera(v, cfg)
        Hi = np.linalg.inv(np.array(head.matrix_world))
        M0 = {n: Hi @ np.array(bpy.data.objects[n].matrix_world) for n in eyes}
        restore = SC.eyes_look(cam.matrix_world.translation, SC.EYE_LOOK.get(v, 1.0),
                               gaze=cfg.get('view_gaze', {}).get(v))
        theta, depth = fc.get(v, 0.0), fc.get('depth', 1.0)
        target = {}
        for n in eyes:
            ob = bpy.data.objects[n]
            Q = FC._xf(Hi @ np.array(ob.matrix_world), FC._basis(ob))
            if theta:
                Q = FC.slide(Q, shape, theta, depth)
            target[n] = FC._xf(np.linalg.inv(M0[n]), Q)
        restore()
        if theta:
            for n in FC.FACE:
                ob = bpy.data.objects.get(n)
                if ob is None or ob.type != 'MESH':
                    continue
                M = Hi @ np.array(ob.matrix_world)
                P0 = FC._xf(M, FC._basis(ob))
                Q = FC.slide(P0, shape, theta, FC.point_depth(n, P0, shape, fc))
                if n.startswith('Glasses') and fc.get('glasses_z', 1.0) != 1.0:
                    zc = shape.eye_centers[0][2]
                    Q[:, 2] = zc + (Q[:, 2] - zc) * fc['glasses_z']
                target[n] = FC._xf(np.linalg.inv(M), Q)
        for n, co in target.items():
            ob = bpy.data.objects[n]
            if np.abs(co - FC._basis(ob)).max() < 1e-6:
                continue
            if not ob.data.shape_keys:
                ob.shape_key_add(name='Basis', from_mix=False)
            kb = ob.shape_key_add(name='Shot_' + v, from_mix=False)
            kb.data.foreach_set('co', co.ravel())
            kb.value = 0.0
        baked.append(v)
    rig.animation_data.action = bpy.data.actions['Pose_Neutral']
    sc.frame_set(1)
    bpy.context.view_layer.update()
    print('[export] shot morphs', baked)
    return baked


def morfi_objects():
    col = bpy.data.collections['Morfi']
    return [o for o in col.all_objects]


def downscale_images(max_size):
    for img in bpy.data.images:
        if img.source != 'FILE' or not img.size[0]:
            continue
        w, h = img.size
        if max(w, h) > max_size:
            s = max_size / max(w, h)
            img.scale(int(w * s), int(h * s))


def ensure_uvs(objects):
    """Every exported mesh gets a UV set (box projection) so textured materials are valid glTF."""
    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
    from morfi import meshutil as mu
    import bmesh
    for o in objects:
        if o.type != 'MESH':
            continue
        if not o.data.uv_layers:
            mu.cube_project_uv(o, 4.0)
        # remove degenerate faces left by decimation (they produce zero tangents)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
        bad = [f for f in bm.faces if f.calc_area() < 1e-12]
        if bad:
            bmesh.ops.delete(bm, geom=bad, context='FACES')
        bm.to_mesh(o.data)
        bm.free()
        o.data.update()


def skinned_to_root(objects):
    """glTF best practice: skinned meshes are root nodes (parent transforms are ignored)."""
    for o in objects:
        if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers) and o.parent is not None:
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw


def export(path, objects, animations=True, skins=True, image_format='AUTO', jpeg_quality=88, morphs=False):
    ensure_uvs(objects)
    if skins:
        skinned_to_root(objects)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.hide_set(False)
        o.hide_render = False
        o.select_set(True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kw = dict(filepath=path, export_format='GLB', use_selection=True, export_apply=False,
              export_yup=True, export_texcoords=True, export_normals=True, export_tangents=True,
              export_materials='EXPORT', export_image_format=image_format,
              export_jpeg_quality=jpeg_quality, export_animations=animations,
              export_skins=skins, export_morph=morphs, export_extras=True,
              export_cameras=False, export_lights=False)
    if animations:
        kw.update(export_animation_mode='ACTIONS', export_force_sampling=True, export_frame_range=False,
                  export_anim_single_armature=True, export_reset_pose_bones=True)
    bpy.ops.export_scene.gltf(**kw)
    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
    from fix_glb_tangents import fix
    fix(path)
    print('[export]', path, f'{os.path.getsize(path) / 1e6:.1f} MB')


def stats(objs):
    tot = 0
    rows = []
    for o in objs:
        if o.type == 'MESH':
            n = tri_count(o)
            tot += n
            rows.append((o.name, n, len(o.data.materials)))
    return tot, rows


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='master,web,parts')
    a = ap.parse_args(argv)
    todo = a.only.split(',')
    src = bpy.data.filepath
    report = {}
    rig = bpy.data.objects.get('Morfi_Rig')
    if rig and rig.animation_data:
        rig.animation_data.action = bpy.data.actions.get('Pose_Neutral')
    if 'master' in todo:
        attach_laptop_hero()
        for o in morfi_objects():
            if o.type == 'MESH' and o.name in MASTER_TRIS:
                decimate_to(o, MASTER_TRIS[o.name])
        objs = morfi_objects()
        export(os.path.join(OUT, 'morfi_master.glb'), objs)
        report['master'] = stats(objs)
        bpy.ops.wm.open_mainfile(filepath=src)
    if 'web' in todo:
        attach_laptop_hero()
        for o in morfi_objects():
            if o.type == 'MESH' and o.name in WEB_TRIS:
                decimate_to(o, WEB_TRIS[o.name])
        downscale_images(2048)
        for img in bpy.data.images:
            if img.name.startswith('T_Head') and img.size[0] > 2048:
                img.scale(2048, 2048)
        objs = morfi_objects()
        ensure_uvs(objs)  # (edits the meshes: before the shape keys are added)
        shots = bake_shot_morphs()
        export(os.path.join(OUT, 'morfi_web.glb'), objs, image_format='JPEG', jpeg_quality=90, morphs=bool(shots))
        report['web'] = stats(objs)
        bpy.ops.wm.open_mainfile(filepath=src)
    if 'parts' in todo:
        rig = bpy.data.objects.get('Morfi_Rig')
        for o in morfi_objects():
            if o.type == 'MESH' and o.name in WEB_TRIS:
                decimate_to(o, MASTER_TRIS[o.name] // 2)
        # the T-shirt on its own is the product state, with its short sleeves
        # (worn under the hoodie it has none: they are never seen)
        tp = bpy.data.objects.get('Tshirt_Product')
        if tp is not None:
            decimate_to(tp, MASTER_TRIS['Tshirt'] // 2)
        tc = bpy.data.objects.get('Tshirt_Product_Collar')
        if tc is not None:
            decimate_to(tc, MASTER_TRIS['Tshirt_Collar'] // 2)
        for part, names in PARTS.items():
            if tp is not None:
                names = ['Tshirt_Product' if n == 'Tshirt' else n for n in names]
            if tc is not None:
                names = ['Tshirt_Product_Collar' if n == 'Tshirt_Collar' else n for n in names]
            objs = [bpy.data.objects[n] for n in names if n in bpy.data.objects]
            # include children (e.g. eyes under head handled explicitly)
            export(os.path.join(OUT, 'parts', f'morfi_{part}.glb'), objs, animations=False, skins=False)
        bpy.ops.wm.open_mainfile(filepath=src)
    with open(os.path.join(OUT, 'export_report.json'), 'w') as f:
        json.dump({k: {'triangles': v[0], 'objects': [{'name': n, 'triangles': t, 'materials': m} for n, t, m in v[1]]}
                   for k, v in report.items()}, f, indent=1)


if __name__ == '__main__':
    main()
