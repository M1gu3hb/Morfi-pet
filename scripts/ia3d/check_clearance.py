"""Per-frame clearance between body parts of the deformed AI mesh (hands vs head, hands vs torso).

blender -b work/ia3d/morfi_ia_anim.blend --python scripts/ia3d/check_clearance.py -- --action Wave [--step 2]

Negative distances mean penetration (a hand vertex is inside the other part's surface is
approximated by the closest-vertex distance being below MARGIN). Prints per frame and a summary.
"""
import argparse
import os
import sys

import bpy
import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anim import rigmap  # noqa: E402


def groups_mask(ob, names, thr):
    idx = {g.index for g in ob.vertex_groups if g.name in names}
    m = np.zeros(len(ob.data.vertices), bool)
    for v in ob.data.vertices:
        if sum(g.weight for g in v.groups if g.group in idx) >= thr:
            m[v.index] = True
    return m


def evaluated_coords(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    no = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", no)
    ev.to_mesh_clear()
    M = np.array(ob.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3], no.reshape(-1, 3) @ M[:3, :3].T


def part_faces(ob, part):
    polys = np.array([p.vertices[:] for p in ob.data.polygons])
    return polys[part[polys].all(1)]


def signed_gap(P, N, part, probe, shallow=0.05):
    """Min signed distance of `probe` points to the `part` surface (negative = inside).

    The sign comes from the normal of the closest part vertex and is only trusted for
    shallow contacts (< `shallow`); in a continuous animation a deep penetration always
    starts as a shallow one, so the per-frame minimum still catches it.
    """
    d, i = cKDTree(P[part]).query(P[probe])
    q, n = P[part][i], N[part][i]
    s = np.einsum("ij,ij->i", P[probe] - q, n)
    return float(np.where((s < 0) & (d < shallow), -d, d).min())


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", required=True)
    ap.add_argument("--step", type=int, default=2)
    args = ap.parse_args(argv)
    rig = bpy.data.objects["Morfi_Rig"]
    ob = bpy.data.objects["Morfi_Body"]
    act = bpy.data.actions[args.action]
    rigmap.assign(rig, act)
    head = groups_mask(ob, {"head"}, 0.95)
    torso = groups_mask(ob, {"hips", "spine", "chest"}, 0.8)
    hand_obs = {s: bpy.data.objects.get(f"Hand_{s}") for s in ("L", "R")}
    hands = {s: groups_mask(ob, {f"hand.{s}", f"fingers.{s}", f"thumb.{s}"}, 0.5) for s in ("L", "R")}
    worst = {}
    for f in range(int(act.frame_start), int(act.frame_end) + 1, args.step):
        bpy.context.scene.frame_set(f)
        P, N = evaluated_coords(ob)
        row = []
        for s, m in hands.items():
            if hand_obs[s] is not None:                   # articulated hands (build_hands.py)
                H, _ = evaluated_coords(hand_obs[s])
                H = H[::3]
                PP = np.concatenate([P, H])
                NN = np.concatenate([N, np.zeros_like(H)])
                sub = np.zeros(len(PP), bool)
                sub[len(P):] = True
                hm = np.concatenate([head, np.zeros(len(H), bool)])
                tm = np.concatenate([torso, np.zeros(len(H), bool)])
                dh = signed_gap(PP, NN, hm, sub)
                dt = signed_gap(PP, NN, tm, sub)
            else:
                sub = m & (np.arange(len(m)) % 3 == 0)      # every 3rd hand vertex is plenty
                dh = signed_gap(P, N, head, sub)
                dt = signed_gap(P, N, torso, sub)
            row.append(f"{s}: head {dh * 100:5.1f} cm torso {dt * 100:5.1f} cm")
            worst[f"{s}_head"] = min(worst.get(f"{s}_head", 9), dh)
            worst[f"{s}_torso"] = min(worst.get(f"{s}_torso", 9), dt)
        print(f"F{f:03d}  " + " | ".join(row))
    print("WORST", {k: round(v * 100, 2) for k, v in worst.items()})


if __name__ == "__main__":
    main()
