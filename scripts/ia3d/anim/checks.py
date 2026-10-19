"""Checks of a baked performance (inside Blender): the contacts, the hands against his head and torso
on every frame outside the touches, and the hands' jitter. Shared by make_scenes.py verify and
bake_perf.py verify.

    ck = Checker()                          # needs the rig / Morfi_Body / Hand_L / Hand_R of the open .blend
    res = ck.run(action, step=2)            # dict, see below
    issues = issues_of(res, fps=30)         # what to look at, in seconds

`res` has the contacts.verify numbers (contacts_ok, overlap_mm, press_mm, support_mm, touch_mm), one
entry per touch ("touches"), and per hand and body part ("L_head", "R_torso"...) the closest the hand
came to the skin outside the touches (min_mm_free, negative = inside) with the runs of frames that were
more than 2 mm inside, and "jitter_L" / "jitter_R" (zig-zag acceleration of the wrist).
"""
import json
import time
from types import SimpleNamespace

import numpy as np

INSIDE_MM = -2.0          # a hand this far inside head / torso (outside a touch) is a collision
JITTER_ACC_MM = 1.5       # zig-zag counted above this wrist acceleration (mm per frame^2)


class Checker:
    def __init__(self):
        import bpy
        from . import contacts
        self.bpy, self.contacts = bpy, contacts
        self.rig = bpy.data.objects["Morfi_Rig"]
        self.body = bpy.data.objects["Morfi_Body"]
        self.hands = {s: bpy.data.objects[f"Hand_{s}"] for s in ("L", "R")}
        faced = contacts._faced(self.body)
        self.parts = {"head": self._mask({"head"}, 0.95) & faced,
                      "torso": self._mask({"hips", "spine", "chest"}, 0.8) & faced}

    def _mask(self, names, thr):
        ob = self.body
        idx = {g.index for g in ob.vertex_groups if g.name in names}
        m = np.zeros(len(ob.data.vertices), bool)
        for v in ob.data.vertices:
            m[v.index] = sum(g.weight for g in v.groups if g.group in idx) >= thr
        return m

    def coords(self, ob):
        dg = self.bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, np.float32)
        no = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        me.vertices.foreach_get("normal", no)
        ev.to_mesh_clear()
        M = np.array(ob.matrix_world)
        return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3], no.reshape(-1, 3) @ M[:3, :3].T

    def run(self, act, step=2):
        from scipy.spatial import cKDTree
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        from . import rigmap
        contacts, rig, body, hands, parts = self.contacts, self.rig, self.body, self.hands, self.parts
        rigmap.assign(rig, act)
        spec = json.loads(act.get("contacts", "{}") or "{}")
        n = int(act.frame_end) + 1
        clip = SimpleNamespace(n=n, contacts=[dict(c, frames=tuple(c["frames"]), point=tuple(c["point"]))
                                              if "point" in c else dict(c, frames=tuple(c["frames"]))
                                              for c in spec.get("contacts", [])],
                               supports=[dict(s, frames=tuple(s["frames"])) for s in spec.get("supports", [])])
        t0 = time.time()
        ok, worst, rows = contacts.verify(rig, act, clip)
        touching = {s: np.zeros(n, bool) for s in ("L", "R")}
        for c in clip.contacts:
            if "touch" in c:
                f0, f1 = c["frames"]
                r = c.get("ramp", 6)
                touching[c["side"]][max(0, f0 - r):min(n, f1 + r + 1)] = True
        gaps = {f"{s}_{p}": [] for s in ("L", "R") for p in parts}
        tips = {s: [] for s in ("L", "R")}
        polys = contacts._body_parts(body)
        for f in range(0, n, step):
            contacts._frame(f)
            P, N = self.coords(body)
            trees = {k: BVHTree.FromPolygons([tuple(v) for v in P], polys[k]) for k in parts}
            for s, h in hands.items():
                H, _ = self.coords(h)
                H = H[::3]
                tips[s].append(np.array(rig.matrix_world @ rig.pose.bones[f"hand.{s}"].tail))
                for pname, m in parts.items():
                    # nearest vertex for the distance; for the points that come close, the side of the
                    # skin they are on from the nearest FACE (vertex normals lie a few cm away)
                    d, _ = cKDTree(P[m]).query(H)
                    g = float(d.min())
                    for q in H[d < 0.03]:
                        loc, nrm, _, dist = trees[pname].find_nearest(Vector(q), 0.03)
                        if loc is not None and (Vector(q) - loc).dot(nrm) < 0:
                            g = min(g, -dist)
                    gaps[f"{s}_{pname}"].append((f, g, bool(touching[s][f])))
        per = []                                          # each touch on its own: the worst gap and where
        for c in clip.contacts:
            if "touch" not in c:
                continue
            f0, f1 = c["frames"]
            hand = hands[c["side"]]
            gs = []
            for f in range(f0, f1 + 1, 2):
                contacts._frame(f)
                gs.append((abs(contacts._touch_error(c, hand, step=2)[2]), f))
            g, fw = max(gs)
            per.append({"side": c["side"], "touch": c["touch"], "frames": [f0, f1], "worst_mm": round(g * 1000, 1),
                        "at": fw, "mean_mm": round(float(np.mean([x for x, _ in gs])) * 1000, 1)})
        res = {"touches": per}
        res.update({"contacts_ok": bool(ok), "overlap_mm": round(max(worst["pen"], 0) * 1000, 2),
                    "press_mm": round(worst["press"] * 1000, 2), "support_mm": round(worst["support"] * 1000, 2),
                    "touch_mm": round(worst["touch"] * 1000, 2)})
        for k, rows_ in gaps.items():
            free = [g for f, g, t in rows_ if not t]
            inside = [(f, round(g * 1000, 1)) for f, g, t in rows_ if not t and g < INSIDE_MM / 1000]
            runs = []                                     # (first frame, last frame, deepest mm)
            for f, g in inside:
                if runs and f - runs[-1][1] <= step:
                    runs[-1] = [runs[-1][0], f, min(runs[-1][2], g)]
                else:
                    runs.append([f, f, g])
            res[k] = {"min_mm_free": round(min(free) * 1000, 1) if free else None, "inside_frames": len(inside),
                      "runs": runs}
        for s, P in tips.items():
            P = np.array(P)
            acc = np.linalg.norm(P[2:] - 2 * P[1:-1] + P[:-2], axis=1) * 1000
            d = np.diff(P, axis=0)
            flip = np.einsum("ij,ij->i", d[1:], d[:-1]) < 0
            zig = flip & (acc > JITTER_ACC_MM)
            # a wave or a beat reverses the hand every few frames; a buzz reverses it three samples in a row
            buzz = zig[:-2] & zig[1:-1] & zig[2:] if len(zig) > 2 else zig[:0]
            res[f"jitter_{s}"] = {"max_acc_mm_f2": round(float(acc.max()), 1), "zig_frames": int(zig.sum()),
                                  "buzz_frames": int(buzz.sum())}
        res["seconds"] = round(time.time() - t0, 1)
        return res


