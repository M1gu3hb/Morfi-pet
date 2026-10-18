// Smear on fast moves: the skin on the trailing side of a fast limb is pulled back along
// its motion, a cartoon motion blur made by the model itself (no post-processing). It
// runs in the vertex shader of the colour and outline materials, from the skinning of a
// trail pose that chases the current one with a short time constant (dqskin.ts keeps it in
// the bone texture; frame-rate independent and smooth although the clips are sampled at
// 30 fps) and a per-bone mask (arms a lot, the head barely). Rigid pieces glued to a bone
// (eye and mouth decals, lenses, props) get the same displacement from their own trail
// matrix, so they stay on.
import * as THREE from 'three';

/** The smoothed normal (outline.ts smoothNormals), declared once per shader. */
export const OUTLINE_NORMAL_ATTRIBUTE = /* glsl */ `
#ifndef MORFI_OUTLINE_NORMAL
#define MORFI_OUTLINE_NORMAL
attribute vec3 outlineNormal;
#endif`;

/** Shared by every smeared material (values change, objects never do). */
export const smearUniforms = {
  /** amount, 0 = off */
  fxSmear: { value: 0 },
  /** current - trail pose -> velocity per 1/60 s (the lag of the trail depends on the frame time) */
  fxFrameScale: { value: 1 },
  /** x: speed where it starts, y: speed where it is full (m per 1/60 s), z: trail length (frames), w: max trail (m) */
  fxSmearParams: { value: new THREE.Vector4(0.004, 0.02, 2.0, 0.045) },
};

const SMEAR_PARS = /* glsl */ `
uniform float fxSmear;
uniform float fxFrameScale;
uniform vec4 fxSmearParams;
#ifndef USE_SKINNING
uniform mat4 fxVelMatrix;     // object -> model space velocity (current - previous matrix)
uniform mat3 fxNormalMatrix;  // object -> model space normals
uniform mat3 fxToObject;      // model -> object space directions
uniform float fxRigidMask;
#endif
#ifdef FX_SMOOTH_NORMAL
${OUTLINE_NORMAL_ATTRIBUTE}
#endif
// vel and n in the same space; the offset comes back in that space
vec3 fxSmearOffset( vec3 vel, vec3 n, float mask ) {
  float speed = length( vel );
  vec3 dir = vel / max( speed, 1e-6 );
  float trailing = smoothstep( 0.0, 0.6, - dot( n, dir ) );
  // a soft cap (tanh, slope 1 at 0): no kink where the trail reaches its maximum length
  float len = fxSmearParams.w * tanh( speed * fxSmearParams.z / fxSmearParams.w ) * smoothstep( fxSmearParams.x, fxSmearParams.y, speed );
  return - dir * len * trailing * mask * fxSmear;
}
`;

// before project_vertex: \`transformed\` is the skinned (or rigid, morphed) object-space position
const SMEAR_VERTEX = /* glsl */ `
#ifdef FX_SMOOTH_NORMAL
  #define FX_NORMAL outlineNormal
#else
  #define FX_NORMAL normal
#endif
#ifdef USE_SKINNING
  if ( fxSmear > 0.0 ) {
    vec4 fxR, fxD, fxS0, fxS1, fxS2;
    dqBlend( 5, fxR, fxD, fxS0, fxS1, fxS2 );
    vec3 fxVel = ( transformed - dqTransform( fxR, fxD, dqScale( fxS0, fxS1, fxS2, dqRestPosition ) ) ) * fxFrameScale;
    // the smoothed normal: split vertices at seams move together (no cracks)
    transformed += fxSmearOffset( fxVel, dqSkinNormal( dqR, dqS0, dqS1, dqS2, FX_NORMAL ), dqMask().x );
  }
#else
  if ( fxSmear > 0.0 && fxRigidMask > 0.0 ) {
    vec3 fxVel = ( fxVelMatrix * vec4( transformed, 1.0 ) ).xyz * fxFrameScale;
    transformed += fxToObject * fxSmearOffset( fxVel, normalize( fxNormalMatrix * FX_NORMAL ), fxRigidMask );
  }
#endif
#include <project_vertex>
`;

