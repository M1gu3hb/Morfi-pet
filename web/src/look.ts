// "Reference look": shading captured from the reference photos.
//
// The references are product shots whose lights stay put relative to the
// camera, so the shading of every material can be written as a function of
// the view-space normal alone: a MatCap. scripts/capture-look.mjs renders the
// viewer's own GLB with the calibrated camera and pose of each reference shot
// (albedo, view-space normal and material passes), divides the photo by the
// albedo pixel by pixel and stores the ratio in a 64x64 matcap per material
// (log2-encoded, scripts/build_look.py). Here each material is shaded as
//   albedo (texture x colour) x matcap(normal) x key-light shadow
// i.e. lit exactly like the photos, felt lines and face texture included.
import * as THREE from 'three';

export type LookInfo = {
  size: number; // tile size in the atlas
  cols: number;
  log2: [number, number]; // encoded value v (0..1) -> ratio = 2^(v * span + lo)
  materials: Record<string, { tile: number; samples: number }>;
  shadow: number; // how much the key light's shadow darkens (0..1)
  exposure: number;
};

// view-space normal + view direction -> matcap uv (same as THREE.MeshMatcapMaterial)
export function matcapUV(n: THREE.Vector3, viewDir: THREE.Vector3, out = new THREE.Vector2()) {
  const x = new THREE.Vector3(viewDir.z, 0, -viewDir.x).normalize();
  const y = new THREE.Vector3().crossVectors(viewDir, x);
  return out.set(x.dot(n) * 0.495 + 0.5, y.dot(n) * 0.495 + 0.5);
}

type Uniforms = {
  refAtlas: { value: THREE.Texture | null };
  refTile: { value: THREE.Vector4 };
  refTile2: { value: THREE.Vector4 };
  refMix: { value: number };
  refShadow: { value: number };
  refLog: { value: THREE.Vector2 };
  refExposure: { value: number };
};

export const lookState = { mix: 1, enabled: true };
const shared = { mix: { value: 1 } };

// Patch a glTF material so it can be shaded with its reference matcap.
export function applyReferenceLook(mat: THREE.Material, atlas: THREE.Texture, info: LookInfo) {
  const m = mat as THREE.MeshStandardMaterial;
  const entry = info.materials[m.name];
  if (!entry || !(m as THREE.MeshStandardMaterial).isMeshStandardMaterial) return false;
  const rows = Math.ceil(Object.keys(info.materials).length / info.cols);
  const tileOf = (k: number) => new THREE.Vector4((k % info.cols) / info.cols, 1 - (Math.floor(k / info.cols) + 1) / rows, 1 / info.cols, 1 / rows);
  // two-tone material (the head): a second matcap for the celeste texels
  const second = info.materials[m.name + '#2'];
  const u: Uniforms = {
    refAtlas: { value: atlas },
    // tile origin and size in atlas uv
    refTile: { value: tileOf(entry.tile) },
    refTile2: { value: tileOf(second ? second.tile : entry.tile) },
    refMix: shared.mix,
    refShadow: { value: info.shadow },
    refLog: { value: new THREE.Vector2(info.log2[0], info.log2[1] - info.log2[0]) },
    refExposure: { value: info.exposure },
  };
  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, u);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
uniform sampler2D refAtlas;
uniform vec4 refTile;
uniform vec4 refTile2;
uniform float refMix;
uniform float refShadow;
uniform vec2 refLog;
uniform float refExposure;`)
      .replace('#include <opaque_fragment>', `
{
  vec3 vd = normalize( vViewPosition );
  vec3 ax = normalize( vec3( vd.z, 0.0, - vd.x ) );
  vec3 ay = cross( vd, ax );
  vec2 muv = vec2( dot( ax, normal ), dot( ay, normal ) ) * 0.495 + 0.5;
  muv = clamp( muv, 0.5 / 64.0, 1.0 - 0.5 / 64.0 );
  vec3 enc = texture2D( refAtlas, refTile.xy + muv * refTile.zw ).rgb;
  vec3 enc2 = texture2D( refAtlas, refTile2.xy + muv * refTile2.zw ).rgb;
  float tone = smoothstep( 0.08, 0.16, diffuseColor.r / max( diffuseColor.b, 1e-4 ) );
  vec3 ratio = exp2( mix( enc, enc2, tone ) * refLog.y + refLog.x );
  float sh = 1.0;
  #if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
    DirectionalLightShadow kls = directionalLightShadows[ 0 ];
    sh = getShadow( directionalShadowMap[ 0 ], kls.shadowMapSize, kls.shadowIntensity, kls.shadowBias, kls.shadowRadius, vDirectionalShadowCoord[ 0 ] );
  #endif
  vec3 refColor = diffuseColor.rgb * ratio * refExposure * mix( 1.0, sh, refShadow );
  outgoingLight = mix( outgoingLight, refColor, refMix );
}
#include <opaque_fragment>`);
  };
  m.customProgramCacheKey = () => 'reflook';
  m.needsUpdate = true;
  return true;
}

export function setReferenceMix(v: number) {
  shared.mix.value = v;
}

export async function loadLook(base = './look/') {
  const info = (await (await fetch(base + 'look.json')).json()) as LookInfo;
  const tex = await new THREE.TextureLoader().loadAsync(base + 'matcaps.png');
  tex.colorSpace = THREE.NoColorSpace; // encoded data, not colour
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  tex.flipY = true;
  return { info, tex };
}

// Per-shot face of the reference photos (scripts/export_assets.py, bake_shot_morphs):
// morph target "Shot_<view>" holds the eyes turned to that shot's camera with the
// fitted gaze and, in the profiles, the face cheat. Weight 1 = exactly the face
// of that photo; every other shot key is set to 0.
export function setShotMorph(root: THREE.Object3D, view: string, w: number) {
  root.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh || !m.morphTargetDictionary || !m.morphTargetInfluences) return;
    for (const [name, i] of Object.entries(m.morphTargetDictionary)) {
      if (name.startsWith('Shot_')) m.morphTargetInfluences[i] = name === 'Shot_' + view ? w : 0;
    }
  });
}
