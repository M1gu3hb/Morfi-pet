// Morfi's living face in the browser: GLSL ports of the Blender shaders of
// scripts/ia3d/build_face.py (MorfiEye, MorfiMouth). The decal meshes come in the GLB
// with their "eye" UVs (metres from the eye / mouth centre); the painted eyes and mouth
// were erased from the body texture, so these shaders draw them and, where a lid
// covers the eye or the mouth is closed, they are transparent over the real skin.
import * as THREE from 'three';

// same list and meaning as FACE_PROPS in scripts/ia3d/anim/clip.py (rig custom properties)
export const FACE_PROPS = ['blink_L', 'blink_R', 'gaze_x', 'gaze_y', 'mouth_open', 'smile', 'mouth_round', 'mouth_side',
  'teeth', 'brow_L', 'brow_R', 'brow_in_L', 'brow_in_R', 'squint', 'lid_drop', 'lid_angle', 'pupil', 'eye_calm'] as const;
export type FaceProp = (typeof FACE_PROPS)[number];
export type FaceState = Record<FaceProp, number>;

export interface FaceParams {
  eyes: Record<'R' | 'L', Record<string, number>>;
  mouth: { half_width: number; corner_up: number; depth: number };
  colors: Record<string, number[]>; // linear RGB
}

export function neutralFace(): FaceState {
  const f = {} as FaceState;
  for (const k of FACE_PROPS) f[k] = 0;
  return f;
}

const GLSL_COMMON = /* glsl */ `
float ss(float a, float b, float x) { float t = clamp((x - a) / (b - a), 0.0, 1.0); return t * t * (3.0 - 2.0 * t); }
`;

const EYE_UNIFORMS = ['A', 'B', 'InCos', 'InSin', 'OutCX', 'OutCY', 'OutA', 'OutB', 'OutCos', 'OutSin', 'IrisX', 'IrisY',
  'IrisR', 'PupilR', 'PupilDX', 'PupilDY', 'HlX', 'HlY', 'HlR', 'GazeRangeX', 'GazeRangeY', 'AA', 'Nose'];
const EYE_LIVE = ['GazeX', 'GazeY', 'Blink', 'Squint', 'LidDrop', 'LidAngle', 'PupilScale', 'ClosedCurve'];
const EYE_COLORS = ['sclera', 'sclera_shade', 'iris_hi', 'iris_lo', 'iris_rim', 'pupil', 'outline', 'highlight'];

const EYE_GLSL = /* glsl */ `
${EYE_UNIFORMS.map((k) => `uniform float e${k};`).join('\n')}
${EYE_LIVE.map((k) => `uniform float e${k};`).join('\n')}
${EYE_COLORS.map((k) => `uniform vec3 c_${k};`).join('\n')}
${GLSL_COMMON}
vec4 morfiEye(vec2 p) {
  float x = p.x, y = p.y;
  float xe = x * eInCos + y * eInSin, ye = y * eInCos - x * eInSin;
  float q = length(vec2(xe / eA, ye / eB));
  float xo0 = x - eOutCX, yo0 = y - eOutCY;
  float qo = length(vec2((xo0 * eOutCos + yo0 * eOutSin) / eOutA, (yo0 * eOutCos - xo0 * eOutSin) / eOutB));
  float inside = ss(1.0 + eAA / eB, 1.0 - eAA / eB, q);
  float outer = ss(1.0 + eAA / eOutB, 1.0 - eAA / eOutB, qo);
  float thick = max(eOutB - eB, 0.002);
  float icx = eIrisX + eGazeX * eGazeRangeX, icy = eIrisY + eGazeY * eGazeRangeY;
  float di = length(vec2(x - icx, y - icy));
  float irs = eIrisR * ePupilScale, prs = ePupilR * ePupilScale * ePupilScale;   // the pupil reacts more
  float iris = ss(irs + eAA, irs - eAA, di);
  float pupil = ss(prs + eAA, prs - eAA, length(vec2(x - icx - ePupilDX, y - icy - ePupilDY)));
  float tI = clamp((di - prs) / (irs - prs), 0.0, 1.0);
  vec3 irisCol = mix(c_iris_hi, c_iris_lo, ss(0.25, 0.85, tI));
  irisCol = mix(irisCol, c_iris_rim, ss(0.80, 1.0, tI));
  float dh = length(vec2(x - (eIrisX + eGazeX * eGazeRangeX * 0.7 + eHlX), y - (eIrisY + eGazeY * eGazeRangeY * 0.7 + eHlY)));
  float hl = ss(eHlR + eAA * 0.8, eHlR - eAA * 0.8, dh);
  float shade = clamp(ss(0.80, 1.0, q) * 0.22 + ss(0.35, 1.0, ye / eB) * 0.30, 0.0, 1.0);
  vec3 col = mix(c_sclera, c_sclera_shade, shade);
  col = mix(col, irisCol, iris);
  col = mix(col, c_pupil, pupil);
  col = mix(col, c_highlight, hl);
  // lids move straight down in the face
  float xn = x / eA;
  float arc = sqrt(clamp(1.0 - xn * xn, 0.0, 1.0));
  float closedY = eB * (-0.30 + 0.22 * eClosedCurve * (1.0 - xn * xn));   // arch (happy) or sag (calm)
  // upper lid drop (tired, angry) and tilt (+ angry: nose side down, - sad)
  float lidY = mix(arc * eB + thick, closedY, eBlink) - eB * (eLidDrop + eLidAngle * eNose * xn) * (1.0 - eBlink);
  float squintY = eB * (-0.62 + 0.25 * (1.0 - xn * xn));
  float lowY = mix(mix(-arc * eB - thick, squintY, eSquint), closedY - 0.0015, eBlink);
  float lids = max(ss(lidY - eAA, lidY + eAA, y), ss(lowY + eAA, lowY - eAA, y));
  float lashW = 0.0030 + eBlink * 0.0022;
  float lash = ss(lashW + eAA, lashW - eAA, abs(y - lidY)) * ss(0.02, 0.15, eBlink + eSquint);
  float lash2 = ss(0.0022 + eAA, 0.0022 - eAA, abs(y - lowY)) * ss(0.02, 0.2, eSquint);
  float ring = clamp(outer - inside, 0.0, 1.0);
  float ringVis = mix(1.0, ss(0.15, -0.35, y / eB), eBlink);
  float ink = clamp(max(ring * ringVis, max(lash, lash2) * inside), 0.0, 1.0);
  return vec4(mix(col, c_outline, ink), clamp(max(inside * (1.0 - lids), ink), 0.0, 1.0));
}
`;

