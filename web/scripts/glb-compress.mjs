// The lab's GLB compression, shared by sync-live.mjs and sync-tests.mjs: every clip is sampled at 30 fps
// for every bone, so first drop the keys a curve does not need (constant channels, straight segments),
// then compress with meshopt (the compressed GLBs are what Vercel serves).
import { execFileSync } from 'node:child_process';
import { rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
// the CLI through node itself: no shell, so paths with spaces are safe on Windows
export const CLI = join(here, '..', 'node_modules', '@gltf-transform', 'cli', 'bin', 'cli.js');

/** src (raw GLB from Blender) -> dst (compressed). The resampled intermediate goes to tmp and is removed with `clean`. */
export function compressGlb(src, dst, tmp = src.replace(/\.glb$/, '_resampled.glb'), clean = false) {
  execFileSync(process.execPath, [CLI, 'resample', src, tmp, '--tolerance', '0.0002'], { stdio: 'inherit' });
  execFileSync(process.execPath, [CLI, 'meshopt', tmp, dst, '--level', 'medium'], { stdio: 'inherit' });
  if (clean) rmSync(tmp, { force: true });
}
