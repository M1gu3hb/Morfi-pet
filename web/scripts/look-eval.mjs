// Renders the viewer at every calibrated reference shot (1145x1374, exact
// lens) in both shaders and saves the frames to work/look/eval/<shader>/<view>.png
// (then: python3 scripts/eval_look.py compares them with the photos).
import { chromium } from 'playwright-core';
import { build, preview } from 'vite';
import { existsSync, mkdirSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, '..');
const repo = resolve(web, '..');
const exe = ['/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell', '/opt/pw-browsers/chromium_headless_shell-1194/chrome-headless-shell-linux64/chrome-headless-shell', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
// a production build served statically: no hot reload while the frames are taken
await build({ root: web, logLevel: 'error' });
const server = await preview({ root: web, logLevel: 'error', preview: { port: 4321, strictPort: true } });
const browser = await chromium.launch({ executablePath: exe, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const views = ['front', 'three_quarter_front', 'profile_left', 'profile_right', 'back', 'three_quarter_back'];
const shaders = (process.argv[2] ?? 'ref').split(',');
try {
  for (const sh of shaders) {
    const out = join(repo, 'work', 'look', 'eval', sh);
    mkdirSync(out, { recursive: true });
    const page = await browser.newPage({ viewport: { width: 1145, height: 1374 }, deviceScaleFactor: 1 });
    page.on('pageerror', (e) => console.log('[pageerror]', e.message));
    page.on('console', (m) => { if (m.type() === 'error') console.log('[console]', m.text()); });
    await page.goto(`http://localhost:4321/?clean=1&exact=1&lowpower=1&shading=${sh}`);
    await page.waitForFunction(() => window.__morfiReady === true, null, { timeout: 600000 });
    for (const v of views) {
      await page.evaluate((vv) => window.__morfiSetView(vv), v);
      await page.waitForTimeout(1500);
      await page.screenshot({ path: join(out, v + '.png'), clip: { x: 0, y: 0, width: 1145, height: 1374 }, timeout: 300000 });
      console.log(sh, v);
    }
    await page.close();
  }
} finally {
  await browser.close();
  await new Promise((r) => server.httpServer.close(r));
}
