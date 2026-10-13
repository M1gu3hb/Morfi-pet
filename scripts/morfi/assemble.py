"""Blender-side assembly of SDF-built parts (body, clothes, shoes, laptop)."""
import numpy as np
import bpy

from . import meshutil as mu
from . import materials as mats
from . import sdf as S
from .body import BodySDF


def sdf_object(name, fn, bmin, bmax, h, col, parent=None, mat=None, smooth_iter=0, uv_scale=None):
    v, f = S.polygonize(fn, bmin, bmax, h)
    ob = mu.fast_mesh_object(name, v, f, collection=col, parent=parent)
    if smooth_iter:
        mu.smooth_mesh(ob, 0.5, smooth_iter)
    if mat is not None:
        mu.assign_material(ob, mat)
    if uv_scale:
        mu.cube_project_uv(ob, uv_scale)
    return ob


def build_body(cfg, col, parent, skin, h=0.0025):
    body = BodySDF(cfg)
    bmin, bmax = body.bounds()
    ob = sdf_object('Body_Base', body, bmin, bmax, h, col, parent=parent, mat=skin, uv_scale=2.5)
    return ob


def build_clothes(cfg, col, parent, tex_dir, h=0.0025, quality='final'):
    from . import clothes
    return clothes.build(cfg, col, parent, tex_dir, h, quality)


def build_shoes(cfg, col, parent, tex_dir, h=0.002, quality='final'):
    from . import shoes
    return shoes.build(cfg, col, parent, tex_dir, h, quality)


def build_laptop(cfg, col, parent, quality='final'):
    from . import laptop
    return laptop.build(cfg, col, parent, quality)
