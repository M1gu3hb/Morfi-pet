// Dual quaternion skinning for three.js materials.
//
// Blender deforms the rig with "Preserve Volume" (dual quaternion skinning)
// and the skin weights were made for it. three.js only does linear blend
// skinning, which averages the bone matrices: where a joint bends a lot
// (a raised arm) the sleeve loses volume and stretches into a thin tube.
// This patch replaces the skinning chunks of any material by dual quaternion
// blending, so the viewer deforms like the Blender renders.
//
// Bones that squash and stretch (non-uniform scale: a squashed head, stretched
// arms) are split the way Blender's mat4_to_dquat does it: a rigid part (a unit
// dual quaternion, blended) and a scale part around the bone (a 3x4 matrix,
// blended linearly with the weights). Both are computed on the CPU per bone and
// frame and travel in the skeleton's bone texture, together with the previous
// frame (for motion effects) and a per-bone effect mask. skeleton.boneMatrices
// (CPU) stays three's, so raycasting keeps working.
import * as THREE from 'three';

/** Texels per bone in the bone texture (one row per bone): current frame (dual quaternion real,
 *  dual, 3 rows of the scale matrix), the previous frame (the same five), effect mask (x: smear). */
export const DQ_TEXELS = 11;
const PREV = 5;
const MASK = 10;

const PARS = /* glsl */ `
#ifdef USE_SKINNING
vec4 dqTexel( const in float bone, const in int k ) {
  return texelFetch( boneTexture, ivec2( k, int( bone ) ), 0 );
}
// blend the vertex's four bones for one frame (o = 0: current, 5: previous): a unit dual
// quaternion (r, d) applied after the scale rows s0..s2 (plain out vectors: no structs, which
// some GPU compilers get wrong when the function is called twice)
void dqBlend( const in int o, out vec4 r, out vec4 d, out vec4 s0, out vec4 s1, out vec4 s2 ) {
  vec4 r0 = dqTexel( skinIndex.x, o ), r1 = dqTexel( skinIndex.y, o );
  vec4 r2 = dqTexel( skinIndex.z, o ), r3 = dqTexel( skinIndex.w, o );
  // shortest path: every quaternion on the same side as the first
  vec4 w = skinWeight * vec4( 1.0, dot( r0, r1 ) < 0.0 ? -1.0 : 1.0, dot( r0, r2 ) < 0.0 ? -1.0 : 1.0, dot( r0, r3 ) < 0.0 ? -1.0 : 1.0 );
  r = w.x * r0 + w.y * r1 + w.z * r2 + w.w * r3;
  d = w.x * dqTexel( skinIndex.x, o + 1 ) + w.y * dqTexel( skinIndex.y, o + 1 )
    + w.z * dqTexel( skinIndex.z, o + 1 ) + w.w * dqTexel( skinIndex.w, o + 1 );
  float len = max( length( r ), 1e-6 );
  r /= len;
  d /= len;
  // the scale part blends linearly (Blender: weighted sum of the bones' scale matrices)
  vec4 ws = skinWeight / max( dot( skinWeight, vec4( 1.0 ) ), 1e-6 );
  s0 = ws.x * dqTexel( skinIndex.x, o + 2 ) + ws.y * dqTexel( skinIndex.y, o + 2 ) + ws.z * dqTexel( skinIndex.z, o + 2 ) + ws.w * dqTexel( skinIndex.w, o + 2 );
  s1 = ws.x * dqTexel( skinIndex.x, o + 3 ) + ws.y * dqTexel( skinIndex.y, o + 3 ) + ws.z * dqTexel( skinIndex.z, o + 3 ) + ws.w * dqTexel( skinIndex.w, o + 3 );
  s2 = ws.x * dqTexel( skinIndex.x, o + 4 ) + ws.y * dqTexel( skinIndex.y, o + 4 ) + ws.z * dqTexel( skinIndex.z, o + 4 ) + ws.w * dqTexel( skinIndex.w, o + 4 );
}
// per-bone effect mask (x: smear), blended with the weights
vec4 dqMask() {
  vec4 ws = skinWeight / max( dot( skinWeight, vec4( 1.0 ) ), 1e-6 );
  return ws.x * dqTexel( skinIndex.x, ${MASK} ) + ws.y * dqTexel( skinIndex.y, ${MASK} )
       + ws.z * dqTexel( skinIndex.z, ${MASK} ) + ws.w * dqTexel( skinIndex.w, ${MASK} );
}
vec3 dqScale( vec4 s0, vec4 s1, vec4 s2, vec3 p ) {
  vec4 h = vec4( p, 1.0 );
  return vec3( dot( s0, h ), dot( s1, h ), dot( s2, h ) );
}
vec3 dqRotate( vec4 r, vec3 v ) {
  return v + 2.0 * cross( r.xyz, cross( r.xyz, v ) + r.w * v );
}
vec3 dqTransform( vec4 r, vec4 d, vec3 p ) {
  return dqRotate( r, p ) + 2.0 * ( r.w * d.xyz - d.w * r.xyz + cross( r.xyz, d.xyz ) );
}
// normals go through the cofactor of the scale part (they stay perpendicular to a squashed surface)
vec3 dqSkinNormal( vec4 r, vec4 s0, vec4 s1, vec4 s2, vec3 n ) {
  vec3 m = vec3( dot( cross( s1.xyz, s2.xyz ), n ), dot( cross( s2.xyz, s0.xyz ), n ), dot( cross( s0.xyz, s1.xyz ), n ) );
  float l = length( m );
  return dqRotate( r, l > 1e-12 ? m / l : n );
}
#endif
`;

