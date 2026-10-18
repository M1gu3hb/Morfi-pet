// "Morfi en vivo": the animated Morfi built on the AI (Meshy) mesh. Loads
// models/morfi_live.glb (rig with articulated hands, the baked clips, props, face decals),
// the face curves and expressions, and the eye/mouth shader constants, and lets people
// play with him: phrases said with his real voice (lip-sync from the audio), full scenes
// played like a video with a cinema camera, every clip and expression, by touch or mouse.
// Also an embeddable character: window.morfi API and
// postMessage({type: 'play'|'speak'|'say'|'expression'|'scene'|'stop', ...}).
import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { useDualQuatSkinning, attachDualQuatSkinning } from '../dqskin';
import { ContactShadow } from '../contact';
import { MorfiFace, type FaceParams } from './face';
import { Director, type FaceAnims } from './director';
import { createStyle, type Style } from './style';
import { VoicePlayer, phraseLabel, plainText, type VoiceIndex } from './voice';
import { ScenePlayer } from './scenes';
import { CinemaCamera, type Frame } from './cinema';

const params = new URLSearchParams(location.search);
const sameOrigin = (u: string) => { try { return new URL(u, location.href).origin === location.origin; } catch { return false; } };
const BASE = './models/';
// ?model= (local tests) only takes a same-origin URL: a link must not make the page load someone else's file
const asked = params.get('model');
const MODEL_URL = asked && sameOrigin(asked) ? asked : BASE + 'morfi_live.glb';
const LOWPOWER = params.has('lowpower');
// dev server only: ?scenes=<json url>[&scenesglb=<glb url>] loads test scenes instead of the real ones
const DEV = (import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV === true;
const SCENES_URL = (DEV && params.get('scenes')) || BASE + 'morfi_live_scenes.json';
const SCENES_GLB = (DEV && params.get('scenesglb')) || SCENES_URL.replace(/\.json$/, '.glb');
if (params.has('clean') || params.has('kiosk')) document.documentElement.classList.add('clean');

// clips by group (names of scripts/ia3d/anim/actions*.py) and their labels; the anims JSON
// may bring its own label / group per clip (scripts/ia3d/anim/catalog.py), which win
const GROUPS: Record<string, Record<string, string>> = {
  actions: {
    Idle: 'Reposo', Wave: 'Saludar', Talk: 'Hablar', Nod_Yes: 'Sí', Shake_No: 'No', Look_Around: 'Curioso',
    Present: 'Presentar', Jump_Happy: '¡Feliz!', Walk: 'Caminar', Run: 'Correr', Dance: 'Bailar',
  },
  emotions: {
    Laugh: 'Reír', Surprised: 'Sorpresa', Sad: 'Triste', Angry: 'Enojado', Scared: 'Miedo', Calm: 'Tranquilo',
    Celebrate: 'Festejar', Shrug: 'No sé',
  },
  work: {
    Tablet: 'Tablet (tutorial)', Calculator: 'Calculadora', Count_123: 'Contar 1-2-3', Point_Side: 'Señalar',
    Thumbs_Up: 'Pulgar arriba', Idea: '¡Idea!', Think: 'Pensar',
  },
  moves: {},
};
// labels of clips that may arrive without one, and words to build a label from a clip name
const MORE_LABELS: Record<string, string> = { Victory: '¡Vamos!', POS_Video: 'Tutorial del punto de venta' };
const WORDS: Record<string, string> = {
  happy: 'feliz', sad: 'triste', jump: 'salto', look: 'mirar', around: 'alrededor', yes: 'sí', no: 'no', wave: 'saludo',
  walk: 'caminar', run: 'correr', dance: 'baile', spin: 'giro', clap: 'aplauso', bow: 'reverencia', sleep: 'dormir',
  yawn: 'bostezo', stretch: 'estirarse', sit: 'sentarse', point: 'señalar', side: 'lado', up: 'arriba', down: 'abajo',
  big: 'grande', small: 'pequeño', hello: 'hola', bye: 'adiós', victory: 'victoria', cheer: 'porra', hop: 'brinco',
  turn: 'vuelta', left: 'izquierda', right: 'derecha', idle: 'reposo', talk: 'hablar', think: 'pensar', shy: 'tímido',
};
const EXPR_LABELS: Record<string, string> = {
  neutral: 'Neutral', happy: 'Contento', joy: 'Alegre', laugh: 'Risa', sad: 'Triste', angry: 'Enojado', scared: 'Asustado',
  surprised: 'Sorprendido', calm: 'Tranquilo', thinking: 'Pensando', skeptical: 'Escéptico', smug: 'Pícaro', love: 'Enamorado',
  wink: 'Guiño', determined: 'Decidido', confused: 'Confundido', shy: 'Tímido', sleepy: 'Con sueño',
};
const MOBILE = window.matchMedia('(max-width: 720px)');
const pixelRatio = () => (LOWPOWER ? 1 : Math.min(window.devicePixelRatio, 2));
const TAP_MS = 250, TAP_PX = 8;                     // a poke is a short tap; anything longer orbits

// ------------------------------------------------------------------ renderer, scene, studio
const canvas = document.getElementById('view') as HTMLCanvasElement;
const app = document.getElementById('app')!;
const statusEl = document.getElementById('status')!;
const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(pixelRatio());
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.setClearColor(0x000000, 0);

const scene = new THREE.Scene();
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.7;

const camera = new THREE.PerspectiveCamera(30, 1, 0.05, 60);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.target.set(0, 0.6, 0);
controls.minDistance = 0.8;                           // the cinema camera's face shot comes this close
controls.maxDistance = 7;
controls.maxPolarAngle = THREE.MathUtils.degToRad(96);
camera.position.set(0.9, 0.85, 3.1);

scene.add(new THREE.HemisphereLight(0xf4f7ff, 0xc9cfda, 0.55));
const key = new THREE.DirectionalLight(0xfff6ec, 2.4);
key.position.set(-2.0, 3.0, 2.6);
key.castShadow = true;
key.shadow.mapSize.set(LOWPOWER ? 1024 : 2048, LOWPOWER ? 1024 : 2048);
Object.assign(key.shadow.camera, { left: -1, right: 1, top: 1.6, bottom: -0.3 });
key.shadow.radius = 5;
key.shadow.bias = -0.0003;
key.shadow.normalBias = 0.01;
scene.add(key);
const fill = new THREE.DirectionalLight(0xeaf1ff, 0.9);
fill.position.set(2.6, 1.4, 2.0);
scene.add(fill);
const rim = new THREE.DirectionalLight(0xf2f6ff, 1.6);
rim.position.set(1.0, 2.4, -2.6);
scene.add(rim);
const contact = new ContactShadow(1.8, LOWPOWER ? 256 : 512, 0.3, 0.5, 2.4);
scene.add(contact.plane);
// view offset (px) that centres Morfi in the stage the panels leave free (and a zoom-out factor
// so he still fits above a phone's sheet), with its targets
const view = { x: 0, y: 0, s: 1, tx: 0, ty: 0, ts: 1, dirty: true };

// ------------------------------------------------------------------ loading
let model: THREE.Object3D | null = null;
let director: Director | null = null;
let style: Style | null = null;
let voice: VoicePlayer | null = null;
let scenes: ScenePlayer | null = null;
let cinema: CinemaCamera | null = null;
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
const loadGLB = (url: string) => new Promise<GLTF>((res, rej) => loader.load(url, res, undefined, rej));
const json = <T,>(url: string): Promise<T> => fetch(url).then((r) => {
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json() as Promise<T>;
});
// the voices are not needed to show Morfi: they load beside him and never block him
const voiceIndex = json<VoiceIndex>('./voice/index.json').catch(() => null);

Promise.all([
  new Promise<GLTF>((res, rej) => loader.load(MODEL_URL, res, (ev) => {
    if (ev.lengthComputable) document.getElementById('progress')!.textContent = Math.round((ev.loaded / ev.total) * 100) + '%';
  }, rej)),
  json<FaceParams>(BASE + 'morfi_live_face.json'),
  json<FaceAnims>(BASE + 'morfi_live_anims.json'),
]).then(([gltf, faceParams, anims]) => {
  model = gltf.scene;
  model.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    m.frustumCulled = false;
    if ((m as THREE.SkinnedMesh).isSkinnedMesh) {
      m.castShadow = true;
      m.receiveShadow = true;
      // deform like Blender's "Preserve Volume" (the rig was weighted for it)
      (Array.isArray(m.material) ? m.material : [m.material]).forEach(useDualQuatSkinning);
      const dm = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });
      useDualQuatSkinning(dm);
      m.customDepthMaterial = dm;
    } else if (m.name === 'Glasses_Frame') {          // rigid frame on the head bone
      m.castShadow = true;
      m.receiveShadow = true;
    }
  });
  attachDualQuatSkinning(model);
  const face = new MorfiFace(model, faceParams);
  scene.add(model);
  style = createStyle({ renderer, scene, camera, model, app, toolbar: document.getElementById('toolbar')!, lowpower: LOWPOWER });
  style.resize(window.innerWidth, window.innerHeight, renderer.getPixelRatio());
  director = new Director(model, gltf.animations, anims, face);
  director.onAction = (name) => {
    document.querySelectorAll<HTMLButtonElement>('button[data-anim]').forEach((b) => b.classList.toggle('on', b.dataset.anim === name));
  };
  buildButtons(director);
  buildExpressions(director.expressions);
  director.kiosk = params.has('kiosk');
  ($('kiosk') as HTMLInputElement).checked = director.kiosk;
  const start = params.get('anim');
  director.play(start && director.names.includes(start) ? start : 'Idle', 0);
  const startExpr = params.get('expr');
  if (startExpr) setExpression(startExpr);
  cinema = new CinemaCamera(camera, controls, model, canvas, freeFrame);
  cinema.enabled = ($('cinema') as HTMLInputElement).checked;
  setupVoice(director);
  setupScenes(director, cinema);
  statusEl.classList.add('hidden');
  document.getElementById('stats')!.textContent = stats(model, gltf.animations.length);
  (window as unknown as { __morfiReady: boolean; __morfiScene: THREE.Scene }).__morfiScene = scene;
  (window as unknown as { __morfiCamera: THREE.Camera }).__morfiCamera = camera;   // tests project the face with it
  (window as unknown as { __morfiReady: boolean }).__morfiReady = true;
}).catch((err: unknown) => {
  statusEl.classList.add('error');
  statusEl.textContent = 'No se pudo cargar a Morfi: ' + (err instanceof Error ? err.message : String(err));
  console.error(err);
});

