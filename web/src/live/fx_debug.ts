// Debug and test hooks for the render layers, loaded only with ?dqdebug (its own chunk):
// window.__morfiDQ.measure(clip, t) skins Morfi on the CPU with the exact math of the
// dqskin.ts shader (and the old uniform-scale one, and three's linear blend) to compare with
// Blender, and freeze(clip, t) holds a pose (with the 1/60 s before it as the previous
// frame, so the smear shows) for screenshots.
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { DQ_TEXELS, dualQuatData } from '../dqskin';
import type { StyleDebugHooks } from './style';
import { smearUniforms } from './fx_smear';
import { outlineUniforms } from './outline';

interface DebugOptions {
  model: THREE.Object3D;
  renderer: THREE.WebGLRenderer;
  camera: THREE.PerspectiveCamera;
  style: unknown;
  /** the rigid pieces' current matrices become their previous ones */
  capturePrev: () => void;
  squash: { sy: number; pivot: THREE.Object3D };
}

// only a same-origin ?model= (a link must not make the page load someone else's file)
const asked = new URLSearchParams(location.search).get('model');
const sameOrigin = (u: string) => { try { return new URL(u, location.href).origin === location.origin; } catch { return false; } };
const MODEL_URL = asked && sameOrigin(asked) ? asked : './models/morfi_live.glb';

function b64(a: Float32Array): string {
  const u = new Uint8Array(a.buffer, a.byteOffset, a.byteLength);
  let s = '';
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000));
  return btoa(s);
}

// --- CPU ports of the vertex shader ---------------------------------------------------
type V3 = [number, number, number];
type Q4 = [number, number, number, number];
const rot = (r: Q4, v: V3): V3 => {
  // v + 2 cross(r.xyz, cross(r.xyz, v) + r.w v)
  const cx = r[1] * v[2] - r[2] * v[1] + r[3] * v[0];
  const cy = r[2] * v[0] - r[0] * v[2] + r[3] * v[1];
  const cz = r[0] * v[1] - r[1] * v[0] + r[3] * v[2];
  return [v[0] + 2 * (r[1] * cz - r[2] * cy), v[1] + 2 * (r[2] * cx - r[0] * cz), v[2] + 2 * (r[0] * cy - r[1] * cx)];
};
const dqT = (r: Q4, d: Q4, p: V3): V3 => {
  const q = rot(r, p);
  // + 2 (r.w d.xyz - d.w r.xyz + cross(r.xyz, d.xyz))
  return [
    q[0] + 2 * (r[3] * d[0] - d[3] * r[0] + (r[1] * d[2] - r[2] * d[1])),
    q[1] + 2 * (r[3] * d[1] - d[3] * r[1] + (r[2] * d[0] - r[0] * d[2])),
    q[2] + 2 * (r[3] * d[2] - d[3] * r[2] + (r[0] * d[1] - r[1] * d[0])),
  ];
};

function blendDQ(rs: Q4[], ds: Q4[], w: number[]): { r: Q4; d: Q4 } {
  const r: Q4 = [0, 0, 0, 0], d: Q4 = [0, 0, 0, 0];
  for (let i = 0; i < 4; i++) {
    const dot = rs[0][0] * rs[i][0] + rs[0][1] * rs[i][1] + rs[0][2] * rs[i][2] + rs[0][3] * rs[i][3];
    const wi = w[i] * (i > 0 && dot < 0 ? -1 : 1);
    for (let k = 0; k < 4; k++) { r[k] += wi * rs[i][k]; d[k] += wi * ds[i][k]; }
  }
  const len = Math.max(Math.hypot(...r), 1e-6);
  for (let k = 0; k < 4; k++) { r[k] /= len; d[k] /= len; }
  return { r, d };
}

/** dqskin.ts shader, current frame, from the bone texture data (mesh space). */
function skinNew(data: Float32Array, idx: number[], w: number[], p: V3): V3 {
  const t = (b: number, k: number) => (b * DQ_TEXELS + k) * 4;
  const rs = idx.map((b) => Array.from(data.subarray(t(b, 0), t(b, 0) + 4)) as Q4);
  const ds = idx.map((b) => Array.from(data.subarray(t(b, 1), t(b, 1) + 4)) as Q4);
  const { r, d } = blendDQ(rs, ds, w);
  const ws = w.reduce((a, b) => a + b, 0) || 1e-6;
  const q: V3 = [0, 0, 0];
  for (let row = 0; row < 3; row++) {
    let acc = 0;
    for (let i = 0; i < 4; i++) {
      const o = t(idx[i], 2 + row);
      acc += (w[i] / ws) * (data[o] * p[0] + data[o + 1] * p[1] + data[o + 2] * p[2] + data[o + 3]);
    }
    q[row] = acc;
  }
  return dqT(r, d, q);
}

