import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

// ------------------------------------------------------------------ setup
const MODEL_URL = new URLSearchParams(location.search).get('model') ?? './models/morfi_web.glb';
const canvas = document.getElementById('view') as HTMLCanvasElement;
const app = document.getElementById('app')!;
const statusEl = document.getElementById('status')!;
const progressEl = document.getElementById('progress')!;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(new URLSearchParams(location.search).has('lowpower') ? 1 : Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.setClearColor(0x000000, 0);

const scene = new THREE.Scene();
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.55;

// Same framing as the Blender cameras (65.2 mm on a 36 mm vertical sensor).
const VFOV = (2 * Math.atan(18 / 65.2) * 180) / Math.PI;
const camera = new THREE.PerspectiveCamera(VFOV, 1, 0.05, 50);
const TARGET = new THREE.Vector3(0, 0.52, 0);
const DIST = 2.5;
const CAM_H = 0.756;

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.target.copy(TARGET);
controls.minDistance = 0.6;
controls.maxDistance = 8;
controls.autoRotateSpeed = 1.5;

// Studio lights (key upper-left/front, fill right, rim back), soft shadow.
scene.add(new THREE.HemisphereLight(0xffffff, 0xe8e6e0, 1.1));
const key = new THREE.DirectionalLight(0xffffff, 2.2);
key.position.set(-2.2, 2.9, 3.0);
key.castShadow = true;
const LOWPOWER = new URLSearchParams(location.search).has('lowpower');
key.shadow.mapSize.set(LOWPOWER ? 512 : 2048, LOWPOWER ? 512 : 2048);
key.shadow.camera.left = -1; key.shadow.camera.right = 1; key.shadow.camera.top = 1.6; key.shadow.camera.bottom = -0.4;
key.shadow.radius = 6; key.shadow.bias = -0.0004;
scene.add(key);
const fill = new THREE.DirectionalLight(0xffffff, 0.8);
fill.position.set(3.0, 1.3, 2.4);
scene.add(fill);
const rim = new THREE.DirectionalLight(0xffffff, 0.9);
rim.position.set(1.2, 2.6, -2.6);
scene.add(rim);
const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 64), new THREE.ShadowMaterial({ opacity: 0.16 }));
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

// ------------------------------------------------------------------ views
// Blender azimuths (camera moves toward Morfi's left with positive values).
const VIEWS: Record<string, number> = {
  front: 0, three_quarter_front: 33, profile_left: 90, profile_right: -90, back: 180, three_quarter_back: -150,
};
function setView(name: string) {
  const az = (VIEWS[name] * Math.PI) / 180;
  // Blender (x, y, z) -> glTF (x, z, -y)
  camera.position.set(DIST * Math.sin(az), CAM_H, DIST * Math.cos(az));
  controls.target.copy(TARGET);
  controls.update();
}

// ------------------------------------------------------------------ toggles
const GROUPS: Record<string, string[]> = {
  Sudadera: ['Hoodie', 'Hoodie_Hem', 'Hoodie_Cuff_L', 'Hoodie_Cuff_R', 'Hoodie_Zipper', 'Hoodie_Drawstrings'],
  Playera: ['Tshirt', 'Tshirt_Collar', 'Tshirt_Logo'],
  Tenis: ['Shoe_L', 'Shoe_R'],
  Lentes: ['Glasses_Frame', 'Glasses_Lens_L', 'Glasses_Lens_R'],
  Cubos: ['Pixel_01', 'Pixel_02', 'Pixel_03'],
  Laptop: ['Laptop'],
};
const groupObjects: Record<string, THREE.Object3D[]> = {};
const groupState: Record<string, boolean> = {};

