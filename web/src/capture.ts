// Capture of the reference look (dev only: run by scripts/capture-look.mjs).
// For every calibrated reference shot: render the viewer's GLB with that shot's
// camera and pose into float targets (albedo, view-space normal, material id),
// compare with the photo pixel by pixel and accumulate, per material, the
// log2 ratio photo / albedo in a matcap grid indexed by the view-space normal.
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { setShotMorph } from './look';

const W = 1145, H = 1374, N = 64;
const VIEWS = ['front', 'profile_left', 'back', 'profile_right', 'three_quarter_front', 'three_quarter_back'];
// colour class each material should show in the photo (prep_web_refs.py):
// 1 blue skin, 2 celeste, 3 black / navy, 4 white / grey; 0 = any figure class
const EXPECT: Record<string, number[]> = {
  M_Skin: [1], M_Head: [1, 2], M_Brow: [3], M_Hoodie: [3], M_HoodieHem: [3], M_HoodieRib: [3], M_Cord: [3],
  M_GlassesFrame: [3], M_Tshirt: [4], M_ShoeLeather: [4], M_ShoeSole: [4], M_ShoeStrap: [4], M_ShoeBlue: [1],
  M_Eye: [4, 3, 1, 2], M_TshirtLogo: [1, 2], M_Metal: [4, 3],
};
const SKIP = new Set(['M_GlassesLens', 'M_Cornea', 'M_EyeHighlight', 'M_Laptop', 'M_LaptopLogo']);

const srgbToLin = new Float32Array(256).map((_, i) => {
  const c = i / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
});

async function imageData(url: string) {
  const img = new Image();
  img.src = url;
  await img.decode();
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  const g = c.getContext('2d')!;
  g.drawImage(img, 0, 0);
  return g.getImageData(0, 0, c.width, c.height).data;
}