/** The previous dqskin.ts (rotation + one uniform scale per bone), for the "before" numbers. */
function skinOld(mesh: THREE.SkinnedMesh, idx: number[], w: number[], p: V3): V3 {
  const bm = mesh.skeleton.boneMatrices;
  const rs: Q4[] = [], ds: Q4[] = [], ss: number[] = [];
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), r3 = new THREE.Matrix4();
  for (const b of idx) {
    m.fromArray(bm, b * 16);
    m.premultiply(mesh.bindMatrixInverse).multiply(mesh.bindMatrix);
    const e = m.elements;
    const s = Math.hypot(e[0], e[1], e[2]);
    const c0 = new THREE.Vector3(e[0], e[1], e[2]).normalize(), c1 = new THREE.Vector3(e[4], e[5], e[6]).normalize();
    const c2 = new THREE.Vector3(e[8], e[9], e[10]).normalize();
    q.setFromRotationMatrix(r3.makeBasis(c0, c1, c2)).normalize();
    const r: Q4 = [q.x, q.y, q.z, q.w], tx = e[12], ty = e[13], tz = e[14];
    rs.push(r);
    ds.push([0.5 * (tx * r[3] + ty * r[2] - tz * r[1]), 0.5 * (ty * r[3] + tz * r[0] - tx * r[2]),
      0.5 * (tz * r[3] + tx * r[1] - ty * r[0]), -0.5 * (tx * r[0] + ty * r[1] + tz * r[2])]);
    ss.push(s);
  }
  const { r, d } = blendDQ(rs, ds, w);
  const ws = w.reduce((a, b) => a + b, 0) || 1e-6;
  const s = w.reduce((a, wi, i) => a + wi * ss[i], 0) / ws;
  return dqT(r, d, [p[0] * s, p[1] * s, p[2] * s]);
}

