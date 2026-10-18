// Morfi's real voice in the lab: the phrases of web/public/voice (voice/gen.py writes them: one mp3
// per voice and phrase plus a JSON with the ElevenLabs character alignment and the audio envelope),
// the lip-sync built from them exactly like the Blender renders (scripts/ia3d/anim/performance.py
// Performance.speak) and a player whose clock is the audio element itself, so the mouth never
// drifts from the sound.
import type { Director } from './director';

export interface VoiceInfo { key: string; name: string; note?: string }
export interface PhraseInfo { key: string; text: string; mood?: string; gesture?: string }
export interface VoiceIndex {
  default: string;
  voices: VoiceInfo[];
  phrases: PhraseInfo[];
  clips: Record<string, Record<string, { dur: number }>>;
}
/** one clip's JSON: text, duration, per-character start/end (s) and RMS envelope per 1/30 s */
export interface VoiceClip { text: string; dur: number; chars: string; t0: number[]; t1: number[]; env: number[] }
/** per-frame mouth curves of a line (FACE_PROPS units), sampled by the audio clock */
export interface LipTrack { fps: number; dur: number; open: Float32Array; round: Float32Array; smile: Float32Array }

const FPS = 30;
// mouth shapes per letter: (open 0..1, round 0..1, smile -1..1), as performance.py VOWEL
const VOWEL: Record<string, [number, number, number]> = {
  a: [1.0, 0.0, 0.10], á: [1.0, 0.0, 0.10], e: [0.70, 0.0, 0.20], é: [0.75, 0.0, 0.20],
  i: [0.42, 0.0, 0.32], í: [0.48, 0.0, 0.32], o: [0.78, 0.62, 0.0], ó: [0.82, 0.62, 0.0],
  u: [0.50, 0.88, 0.0], ú: [0.55, 0.88, 0.0], y: [0.40, 0.0, 0.25],
};
const CLOSED = new Set(['m', 'b', 'p']);   // lips meet
const NARROW = new Set(['f', 'v']);        // lip to teeth
const TALK_BASE = -0.30;                   // mouth between syllables while talking
const LEAD = 0.05;                         // the mouth leads the sound a little (s)

// gesture of a phrase -> body clip (Victory is new; Thumbs_Up stands in while it is missing)
const GESTURES: Record<string, string[]> = {
  wave: ['Wave'], present: ['Present'], point: ['Point_Side'], thumbs_up: ['Thumbs_Up'], celebrate: ['Celebrate'],
  idea: ['Idea'], shrug: ['Shrug'], cheeks: ['Surprised'], fist: ['Victory', 'Thumbs_Up'], laugh: ['Laugh'],
};
// short button labels (the full text goes in the tooltip)
const LABELS: Record<string, string> = {
  hola: '¡Hola!', bienvenido: '¡Bienvenido!', cobramos: '¿Cobramos?', listo: '¡Venta cobrada!', gracias: '¡Gracias!',
  corte: 'Corte de caja', pensar: 'Déjame pensar', ups: '¡Ups!', wow: '¡Wow!', animo: '¡Tú puedes!', risa: 'Jajaja',
  acabo: 'Se acabó el café',
};

/** The text without ElevenLabs audio tags ([excited], [laughs]...). */
export const plainText = (t: string): string => t.replace(/\[[^\]]*\]\s*/g, '').trim();

export function phraseLabel(p: PhraseInfo): string {
  if (LABELS[p.key]) return LABELS[p.key];
  const first = plainText(p.text).split(/(?<=[.!?…])\s/)[0];
  return first.length > 22 ? first.slice(0, 20).trimEnd() + '…' : first;
}

/** Damped spring x'' = w^2 (drive - x) - 2 z w x' (scripts/ia3d/anim/curves.py spring, 4 substeps). */
function spring(drive: ArrayLike<number>, freq: number, damping: number, fps: number): Float32Array {
  const w = 2 * Math.PI * freq, dt = 1 / fps / 4;
  const out = new Float32Array(drive.length);
  let x = drive.length ? drive[0] : 0, v = 0;
  for (let i = 0; i < drive.length; i++) {
    for (let s = 0; s < 4; s++) {
      v += (w * w * (drive[i] - x) - 2 * damping * w * v) * dt;
      x += v * dt;
    }
    out[i] = x;
  }
  return out;
}

