import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { applyReferenceLook, loadLook, setReferenceMix, setShotMorph } from './look';
import { sfx, setMusic, setSfxEnabled, setVolume, unlockAudio } from './sfx';
import { ContactShadow } from './contact';

// ------------------------------------------------------------------ setup
const params = new URLSearchParams(location.search);
const MODEL_URL = params.get('model') ?? './models/morfi.glb';
const LOWPOWER = params.has('lowpower');
const EXACT = params.has('exact'); // tests: exact reference lens, no framing margin
if (params.has('clean')) document.documentElement.classList.add('clean');
const canvas = document.getElementById('view') as HTMLCanvasElement;
const app = document.getElementById('app')!;
const stage = document.getElementById('stage')!;
const refImg = document.getElementById('ref-img') as HTMLImageElement;
const statusEl = document.getElementById('status')!;
const progressEl = document.getElementById('progress')!;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(LOWPOWER ? 1 : Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
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
const REF_W = 1145, REF_H = 1374;

const controls = new OrbitControls(camera, canvas);
let dirtyFrames = 4;
controls.enableDamping = true;
controls.target.copy(TARGET);
controls.minDistance = 0.6;
controls.maxDistance = 8;
controls.autoRotateSpeed = 1.5;

// Studio lights (key upper-left/front, fill right, rim back), soft shadow.
// The references are product shots: the lights keep their place relative to
// the camera ("Luz sigue a la cámara"). In the "Fiel a la foto" shader the
// shading comes from the photos themselves (look.ts); only the key light's
// shadow is used there.
scene.add(new THREE.HemisphereLight(0xffffff, 0xe8e6e0, 1.1));
const lightRig = new THREE.Group();
scene.add(lightRig);
let lightsFollow = true;
function turnLights() {
  const dx = camera.position.x - controls.target.x;
  const dz = camera.position.z - controls.target.z;
  lightRig.rotation.y = lightsFollow ? Math.atan2(dx, dz) : 0;
  lightRig.updateMatrixWorld(true);
}
const key = new THREE.DirectionalLight(0xffffff, 2.2);
key.position.set(-2.2, 2.9, 3.0);
key.castShadow = true;
key.shadow.mapSize.set(LOWPOWER ? 512 : 2048, LOWPOWER ? 512 : 2048);
key.shadow.camera.left = -1; key.shadow.camera.right = 1; key.shadow.camera.top = 1.6; key.shadow.camera.bottom = -0.4;
key.shadow.radius = 6; key.shadow.bias = -0.0004;
lightRig.add(key);
const fill = new THREE.DirectionalLight(0xffffff, 0.8);
fill.position.set(3.0, 1.3, 2.4);
lightRig.add(fill);
const rim = new THREE.DirectionalLight(0xffffff, 0.9);
rim.position.set(1.2, 2.6, -2.6);
lightRig.add(rim);
// floor: a soft contact shadow under the feet, as on the white studio floor of
// the photos (the key light's own shadow only falls on Morfi)
const contact = new ContactShadow(1.6, LOWPOWER ? 256 : 512, 0.32, 0.5, 2.4);
const ground = contact.plane;
scene.add(ground);
const _centre = new THREE.Vector3();

// ------------------------------------------------------------------ views
const VIEWS: Record<string, number> = {
  front: 0, three_quarter_front: 33, profile_left: 90, profile_right: -90, back: 180, three_quarter_back: -150,
};
type CamView = { az: number; height: number; distance: number; lens: number; target: number[]; roll?: number };
let CAMS: Record<string, CamView> = {};
let REF_POSES: string[] = [];
let lensFov = VFOV;
let currentView = 'front';
let aligned = true; // camera still exactly at the reference camera (no orbiting since)
let rollRad = 0;
const b2t = (v: number[]) => new THREE.Vector3(v[0], v[2], -v[1]);
fetch('./models/views.json').then((r) => (r.ok ? r.json() : null)).then((j) => {
  if (!j) return;
  CAMS = j.camera_views ?? {};
  REF_POSES = j.poses ?? [];
  setView(currentView, false);
}).catch(() => undefined);

function setView(name: string, sound = true) {
  currentView = name;
  const c = CAMS[name];
  if (c) {
    const a = (c.az * Math.PI) / 180;
    const t = c.target;
    camera.position.copy(b2t([t[0] + c.distance * Math.sin(a), t[1] - c.distance * Math.cos(a), c.height]));
    controls.target.copy(b2t(t));
    lensFov = (2 * Math.atan(18 / c.lens) * 180) / Math.PI;
    rollRad = ((c.roll ?? 0) * Math.PI) / 180;
  } else {
    const az = ((VIEWS[name] ?? 0) * Math.PI) / 180;
    camera.position.set(DIST * Math.sin(az), CAM_H, DIST * Math.cos(az));
    controls.target.copy(TARGET);
    lensFov = VFOV;
    rollRad = 0;
  }
  aligned = true;
  document.querySelectorAll('#views button').forEach((b) => b.classList.toggle('on', (b as HTMLElement).dataset.view === name));
  if (sound) sfx.whoosh();
  updateCompare();
  resize();
  const cur = action?.getClip().name ?? 'Pose_Neutral';
  if (mixer && (cur === 'Pose_Neutral' || cur.startsWith('Ref_'))) {
    const want = REF_POSES.includes(name) && clips.some((k) => k.name === 'Ref_' + name) ? 'Ref_' + name : 'Pose_Neutral';
    if (want !== cur) playClip(want, false);
  }
  controls.update();
  invalidate(4);
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
let eyesFollow = true;
let eyeBones: THREE.Object3D[] = [];
const EYE_MAX = (28 * Math.PI) / 180;
let eyeBase: THREE.Quaternion[] = [];
let headBone: THREE.Object3D | null = null;
const headRestInv = new THREE.Quaternion();
const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _qk = new THREE.Quaternion();
const _v = new THREE.Vector3(), _mid = new THREE.Vector3(), _fwd = new THREE.Vector3();
// face of the photo (shot morph) while the camera is aligned with a reference
// shot in its pose; it fades out as soon as the camera is moved
let shotW = 0;
let shotView = '';
function updateShot(dt: number) {
  if (!model) return false;
  const want = aligned && action?.getClip().name === 'Ref_' + currentView ? 1 : 0;
  if (want && shotView !== currentView) { shotView = currentView; shotW = 0; }
  const prev = shotW;
  shotW = EXACT ? want : shotW + (want - shotW) * Math.min(1, dt * 7);
  if (Math.abs(shotW - want) < 0.005) shotW = want;
  if (shotW === prev) return false;
  setShotMorph(model, shotView, shotW);
  return true;
}
function captureEyeBase() { eyeBase = eyeBones.map((b) => b.quaternion.clone()); }
// put the eyes back to the animated pose once a frame is drawn: three.js only
// writes a bone when its animated value changes, so with a still pose the
// follow-the-camera turn would otherwise be taken as the next frame's base and
// pile up (the eyes rolled until only the white showed)
function unaimEyes() { eyeBones.forEach((b, i) => { if (eyeBase[i]) b.quaternion.copy(eyeBase[i]); }); }
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
  // the shot key already turns the eyes as in the photo; never more than
  // EYE_MAX, so the iris stays inside its socket
  const kk = Math.min(k * (1 - shotW), EYE_MAX / Math.max(ang, 1e-6));
  if (kk <= 0) return;
  _qk.identity().slerp(_q2.setFromUnitVectors(_fwd, toCam), kk);
  for (const b of eyeBones) {
    b.parent!.getWorldQuaternion(_q);
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
    cb.addEventListener('change', () => { setGroup(name, cb.checked); sfx.toggle(cb.checked); });
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

// ------------------------------------------------------------------ shader: photo look / physical
let lookReady = false;
let shading: 'ref' | 'pbr' = 'ref';
function setShading(mode: 'ref' | 'pbr') {
  shading = lookReady ? mode : 'pbr';
  setReferenceMix(shading === 'ref' ? 1 : 0);
  // the photo look is already the final colour: no tone curve on top of it
  renderer.toneMapping = shading === 'ref' ? THREE.NoToneMapping : THREE.NeutralToneMapping;
  document.querySelectorAll('#shading button').forEach((b) => b.classList.toggle('on', (b as HTMLElement).dataset.shading === shading));
  invalidate(4);
}

// ------------------------------------------------------------------ compare with the reference photo
type CompareMode = 'off' | 'overlay' | 'wipe' | 'diff' | 'side';
let compare: CompareMode = 'off';
const REF_VIEWS = ['front', 'three_quarter_front', 'profile_left', 'profile_right', 'back', 'three_quarter_back'];
const hasRef = (v: string) => REF_VIEWS.includes(v);
function setCompare(mode: CompareMode) {
  compare = mode;
  document.querySelectorAll('#compare-modes button').forEach((b) => b.classList.toggle('on', (b as HTMLElement).dataset.cmp === mode));
  updateCompare();
  resize();
  invalidate(4);
}
function updateCompare() {
  const on = compare !== 'off' && hasRef(currentView);
  app.classList.toggle('comparing', on);
  app.dataset.cmp = on ? compare : 'off';
  if (on) refImg.src = `./refs/${currentView}.jpg`;
  const hint = document.getElementById('cmp-hint')!;
  hint.textContent = !hasRef(currentView) ? 'Elige una vista con foto de referencia.'
    : !aligned ? 'Moviste la cámara: vuelve a pulsar la vista para alinear con la foto.' : '';
  const amt = parseFloat((document.getElementById('cmp-amount') as HTMLInputElement).value);
  stage.style.setProperty('--amt', String(amt));
}

// ------------------------------------------------------------------ animation
const ANIM_LABELS: Record<string, string> = {
  Pose_Neutral: 'Pose neutra', Pose_Hero: 'Pose hero (laptop)', Idle: 'Idle (respira)', Walk: 'Caminar', Run: 'Correr', Wave: 'Saludar',
};
function playClip(name: string, sound = true) {
  if (!mixer) return;
  const clip = clips.find((c) => c.name === name);
  mixer.stopAllAction();
  if (!clip) return;
  action = mixer.clipAction(clip);
  const isPose = name.startsWith('Pose_') || name.startsWith('Ref_');
  action.setLoop(isPose ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
  action.clampWhenFinished = true;
  action.reset().play();
  action.paused = !playing && !isPose;
  setGroup('Laptop', name === 'Pose_Hero');
  footY.length = 0;
  if (sound) {
    if (name === 'Wave') sfx.wave();
    else if (name === 'Pose_Hero') sfx.hero();
    else sfx.click();
  }
  invalidate(6);
}

// footsteps: a foot that comes down to its lowest height plays a step
let feet: THREE.Object3D[] = [];
const footY: { y: number; down: boolean; min: number }[] = [];
function footsteps() {
  const name = action?.getClip().name;
  if (!name || (name !== 'Walk' && name !== 'Run') || action!.paused) return;
  feet.forEach((f, i) => {
    const y = f.getWorldPosition(_v).y;
    const s = footY[i] ?? (footY[i] = { y, down: false, min: y });
    s.min = Math.min(s.min, y);
    const near = y < s.min + 0.012;
    if (near && !s.down && y < s.y) sfx.step(name === 'Run');
    s.down = near;
    s.y = y;
  });
}

// poke Morfi: squash and stretch + a squeak
const raycaster = new THREE.Raycaster();
let bounceT = -1;
function bounce(dt: number) {
  if (!model || bounceT < 0) return;
  bounceT += dt;
  const t = bounceT / 0.45;
  if (t >= 1) { model.scale.set(1, 1, 1); bounceT = -1; return; }
  const s = 1 + 0.07 * Math.sin(t * Math.PI * 2.5) * (1 - t);
  model.scale.set(1 / Math.sqrt(s), s, 1 / Math.sqrt(s));
}
let downAt: { x: number; y: number } | null = null;
canvas.addEventListener('pointerdown', (e) => { downAt = { x: e.clientX, y: e.clientY }; unlockAudio(); });
canvas.addEventListener('pointerup', (e) => {
  if (!downAt || !model || Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 5) return;
  const r = canvas.getBoundingClientRect();
  raycaster.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
  if (raycaster.intersectObject(model, true).length) { bounceT = 0; sfx.boop(); invalidate(30); }
});

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

const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
loader.load(
  MODEL_URL,
  (gltf: GLTF) => {
    model = gltf.scene;
    model.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh) return;
      m.castShadow = true; m.receiveShadow = true; m.frustumCulled = false;
      // clear lenses as in the photos: a faint reflection, no frosted look
      for (const mt of Array.isArray(m.material) ? m.material : [m.material]) {
        // (the same for the corneas: a transmissive cornea blurs the iris
        // behind it, or shows the white background at grazing angles)
        if (mt.name === 'M_GlassesLens' || mt.name === 'M_Cornea') {
          const g = mt as THREE.MeshPhysicalMaterial;
          g.transmission = 0; g.transparent = true; g.opacity = mt.name === 'M_Cornea' ? 0.05 : 0.08; g.roughness = 0.04;
          g.envMapIntensity = 0.5; g.color.set(0xffffff); g.depthWrite = false; g.needsUpdate = true;
          m.renderOrder = 2;
        }
      }
    });
    scene.add(model);
    for (const [g, names] of Object.entries(GROUPS)) {
      groupObjects[g] = names.map((n) => model!.getObjectByName(n)).filter((x): x is THREE.Object3D => !!x);
      groupState[g] = g !== 'Laptop';
    }
    buildToggles();
    for (const g of Object.keys(GROUPS)) setGroup(g, groupState[g]);
    eyeBones = ['eyeL', 'eyeR', 'eye.L', 'eye.R'].map((n) => model!.getObjectByName(n)).filter((x): x is THREE.Object3D => !!x);
    feet = ['foot.L', 'foot.R'].map((n) => model!.getObjectByName(n)).filter((x): x is THREE.Object3D => !!x);
    headBone = model.getObjectByName('head') ?? null;
    model.updateMatrixWorld(true);
    if (headBone) headRestInv.copy(headBone.getWorldQuaternion(_q)).invert();
    captureEyeBase();
    clips = gltf.animations;
    mixer = new THREE.AnimationMixer(model);
    const sel = document.getElementById('anim') as HTMLSelectElement;
    sel.innerHTML = '';
    const order = ['Pose_Neutral', 'Pose_Hero', 'Idle', 'Walk', 'Run', 'Wave'];
    const names = clips.map((c) => c.name).filter((n) => !n.startsWith('Ref_')).sort((a, b) => (order.indexOf(a) + 99 * +(order.indexOf(a) < 0)) - (order.indexOf(b) + 99 * +(order.indexOf(b) < 0)));
    for (const n of names) {
      const opt = document.createElement('option');
      opt.value = n;
      opt.textContent = ANIM_LABELS[n] ?? n;
      sel.append(opt);
    }
    if (names.includes('Pose_Neutral')) { sel.value = 'Pose_Neutral'; playClip('Pose_Neutral', false); }
    setView(currentView, false);
    const s = countStats(model);
    document.getElementById('stats')!.textContent =
      `${s.tris.toLocaleString('es-MX')} triángulos · ${s.meshes} mallas · ${s.mats} materiales · ${clips.length} animaciones`;
    statusEl.classList.add('hidden');
    // the photo-captured shading (falls back to the physical one if missing)
    loadLook().then(({ info, tex }) => {
      model!.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        for (const mt of Array.isArray(m.material) ? m.material : [m.material]) applyReferenceLook(mt, tex, info);
      });
      lookReady = true;
      setShading(params.get('shading') === 'pbr' ? 'pbr' : 'ref');
    }).catch((e) => { console.warn('look not available', e); setShading('pbr'); })
      .finally(() => {
        invalidate(6);
        (window as unknown as { __morfiReady: boolean }).__morfiReady = true;
      });
    (window as unknown as { __morfiModel: THREE.Object3D }).__morfiModel = model;
  },
  (ev) => {
    if (ev.lengthComputable) progressEl.textContent = Math.round((ev.loaded / ev.total) * 100) + '%';
  },
  (err) => {
    statusEl.classList.add('error');
    statusEl.textContent = 'No se pudo cargar el modelo (' + MODEL_URL + '). ' + String((err as Error)?.message ?? err);
    console.error(err);
  },
);

