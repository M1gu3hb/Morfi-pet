"""Soft photo studio for Morfi: cyclorama, key/fill/rim/top area lights, HDRI reflections.

Used by render_beauty.py and render_showcase.py (import, then setup(scene, engine)).
"""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

HDRI = os.path.join(os.path.dirname(bpy.app.binary_path), "4.5", "datafiles", "studiolights", "world", "studio.exr")
BACKDROP = (0.60, 0.65, 0.72)
FLOOR = (0.36, 0.39, 0.44)


def _look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def cyclorama(name="Cyclorama", depth_front=14.0, back=2.6, radius=1.6, height=9.0, width=34.0):
    """Floor that bends up into a back wall (no visible horizon)."""
    prof = [(-depth_front, 0.0)]
    for a in np.linspace(0, math.pi / 2, 16):
        prof.append((back + radius * math.sin(a), radius - radius * math.cos(a)))
    prof.append((back + radius, height))
    verts, faces = [], []
    for i, (y, z) in enumerate(prof):
        verts += [(-width / 2, y, z), (width / 2, y, z)]
        if i:
            a = 2 * (i - 1)
            faces.append([a, a + 1, a + 3, a + 2])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new("Backdrop")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*FLOOR, 1)
    ramp.color_ramp.elements[1].position = 1.2
    ramp.color_ramp.elements[1].color = (*BACKDROP, 1)
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.9
    b.inputs["Specular IOR Level"].default_value = 0.2
    me.materials.append(mat)
    return ob


def area(name, loc, target, size, power, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "DISK"
    ld.size = size
    ld.energy = power
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    _look_at(ob, target)
    return ob


def setup(scene, engine="eevee", samples=64, res=(1920, 1080), percent=100):
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = percent
    scene.render.film_transparent = False
    scene.render.fps = 30
    # Standard keeps the brand blue (#014EF0) electric; AgX turned it lavender and Khronos
    # PBR Neutral violet. Whites are kept under clipping by the light balance instead.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = -0.45
    if engine == "eevee":
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        ee = scene.eevee
        ee.taa_render_samples = samples
        for attr, val in (("use_raytracing", True), ("use_shadows", True), ("shadow_ray_count", 2),
                          ("shadow_step_count", 8), ("use_fast_gi", True), ("fast_gi_method", "GLOBAL_ILLUMINATION")):
            if hasattr(ee, attr):
                setattr(ee, attr, val)
        if hasattr(ee, "ray_tracing_options"):
            ee.ray_tracing_options.resolution_scale = "2"
            ee.ray_tracing_options.use_denoise = True
    else:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 6
        prefs = bpy.context.preferences.addons["cycles"].preferences
        try:
            prefs.compute_device_type = "CUDA"
            prefs.get_devices()
            for d in prefs.devices:
                d.use = d.type == "CUDA"
            scene.cycles.device = "GPU"
        except Exception:
            scene.cycles.device = "CPU"
    # world: HDRI for reflections and soft ambient, not seen directly (the cyclorama is)
    world = bpy.data.worlds.new("Studio_HDRI")
    world.use_nodes = True
    nt = world.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(HDRI)
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.30
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    scene.world = world
    cyclorama()
    tgt = (0, 0, 0.55)
    lights = [
        area("Key", (-1.5, -1.9, 1.9), tgt, 1.4, 150, (1.0, 0.97, 0.93)),
        area("Fill", (1.9, -1.5, 1.0), tgt, 2.2, 70, (0.93, 0.96, 1.0)),
        area("Rim", (0.9, 1.7, 1.7), (0, 0, 0.7), 1.0, 170, (0.95, 0.97, 1.0)),
        area("Top", (0.0, -0.2, 2.8), tgt, 2.4, 15),
        area("Kick", (-1.6, 1.4, 0.6), (0, 0, 0.35), 0.8, 45),
    ]
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 50
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 5.6
    cam = bpy.data.objects.new("Cam", cd)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam, lights


def frame_camera(cam, az_deg, dist, height, target, lens=50, focus=None):
    a = math.radians(az_deg)
    cam.location = (target[0] + dist * math.sin(a), target[1] - dist * math.cos(a), height)
    _look_at(cam, target)
    cam.data.lens = lens
    cam.data.dof.focus_distance = focus if focus else (Vector(target) - cam.location).length