/** Lip-sync of one line: letters give the shape, the audio envelope gives how much (performance.py speak). */
export function lipTrack(clip: VoiceClip, fps = FPS): LipTrack {
  const n = Math.ceil((clip.dur + 0.5) * fps);
  const f = (s: number) => Math.round(s * fps);
  const open = new Float32Array(n), round = new Float32Array(n), smile = new Float32Array(n);
  const talking = new Uint8Array(n), gain = new Float32Array(n).fill(1);
  const chars = Array.from(clip.chars);
  chars.forEach((ch, i) => {
    const c = ch.toLowerCase();
    const a = clip.t0[i] - LEAD, b = Math.max(clip.t1[i] - LEAD, a + 1 / fps);
    // frames whose time t = k / fps falls in [a, b)
    for (let k = Math.max(0, Math.ceil(a * fps)); k < n && k / fps < b; k++) {
      const v = VOWEL[c];
      if (v) {
        open[k] = Math.max(open[k], v[0]);
        round[k] = Math.max(round[k], v[1]);
        smile[k] = v[2];
      } else if (CLOSED.has(c)) {
        open[k] = Math.min(open[k], -0.35);
      } else if (NARROW.has(c)) {
        open[k] = Math.min(open[k], 0.12);
      }
    }
  });
  if (chars.length) talking.fill(1, Math.max(0, f(clip.t0[0] - LEAD)), Math.min(n, f(clip.t1[chars.length - 1]) + 1));
  const f0 = f(-LEAD);
  clip.env.forEach((e, i) => {
    const k = i + f0;
    if (k >= 0 && k < n) gain[k] = Math.min(1.25, Math.max(0.35, 0.45 + 0.75 * (Number.isFinite(e) ? e : 0)));
  });
  const target = new Float32Array(n);
  for (let k = 0; k < n; k++) target[k] = talking[k] ? TALK_BASE + 1.15 * Math.min(1, Math.max(-0.5, open[k] * gain[k])) : 0;
  const r = spring(round, 8.0, 0.7, fps).map((v) => Math.min(1, Math.max(0, v)));
  return { fps, dur: clip.dur, open: spring(target, 9.0, 0.62, fps), round: r, smile: spring(smile, 6.0, 0.8, fps).map((v) => 0.25 * v) };
}

/**
 * Time of a media element for animation: currentTime itself (the source of truth, so there is no
 * drift), smoothed between its updates by the wall clock (some browsers refresh it coarsely).
 */
export class MediaClock {
  private ct = -1;
  private wall = 0;
  constructor(readonly el: HTMLMediaElement) {}
  now(): number {
    const t = this.el.currentTime, w = performance.now();
    if (t !== this.ct || this.el.paused || this.el.seeking || this.el.readyState < 3) {
      this.ct = t;
      this.wall = w;
      return t;
    }
    return t + Math.min(0.25, (w - this.wall) / 1000) * this.el.playbackRate;
  }
}

const STORE_KEY = 'morfi.voice';
const INTERACTIVE = 'button, input, select, textarea, a, label';

/** Plays the phrases with the chosen voice and drives the director (body, mood, mouth). */
export class VoicePlayer {
  readonly audio = new Audio();
  readonly clock = new MediaClock(this.audio);
  private index: VoiceIndex | null = null;
  private cache = new Map<string, Promise<LipTrack | null>>();
  private tracks = new Map<string, LipTrack>();
  private token = 0;
  private line: { token: number; key: string; voice: string; speech: number; dur: number } | null = null;
  private pending: { key: string; voice: string } | null = null;
  private current = '';
  /** the line being said changed (key, or '' when he stops talking) */
  onLine: (key: string) => void = () => {};
  /** the browser blocked the sound until the visitor touches the page */
  onBlocked: (blocked: boolean) => void = () => {};
  /** a line is about to start (a running scene must stop first) */
  beforeSay: () => void = () => {};

  constructor(private director: Director, private base = './voice/') {
    this.audio.preload = 'auto';
    this.audio.addEventListener('ended', () => this.finish());
    this.audio.addEventListener('error', () => this.failed());
    // a blocked line plays again on the next touch of the page (buttons do their own thing)
    const retry = (e: Event) => { if (!(e.target instanceof Element && e.target.closest(INTERACTIVE))) this.retry(); };
    window.addEventListener('pointerdown', retry, true);
    window.addEventListener('keydown', retry, true);
  }

  /** Say the line that the browser blocked (call it from a touch). */
  retry(): void {
    const p = this.pending;
    if (!p) return;
    this.pending = null;
    this.onBlocked(false);
    this.say(p.key, p.voice);
  }

  /** Use voice/index.json (voices, phrases, durations); picks the remembered voice or the official one. */
  setIndex(idx: VoiceIndex): void {
    this.index = idx;
    let saved: string | null = null;
    try { saved = localStorage.getItem(STORE_KEY); } catch { /* storage blocked: use the default */ }
    const has = (k: string | null) => !!k && idx.voices.some((v) => v.key === k);
    this.current = has(saved) ? saved! : has(idx.default) ? idx.default : idx.voices[0]?.key ?? '';
  }

