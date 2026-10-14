// Dual quaternion skinning for three.js materials.
//
// Blender deforms the rig with "Preserve Volume" (dual quaternion skinning)
// and the skin weights were made for it. three.js only does linear blend
// skinning, which averages the bone matrices: where a joint bends a lot
// (a raised arm) the sleeve loses volume and stretches into a thin tube.
// This patch replaces the skinning chunks of any material by dual quaternion
// blending, so the viewer deforms like the Blender renders.
import * as THREE from 'three';

const PARS = /* glsl */ `
#ifdef USE_SKINNING
vec4 dqQuat( mat3 m ) {
  float tr = m[0][0] + m[1][1] + m[2][2];
  if ( tr > 0.0 ) {
    float s = sqrt( tr + 1.0 ) * 2.0;
    return vec4( ( m[1][2] - m[2][1] ) / s, ( m[2][0] - m[0][2] ) / s, ( m[0][1] - m[1][0] ) / s, 0.25 * s );
  } else if ( m[0][0] > m[1][1] && m[0][0] > m[2][2] ) {
    float s = sqrt( 1.0 + m[0][0] - m[1][1] - m[2][2] ) * 2.0;
    return vec4( 0.25 * s, ( m[1][0] + m[0][1] ) / s, ( m[2][0] + m[0][2] ) / s, ( m[1][2] - m[2][1] ) / s );
  } else if ( m[1][1] > m[2][2] ) {
    float s = sqrt( 1.0 + m[1][1] - m[0][0] - m[2][2] ) * 2.0;
    return vec4( ( m[1][0] + m[0][1] ) / s, 0.25 * s, ( m[2][1] + m[1][2] ) / s, ( m[2][0] - m[0][2] ) / s );
  }
  float s = sqrt( 1.0 + m[2][2] - m[0][0] - m[1][1] ) * 2.0;
  return vec4( ( m[2][0] + m[0][2] ) / s, ( m[2][1] + m[1][2] ) / s, 0.25 * s, ( m[0][1] - m[1][0] ) / s );
}
// bone transform (in the mesh's bind space) -> unit dual quaternion (r, d) and
// its uniform scale s (the exported skeleton maps the bind-space vertices with
// a common scale: p' = s R p + t)
void dqFrom( mat4 b, out vec4 r, out vec4 d, out float s ) {
  mat4 m = bindMatrixInverse * b * bindMatrix;
  s = length( m[0].xyz );
  mat3 R = mat3( normalize( m[0].xyz ), normalize( m[1].xyz ), normalize( m[2].xyz ) );
  r = normalize( dqQuat( R ) );
  vec3 t = m[3].xyz;
  d = 0.5 * vec4( t.x * r.w + t.y * r.z - t.z * r.y,
                  t.y * r.w + t.z * r.x - t.x * r.z,
                  t.z * r.w + t.x * r.y - t.y * r.x,
                  - dot( t, r.xyz ) );
}
vec3 dqRotate( vec4 r, vec3 v ) {
  return v + 2.0 * cross( r.xyz, cross( r.xyz, v ) + r.w * v );
}
vec3 dqTransform( vec4 r, vec4 d, vec3 p ) {
  return dqRotate( r, p ) + 2.0 * ( r.w * d.xyz - d.w * r.xyz + cross( r.xyz, d.xyz ) );
}
#endif
`;

const BLEND = /* glsl */ `
#include <skinbase_vertex>
#ifdef USE_SKINNING
  vec4 dqR, dqD;
  float dqS;
  {
    vec4 r0, d0, r1, d1, r2, d2, r3, d3;
    float s0, s1, s2, s3;
    dqFrom( boneMatX, r0, d0, s0 );
    dqFrom( boneMatY, r1, d1, s1 );
    dqFrom( boneMatZ, r2, d2, s2 );
    dqFrom( boneMatW, r3, d3, s3 );
    dqS = dot( skinWeight, vec4( s0, s1, s2, s3 ) ) / max( dot( skinWeight, vec4( 1.0 ) ), 1e-6 );
    // shortest path: every quaternion on the same side as the first
    float w0 = skinWeight.x;
    float w1 = skinWeight.y * ( dot( r0, r1 ) < 0.0 ? -1.0 : 1.0 );
    float w2 = skinWeight.z * ( dot( r0, r2 ) < 0.0 ? -1.0 : 1.0 );
    float w3 = skinWeight.w * ( dot( r0, r3 ) < 0.0 ? -1.0 : 1.0 );
    dqR = w0 * r0 + w1 * r1 + w2 * r2 + w3 * r3;
    dqD = w0 * d0 + w1 * d1 + w2 * d2 + w3 * d3;
    float len = max( length( dqR ), 1e-6 );
    dqR /= len;
    dqD /= len;
  }
#endif
`;

const NORMAL = /* glsl */ `
#ifdef USE_SKINNING
  objectNormal = dqRotate( dqR, objectNormal );
  #ifdef USE_TANGENT
  objectTangent = dqRotate( dqR, objectTangent );
  #endif
#endif
`;

const POSITION = /* glsl */ `
#ifdef USE_SKINNING
  transformed = dqTransform( dqR, dqD, transformed * dqS );
#endif
`;

export function patchShader(shader: { vertexShader: string }) {
  shader.vertexShader = shader.vertexShader
    .replace('#include <skinning_pars_vertex>', '#include <skinning_pars_vertex>\n' + PARS)
    .replace('#include <skinbase_vertex>', BLEND)
    .replace('#include <skinnormal_vertex>', NORMAL)
    .replace('#include <skinning_vertex>', POSITION);
}

// Add the patch to a material, after whatever onBeforeCompile it already has
// (the reference look patches the fragment shader of the same materials).
export function useDualQuatSkinning(mat: THREE.Material) {
  const m = mat as THREE.Material & { __dq?: boolean };
  if (m.__dq) return;
  m.__dq = true;
  const prev = m.onBeforeCompile;
  m.onBeforeCompile = (shader, renderer) => {
    prev.call(m, shader, renderer);
    patchShader(shader);
  };
  const key = m.customProgramCacheKey.bind(m);
  m.customProgramCacheKey = () => key() + '|dq';
  m.needsUpdate = true;
}