// ------------------------------------------------------------------ UI wiring
const ROUND = 10; // correction round of the model shown (docs/art-direction.md)
document.getElementById('build-info')!.textContent = `Ronda ${ROUND} · versión ${__BUILD_INFO__.commit} · ${__BUILD_INFO__.date}`;
document.querySelectorAll<HTMLButtonElement>('#views button').forEach((b) => b.addEventListener('click', () => setView(b.dataset.view!)));
document.getElementById('reset')!.addEventListener('click', () => setView('front'));
(document.getElementById('autorotate') as HTMLInputElement).addEventListener('change', (e) => {
  controls.autoRotate = (e.target as HTMLInputElement).checked;
  if (controls.autoRotate) { aligned = false; updateCompare(); }
  sfx.toggle(controls.autoRotate);
});
(document.getElementById('eyes') as HTMLInputElement).addEventListener('change', (e) => {
  eyesFollow = (e.target as HTMLInputElement).checked;
  sfx.toggle(eyesFollow);
  invalidate(3);
});
(document.getElementById('lightsFollow') as HTMLInputElement).addEventListener('change', (e) => {
  lightsFollow = (e.target as HTMLInputElement).checked;
  sfx.toggle(lightsFollow);
  invalidate(3);
});
(document.getElementById('anim') as HTMLSelectElement).addEventListener('change', (e) => playClip((e.target as HTMLSelectElement).value));
document.getElementById('play')!.addEventListener('click', (e) => {
  playing = !playing;
  if (action) action.paused = !playing;
  (e.target as HTMLButtonElement).textContent = playing ? 'Pausa' : 'Reproducir';
  sfx.click();
});
const speed = document.getElementById('speed') as HTMLInputElement;
speed.addEventListener('input', () => {
  if (mixer) mixer.timeScale = parseFloat(speed.value);
  document.getElementById('speed-val')!.textContent = speed.value + '×';
});
document.getElementById('preset-full')!.addEventListener('click', () => {
  for (const g of Object.keys(GROUPS)) setGroup(g, g !== 'Laptop' || (action?.getClip().name === 'Pose_Hero'));
  sfx.click();
});
document.getElementById('preset-base')!.addEventListener('click', () => {
  for (const g of Object.keys(GROUPS)) setGroup(g, false);
  sfx.click();
});
document.querySelectorAll<HTMLButtonElement>('#bgs button').forEach((b) => b.addEventListener('click', () => { setBackground(b.dataset.bg!); sfx.click(); }));
document.querySelectorAll<HTMLButtonElement>('#modes button').forEach((b) => b.addEventListener('click', () => { setMode(b.dataset.mode!); sfx.click(); }));
document.querySelectorAll<HTMLButtonElement>('#shading button').forEach((b) => b.addEventListener('click', () => { setShading(b.dataset.shading as 'ref' | 'pbr'); sfx.click(); }));
document.querySelectorAll<HTMLButtonElement>('#compare-modes button').forEach((b) => b.addEventListener('click', () => { setCompare(b.dataset.cmp as CompareMode); sfx.click(); }));
(document.getElementById('cmp-amount') as HTMLInputElement).addEventListener('input', updateCompare);
(document.getElementById('sound') as HTMLInputElement).addEventListener('change', (e) => {
  const on = (e.target as HTMLInputElement).checked;
  setSfxEnabled(on);
  if (on) { unlockAudio(); sfx.toggle(true); }
  (document.getElementById('music') as HTMLInputElement).disabled = !on;
});
(document.getElementById('music') as HTMLInputElement).addEventListener('change', (e) => setMusic((e.target as HTMLInputElement).checked));
(document.getElementById('volume') as HTMLInputElement).addEventListener('input', (e) => setVolume(parseFloat((e.target as HTMLInputElement).value)));
window.addEventListener('keydown', unlockAudio, { once: true });
controls.addEventListener('start', () => {
  if (aligned) { aligned = false; updateCompare(); }
});
document.getElementById('shot')!.addEventListener('click', () => {
  // render once at the reference image size (1145x1374) so a shot taken from a
  // reference view is framed exactly like that reference
  const bg = app.className.split(' ').find((c) => c.startsWith('bg-'))?.replace('bg-', '');
  const prev = renderer.getClearAlpha();
  if (bg === 'light') renderer.setClearColor(0xfdfdf9, 1);
  if (bg === 'dark') renderer.setClearColor(0x14161c, 1);
  aimEyes();
  turnLights();
  const size = renderer.getSize(new THREE.Vector2());
  const pr = renderer.getPixelRatio();
  const [aspect, fov] = [camera.aspect, camera.fov];
  renderer.setPixelRatio(1);
  renderer.setSize(REF_W, REF_H, false);
  camera.aspect = REF_W / REF_H;
  camera.fov = lensFov;
  camera.updateProjectionMatrix();
  renderer.render(scene, camera);
  unaimEyes();
  const url = renderer.domElement.toDataURL('image/png');
  renderer.setPixelRatio(pr);
  renderer.setSize(size.x, size.y, false);
  camera.aspect = aspect;
  camera.fov = fov;
  camera.updateProjectionMatrix();
  renderer.setClearColor(0x000000, prev);
  sfx.shutter();
  const a = document.createElement('a');
  a.href = url;
  a.download = `morfi_${currentView}_${Date.now()}.png`;
  a.click();
});
const panel = document.getElementById('panel')!;
const ptoggle = document.getElementById('panel-toggle')!;
ptoggle.addEventListener('click', () => {
  const collapsed = panel.classList.toggle('collapsed');
  ptoggle.setAttribute('aria-expanded', String(!collapsed));
  sfx.click();
  window.setTimeout(resize, 0);
});
if (window.matchMedia('(max-width: 720px)').matches) panel.classList.add('collapsed');
(document.getElementById('download') as HTMLAnchorElement).href = MODEL_URL;

