// Screenshots of the viewer holding animations at given times from given
// camera angles (development check of deformations as three.js skins them).
//   node scripts/pose-shots.mjs <outdir> '<json list of [clip, t, az, el, dist, label]>'
import { chromium } from 'playwright-core';
import { build, preview } from 'vite';
import { existsSync, mkdirSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, '..');
const out = resolve(process.argv[2] ?? join(web, '..', 'work', 'shots'));
const shots = JSON.parse(process.argv[3] ?? '[["Pose_Neutral",0,0,8,3.2,"neutral_front"]]');
mkdirSync(out, { recursive: true });
const exe = ['/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
await build({ root: web, logLevel: 'error' });
const server = await preview({ root: web, logLevel: 'error', preview: { port: 4323, strictPort: true } });
const browser = await chromium.launch({ executablePath: exe, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
try {
  const page = await browser.newPage({ viewport: { width: 800, height: 1000 }, deviceScaleFactor: 1 });
  page.on('pageerror', (e) => console.log('[pageerror]', e.message));
  await page.goto(`http://localhost:4323/?clean=1&lowpower=1${process.argv[4] ?? ''}`);
  await page.waitForFunction(() => window.__morfiReady === true, null, { timeout: 600000 });
  for (const [clip, t, az, el, dist, label] of shots) {
    await page.evaluate(([c, tt]) => window.__morfiPose(c, tt), [clip, t]);
    await page.evaluate(([a, e, d]) => window.__morfiOrbit(a, e, d), [az, el, dist]);
    await page.waitForTimeout(1200);
    await page.screenshot({ path: join(out, label + '.png'), timeout: 300000 });
    console.log(label);
  }
} finally {
  await browser.close();
  await new Promise((r) => server.httpServer.close(r));
}