function stats(root: THREE.Object3D, clips: number): string {
  let tris = 0;
  root.traverse((o) => {
    const g = (o as THREE.Mesh).isMesh ? (o as THREE.Mesh).geometry : null;
    if (g) tris += g.index ? g.index.count / 3 : g.attributes.position.count / 3;
  });
  return `${Math.round(tris).toLocaleString('es-MX')} triángulos · ${clips} animaciones`;
}

// ------------------------------------------------------------------ panel buttons
/** a clip taken by the visitor or the host: a phrase the browser blocked must not wait to play later */
function playClip(name: string): void {
  voice?.dropPending();
  director?.play(name);
}

function clipLabel(d: Director, n: string): string {
  const own = d.info(n)?.label;
  if (typeof own === 'string' && own.trim()) return own.trim();
  for (const g of Object.values(GROUPS)) if (g[n]) return g[n];
  if (MORE_LABELS[n]) return MORE_LABELS[n];
  // last resort: the clip's words in Spanish where we know them
  const words = n.replace(/([a-z])([A-Z])/g, '$1 $2').split(/[_\s]+/).filter(Boolean).map((w) => WORDS[w.toLowerCase()] ?? w.toLowerCase());
  const s = words.join(' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function clipGroup(d: Director, n: string): string {
  const own = d.info(n)?.group;
  if (typeof own === 'string' && own in GROUPS) return own;
  return Object.keys(GROUPS).find((g) => n in GROUPS[g]) ?? 'actions';
}

function buildButtons(d: Director): void {
  const names = d.names;
  const order = (g: string, n: string) => { const i = Object.keys(GROUPS[g]).indexOf(n); return i >= 0 ? i : 1000 + names.indexOf(n); };
  for (const group of Object.keys(GROUPS)) {
    const box = document.getElementById(group)!;
    box.innerHTML = '';
    const list = names.filter((n) => clipGroup(d, n) === group).sort((a, b) => order(group, a) - order(group, b));
    for (const n of list) {
      const b = document.createElement('button');
      b.type = 'button';
      b.dataset.anim = n;
      b.textContent = clipLabel(d, n);
      b.addEventListener('click', () => playClip(n));
      box.append(b);
    }
    box.closest('section')!.hidden = list.length === 0;
  }
}

/** Set (or clear with '' / 'neutral') the face expression; `toggle` is for the panel buttons. */
function setExpression(name: string, toggle = false): void {
  if (!director) return;
  const off = !name || name === 'neutral' || (toggle && director.expression === name);
  director.setExpression(off ? null : name);
  document.querySelectorAll<HTMLButtonElement>('#expressions button').forEach((b) =>
    b.classList.toggle('on', off ? b.dataset.expr === 'neutral' : b.dataset.expr === name));
}

function buildExpressions(names: string[]): void {
  const box = document.getElementById('expressions')!;
  box.innerHTML = '';
  for (const n of names) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.expr = n;
    b.textContent = EXPR_LABELS[n] ?? n;
    b.classList.toggle('on', n === 'neutral');
    b.addEventListener('click', () => setExpression(n, true));
    box.append(b);
  }
}