// ------------------------------------------------------------------ layout
// Normal: the canvas fills the window. Comparing: the canvas becomes a box
// with the reference photo's aspect (and the reference camera's exact lens),
// with the photo over it, beside it or as a wipe / difference.
function resize() {
  const comparing = app.classList.contains('comparing');
  let w = window.innerWidth, h = window.innerHeight;
  if (comparing) {
    const panelW = panel.classList.contains('collapsed') || window.innerWidth <= 720 ? 0 : panel.getBoundingClientRect().width + 32;
    const availW = Math.max(200, window.innerWidth - panelW - 32), availH = Math.max(200, window.innerHeight - 32);
    const n = compare === 'side' ? 2 : 1;
    const s = Math.min(availW / (n * REF_W + (n - 1) * 12), availH / REF_H);
    w = Math.round(REF_W * s); h = Math.round(REF_H * s);
    stage.style.width = `${w * n + (n - 1) * 12}px`;
    stage.style.height = `${h}px`;
    stage.style.left = `${16 + (availW - (w * n + (n - 1) * 12)) / 2}px`;
    stage.style.top = `${16 + (availH - h) / 2}px`;
    stage.style.setProperty('--cw', `${w}px`);
  } else {
    stage.removeAttribute('style');
  }
  renderer.setSize(w, h, false);
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  camera.aspect = w / h;
  const fit = !comparing && !EXACT && w / h < 0.85 ? 1.25 : 1.0;
  camera.fov = lensFov * fit;
  camera.updateProjectionMatrix();
  invalidate(3);
}
window.addEventListener('resize', resize);
resize();
setView('front', false);
setBackground('light');

