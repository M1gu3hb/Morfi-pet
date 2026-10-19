// "Escenas": full performances with their voice, played like a video. They travel apart from the
// main model (scripts/ia3d/export_scenes.py): models/morfi_live_scenes.json (titles, audio, camera
// cues and the face curves of every frame) and models/morfi_live_scenes.glb (animation only, the
// same bone names as morfi_live.glb, so its clips bind to the rig already on screen). Both are
// loaded the first time someone looks at the section. The body's time is the audio's time, so a
// pause, a seek or a slow network never leaves the mouth behind the voice.
// The "Prueba" performances (one animation-only GLB + JSON each, models/tests/<id>.*) play through the same
// player: addTest() registers an entry, playTest() loads its GLB the first time it is played.
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { Director } from './director';
import type { CinemaCamera, Cue } from './cinema';
import { MediaClock } from './voice';

export interface SceneInfo {
  title: string;
  group: 'scene' | 'video' | 'test';
  frames: number;
  /** only the test entries carry their own rate (the scenes file has one for all) */
  fps?: number;
  /** relative to the site root: voice/scenes/<file>.mp3 */
  audio?: string;
  /** he talks to himself (not to the camera) */
  solo?: boolean;
  props: Record<string, number[]>;
  camera?: Cue[];
}
export interface ScenesFile { fps: number; scenes: Record<string, SceneInfo> }
export interface TestCosts { creation: number | null; review: number | null; publish: number | null; total: number | null }
/** models/tests/<id>.json: a scene entry plus who made it and what it cost (USD; null = not known yet) */
export interface TestEntry extends SceneInfo {
  id: string;
  /** the clip's name in its GLB (Test_<Id>) and the key the player uses */
  action: string;
  model?: string | null;
  costs?: Partial<TestCosts> | null;
  changes?: number | null;
  /** what happened in the run, e.g. a phase cut short by the API credits running out */
  note?: string | null;
}
export interface SceneItem { key: string; title: string; group: 'scene' | 'video'; dur: number }
export interface SceneState { key: string; title: string; t: number; dur: number; paused: boolean; waiting: boolean }

const INTERACTIVE = 'button, input, select, textarea, a, label';
// a silent clip, played inside a tap to unlock the audio element (see unlock)
const SILENCE = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
// titles if the export did not give one
const TITLES: Record<string, string> = { POS_Video: 'Tutorial del punto de venta' };

export class ScenePlayer {
  readonly audio = new Audio();
  private clock = new MediaClock(this.audio);
  private file: ScenesFile | null = null;
  private items: SceneItem[] = [];
  private loading: Promise<boolean> | null = null;
  /** the "Prueba" performances: their entries (by clip name), GLB urls and the loads in flight */
  private extra = new Map<string, SceneInfo>();
  private testGlb = new Map<string, string>();
  private testLoads = new Map<string, Promise<boolean>>();
  private unlocking = 0;
  private now: { key: string; info: SceneInfo; silent: boolean; t: number; paused: boolean; waiting: boolean; blocked: boolean; dur: number } | null = null;
  /** the browser blocked the sound until the visitor touches the page */
  onBlocked: (blocked: boolean) => void = () => {};
  /** a scene started, paused, resumed or ended */
  onChange: () => void = () => {};
  /** a scene is about to start (a running phrase must stop first) */
  beforePlay: () => void = () => {};
  /** a scene started (after beforePlay) */
  onStart: () => void = () => {};
  /** the animation jumps instead of blending: a scene started, was sought, stopped or ended */
  onCut: () => void = () => {};