// ------------------------------------------------------------------ "Que diga algo": phrases with his voice
const soundHint = $('sound-hint');
const blocked = { voice: false, scene: false };
function showSoundHint(which: 'voice' | 'scene', on: boolean): void {
  blocked[which] = on;
  soundHint.hidden = !(blocked.voice || blocked.scene);
}
soundHint.addEventListener('click', () => { voice?.retry(); scenes?.retry(); });

function setupVoice(d: Director): void {
  const v = new VoicePlayer(d);
  v.beforeSay = () => scenes?.stop();
  const select = $('voice') as HTMLSelectElement;
  const note = $('voice-note');
  void voiceIndex.then((idx) => {
    if (!idx || !Array.isArray(idx.voices) || !Array.isArray(idx.phrases)) {
      select.closest('label')!.hidden = true;
      note.textContent = 'Las voces no están disponibles ahora.';
      return;
    }
    v.setIndex(idx);
    voice = v;
    select.innerHTML = '';
    for (const vc of v.voices) {
      const o = document.createElement('option');
      o.value = vc.key;
      o.textContent = vc.key === v.official ? `${vc.name} (oficial)` : vc.name;
      select.append(o);
    }
    select.value = v.voice;
    select.disabled = false;
    const showNote = () => {
      const vc = v.voices.find((x) => x.key === v.voice);
      note.textContent = v.voice === v.official ? 'La voz oficial de Morfi.' : (vc?.note ?? '').replace(/\s*\([^)]*Hz\)/g, '');
    };
    showNote();
    select.addEventListener('change', () => { v.voice = select.value; showNote(); });
    const box = $('phrases');
    box.innerHTML = '';
    for (const p of v.phrases) {
      const b = document.createElement('button');
      b.type = 'button';
      b.dataset.say = p.key;
      b.title = plainText(p.text);
      b.textContent = phraseLabel(p);
      b.addEventListener('click', () => v.say(p.key));
      box.append(b);
    }
    v.onLine = (k) => document.querySelectorAll<HTMLButtonElement>('button[data-say]').forEach((b) => {
      b.classList.toggle('on', b.dataset.say === k);
      if (b.dataset.say !== k) b.style.removeProperty('--p');
    });
    v.onBlocked = (on) => showSoundHint('voice', on);
    v.prefetch();
  });
}