const MOUTH_GLSL = /* glsl */ `
uniform float mOpen, mSmile, mRound, mTeeth, mSide, mAA, mHalfW, mCornerUp, mDepth;
uniform vec3 c_mouth_in, c_mouth_lip, c_tongue, c_teeth;
${GLSL_COMMON}
vec4 morfiMouth(vec2 p) {
  float x = p.x - mSide * 0.010, y = p.y;                 // a sideways mouth (smirk, doubt)
  float w = mHalfW * (1.0 + mSmile * 0.08 - mRound * 0.32);
  float xn = x / w;
  float xx = clamp(xn * xn, 0.0, 1.0);
  float top = mCornerUp * (mSmile * 1.25 - mRound * 0.6) * xx + mRound * 0.004 + mSide * 0.005 * xn;
  float depth = (mOpen * 2.0 * mDepth + mRound * 0.006) * pow(clamp(1.0 - xx, 0.0, 1.0), mix(0.43, 0.75, mRound));
  float bot = top - depth - 0.0024;
  float insideX = ss(1.0 + mAA / w, 1.0 - mAA / w, abs(xn));
  float mouth = ss(top + mAA, top - mAA, y) * ss(bot - mAA, bot + mAA, y) * insideX;
  float t = clamp((top - y) / max(top - bot, 0.001), 0.0, 1.0);
  vec3 inner = mix(c_mouth_in, c_mouth_lip, ss(0.15, 0.9, t) * ss(0.004, 0.02, depth));
  float dt = length(vec2(x / (w * 0.55), (y - (bot + depth * 0.28)) / max(depth * 0.45, 0.002)));
  float tongue = ss(1.05, 0.9, dt) * ss(0.008, 0.02, depth) * (1.0 - mRound * 0.6);
  inner = mix(inner, c_tongue, tongue * 0.85);
  // upper teeth: a soft white band under the top lip of a wide open smile
  float tband = ss(top - depth * 0.30 - mAA, top - depth * 0.30 + mAA, y) * mTeeth * ss(0.006, 0.014, depth);
  return vec4(mix(inner, c_teeth, tband), mouth);
}
`;

type Uniforms = Record<string, THREE.IUniform>;

function decalMaterial(glsl: string, call: string, uniforms: Uniforms, roughness: number): THREE.MeshPhysicalMaterial {
  const mat = new THREE.MeshPhysicalMaterial({
    roughness, metalness: 0, transparent: true, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, clearcoat: 0.25, clearcoatRoughness: 0.2,
  });
  mat.defines = { USE_UV: '' };
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.fragmentShader = shader.fragmentShader
      .replace('void main() {', `${glsl}\nvoid main() {`)
      // glTF stores v flipped: the decal's own (metres) coordinates are (u, 1 - v)
      .replace('#include <map_fragment>', `vec4 decal = ${call}(vec2(vUv.x, 1.0 - vUv.y));\ndiffuseColor.rgb = decal.rgb;\ndiffuseColor.a *= decal.a;`);
  };
  mat.customProgramCacheKey = () => call;
  return mat;
}

function colorUniforms(colors: Record<string, number[]>, keys: string[]): Uniforms {
  const u: Uniforms = {};
  for (const k of keys) u['c_' + k] = { value: new THREE.Vector3(...(colors[k] as [number, number, number])) };
  return u;
}

export class MorfiFace {
  private eyes: Record<'R' | 'L', Uniforms> = { R: {}, L: {} };
  private mouth: Uniforms = {};
  private bodies: THREE.Mesh[] = [];
  private mouthDecal: THREE.Mesh | null = null;