async function main() {
  const log = (s: string) => { console.log(s); document.body.append(s + '\n'); };
  const p = new URLSearchParams(location.search);
  const refRoot = p.get('refs') ?? '';
  const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true });
  renderer.setSize(W, H, false);
  const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(p.get('model') ?? './models/morfi_web.glb');
  const scene = new THREE.Scene();
  const model = gltf.scene;
  scene.add(model);
  const views = await (await fetch('./models/views.json')).json();
  const mixer = new THREE.AnimationMixer(model);

  // material ids and per-pass override materials
  const names: string[] = [];
  const meshes: THREE.Mesh[] = [];
  model.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    meshes.push(m);
    for (const mt of Array.isArray(m.material) ? m.material : [m.material]) if (!names.includes(mt.name)) names.push(mt.name);
  });
  const orig = new Map(meshes.map((m) => [m, m.material]));
  // clear / emissive / absent parts (lens, cornea, highlight, laptop) are left
  // out of the passes: the photo shows what is behind the lens and the cornea
  for (const m of meshes) {
    const mats = Array.isArray(m.material) ? m.material : [m.material];
    if (mats.every((x) => SKIP.has(x.name))) m.visible = false;
  }
  const over = (kind: 'albedo' | 'normal' | 'id') => (src: THREE.Material) => {
    const s = src as THREE.MeshStandardMaterial;
    const id = names.indexOf(s.name) + 1;
    if (kind === 'albedo') return new THREE.MeshBasicMaterial({ map: s.map ?? null, color: s.color, side: s.side });
    if (kind === 'normal') return new THREE.MeshNormalMaterial({ normalMap: s.normalMap ?? null, normalScale: s.normalScale, side: s.side });
    return new THREE.MeshBasicMaterial({ color: new THREE.Color(SKIP.has(s.name) ? 0 : id / 255, 0, 0), side: s.side });
  };
  const sets = Object.fromEntries((['albedo', 'normal', 'id'] as const).map((k) => [k, new Map(meshes.map((m) => {
    const mats = Array.isArray(m.material) ? m.material : [m.material];
    const f = over(k);
    return [m, Array.isArray(m.material) ? mats.map(f) : f(mats[0])];
  }))]));
  const rt = new THREE.WebGLRenderTarget(W, H, { type: THREE.FloatType, depthBuffer: true });
  const buf = new Float32Array(W * H * 4);
  const camera = new THREE.PerspectiveCamera(30, W / H, 0.05, 50);
  const b2t = (v: number[]) => new THREE.Vector3(v[0], v[2], -v[1]);
  const pass = (k: 'albedo' | 'normal' | 'id') => {
    for (const m of meshes) m.material = sets[k].get(m)!;
    renderer.setRenderTarget(rt);
    renderer.setClearColor(0x000000, 0);
    renderer.clear();
    renderer.render(scene, camera);
    renderer.readRenderTargetPixels(rt, 0, 0, W, H, buf);
    renderer.setRenderTarget(null);
    return buf.slice();
  };

  // two-tone materials (the head: blue skin and celeste face) get one matcap per tone
  const acc = new Map<string, { sum: Float64Array; n: Float64Array }>();
  const accFor = (key: string) => {
    if (!acc.has(key)) acc.set(key, { sum: new Float64Array(N * N * 3), n: new Float64Array(N * N) });
    return acc.get(key)!;
  };
  const nb = new THREE.Vector3(), vd = new THREE.Vector3(), ax = new THREE.Vector3(), ay = new THREE.Vector3();
  for (const view of VIEWS) {
    const c = views.camera_views[view];
    if (!c) continue;
    // pose of that shot
    mixer.stopAllAction();
    const clip = gltf.animations.find((a) => a.name === 'Ref_' + view) ?? gltf.animations.find((a) => a.name === 'Pose_Neutral');
    if (clip) { mixer.clipAction(clip).play(); mixer.update(0); }
    setShotMorph(model, view, 1);
    model.updateMatrixWorld(true);
    // calibrated camera (Blender -> glTF axes), roll about the view axis
    const a = (c.az * Math.PI) / 180, t = c.target;
    camera.position.copy(b2t([t[0] + c.distance * Math.sin(a), t[1] - c.distance * Math.cos(a), c.height]));
    camera.up.set(0, 1, 0);
    camera.lookAt(b2t(t));
    camera.rotateZ(((c.roll ?? 0) * Math.PI) / 180);
    camera.fov = (2 * Math.atan(18 / c.lens) * 180) / Math.PI;
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    const alb = pass('albedo'), nor = pass('normal'), ids = pass('id');
    for (const m of meshes) m.material = orig.get(m)!;
    const ref = await imageData(refRoot + view + '.png');
    const cls = await imageData('./refs/' + view + '_cls.png');
    // stable pixels: same material and same photo class in a 7x7 window
    const idAt = new Int32Array(W * H), clAt = new Uint8Array(W * H);
    for (let j = 0; j < H; j++) for (let i = 0; i < W; i++) {
      const src = ((H - 1 - j) * W + i) * 4; // render targets are bottom-up
      idAt[j * W + i] = Math.round(ids[src] * 255);
      clAt[j * W + i] = cls[(j * W + i) * 4];
    }
    const unstable = new Uint8Array(W * H);
    const R = 3;
    for (let j = R; j < H - R; j++) for (let i = R; i < W - R; i++) {
      const k = j * W + i, id0 = idAt[k], c0 = clAt[k];
      if (!id0) continue;
      outer: for (let dj = -R; dj <= R; dj += R) for (let di = -R; di <= R; di += R) {
        const q = (j + dj) * W + (i + di);
        if (idAt[q] !== id0 || clAt[q] !== c0) { unstable[k] = 1; break outer; }
      }
    }
    const tanY = Math.tan(((camera.fov / 2) * Math.PI) / 180), tanX = tanY * camera.aspect;
    let used = 0;
    for (let j = R; j < H - R; j++) for (let i = R; i < W - R; i++) {
      const k = j * W + i, id = idAt[k];
      if (!id || unstable[k]) continue;
      const name = names[id - 1];
      if (SKIP.has(name)) continue;
      const src = ((H - 1 - j) * W + i) * 4;
      const ar = alb[src], ag = alb[src + 1], ab = alb[src + 2];
      // skin and head: which colour this texel is decides the expected class
      let want = EXPECT[name] ?? [1, 2, 3, 4];
      let key = name;
      if (name === 'M_Head' || name === 'M_TshirtLogo') {
        const cel = ar / Math.max(ab, 1e-4) > 0.12; // linear albedo: celeste ~0.27, skin blue ~0.02
        want = [cel ? 2 : 1];
        if (name === 'M_Head' && cel) key = 'M_Head#2';
      }
      if (!want.includes(clAt[k])) continue;
      const q = (j * W + i) * 4;
      const rr = srgbToLin[ref[q]], rg = srgbToLin[ref[q + 1]], rb = srgbToLin[ref[q + 2]];
      nb.set(nor[src] * 2 - 1, nor[src + 1] * 2 - 1, nor[src + 2] * 2 - 1).normalize();
      // direction from the surface to the camera, in view space
      vd.set(-(((i + 0.5) / W) * 2 - 1) * tanX, -(1 - ((j + 0.5) / H) * 2) * tanY, 1).normalize();
      ax.set(vd.z, 0, -vd.x).normalize();
      ay.crossVectors(vd, ax);
      const u = Math.min(N - 1, Math.max(0, Math.floor((ax.dot(nb) * 0.495 + 0.5) * N)));
      const v = Math.min(N - 1, Math.max(0, Math.floor((ay.dot(nb) * 0.495 + 0.5) * N)));
      const bin = v * N + u, e = 1e-4;
      const A = accFor(key);
      A.sum[bin * 3] += Math.log2(Math.max(rr, e) / Math.max(ar, e));
      A.sum[bin * 3 + 1] += Math.log2(Math.max(rg, e) / Math.max(ag, e));
      A.sum[bin * 3 + 2] += Math.log2(Math.max(rb, e) / Math.max(ab, e));
      A.n[bin] += 1;
      used++;
    }
    log(`${view}: ${used} pixels`);
  }
  const out: Record<string, { n: number[]; mean: number[] }> = {};
  acc.forEach((A, nm) => {
    const total = A.n.reduce((s, x) => s + x, 0);
    if (!total) return;
    out[nm] = { n: Array.from(A.n), mean: Array.from(A.sum, (s, i) => (A.n[Math.floor(i / 3)] ? s / A.n[Math.floor(i / 3)] : 0)) };
    log(`${nm}: ${total} samples`);
  });
  (window as unknown as { __capture: unknown }).__capture = { size: N, materials: out };
}

main().catch((e) => {
  console.error(e);
  (window as unknown as { __capture: unknown }).__capture = { error: String(e) };
});
