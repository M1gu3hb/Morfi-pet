// Copies the exported GLB(s) from ../exports into public/models so the viewer
// always loads the real exported asset (no geometry is rebuilt in the browser).
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
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
