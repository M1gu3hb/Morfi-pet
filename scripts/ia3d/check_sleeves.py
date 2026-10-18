"""Per-frame check that the hand / forearm skin stays inside the hoodie sleeve and cuff.

blender -b <look.blend> --python scripts/ia3d/check_sleeves.py -- --action Wave,Present|all [--step 2]
    [--actions-from work/ia3d/morfi_ia_scenes.blend] [--clips-from work/ia3d/morfi_ia_anim6.blend] [--verbose] [--json out.json]

The sleeve surface is the Hoodie vertices skinned to the arm bones of one side (evaluated), behind
the cuff opening (the open loop that ends the sleeve). Signed distance = (p - closest cloth vertex) .
outward direction of the sleeve tube there, positive = outside the cloth.
  * "skin" points are the hand-mesh and body-skin vertices that sit INSIDE the sleeve in the rest
    pose (wrist, forearm): `out` is how far (mm) the worst one has come out of the cloth with the cloth
    between it and the sleeve axis (a bent wrist swings points beside the cuff opening, beyond the straight
    sleeve tube but in free air: that is the hand coming out of the cuff; --raw counts those too);
  * the visible hand vertices (thumb / fingers / palm) that swing behind the cuff plane beside
    the opening must not be inside the cloth: `x_*` is how deep (mm) the worst one has sunk in.
Prints per action the WORST numbers per hand (with the frame) and a final WORST summary in mm,
like check_clearance.py. `--actions-from` appends the actions whose name starts with --prefix
(default Scene_) from another .blend, which is only read.
"""
import argparse
import json
import os
import sys

import bpy
import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim import rigmap  # noqa: E402

POKE = 0.004          # a skin point this far outside the cloth is a candidate for "poking out" ...
NEAR = 0.015          # a visible vertex this close to the cloth counts as touching it
CROSS_AX = 0.012     # a visible vertex must be this far behind the cuff plane to count as inside the wall


def evaluated(ob):
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    M = np.array(ob.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3], None


def weight_matrix(ob, names):
    ids = {g.index: names.index(g.name) for g in ob.vertex_groups if g.name in names}
    W = np.zeros((len(ob.data.vertices), len(names)))
    for v in ob.data.vertices:
        for e in v.groups:
            if e.group in ids:
                W[v.index, ids[e.group]] = e.weight
    return W


