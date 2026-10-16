// Directs Morfi: crossfades between the baked clips, samples the face curves that
// travel beside the GLB (morfi_live_anims.json), and layers the things that make a
// character feel alive on top of any clip: random blinks, eyes and head that follow
// the viewer, speech from text (for the chatbot) and, in kiosk mode, small idle
// behaviours on their own.
import * as THREE from 'three';
import { FACE_PROPS, neutralFace, type FaceState, type MorfiFace } from './face';

export interface FaceAnims {
  fps: number;
  actions: Record<string, { frames: number; loop: boolean; props: Record<string, number[]> }>;
}

export const LOOPS = new Set(['Idle', 'Walk', 'Dance']);
const FADE = 0.35;
const HEAD_YAW = THREE.MathUtils.degToRad(14);
const HEAD_PITCH = THREE.MathUtils.degToRad(7);

function sample(arr: number[], frame: number, loop: boolean): number {
  const n = arr.length;
  if (loop) {
    const f = ((frame % n) + n) % n;
    const i = Math.floor(f), t = f - i;
    return arr[i] * (1 - t) + arr[(i + 1) % n] * t;
  }
  const f = THREE.MathUtils.clamp(frame, 0, n - 1);
  const i = Math.floor(f), t = f - i;
  return arr[i] * (1 - t) + arr[Math.min(i + 1, n - 1)] * t;
}

/** Mouth curve for a sentence: ~5 syllables per second in phrases, like the Talk clip. */
function speechTrack(text: string, fps: number): { open: number[]; round: number[] } {
  const words = text.trim().split(/\s+/).filter(Boolean);
  const open: number[] = [], round: number[] = [];
  const push = (v: number, r: number, frames: number) => { for (let i = 0; i < frames; i++) { open.push(v); round.push(r); } };
  push(-0.3, 0, 3);
  for (const w of words) {
    const syl = Math.max(1, (w.toLowerCase().match(/[aeiouáéíóúü]+/g) ?? []).length);
    for (let s = 0; s < syl; s++) {
      const vowel = (w.toLowerCase().match(/[aeiouáéíóúü]/g) ?? ['a'])[s] ?? 'a';
      const amp = /[aá]/.test(vowel) ? 0.85 : /[eé]/.test(vowel) ? 0.55 : /[ií]/.test(vowel) ? 0.35 : 0.5;
      const r = /[oóuú]/.test(vowel) ? 0.75 : 0;
      const len = Math.round(fps * (0.13 + Math.random() * 0.06));
      push(amp, r, Math.ceil(len * 0.55));
      push(amp * 0.25 - 0.3, r * 0.5, Math.floor(len * 0.45));
    }
    if (/[.,;:!?]$/.test(w)) push(-0.7, 0, Math.round(fps * 0.22));
    else push(-0.2, 0, 2);
  }
  push(-0.3, 0, 4);
  // soften like the Blender spring: a short moving average
  const soft = open.map((_, i) => (open[Math.max(0, i - 1)] + 2 * open[i] + open[Math.min(open.length - 1, i + 1)]) / 4);
  return { open: soft, round };
}

export class Director {
  readonly mixer: THREE.AnimationMixer;
  private clips = new Map<string, THREE.AnimationClip>();
  private actions = new Set<THREE.AnimationAction>();
  private current: THREE.AnimationAction | null = null;
  private currentName = '';
  private face = neutralFace();
  private blinkT = 2;
  private blinkPhase = -1;
  private speech: { open: number[]; round: number[]; t: number } | null = null;
  private idleTimer = 6;
  private head: THREE.Object3D | null;
  private neck: THREE.Object3D | null;
  private headBase = new THREE.Quaternion();
  private neckBase = new THREE.Quaternion();
  private look = new THREE.Vector2();            // smoothed follow target (-1..1)
  private lookTarget = new THREE.Vector2();
  followViewer = true;
  kiosk = false;
  onAction: (name: string) => void = () => {};

  constructor(private root: THREE.Object3D, clips: THREE.AnimationClip[], private anims: FaceAnims, private faceRig: MorfiFace) {
    this.mixer = new THREE.AnimationMixer(root);
    for (const c of clips) this.clips.set(c.name, c);
    this.mixer.addEventListener('finished', (e) => {
      const name = (e.action as THREE.AnimationAction).getClip().name;
      if (name === this.currentName && !LOOPS.has(name)) this.play('Idle');
    });
    this.head = root.getObjectByName('head') ?? null;
    this.neck = root.getObjectByName('neck') ?? null;
  }

  get names(): string[] { return [...this.clips.keys()]; }
  get playing(): string { return this.currentName; }