// ------------------------------------------------------------------ eyes follow the camera
// In the references Morfi always looks at the viewer in front / 3-4 shots. The
// eye bones get the same turn (so the modelled convergence is kept), fading out
// toward the profile and switched off from behind.
let eyesFollow = true;
let eyeBones: THREE.Object3D[] = [];
let eyeBase: THREE.Quaternion[] = [];
let headBone: THREE.Object3D | null = null;
const headRestInv = new THREE.Quaternion();
const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _qk = new THREE.Quaternion();
const _v = new THREE.Vector3(), _mid = new THREE.Vector3(), _fwd = new THREE.Vector3();
function captureEyeBase() { eyeBase = eyeBones.map((b) => b.quaternion.clone()); }
function aimEyes() {
  if (eyeBones.length < 2 || !headBone) return;
  eyeBones.forEach((b, i) => b.quaternion.copy(eyeBase[i]));
  if (!eyesFollow) return;
  model!.updateMatrixWorld(true);
  headBone.getWorldQuaternion(_q).multiply(headRestInv);
  _fwd.set(0, 0, 1).applyQuaternion(_q);
  _mid.set(0, 0, 0);
  for (const b of eyeBones) _mid.add(b.getWorldPosition(_v));
  _mid.multiplyScalar(1 / eyeBones.length);
  const toCam = _v.copy(camera.position).sub(_mid).normalize();
  const ang = _fwd.angleTo(toCam);
  const k = ang < 0.7 ? 1 : ang < 1.571 ? 1 - (0.65 * (ang - 0.7)) / 0.871 : Math.max(0, 0.35 * (1 - (ang - 1.571) / 0.5));
  if (k <= 0) return;
  _qk.identity().slerp(_q2.setFromUnitVectors(_fwd, toCam), k);
  for (const b of eyeBones) {
    b.parent!.getWorldQuaternion(_q);
    // local = parent^-1 * delta * parent * local
    b.quaternion.premultiply(_q2.copy(_q).premultiply(_qk).premultiply(_q.clone().invert()));
  }
}

let model: THREE.Object3D | null = null;
let mixer: THREE.AnimationMixer | null = null;
let clips: THREE.AnimationClip[] = [];
let action: THREE.AnimationAction | null = null;
let playing = true;
const originalMaterials = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
const clayMat = new THREE.MeshStandardMaterial({ color: 0xb9bcc4, roughness: 0.75, metalness: 0 });
const wireMat = new THREE.MeshBasicMaterial({ color: 0x1b2a4a, wireframe: true });

function setGroup(name: string, on: boolean) {
  groupState[name] = on;
  for (const o of groupObjects[name] ?? []) o.visible = on;
  const cb = document.querySelector<HTMLInputElement>(`input[data-group="${name}"]`);
  if (cb) cb.checked = on;
}

function buildToggles() {
  const box = document.getElementById('toggles')!;
  box.innerHTML = '';
  for (const name of Object.keys(GROUPS)) {
    const label = document.createElement('label');
    label.className = 'check';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.dataset.group = name;
    cb.checked = groupState[name];
    cb.addEventListener('change', () => setGroup(name, cb.checked));
    label.append(cb, document.createTextNode(' ' + name));
    box.append(label);
  }
}

function setMode(mode: string) {
  model?.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    if (!originalMaterials.has(m)) originalMaterials.set(m, m.material);
    m.material = mode === 'clay' ? clayMat : mode === 'wire' ? wireMat : originalMaterials.get(m)!;
  });
  document.querySelectorAll('#modes button').forEach((b) => b.classList.toggle('on', (b as HTMLElement).dataset.mode === mode));
}

function setBackground(bg: string) {
  app.className = 'bg-' + bg;
  ground.visible = bg !== 'transparent';
  document.querySelectorAll('#bgs button').forEach((b) => b.classList.toggle('on', (b as HTMLElement).dataset.bg === bg));
}

