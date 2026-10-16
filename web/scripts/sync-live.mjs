// Copies Morfi en vivo's exported files (scripts/ia3d/export_web.py and
// export_face_anims.py write them to ../work/ia3d/web) into public/models and
// resamples the animation and compresses the GLB with meshopt (the compressed GLB is what Vercel serves).
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
const tmp = join(src, 'morfi_live_resampled.glb');
execFileSync(process.execPath, [cli, 'resample', glb, tmp, '--tolerance', '0.0002'], { stdio: 'inherit' });
execFileSync(process.execPath, [cli, 'meshopt', tmp, join(dst, 'morfi_live.glb'), '--level', 'medium'], { stdio: 'inherit' });
console.log('compressed morfi_live.glb', (statSync(join(dst, 'morfi_live.glb')).size / 1e6).toFixed(2), 'MB');
