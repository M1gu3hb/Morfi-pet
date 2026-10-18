// Ink contour ("contorno"): the same 3D Morfi with a thin line only on his silhouettes,
// stronger on the glasses. An inverted hull per mesh: a child that shares the geometry
// (and the skeleton and the face morphs), drawn with back faces only and pushed out in
// screen space along a smoothed normal, so the line has the same width in pixels at any
// zoom (a little thinner far away) and never cracks at the UV seams. The hulls skin and
// smear exactly like the colour pass, so the line follows every clip and the smear.
import * as THREE from 'three';
import { useDualQuatSkinning } from '../dqskin';
import { OUTLINE_NORMAL_ATTRIBUTE, useSmear, type RigidSmear } from './fx_smear';

/** Shared by every hull material. */
export const outlineUniforms = {
  /** line width in device pixels (CSS px x pixel ratio) */
  olWidth: { value: 1.6 },
  /** drawing buffer size (device pixels) */
  olRes: { value: new THREE.Vector2(1, 1) },
  /** 0..1: how much the line thins with distance */
  olThin: { value: 0.5 },
  /** camera distance (m) where the line has its full width */
  olRefDist: { value: 3.3 },
  /** the hull is pushed this far away from the camera (m): no ink poking through creases */
  olBias: { value: 0.012 },
};

const OUTLINE_PARS = /* glsl */ `
${OUTLINE_NORMAL_ATTRIBUTE}
uniform float olWidth;
uniform vec2 olRes;
uniform float olThin;
uniform float olRefDist;
uniform float olBias;
uniform float olScale;
`;

const OUTLINE_VERTEX = /* glsl */ `
#include <project_vertex>
{
  #ifdef USE_SKINNING
  vec3 olN = dqSkinNormal( dqR, dqS0, dqS1, dqS2, outlineNormal );
  #else
  vec3 olN = outlineNormal;
  #endif
  vec3 olView = normalize( normalMatrix * olN );
  float olDist = max( - mvPosition.z, 1e-3 );
  mvPosition.xyz += normalize( mvPosition.xyz ) * olBias;
  gl_Position = projectionMatrix * mvPosition;
  // the normal's direction on screen, in pixels
  vec2 olDir = ( projectionMatrix * vec4( olView, 0.0 ) ).xy * olRes;
  float olLen = length( olDir );
  olDir = olLen > 1e-6 ? olDir / olLen : vec2( 0.0 );
  float olK = mix( 1.0, clamp( olRefDist / olDist, 0.35, 1.0 ), olThin );
  gl_Position.xy += olDir * ( olWidth * olScale * olK * 2.0 / olRes ) * gl_Position.w;
}
`;

function hullMaterial(scale: { value: number }, rigid: RigidSmear | undefined, skinned: boolean): THREE.MeshBasicMaterial {
  const mat = new THREE.MeshBasicMaterial({ color: 0x0d1220, side: THREE.BackSide, toneMapped: false, fog: false });
  mat.name = 'Outline';
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, outlineUniforms, { olScale: scale });
    shader.vertexShader = shader.vertexShader
      .replace('void main() {', OUTLINE_PARS + '\nvoid main() {')
      .replace('#include <project_vertex>', OUTLINE_VERTEX);
  };
  mat.customProgramCacheKey = () => 'outline';
  // the same deformation as the colour pass: skinning first, then the smear (chained in that order)
  if (skinned) useDualQuatSkinning(mat);
  useSmear(mat, rigid);
  return mat;
}

/** Integer key of every vertex position (0.1 mm grid, one number: 16 bits per axis), computed once. */
function positionKeys(pos: Float32Array): Float64Array {
  const keys = new Float64Array(pos.length / 3);
  const q = (x: number) => Math.min(65535, Math.max(0, Math.round(x * 1e4) + 32768));
  for (let i = 0; i < keys.length; i++) keys[i] = (q(pos[i * 3]) * 65536 + q(pos[i * 3 + 1])) * 65536 + q(pos[i * 3 + 2]);
  return keys;
}

/** An attribute's x, y, z as plain floats (decoded once: quantised attributes are normalised by getX). */
function floats(a: THREE.BufferAttribute | THREE.InterleavedBufferAttribute): Float32Array {
  const out = new Float32Array(a.count * 3);
  for (let i = 0; i < a.count; i++) { out[i * 3] = a.getX(i); out[i * 3 + 1] = a.getY(i); out[i * 3 + 2] = a.getZ(i); }
  return out;
}

/** Connected pieces of a geometry (by triangles, through vertices at the same position) and
 *  whether each one is inside out: normals and winding pointing in (the hands and the props
 *  are; they look right because their materials are double sided). Returns per vertex +1 / -1. */