export function installDebug(o: DebugOptions): StyleDebugHooks {
  let clips: Promise<Map<string, THREE.AnimationClip>> | null = null;
  const loadClips = () => (clips ??= new Promise((res, rej) => {
    new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).load(MODEL_URL, (g) => res(new Map(g.animations.map((c) => [c.name, c]))), undefined, rej);
  }));
  const mixer = new THREE.AnimationMixer(o.model);
  let held: { clip: THREE.AnimationClip; t: number; velocity: boolean } | null = null;

  function pose(clip: THREE.AnimationClip, t: number): void {
    const a = mixer.clipAction(clip);
    if (!a.isRunning()) {
      mixer.stopAllAction();
      a.reset();
      a.setLoop(THREE.LoopOnce, 1);
      a.clampWhenFinished = true;
      a.play();
    }
    a.time = Math.min(t, clip.duration - 1e-4);
    a.enabled = true;
    a.setEffectiveWeight(1);
    mixer.update(0);
  }

  const skinnedMeshes = (): THREE.SkinnedMesh[] => {
    const out: THREE.SkinnedMesh[] = [];
    o.model.traverse((x) => { const m = x as THREE.SkinnedMesh; if (m.isSkinnedMesh && !m.userData.outline) out.push(m); });
    return out;
  };

  const api = {
    uniforms: { ...smearUniforms, ...outlineUniforms },
    camera: o.camera,
    squash: o.squash,
    clips: async () => [...(await loadClips()).keys()],
    /** hold a pose (null: back to the director); velocity: the 1/60 s before is the previous frame */
    async freeze(name: string | null, t = 0, velocity = true) {
      if (!name) { held = null; return true; }
      const clip = (await loadClips()).get(name);
      if (!clip) return false;
      held = { clip, t, velocity };
      return true;
    },
    /** model-space vertex positions: rest, new DQ (exact shader math), old DQ, three's linear blend */
    async measure(name: string, t: number) {
      const clip = (await loadClips()).get(name);
      if (!clip) throw new Error('no clip ' + name);
      pose(clip, t);
      o.model.updateMatrixWorld(true);
      const modelInv = o.model.matrixWorld.clone().invert();
      const meshes = skinnedMeshes();
      let checkError = 0;
      for (const sk of new Set(meshes.map((m) => m.skeleton))) {
        const dq = dualQuatData(sk)!;
        dq.check = true; dq.checkError = 0;
        sk.update();
        dq.check = false;
        checkError = Math.max(checkError, dq.checkError);
      }
      const out = [];
      const v = new THREE.Vector3(), m4 = new THREE.Matrix4();
      for (const mesh of meshes) {
        const g = mesh.geometry, P = g.getAttribute('position'), I = g.getAttribute('skinIndex'), W = g.getAttribute('skinWeight');
        const n = P.count, dq = dualQuatData(mesh.skeleton)!;
        const rest = new Float32Array(n * 3), now = new Float32Array(n * 3), old = new Float32Array(n * 3), lbs = new Float32Array(n * 3);
        const toModel = modelInv.clone().multiply(mesh.matrixWorld);
        const influences = mesh.morphTargetInfluences ? [...mesh.morphTargetInfluences] : null;
        mesh.morphTargetInfluences?.fill(0);
        for (let i = 0; i < n; i++) {
          const p: V3 = [P.getX(i), P.getY(i), P.getZ(i)];
          const idx = [I.getX(i), I.getY(i), I.getZ(i), I.getW(i)], w = [W.getX(i), W.getY(i), W.getZ(i), W.getW(i)];
          // rest: the bones as loaded (the glTF rest pose), linear blend is exact there
          const r = new THREE.Vector3();
          for (let k = 0; k < 4; k++) {
            if (!w[k]) continue;
            m4.multiplyMatrices(dq.restWorld[idx[k]], mesh.skeleton.boneInverses[idx[k]]).multiply(mesh.bindMatrix);
            r.addScaledVector(v.set(...p).applyMatrix4(m4), w[k]);
          }
          rest.set([r.x, r.y, r.z], i * 3);
          now.set(v.set(...skinNew(dq.data, idx, w, p)).applyMatrix4(toModel).toArray(), i * 3);
          old.set(v.set(...skinOld(mesh, idx, w, p)).applyMatrix4(toModel).toArray(), i * 3);
          mesh.getVertexPosition(i, v);
          lbs.set(v.applyMatrix4(toModel).toArray(), i * 3);
        }
        if (influences) mesh.morphTargetInfluences!.splice(0, influences.length, ...influences);
        const mat = mesh.material as THREE.Material;
        out.push({ name: mesh.name, material: mat.name, skeleton: mesh.skeleton.uuid, count: n,
          rest: b64(rest), now: b64(now), old: b64(old), lbs: b64(lbs) });
      }
      // the pose itself (model space), so Blender can deform its own mesh with exactly these bones
      const sk0 = meshes[0].skeleton, dq0 = dualQuatData(sk0)!;
      const bones = sk0.bones.map((b, i) => ({
        name: b.name, world: modelInv.clone().multiply(b.matrixWorld).toArray(), rest: dq0.restWorld[i].toArray(),
      }));
      return { checkError, meshes: out, bones };
    },
    /** world positions of some bones along a clip (tuning the squash) */
    async sample(name: string, bones: string[], fps = 60) {
      const clip = (await loadClips()).get(name);
      if (!clip) throw new Error('no clip ' + name);
      const res: Record<string, number[][]> = {};
      for (const b of bones) res[b] = [];
      const p = new THREE.Vector3();
      for (let t = 0; t <= clip.duration; t += 1 / fps) {
        pose(clip, t);
        o.model.updateMatrixWorld(true);
        for (const b of bones) res[b].push(o.model.getObjectByName(b)!.getWorldPosition(p).toArray());
      }
      return res;
    },
    dqCheck() {
      let e = 0;
      for (const sk of new Set(skinnedMeshes().map((m) => m.skeleton))) {
        const dq = dualQuatData(sk)!;
        dq.check = true; dq.checkError = 0;
        sk.update();
        dq.check = false;
        e = Math.max(e, dq.checkError);
      }
      return e;
    },
  };
  (window as unknown as { __morfiDQ: typeof api }).__morfiDQ = api;

  return {
    beforeFrame(): boolean {
      if (!held) return false;
      const { clip, t, velocity } = held;
      if (velocity) {
        // the previous frame: 1/60 s earlier, through the same path as a real frame
        pose(clip, Math.max(0, t - 1 / 60));
        o.model.updateMatrixWorld(true);
        for (const sk of new Set(skinnedMeshes().map((m) => m.skeleton))) sk.update();
        o.capturePrev();
      }
      pose(clip, t);
      return true;
    },
  };
}
