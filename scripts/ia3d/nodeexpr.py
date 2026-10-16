"""Write shader math as Python expressions; each operation adds Blender shader nodes.

    ng = bpy.data.node_groups.new("X", "ShaderNodeTree")
    E = NodeExpr(ng)
    p = E.input("UV", "NodeSocketVector")
    d = (E.sep(p)[0] - 0.1).abs()
    E.output("Mask", E.smoothstep(0.02, 0.0, d))

Scalars are float sockets; vectors use VectorMath. Only what the face shaders need.
"""
import bpy


class S:
    """A float socket wrapper with operator overloading."""

    def __init__(self, E, sock):
        self.E, self.sock = E, sock

    def _bin(self, op, other, swap=False):
        a, b = (other, self) if swap else (self, other)
        return self.E.math(op, a, b)

    def __add__(self, o): return self._bin("ADD", o)
    def __radd__(self, o): return self._bin("ADD", o, True)
    def __sub__(self, o): return self._bin("SUBTRACT", o)
    def __rsub__(self, o): return self._bin("SUBTRACT", o, True)
    def __mul__(self, o): return self._bin("MULTIPLY", o)
    def __rmul__(self, o): return self._bin("MULTIPLY", o, True)
    def __truediv__(self, o): return self._bin("DIVIDE", o)
    def __rtruediv__(self, o): return self._bin("DIVIDE", o, True)
    def __neg__(self): return self.E.math("MULTIPLY", self, -1.0)
    def __pow__(self, o): return self._bin("POWER", o)
    def abs(self): return self.E.math("ABSOLUTE", self)
    def sqrt(self): return self.E.math("SQRT", self)
    def clamp(self): return self.E.math("MINIMUM", self.E.math("MAXIMUM", self, 0.0), 1.0)


class NodeExpr:
    def __init__(self, tree):
        self.t = tree
        self.nodes, self.links = tree.nodes, tree.links
        self.x = 0
        self.gin = self.gout = None
        if hasattr(tree, "interface"):
            self.gin = next((n for n in self.nodes if n.type == "GROUP_INPUT"), None) or self.nodes.new("NodeGroupInput")
            self.gout = next((n for n in self.nodes if n.type == "GROUP_OUTPUT"), None) or self.nodes.new("NodeGroupOutput")

    # ------------------------------------------------------------ plumbing
    def _node(self, kind):
        n = self.nodes.new(kind)
        n.location = (self.x, 0)
        self.x += 30
        return n

    def _in(self, sock, v):
        if isinstance(v, S):
            self.links.new(v.sock, sock)
        elif isinstance(v, (tuple, list)):
            sock.default_value = v
        elif hasattr(v, "is_output"):
            self.links.new(v, sock)
        else:
            sock.default_value = float(v)

    def input(self, name, kind="NodeSocketFloat", default=0.0):
        self.t.interface.new_socket(name, in_out="INPUT", socket_type=kind)
        item = self.t.interface.items_tree[name]
        if kind == "NodeSocketFloat":
            item.default_value = default
        elif default is not None and kind in ("NodeSocketColor", "NodeSocketVector"):
            item.default_value = default
        return S(self, self.gin.outputs[name])

    def output(self, name, value, kind="NodeSocketFloat"):
        self.t.interface.new_socket(name, in_out="OUTPUT", socket_type=kind)
        self._in(self.gout.inputs[name], value)

    def const(self, v):
        n = self._node("ShaderNodeValue")
        n.outputs[0].default_value = float(v)
        return S(self, n.outputs[0])

    # ------------------------------------------------------------ math
    def math(self, op, a, b=None):
        n = self._node("ShaderNodeMath")
        n.operation = op
        self._in(n.inputs[0], a)
        if b is not None:
            self._in(n.inputs[1], b)
        return S(self, n.outputs[0])

    def min(self, a, b): return self.math("MINIMUM", a, b)
    def max(self, a, b): return self.math("MAXIMUM", a, b)

    def smoothstep(self, e0, e1, x):
        """Hermite smoothstep that also works with e0 > e1 (falling edge)."""
        t = ((x - e0) / (self._s(e1) - e0)).clamp()
        return t * t * (3.0 - 2.0 * t)

    def _s(self, v):
        return v if isinstance(v, S) else self.const(v)

    def mix(self, a, b, t):
        return a + (self._s(b) - a) * t

    def length2(self, x, y):
        return (x * x + y * y).sqrt()

    def sep(self, vec):
        n = self._node("ShaderNodeSeparateXYZ")
        self._in(n.inputs[0], vec)
        return S(self, n.outputs[0]), S(self, n.outputs[1]), S(self, n.outputs[2])

    def mix_color(self, a, b, t):
        """Linear mix of two colours (RGBA tuples or colour sockets) by a float."""
        n = self._node("ShaderNodeMix")
        n.data_type = "RGBA"
        n.blend_type = "MIX"
        self._in(n.inputs["Factor"], t)
        self._in(n.inputs[6], a)   # A (colour)
        self._in(n.inputs[7], b)   # B (colour)
        return n.outputs[2]
