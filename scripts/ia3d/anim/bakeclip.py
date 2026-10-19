"""The production bake of a long performance: Clip -> action on Morfi_Rig with every contact pass.

Runs inside Blender. One place for make_scenes.py (the lab's scenes) and bake_perf.py (any
performance module), so both come out of the same passes:

  bake -> reach cap -> hands out of the body -> smooth_ik -> touches (contacts.solve) -> smooth_touches
  -> hands out of the body again -> reach cap -> smooth_ik -> wide smooth_touches (one resting place
  per touch) -> rest_on_skin -> smooth_ik -> arms to FK with a volume-kept stretch (rebake_arms) ->
  the touch is solved again where the FK arm landed off the skin -> [fk_passes: sleeve swivel,
  contact refine, FK body pass, as make_actions.py does for the clips] -> held prop rides in the
  hand (hold_prop, last) -> contacts.verify.

    act = bake_clip(rig, "Test_Opus", clip, meta=..., fast=False, fk_passes=True)
"""
import json
import time

import numpy as np

REST_WIN = 15         # frames: one resting place on the skin for a hand held on his face
REST_TOL = (-0.0005, 0.0010)   # signed gap (m) a resting hand may keep: a hair in, a hair off
RETARGET_MM = 2.0     # a touch that ends more than this off the skin after the FK rebake is solved again


def _objects():
    import bpy
    return bpy.data.objects


def _timed(report, label, fn, *args, **kw):
    """Run one pass and note how long it took (report["pass_seconds"][label]): the long bakes show where the time goes."""
    t = time.time()
    out = fn(*args, **kw)
    spent = time.time() - t
    report.setdefault("pass_seconds", {})[label] = round(report.get("pass_seconds", {}).get(label, 0.0) + spent, 1)
    print(f"PASS {label}: {getattr(fn, '__name__', label)} done in {spent:.0f} s", flush=True)
    return out


def set_reach(contacts, limit):
    """The reach cap for the next solves (contacts.set_max_reach when the motor has it)."""
    if hasattr(contacts, "set_max_reach"):
        contacts.set_max_reach(limit)
    else:
        contacts.MAX_REACH = limit or 1.08


class keep_hands:
    """contacts.hands_keep_size when the motor has it (the hands do not inherit the IK stretch)."""

    def __init__(self, contacts, rig):
        self.cm = contacts.hands_keep_size(rig) if hasattr(contacts, "hands_keep_size") else None

    def __enter__(self):
        return self.cm.__enter__() if self.cm else self

    def __exit__(self, *exc):
        return self.cm.__exit__(*exc) if self.cm else False


def rest_on_skin(contacts, rig, action, clip, reach=0.02, steps=12, target=None):
    """After the wide smoothing the resting place is an average of nearby contacts: on his round
    chin that sits a few mm inside (or off) the skin, and the per-frame re-contact can bounce
    between two fingers. Here each touch frame moves only along the skin's outward normal at the
    chosen spot, bisecting the signed gap to zero (moving out along it never brings the hand in).
    `target` ({(side, frame): gap in m}) asks for a different signed gap on those frames: the one that
    the FK rebake will turn back into zero. Returns (frames moved, worst |gap| after) in m."""
    moved, worst = 0, 0.0
    target = target or {}
    for spec in getattr(clip, "contacts", []):
        if "touch" not in spec:
            continue
        bone = f"hand_ik.{spec['side']}"
        fcs = contacts._loc_curves(action, bone)
        hand = _objects()[f"Hand_{spec['side']}"]
        f0, f1 = spec["frames"]
        for f in range(f0, f1 + 1):
            contacts._frame(f)
            L0 = contacts._get_loc(fcs, f)
            tg = target.get((spec["side"], f), 0.0)
            sd = contacts._touch_error(spec, hand, step=2, slide_gain=0.0)[2] - tg
            if REST_TOL[0] <= sd <= REST_TOL[1]:
                worst = max(worst, abs(sd))
                continue
            _, n = contacts._body_target(spec)
            dloc = np.linalg.solve(contacts._jacobian(rig, bone), n)    # 1 m along the normal

            def gap(t):
                contacts._set_loc(fcs, f, L0 + t * dloc)
                contacts._refresh(fcs)
                contacts._frame(f)
                return contacts._touch_error(spec, hand, step=2, slide_gain=0.0)[2] - tg

            lo, hi = (0.0, reach) if sd < 0 else (-reach, 0.0)
            g_lo, g_hi = (sd, gap(hi)) if sd < 0 else (gap(lo), sd)
            if g_lo > 0 or g_hi < 0:                   # no zero in reach: keep the frame as it was
                gap(0.0)
                worst = max(worst, abs(sd))
                continue
            for _ in range(steps):
                mid = 0.5 * (lo + hi)
                g = gap(mid)
                if g < 0:
                    lo = mid
                else:
                    hi = mid
            g = gap(hi)                                # end just on / off the skin, never in it
            worst = max(worst, abs(g))
            moved += 1
    return moved, worst


