// Sound effects, synthesized with WebAudio (no audio files): UI ticks, a soft
// whoosh when the camera flies to a shot, footsteps synced to the walk / run
// cycles, a cheerful chirp for the wave, a chime for the hero pose, a squeaky
// "boop" when Morfi is poked, and an optional ambient pad.
// Browsers only let audio start after a user gesture: the context is created
// on the first click / key press.

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let musicBus: GainNode | null = null;
let noiseBuf: AudioBuffer | null = null;
let enabled = true;
let musicOn = false;
let musicNodes: AudioNode[] = [];
let musicTimer = 0;

function ensure(): AudioContext | null {
  if (!enabled) return null;
  if (!ctx) {
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.55;
    // gentle glue so overlapping sounds never clip
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14;
    comp.ratio.value = 3;
    master.connect(comp).connect(ctx.destination);
    musicBus = ctx.createGain();
    musicBus.gain.value = 0;
    musicBus.connect(master);
    noiseBuf = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  if (ctx.state === 'suspended') void ctx.resume();
  return ctx;
}

export function unlockAudio() { ensure(); }
export function setSfxEnabled(on: boolean) {
  enabled = on;
  if (!on) setMusic(false);
  if (master && ctx) master.gain.setTargetAtTime(on ? 0.55 : 0, ctx.currentTime, 0.05);
}
export function setVolume(v: number) {
  if (master && ctx) master.gain.setTargetAtTime(enabled ? v : 0, ctx.currentTime, 0.05);
}

function env(g: GainNode, t: number, a: number, peak: number, d: number) {
  g.gain.cancelScheduledValues(t);
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(peak, t + a);
  g.gain.exponentialRampToValueAtTime(0.0001, t + a + d);
}

function tone(freq: number, dur: number, type: OscillatorType = 'sine', peak = 0.2, glideTo?: number, when = 0) {
  const c = ensure();
  if (!c || !master) return;
  const t = c.currentTime + when;
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, t);
  if (glideTo) o.frequency.exponentialRampToValueAtTime(glideTo, t + dur);
  env(g, t, 0.006, peak, dur);
  o.connect(g).connect(master);
  o.start(t);
  o.stop(t + dur + 0.05);
}

function noise(dur: number, f0: number, f1: number, q = 1.2, peak = 0.25, when = 0, type: BiquadFilterType = 'bandpass') {
  const c = ensure();
  if (!c || !master || !noiseBuf) return;
  const t = c.currentTime + when;
  const s = c.createBufferSource();
  s.buffer = noiseBuf;
  const f = c.createBiquadFilter();
  f.type = type;
  f.Q.value = q;
  f.frequency.setValueAtTime(f0, t);
  f.frequency.exponentialRampToValueAtTime(f1, t + dur);
  const g = c.createGain();
  env(g, t, dur * 0.35, peak, dur * 0.65);
  s.connect(f).connect(g).connect(master);
  s.start(t, Math.random() * 0.5);
  s.stop(t + dur + 0.05);
}

export const sfx = {
  click() { tone(1180, 0.05, 'sine', 0.09, 760); },
  toggle(on: boolean) { tone(on ? 700 : 520, 0.07, 'triangle', 0.08, on ? 980 : 380); },
  whoosh() { noise(0.42, 380, 2400, 0.9, 0.16); noise(0.42, 2600, 500, 0.7, 0.06, 0.05); },
  step(heavy = false) {
    // soft felt sole on a studio floor: a short low thump plus a tiny scuff
    tone(heavy ? 95 : 120, 0.09, 'sine', heavy ? 0.32 : 0.22, 60);
    noise(0.06, 1800, 900, 0.8, heavy ? 0.07 : 0.045, 0.004, 'bandpass');
  },
  wave() {
    // "hi!": two quick rising chirps and a sparkle
    tone(660, 0.12, 'triangle', 0.14, 990);
    tone(880, 0.16, 'triangle', 0.14, 1320, 0.13);
    [2093, 2637, 3136].forEach((f, i) => tone(f, 0.18, 'sine', 0.035, undefined, 0.28 + i * 0.05));
  },
  hero() {
    // laptop boot chime: a soft major arpeggio
    [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => tone(f, 0.55, 'sine', 0.09, undefined, i * 0.08));
    tone(261.63, 0.9, 'triangle', 0.05, undefined, 0.02);
  },
  boop() {
    // squeaky plush toy
    tone(520, 0.16, 'square', 0.05, 820);
    tone(1040, 0.12, 'sine', 0.08, 1600, 0.02);
    noise(0.1, 3000, 1200, 2.5, 0.03, 0.0);
  },
  shutter() { noise(0.05, 4000, 2500, 1.5, 0.2); noise(0.08, 2500, 1500, 1.2, 0.15, 0.07); },
};

// ------------------------------------------------------------------ ambient pad
const CHORDS = [[261.63, 329.63, 392.0, 493.88], [220.0, 277.18, 329.63, 440.0], [174.61, 261.63, 349.23, 440.0], [196.0, 293.66, 392.0, 493.88]];
function padChord(i: number) {
  const c = ctx;
  if (!c || !musicBus) return;
  const t = c.currentTime;
  for (const f of CHORDS[i % CHORDS.length]) {
    for (const det of [-4, 4]) {
      const o = c.createOscillator();
      o.type = 'sine';
      o.frequency.value = f / 2;
      o.detune.value = det;
      const g = c.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime(0.022, t + 1.6);
      g.gain.linearRampToValueAtTime(0.0001, t + 6.2);
      o.connect(g).connect(musicBus);
      o.start(t);
      o.stop(t + 6.4);
      musicNodes.push(o);
    }
  }
  // a quiet music-box note on top
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = 'sine';
  o.frequency.value = CHORDS[i % CHORDS.length][(i * 2) % 4] * 2;
  env(g, t + 0.4, 0.01, 0.03, 1.4);
  o.connect(g).connect(musicBus);
  o.start(t + 0.4);
  o.stop(t + 2);
}

export function setMusic(on: boolean) {
  musicOn = on;
  const c = on ? ensure() : ctx;
  if (!c || !musicBus) return;
  musicBus.gain.setTargetAtTime(on ? 1 : 0, c.currentTime, 0.6);
  window.clearInterval(musicTimer);
  if (on) {
    let i = 0;
    padChord(i++);
    musicTimer = window.setInterval(() => { if (musicOn) padChord(i++); }, 4800);
  } else {
    window.setTimeout(() => { if (!musicOn) { musicNodes.forEach((n) => { try { (n as OscillatorNode).stop(); } catch { /* already stopped */ } }); musicNodes = []; } }, 1500);
  }
}
export const isMusicOn = () => musicOn;