// ------------------------------------------------------------------ animation
const ANIM_LABELS: Record<string, string> = {
  Pose_Neutral: 'Pose neutra', Pose_Hero: 'Pose hero (laptop)', Idle: 'Idle (respira)', Walk: 'Caminar', Run: 'Correr', Wave: 'Saludar',
};
function playClip(name: string) {
  if (!mixer) return;
  const clip = clips.find((c) => c.name === name);
  mixer.stopAllAction();
  if (!clip) return;
  action = mixer.clipAction(clip);
  const isPose = name.startsWith('Pose_');
  action.setLoop(isPose ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
  action.clampWhenFinished = true;
  action.reset().play();
  action.paused = !playing && !isPose;
  // the laptop lives on the right hand: shown automatically in the hero pose
  setGroup('Laptop', name === 'Pose_Hero');
  invalidate(6);
}

// ------------------------------------------------------------------ loading
function countStats(root: THREE.Object3D) {
  let tris = 0, meshes = 0;
  const mats = new Set<string>();
  root.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    meshes++;
    const g = m.geometry;
    tris += g.index ? g.index.count / 3 : g.attributes.position.count / 3;
    (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => mats.add(x.uuid));
  });
  return { tris: Math.round(tris), meshes, mats: mats.size };
}

const loader = new GLTFLoader();
loader.load(
  MODEL_URL,
  (gltf: GLTF) => {
    model = gltf.scene;
    model.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; m.frustumCulled = false; }
    });
    scene.add(model);
    for (const [g, names] of Object.entries(GROUPS)) {
      groupObjects[g] = names.map((n) => model!.getObjectByName(n)).filter((x): x is THREE.Object3D => !!x);
      groupState[g] = g !== 'Laptop';
    }
    buildToggles();
    for (const g of Object.keys(GROUPS)) setGroup(g, groupState[g]);
    eyeBones = ['eyeL', 'eyeR', 'eye.L', 'eye.R'].map((n) => model!.getObjectByName(n)).filter((x): x is THREE.Object3D => !!x);
    headBone = model.getObjectByName('head') ?? null;
    model.updateMatrixWorld(true);
    if (headBone) headRestInv.copy(headBone.getWorldQuaternion(_q)).invert();
    captureEyeBase();
    clips = gltf.animations;
    mixer = new THREE.AnimationMixer(model);
    const sel = document.getElementById('anim') as HTMLSelectElement;
    sel.innerHTML = '';
    const order = ['Pose_Neutral', 'Pose_Hero', 'Idle', 'Walk', 'Run', 'Wave'];
    const names = clips.map((c) => c.name).sort((a, b) => (order.indexOf(a) + 99 * +(order.indexOf(a) < 0)) - (order.indexOf(b) + 99 * +(order.indexOf(b) < 0)));
    for (const n of names) {
      const opt = document.createElement('option');
      opt.value = n;
      opt.textContent = ANIM_LABELS[n] ?? n;
      sel.append(opt);
    }
    if (names.includes('Pose_Neutral')) { sel.value = 'Pose_Neutral'; playClip('Pose_Neutral'); }
    const s = countStats(model);
    document.getElementById('stats')!.textContent =
      `${s.tris.toLocaleString('es-MX')} triángulos · ${s.meshes} mallas · ${s.mats} materiales · ${clips.length} animaciones`;
    statusEl.classList.add('hidden');
    invalidate(6);
    (window as unknown as { __morfiReady: boolean }).__morfiReady = true;
    (window as unknown as { __morfiModel: THREE.Object3D }).__morfiModel = model;
  },
  (ev) => {
    if (ev.lengthComputable) progressEl.textContent = Math.round((ev.loaded / ev.total) * 100) + '%';
  },
  (err) => {
    statusEl.classList.add('error');
    statusEl.textContent = 'No se pudo cargar el modelo (' + MODEL_URL + '). Ejecuta "npm run sync-assets" después de exportar. ' + String((err as Error)?.message ?? err);
    console.error(err);
  },
);

