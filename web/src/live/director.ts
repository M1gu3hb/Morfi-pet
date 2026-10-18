// Directs Morfi: crossfades between the baked clips, samples the face curves that
// travel beside the GLB (morfi_live_anims.json), and layers the things that make a
// character feel alive on top of any clip: random blinks, eyes and head that follow
// the viewer, speech (the real voice with its lip-sync, or text for the chatbot) and, in
// kiosk mode, small idle behaviours on their own. Full scenes (long performances with
// their own face and voice) take over everything while they play.
import * as THREE from 'three';
import { FACE_PROPS, neutralFace, type FaceState, type MorfiFace } from './face';
import type { LipTrack } from './voice';

export interface ActionInfo {
  frames: number;
  loop: boolean;
  props: Record<string, number[]>;
  /** short Spanish label for the lab's button (scripts/ia3d/anim/catalog.py) */
  label?: string;
  /** panel section: actions | emotions | work | moves */
  group?: string;
}
export interface FaceAnims {
  fps: number;
  actions: Record<string, ActionInfo>;
  /** face-only presets (scripts/ia3d/anim/motor.py EXPRESSIONS), layered on any clip */
  expressions?: Record<string, Partial<Record<string, number>>>;
}
/** a voice line: lip-sync curves sampled at clock() (the audio's own time), a mood, a gesture */
export interface Line { track: LipTrack; clock: () => number; mood?: string; gesture?: string }

const FADE = 0.35;
const EXPR_FADE = 4;                 // 1/s: an expression takes ~0.25 s to settle
// clips that look at something on purpose (a prop, the chin...): the head follows the viewer less
const BUSY = new Set(['Look_Around', 'Shake_No', 'Nod_Yes', 'Jump_Happy', 'Dance', 'Run', 'Tablet', 'Calculator',
  'Think', 'Count_123', 'Point_Side', 'Scared', 'Sad', 'Laugh']);
const HEAD_YAW = THREE.MathUtils.degToRad(14);
const HEAD_PITCH = THREE.MathUtils.degToRad(7);