  constructor(private director: Director, private cinema: CinemaCamera, private loadGLB: (url: string) => Promise<GLTF>,
    private jsonUrl: string, private glbUrl: string, private base = './') {
    this.audio.preload = 'auto';
    this.audio.addEventListener('ended', () => { if (this.now && !this.now.silent) this.finish(); });
    this.audio.addEventListener('error', () => {
      // no audio: the scene goes on silently, timed by the frames
      const n = this.now;
      if (n && !n.silent && this.audio.error) { n.silent = true; n.t = this.audio.currentTime || 0; n.waiting = false; this.onChange(); }
    });
    this.audio.addEventListener('playing', () => { if (this.now) { this.now.waiting = false; this.onChange(); } });
    this.audio.addEventListener('durationchange', () => {
      const n = this.now;
      if (n && Number.isFinite(this.audio.duration) && this.audio.duration > 0) n.dur = this.audio.duration;
    });
    // a blocked scene starts on the next touch (buttons and fields do their own thing)
    const retry = (e: Event) => { if (!(e.target instanceof Element && e.target.closest(INTERACTIVE))) this.retry(); };
    window.addEventListener('pointerdown', retry, true);
    window.addEventListener('keydown', retry, true);
  }

  /** Start the sound that the browser blocked (call it from a touch). */
  retry(): void {
    const n = this.now;
    if (!n || !n.blocked) return;
    n.blocked = false;
    this.onBlocked(false);
    this.resume();
  }

  get loaded(): boolean { return !!this.file; }
  get list(): SceneItem[] { return this.items; }
  get state(): SceneState | null {
    const n = this.now;
    return n ? { key: n.key, title: this.title(n.key), t: this.time(), dur: n.dur, paused: n.paused, waiting: n.waiting } : null;
  }

  /** Load the scenes once (JSON first; the GLB only if there is a JSON). Resolves false if there are none. */
  load(): Promise<boolean> {
    this.loading ??= (async () => {
      let file: ScenesFile;
      try {
        const r = await fetch(this.jsonUrl);
        if (!r.ok || !(r.headers.get('content-type') ?? '').includes('json')) return false;
        file = (await r.json()) as ScenesFile;
        if (!file || typeof file.scenes !== 'object') return false;
      } catch {
        return false;
      }
      const gltf = await this.loadGLB(this.glbUrl).catch(() => null);
      const faces: Record<string, { frames: number; props: Record<string, number[]> }> = {};
      for (const [k, s] of Object.entries(file.scenes)) if (s && s.props && s.frames > 0) faces[k] = { frames: s.frames, props: s.props };
      const ok = new Set(this.director.addScenes(gltf?.animations ?? [], faces));
      const fps = file.fps || 30;
      this.items = Object.entries(file.scenes).filter(([k]) => ok.has(k)).map(([k, s]) => ({
        key: k, title: this.titleOf(k, s), group: s.group === 'video' ? 'video' : 'scene', dur: s.frames / fps,
      }));
      this.file = file;
      return this.items.length > 0;
    })();
    // a failed load is not kept: the next request tries again
    void this.loading.then((ok) => { if (!ok) this.loading = null; });
    return this.loading;
  }

  /** Register a test performance (its JSON, already read); the GLB at `glbUrl` loads on the first play. */
  addTest(entry: TestEntry, glbUrl: string): void {
    this.extra.set(entry.action, entry);
    this.testGlb.set(entry.action, glbUrl);
  }

  /** Load the GLB of a registered test (once); true when its clip is ready to play. */
  loadTest(key: string): Promise<boolean> {
    if (this.director.hasScene(key)) return Promise.resolve(true);
    const info = this.extra.get(key), url = this.testGlb.get(key);
    if (!info || !url) return Promise.resolve(false);
    let p = this.testLoads.get(key);
    if (!p) {
      p = this.loadGLB(url).then((gltf) => this.director.addScenes(gltf.animations, { [key]: { frames: info.frames, props: info.props } }).includes(key))
        .catch(() => false);
      this.testLoads.set(key, p);
      void p.then((ok) => { if (!ok) this.testLoads.delete(key); });      // a failed load is tried again next time
    }
    return p;
  }

  /** Play a test from the start (inside a tap): loads its GLB the first time, then plays like a scene. */
  async playTest(key: string): Promise<boolean> {
    if (!this.director.hasScene(key)) this.unlock();
    if (!(await this.loadTest(key))) return false;
    return this.play(key);
  }