def _snapshot(act):
    return {(fc.data_path, fc.array_index): [kp.co[1] for kp in fc.keyframe_points] for fc in act.fcurves}


def _restore(act, snap):
    for (path, idx), vals in snap.items():
        fc = act.fcurves.find(path, index=idx)
        if fc is not None and len(fc.keyframe_points) == len(vals):
            for kp, v in zip(fc.keyframe_points, vals):
                kp.co[1] = v
            fc.update()


def _touch_offsets(contacts, clip, win=5):
    """Signed gap (m) of every touch frame on the arm as it is now (FK), smoothed over `win` frames:
    what the IK -> FK rebake left between the hand and the skin. {(side, frame): gap}."""
    out = {}
    for spec in clip.contacts:
        if "touch" not in spec:
            continue
        hand = _objects()[f"Hand_{spec['side']}"]
        f0, f1 = spec["frames"]
        g = []
        for f in range(f0, f1 + 1):
            contacts._frame(f)
            g.append(contacts._touch_error(spec, hand, step=2, slide_gain=0.0)[2])
        g = np.convolve(np.pad(g, win // 2, mode="edge"), np.ones(win) / win, mode="valid")
        out.update({(spec["side"], f0 + i): float(v) for i, v in enumerate(g)})
    return out


def fk_skip(contacts, clip):
    """Frames whose hand belongs to a contact (and its approach), per arm: the FK body pass leaves
    them (as make_actions.py). A clip with a prop resting on a palm is left alone entirely."""
    if getattr(clip, "supports", None):
        return {"L": [(0, clip.n)], "R": [(0, clip.n)]}
    out = {"L": [], "R": []}
    for spec in list(getattr(clip, "contacts", None) or []):
        a, b = spec["frames"]
        pad = max(int(spec.get("ramp", 0)), contacts.LEAD)
        out[spec["side"]].append((a - pad, b + pad))
    return out


def run_fk_passes(contacts, rig, act, clip, report, log):
    """The passes make_actions.py runs on the FK arms: swivel a sleeve out of the head, close the
    touches again, keep the FK arms out of the head and torso. The held props are not in
    clip.supports at this point (they ride in the hand later), so the contacts decide what is skipped."""
    t = time.time()
    sw = _timed(report, "fk_sleeves", contacts.clear_sleeves_fk, rig, act, clip)
    if sw:
        report["sleeves"] = {s: [v[0], round(v[1] * 1000, 2), round(v[2] * 1000, 2)] for s, v in sw.items()}
        log("SLEEVES " + ", ".join(f"{s} {v[0]} frames, worst gap {v[1] * 1000:.1f} -> {v[2] * 1000:.1f} mm"
                                   for s, v in sw.items()))
    ref = _timed(report, "fk_refine", contacts.refine_contacts_fk, rig, act, clip)
    if ref:
        report["refine"] = {s: [v[0], round(v[1] * 1000, 2), round(v[2] * 1000, 2)] for s, v in ref.items()}
        log("REFINE " + ", ".join(f"{s} {v[0]} frames, worst gap {v[1] * 1000:.1f} -> {v[2] * 1000:.1f} mm"
                                  for s, v in ref.items()))
    fk = _timed(report, "fk_body", contacts.resolve_body_fk, rig, act, clip.n, loop=getattr(clip, "loop", False),
                skip=fk_skip(contacts, clip))
    report["body_fk"] = {s: [v[0], round(v[1] * 1000, 2), round(v[2] * 1000, 2)] for s, v in fk.items()}
    log("BODYFK " + ", ".join(f"{s} {v[0]} frames, worst gap {v[1] * 1000:.1f} -> {v[2] * 1000:.1f} mm"
                              for s, v in fk.items()) + f", {time.time() - t:.0f} s")


def bake_clip(rig, name, clip, meta=None, fast=False, fk_passes=False, log=print):
    """Clip -> action `name` with the contact passes listed in the module doc. `meta`: the JSON
    string property "scene" of the action (title, audio, camera cues... for the export and the web).
    fast = no contact solvers (pose checks). fk_passes = also the FK body / sleeve passes."""
    from . import contacts, rigmap
    t_start = time.time()
    rigmap.ensure_props(rig)
    act = rigmap.bake(rig, name, clip.channels(), clip.n)
    if meta is not None:
        act["scene"] = json.dumps(meta, ensure_ascii=False)
    log(f"BAKED {name}: {clip.n} frames, {len(clip.ch)} channels")
    held = list(clip.supports)
    clip.supports = []                                 # held props ride in the hand (hold_prop)
    touch_frames = [tuple(c["frames"]) for c in clip.contacts]
    report = {"name": name, "frames": clip.n, "max_reach": getattr(clip, "max_reach", None)}
    set_reach(contacts, getattr(clip, "max_reach", None))  # a cartoon stretch the clip may ask for
    try:
        if not fast:
            T = lambda label, fn, *args, **kw: _timed(report, label, fn, *args, **kw)    # noqa: E731
            with keep_hands(contacts, rig):
                report["reach_pulled"] = T("reach", contacts.clamp_reach, rig, act, clip.n)
                report["body_pushed"] = T("body", contacts.resolve_body, rig, act, clip.n, skip=touch_frames)
                T("smooth", contacts.smooth_ik, rig, act, clip)
                if clip.contacts:
                    T("touches", contacts.solve, rig, act, clip)
                    T("touches", contacts.smooth_touches, rig, act, clip)
                report["body_after"] = T("body", contacts.resolve_body, rig, act, clip.n, skip=touch_frames)
                report["reach_after"] = T("reach", contacts.clamp_reach, rig, act, clip.n)
                T("smooth", contacts.smooth_ik, rig, act, clip, sigma=2.0, ramp=8)
                if clip.contacts:
                    # a hand held on his face for seconds while he talks: the per-frame solve can
                    # switch between fingers resting on the skin (the hand hops 2 cm sideways and
                    # back); one wide pass keeps one resting place, then the ramps are blended again
                    T("touches", contacts.smooth_touches, rig, act, clip, win=REST_WIN)
                    report["rest_on_skin"] = T("touches", rest_on_skin, contacts, rig, act, clip)
                    T("smooth", contacts.smooth_ik, rig, act, clip, sigma=2.0, ramp=8)
            if hasattr(contacts, "rebake_arms"):
                snap = _snapshot(act) if any("touch" in c for c in clip.contacts) else None
                st = T("rebake", contacts.rebake_arms, rig, act, clip.n)
                if snap:
                    off = _touch_offsets(contacts, clip)
                    report["rebake_off_mm"] = round(max(abs(v) for v in off.values()) * 1000, 2)
                    target = {}
                    for _ in range(3):
                        if max(abs(v) for v in off.values()) * 1000 <= RETARGET_MM:
                            break
                        # the FK arm lands a few mm off the skin the IK solved: solve once more asking for
                        # the opposite gap on those frames, then rebake again (the gap that is still left
                        # after a pass is added to what we ask for in the next one)
                        target = {k: target.get(k, 0.0) - v for k, v in off.items()}
                        _restore(act, snap)
                        with keep_hands(contacts, rig):
                            report["retarget"] = T("touches", rest_on_skin, contacts, rig, act, clip, target=target)
                        st = T("rebake", contacts.rebake_arms, rig, act, clip.n)
                        off = _touch_offsets(contacts, clip)
                        report.setdefault("retarget_off_mm", []).append(round(max(abs(v) for v in off.values()) * 1000, 2))
                report["rebake"] = {s: {k: round(float(x), 4) for k, x in v.items()} for s, v in st.items()}
                log("REBAKE " + ", ".join(f"{s_} stretch {v['stretch']:.3f} wrist {v['wrist_mm']:.2f} mm "
                                          f"dir {v['dir_deg']:.2f} deg" for s_, v in st.items()))
                if fk_passes:
                    run_fk_passes(contacts, rig, act, clip, report, log)
        # last: a held prop takes the hand's final path (anything that moved the hand after the
        # grip would leave the prop behind)
        for h in held:
            g0, g1 = contacts.hold_prop(rig, act, h["bone"], h["prop"], h["side"], h["frames"], h["ref"])
            report[f"held_{h['prop']}"] = [g0, g1]
            log(f"HELD {h['prop']}: palm gap {g0 * 1000 if g0 is not None else 'n/a'} mm -> "
                f"{g1 * 1000 if g1 is not None else 'n/a'} mm")
        if not fast:
            clip.supports = [{"side": h["side"], "prop": h["prop"], "frames": h["frames"]} for h in held]
            ok, worst, _ = _timed(report, "verify", contacts.verify, rig, act, clip)
            report["contacts_ok"], report["worst"] = bool(ok), {k: float(v) for k, v in worst.items()}
            log(f"CONTACTS {name}: ok={ok} overlap {max(worst['pen'], 0) * 1000:.1f} mm press "
                f"{worst['press'] * 1000:.1f} mm support {worst['support'] * 1000:.1f} mm "
                f"touch {worst['touch'] * 1000:.1f} mm")
    finally:
        set_reach(contacts, None)
    act["contacts"] = json.dumps({"contacts": clip.contacts, "supports": [
        {k: v for k, v in h.items()} for h in held]}, default=float)
    report["seconds"] = round(time.time() - t_start, 1)
    act["bake_report"] = json.dumps(report, default=float)
    log(f"REPORT {json.dumps(report, default=float)}")
    return act
