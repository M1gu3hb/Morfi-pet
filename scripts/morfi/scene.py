"""Studio scene: backdrop, lights, cameras, render settings."""
import math
import bpy
import numpy as np
from mathutils import Vector

from . import meshutil as mu
from . import materials as mats

# Camera presets. azimuth: 0 = front (camera at -Y). Positive azimuth moves the
# camera toward Morfi's left side (+X).
VIEWS = {
    'front': dict(az=0.0),
    'profile_left': dict(az=90.0),     # Morfi looks to the image left (camera on his left, +X)
    'back': dict(az=180.0),
    'profile_right': dict(az=-90.0),   # Morfi looks to the image right
    'three_quarter_front': dict(az=33.0),
    'three_quarter_back': dict(az=-150.0),
}


def setup_render(engine='CYCLES', samples=128, res=(1145, 1374), transparent=False, denoise=True):
    sc = bpy.context.scene
    sc.render.engine = engine
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = denoise
    try:
        sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    sc.cycles.max_bounces = 8
    sc.cycles.transmission_bounces = 8
    sc.cycles.transparent_max_bounces = 16
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA' if transparent else 'RGB'
    sc.render.use_compositing = not transparent
    sc.render.image_settings.color_depth = '8'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
    sc.render.threads_mode = 'AUTO'
    return sc


def build_studio(cfg, col):
    """Shadow-catcher floor + soft area lights; background composited flat.

    Renders are made with a transparent film; the floor only catches shadows
    and the compositor lays the result over the reference background colour.
    """
    floor_v = np.array([(-8, -8, 0), (8, -8, 0), (8, 8, 0), (-8, 8, 0)], float)
    floor = mu.mesh_object('Studio_Floor', floor_v, [(0, 1, 2, 3)], collection=col)
    floor.is_shadow_catcher = True
    mu.assign_material(floor, mats.flat('M_Studio', cfg['colors']['background'], rough=1.0, spec=0.0))

    def area(name, loc, target, size, power, color=(1, 1, 1), shape='DISK'):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.shape = shape
        ld.size = size
        ld.energy = power
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        col.objects.link(ob)
        ob.location = loc
        d = Vector(target) - Vector(loc)
        ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        return ob
    L = cfg.get('lights', {})
    area('Light_Key', L.get('key_loc', (-2.2, -3.0, 2.9)), L.get('key_target', (0, 0, 0.5)), L.get('key_size', 2.6), L.get('key_power', 95.0))
    area('Light_Fill', L.get('fill_loc', (3.0, -2.4, 1.3)), (0, 0, 0.5), L.get('fill_size', 3.0), L.get('fill_power', 30.0))
    area('Light_Rim', L.get('rim_loc', (1.2, 2.6, 2.6)), (0, 0, 0.7), L.get('rim_size', 2.0), L.get('rim_power', 45.0))
    area('Light_Top', L.get('top_loc', (0.0, -0.6, 3.6)), (0, 0, 0.5), L.get('top_size', 3.0), L.get('top_power', 30.0))
    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bgn = nt.nodes.get('Background')
    bgn.inputs['Color'].default_value = (1, 1, 1, 1)
    bgn.inputs['Strength'].default_value = L.get('world', 0.5)
    # glossy rays see a dark studio (so eyes/pupils/lenses keep deep blacks and
    # only the softboxes show up as highlights); diffuse rays see the white room
    dark = nt.nodes.new('ShaderNodeBackground')
    dark.inputs['Color'].default_value = (1, 1, 1, 1)
    dark.inputs['Strength'].default_value = L.get('world_glossy', 0.06)
    lp = nt.nodes.new('ShaderNodeLightPath')
    mix = nt.nodes.new('ShaderNodeMixShader')
    out = nt.nodes.get('World Output')
    nt.links.new(lp.outputs['Is Glossy Ray'], mix.inputs['Fac'])
    nt.links.new(bgn.outputs['Background'], mix.inputs[1])
    nt.links.new(dark.outputs['Background'], mix.inputs[2])
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
    # small catch-light that only the eyes see (light linking) -> crisp
    # specular dot on the pupils like the reference renders
    eyes = bpy.data.collections.get('EyeCatch') or bpy.data.collections.new('EyeCatch')
    no_cornea = bpy.data.collections.get('NoCornea') or bpy.data.collections.new('NoCornea')
    for n in ('Cornea_L', 'Cornea_R'):
        ob = bpy.data.objects.get(n)
        if ob and ob.name not in eyes.objects:
            eyes.objects.link(ob)
        if ob and ob.name not in no_cornea.objects:
            no_cornea.objects.link(ob)
    for i in range(len(no_cornea.collection_objects)):
        no_cornea.collection_objects[i].light_linking.link_state = 'EXCLUDE'
    for ln in ('Light_Key', 'Light_Fill', 'Light_Rim', 'Light_Top'):
        lo = bpy.data.objects.get(ln)
        if lo:
            lo.light_linking.receiver_collection = no_cornea
    catch = area('Light_EyeCatch', L.get('catch_loc', (-0.9, -2.6, 1.55)), (0, 0, 0.72),
                 L.get('catch_size', 0.22), L.get('catch_power', 40.0))
    catch.visible_diffuse = False
    catch.visible_transmission = False
    catch.visible_volume_scatter = False
    try:
        catch.light_linking.receiver_collection = eyes
    except Exception as e:  # pragma: no cover
        print('light linking unavailable', e)
    setup_compositor(cfg)
    return floor


