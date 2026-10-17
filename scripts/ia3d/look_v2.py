"""Alternative look (NOT the default): Morfi as a satin vinyl toy with two rim lights.

Tried for the POS video (6 variants: coat, subsurface, rims, outline): every one of them lifts and
washes the brand blue, so the original materials of build_look.py stay the default. Kept to render
`scene.py render --look v2` side by side if the look is revisited.

blender -b <file>.blend --python scripts/ia3d/look_v2.py [-- --save]

Materials (applied to whatever file is open, the baked video file included):
  * skin (body + hands, one look): a satin coat over the blue, a touch of subsurface so the
    shadows stay coloured instead of going grey, a soft sheen at grazing angles;
  * glasses frame: glossier; lenses unchanged.
lights(scene): the studio of studio.py gets a warmer key, two cool rims that draw his
silhouette from both sides, and a soft top light on the head and the cubes.
"""
import sys

import bpy

SKIN = {"Roughness": 0.5, "Coat Weight": 0.14, "Coat Roughness": 0.32, "Subsurface Weight": 0.06,
        "Subsurface Scale": 0.02, "Sheen Weight": 0.45, "Sheen Roughness": 0.45, "Specular IOR Level": 0.4}
FRAME = {"Roughness": 0.22, "Coat Weight": 0.6, "Coat Roughness": 0.08}


def _principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if mat and mat.use_nodes else None


def _set(b, values):
    for k, v in values.items():
        if k in b.inputs and not b.inputs[k].is_linked:
            b.inputs[k].default_value = v
    if "Subsurface Radius" in b.inputs:
        b.inputs["Subsurface Radius"].default_value = (0.35, 0.55, 1.0)     # blue scatters furthest


def materials():
    for name in ("Skin", "Skin_Hand"):
        b = _principled(bpy.data.materials.get(name))
        if b:
            _set(b, SKIN)
    b = _principled(bpy.data.materials.get("Frame"))
    if b:
        _set(b, FRAME)


def lights(scene):
    """Rebalance the studio lights (call after studio.setup)."""
    def light(name):
        ob = bpy.data.objects.get(name)
        return ob.data if ob else None
    if light("Key"):
        light("Key").energy, light("Key").color = 150, (1.0, 0.95, 0.9)
    if light("Fill"):
        light("Fill").energy, light("Fill").color = 60, (0.88, 0.93, 1.0)
    if light("Rim"):
        light("Rim").energy, light("Rim").color = 210, (0.85, 0.92, 1.0)
    if light("Top"):
        light("Top").energy = 12
    from studio import area
    if not bpy.data.objects.get("Rim2"):
        area("Rim2", (-1.1, 1.5, 1.1), (0, 0, 0.6), 0.9, 170, (0.88, 0.93, 1.0))


if __name__ == "__main__":
    materials()
    if "--save" in sys.argv:
        bpy.ops.wm.save_mainfile()
    print("DONE look_v2")
