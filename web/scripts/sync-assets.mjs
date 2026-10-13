// Copies the exported GLB(s) from ../exports into public/models so the viewer
// always loads the real exported asset (no geometry is rebuilt in the browser).
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', '..', 'exports');
const dst = join(here, '..', 'public', 'models');
mkdirSync(dst, { recursive: true });
for (const f of ['morfi_web.glb', 'morfi_master.glb']) {
  const s = join(src, f);
  if (existsSync(s)) { copyFileSync(s, join(dst, f)); console.log('synced', f); }
  else console.warn('missing', s);
}
// calibrated camera of every reference shot (+ which shots have a Ref_ pose)
const cfg = JSON.parse(readFileSync(join(here, '..', '..', 'config', 'morfi.json'), 'utf8'));
const views = { camera_views: {}, poses: [] };
for (const [k, v] of Object.entries(cfg.camera_views ?? {})) if (!k.startsWith('_')) views.camera_views[k] = v;
for (const k of Object.keys(cfg.view_poses ?? {})) if (!k.startsWith('_')) views.poses.push(k);
writeFileSync(join(dst, 'views.json'), JSON.stringify(views, null, 1));
console.log('synced views.json', Object.keys(views.camera_views).length, 'cameras');