function orientation(g: THREE.BufferGeometry, p: Float32Array, keys: Float64Array): Int8Array {
  const n = keys.length;
  const sign = new Int8Array(n).fill(1);
  const index = g.getIndex();
  if (!index) return sign;
  const idx = index.array;
  const first = new Map<number, number>();
  const merged = new Int32Array(n);                 // vertices at the same position -> one id
  for (let i = 0; i < n; i++) {
    const f = first.get(keys[i]);
    if (f === undefined) first.set(keys[i], i);
    merged[i] = f ?? i;
  }
  const parent = merged.slice();
  const find = (x: number) => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
  const tris = index.count / 3;
  const edges = new Float64Array(tris * 3);        // edge ids (smaller * n + larger), sorted below to count their uses
  for (let t = 0, e = 0; t < index.count; t += 3) {
    const a = merged[idx[t]], b = merged[idx[t + 1]], c = merged[idx[t + 2]];
    edges[e++] = Math.min(a, b) * n + Math.max(a, b);
    edges[e++] = Math.min(b, c) * n + Math.max(b, c);
    edges[e++] = Math.min(c, a) * n + Math.max(c, a);
    const ra = find(a);
    parent[find(b)] = ra;
    parent[find(c)] = ra;
  }
  edges.sort();
  // only closed pieces have an inside: an open patch (a decal, a sleeve end) keeps its normals
  const edgeCount = new Float64Array(n), openCount = new Float64Array(n);   // per piece root: edges, edges used once
  for (let i = 0; i < edges.length;) {
    let j = i + 1;
    while (j < edges.length && edges[j] === edges[i]) j++;
    const r = find(Math.floor(edges[i] / n));
    edgeCount[r]++;
    if (j - i === 1) openCount[r]++;
    i = j;
  }
  // signed volume of each piece, about its own centre (sum of tetrahedra on its triangles)
  const cx = new Float64Array(n), cy = new Float64Array(n), cz = new Float64Array(n), cn = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const r = find(i);
    cx[r] += p[i * 3]; cy[r] += p[i * 3 + 1]; cz[r] += p[i * 3 + 2]; cn[r]++;
  }
  const volume = new Float64Array(n);
  for (let t = 0; t < index.count; t += 3) {
    const i0 = idx[t], i1 = idx[t + 1], i2 = idx[t + 2];
    const r = find(i0), mx = cx[r] / cn[r], my = cy[r] / cn[r], mz = cz[r] / cn[r];
    const ax = p[i0 * 3] - mx, ay = p[i0 * 3 + 1] - my, az = p[i0 * 3 + 2] - mz;
    const bx = p[i1 * 3] - mx, by = p[i1 * 3 + 1] - my, bz = p[i1 * 3 + 2] - mz;
    const dx = p[i2 * 3] - mx, dy = p[i2 * 3 + 1] - my, dz = p[i2 * 3 + 2] - mz;
    volume[r] += ax * (by * dz - bz * dy) - ay * (bx * dz - bz * dx) + az * (bx * dy - by * dx);
  }
  for (let i = 0; i < n; i++) {
    const r = find(i);
    if (volume[r] < 0 && edgeCount[r] > 0 && openCount[r] <= edgeCount[r] * 0.02) sign[i] = -1;
  }
  return sign;
}

/** Average of the normals at the same position (over the geometries of one mesh, which share
 *  its space), pointing out of the surface, as the attribute outlineNormal: split vertices at
 *  seams get one direction. Inside-out pieces also get their triangles turned for the hull
 *  (userData.outlineIndex). */