// ------------------------------------------------------------------ UI wiring
document.querySelectorAll<HTMLButtonElement>('#views button').forEach((b) => b.addEventListener('click', () => setView(b.dataset.view!)));
document.getElementById('reset')!.addEventListener('click', () => setView('front'));
(document.getElementById('autorotate') as HTMLInputElement).addEventListener('change', (e) => {
  controls.autoRotate = (e.target as HTMLInputElement).checked;
});
(document.getElementById('eyes') as HTMLInputElement).addEventListener('change', (e) => {
  eyesFollow = (e.target as HTMLInputElement).checked;
  invalidate(3);
});
(document.getElementById('anim') as HTMLSelectElement).addEventListener('change', (e) => playClip((e.target as HTMLSelectElement).value));
document.getElementById('play')!.addEventListener('click', (e) => {
  playing = !playing;
  if (action) action.paused = !playing;
  (e.target as HTMLButtonElement).textContent = playing ? 'Pausa' : 'Reproducir';
});
const speed = document.getElementById('speed') as HTMLInputElement;
speed.addEventListener('input', () => {
  if (mixer) mixer.timeScale = parseFloat(speed.value);
  document.getElementById('speed-val')!.textContent = speed.value + '×';
});
document.getElementById('preset-full')!.addEventListener('click', () => {
  for (const g of Object.keys(GROUPS)) setGroup(g, g !== 'Laptop' || (action?.getClip().name === 'Pose_Hero'));
});
document.getElementById('preset-base')!.addEventListener('click', () => {
  for (const g of Object.keys(GROUPS)) setGroup(g, false);
});
document.querySelectorAll<HTMLButtonElement>('#bgs button').forEach((b) => b.addEventListener('click', () => setBackground(b.dataset.bg!)));
document.querySelectorAll<HTMLButtonElement>('#modes button').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode!)));
document.getElementById('shot')!.addEventListener('click', () => {
  // render once with the page background baked in (unless transparent)
  const bg = app.className.replace('bg-', '');
  const prev = renderer.getClearAlpha();
  if (bg === 'light') renderer.setClearColor(0xfdfdf9, 1);
  if (bg === 'dark') renderer.setClearColor(0x14161c, 1);
  aimEyes();
  renderer.render(scene, camera);
  const url = renderer.domElement.toDataURL('image/png');
  renderer.setClearColor(0x000000, prev);
  const a = document.createElement('a');
  a.href = url;
  a.download = `morfi_${Date.now()}.png`;
  a.click();
});
const panel = document.getElementById('panel')!;
const ptoggle = document.getElementById('panel-toggle')!;
ptoggle.addEventListener('click', () => {
  const collapsed = panel.classList.toggle('collapsed');
  ptoggle.setAttribute('aria-expanded', String(!collapsed));
});
if (window.matchMedia('(max-width: 720px)').matches) panel.classList.add('collapsed');
(document.getElementById('download') as HTMLAnchorElement).href = MODEL_URL;
document.getElementById('model-name')!.textContent = MODEL_URL.split('/').pop()!;

// ------------------------------------------------------------------ loop
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  // keep the whole character in frame on portrait/landscape screens
  const fit = w / h < 0.85 ? 1.25 : 1.0;
  camera.fov = VFOV * fit;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();
setView('front');
setBackground('light');
// Render on demand: redraw only while something moves (camera damping,
// auto-rotate, a looping animation) or after a UI change.
const clock = new THREE.Clock();
let dirtyFrames = 4;
export function invalidate(frames = 3) { dirtyFrames = Math.max(dirtyFrames, frames); }
controls.addEventListener('change', () => invalidate(2));
document.getElementById('panel')!.addEventListener('click', () => invalidate(6));
document.getElementById('panel')!.addEventListener('change', () => invalidate(6));
window.addEventListener('resize', () => invalidate(3));
renderer.setAnimationLoop(() => {
  const dt = clock.getDelta();
  const animating = !!(mixer && action && !action.paused && action.isRunning() && !action.getClip().name.startsWith('Pose_'));
  if (mixer && (animating || dirtyFrames > 0)) { mixer.update(animating ? dt : 0); captureEyeBase(); }
  const moving = controls.update() || controls.autoRotate;
  if (animating || moving || dirtyFrames > 0) {
    aimEyes();
    renderer.render(scene, camera);
    if (dirtyFrames > 0) dirtyFrames--;
  }
});
(window as unknown as { __morfiInvalidate: () => void }).__morfiInvalidate = () => invalidate(4);