// ------------------------------------------------------------------ loop (render on demand)
const clock = new THREE.Clock();
export function invalidate(frames = 3) { dirtyFrames = Math.max(dirtyFrames, frames); }
controls.addEventListener('change', () => invalidate(2));
panel.addEventListener('click', () => invalidate(6));
panel.addEventListener('change', () => invalidate(6));
renderer.setAnimationLoop(() => {
  const dt = clock.getDelta();
  const animating = !!(mixer && action && !action.paused && action.isRunning() && !action.getClip().name.startsWith('Pose_') && !action.getClip().name.startsWith('Ref_'));
  if (mixer && (animating || dirtyFrames > 0)) { mixer.update(animating ? dt : 0); captureEyeBase(); }
  const moving = controls.update() || controls.autoRotate;
  bounce(dt);
  if (updateShot(dt)) invalidate(2);
  if (animating || moving || dirtyFrames > 0 || bounceT >= 0) {
    if (aligned && rollRad) { camera.rotateZ(rollRad); camera.updateMatrixWorld(); }
    aimEyes();
    turnLights();
    if (animating) footsteps();
    if (model && ground.visible && (animating || dirtyFrames > 0 || bounceT >= 0)) {
      model.getWorldPosition(_centre);
      contact.update(renderer, scene, _centre);
    }
    renderer.render(scene, camera);
    unaimEyes();
    if (dirtyFrames > 0) dirtyFrames--;
  }
});
(window as unknown as { __morfiInvalidate: () => void }).__morfiInvalidate = () => invalidate(4);
(window as unknown as { __morfiSetView: (v: string) => void }).__morfiSetView = (v: string) => setView(v, false);
// tests: hold an animation at a given time (seconds) and orbit the camera
(window as unknown as { __morfiPose: (clip: string, t: number) => void }).__morfiPose = (clip: string, t: number) => {
  playClip(clip, false);
  if (action && mixer) { action.paused = true; action.time = t; mixer.update(0); captureEyeBase(); }
  invalidate(6);
};
(window as unknown as { __morfiOrbit: (az: number, el: number, dist: number) => void }).__morfiOrbit = (az: number, el: number, dist: number) => {
  aligned = false;
  const a = (az * Math.PI) / 180, e = (el * Math.PI) / 180;
  camera.position.set(controls.target.x + dist * Math.cos(e) * Math.sin(a), controls.target.y + dist * Math.sin(e), controls.target.z + dist * Math.cos(e) * Math.cos(a));
  camera.lookAt(controls.target);
  controls.update();
  invalidate(6);
};
(window as unknown as { __morfiEyes: () => number[][] }).__morfiEyes = () => eyeBones.map((b) => b.quaternion.toArray().map((x) => +x.toFixed(4)));
