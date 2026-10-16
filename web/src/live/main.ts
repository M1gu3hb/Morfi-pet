// "Morfi en vivo": the animated Morfi built on the AI (Meshy) mesh. Loads
// models/morfi_live.glb (rig, 10 baked clips, face decals), the face curves and the
// eye/mouth shader constants, and lets people play with him. Also an embeddable
// character: window.morfi API and postMessage({type: 'play'|'speak', ...}).
import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { useDualQuatSkinning } from '../dqskin';
import { ContactShadow } from '../contact';
import { MorfiFace, type FaceParams } from './face';
import { Director, type FaceAnims } from './director';

const params = new URLSearchParams(location.search);
const BASE = './models/';
const MODEL_URL = params.get('model') ?? BASE + 'morfi_live.glb';
const LOWPOWER = params.has('lowpower');
if (params.has('clean') || params.has('kiosk')) document.documentElement.classList.add('clean');

const LABELS: Record<string, string> = {
  Idle: 'Reposo', Wave: 'Saludar', Talk: 'Hablar', Nod_Yes: 'Sí', Shake_No: 'No', Look_Around: 'Curioso',
  Present: 'Presentar', Jump_Happy: '¡Feliz!', Walk: 'Caminar', Dance: 'Bailar',
};
const ORDER = Object.keys(LABELS);

// ------------------------------------------------------------------ renderer, scene, studio
const canvas = document.getElementById('view') as HTMLCanvasElement;
const app = document.getElementById('app')!;
const statusEl = document.getElementById('status')!;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(LOWPOWER ? 1 : Math.min(window.devicePixelRatio, 2));
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
controls.minDistance = 1.0;
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

// ------------------------------------------------------------------ loading
let model: THREE.Object3D | null = null;
let director: Director | null = null;
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
const json = <T,>(url: string): Promise<T> => fetch(url).then((r) => {
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json() as Promise<T>;
});

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
    }
  });
  const face = new MorfiFace(model, faceParams);
  scene.add(model);
  director = new Director(model, gltf.animations, anims, face);
  director.onAction = (name) => {
    document.querySelectorAll<HTMLButtonElement>('#actions button').forEach((b) => b.classList.toggle('on', b.dataset.anim === name));
  };
  buildButtons(director.names);
  director.kiosk = params.has('kiosk');
  (document.getElementById('kiosk') as HTMLInputElement).checked = director.kiosk;
  const start = params.get('anim');
  director.play(start && director.names.includes(start) ? start : 'Idle', 0);
  statusEl.classList.add('hidden');
  document.getElementById('stats')!.textContent = stats(model, gltf.animations.length);
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

function buildButtons(names: string[]): void {
  const box = document.getElementById('actions')!;
  box.innerHTML = '';
  for (const n of [...ORDER.filter((k) => names.includes(k)), ...names.filter((k) => !ORDER.includes(k))]) {
    const b = document.createElement('button');
    b.dataset.anim = n;
    b.textContent = LABELS[n] ?? n;
    b.addEventListener('click', () => director?.play(n));
    box.append(b);
  }
}

// ------------------------------------------------------------------ the viewer: where Morfi looks
const pointer = new THREE.Vector2();
let pointerActive = 0;              // seconds left of "follow the pointer"; then he looks at the camera
const raycaster = new THREE.Raycaster();
const plane = new THREE.Plane();
const _head = new THREE.Vector3(), _p = new THREE.Vector3(), _inv = new THREE.Matrix4();
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
    plane.setFromNormalAndCoplanarPoint(camera.getWorldDirection(_p).negate(), _head.clone().addScaledVector(_p, 0.6));
    raycaster.setFromCamera(pointer, camera);
    if (!raycaster.ray.intersectPlane(plane, _p)) _p.copy(camera.position);
  } else {
    _p.copy(camera.position);
  }
  // direction to the target in Morfi's own frame (he faces +Z)
  _inv.copy(model.matrixWorld).invert();
  const local = _p.clone().applyMatrix4(_inv).sub(_head.clone().applyMatrix4(_inv));
  const yaw = Math.atan2(local.x, local.z);
  const pitch = Math.atan2(local.y, Math.hypot(local.x, local.z));
  const behind = local.z < 0 ? 0 : 1;
  director.setLookTarget((yaw / THREE.MathUtils.degToRad(38)) * behind, (pitch / THREE.MathUtils.degToRad(30)) * behind);
}

