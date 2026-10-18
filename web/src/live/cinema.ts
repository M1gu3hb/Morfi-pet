// "Cámara de cine": while a scene plays, the camera moves on its own between four framings of
// Morfi (wide, medium, close, face), following the scene's camera cues (scripts/ia3d/
// export_scenes.py turns the video's camera into them) with slow eased moves and a gentle
// push-in while it holds. The moment the visitor orbits, pinches or zooms, it lets go for the
// rest of that scene. At the end it glides back to where the visitor had the camera.
import * as THREE from 'three';
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export type Shot = 'wide' | 'medium' | 'close' | 'face';
export type Cue = [number, Shot];

interface Pose { target: THREE.Vector3; dist: number; az: number; el: number }

const DEG = Math.PI / 180;
const EYES = 0.705;                // eye height of the rig (m): the framings scale with it
const MOVE = 1.6;                  // s of an eased camera move
const BACK = 1.3;                  // s of the glide back to the visitor's camera
const SOLO = 26;                   // deg: when he talks to himself we watch from his side
const TAP = 8;                     // px a finger may move before it counts as orbiting
// framings for a 30 deg vertical lens (y, dist in eye heights; width = what must fit across, m)
const SHOTS: Record<Shot, { y: number; dist: number; width: number; az: number; el: number }> = {
  wide: { y: 0.74, dist: 4.2, width: 1.2, az: 14, el: 6 },
  medium: { y: 0.95, dist: 2.9, width: 0.8, az: -10, el: 4 },
  close: { y: 1.2, dist: 2.5, width: 0.8, az: 8, el: 3 },
  face: { y: 1.0, dist: 1.2, width: 0.38, az: -3, el: 2 },
};
export const SHOT_NAMES = Object.keys(SHOTS) as Shot[];

// visitors who ask for less motion get straight cuts and a still camera
const STILL = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
const ease = (u: number) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const wrap = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));

export interface Frame {
  /** fraction of the canvas width / height not covered by the panels (the view is centred there) */
  fx: number;
  fy: number;
}

export class CinemaCamera {
  /** the switch: when off the camera stays where the visitor leaves it */
  enabled = true;
  private state: 'off' | 'shot' | 'back' = 'off';
  private inScene = false;
  private userTook = false;
  private saved: Pose | null = null;
  private from: Pose | null = null;
  private moveT = 0;
  private cues: Cue[] = [];
  private solo = false;
  private cue = -1;
  private cueT = 0;
  private downs = new Map<number, { x: number; y: number }>();