  /** Inside a tap: let this audio element play later (iOS only starts sound a tap has allowed) while the GLB loads. */
  private unlock(): void {
    const a = this.audio, id = ++this.unlocking;
    a.muted = true;
    a.src = SILENCE;
    void a.play().then(() => { if (!this.now && this.unlocking === id) a.pause(); }, () => {}).finally(() => { if (!this.now) a.muted = false; });
  }

  /** Play a scene from the start (inside a tap, so the audio may start). */
  play(key: string): boolean {
    const info = this.infoOf(key);
    if (!info || !this.director.hasScene(key)) return false;
    this.beforePlay();
    this.stop(false);
    this.audio.muted = false;
    const fps = info.fps || this.file?.fps || 30;
    const silent = !info.audio;
    this.now = { key, info, silent, t: 0, paused: false, waiting: !silent, blocked: false, dur: info.frames / fps };
    if (!silent) {
      this.audio.src = this.base + info.audio!.replace(/^\.?\//, '');
      this.audio.currentTime = 0;
      this.audio.play().catch((err: unknown) => {
        const n = this.now;
        if (!n || n.key !== key || n.silent) return;
        if (err instanceof DOMException && err.name === 'NotAllowedError') {
          n.paused = n.blocked = true;           // wait for a touch, at the first frame
          this.onBlocked(true);
          this.onChange();
        }
      });
    }
    this.director.startScene(key, () => this.time(), info.frames);
    this.cinema.begin(info.camera, !!info.solo);
    this.onCut();
    this.onStart();
    this.onChange();
    return true;
  }

  togglePause(): void {
    const n = this.now;
    if (!n) return;
    if (n.paused) this.resume(); else this.pause();
  }

  pause(): void {
    const n = this.now;
    if (!n || n.paused) return;
    n.paused = true;
    if (!n.silent) this.audio.pause();
    this.onChange();
  }

  resume(): void {
    const n = this.now;
    if (!n || !n.paused) return;
    n.paused = n.blocked = false;
    if (!n.silent) {
      this.audio.play().catch((err: unknown) => {
        if (this.now === n && err instanceof DOMException && err.name === 'NotAllowedError') { n.paused = n.blocked = true; this.onBlocked(true); this.onChange(); }
      });
    }
    this.onChange();
  }

  /** Jump to a time (s): the body and the face follow the audio there. */
  seek(t: number): void {
    const n = this.now;
    if (!n) return;
    const x = Math.max(0, Math.min(t, n.dur - 0.05));
    if (n.silent) n.t = x; else this.audio.currentTime = x;
    this.onCut();
  }

  /** Stop the scene now; Morfi goes back to Idle and the camera to the visitor's. */
  stop(back = true): void {
    if (!this.now) return;
    this.now = null;
    this.audio.pause();
    this.onBlocked(false);
    if (back) this.director.stopScene();
    this.cinema.end();
    this.onCut();
    this.onChange();
  }

  /** Once per frame: the silent clock, the end, and letting go if something else took the body. */
  update(dt: number): void {
    const n = this.now;
    if (!n) return;
    if (this.director.sceneName !== n.key) {          // an animation, a phrase... replaced the scene
      this.now = null;
      this.audio.pause();
      this.onBlocked(false);
      this.cinema.end();
      this.onCut();
      this.onChange();
      return;
    }
    if (n.silent && !n.paused) {
      n.t += dt;
      if (n.t >= n.dur) this.finish();
    }
  }

  private finish(): void {
    if (!this.now) return;
    this.now = null;
    this.onBlocked(false);
    this.director.stopScene(0.8);
    this.cinema.end();
    this.onCut();
    this.onChange();
  }

  private time(): number {
    const n = this.now;
    if (!n) return 0;
    return n.silent ? n.t : this.clock.now();
  }

  private infoOf(key: string): SceneInfo | undefined {
    return this.file?.scenes[key] ?? this.extra.get(key);
  }

  private title(key: string): string {
    const s = this.infoOf(key);
    return s ? this.titleOf(key, s) : key;
  }

  private titleOf(key: string, s: SceneInfo): string {
    return (typeof s.title === 'string' && s.title.trim()) || TITLES[key] || 'Escena';
  }
}
