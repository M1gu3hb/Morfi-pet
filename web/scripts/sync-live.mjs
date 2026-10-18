// Copies Morfi en vivo's exported files (scripts/ia3d/export_web.py, export_face_anims.py and
// export_scenes.py write them to ../work/ia3d/web) into public/models and resamples the animation
// and compresses the GLBs with meshopt (the compressed GLBs are what Vercel serves). The scenes
// (long performances with voice, loaded only when someone opens "Escenas") are a second,
// animation-only GLB.
import { copyFileSync, existsSync, mkdirSync, statSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', '..', 'work', 'ia3d', 'web');
const dst = join(here, '..', 'public', 'models');
mkdirSync(dst, { recursive: true });
for (const f of ['morfi_live_face.json', 'morfi_live_anims.json']) {
  if (!existsSync(join(src, f))) throw new Error(`missing ${join(src, f)} (run the exporters first)`);
  copyFileSync(join(src, f), join(dst, f));
  console.log('synced', f);
}
const glb = join(src, 'morfi_live.glb');
if (!existsSync(glb)) throw new Error(`missing ${glb}`);
// the CLI through node itself: no shell, so paths with spaces are safe on Windows
const cli = join(here, '..', 'node_modules', '@gltf-transform', 'cli', 'bin', 'cli.js');
// every clip is sampled at 30 fps for every bone: drop the keys a curve does not need
// (constant channels, straight segments), then compress with meshopt
function compress(name) {
  const tmp = join(src, name.replace('.glb', '_resampled.glb'));
  execFileSync(process.execPath, [cli, 'resample', join(src, name), tmp, '--tolerance', '0.0002'], { stdio: 'inherit' });
  execFileSync(process.execPath, [cli, 'meshopt', tmp, join(dst, name), '--level', 'medium'], { stdio: 'inherit' });
  console.log('compressed', name, (statSync(join(dst, name)).size / 1e6).toFixed(2), 'MB');
}
compress('morfi_live.glb');
if (existsSync(join(src, 'morfi_live_scenes.glb'))) {
  if (!existsSync(join(src, 'morfi_live_scenes.json'))) throw new Error('morfi_live_scenes.glb without its json');
  copyFileSync(join(src, 'morfi_live_scenes.json'), join(dst, 'morfi_live_scenes.json'));
  console.log('synced morfi_live_scenes.json');
  compress('morfi_live_scenes.glb');
}