  constructor(root: THREE.Object3D, params: FaceParams) {
    for (const side of ['R', 'L'] as const) {
      const u: Uniforms = colorUniforms(params.colors, EYE_COLORS);
      for (const k of EYE_UNIFORMS) u['e' + k] = { value: params.eyes[side][k] };
      for (const k of EYE_LIVE) u['e' + k] = { value: k === 'PupilScale' || k === 'ClosedCurve' ? 1 : 0 };
      if (params.eyes[side].Nose === undefined) u.eNose.value = side === 'R' ? 1 : -1;
      this.eyes[side] = u;
    }
    this.mouth = colorUniforms({ teeth: [0.92, 0.93, 0.95], ...params.colors }, ['mouth_in', 'mouth_lip', 'tongue', 'teeth']);
    Object.assign(this.mouth, {
      mOpen: { value: 0.5 }, mSmile: { value: 0.55 }, mRound: { value: 0 }, mTeeth: { value: 0 }, mSide: { value: 0 },
      mAA: { value: 0.0008 },
      mHalfW: { value: params.mouth.half_width }, mCornerUp: { value: params.mouth.corner_up }, mDepth: { value: params.mouth.depth },
    });
    root.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh) return;
      const name = (Array.isArray(m.material) ? m.material[0] : m.material).name;
      if (name.startsWith('MorfiEye_')) {
        const side = name.endsWith('_L') ? 'L' : 'R';
        m.material = decalMaterial(EYE_GLSL, 'morfiEye', this.eyes[side], 0.32);
        m.renderOrder = 1; m.castShadow = false;
      } else if (name.startsWith('MorfiMouth')) {
        m.material = decalMaterial(MOUTH_GLSL, 'morfiMouth', this.mouth, 0.5);
        m.renderOrder = 1; m.castShadow = false;
        this.mouthDecal = m;
      } else if (name.startsWith('MorfiLens')) {
        // thin clear glass: reflections only (transmission blurs what is behind)
        m.material = new THREE.MeshPhysicalMaterial({
          color: 0xffffff, roughness: 0.03, metalness: 0, transparent: true, opacity: 0.1, depthWrite: false,
          clearcoat: 1, clearcoatRoughness: 0.02, envMapIntensity: 1.4, specularIntensity: 1,
        });
        m.renderOrder = 2; m.castShadow = false;
      } else if (m.morphTargetDictionary && 'Brow_L' in m.morphTargetDictionary) {
        this.bodies.push(m);
      }
    });
  }

  apply(f: FaceState): void {
    const R = this.eyes.R, L = this.eyes.L;
    R.eGazeX.value = L.eGazeX.value = f.gaze_x;
    R.eGazeY.value = L.eGazeY.value = f.gaze_y;
    R.eBlink.value = THREE.MathUtils.clamp(f.blink_R, 0, 1);
    L.eBlink.value = THREE.MathUtils.clamp(f.blink_L, 0, 1);
    const clamp = THREE.MathUtils.clamp;
    for (const e of [R, L]) {
      e.eSquint.value = clamp(f.squint, 0, 1);
      e.eLidDrop.value = clamp(f.lid_drop, 0, 1);
      e.eLidAngle.value = clamp(f.lid_angle, -1, 1);
      e.ePupilScale.value = 1 + 0.3 * clamp(f.pupil, -1, 1);
      e.eClosedCurve.value = 1 - 1.6 * clamp(f.eye_calm, 0, 1);
    }
    // the same mappings as the Blender drivers (scripts/ia3d/build_face.py MOUTH_PROPS / EYE_PROPS)
    const sm = clamp(f.smile, -1, 1);
    this.mouth.mOpen.value = Math.max(0, 0.5 + 0.5 * clamp(f.mouth_open, -1, 1));   // the rig props are -1..1
    this.mouth.mSmile.value = 0.55 + 0.45 * Math.max(sm, 0) + 1.55 * Math.min(sm, 0);
    this.mouth.mRound.value = clamp(f.mouth_round, 0, 1);
    this.mouth.mTeeth.value = clamp(f.teeth, 0, 1);
    this.mouth.mSide.value = clamp(f.mouth_side, -1, 1);
    const fill = clamp(-f.mouth_open, 0, 1);
    for (const b of this.bodies) {
      const d = b.morphTargetDictionary!, w = b.morphTargetInfluences!;
      w[d.Brow_L] = clamp(f.brow_L, -1, 1);
      w[d.Brow_R] = clamp(f.brow_R, -1, 1);
      if (d.Brow_In_L !== undefined) w[d.Brow_In_L] = clamp(f.brow_in_L, -1, 1);
      if (d.Brow_In_R !== undefined) w[d.Brow_In_R] = clamp(f.brow_in_R, -1, 1);
      if (d.Mouth_Fill !== undefined) w[d.Mouth_Fill] = fill;
    }
    const md = this.mouthDecal;
    if (md?.morphTargetDictionary && md.morphTargetInfluences && md.morphTargetDictionary.Mouth_Fill !== undefined) {
      md.morphTargetInfluences[md.morphTargetDictionary.Mouth_Fill] = fill;
    }
  }
}