const BLEND = /* glsl */ `
#ifdef USE_SKINNING
  vec4 dqR, dqD, dqS0, dqS1, dqS2;
  dqBlend( 0, dqR, dqD, dqS0, dqS1, dqS2 );
#endif
`;

const NORMAL = /* glsl */ `
#ifdef USE_SKINNING
  objectNormal = dqSkinNormal( dqR, dqS0, dqS1, dqS2, objectNormal );
  #ifdef USE_TANGENT
  objectTangent = dqRotate( dqR, normalize( vec3( dot( dqS0.xyz, objectTangent ), dot( dqS1.xyz, objectTangent ), dot( dqS2.xyz, objectTangent ) ) ) );
  #endif
#endif
`;

const POSITION = /* glsl */ `
#ifdef USE_SKINNING
  vec3 dqRestPosition = transformed;   // morphed, not skinned yet (motion effects skin it with the previous frame)
  transformed = dqTransform( dqR, dqD, dqScale( dqS0, dqS1, dqS2, transformed ) );
#endif
`;

export function patchShader(shader: { vertexShader: string }) {
  shader.vertexShader = shader.vertexShader
    .replace('#include <skinning_pars_vertex>', '#include <skinning_pars_vertex>\n' + PARS)
    .replace('#include <skinbase_vertex>', BLEND)
    .replace('#include <skinnormal_vertex>', NORMAL)
    .replace('#include <skinning_vertex>', POSITION);
}

type DQMaterial = THREE.Material & { __dq?: boolean };

// Add the patch to a material, after whatever onBeforeCompile it already has
// (the reference look patches the fragment shader of the same materials).
export function useDualQuatSkinning(mat: THREE.Material) {
  const m = mat as DQMaterial;
  if (m.__dq) return;
  m.__dq = true;
  const prev = m.onBeforeCompile;
  m.onBeforeCompile = (shader, renderer) => {
    prev.call(m, shader, renderer);
    patchShader(shader);
  };
  const key = m.customProgramCacheKey.bind(m);
  m.customProgramCacheKey = () => key() + '|dq';
  // a skeleton nobody attached (the technical viewer) gets its data the first time it is drawn
  const before = m.onBeforeRender;
  m.onBeforeRender = (renderer, scene, camera, geometry, object, group) => {
    before.call(m, renderer, scene, camera, geometry, object, group);
    const sm = object as THREE.SkinnedMesh;
    if (sm.isSkinnedMesh && sm.skeleton && !skeletons.has(sm.skeleton)) attachSkeleton(sm.skeleton, sm).compute();
  };
  m.needsUpdate = true;
}

/** Mark a material whose onBeforeCompile already calls patchShader (contact.ts). */
export function markDualQuat(mat: THREE.Material) {
  (mat as DQMaterial).__dq = true;
}

// ------------------------------------------------------------------ per-skeleton data (CPU)
const _W = new THREE.Matrix4(), _Wr = new THREE.Matrix4(), _Ws = new THREE.Matrix4();
const _R = new THREE.Matrix4(), _S = new THREE.Matrix4(), _M = new THREE.Matrix4();
const _x = new THREE.Vector3(), _y = new THREE.Vector3(), _z = new THREE.Vector3(), _c = new THREE.Vector3();
const _q = new THREE.Quaternion();
const IDENTITY = new THREE.Matrix4();

/** Bone matrix in mesh space -> its rotation, keeping the bone's Y axis (Blender orthogonalize_m4(m, 1)),
 *  with the same translation. */