def cuff_ring(body, rig, side):
    """Vertex ids of the open loop that ends the sleeve (the cuff opening) of one side."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    par = {}

    def find(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for e in bm.edges:
        if len(e.link_faces) == 1:
            par[find(e.verts[0].index)] = find(e.verts[1].index)
    comps = {}
    for v in list(par):
        comps.setdefault(find(v), []).append(v)
    bm.free()
    target = np.array(rig.matrix_world @ rig.data.bones[f"hand.{side}"].head_local)
    co = np.array([v.co[:] for v in body.data.vertices])
    best = min((c for c in comps.values() if len(c) >= 30), key=lambda c: np.linalg.norm(co[c].mean(0) - target))
    return np.array(sorted(best))


class Side:
    """One sleeve: its cuff ring, the sleeve surface behind it and the hand points to watch."""

    def __init__(self, body, rig, hand, side, stride, raw=False):
        self.side, self.body, self.rig, self.hand, self.raw = side, body, rig, hand, raw
        self.ring = cuff_ring(body, rig, side)
        arm = [f"{b}.{side}" for b in ("shoulder", "upper_arm", "forearm", "hand")]
        wb = weight_matrix(body, arm).sum(1)
        mats = [m.name if m else "" for m in body.data.materials]
        hood = np.zeros(len(body.data.vertices), bool)
        skin = np.zeros(len(body.data.vertices), bool)
        for p in body.data.polygons:
            if mats[p.material_index] == "Hoodie":
                hood[list(p.vertices)] = True
            elif mats[p.material_index] == "Skin":
                skin[list(p.vertices)] = True
        self.cloth = [tuple(p.vertices) for p in body.data.polygons if mats[p.material_index] in ("Hoodie", "Shirt", "Metal")]
        self.sleeve_v = np.nonzero(hood & (wb >= 0.5))[0]
        fore = weight_matrix(body, [f"forearm.{side}", f"hand.{side}"]).sum(1)
        self.skin_v = np.nonzero(skin & ~hood & (fore >= 0.5))[0]
        hn = [f"thumb.{side}", f"thumb.02.{side}", f"thumb.03.{side}"]
        fn = [f"{f}.0{i}.{side}" for f in ("index", "middle", "ring") for i in (1, 2, 3)]
        Wh = weight_matrix(hand, hn + fn)
        self.is_thumb = Wh[:, :3].sum(1) >= 0.5
        self.is_finger = Wh[:, 3:].sum(1) >= 0.5
        self.hsel = np.arange(0, len(hand.data.vertices), stride)

    def frame(self, P):
        """Cuff plane of this frame: centre, unit axis pointing from the elbow to the hand, mean radius."""
        R = P[self.ring]
        c = R.mean(0)
        a = np.linalg.svd(R - c)[2][2]
        elbow = np.array(self.rig.matrix_world @ self.rig.pose.bones[f"forearm.{self.side}"].head)
        if a @ (c - elbow) < 0:
            a = -a
        return c, a, np.linalg.norm(R - c, axis=1).mean()

    def sdist(self, P, Q, c, a):
        """Signed distance (m) of points Q to the cloth of the sleeve behind the cuff, positive = outside.

        The sign is taken against the outward direction of the sleeve tube at the closest cloth vertex
        (the cloth's own vertex normals are not reliable in folds) and the plain distance."""
        S = P[self.sleeve_v]
        ax = (S - c) @ a
        S = S[(ax < -0.003) & (ax > -0.10)]
        d, i = cKDTree(S).query(Q)
        Sc = S[i]
        rad = (Sc - c) - np.outer((Sc - c) @ a, a)
        rad /= np.maximum(np.linalg.norm(rad, axis=1), 1e-9)[:, None]
        return np.einsum("ij,ij->i", Q - Sc, rad), d

    def snapshot(self, rest):
        """Rest pose: which skin points start behind the cuff plane (they must stay inside the cloth)."""
        P, H = rest
        fr = self.frame(P)
        c, a, r = fr
        ah = (H[self.hsel] - c) @ a
        self.in_hand = self.hsel[ah < -0.003]
        self.in_skin = self.skin_v[(P[self.skin_v] - c) @ a < -0.003]
        self.vis = np.nonzero((H - c) @ a >= -0.003)[0]
        self.r_rest = r

    def pierced(self, P, Q, c, a):
        """Points of Q that really are on the far side of the cloth: the straight way from the point to the
        sleeve axis (at the same depth) crosses the hoodie. A bent wrist swings points beside the cuff
        opening, beyond the straight sleeve tube but in free air (nothing between them and the axis): the
        hand coming out of the cuff, not skin through the cloth."""
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        tree = BVHTree.FromPolygons([tuple(v) for v in P], self.cloth, epsilon=1e-5)
        ax = (Q - c) @ a
        rv = (Q - c) - np.outer(ax, a)
        rad = np.linalg.norm(rv, axis=1)
        out = np.zeros(len(Q), bool)
        for k, q in enumerate(Q):
            d = -rv[k] / max(rad[k], 1e-9)
            out[k] = tree.ray_cast(Vector(q + d * 0.0005), Vector(d), max(rad[k] - 0.001, 0.001))[0] is not None
        return out

    def poke(self, P, Q, c, a):
        """Largest distance (m) a point of Q is outside the cloth with the cloth in between; 0 if none."""
        if not len(Q):
            return 0.0
        s = self.sdist(P, Q, c, a)[0]
        m = s > POKE
        if not m.any():
            return 0.0
        if self.raw:
            return float(s.max())
        ok = self.pierced(P, Q[m], c, a)
        return float(s[m][ok].max()) if ok.any() else 0.0

    def measure(self, P, H):
        fr = self.frame(P)
        c, a, r = fr
        # skin that started behind the cuff and is still behind it must be inside the cloth
        # (a bent hand that has come out through the opening is fine)
        Hi = H[self.in_hand]
        Hi = Hi[(Hi - c) @ a < -0.003]
        Si = P[self.in_skin]
        Si = Si[(Si - c) @ a < -0.003]
        out_h = self.poke(P, Hi, c, a)
        out_s = self.poke(P, Si, c, a)
        # a visible vertex behind the cuff plane but outside the opening must not be inside the cloth
        Hv = H[self.vis]
        ax = (Hv - c) @ a
        rad = np.linalg.norm((Hv - c) - np.outer(ax, a), axis=1)
        deep = np.zeros(len(Hv))
        m = (ax < -CROSS_AX) & (rad > 0.9 * r)
        if m.any():
            s, d = self.sdist(P, Hv[m], c, a)
            deep[m] = np.where((s < 0) & (d < NEAR), -s, 0.0)
        res = {"out_hand": float(max(out_h, 0)), "out_skin": float(max(out_s, 0))}
        for k, mk in (("thumb", self.is_thumb[self.vis]), ("fingers", self.is_finger[self.vis] & ~self.is_thumb[self.vis]),
                      ("palm", ~self.is_finger[self.vis] & ~self.is_thumb[self.vis])):
            res["cross_" + k] = float(deep[mk].max()) if mk.any() else 0.0
        return res


KEYS = ("out_hand", "out_skin", "cross_thumb", "cross_fingers", "cross_palm")


def run_action(rig, body, sides, act, step, verbose):
    rigmap.assign(rig, act)
    worst = {s: {k: (0.0, 0) for k in KEYS} for s in sides}
    for f in range(int(act.frame_start), int(act.frame_end) + 1, step):
        bpy.context.scene.frame_set(f)
        P = evaluated(body)[0]
        for s, sd in sides.items():
            H, _ = evaluated(sd.hand)
            r = sd.measure(P, H)
            if verbose:
                print(f"F{f:03d} {s} " + " ".join(f"{k} {r[k] * 1000:5.1f}" for k in KEYS))
            for k in KEYS:
                if r[k] > worst[s][k][0]:
                    worst[s][k] = (r[k], f)
    return worst


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", required=True, help="A,B,... or all")
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--actions-from", default="", help="another .blend whose actions are appended (read only)")
    ap.add_argument("--prefix", default="Scene_")
    ap.add_argument("--clips-from", default="", help="another .blend whose clips (all actions) replace those of the same name")
    ap.add_argument("--stride", type=int, default=4, help="sample every Nth hand vertex")
    ap.add_argument("--raw", action="store_true", help="count every skin point outside the sleeve wall, covered or not")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    if a.clips_from:
        have = {x.name for x in bpy.data.actions}
        with bpy.data.libraries.load(os.path.abspath(a.clips_from), link=False) as (src, dst):
            dst.actions = list(src.actions)
        for act in dst.actions:
            if act is not None:
                act.use_fake_user = True
                if act.name.endswith(".001") and act.name[:-4] in have:
                    bpy.data.actions.remove(bpy.data.actions[act.name[:-4]])
                    act.name = act.name[:-4]
    if a.actions_from:
        with bpy.data.libraries.load(os.path.abspath(a.actions_from), link=False) as (src, dst):
            dst.actions = [n for n in src.actions if n.startswith(a.prefix)]
        for act in dst.actions:
            if act is not None:
                act.use_fake_user = True
    rig, body = bpy.data.objects["Morfi_Rig"], bpy.data.objects["Morfi_Body"]
    sides = {s: Side(body, rig, bpy.data.objects[f"Hand_{s}"], s, a.stride, a.raw) for s in ("L", "R")}
    rig.animation_data_create()
    rig.animation_data.action = None
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    P = evaluated(body)[0]
    for s, sd in sides.items():
        sd.snapshot((P, evaluated(sd.hand)[0]))
    rig.data.pose_position = "POSE"
    print("REST", {s: (len(sd.in_hand), len(sd.in_skin), len(sd.vis)) for s, sd in sides.items()}, "(hand-in, skin-in, visible)")
    if a.action == "all":
        names = [x.name for x in bpy.data.actions if not x.name.startswith(("Pose_", "POS_")) and x.name != "Scratch_Head"]
    else:
        names = a.action.split(",")
    total = {s: {k: (0.0, "", 0) for k in KEYS} for s in sides}
    res = {}
    hdr = "action".ljust(16) + " | ".join(f"{s}: " + " ".join(k.replace("cross_", "x_").ljust(9) for k in KEYS) for s in sides)
    print(hdr)
    for n in names:
        w = run_action(rig, body, sides, bpy.data.actions[n], a.step, a.verbose)
        res[n] = {s: {k: [round(v * 1000, 2), f] for k, (v, f) in w[s].items()} for s in sides}
        print(n.ljust(16) + " | ".join(f"{s}: " + " ".join(f"{w[s][k][0] * 1000:4.1f}@{w[s][k][1]:<4d}" for k in KEYS) for s in sides))
        for s in sides:
            for k in KEYS:
                if w[s][k][0] > total[s][k][0]:
                    total[s][k] = (w[s][k][0], n, w[s][k][1])
    print("WORST", {s: {k: [round(v * 1000, 1), n, f] for k, (v, n, f) in total[s].items()} for s in sides})
    if a.json:
        json.dump(res, open(a.json, "w"))


if __name__ == "__main__":
    main()
