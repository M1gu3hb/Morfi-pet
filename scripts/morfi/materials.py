"""Material library for Morfi (Cycles render + glTF-friendly Principled setups).

Every material is built around a single Principled BSDF so the glTF exporter
can translate base colour / roughness / metallic / normal / sheen /
transmission / clearcoat. Procedural micro-detail (bump noise) is added for
Cycles; the glTF exporter ignores those nodes and uses the baked maps
documented in docs/validation.md instead.
"""
import bpy
from .meshutil import hex_to_linear


def _new(name):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (600, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (250, 0)
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return m, nt, bsdf


def _micro_bump(nt, bsdf, scale=110.0, strength=0.12, distance=0.0015, fine=520.0, normal_in=None):
    """Velvet / fleece micro relief: voronoi cells + fine noise -> bump."""
    tc = nt.nodes.new('ShaderNodeTexCoord')
    tc.location = (-1100, -300)
    vor = nt.nodes.new('ShaderNodeTexVoronoi')
    vor.location = (-850, -250)
    vor.feature = 'DISTANCE_TO_EDGE'
    vor.inputs['Scale'].default_value = scale
    vor.inputs['Randomness'].default_value = 1.0
    noi = nt.nodes.new('ShaderNodeTexNoise')
    noi.location = (-850, -500)
    noi.inputs['Scale'].default_value = fine
    noi.inputs['Detail'].default_value = 4.0
    nt.links.new(tc.outputs['Object'], vor.inputs['Vector'])
    nt.links.new(tc.outputs['Object'], noi.inputs['Vector'])
    mix = nt.nodes.new('ShaderNodeMath')
    mix.location = (-600, -350)
    mix.operation = 'MULTIPLY_ADD'
    nt.links.new(noi.outputs['Fac'], mix.inputs[0])
    mix.inputs[1].default_value = 0.35
    nt.links.new(vor.outputs['Distance'], mix.inputs[2])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.location = (-300, -350)
    bump.inputs['Strength'].default_value = strength
    bump.inputs['Distance'].default_value = distance
    nt.links.new(mix.outputs['Value'], bump.inputs['Height'])
    if normal_in is not None:
        nt.links.new(normal_in, bump.inputs['Normal'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return bump


TILES = {}
SKIN_NORMAL = 0.55  # strength of the skin relief normal map (config textures.skin.normal)


def load_tiles(paths):
    """Register tile textures {key: path} as Blender images."""
    import os
    for k, pth in paths.items():
        img = bpy.data.images.get(os.path.basename(pth))
        if img is None:
            img = bpy.data.images.load(pth, check_existing=True)
        img.colorspace_settings.name = 'Non-Color' if k.endswith('_n') else 'sRGB'
        TILES[k] = img


def normal_tex(nt, bsdf, key, strength=0.4, uv='UVMap', loc=(-650, -350)):
    img = TILES.get(key)
    if img is None:
        return None
    uvn = nt.nodes.new('ShaderNodeUVMap')
    uvn.uv_map = uv
    uvn.location = (loc[0] - 450, loc[1])
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = img
    t.location = (loc[0] - 250, loc[1])
    t.interpolation = 'Cubic'
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nm.location = (loc[0] + 50, loc[1])
    nm.uv_map = uv
    nm.inputs['Strength'].default_value = strength
    nt.links.new(uvn.outputs['UV'], t.inputs['Vector'])
    nt.links.new(t.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    return nm


def color_tex(nt, bsdf, key, uv='UVMap', loc=(-650, 250)):
    img = TILES.get(key)
    if img is None:
        return None
    uvn = nt.nodes.new('ShaderNodeUVMap')
    uvn.uv_map = uv
    uvn.location = (loc[0] - 450, loc[1])
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = img
    t.location = (loc[0] - 250, loc[1])
    nt.links.new(uvn.outputs['UV'], t.inputs['Vector'])
    nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
    return t


def _image(nt, img, loc, non_color=False):
    t = nt.nodes.new('ShaderNodeTexImage')
    t.location = loc
    t.image = img
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    return t


def skin(name='M_Skin', color='#0757F5', base_img=None, rough_img=None, sheen=0.35, tile_uv='UVMap'):
    # flocked velvet: no white specular (it washed out the saturated blue of
    # the references, measured R 21 vs 3 in sRGB), a blue sheen gives the soft rim
    m, nt, b = _new(name)
    b.inputs['Base Color'].default_value = hex_to_linear(color)
    b.inputs['Roughness'].default_value = 0.78
    b.inputs['Specular IOR Level'].default_value = 0.0
    b.inputs['Sheen Weight'].default_value = sheen
    b.inputs['Sheen Roughness'].default_value = 0.45
    b.inputs['Sheen Tint'].default_value = (0.0, 0.35, 1.0, 1.0)
    b.inputs['Diffuse Roughness'].default_value = 0.4
    if base_img is not None:
        t = _image(nt, base_img, (-300, 250))
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    elif 'skin_c' in TILES:
        # labyrinth lines in the colour (the head has them baked in its atlas)
        color_tex(nt, b, 'skin_c', uv=tile_uv)
    if rough_img is not None:
        t = _image(nt, rough_img, (-300, 0), non_color=True)
        nt.links.new(t.outputs['Color'], b.inputs['Roughness'])
    if not normal_tex(nt, b, 'skin_n', SKIN_NORMAL, uv=tile_uv):
        if not normal_tex(nt, b, 'velvet_n', 0.30, uv=tile_uv):
            _micro_bump(nt, b, scale=95.0, strength=0.22, distance=0.0016)
    return m


def flat(name, color, rough=0.5, metal=0.0, sheen=0.0, coat=0.0, coat_rough=0.1, spec=0.5,
         bump=None, base_img=None, tile_normal=None, tile_color=None):
    m, nt, b = _new(name)
    b.inputs['Base Color'].default_value = hex_to_linear(color)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    b.inputs['Specular IOR Level'].default_value = spec
    if sheen:
        b.inputs['Sheen Weight'].default_value = sheen
        b.inputs['Sheen Roughness'].default_value = 0.4
    if coat:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = coat_rough
    if base_img is not None:
        t = _image(nt, base_img, (-300, 250))
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    if tile_color:
        color_tex(nt, b, tile_color)
    if tile_normal:
        normal_tex(nt, b, tile_normal[0], tile_normal[1])
    elif bump:
        _micro_bump(nt, b, **bump)
    return m


def eye(name, img):
    m, nt, b = _new(name)
    t = _image(nt, img, (-300, 200))
    nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.45
    b.inputs['Specular IOR Level'].default_value = 0.0
    # cartoon sclera stays bright on the shaded side: a little self light
    nt.links.new(t.outputs['Color'], b.inputs['Emission Color'])
    b.inputs['Emission Strength'].default_value = 0.22
    return m


def cornea(name='M_Cornea'):
    """Clear wet cornea shell: thin-glass in Cycles, transmission in glTF."""
    m = glass(name)
    nt = m.node_tree
    for n in nt.nodes:
        if n.type == 'BSDF_GLOSSY':
            n.inputs['Roughness'].default_value = 0.0
        if n.type == 'FRESNEL':
            n.inputs['IOR'].default_value = 1.376
    nt.nodes['Principled BSDF'].inputs['IOR'].default_value = 1.376
    return m


def glass(name='M_Lens'):
    """Thin optical lens.

    Cycles: camera rays see a Fresnel mix of transparent + sharp glossy (thin
    glass, no refraction offset); every other ray passes straight through so
    the face behind keeps its full lighting. The Principled node (transmission
    1.0, IOR 1.45) is kept in the tree for glTF export (see export_assets.py).
    """
    m, nt, b = _new(name)
    b.inputs['Base Color'].default_value = (1, 1, 1, 1)
    b.inputs['Roughness'].default_value = 0.02
    b.inputs['Transmission Weight'].default_value = 1.0
    b.inputs['IOR'].default_value = 1.45
    out = nt.nodes['Material Output']
    out.target = 'EEVEE'
    out_c = nt.nodes.new('ShaderNodeOutputMaterial')
    out_c.target = 'CYCLES'
    out_c.location = (900, -250)
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    gl = nt.nodes.new('ShaderNodeBsdfGlossy')
    gl.inputs['Roughness'].default_value = 0.015
    fr = nt.nodes.new('ShaderNodeFresnel')
    fr.inputs['IOR'].default_value = 1.18
    thin = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(fr.outputs['Fac'], thin.inputs['Fac'])
    nt.links.new(tr.outputs['BSDF'], thin.inputs[1])
    nt.links.new(gl.outputs['BSDF'], thin.inputs[2])
    lp = nt.nodes.new('ShaderNodeLightPath')
    sel = nt.nodes.new('ShaderNodeMixShader')
    tr2 = nt.nodes.new('ShaderNodeBsdfTransparent')
    nt.links.new(lp.outputs['Is Camera Ray'], sel.inputs['Fac'])
    nt.links.new(tr2.outputs['BSDF'], sel.inputs[1])
    nt.links.new(thin.outputs['Shader'], sel.inputs[2])
    nt.links.new(sel.outputs['Shader'], out_c.inputs['Surface'])
    return m