  play(name: string, fade = FADE): void {
    const clip = this.clips.get(name);
    if (!clip) return;
    const next = this.mixer.clipAction(clip);
    this.actions.add(next);
    next.reset();
    next.setLoop(LOOPS.has(name) ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
    next.clampWhenFinished = true;
    next.enabled = true;
    next.setEffectiveWeight(1);
    next.play();
    if (this.current && this.current !== next) this.current.crossFadeTo(next, fade, false);
    this.current = next;
    this.currentName = name;
    if (name !== 'Talk') this.speech = null;
    this.idleTimer = 6 + Math.random() * 8;
    this.onAction(name);
  }

  /** Say a sentence: body from the Talk clip, mouth from the text. Returns its length (s). */
  speak(text: string): number {
    const fps = this.anims.fps;
    const track = speechTrack(text, fps);
    if (this.currentName !== 'Talk') this.play('Talk');
    this.speech = { ...track, t: 0 };
    const dur = track.open.length / fps;
    // keep the gesturing body going for the whole sentence
    if (this.current) this.current.setLoop(THREE.LoopPingPong, Infinity);
    window.setTimeout(() => { if (this.currentName === 'Talk' && this.speech) { this.speech = null; this.play('Idle', 0.5); } }, dur * 1000);
    return dur;
  }

  /** Where the viewer is, in -1..1 of the head's field (x right, y up). */
  setLookTarget(x: number, y: number): void { this.lookTarget.set(THREE.MathUtils.clamp(x, -1, 1), THREE.MathUtils.clamp(y, -1, 1)); }

  update(dt: number): void {
    this.mixer.update(dt);
    this.updateFace(dt);
    this.kioskStep(dt);
  }

  private clipFace(): FaceState {
    const f = neutralFace();
    let total = 0;
    for (const a of this.actions) {
      const w = a.enabled ? a.getEffectiveWeight() : 0;
      if (w <= 0.001) continue;
      const name = a.getClip().name;
      const data = this.anims.actions[name];
      if (!data) continue;
      const frame = a.time * this.anims.fps;
      for (const k of FACE_PROPS) f[k] += sample(data.props[k], frame, data.loop) * w;
      total += w;
    }
    if (total > 0 && total < 1) for (const k of FACE_PROPS) f[k] /= total;
    return f;
  }

  private updateFace(dt: number): void {
    const f = this.clipFace();
    // speech overrides the clip's mouth
    if (this.speech) {
      const s = this.speech;
      s.t += dt;
      const fr = s.t * this.anims.fps;
      f.mouth_open = sample(s.open, fr, false);
      f.mouth_round = sample(s.round, fr, false);
    }
    // random blinks on top of the clip's own (every 2.5-6 s; sometimes a double blink)
    this.blinkT -= dt;
    if (this.blinkT <= 0 && this.blinkPhase < 0) { this.blinkPhase = 0; this.blinkT = 2.5 + Math.random() * 3.5; }
    if (this.blinkPhase >= 0) {
      this.blinkPhase += dt;
      const p = this.blinkPhase;
      const b = p < 0.07 ? p / 0.07 : p < 0.1 ? 1 : p < 0.25 ? 1 - (p - 0.1) / 0.15 : 0;
      f.blink_L = Math.max(f.blink_L, b);
      f.blink_R = Math.max(f.blink_R, b);
      if (p > 0.25) {
        this.blinkPhase = -1;
        if (Math.random() < 0.15) this.blinkT = 0.12;   // now and then a double blink
      }
    }
    // eyes follow the viewer unless the clip is looking somewhere on purpose
    this.look.lerp(this.followViewer ? this.lookTarget : new THREE.Vector2(), Math.min(1, dt * 6));
    const own = Math.min(1, (Math.abs(f.gaze_x) + Math.abs(f.gaze_y)) * 4);
    f.gaze_x = THREE.MathUtils.clamp(f.gaze_x + this.look.x * 0.75 * (1 - own), -1, 1);
    f.gaze_y = THREE.MathUtils.clamp(f.gaze_y + this.look.y * 0.6 * (1 - own), -1, 1);
    this.face = f;
    this.faceRig.apply(f);
  }

  /** Head and neck turn a little towards the viewer (call before render, then restore()). */
  aimHead(): void {
    if (!this.head || !this.neck) return;
    this.headBase.copy(this.head.quaternion);
    this.neckBase.copy(this.neck.quaternion);
    if (!this.followViewer) return;
    const busy = ['Look_Around', 'Shake_No', 'Nod_Yes', 'Jump_Happy', 'Dance'].includes(this.currentName) ? 0.25 : 1;
    const yaw = this.look.x * HEAD_YAW * busy, pitch = -this.look.y * HEAD_PITCH * busy;
    const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(pitch * 0.6, yaw * 0.6, 0, 'YXZ'));
    const qn = new THREE.Quaternion().setFromEuler(new THREE.Euler(pitch * 0.4, yaw * 0.4, 0, 'YXZ'));
    this.head.quaternion.multiply(this.boneLocal(this.head, q));
    this.neck.quaternion.multiply(this.boneLocal(this.neck, qn));
  }

  restore(): void {
    if (!this.head || !this.neck) return;
    this.head.quaternion.copy(this.headBase);
    this.neck.quaternion.copy(this.neckBase);
  }

  /** A world-space (model-space) rotation expressed in a bone's local frame. */
  private boneLocal(bone: THREE.Object3D, q: THREE.Quaternion): THREE.Quaternion {
    const wq = this.root.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(bone.getWorldQuaternion(new THREE.Quaternion()));
    return wq.clone().invert().multiply(q).multiply(wq);
  }

  private kioskStep(dt: number): void {
    if (!this.kiosk || this.currentName !== 'Idle') return;
    this.idleTimer -= dt;
    if (this.idleTimer > 0) return;
    const r = Math.random();
    this.play(r < 0.35 ? 'Look_Around' : r < 0.6 ? 'Wave' : r < 0.75 ? 'Nod_Yes' : r < 0.9 ? 'Present' : 'Jump_Happy');
  }

  get faceState(): FaceState { return this.face; }
}