// ------------------------------------------------------------------ "Escenas": full performances with audio
const player = $('player');
const seek = $('player-seek') as HTMLInputElement;
let seeking = false;
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

function setupScenes(d: Director, cam: CinemaCamera): void {
  const sp = new ScenePlayer(d, cam, loadGLB, SCENES_URL, SCENES_GLB);
  scenes = sp;
  // phrases and scenes cut each other off at once (no frame of double audio)
  sp.beforePlay = () => voice?.stop();
  sp.onStart = () => { if (MOBILE.matches) setPanel(false, false); };   // watch it: the sheet steps aside
  sp.onCut = () => style?.cut();
  d.onJump = () => style?.cut();
  const hint = $('scenes-hint');
  let asked = false;
  const load = () => {
    if (asked) return;
    asked = true;
    hint.textContent = 'Cargando escenas…';
    void sp.load().then((ok) => {
      hint.textContent = ok ? 'Actuaciones completas con voz, como un video.' : 'Las escenas llegan pronto.';
      $('cinema').closest('label')!.hidden = !ok;
      if (ok) buildScenes(sp);
    });
  };
  // lazily: when the section comes into view in an open panel, or after the first quiet seconds
  const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting) && isOpen()) { io.disconnect(); load(); } });
  io.observe($('sec-scenes'));
  const later = () => window.setTimeout(load, 3000);
  if ('requestIdleCallback' in window) window.requestIdleCallback(later, { timeout: 4000 }); else later();
  sp.onBlocked = (on) => showSoundHint('scene', on);
  sp.onChange = () => {
    const s = sp.state;
    player.hidden = !s;
    app.classList.toggle('in-scene', !!s);
    document.querySelectorAll<HTMLButtonElement>('button[data-scene]').forEach((b) => {
      b.classList.toggle('on', !!s && b.dataset.scene === s.key);
      if (!s || b.dataset.scene !== s.key) b.style.removeProperty('--p');
    });
    if (!s) return;
    $('player-title').textContent = s.title;
    $('player-pause-label').textContent = s.paused ? 'Reanudar' : 'Pausa';
    $('player-pause').setAttribute('aria-label', s.paused ? 'Reanudar' : 'Pausa');
    player.classList.toggle('paused', s.paused);
  };
  $('player-pause').addEventListener('click', () => sp.togglePause());
  $('player-stop').addEventListener('click', () => sp.stop());
  seek.addEventListener('input', () => {
    const s = sp.state;
    seeking = true;
    if (s) sp.seek((Number(seek.value) / 1000) * s.dur);
  });
  seek.addEventListener('change', () => { seeking = false; });
  ($('cinema') as HTMLInputElement).addEventListener('change', (e) => cam.setEnabled((e.target as HTMLInputElement).checked));
}

