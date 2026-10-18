// Whole-body squash and stretch, procedural, for every clip and scene: Morfi stretches a
// little along his height while he flies up or falls fast, and squashes when he lands
// (or pushes off), through a small under-damped spring so it settles with a bounce. The
// volume is kept (XZ = 1 / sqrt(Y)). The model hangs from a pivot group: at his feet
// while he stands, near his hips while he is in the air.
import * as THREE from 'three';

const MAX_DEFORM = 0.12;       // 0.88 .. 1.12 at amount 1
const FREQ = 3.2;              // Hz, the spring
const DAMPING = 0.32;          // < 1: it overshoots once, like a cartoon
const STRETCH_SPEED = 0.45;    // m/s of vertical speed (hips) for the full stretch (sensitivity 0.5)
const LAND_SPEED = 0.45;       // m/s of fall speed (hips) for the full squash on landing
const AIR_LIFT = [0.012, 0.05]; // feet above their lowest rest height (m): grounded .. airborne

export class SquashStretch {
  readonly pivot = new THREE.Group();
  /** current scale along Y (1 = none) */
  sy = 1;
  private v = 0;
  private hips: THREE.Object3D | null;
  private feet: THREE.Object3D[];
  private footRest = 0;
  private prevY = NaN;
  private air = 0;
  private fall = 0;               // most negative vertical speed of this jump
  private _p = new THREE.Vector3();
  private _inv = new THREE.Matrix4();
  private _m = new THREE.Matrix4();

  constructor(private model: THREE.Object3D) {
    this.pivot.name = 'Morfi_Squash';
    this.pivot.matrixAutoUpdate = false;
    const parent = model.parent;
    if (parent) {
      parent.add(this.pivot);
      this.pivot.add(model);                     // model keeps its own local transform
    }
    this.hips = model.getObjectByName('hips') ?? model.getObjectByName('root') ?? null;
    // three.js drops the dots of node names (PropertyBinding.sanitizeNodeName): foot.L -> footL
    this.feet = ['footL', 'footR', 'toeL', 'toeR', 'foot.L', 'foot.R'].map((n) => model.getObjectByName(n)).filter((o): o is THREE.Object3D => !!o);
    model.updateMatrixWorld(true);
    this.footRest = this.lowestFoot();
  }

  /** feet height in the model's own space */
  private lowestFoot(): number {
    if (!this.feet.length) return 0;
    this._inv.copy(this.model.matrixWorld).invert();
    let y = Infinity;
    for (const f of this.feet) y = Math.min(y, this._p.setFromMatrixPosition(f.matrixWorld).applyMatrix4(this._inv).y);
    return y;
  }

  /** a cut (seek, clip reset): no impact from the jump in position */
  reset(): void {
    this.prevY = NaN;
  }

  /** after the pose is final (model.updateMatrixWorld done); amount 0..1, sensitivity 0..1 */
  update(dt: number, amount: number, sensitivity: number): void {
    if (!this.hips || dt <= 0) return;
    this._inv.copy(this.model.matrixWorld).invert();
    const hip = this._p.setFromMatrixPosition(this.hips.matrixWorld).applyMatrix4(this._inv);
    const hx = hip.x, hy = hip.y, hz = hip.z;
    const lift = this.lowestFoot() - this.footRest;
    const wasAir = this.air;
    this.air = THREE.MathUtils.smoothstep(lift, AIR_LIFT[0], AIR_LIFT[1]);
    let vy = Number.isNaN(this.prevY) ? 0 : (hy - this.prevY) / dt;
    if (Math.abs(vy) > 8) vy = 0;                  // a teleport, not a motion
    this.prevY = hy;
    this.fall = this.air > 0.05 ? Math.min(this.fall, vy) : this.fall * 0.8;
    const sens = 0.4 + 1.2 * sensitivity;         // 0..1 -> 0.4..1.6
    const w = 2 * Math.PI * FREQ;
    // stretch with vertical speed while in the air (or leaving the ground fast)
    const going = Math.max(this.air, THREE.MathUtils.smoothstep(vy, 0.15, 0.35));
    const stretch = Math.min(1, (Math.abs(vy) * sens) / STRETCH_SPEED) * going;
    const target = 1 + stretch * MAX_DEFORM * amount;
    // landing: a kick down proportional to the fall speed, the spring does the bounce
    if (wasAir > 0.5 && this.air <= 0.5) {
      const hit = Math.min(1, (-this.fall * sens) / LAND_SPEED);
      this.v -= hit * MAX_DEFORM * amount * w * 2.0;
      this.fall = 0;
    }
    // the spring, in small steps (stable at any frame rate)
    const steps = Math.max(1, Math.ceil(dt * 240));
    const h = dt / steps;
    for (let i = 0; i < steps; i++) {
      this.v += (-w * w * (this.sy - target) - 2 * DAMPING * w * this.v) * h;
      this.sy += this.v * h;
    }
    const lo = 1 - MAX_DEFORM * amount, hi = 1 + MAX_DEFORM * amount;
    if (this.sy < lo) { this.sy = lo; this.v = Math.max(this.v, 0); }
    if (this.sy > hi) { this.sy = hi; this.v = Math.min(this.v, 0); }
    this.apply(hx, THREE.MathUtils.lerp(0, hy, this.air), hz);
  }

  /** scale about a point given in the model's own space */
  private apply(px: number, py: number, pz: number): void {
    const sy = this.sy, sxz = 1 / Math.sqrt(sy);
    // the point in the pivot's space (the model's local transform first)
    const p = this._p.set(px, py, pz).applyMatrix4(this.model.matrix);
    const m = this._m;
    m.makeScale(sxz, sy, sxz);
    m.setPosition(p.x * (1 - sxz), p.y * (1 - sy), p.z * (1 - sxz));
    this.pivot.matrix.copy(m);
    this.pivot.matrixWorldNeedsUpdate = true;
  }

  dispose(): void {
    this.pivot.matrix.identity();
  }
}
