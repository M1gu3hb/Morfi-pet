// Compresses the test performances (model comparison) that scripts/ia3d/export_test.py wrote to
// ../work/ia3d/web/tests/<id>.glb into public/models/tests/<id>.glb (resample + meshopt). The matching
// public/models/tests/<id>.json and public/voice/tests/<id>.mp3 are written by the exporter itself.
//   node scripts/sync-tests.mjs            every test found
//   node scripts/sync-tests.mjs opus       only that one (what export_test.py runs after exporting)
import { existsSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { compressGlb } from './glb-compress.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', '..', 'work', 'ia3d', 'web', 'tests');
const dst = join(here, '..', 'public', 'models', 'tests');

/** Compress the given ids (all the raw GLBs in work/ia3d/web/tests when none). Returns the ids done. */
export function syncTests(ids = []) {
  if (!existsSync(src)) {
    if (ids.length) throw new Error(`missing ${src} (run scripts/ia3d/export_test.py first)`);
    return [];
  }
  const all = readdirSync(src).filter((f) => /^[a-z0-9]+\.glb$/.test(f)).map((f) => f.replace(/\.glb$/, ''));
  const todo = ids.length ? ids : all;
  mkdirSync(dst, { recursive: true });
  for (const id of todo) {
    if (!/^[a-z0-9]+$/.test(id)) throw new Error(`bad test id ${id}`);
    const glb = join(src, id + '.glb');
    if (!existsSync(glb)) throw new Error(`missing ${glb} (run scripts/ia3d/export_test.py for ${id})`);
    if (!existsSync(join(dst, id + '.json'))) throw new Error(`missing ${join(dst, id + '.json')}: the exporter writes it with the GLB`);
    compressGlb(glb, join(dst, id + '.glb'), join(src, id + '_resampled.glb'), true);
    console.log('compressed test', id, (statSync(join(dst, id + '.glb')).size / 1e6).toFixed(2), 'MB');
  }
  return todo;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const done = syncTests(process.argv.slice(2));
  console.log(done.length ? `synced tests: ${done.join(', ')}` : 'no tests to sync');
}
