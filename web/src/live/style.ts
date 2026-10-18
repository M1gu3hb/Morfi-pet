// "Estilo": the look layers that sit on top of the 3D model and work with every clip:
// a thin ink outline (contorno, stronger on the glasses) and motion effects that come from
// the model itself (smear on fast moves, squash and stretch on jumps). It has its own panel,
// apart from "Controles".
//
// Integration contract with main.ts (do not change the call sites without updating both):
//   const style = createStyle({ renderer, scene, camera, model, app, toolbar, lowpower });
//   loop:  director.update(dt) -> updateLook -> director.aimHead() -> style.update(dt)
//          -> style.beforeContact() -> contact.update(...) -> style.afterContact()
//          -> renderer.render(scene, camera) -> director.restore()
//   resize: style.resize(width, height, pixelRatio)
//   seek / clip reset without a crossfade (optional): style.cut()
import * as THREE from 'three';
import './style.css';
import { TRAIL_TAU, dqFrameTick, setDualQuatMask } from '../dqskin';
import { Outline, outlineUniforms, smoothNormals, type OutlineTarget } from './outline';
import { rigidSmear, smearUniforms, updateRigidSmear, useSmear, type RigidSmear } from './fx_smear';
import { SquashStretch } from './fx_squash';
import { createStylePanel } from './style_panel';

export interface StyleOptions {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  /** gltf.scene of morfi_live.glb, already in the scene */
  model: THREE.Object3D;
  /** #app: the panel is appended here */
  app: HTMLElement;
  /** #toolbar: the panel's toggle button goes here, next to "Controles" */
  toolbar: HTMLElement;
  lowpower: boolean;
}

export interface Style {
  /** once per animation frame, after the pose is final (clips + head aim) and before any render */
  update(dt: number): void;
  /** around the contact-shadow pass (outline hulls must not darken the floor shadow) */
  beforeContact(): void;
  afterContact(): void;
  resize(width: number, height: number, pixelRatio: number): void;
  /** a jump in the animation (seek, clip reset without a fade): no motion effects across it */
  cut(): void;
}

export interface StyleSettings {
  outline: boolean;
  /** CSS px */
  width: number;
  /** times the body width */
  glasses: number;
  /** 0 gray .. 1 near-black */
  ink: number;
  /** 0..1 thinner far away */
  thin: number;
  fx: boolean;
  smear: number;
  squash: number;
  sensitivity: number;
}

const DEFAULTS: StyleSettings = {
  outline: true, width: 1.3, glasses: 1.8, ink: 0.9, thin: 0.5,
  fx: true, smear: 0.5, squash: 0.6, sensitivity: 0.5,
};
const STORE = 'morfi.style.v1';
const NUMBERS: (keyof StyleSettings)[] = ['width', 'glasses', 'ink', 'thin', 'smear', 'squash', 'sensitivity'];
const RANGES: Partial<Record<keyof StyleSettings, [number, number]>> = {
  width: [0.5, 4], glasses: [1, 3], ink: [0, 1], thin: [0, 1], smear: [0, 1], squash: [0, 1], sensitivity: [0, 1],
};
// speeds (m per 1/60 s) where the smear starts and is full, at sensitivity 0.5
const SMEAR_FROM = 0.004, SMEAR_FULL = 0.02;
const TELEPORT = 0.25;              // m per 1/60 s: faster than this is a cut, not a motion

/** How much the smear moves each bone's skin: the limbs a lot, the head and body barely. */
function boneMask(bone: THREE.Object3D): number {
  const n = bone.name.toLowerCase();
  if (/arm|hand|finger|thumb|index|middle|ring|prop/.test(n)) return 1;
  if (/shoulder/.test(n)) return 0.6;
  if (/thigh|shin|foot|toe|knee/.test(n)) return 0.7;
  return 0.15;                       // root, hips, spine, chest, neck, head, hood, pixels
}

function clean(v: Partial<StyleSettings>): Partial<StyleSettings> {
  const out: Partial<StyleSettings> = {};
  if (typeof v.outline === 'boolean') out.outline = v.outline;
  if (typeof v.fx === 'boolean') out.fx = v.fx;
  for (const k of NUMBERS) {
    const x = v[k], r = RANGES[k]!;
    if (typeof x === 'number' && Number.isFinite(x)) (out as Record<string, number>)[k] = THREE.MathUtils.clamp(x, r[0], r[1]);
  }
  return out;
}