def issues_of(res, fps=30, touch_tol_mm=4.0, overlap_tol_mm=1.5):
    """What the numbers say to look at, as short sentences with times: a hand inside the head or torso
    (outside a touch), a prop or touch that is not closed, a hand that does not stop shaking."""
    out = []
    sec = lambda f: f / fps          # noqa: E731
    for side in ("L", "R"):
        for part in ("head", "torso"):
            for f0, f1, deep in res.get(f"{side}_{part}", {}).get("runs", []):
                out.append(f"hand {side} inside the {part} at {sec(f0):.2f}-{sec(f1):.2f} s "
                           f"(frames {f0}-{f1}), up to {-deep:.0f} mm deep")
    if res.get("overlap_mm", 0) > overlap_tol_mm:
        out.append(f"hands / body overlap a prop by {res['overlap_mm']} mm")
    for k in ("press_mm", "support_mm"):
        if res.get(k, 0) > 4.0:
            out.append(f"{k[:-3]} gap {res[k]} mm (a fingertip or palm that does not touch)")
    for t in res.get("touches", []):
        if t["worst_mm"] > touch_tol_mm:
            out.append(f"touch of hand {t['side']} on the {t['touch']} is {t['worst_mm']} mm off the skin at frame "
                       f"{t['at']} ({sec(t['at']):.2f} s)")
    for side in ("L", "R"):
        j = res.get(f"jitter_{side}", {})
        if j.get("buzz_frames", 0) > 0:
            out.append(f"hand {side} buzzes: it reverses direction on {j['buzz_frames']} runs of 3+ sampled frames in a row "
                       f"(max acceleration {j['max_acc_mm_f2']} mm/frame^2)")
    return out