  constructor(private camera: THREE.PerspectiveCamera, private controls: OrbitControls, private model: THREE.Object3D,
    canvas: HTMLElement, private frame: () => Frame = () => ({ fx: 1, fy: 1 })) {
    // the visitor takes the camera: a drag, a second finger (pinch) or the wheel
    canvas.addEventListener('pointerdown', (e) => {
      this.downs.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (this.downs.size > 1) this.takeOver();
    });
    canvas.addEventListener('pointermove', (e) => {
      const d = this.downs.get(e.pointerId);
      if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) > TAP) this.takeOver();
    });
    const up = (e: PointerEvent) => this.downs.delete(e.pointerId);
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', up);
    canvas.addEventListener('wheel', () => this.takeOver(), { passive: true });
  }

  /** moving on its own right now (a shot or the glide back) */
  get active(): boolean { return this.state !== 'off'; }
  get shot(): Shot | '' { return this.state === 'shot' && this.cue >= 0 ? this.cues[this.cue][1] : ''; }

  /** A scene starts: remember the visitor's camera and follow the cues (or a medium shot). */
  begin(cues: Cue[] | undefined, solo: boolean): void {
    // the visitor's camera (not the one gliding back from a previous scene)
    if (!this.inScene && this.state !== 'back') this.saved = this.pose();
    this.inScene = true;
    this.userTook = false;
    this.solo = solo;
    const ok = (cues ?? []).filter((c) => Array.isArray(c) && Number.isFinite(c[0]) && Object.prototype.hasOwnProperty.call(SHOTS, c[1]));
    this.cues = ok.length ? [...ok].sort((a, b) => a[0] - b[0]) : [[0, 'medium']];
    this.cue = -1;
    if (this.enabled) this.state = 'shot';
  }

  /** The switch changed mid-scene. */
  setEnabled(on: boolean): void {
    this.enabled = on;
    if (on && this.inScene && !this.userTook) { this.state = 'shot'; this.cue = -1; }
    if (!on && this.state === 'shot') this.state = 'off';
  }

  /** The scene is over: glide back to the visitor's camera (unless they took it). */
  end(): void {
    if (!this.inScene) return;
    this.inScene = false;
    if (this.state === 'shot' && this.saved) {
      this.from = this.pose();
      this.moveT = 0;
      this.state = 'back';
    } else {
      this.state = 'off';
    }
  }

  private takeOver(): void {
    if (this.inScene) this.userTook = true;
    this.state = 'off';
  }

  /** Once per frame before controls.update(); t = the scene's time (s). */
  update(dt: number, t: number): void {
    if (this.state === 'off') return;
    if (this.state === 'back') {
      this.moveT += dt;
      const u = STILL ? 1 : Math.min(1, this.moveT / BACK);
      this.apply(this.mix(this.from!, this.saved!, ease(u)));
      if (u >= 1) this.state = 'off';
      return;
    }
    // the cue in force at time t
    let i = 0;
    while (i + 1 < this.cues.length && this.cues[i + 1][0] <= t) i++;
    if (i !== this.cue) {
      this.cue = i;
      this.cueT = 0;
      this.moveT = 0;
      this.from = this.pose();
    }
    this.cueT += dt;
    this.moveT += dt;
    const goal = this.shotPose(this.cues[i][1], i, STILL ? 0 : this.cueT);
    const u = STILL ? 1 : Math.min(1, this.moveT / MOVE);
    this.apply(u < 1 ? this.mix(this.from!, goal, ease(u)) : goal);
  }

  /** where a framing puts the camera (relative to Morfi), drifting slowly while it holds */
  private shotPose(shot: Shot, index: number, held: number): Pose {
    const s = SHOTS[shot];
    const k = EYES;
    const centre = this.model.getWorldPosition(new THREE.Vector3());
    const f = this.frame();
    const tanV = Math.tan((this.camera.fov * DEG) / 2) * Math.max(0.2, f.fy);
    const tanH = Math.tan((this.camera.fov * DEG) / 2) * this.camera.aspect * Math.max(0.2, f.fx);
    // same framed height as with the 30 deg lens, and the width must fit too (phones)
    const dist = Math.max((s.dist * k * Math.tan(15 * DEG)) / tanV, (s.width / 2) / tanH);
    const side = index % 2 ? -1 : 1;                       // consecutive shots from alternating sides
    const drift = Math.min(held, 10);
    const az = (s.az * side + (this.solo ? SOLO : 0) + 0.35 * drift * side) * DEG;
    return {
      target: new THREE.Vector3(centre.x, centre.y + s.y * k, centre.z),
      dist: dist * (1 - 0.035 * THREE.MathUtils.smoothstep(drift, 0, 10)),   // a slow push-in
      az, el: s.el * DEG,
    };
  }

  private pose(): Pose {
    const off = this.camera.position.clone().sub(this.controls.target);
    const dist = Math.max(1e-3, off.length());
    return { target: this.controls.target.clone(), dist, az: Math.atan2(off.x, off.z), el: Math.asin(THREE.MathUtils.clamp(off.y / dist, -1, 1)) };
  }

  private mix(a: Pose, b: Pose, u: number): Pose {
    return {
      target: a.target.clone().lerp(b.target, u),
      dist: Math.exp(THREE.MathUtils.lerp(Math.log(a.dist), Math.log(b.dist), u)),
      az: a.az + wrap(b.az - a.az) * u,
      el: THREE.MathUtils.lerp(a.el, b.el, u),
    };
  }

  private apply(p: Pose): void {
    const c = Math.cos(p.el);
    this.controls.target.copy(p.target);
    this.camera.position.set(p.target.x + p.dist * c * Math.sin(p.az), p.target.y + p.dist * Math.sin(p.el), p.target.z + p.dist * c * Math.cos(p.az));
    this.camera.lookAt(p.target);
  }
}