function loadSettings(): Partial<StyleSettings> {
  try {
    const raw = localStorage.getItem(STORE);
    return raw ? clean(JSON.parse(raw) as Partial<StyleSettings>) : {};
  } catch {
    return {};
  }
}

function saveSettings(s: StyleSettings | null): void {
  try {
    if (s) localStorage.setItem(STORE, JSON.stringify(s));
    else localStorage.removeItem(STORE);
  } catch {
    // private mode or blocked storage: the settings just last this visit
  }
}

function boneOf(o: THREE.Object3D): THREE.Object3D | null {
  for (let p = o.parent; p; p = p.parent) if ((p as THREE.Bone).isBone) return p;
  return null;
}

function inProp(o: THREE.Object3D): boolean {
  for (let p: THREE.Object3D | null = o; p; p = p.parent) if (/^Prop_(Tablet|Calc)/.test(p.name)) return true;
  return false;
}

/** Hooks for the debug module (fx_debug.ts, only with ?dqdebug). */
export interface StyleDebugHooks {
  /** called first in update(): may pose the model; returns true when the frame step is a fixed 1/60 s */
  beforeFrame?: () => boolean;
}

export function createStyle(o: StyleOptions): Style {
  const { model } = o;
  const params = new URLSearchParams(location.search);
  // a slow device starts without the smear; "reduce motion" starts without the motion effects
  let reduced = false;
  try { reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { /* old browser */ }
  const defaults: StyleSettings = { ...DEFAULTS, smear: o.lowpower ? 0 : DEFAULTS.smear, fx: !reduced };
  let s: StyleSettings = { ...defaults, ...loadSettings() };
  if (params.has('outline')) s.outline = params.get('outline') !== '0';
  if (params.has('fx')) s.fx = params.get('fx') !== '0';

  setDualQuatMask(boneMask);

  // ---------------------------------------------------------------- what gets smeared and outlined
  const skinned: THREE.SkinnedMesh[] = [];
  const rigid: RigidSmear[] = [];
  const targets: OutlineTarget[] = [];
  const uses = new Map<THREE.Material, number>();
  model.traverse((obj) => {
    const m = obj as THREE.Mesh;
    if (m.isMesh) for (const mat of [m.material].flat()) uses.set(mat, (uses.get(mat) ?? 0) + 1);
  });
  const meshes: THREE.Mesh[] = [];
  model.traverse((obj) => { if ((obj as THREE.Mesh).isMesh) meshes.push(obj as THREE.Mesh); });
  for (const m of meshes) {
    const mat = m.material as THREE.Material;
    const glasses = mat.name === 'Frame' || /^Glasses_Frame/.test(m.name);
    if ((m as THREE.SkinnedMesh).isSkinnedMesh) {
      skinned.push(m as THREE.SkinnedMesh);
      targets.push({ mesh: m, glasses });
      continue;
    }
    const decal = /^(Eye_Decal|Mouth_Decal)/.test(m.name);
    const lens = /^Lens_/.test(m.name);
    const prop = inProp(m);
    if (!decal && !lens && !prop && !glasses) continue;
    // rigid pieces on a bone: the smear needs their own material (per-object uniforms)
    // (never a decal's: clone() drops its onBeforeCompile, and the face gives each decal its own)
    if (!decal && (uses.get(mat) ?? 0) > 1) m.material = mat.clone();
    const bone = boneOf(m);
    const r = rigidSmear(m, bone ? boneMask(bone) : 0.15);
    useSmear(m.material as THREE.Material, r);
    rigid.push(r);
    // the eye/mouth decals and the clear lenses never get a contour; the props' screens neither
    if (glasses || (prop && !/_(Screen|Display)$/.test(m.name))) targets.push({ mesh: m, glasses, rigid: r });
  }
  // smoothed normals: the primitives of one skinned mesh share its space (and its skeleton)
  const bySkeleton = new Map<THREE.Skeleton, THREE.BufferGeometry[]>();
  for (const m of skinned) bySkeleton.set(m.skeleton, [...(bySkeleton.get(m.skeleton) ?? []), m.geometry]);
  for (const geos of bySkeleton.values()) smoothNormals(geos);
  for (const m of meshes) smoothNormals([m.geometry]);   // every other mesh on its own
  for (const m of skinned) [m.material].flat().forEach((mat) => useSmear(mat));

  // the hulls are built on the first frame (after main.ts counted the model's triangles)
  let outline: Outline | null = null;
  const squash = new SquashStretch(model);
  const _modelInv = new THREE.Matrix4();
  let pixelRatio = o.renderer.getPixelRatio();
  let last = -1;
  let cutPending = true;
  let hooks: StyleDebugHooks = {};

  function apply(): void {
    if (outline) {
      outline.setVisible(s.outline);
      outline.glassesScale.value = s.glasses;
      outline.setInk(s.ink);
    }
    outlineUniforms.olWidth.value = s.width * pixelRatio;
    outlineUniforms.olThin.value = s.thin;
    smearUniforms.fxSmear.value = s.fx ? s.smear : 0;
    const k = Math.pow(2, 1 - 2 * s.sensitivity);    // sensitivity 0..1 -> thresholds x2 .. x0.5
    smearUniforms.fxSmearParams.value.x = SMEAR_FROM * k;
    smearUniforms.fxSmearParams.value.y = SMEAR_FULL * k;
    panel.sync(s);
  }

  function set(key: keyof StyleSettings, value: number | boolean): void {
    const next = clean({ [key]: value } as Partial<StyleSettings>);
    if (!(key in next)) return;
    s = { ...s, ...next };
    saveSettings(s);
    apply();
  }

  const panel = createStylePanel(o.app, o.toolbar, set, () => {
    s = { ...defaults };
    saveSettings(null);
    apply();
  });
  apply();

  const api = {
    outline: (on: boolean) => set('outline', !!on),
    fx: (on: boolean) => set('fx', !!on),
    set: (name: string, value: number | boolean) => set(name as keyof StyleSettings, value),
    get: (): StyleSettings => ({ ...s }),
    open: (on = true) => panel.open(on),
    cut: () => { cutPending = true; },
  };
  (window as unknown as { morfiStyle: typeof api }).morfiStyle = api;
  if (params.has('dqdebug')) {
    const capturePrev = () => {
      model.updateMatrixWorld(true);
      _modelInv.copy(model.matrixWorld).invert();
      for (const r of rigid) updateRigidSmear(r, _modelInv, false, 1);
    };
    import('./fx_debug').then((d) => { hooks = d.installDebug({ model, renderer: o.renderer, camera: o.camera, style: api, capturePrev, squash }); })
      .catch((err: unknown) => console.error(err));
  }

  return {
    update(dt: number): void {
      if (!outline) {
        outline = new Outline(targets);
        apply();
      }
      // the real frame time (main.ts clamps dt): a hidden tab or a stall is a cut
      const now = performance.now();
      let frame = last < 0 ? Infinity : (now - last) / 1000;
      last = now;
      const fixed = hooks.beforeFrame?.() ?? false;
      if (fixed) frame = 1 / 60;
      const jump = cutPending || frame > 0.1;
      cutPending = false;
      const step = Math.min(frame, 0.1);
      model.updateMatrixWorld(true);
      if (jump) squash.reset();
      squash.update(fixed ? 1 / 60 : Math.max(dt, 1e-4), s.fx ? s.squash : 0, s.sensitivity);
      // velocities: the trail pose chases the new pose (same time constant at any frame rate)
      // (a held debug pose has its previous pose in the trail: chase 0 for the rigid pieces, scale 1)
      const chase = fixed ? 0 : 1 - Math.exp(-Math.max(step, 1e-4) / TRAIL_TAU);
      dqFrameTick(jump, TELEPORT * step * 60, step, fixed);
      _modelInv.copy(model.matrixWorld).invert();
      for (const r of rigid) updateRigidSmear(r, _modelInv, jump, chase);
      // at constant speed the trail lags by v * step * (1 - chase) / chase: that gap -> speed per 1/60 s
      smearUniforms.fxFrameScale.value = jump ? 0 : fixed ? 1 : chase / ((1 - chase) * Math.max(step, 1e-4) * 60);
    },
    beforeContact(): void {
      outline?.setVisible(false);
    },
    afterContact(): void {
      outline?.setVisible(s.outline);
    },
    resize(width: number, height: number, pr: number): void {
      pixelRatio = pr;
      outlineUniforms.olRes.value.set(Math.max(1, Math.round(width * pr)), Math.max(1, Math.round(height * pr)));
      outlineUniforms.olWidth.value = s.width * pr;
    },
    cut(): void {
      cutPending = true;
    },
  };
}