function buildScenes(sp: ScenePlayer): void {
  for (const [group, id] of [['scene', 'scenes'], ['video', 'videos']] as const) {
    const box = $(id);
    box.innerHTML = '';
    const items = sp.list.filter((s) => s.group === group);
    for (const s of items) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = group === 'video' ? 'scene video' : 'scene';
      b.dataset.scene = s.key;
      const t = document.createElement('span');
      t.className = 'stitle';
      t.textContent = s.title;
      const m = document.createElement('span');
      m.className = 'sdur';
      m.textContent = group === 'video' ? `Con su voz · ${mmss(s.dur)}` : mmss(s.dur);
      b.append(t, m);
      if (group === 'video') {
        const icon = document.createElement('span');
        icon.className = 'play';
        icon.setAttribute('aria-hidden', 'true');
        icon.innerHTML = '<svg viewBox="0 0 24 24"><path d="M7 4.8v14.4L19 12z" /></svg>';
        b.prepend(icon);
      }
      b.addEventListener('click', () => {
        if (sp.state?.key === s.key) { sp.togglePause(); return; }
        sp.play(s.key);
      });
      box.append(b);
    }
    if (group === 'video') $('h-videos').hidden = items.length === 0;
  }
}

// ------------------------------------------------------------------ the viewer: where Morfi looks
const pointer = new THREE.Vector2();
let pointerActive = 0;              // seconds left of "follow the pointer"; then he looks at the camera
const raycaster = new THREE.Raycaster();
const plane = new THREE.Plane();
const _head = new THREE.Vector3(), _p = new THREE.Vector3(), _inv = new THREE.Matrix4();
const _look = new THREE.Vector3(), _eye = new THREE.Vector3(), _dir = new THREE.Vector3();
canvas.addEventListener('pointermove', (e) => {
  const r = canvas.getBoundingClientRect();
  pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  pointerActive = 4;
});
function updateLook(dt: number): void {
  if (!model || !director) return;
  pointerActive = Math.max(0, pointerActive - dt);
  const head = model.getObjectByName('head');
  if (!head) return;
  head.getWorldPosition(_head);
  _head.y += 0.2;                                        // between the eyes
  if (pointerActive > 0) {
    plane.setFromNormalAndCoplanarPoint(camera.getWorldDirection(_p).negate(), _dir.copy(_head).addScaledVector(_p, 0.6));
    raycaster.setFromCamera(pointer, camera);
    if (!raycaster.ray.intersectPlane(plane, _p)) _p.copy(camera.position);
  } else {
    _p.copy(camera.position);
  }
  // direction to the target in Morfi's own frame (he faces +Z)
  _inv.copy(model.matrixWorld).invert();
  const local = _look.copy(_p).applyMatrix4(_inv).sub(_eye.copy(_head).applyMatrix4(_inv));
  const yaw = Math.atan2(local.x, local.z);
  const pitch = Math.atan2(local.y, Math.hypot(local.x, local.z));
  const behind = local.z < 0 ? 0 : 1;
  director.setLookTarget((yaw / THREE.MathUtils.degToRad(38)) * behind, (pitch / THREE.MathUtils.degToRad(30)) * behind);
}

