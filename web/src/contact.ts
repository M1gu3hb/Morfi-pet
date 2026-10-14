// Soft contact shadow, like the studio floor of the reference photos: the
// character is rendered from below (orthographic, depth-faded so only what is
// near the floor darkens it), blurred twice, and shown on a floor plane.
import * as THREE from 'three';
import { HorizontalBlurShader } from 'three/examples/jsm/shaders/HorizontalBlurShader.js';
import { VerticalBlurShader } from 'three/examples/jsm/shaders/VerticalBlurShader.js';
import { patchShader as patchDualQuat } from './dqskin';

export class ContactShadow {
  readonly plane: THREE.Mesh;
  private rt: THREE.WebGLRenderTarget;
  private rtBlur: THREE.WebGLRenderTarget;
  private cam: THREE.OrthographicCamera;
  private depthMat: THREE.MeshDepthMaterial;
  private hBlur: THREE.ShaderMaterial;
  private vBlur: THREE.ShaderMaterial;
  private quad: THREE.Mesh;
  private quadScene = new THREE.Scene();
  private quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  constructor(size = 1.4, res = 512, private height = 0.35, opacity = 0.55, private blur = 2.6) {
    this.rt = new THREE.WebGLRenderTarget(res, res);
    this.rt.texture.generateMipmaps = false;
    this.rtBlur = new THREE.WebGLRenderTarget(res, res);
    this.rtBlur.texture.generateMipmaps = false;
    const mat = new THREE.MeshBasicMaterial({ map: this.rt.texture, transparent: true, opacity, depthWrite: false, toneMapped: false });
    this.plane = new THREE.Mesh(new THREE.PlaneGeometry(size, size).rotateX(-Math.PI / 2), mat);
    this.plane.position.y = 0.0015;
    this.plane.renderOrder = -1;
    // the texture is rendered looking up: flip it so it lies right on the floor
    this.plane.scale.z = -1;
    this.cam = new THREE.OrthographicCamera(-size / 2, size / 2, size / 2, -size / 2, 0, height);
    this.cam.rotation.x = Math.PI / 2;
    // darkness fades with height above the floor
    this.depthMat = new THREE.MeshDepthMaterial();
    this.depthMat.onBeforeCompile = (s) => {
      patchDualQuat(s); // the character deforms with dual quaternions (dqskin.ts)
      s.fragmentShader = s.fragmentShader.replace(
        'gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );',
        'gl_FragColor = vec4( vec3( 0.0 ), ( 1.0 - fragCoordZ ) * ( 1.0 - fragCoordZ ) );',
      );
    };
    this.depthMat.customProgramCacheKey = () => 'contact|dq';
    this.depthMat.depthTest = false;
    this.depthMat.depthWrite = false;
    this.hBlur = new THREE.ShaderMaterial(HorizontalBlurShader);
    this.hBlur.depthTest = false;
    this.vBlur = new THREE.ShaderMaterial(VerticalBlurShader);
    this.vBlur.depthTest = false;
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2));
    this.quadScene.add(this.quad);
  }

  private blurPass(renderer: THREE.WebGLRenderer, amount: number) {
    this.quad.material = this.hBlur;
    this.hBlur.uniforms.tDiffuse.value = this.rt.texture;
    this.hBlur.uniforms.h.value = amount / 256;
    renderer.setRenderTarget(this.rtBlur);
    renderer.render(this.quadScene, this.quadCam);
    this.quad.material = this.vBlur;
    this.vBlur.uniforms.tDiffuse.value = this.rtBlur.texture;
    this.vBlur.uniforms.v.value = amount / 256;
    renderer.setRenderTarget(this.rt);
    renderer.render(this.quadScene, this.quadCam);
  }

  update(renderer: THREE.WebGLRenderer, scene: THREE.Scene, centre: THREE.Vector3) {
    this.plane.position.x = centre.x;
    this.plane.position.z = centre.z;
    this.cam.position.set(centre.x, 0, centre.z);
    this.cam.updateMatrixWorld();
    const vis = this.plane.visible;
    this.plane.visible = false;
    const bg = scene.background, ov = scene.overrideMaterial;
    const prevTarget = renderer.getRenderTarget();
    const prevClear = renderer.getClearAlpha();
    const prevShadow = renderer.shadowMap.autoUpdate;
    renderer.shadowMap.autoUpdate = false;
    scene.background = null;
    scene.overrideMaterial = this.depthMat;
    renderer.setRenderTarget(this.rt);
    renderer.setClearColor(0x000000, 0);
    renderer.clear();
    renderer.render(scene, this.cam);
    scene.overrideMaterial = ov;
    this.blurPass(renderer, this.blur);
    this.blurPass(renderer, this.blur * 0.4);
    renderer.setRenderTarget(prevTarget);
    renderer.setClearColor(0x000000, prevClear);
    renderer.shadowMap.autoUpdate = prevShadow;
    scene.background = bg;
    this.plane.visible = vis;
  }
}