def setup_compositor(cfg, enabled=True):
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new('CompositorNodeRLayers')
    rl.location = (-300, 0)
    comp = nt.nodes.new('CompositorNodeComposite')
    comp.location = (400, 0)
    ao = nt.nodes.new('CompositorNodeAlphaOver')
    ao.location = (100, 0)
    ao.name = 'BG_Over'
    bg = mu.hex_to_linear(cfg['colors']['background'])
    ao.inputs[1].default_value = bg
    nt.links.new(rl.outputs['Image'], ao.inputs[2])
    nt.links.new(ao.outputs['Image'], comp.inputs['Image'])
    sc.render.use_compositing = enabled
    return nt


def set_transparent_output(transparent):
    """transparent=True: RGBA output without floor shadows/background."""
    sc = bpy.context.scene
    sc.render.film_transparent = True
    sc.render.use_compositing = not transparent
    sc.render.image_settings.color_mode = 'RGBA' if transparent else 'RGB'
    fl = bpy.data.objects.get('Studio_Floor')
    if fl:
        fl.hide_render = transparent


def make_camera(name, az_deg, cfg, col, target=None, dist=None, height=None, lens=None):
    c = cfg.get('camera', {})
    lens = lens or c.get('lens', 58.0)
    dist = dist or c.get('distance', 2.1)
    height = height if height is not None else c.get('height', 0.62)
    target = target or c.get('target', (0.0, 0.0, 0.565))
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_fit = 'VERTICAL'
    cd.sensor_height = 36.0
    cd.sensor_width = 36.0
    cd.clip_start = 0.05
    cd.clip_end = 50
    ob = bpy.data.objects.new(name, cd)
    col.objects.link(ob)
    a = math.radians(az_deg)
    tx, ty, tz = target
    ob.location = (tx + dist * math.sin(a), ty - dist * math.cos(a), height)
    d = Vector(target) - Vector(ob.location)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return ob


# how much the eyes turn toward each camera (0 = modelled forward gaze, 1 = at the lens).
# The references always show Morfi looking at the viewer in front / 3-4 shots.
EYE_LOOK = {'front': 1.0, 'three_quarter_front': 1.0, 'profile_left': 0.35, 'profile_right': 0.35,
            'back': 0.0, 'three_quarter_back': 0.0, 'hero': 1.0}


def eyes_look(cam_loc, k):
    """Turn both eyes toward a camera (same rotation for both, so the modelled
    convergence is kept). Works on the rigged file and on an unrigged build.
    Returns a restore() callable.
    """
    from mathutils import Matrix, Vector
    eyes = [bpy.data.objects.get('Eye_L'), bpy.data.objects.get('Eye_R')]
    if k <= 0 or any(e is None for e in eyes):
        return lambda: None
    bpy.context.view_layer.update()
    cs = [e.matrix_world.translation.copy() for e in eyes]
    ds = [-(e.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized() for e in eyes]
    mid = (cs[0] + cs[1]) / 2
    fwd = (ds[0] + ds[1]).normalized()
    to_cam = (Vector(cam_loc) - mid).normalized()
    look = fwd.slerp(to_cam, k)
    rq = fwd.rotation_difference(look)
    # Rotate the eye objects themselves (their transform relative to the eye
    # bone). Rotating the pose bones would be undone at render time, when the
    # active action (whose keys include every bone) is evaluated again.
    undo = []
    for e, c in zip(eyes, cs):
        M = Matrix.Translation(c) @ rq.to_matrix().to_4x4() @ Matrix.Translation(-c)
        undo.append((e, e.matrix_basis.copy()))
        e.matrix_world = M @ e.matrix_world
    bpy.context.view_layer.update()

    def restore():
        for ob, old in undo:
            ob.matrix_basis = old
        bpy.context.view_layer.update()
    return restore
