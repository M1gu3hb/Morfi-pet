"""Clip: a bag of per-frame channels with semantic helpers for Morfi's body.

Sign conventions are the ones of rigmap.py (world rest axes, Morfi faces -Y, left = +X).
Helpers take either an array (one value per frame) or a list of keys [(frame, value), ...].
"""
from collections import defaultdict

import numpy as np

from . import curves as C

SGN = {"L": 1.0, "R": -1.0}
# rig custom properties that drive the face (defaults when an action does not key them)
FACE_PROPS = {
    "blink_L": 0.0, "blink_R": 0.0,          # 0 open .. 1 closed (wink = one of them)
    "gaze_x": 0.0, "gaze_y": 0.0,            # -1..1, iris inside the eye
    "mouth_open": 0.0,                       # -1 closed .. 0 as painted .. 1 wide open
    "smile": 0.0,                            # -1 frown .. 1 big smile
    "mouth_round": 0.0,                      # 0..1 "o"
    "mouth_side": 0.0,                       # -1..1 sideways mouth (smirk, doubt)
    "teeth": 0.0,                            # 0..1 upper teeth in a wide smile
    "brow_L": 0.0, "brow_R": 0.0,            # -1 down .. 1 up
    "brow_in_L": 0.0, "brow_in_R": 0.0,      # inner end: 1 up (worried, sad) .. -1 down (angry)
    "squint": 0.0,                           # 0..1 lower lid up (happy, suspicious)
    "lid_drop": 0.0,                         # 0..1 upper lid down (tired, bored, angry)
    "lid_angle": 0.0,                        # -1 sad (outer side down) .. 1 angry (nose side down)
    "pupil": 0.0,                            # -1 small (scared) .. 1 big (love, cute)
    "eye_calm": 0.0,                         # 0 closed eyes arch up (happy) .. 1 sag (calm, asleep)
}
FPS = 30