function sample(arr: ArrayLike<number>, frame: number, loop: boolean): number {
  const n = arr.length;
  if (!n) return 0;
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

interface Speech {
  token: number;
  open: ArrayLike<number>;
  round: ArrayLike<number>;
  smile: ArrayLike<number> | null;
  fps: number;
  dur: number;
  /** the voice's clock (audio.currentTime); null = text speech, timed by the frames */
  clock: (() => number) | null;
  t: number;
}

interface Scene { name: string; action: THREE.AnimationAction; clock: () => number; frames: number }

export class Director {
  readonly mixer: THREE.AnimationMixer;
  private clips = new Map<string, THREE.AnimationClip>();
  private sceneClips = new Map<string, THREE.AnimationClip>();
  private sceneFaces = new Map<string, ActionInfo>();
  private actions = new Set<THREE.AnimationAction>();
  private current: THREE.AnimationAction | null = null;
  private currentName = '';
  private face = neutralFace();
  private blinkT = 2;
  private blinkPhase = -1;
  private speech: Speech | null = null;
  private tokens = 0;
  private idleTimer = 6;
  private head: THREE.Object3D | null;
  private neck: THREE.Object3D | null;
  private headBase = new THREE.Quaternion();
  private neckBase = new THREE.Quaternion();
  private look = new THREE.Vector2();            // smoothed follow target (-1..1)
  private lookTarget = new THREE.Vector2();
  private zero = new THREE.Vector2();
  // scratch objects for aimHead (every frame)
  private _q = new THREE.Quaternion();
  private _wq = new THREE.Quaternion();
  private _bq = new THREE.Quaternion();
  private _euler = new THREE.Euler(0, 0, 0, 'YXZ');
  private loops: Set<string>;
  private expr: { name: string; values: Partial<Record<string, number>> } | null = null;
  private exprW = 0;
  // the mood of the line being said: over the chosen expression, only while he talks
  private mood: Partial<Record<string, number>> | null = null;
  private moodOn = false;
  private moodW = 0;
  private scene: Scene | null = null;
  followViewer = true;
  kiosk = false;
  onAction: (name: string) => void = () => {};

  constructor(private root: THREE.Object3D, clips: THREE.AnimationClip[], private anims: FaceAnims, private faceRig: MorfiFace) {
    this.mixer = new THREE.AnimationMixer(root);
    for (const c of clips) this.clips.set(c.name, c);
    this.loops = new Set(Object.entries(anims.actions).filter(([, a]) => a.loop).map(([k]) => k));
    this.mixer.addEventListener('finished', (e) => {
      const name = (e.action as THREE.AnimationAction).getClip().name;
      if (name !== this.currentName || this.loops.has(name) || this.scene) return;
      // a line's gesture ended before the voice: keep talking with the hands until it does
      if (this.speech?.clock) this.talkBody();
      else this.play('Idle');
    });
    this.head = root.getObjectByName('head') ?? null;
    this.neck = root.getObjectByName('neck') ?? null;
  }

  get names(): string[] { return [...this.clips.keys()]; }
  get playing(): string { return this.currentName; }
  get expressions(): string[] { return Object.keys(this.anims.expressions ?? {}); }
  get expression(): string { return this.expr?.name ?? ''; }
  /** label / group of a clip from the anims JSON (undefined if the export did not say) */
  info(name: string): ActionInfo | undefined { return this.anims.actions[name]; }
  /** token of the speech in progress (0 = silent) */
  get speechToken(): number { return this.speech?.token ?? 0; }
  get speaking(): boolean { return !!this.speech; }
  /** the time (s) the mouth was last sampled at: the voice's own clock while a line plays */
  get speechTime(): number { return this.speech?.t ?? 0; }
  get sceneName(): string { return this.scene?.name ?? ''; }
  /** current scene time (s), from its clock */
  get sceneTime(): number { return this.scene ? this.scene.action.time : 0; }

  /** Layer a facial expression on whatever the body does (null or 'neutral' = the clip's own face). */
  setExpression(name: string | null): void {
    const all = this.anims.expressions ?? {};
    const values = name && Object.prototype.hasOwnProperty.call(all, name) ? all[name] : undefined;
    if (!name || name === 'neutral' || !values) { this.expr = this.expr ? { ...this.expr, name: '' } : null; return; }
    if (this.expr?.name !== name) this.exprW = Math.min(this.exprW, 0.35);
    this.expr = { name, values };
  }

  play(name: string, fade = FADE): void {
    const clip = this.clips.get(name);
    if (clip) this.playClip(clip, name, fade);
  }

  /** a clip started without a crossfade: the pose jumps */
  onJump: () => void = () => {};

  private playClip(clip: THREE.AnimationClip, name: string, fade: number): void {
    if (fade <= 0) this.onJump();
    const next = this.mixer.clipAction(clip);
    this.actions.add(next);
    next.reset();
    next.timeScale = 1;
    next.setLoop(this.loops.has(clip.name) ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
    next.clampWhenFinished = true;
    next.enabled = true;
    next.setEffectiveWeight(1);
    next.play();
    if (this.current && this.current !== next) this.current.crossFadeTo(next, fade, false);
    this.current = next;
    this.currentName = name;
    if (name !== 'Talk') { this.speech = null; this.moodOn = false; }
    if (this.scene && this.scene.name !== name) this.scene = null;
    this.idleTimer = 6 + Math.random() * 8;
    this.onAction(name);
  }

  /** Say a sentence from its text: body from the Talk clip. With a clock (s) the mouth follows it and the
   *  caller ends the line (endSpeech); without, the frames time it. Returns its length (s). */
  speak(text: string, clock: (() => number) | null = null): number {
    const fps = this.anims.fps;
    const track = speechTrack(text, fps);
    if (this.currentName !== 'Talk') this.play('Talk');            // (this also ends a scene)
    // keep the gesturing body going for the whole sentence
    if (this.current) this.current.setLoop(THREE.LoopPingPong, Infinity);
    const dur = track.open.length / fps;
    this.speech = { token: ++this.tokens, open: track.open, round: track.round, smile: null, fps, dur, clock, t: 0 };
    this.moodOn = false;
    return dur;
  }

  /**
   * Say a voice line: the mouth follows the audio's clock with the lip-sync of the real voice,
   * the mood colours the face for the line and the gesture plays (then Talk until the voice ends,
   * then Idle). A new line or speak() replaces it. Returns its token for endSpeech().
   */
  say(line: Line): number {
    if (line.gesture && this.clips.has(line.gesture)) this.play(line.gesture);
    else this.talkBody();
    const t = line.track;
    this.speech = { token: ++this.tokens, open: t.open, round: t.round, smile: t.smile, fps: t.fps, dur: t.dur, clock: line.clock, t: 0 };
    const all = this.anims.expressions ?? {};
    const mood = line.mood && Object.prototype.hasOwnProperty.call(all, line.mood) ? all[line.mood] : undefined;
    if (mood) { this.mood = mood; this.moodOn = true; } else this.moodOn = false;
    return this.speech.token;
  }

  /** The line (of that token) is over: the mouth goes back to the clip, the talking body to Idle. */
  endSpeech(token: number): void {
    if (!token || this.speech?.token !== token) return;
    this.speech = null;
    this.moodOn = false;
    this.blinkT = Math.min(this.blinkT, 0.1);                // a blink in the pause after a line
    if (this.currentName === 'Talk') this.play('Idle', 0.5);
  }

  private talkBody(): void {
    if (this.currentName !== 'Talk') this.play('Talk');
    if (this.current) this.current.setLoop(THREE.LoopPingPong, Infinity);
  }

  /**
   * Clips of the full scenes (animation-only GLB, same bone names: they bind to this rig) and
   * their face curves, by scene name. A scene whose clip is not in the GLB borrows a copy of the
   * body clip of that name (handy for test fixtures); a scene without any clip is skipped.
   */
  addScenes(clips: THREE.AnimationClip[], faces: Record<string, { frames: number; props: Record<string, number[]> }>): string[] {
    const byName = new Map(clips.map((c) => [c.name, c]));
    const added: string[] = [];
    for (const [key, f] of Object.entries(faces)) {
      let clip = byName.get(key);
      if (!clip && this.clips.has(key)) {
        clip = this.clips.get(key)!.clone();
        clip.name = 'scene:' + key;
      }
      if (!clip) continue;
      this.sceneClips.set(key, clip);
      this.sceneFaces.set(clip.name, { frames: f.frames, loop: false, props: f.props });
      added.push(key);
    }
    return added;
  }

  hasScene(name: string): boolean { return this.sceneClips.has(name); }

  /**
   * Play a scene: its clip is placed every frame at clock() (the scene audio's time), its own face
   * curves drive the face; no random blinks, no following the viewer, no kiosk, no expression.
   */
  startScene(name: string, clock: () => number, frames: number): boolean {
    const clip = this.sceneClips.get(name);
    if (!clip) return false;
    this.speech = null;
    this.moodOn = false;
    this.playClip(clip, name, 0.5);
    const action = this.current!;
    action.timeScale = 0;                                    // time comes from the clock only
    this.scene = { name, action, clock, frames };
    return true;
  }

  /** End the scene (if one plays): crossfade back to Idle. */
  stopScene(fade = 0.6): void {
    if (!this.scene) return;
    this.scene = null;
    this.play('Idle', fade);
  }

  /** Where the viewer is, in -1..1 of the head's field (x right, y up). */
  setLookTarget(x: number, y: number): void { this.lookTarget.set(THREE.MathUtils.clamp(x, -1, 1), THREE.MathUtils.clamp(y, -1, 1)); }

  update(dt: number): void {
    const s = this.scene;
    if (s) s.action.time = THREE.MathUtils.clamp(s.clock(), 0, s.action.getClip().duration);
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
      const data = this.anims.actions[name] ?? this.sceneFaces.get(name);
      if (!data) continue;
      const frame = a.time * this.anims.fps;
      for (const k of FACE_PROPS) if (data.props[k]) f[k] += sample(data.props[k], frame, data.loop) * w;
      total += w;
    }
    if (total > 0 && total < 1) for (const k of FACE_PROPS) f[k] /= total;
    return f;
  }

  private updateFace(dt: number): void {
    const f = this.clipFace();
    const k = Math.min(1, dt * EXPR_FADE);
    if (this.scene) {
      // the performance has its own face (blinks, gaze, lip-sync): nothing on top
      this.exprW += (0 - this.exprW) * k;
      this.moodW = 0;
      this.look.lerp(this.zero, Math.min(1, dt * 6));
      this.face = f;
      this.faceRig.apply(f);
      return;
    }
    // a chosen expression replaces the clip's values for the controls it defines
    const on = this.expr && this.expr.name ? 1 : 0;
    this.exprW += (on - this.exprW) * k;
    if (this.expr && this.exprW > 0.002) {
      for (const p of FACE_PROPS) {
        const v = this.expr.values[p];
        if (v !== undefined) f[p] = f[p] + (v - f[p]) * this.exprW;
      }
      if (!on && this.exprW < 0.01) this.expr = null;
    }
    // the line's mood, over it while he talks
    const s = this.speech;
    this.moodW += ((this.moodOn ? 1 : 0) - this.moodW) * k;
    if (this.mood && this.moodW > 0.002) {
      for (const p of FACE_PROPS) {
        const v = this.mood[p];
        if (v !== undefined) f[p] = f[p] + (v - f[p]) * this.moodW;
      }
    } else if (!this.moodOn) {
      this.mood = null;
    }
    // speech overrides the mouth (lip-sync curves at the voice's own time)
    if (s) {
      s.t = s.clock ? s.clock() : s.t + dt;
      const fr = s.t * s.fps;
      f.mouth_open = sample(s.open, fr, false);
      f.mouth_round = sample(s.round, fr, false);
      if (s.smile) f.smile += sample(s.smile, fr, false);
      if (!s.clock && s.t >= s.dur) this.endSpeech(s.token);
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
    this.look.lerp(this.followViewer ? this.lookTarget : this.zero, Math.min(1, dt * 6));
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
    if (!this.followViewer || this.scene) return;
    const busy = BUSY.has(this.currentName) ? 0.25 : 1;
    const yaw = this.look.x * HEAD_YAW * busy, pitch = -this.look.y * HEAD_PITCH * busy;
    this.head.quaternion.multiply(this.boneLocal(this.head, pitch * 0.6, yaw * 0.6));
    this.neck.quaternion.multiply(this.boneLocal(this.neck, pitch * 0.4, yaw * 0.4));
  }

  restore(): void {
    if (!this.head || !this.neck) return;
    this.head.quaternion.copy(this.headBase);
    this.neck.quaternion.copy(this.neckBase);
  }

  /** A model-space rotation (pitch, yaw) expressed in a bone's local frame (returns a shared scratch quaternion). */
  private boneLocal(bone: THREE.Object3D, pitch: number, yaw: number): THREE.Quaternion {
    const q = this._q.setFromEuler(this._euler.set(pitch, yaw, 0, 'YXZ'));
    const wq = this.root.getWorldQuaternion(this._wq).invert().multiply(bone.getWorldQuaternion(this._bq));
    return q.premultiply(this._bq.copy(wq).invert()).multiply(wq);
  }

  private kioskStep(dt: number): void {
    if (!this.kiosk || this.currentName !== 'Idle' || this.scene || this.speech) return;
    this.idleTimer -= dt;
    if (this.idleTimer > 0) return;
    const pool = ['Look_Around', 'Look_Around', 'Wave', 'Nod_Yes', 'Present', 'Jump_Happy', 'Idea', 'Thumbs_Up', 'Calculator',
      'Tablet', 'Celebrate'].filter((n) => this.clips.has(n));
    this.play(pool[Math.floor(Math.random() * pool.length)]);
  }

  get faceState(): FaceState { return this.face; }
}
