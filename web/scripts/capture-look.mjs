// Runs web/capture.html in headless Chromium and saves the per-material
// shading statistics measured against the reference photos to
// work/look/raw.json (then: python3 scripts/build_look.py).
import { chromium } from 'playwright-core';
import { createServer } from 'vite';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, '..');
const repo = resolve(web, '..');
const model = process.argv[2] ?? './models/morfi_web.glb';
const exe = ['/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell', '/opt/pw-browsers/chromium_headless_shell-1194/chrome-headless-shell-linux64/chrome-headless-shell', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
const server = await createServer({ root: web, logLevel: 'error', server: { port: 4319, strictPort: true, fs: { allow: [repo] } } });
await server.listen();
const browser = await chromium.launch({ executablePath: exe, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
try {
  const page = await browser.newPage();
  page.on('console', (m) => console.log('[page]', m.text()));
  page.on('pageerror', (e) => console.log('[pageerror]', e.message));
  const refs = '/@fs' + join(repo, 'work', 'look', 'refs') + '/';
  await page.goto(`http://localhost:4319/capture.html?refs=${encodeURIComponent(refs)}&model=${encodeURIComponent(model)}`);
  await page.waitForFunction(() => window.__capture !== undefined, null, { timeout: 1800000 });
  const res = await page.evaluate(() => window.__capture);
  if (res.error) throw new Error(res.error);
  mkdirSync(join(repo, 'work', 'look'), { recursive: true });
  writeFileSync(join(repo, 'work', 'look', 'raw.json'), JSON.stringify(res));
  console.log('saved work/look/raw.json', Object.keys(res.materials).length, 'materials');
} finally {
  await browser.close();
  await server.close();
}