// poke Morfi: he reacts. Only a short tap with one finger; dragging orbits, two fingers pinch.
const presses = new Map<number, { x: number; y: number; t: number; moved: boolean }>();
let multiTouch = false;
let pokes = 0;
canvas.addEventListener('pointerdown', (e) => {
  presses.set(e.pointerId, { x: e.clientX, y: e.clientY, t: performance.now(), moved: false });
  if (presses.size > 1) multiTouch = true;
});
canvas.addEventListener('pointermove', (e) => {
  const p = presses.get(e.pointerId);
  if (p && Math.hypot(e.clientX - p.x, e.clientY - p.y) > TAP_PX) p.moved = true;
});
canvas.addEventListener('pointercancel', (e) => { presses.delete(e.pointerId); if (!presses.size) multiTouch = false; });
canvas.addEventListener('pointerup', (e) => {
  const p = presses.get(e.pointerId);
  presses.delete(e.pointerId);
  const multi = multiTouch;
  if (!presses.size) multiTouch = false;
  if (!p || multi || presses.size || p.moved || performance.now() - p.t > TAP_MS) return;
  if (Math.hypot(e.clientX - p.x, e.clientY - p.y) > TAP_PX || !model || !director) return;
  if (director.speaking || director.sceneName) return;   // he is busy talking or acting
  const r = canvas.getBoundingClientRect();
  raycaster.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
  if (raycaster.intersectObject(model, true).length) director.play(['Jump_Happy', 'Nod_Yes', 'Wave', 'Laugh'][pokes++ % 4]);
});

// ------------------------------------------------------------------ UI
document.getElementById('build-info')!.textContent = `versión ${__BUILD_INFO__.commit} · ${__BUILD_INFO__.date}`;
($('follow') as HTMLInputElement).addEventListener('change', (e) => {
  if (director) director.followViewer = (e.target as HTMLInputElement).checked;
});
($('kiosk') as HTMLInputElement).addEventListener('change', (e) => {
  if (director) director.kiosk = (e.target as HTMLInputElement).checked;
});
function setBackground(bg: string): void {
  app.classList.toggle('bg-light', bg !== 'dark');
  app.classList.toggle('bg-dark', bg === 'dark');
  document.querySelectorAll<HTMLButtonElement>('#bgs button').forEach((b) => b.classList.toggle('on', b.dataset.bg === bg));
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', bg === 'dark' ? '#1b2233' : '#eef1f7');
}
document.querySelectorAll<HTMLButtonElement>('#bgs button').forEach((b) => b.addEventListener('click', () => setBackground(b.dataset.bg!)));
setBackground(params.get('bg') === 'dark' ? 'dark' : 'light');

// the Controles panel: a side panel on wide screens, a bottom sheet on phones (swipe it down);
// only one panel at a time on phones (the Estilo panel speaks the same 'morfi:panel-open' event)
const panel = $('panel');
const ptoggle = $('panel-toggle');
const isOpen = () => !panel.classList.contains('collapsed');
function setPanel(open: boolean, announce = true): void {
  panel.classList.toggle('collapsed', !open);
  if (!open) panel.classList.remove('tall');
  panel.inert = !open;
  ptoggle.classList.toggle('on', open);
  ptoggle.setAttribute('aria-expanded', String(open));
  view.dirty = true;
  if (open && announce) document.dispatchEvent(new CustomEvent('morfi:panel-open', { detail: 'controls' }));
}
ptoggle.addEventListener('click', () => setPanel(!isOpen()));
$('panel-close').addEventListener('click', () => { setPanel(false); ptoggle.focus(); });
panel.addEventListener('keydown', (e) => { if (e.key === 'Escape') { setPanel(false); ptoggle.focus(); } });
document.addEventListener('morfi:panel-open', (e) => {
  if ((e as CustomEvent<string>).detail !== 'controls' && MOBILE.matches) setPanel(false, false);
});
MOBILE.addEventListener('change', (e) => setPanel(!e.matches, false));   // rotate / resize across the breakpoint
setPanel(!MOBILE.matches, false);

// swipe the sheet: down closes it, up makes it tall, a tap on the handle toggles tall
{
  const grip = $('panel-grip'), head = $('panel-head');
  let drag: { id: number; y: number; t: number; dy: number } | null = null;
  const down = (e: PointerEvent) => {
    if (!MOBILE.matches || (e.target as Element).closest('button')) return;
    drag = { id: e.pointerId, y: e.clientY, t: performance.now(), dy: 0 };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    panel.classList.add('dragging');
  };
  const move = (e: PointerEvent) => {
    if (!drag || e.pointerId !== drag.id) return;
    drag.dy = e.clientY - drag.y;
    panel.style.transform = `translateY(${Math.max(drag.dy, -40)}px)`;
  };
  const up = (e: PointerEvent) => {
    if (!drag || e.pointerId !== drag.id) return;
    const { dy, t } = drag;
    const v = dy / Math.max(1, performance.now() - t);    // px/ms
    drag = null;
    panel.classList.remove('dragging');
    panel.style.removeProperty('transform');
    if (dy > 70 || v > 0.6) {
      if (panel.classList.contains('tall') && dy < 200) panel.classList.remove('tall'); else setPanel(false);
    } else if (dy < -30 || v < -0.5) {
      panel.classList.add('tall');
    } else if (Math.abs(dy) < 6) {
      panel.classList.toggle('tall');
    }
  };
  for (const el of [grip, head]) {
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  }
}