class Clip:
    def __init__(self, n, loop=False, fps=FPS):
        self.n, self.loop, self.fps = n, loop, fps
        self.ch = defaultdict(lambda: np.zeros(n))

    # ------------------------------------------------------------ basics
    def arr(self, v):
        if isinstance(v, (list, tuple)):
            return C.keys(self.n, v, loop=self.loop)
        if np.isscalar(v):
            return np.full(self.n, float(v))
        return np.asarray(v, float)

    def add(self, name, v, scale=1.0):
        self.ch[name] = self.ch[name] + self.arr(v) * scale

    def get(self, name):
        return self.ch[name] if name in self.ch else np.zeros(self.n)

    def frames(self):
        return np.arange(self.n)

    # ------------------------------------------------------------ body helpers
    def arm_raise(self, s, v):          # abduction, + = away from the body / up to the side
        self.add(f"upper_arm.{s}.ry", v, -SGN[s])

    def arm_fwd(self, s, v):            # flexion, + = arm forward (towards -Y)
        self.add(f"upper_arm.{s}.rx", v, -1.0)

    def arm_swing(self, s, v):          # horizontal swing, + = towards the front
        self.add(f"upper_arm.{s}.rz", v, -SGN[s])

    def elbow(self, s, v):              # + = forearm bends forward
        self.add(f"forearm.{s}.rx", v, -1.0)

    def forearm_lift(self, s, v):       # + = forearm turns out / up in the arm's plane
        self.add(f"forearm.{s}.ry", v, -SGN[s])

    def forearm_in(self, s, v):         # + = forearm swings in front of the body
        self.add(f"forearm.{s}.rz", v, -SGN[s])

    def palm(self, s, v):               # hand twist about its own axis, + = palm turns forward
        self.add(f"hand.{s}.tw", v, -SGN[s])

    def wrist(self, s, flex=None, side=None, turn=None):
        if flex is not None:            # + = hand bends forward
            self.add(f"hand.{s}.rx", flex, -1.0)
        if side is not None:            # + = hand bends outward
            self.add(f"hand.{s}.ry", side, -SGN[s])
        if turn is not None:
            self.add(f"hand.{s}.rz", turn, -SGN[s])

    def curl(self, s, v):               # fingers and thumb close a little (+), open (-)
        v = self.arr(v)
        for fname in ("index", "middle", "ring"):
            for seg, k in enumerate((1.0, 1.2, 0.9)):
                self.add(f"{fname}.{seg + 1:02d}.{s}.cx", v * k)
        for bname in (f"thumb.{s}", f"thumb.02.{s}", f"thumb.03.{s}"):
            self.add(f"{bname}.cx", v * 0.5)

    # ------------------------------------------------------------ motor (anim/motor.py)
    def hand(self, s, keys):
        from . import motor
        motor.hand_channels(self, s, keys)

    def expr(self, keys, scale=1.0):
        from . import motor
        motor.expr_channels(self, keys, scale)

    def reach(self, s, keys):
        from . import motor
        motor.reach_channels(self, s, keys)

    def reach_rot(self, s, rx=None, ry=None, rz=None):
        from . import motor
        motor.reach_rot(self, s, rx, ry, rz)

    def stretch(self, s, keys):
        from . import motor
        motor.stretch_channels(self, s, keys)

    def show(self, bone, keys):
        from . import motor
        motor.show_prop(self, bone, keys)

    def place_prop(self, loc=None, rot=None):
        from . import motor
        motor.place_prop(self, loc, rot)

    def shrug(self, s, v):              # + = shoulder up
        self.add(f"shoulder.{s}.ry", v, -SGN[s])

    def foot(self, s, x=None, y=None, z=None, pitch=None, turn=None):
        """IK foot offsets in metres (+y = backwards) and pitch in degrees (+ = toes down)."""
        for axis, v in (("lx", x), ("ly", y), ("lz", z)):
            if v is not None:
                self.add(f"foot_ik.{s}.{axis}", v)
        if pitch is not None:
            self.add(f"foot_ik.{s}.rx", pitch)
        if turn is not None:
            self.add(f"foot_ik.{s}.rz", turn, SGN[s])

    def prop(self, name, v, scale=1.0):
        self.add(f"prop.{name}", v, scale)

    # ------------------------------------------------------------ secondary motion
    def chain_angle(self, bones, axis):
        """Approximate world angle of the last bone of a chain (small-angle sum)."""
        return sum(self.get(f"{b}.{axis}") for b in bones)

    def plant_feet(self, toe=(-0.132, -0.100), heel=(0.030, -0.100), reach=0.05):
        """Roll the foot over its toe or heel instead of its ankle while it touches the floor.

        foot_ik pitches about the ankle; a real foot on the ground pivots on the toe (heel
        rising, + pitch) or on the heel (toes up, - pitch). The ankle is moved so the
        pivot stays put: offsets are the pivot relative to the ankle (y, z), in metres.
        """
        for s in ("L", "R"):
            th = np.radians(self.get(f"foot_ik.{s}.rx"))
            if not np.any(th):
                continue
            z = self.get(f"foot_ik.{s}.lz")
            contact = np.clip(1.0 - z / reach, 0.0, 1.0)
            py = np.where(th > 0, toe[0], heel[0])
            pz = np.where(th > 0, toe[1], heel[1])
            ay, az = -py, -pz                                  # ankle relative to the pivot
            dy = (ay * np.cos(th) - az * np.sin(th)) - ay
            dz = (ay * np.sin(th) + az * np.cos(th)) - az
            self.add(f"foot_ik.{s}.ly", dy * contact)
            self.add(f"foot_ik.{s}.lz", dz * contact)

    def secondary(self):
        """Cubes, hood and head follow-through, derived from the primary motion."""
        self.plant_feet()
        loop = self.loop
        spine_chain = ["hips", "spine", "chest", "neck", "head"]
        head_z = self.get("root.lz") + self.get("hips.lz")
        # cubes: soft appendage on top of the head; tilt against the head's angular and
        # vertical accelerations, settle with a slightly underdamped spring
        for ax, gain in (("rx", 0.010), ("ry", 0.010)):
            ang = self.chain_angle(spine_chain, ax)
            a = C.accel(ang, self.fps, loop)
            self.add(f"pixels.{ax}", C.jiggle(a, freq=3.2, damping=0.18, gain=gain, fps=self.fps, loop=loop))
        vz = C.accel(head_z, self.fps, loop)   # m/s^2: a bounce tips the cubes forward/back
        self.add("pixels.rx", np.clip(C.jiggle(vz, freq=3.2, damping=0.18, gain=-2.5, fps=self.fps, loop=loop),
                                      -10, 10))
        # hood: heavier, lower frequency, reacts to the chest and to bounces
        for ax, gain in (("rx", 0.006), ("ry", 0.006)):
            ang = self.chain_angle(["hips", "spine", "chest"], ax)
            a = C.accel(ang, self.fps, loop)
            self.add(f"hood.{ax}", C.jiggle(a, freq=1.8, damping=0.30, gain=gain, fps=self.fps, loop=loop))
        self.add("hood.rx", np.clip(C.jiggle(vz, freq=1.8, damping=0.30, gain=-4.0, fps=self.fps, loop=loop),
                                    -12, 12))
        # follow-through: arms hang from the shoulders and lag behind the torso, the hands lag
        # behind the forearms, the head behind the chest (FK channels; an arm on IK ignores it)
        for ax, gain in (("rx", 0.004), ("ry", 0.004), ("rz", 0.003)):
            a = C.accel(self.chain_angle(["hips", "spine", "chest"], ax), self.fps, loop)
            lag = np.clip(C.jiggle(a, freq=2.2, damping=0.32, gain=gain, fps=self.fps, loop=loop), -5, 5)
            for s in ("L", "R"):
                self.add(f"upper_arm.{s}.{ax}", lag)
            self.add(f"head.{ax}", np.clip(C.jiggle(a, freq=2.6, damping=0.35, gain=gain * 0.5, fps=self.fps,
                                                    loop=loop), -3, 3))
        for s in ("L", "R"):
            for ax in ("rx", "rz"):
                a = C.accel(self.get(f"forearm.{s}.{ax}") + self.get(f"upper_arm.{s}.{ax}"), self.fps, loop)
                self.add(f"hand.{s}.{ax}", np.clip(C.jiggle(a, freq=3.0, damping=0.30, gain=0.003, fps=self.fps,
                                                           loop=loop), -6, 6))

    def life(self, seed=0, breath=1.0, sway=1.0, blinks=None, arms=True, hands=True):
        """The always-on layer that keeps him alive: breathing, the weight drifting from one foot
        to the other, a torso that is never quite square, a head that is never still, arms and
        fingers that drift, and blinks. Every action starts from this."""
        n, loop = self.n, self.loop
        period = 80.0                       # ~22 breaths a minute: calm
        if loop:                            # a period that divides the loop
            period = n / max(1, round(n / 80))
        self.add("chest.rx", C.sine(n, period, -1.3 * breath))
        self.add("spine.rx", C.sine(n, period, -0.5 * breath, phase=-0.05))
        self.add("neck.rx", C.sine(n, period, 0.8 * breath, phase=0.06))
        for s in ("L", "R"):
            self.shrug(s, C.sine(n, period, 1.2 * breath, phase=0.03))
        # weight shift: the hips drift over the planted feet (the leg IK bends the knees), the
        # chest counters so the head stays over the body
        w = C.noise(n, 150, 1.0, seed + 7, loop)
        self.add("hips.lx", 0.007 * sway * w)
        self.add("hips.ry", 1.6 * sway * w)
        self.add("spine.ry", -0.9 * sway * w)
        self.add("chest.ry", -0.5 * sway * w)
        self.add("hips.rz", C.noise(n, 170, 1.6 * sway, seed + 8, loop))
        self.add("chest.rz", C.noise(n, 120, 1.4 * sway, seed + 9, loop))
        # the head is never still: small looks and tilts, slower in the neck
        self.add("head.rx", C.noise(n, 45, 2.4 * sway, seed, loop))
        self.add("head.rz", C.noise(n, 55, 4.0 * sway, seed + 1, loop))
        self.add("head.ry", C.noise(n, 50, 2.6 * sway, seed + 2, loop))
        self.add("neck.rz", C.noise(n, 90, 1.2 * sway, seed + 3, loop))
        if arms:
            for k, s in enumerate(("L", "R")):
                self.arm_raise(s, -4.0 + C.noise(n, 70, 2.0 * sway, seed + 11 + k, loop))
                self.arm_swing(s, C.noise(n, 90, 2.0 * sway, seed + 13 + k, loop))
                self.elbow(s, 12.0 + C.noise(n, 60, 3.0 * sway, seed + 15 + k, loop))
                self.wrist(s, flex=6.0 + C.noise(n, 50, 3.0 * sway, seed + 17 + k, loop))
                if hands:                   # actions that pose the fingers use the motor instead
                    self.curl(s, 8.0 + C.noise(n, 40, 5.0 * sway, seed + 19 + k, loop))
        if blinks:
            b = C.blink_track(n, blinks)
            self.prop("blink_L", b)
            self.prop("blink_R", b)

    def look_at(self, keys, head=0.55, neck=0.15, max_nod=7.0):
        from . import motor
        motor.look_at(self, keys, head, neck, max_nod)

    def channels(self):
        return dict(self.ch)