/** Per-object uniforms of a rigid piece (its own material instance). */
export interface RigidSmear {
  object: THREE.Object3D;
  uniforms: {
    fxVelMatrix: { value: THREE.Matrix4 };
    fxNormalMatrix: { value: THREE.Matrix3 };
    fxToObject: { value: THREE.Matrix3 };
    fxRigidMask: { value: number };
  };
  prev: THREE.Matrix4;
  hasPrev: boolean;
}

export function rigidSmear(object: THREE.Object3D, mask: number): RigidSmear {
  return {
    object,
    uniforms: {
      fxVelMatrix: { value: new THREE.Matrix4().set(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) },
      fxNormalMatrix: { value: new THREE.Matrix3() },
      fxToObject: { value: new THREE.Matrix3() },
      fxRigidMask: { value: mask },
    },
    prev: new THREE.Matrix4(),
    hasPrev: false,
  };
}

/** Chain the smear on a material (after the dual quaternion patch for skinned meshes). A rigid
 *  piece passes its own uniforms: its material must not be shared with other objects. */
export function useSmear(mat: THREE.Material, rigid?: RigidSmear, smoothNormal = true): void {
  const m = mat as THREE.Material & { __smear?: boolean };
  if (m.__smear) return;
  m.__smear = true;
  const prev = m.onBeforeCompile;
  m.onBeforeCompile = (shader, renderer) => {
    prev.call(m, shader, renderer);
    Object.assign(shader.uniforms, smearUniforms);
    if (rigid) Object.assign(shader.uniforms, rigid.uniforms);
    else Object.assign(shader.uniforms, IDLE_RIGID);
    shader.vertexShader = shader.vertexShader
      .replace('void main() {', (smoothNormal ? '#define FX_SMOOTH_NORMAL\n' : '') + SMEAR_PARS + '\nvoid main() {')
      .replace('#include <project_vertex>', SMEAR_VERTEX);
  };
  const key = m.customProgramCacheKey.bind(m);
  m.customProgramCacheKey = () => key() + (smoothNormal ? '|smear' : '|smear0');
  m.needsUpdate = true;
}

// a skinned material compiled for a rigid mesh (never smeared there)
const IDLE_RIGID = {
  fxVelMatrix: { value: new THREE.Matrix4().set(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) },
  fxNormalMatrix: { value: new THREE.Matrix3() },
  fxToObject: { value: new THREE.Matrix3() },
  fxRigidMask: { value: 0 },
};

const _rel = new THREE.Matrix4(), _inv = new THREE.Matrix4();

/** Once per frame, after the pose is final: the trail matrix of a rigid piece chases its current one
 *  by `chase` (1 - exp(-dt / tau)); its velocity (current - trail) in model space. */
export function updateRigidSmear(r: RigidSmear, modelInverse: THREE.Matrix4, jump: boolean, chase: number): void {
  _rel.multiplyMatrices(modelInverse, r.object.matrixWorld);
  const u = r.uniforms;
  const det = _rel.determinant(), detPrev = r.prev.determinant();
  const v = u.fxVelMatrix.value.elements, a = _rel.elements, b = r.prev.elements;
  // appearing or disappearing (a prop scaled from 0) is not a motion
  const still = jump || !r.hasPrev || Math.abs(det) < 1e-9 || Math.abs(detPrev) < 1e-9 || Math.abs(det / detPrev - 1) > 0.02;
  if (still) r.prev.copy(_rel);
  else for (let i = 0; i < 16; i++) b[i] += chase * (a[i] - b[i]);
  for (let i = 0; i < 16; i++) v[i] = still ? 0 : a[i] - b[i];
  if (Math.abs(det) > 1e-12) {
    u.fxToObject.value.setFromMatrix4(_inv.copy(_rel).invert());
    u.fxNormalMatrix.value.getNormalMatrix(_rel);
  }
  r.hasPrev = true;
}