// ------------------------------------------------------------------ embedding API (chatbot, screens)
const api = {
  play: (name: string) => { if (director?.names.includes(name)) playClip(name); },
  /** text only (no audio): the chatbot's own sentences */
  speak: (text: string) => (director && typeof text === 'string' ? director.speak(text.slice(0, 500)) : 0),
  /** a phrase of voice/index.json with Morfi's real voice (default: the chosen one); returns its length (s) */
  say: (k: string, v?: string) => (voice && typeof k === 'string' ? voice.say(k, typeof v === 'string' && voice.voices.some((x) => x.key === v) ? v : voice.voice) : 0),
  get voices() { return voice?.voices.map((v) => ({ key: v.key, name: v.name, official: v.key === voice!.official })) ?? []; },
  get phrases() { return voice?.phrases.map((p) => ({ key: p.key, label: phraseLabel(p), text: plainText(p.text), mood: p.mood, gesture: p.gesture })) ?? []; },
  /** facial expression layered on the current clip ('neutral' or '' to clear) */
  expression: (name: string) => { if (typeof name === 'string') setExpression(name); },
  get expressions() { return director?.expressions ?? []; },
  follow: (on: boolean) => { if (director) director.followViewer = !!on; },
  kiosk: (on: boolean) => { if (director) director.kiosk = !!on; },
  get actions() { return director?.names ?? []; },
  /** play a full scene (loads them the first time); resolves false if there is no such scene */
  scene: async (name: string) => (scenes && typeof name === 'string' && (await scenes.load()) ? scenes.play(name) : false),
  get scenes() { return scenes?.list ?? []; },
  /** stop talking or acting, back to Idle */
  stop: () => { voice?.stop(); scenes?.stop(); },
  /** what he is doing now (for a host page or a test) */
  get status() {
    return {
      playing: director?.playing ?? '', saying: voice?.saying ?? '', speaking: director?.speaking ?? false,
      voice: voice?.voice ?? '', audio: voice?.src ?? '', audioTime: voice?.audio.currentTime ?? 0,
      scene: scenes?.state ?? null, sceneTime: director?.sceneTime ?? 0, cinema: cinema?.shot ?? '',
      mouth: director?.faceState.mouth_open ?? 0, mouthTime: director?.speechTime ?? 0,
    };
  },
};
(window as unknown as { morfi: typeof api }).morfi = api;
// embedded as a widget: only the embedding page (parent) or the page itself may command him, not other windows
window.addEventListener('message', (e: MessageEvent) => {
  if (e.source !== window.parent && e.source !== window) return;
  const d = e.data as { type?: unknown; name?: unknown; text?: unknown; key?: unknown; voice?: unknown } | null;
  if (!d || typeof d !== 'object') return;
  if (d.type === 'play' && typeof d.name === 'string') api.play(d.name);
  if (d.type === 'speak' && typeof d.text === 'string') api.speak(d.text);
  if (d.type === 'say' && typeof d.key === 'string') api.say(d.key, typeof d.voice === 'string' ? d.voice : undefined);
  if (d.type === 'expression' && typeof d.name === 'string') api.expression(d.name);
  if (d.type === 'scene' && typeof d.name === 'string') void api.scene(d.name);
  if (d.type === 'stop') api.stop();
});

