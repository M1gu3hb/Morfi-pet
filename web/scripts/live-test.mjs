// Headless test of "Morfi en vivo" (live.html): loads the real GLB, plays every
// animation, makes him speak, checks the face reacts, screenshots desktop and
// mobile, and fails on any console error.
//   npm run build && npm run test:live          (screenshots -> ../work/ia3d/viewer_test)
import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, '..', '..', 'work', 'ia3d', 'viewer_test');
mkdirSync(outDir, { recursive: true });
const pw = process.env.PLAYWRIGHT_BROWSERS_PATH ?? '';
const exe = [
  join(pw, 'chromium_headless_shell-1243', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe'),
  join(pw, 'chromium-1243', 'chrome-win64', 'chrome.exe'),
  '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell',
].find(existsSync);
if (!exe) throw new Error('no Chromium found (set PLAYWRIGHT_BROWSERS_PATH)');
const vite = join(here, '..', 'node_modules', 'vite', 'bin', 'vite.js');
const server = spawn(process.execPath, [vite, 'preview', '--port', '4318', '--strictPort'], { cwd: join(here, '..'), stdio: 'pipe' });
await new Promise((r) => setTimeout(r, 2500));
const gl = process.platform === 'win32' ? ['--use-angle=d3d11'] : ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'];
const browser = await chromium.launch({ executablePath: exe, args: [...gl, '--ignore-gpu-blocklist'] });
const errors = [];
let ok = true;
try {
  for (const [label, vp] of [['desktop', { width: 1280, height: 800 }], ['mobile', { width: 390, height: 844 }]]) {
    const page = await browser.newPage({ viewport: vp, deviceScaleFactor: 1 });
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${label}] ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`[${label}] ${e.message}`));
    page.setDefaultTimeout(180000);
    await page.goto('http://localhost:4318/live.html', { waitUntil: 'load' });
    await page.waitForFunction(() => window.__morfiReady === true, null, { timeout: 180000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: join(outDir, `${label}_idle.png`) });
    if (label === 'mobile') continue;
    const actions = await page.evaluate(() => window.morfi.actions);
    if (actions.length !== 10) throw new Error(`expected 10 animations, got ${actions.length}: ${actions}`);
    for (const name of actions) {
      await page.evaluate((n) => window.morfi.play(n), name);
      await page.waitForTimeout(name === 'Wave' ? 1300 : 900);
      await page.screenshot({ path: join(outDir, `${label}_${name}.png`) });
    }
    // speech must move the mouth (decal pixels change between two instants)
    const dur = await page.evaluate(() => window.morfi.speak('¡Hola! Soy Morfi. ¿En qué te ayudo hoy?'));
    if (!(dur > 1)) throw new Error(`speak returned ${dur}`);
    await page.waitForTimeout(700);
    const a = await page.screenshot({ path: join(outDir, `${label}_speak_a.png`) });
    await page.waitForTimeout(170);
    const b = await page.screenshot({ path: join(outDir, `${label}_speak_b.png`) });
    if (a.equals(b)) throw new Error('the face did not change while speaking');
    // postMessage API (for embedding in a chatbot widget)
    await page.evaluate(() => window.postMessage({ type: 'play', name: 'Nod_Yes' }, '*'));
    await page.waitForTimeout(600);
    await page.screenshot({ path: join(outDir, `${label}_postmessage_nod.png`) });
    await page.click('#bgs button[data-bg="dark"]');
    await page.waitForTimeout(400);
    await page.screenshot({ path: join(outDir, `${label}_dark.png`) });
  }
} catch (e) {
  ok = false;
  console.error(e);
} finally {
  await browser.close();
  server.kill();
}
if (errors.length) { ok = false; console.error('console errors:\n' + errors.join('\n')); }
console.log(ok ? 'LIVE TEST PASSED' : 'LIVE TEST FAILED', '->', outDir);
process.exit(ok ? 0 : 1);