function orthogonalizeY(m: THREE.Matrix4, out: THREE.Matrix4): THREE.Matrix4 {
  const e = m.elements;
  _y.set(e[4], e[5], e[6]);
  if (_y.lengthSq() < 1e-20) _y.set(0, 1, 0);
  _y.normalize();
  _z.crossVectors(_c.set(e[0], e[1], e[2]), _y);
  if (_z.lengthSq() < 1e-20) {                     // X along the bone or zero (a hidden prop): any frame
    _c.set(Math.abs(_y.x) < 0.9 ? 1 : 0, Math.abs(_y.x) < 0.9 ? 0 : 1, 0);
    _z.crossVectors(_c, _y);
  }
  _z.normalize();
  _x.crossVectors(_y, _z);
  return out.makeBasis(_x, _y, _z).setPosition(e[12], e[13], e[14]);
}

class DQSkeleton {
  readonly data: Float32Array;
  readonly texture: THREE.DataTexture;
  /** per bone: X (rigid part of the bind-space inverse bind matrix), its inverse, and IBM * bindMatrix */
  private X: THREE.Matrix4[] = [];
  private Xinv: THREE.Matrix4[] = [];
  private IBM: THREE.Matrix4[] = [];
  /** bone positions in mesh space this frame and the last (jump detection) */
  private pos: Float32Array;
  private posPrev: Float32Array;
  private fresh = false;
  private snap = true;
  private maxStep = Infinity;
  /** bone world matrices at attach time (the rest pose of a freshly loaded glTF), for checks */
  readonly restWorld: THREE.Matrix4[];
  /** largest |R*S - bindMatrixInverse * boneMatrix * bindMatrix| seen while checking (debug) */
  checkError = 0;
  check = false;

  constructor(readonly skeleton: THREE.Skeleton, readonly mesh: THREE.SkinnedMesh) {
    const n = skeleton.bones.length;
    this.data = new Float32Array(DQ_TEXELS * n * 4);
    this.texture = new THREE.DataTexture(this.data, DQ_TEXELS, n, THREE.RGBAFormat, THREE.FloatType);
    this.texture.needsUpdate = true;
    this.pos = new Float32Array(n * 3);
    this.posPrev = new Float32Array(n * 3);
    this.restWorld = skeleton.bones.map((b) => (b ? b.matrixWorld.clone() : new THREE.Matrix4()));
    for (let i = 0; i < n; i++) {
      // the inverse bind matrix carries the mesh quantization (KHR_mesh_quantization folds the
      // dequantization into it): IBM * bindMatrix = X * uniform scale s, X rigid
      const ibm = skeleton.boneInverses[i].clone().multiply(mesh.bindMatrix);
      const e = ibm.elements;
      const s = Math.hypot(e[0], e[1], e[2]) || 1;
      const X = ibm.clone();
      for (const k of [0, 1, 2, 4, 5, 6, 8, 9, 10]) X.elements[k] /= s;
      this.IBM.push(ibm);
      this.X.push(X);
      this.Xinv.push(X.clone().invert());
    }
    for (let i = 0; i < n; i++) this.setMask(i, 1);
  }

  setMask(bone: number, smear: number): void {
    const o = (bone * DQ_TEXELS + MASK) * 4;
    this.data[o] = smear;
    this.texture.needsUpdate = true;
  }

  /** the current frame becomes the previous one (once per animation frame) */
  tick(jump: boolean, maxStep: number): void {
    if (!this.fresh || jump) { this.snap = true; return; }
    const d = this.data;
    for (let b = 0, n = this.skeleton.bones.length; b < n; b++) {
      const o = b * DQ_TEXELS * 4;
      d.copyWithin(o + PREV * 4, o, o + PREV * 4);
    }
    this.posPrev.set(this.pos);
    this.maxStep = maxStep;
    this.texture.needsUpdate = true;
  }