  get voices(): VoiceInfo[] { return this.index?.voices ?? []; }
  get phrases(): PhraseInfo[] { return this.index?.phrases ?? []; }
  get official(): string { return this.index?.default ?? ''; }
  get voice(): string { return this.current; }
  set voice(key: string) {
    if (!this.voices.some((v) => v.key === key)) return;
    this.current = key;
    try { localStorage.setItem(STORE_KEY, key); } catch { /* not remembered, still used */ }
    this.prefetch();
  }
  /** key of the line being said ('' if none) and how far along it is (0..1) */
  get saying(): string { return this.line?.key ?? ''; }
  get progress(): number { return this.line ? Math.min(1, this.clock.now() / Math.max(0.1, this.line.dur)) : 0; }
  get src(): string { return this.audio.currentSrc || this.audio.src; }

  has(key: string, voice = this.current): boolean { return !!this.index?.clips[voice]?.[key]; }
  duration(key: string, voice = this.current): number { return this.index?.clips[voice]?.[key]?.dur ?? 0; }

  /** Warm the lip-sync tracks of the current voice (small JSONs) so a tap starts at once. */
  prefetch(): void {
    for (const p of this.phrases) if (this.has(p.key)) void this.track(this.current, p.key);
  }

  private track(voice: string, key: string): Promise<LipTrack | null> {
    const id = voice + '/' + key;
    let p = this.cache.get(id);
    if (!p) {
      p = fetch(`${this.base}${voice}/${key}.json`)
        .then((r) => (r.ok ? (r.json() as Promise<VoiceClip>) : null))
        .then((c) => {
          const t = c && Array.isArray(c.t0) ? lipTrack(c) : null;
          if (t) this.tracks.set(id, t);
          return t;
        })
        .catch(() => null);
      this.cache.set(id, p);
    }
    return p;
  }

  /**
   * Say a phrase (or any clip of index.json) with a voice (default: the chosen one). The audio
   * starts inside the caller's gesture (play() is called synchronously, as Safari wants);
   * the lip-sync follows audio.currentTime. A new line interrupts the current one.
   * Returns the line's length in seconds (0 if there is no such clip).
   */
  say(key: string, voice = this.current): number {
    if (!this.has(key, voice)) return 0;
    this.beforeSay();
    const token = ++this.token;
    const dur = this.duration(key, voice);
    this.pending = null;
    this.onBlocked(false);
    this.audio.pause();
    this.audio.src = `${this.base}${voice}/${key}.mp3`;
    this.audio.currentTime = 0;
    this.line = { token, key, voice, speech: 0, dur };
    const phrase = this.phrases.find((p) => p.key === key);
    const start = (track: LipTrack | null) => {
      if (this.line?.token !== token) return;
      if (!track) {                         // no alignment: the text lip-sync still moves the mouth
        // (timed by the audio clock: the mp3's end closes the line, not the text's estimate)
        this.director.speak(plainText(phrase?.text ?? ''), () => this.clock.now());
        this.line.speech = this.director.speechToken;
        return;
      }
      const gesture = (GESTURES[phrase?.gesture ?? ''] ?? []).find((g) => this.director.names.includes(g));
      this.line.speech = this.director.say({ track, clock: () => this.clock.now(), mood: phrase?.mood, gesture });
    };
    const ready = this.tracks.get(voice + '/' + key);
    if (ready) start(ready); else void this.track(voice, key).then(start);
    this.onLine(key);
    this.audio.play().catch((err: unknown) => {
      if (this.line?.token !== token) return;          // interrupted by a newer line: nothing to do
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        // autoplay policy (a postMessage or API call without a touch): wait for the visitor
        this.stopLine();
        this.pending = { key, voice };
        this.onBlocked(true);
      } else if (!(err instanceof DOMException && err.name === 'AbortError')) {
        this.failed();
      }
    });
    return dur;
  }

  /** Forget a line the browser blocked (the visitor went on to something else). */
  dropPending(): void {
    if (!this.pending) return;
    this.pending = null;
    this.onBlocked(false);
  }

  /** Stop talking now (a new animation, a scene...). */
  stop(): void {
    this.pending = null;
    this.onBlocked(false);
    this.stopLine();
  }

  /** Once per frame: if something else took the body or the mouth (an animation, a poke), go quiet. */
  update(): void {
    const l = this.line;
    if (l && l.speech && this.director.speechToken !== l.speech) this.stopLine();
  }

  private stopLine(): void {
    const l = this.line;
    this.line = null;
    this.token++;
    if (!this.audio.paused) this.audio.pause();
    if (l) {
      if (l.speech) this.director.endSpeech(l.speech);
      this.onLine('');
    }
  }

  private finish(): void {
    const l = this.line;
    if (!l) return;
    this.line = null;
    if (l.speech) this.director.endSpeech(l.speech);
    this.onLine('');
  }

  /** the mp3 did not load: say it with the text lip-sync, silently, rather than not at all */
  private failed(): void {
    const l = this.line;
    if (!l || !this.audio.error) return;
    const phrase = this.phrases.find((p) => p.key === l.key);
    if (l.speech) this.director.endSpeech(l.speech);
    this.line = null;
    this.onLine('');
    if (phrase) this.director.speak(plainText(phrase.text));
  }
}