export function smoothNormals(geometries: THREE.BufferGeometry[]): void {
  const todo = geometries.filter((g) => !g.getAttribute('outlineNormal') && g.getAttribute('normal'));
  const slot = new Map<number, number>();           // position key -> slot of its normal sum
  const pos = todo.map((g) => floats(g.getAttribute('position')));
  const keys = pos.map(positionKeys);
  const signs = todo.map((g, j) => orientation(g, pos[j], keys[j]));
  const nor = todo.map((g) => floats(g.getAttribute('normal')));
  const ids = keys.map((ks) => {
    const out = new Int32Array(ks.length);
    for (let i = 0; i < ks.length; i++) {
      let id = slot.get(ks[i]);
      if (id === undefined) slot.set(ks[i], (id = slot.size));
      out[i] = id;
    }
    return out;
  });
  const sums = new Float64Array(slot.size * 3);
  todo.forEach((g, j) => {
    const n = nor[j], sg = signs[j], id = ids[j];
    for (let i = 0; i < id.length; i++) {
      sums[id[i] * 3] += n[i * 3] * sg[i]; sums[id[i] * 3 + 1] += n[i * 3 + 1] * sg[i]; sums[id[i] * 3 + 2] += n[i * 3 + 2] * sg[i];
    }
  });
  todo.forEach((g, j) => {
    const n = nor[j], sg = signs[j], id = ids[j];
    const out = new Int16Array(id.length * 3);
    for (let i = 0; i < id.length; i++) {
      let x = sums[id[i] * 3], y = sums[id[i] * 3 + 1], z = sums[id[i] * 3 + 2];
      let l = Math.hypot(x, y, z);
      if (l < 1e-6) { x = n[i * 3] * sg[i]; y = n[i * 3 + 1] * sg[i]; z = n[i * 3 + 2] * sg[i]; l = Math.hypot(x, y, z) || 1; }
      out[i * 3] = Math.round((x / l) * 32767);
      out[i * 3 + 1] = Math.round((y / l) * 32767);
      out[i * 3 + 2] = Math.round((z / l) * 32767);
    }
    g.setAttribute('outlineNormal', new THREE.BufferAttribute(out, 3, true));
    const index = g.getIndex();
    if (index && sg.some((x) => x < 0)) {
      const tri = index.array.slice();
      for (let t = 0; t < tri.length; t += 3) {
        if (sg[tri[t]] < 0) { const b = tri[t + 1]; tri[t + 1] = tri[t + 2]; tri[t + 2] = b; }
      }
      g.userData.outlineIndex = new THREE.BufferAttribute(tri, 1);
    }
  });
}

/** The hull's geometry: the same attributes (same GPU buffers), its own turned index if needed. */
function hullGeometry(src: THREE.BufferGeometry): THREE.BufferGeometry {
  const index = src.userData.outlineIndex as THREE.BufferAttribute | undefined;
  if (!index) return src;
  const g = new THREE.BufferGeometry();
  for (const [name, a] of Object.entries(src.attributes)) g.setAttribute(name, a);
  g.morphAttributes = src.morphAttributes;
  g.morphTargetsRelative = src.morphTargetsRelative;
  g.setIndex(index);
  g.boundingBox = src.boundingBox;
  g.boundingSphere = src.boundingSphere;
  return g;
}

export interface OutlineTarget {
  mesh: THREE.Mesh;
  glasses: boolean;
  /** the rigid smear of that mesh (its hull moves with it), if it has one */
  rigid?: RigidSmear;
}

export class Outline {
  readonly hulls: THREE.Mesh[] = [];
  readonly materials: THREE.MeshBasicMaterial[] = [];
  readonly bodyScale = { value: 1 };
  readonly glassesScale = { value: 1.8 };
  private shared = new Map<string, THREE.MeshBasicMaterial>();

  constructor(targets: OutlineTarget[]) {
    for (const t of targets) this.add(t);
  }

  private add({ mesh, glasses, rigid }: OutlineTarget): void {
    const skinned = (mesh as THREE.SkinnedMesh).isSkinnedMesh === true;
    const scale = glasses ? this.glassesScale : this.bodyScale;
    // skinned hulls share a material per width; rigid ones carry their mesh's smear uniforms
    let mat: THREE.MeshBasicMaterial | undefined;
    const key = (glasses ? 'g' : 'b') + (skinned ? 's' : 'r');
    if (!rigid) mat = this.shared.get(key);
    if (!mat) {
      mat = hullMaterial(scale, rigid, skinned);
      this.materials.push(mat);
      if (!rigid) this.shared.set(key, mat);
    }
    let hull: THREE.Mesh;
    if (skinned) {
      const src = mesh as THREE.SkinnedMesh;
      const sk = new THREE.SkinnedMesh(hullGeometry(src.geometry), mat);
      sk.bind(src.skeleton, src.bindMatrix);
      hull = sk;
    } else {
      hull = new THREE.Mesh(hullGeometry(mesh.geometry), mat);
    }
    // the face morphs (brows, cheeks, jaw) move the hull too
    if (mesh.morphTargetInfluences) {
      hull.morphTargetInfluences = mesh.morphTargetInfluences;
      hull.morphTargetDictionary = mesh.morphTargetDictionary;
    }
    hull.name = mesh.name + '_outline';
    hull.userData.outline = true;
    hull.castShadow = false;
    hull.receiveShadow = false;
    hull.frustumCulled = false;
    hull.renderOrder = 0.5;                       // after the body, before the decals (1) and lenses (2)
    hull.raycast = () => {};                      // tap-to-poke hits Morfi, not his contour
    mesh.add(hull);
    this.hulls.push(hull);
  }

  setVisible(on: boolean): void {
    for (const h of this.hulls) h.visible = on;
  }

  setInk(intensity: number): void {
    // gray to near-black ink
    const c = new THREE.Color(0x7d8698).lerp(new THREE.Color(0x0d1220), THREE.MathUtils.clamp(intensity, 0, 1));
    for (const m of this.materials) m.color.copy(c);
  }
}