  /** current frame from the bones (three calls skeleton.update once per render() call) */
  compute(): void {
    const bones = this.skeleton.bones, d = this.data;
    const binv = this.mesh.bindMatrixInverse;
    let moved = 0;
    for (let i = 0, n = bones.length; i < n; i++) {
      const bone = bones[i];
      _W.multiplyMatrices(binv, bone ? bone.matrixWorld : IDENTITY);   // bone in mesh space
      orthogonalizeY(_W, _Wr);                                          // its rotation + translation
      _Ws.copy(_Wr).invert().multiply(_W);                              // what is left: scale/shear in the bone's frame
      _R.multiplyMatrices(_Wr, this.X[i]);                              // rigid part
      _S.multiplyMatrices(this.Xinv[i], _Ws).multiply(this.IBM[i]);     // scale part, in the rest mesh space
      _q.setFromRotationMatrix(_R);
      const r = _R.elements, s = _S.elements;
      const tx = r[12], ty = r[13], tz = r[14];
      const o = i * DQ_TEXELS * 4;
      d[o] = _q.x; d[o + 1] = _q.y; d[o + 2] = _q.z; d[o + 3] = _q.w;
      d[o + 4] = 0.5 * (tx * _q.w + ty * _q.z - tz * _q.y);
      d[o + 5] = 0.5 * (ty * _q.w + tz * _q.x - tx * _q.z);
      d[o + 6] = 0.5 * (tz * _q.w + tx * _q.y - ty * _q.x);
      d[o + 7] = -0.5 * (tx * _q.x + ty * _q.y + tz * _q.z);
      for (let row = 0; row < 3; row++) {
        const t = o + 8 + row * 4;
        d[t] = s[row]; d[t + 1] = s[4 + row]; d[t + 2] = s[8 + row]; d[t + 3] = s[12 + row];
      }
      const w = _W.elements, p = i * 3;
      this.pos[p] = w[12]; this.pos[p + 1] = w[13]; this.pos[p + 2] = w[14];
      if (this.maxStep < Infinity) {
        moved = Math.max(moved, Math.hypot(w[12] - this.posPrev[p], w[13] - this.posPrev[p + 1], w[14] - this.posPrev[p + 2]));
      }
      if (this.check) this.checkBone(i);
    }
    // a seek, a clip reset or a hidden tab: no velocity this frame
    if (moved > this.maxStep) this.snap = true;
    this.maxStep = Infinity;
    if (this.snap) {
      for (let b = 0, n = bones.length; b < n; b++) {
        const o = b * DQ_TEXELS * 4;
        d.copyWithin(o + PREV * 4, o, o + PREV * 4);
      }
      this.posPrev.set(this.pos);
      this.snap = false;
    }
    this.fresh = true;
    this.texture.needsUpdate = true;
  }

  private checkBone(i: number): void {
    _M.multiplyMatrices(this.mesh.bindMatrixInverse, this.skeleton.bones[i].matrixWorld)
      .multiply(this.skeleton.boneInverses[i]).multiply(this.mesh.bindMatrix);
    const rs = _R.clone().multiply(_S).elements, m = _M.elements;
    for (let k = 0; k < 16; k++) this.checkError = Math.max(this.checkError, Math.abs(rs[k] - m[k]));
  }
}

const skeletons = new Map<THREE.Skeleton, DQSkeleton>();
let maskFn: ((bone: THREE.Bone) => number) | null = null;

function attachSkeleton(skeleton: THREE.Skeleton, mesh: THREE.SkinnedMesh): DQSkeleton {
  let dq = skeletons.get(skeleton);
  if (dq) return dq;
  dq = new DQSkeleton(skeleton, mesh);
  skeletons.set(skeleton, dq);
  if (maskFn) skeleton.bones.forEach((b, i) => dq!.setMask(i, maskFn!(b)));
  skeleton.boneTexture?.dispose();
  skeleton.boneTexture = dq.texture;
  const update = skeleton.update.bind(skeleton);
  const target = dq;
  skeleton.update = () => {
    update();            // three's CPU bone matrices (raycasting, bounding volumes)
    target.compute();
  };
  return dq;
}

// Per-skeleton data for the shader (rigid dual quaternion + scale matrix per bone, like Blender's
// DQS with non-uniform scale, plus the previous frame for velocity effects). Call once after the
// model is loaded, before the first render. Every mesh bound to one skeleton must share the
// transform of the first one (true for glTF primitives and for the outline hulls).
export function attachDualQuatSkinning(root: THREE.Object3D): void {
  root.updateMatrixWorld(true);
  root.traverse((o) => {
    const m = o as THREE.SkinnedMesh;
    if (!m.isSkinnedMesh || !m.skeleton) return;
    // every material that draws a skinned mesh has to read the new bone texture layout
    (Array.isArray(m.material) ? m.material : [m.material]).forEach(useDualQuatSkinning);
    if (m.customDepthMaterial) useDualQuatSkinning(m.customDepthMaterial);
    if (m.customDistanceMaterial) useDualQuatSkinning(m.customDistanceMaterial);
    attachSkeleton(m.skeleton, m);
  });
}

/** Once per animation frame, before the first render of it: the current pose becomes the previous
 *  one. `jump`: no velocity this frame (seek, clip reset); a bone moving more than `maxStep`
 *  (mesh units) since the last frame counts as a jump too. */
export function dqFrameTick(jump = false, maxStep = Infinity): void {
  for (const dq of skeletons.values()) dq.tick(jump, maxStep);
}

/** Per-bone effect mask (x: how much the smear moves that bone's skin), for every skeleton. */
export function setDualQuatMask(fn: (bone: THREE.Bone) => number): void {
  maskFn = fn;
  for (const dq of skeletons.values()) dq.skeleton.bones.forEach((b, i) => dq.setMask(i, fn(b)));
}

/** Debug and tests: the CPU-side data of a skeleton (null if it has none). */
export function dualQuatData(skeleton: THREE.Skeleton): DQSkeleton | null {
  return skeletons.get(skeleton) ?? null;
}