// poke Morfi: he reacts
let downAt: { x: number; y: number } | null = null;
let pokes = 0;
canvas.addEventListener('pointerdown', (e) => { downAt = { x: e.clientX, y: e.clientY }; });
canvas.addEventListener('pointerup', (e) => {
  if (!downAt || !model || !director || Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 5) return;
  const r = canvas.getBoundingClientRect();
  raycaster.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
  if (raycaster.intersectObject(model, true).length) director.play(['Jump_Happy', 'Nod_Yes', 'Wave'][pokes++ % 3]);
});

// ------------------------------------------------------------------ UI
document.getElementById('build-info')!.textContent = `versión ${__BUILD_INFO__.commit} · ${__BUILD_INFO__.date}`;
document.getElementById('say-form')!.addEventListener('submit', (e) => {
  e.preventDefault();
  const t = (document.getElementById('say-text') as HTMLInputElement).value.trim();
  if (t) director?.speak(t);
});
(document.getElementById('follow') as HTMLInputElement).addEventListener('change', (e) => {
  if (director) director.followViewer = (e.target as HTMLInputElement).checked;
});
(document.getElementById('kiosk') as HTMLInputElement).addEventListener('change', (e) => {
  if (director) director.kiosk = (e.target as HTMLInputElement).checked;
});
function setBackground(bg: string): void {
  app.className = 'bg-' + bg;
  document.querySelectorAll<HTMLButtonElement>('#bgs button').forEach((b) => b.classList.toggle('on', b.dataset.bg === bg));
}
document.querySelectorAll<HTMLButtonElement>('#bgs button').forEach((b) => b.addEventListener('click', () => setBackground(b.dataset.bg!)));
setBackground(params.get('bg') === 'dark' ? 'dark' : 'light');
const panel = document.getElementById('panel')!;
const ptoggle = document.getElementById('panel-toggle')!;
function setPanel(open: boolean): void {
  panel.classList.toggle('collapsed', !open);
  ptoggle.classList.toggle('show', !open);
  ptoggle.setAttribute('aria-expanded', String(open));
}
ptoggle.addEventListener('click', () => setPanel(true));
panel.addEventListener('dblclick', () => setPanel(false));
if (window.matchMedia('(max-width: 720px)').matches) setPanel(false);

// ------------------------------------------------------------------ embedding API (chatbot, screens)
const api = {
  play: (name: string) => { if (director?.names.includes(name)) director.play(name); },
  speak: (text: string) => (director && typeof text === 'string' ? director.speak(text.slice(0, 500)) : 0),
  follow: (on: boolean) => { if (director) director.followViewer = !!on; },
  kiosk: (on: boolean) => { if (director) director.kiosk = !!on; },
  get actions() { return director?.names ?? []; },
};
(window as unknown as { morfi: typeof api }).morfi = api;
window.addEventListener('message', (e: MessageEvent) => {
  const d = e.data as { type?: unknown; name?: unknown; text?: unknown } | null;
  if (!d || typeof d !== 'object') return;
  if (d.type === 'play' && typeof d.name === 'string') api.play(d.name);
  if (d.type === 'speak' && typeof d.text === 'string') api.speak(d.text);
});

// ------------------------------------------------------------------ layout and loop
function resize(): void {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.fov = w / h < 0.8 ? 40 : 30;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();

const clock = new THREE.Clock();
const _centre = new THREE.Vector3();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1);
  controls.update();
  if (model && director) {
    director.update(dt);
    updateLook(dt);
    director.aimHead();
    model.getWorldPosition(_centre);
    contact.update(renderer, scene, _centre);
  }
  renderer.render(scene, camera);
  director?.restore();
});