// ------------------------------------------------------------------ layout and loop
// Morfi is framed in the part of the stage the panels leave free (a view offset, not a camera move)
function occlusion(): void {
  const w = window.innerWidth, h = window.innerHeight;
  view.tx = view.ty = 0;
  if (document.documentElement.classList.contains('clean')) return;
  // the open panels (Controles and Estilo), by their layout boxes (offset*), not their sliding transform
  let left = 0, right = w, top = h;
  for (const el of document.querySelectorAll<HTMLElement>('#panel:not(.collapsed), .style-panel.open')) {
    if (MOBILE.matches) top = Math.min(top, el.offsetTop);
    else if (el.offsetLeft + el.offsetWidth / 2 > w / 2) right = Math.min(right, el.offsetLeft);
    else left = Math.max(left, el.offsetLeft + el.offsetWidth);
  }
  if (right - left > w * 0.3) view.tx = w / 2 - (left + right) / 2;
  view.ty = Math.max(0, Math.min(h * 0.6, h - top)) / 2;
  view.ts = Math.sqrt(h / (h - 2 * view.ty));
}
new ResizeObserver(() => { view.dirty = true; }).observe(panel);
document.addEventListener('morfi:panel-open', () => { view.dirty = true; });
/** the part of the lens the free stage shows (for the cinema framings); follows the eased view, so no jumps */
function freeFrame(): Frame {
  return { fx: (1 - (2 * view.x) / window.innerWidth) * view.s, fy: (1 - (2 * view.y) / window.innerHeight) * view.s };
}
let frameNo = 0;
function applyView(dt: number): void {
  if (view.dirty || ++frameNo % 15 === 0) { occlusion(); view.dirty = false; }   // the other panel says nothing when it closes
  const k = Math.min(1, dt * 5);
  view.x += (view.tx - view.x) * k;
  view.y += (view.ty - view.y) * k;
  view.s += (view.ts - view.s) * k;
  if (Math.abs(view.x - view.tx) < 0.2) view.x = view.tx;
  if (Math.abs(view.y - view.ty) < 0.2) view.y = view.ty;
  if (Math.abs(view.s - view.ts) < 0.001) view.s = view.ts;
  const w = window.innerWidth, h = window.innerHeight;
  const v = camera.view;
  if (view.x || view.y || view.s !== 1) {
    // a window of the full image, s times as big, centred so the image centre lands mid free stage
    const s = view.s, ox = w / 2 + view.x * s - (w * s) / 2, oy = h / 2 + view.y * s - (h * s) / 2;
    if (!v || !v.enabled || v.offsetX !== ox || v.offsetY !== oy || v.width !== w * s || v.fullWidth !== w || v.fullHeight !== h) camera.setViewOffset(w, h, ox, oy, w * s, h * s);
  } else if (v?.enabled) {
    camera.clearViewOffset();
  }
  // the scene player floats just above the sheet on phones, in the middle of the free stage
  setText(null, `${Math.round(view.y * 2)}|${Math.round(view.x)}`, 'view', () => {
    player.style.setProperty('--sheet', `${Math.round(view.y * 2)}px`);
    player.style.setProperty('--shift', `${Math.round(view.x)}px`);
  });
}

/** write to the DOM only when a value changes (the loop runs every frame) */
const shown = new Map<string, string>();
function setText(el: HTMLElement | null, value: string, key = el?.id ?? '', write?: () => void): void {
  if (shown.get(key) === value) return;
  shown.set(key, value);
  if (write) write(); else if (el) el.textContent = value;
}

function resize(): void {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setPixelRatio(pixelRatio());              // the window may have moved to a screen with another ratio
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.fov = w / h < 0.8 ? 40 : 30;
  camera.updateProjectionMatrix();
  style?.resize(w, h, renderer.getPixelRatio());
  view.dirty = true;
}
window.addEventListener('resize', resize);
resize();

const playerTime = $('player-time');
/** the phrase / scene button of a key, looked up once per key (the buttons are built once) */
const buttons = new Map<string, HTMLButtonElement | null>();
function buttonFor(kind: 'say' | 'scene', key: string): HTMLButtonElement | null {
  const id = kind + ':' + key;
  let b = buttons.get(id);
  if (!b) {
    b = document.querySelector<HTMLButtonElement>(`button[data-${kind}="${CSS.escape(key)}"]`);
    if (b) buttons.set(id, b);
  }
  return b;
}

/** progress of the phrase and the scene on their buttons and in the player */
function updateUI(): void {
  if (voice?.saying) {
    const b = buttonFor('say', voice.saying);
    b?.style.setProperty('--p', voice.progress.toFixed(3));
  }
  const s = scenes?.state;
  if (s) {
    const p = s.dur > 0 ? Math.min(1, s.t / s.dur) : 0;
    buttonFor('scene', s.key)?.style.setProperty('--p', p.toFixed(4));
    if (!seeking) seek.value = String(Math.round(p * 1000));
    seek.style.setProperty('--p', p.toFixed(4));
    setText(playerTime, s.waiting && !s.paused ? 'Cargando…' : `${mmss(s.t)} / ${mmss(s.dur)}`);
  }
}

const clock = new THREE.Clock();
const _centre = new THREE.Vector3();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1);
  applyView(dt);
  if (director) cinema?.update(dt, director.sceneTime);
  controls.update();
  if (model && director) {
    voice?.update();
    scenes?.update(dt);
    director.update(dt);
    updateLook(dt);
    director.aimHead();
    style?.update(dt);
    model.getWorldPosition(_centre);
    style?.beforeContact();
    contact.update(renderer, scene, _centre);
    style?.afterContact();
  }
  renderer.render(scene, camera);
  director?.restore();
  updateUI();
});
