// Headless test of the lab's "Prueba" section (the model-comparison performances), against a server that is
// already running (your own dev server: `npx vite --port 5210 --strictPort`):
//   node scripts/prueba-test.mjs --url http://localhost:5210/ [--ready haiku3,opus] [--exact]
// --ready: ids that must be published (public/models/tests/<id>.json exists: play button, cost lines, they play; the
// first one is played). Any other id of index.json may be either; with --exact it must say "En preparación". Checks: nothing under models/tests/ is fetched before
// the section is opened, the GLB only when an entry is played, the cost lines, 44 px targets on a phone,
// and zero console errors. Screenshots go to ../work/ia3d/viewer_test/prueba_*.png.
import { chromium } from 'playwright-core';
import { existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const arg = (k, d = '') => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const url = arg('--url', 'http://localhost:5210/');
const ready = arg('--ready', '').split(',').filter(Boolean);
const exact = process.argv.includes('--exact');
const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, '..', '..', 'work', 'ia3d', 'viewer_test');
mkdirSync(outDir, { recursive: true });
const pw = process.env.PLAYWRIGHT_BROWSERS_PATH ?? 'D:/_cache-dev/playwright';
const exe = [
  join(pw, 'chromium_headless_shell-1243', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe'),
  join(pw, 'chromium-1243', 'chrome-win64', 'chrome.exe'),
].find(existsSync);
if (!exe) throw new Error('no Chromium found (set PLAYWRIGHT_BROWSERS_PATH)');
const browser = await chromium.launch({ executablePath: exe, args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required'] });
const errors = [];
let ok = true;
const need = (cond, msg) => { if (!cond) throw new Error(msg); };
try {
  for (const [label, vp] of [['desktop', { width: 1280, height: 800 }], ['mobile', { width: 390, height: 844 }]]) {
    const page = await browser.newPage({ viewport: vp, deviceScaleFactor: 1 });
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${label}] ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`[${label}] ${e.message}`));
    page.setDefaultTimeout(120000);
    const asked = [];
    page.on('request', (r) => { if (r.url().includes('/models/tests/')) asked.push(r.url().split('/models/tests/')[1]); });
    await page.goto(url, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__morfiReady === true, null, { timeout: 120000 });
    if (label === 'mobile') { await page.click('#panel-toggle'); await page.waitForTimeout(500); }
    await page.waitForTimeout(3500);                            // past the idle load of the scenes
    need(asked.length === 0, `[${label}] models/tests/ was fetched before the section was opened: ${asked}`);
    const sum = page.locator('#h-tests');
    await sum.scrollIntoViewIfNeeded();
    const h = (await sum.boundingBox()).height;
    need(h >= 43.5, `[${label}] the Prueba summary is ${h} px tall (< 44)`);
    await sum.click();
    await page.waitForSelector('#tests .test');
    const cards = await page.evaluate(() => [...document.querySelectorAll('#tests .test')].map((c) => ({
      id: c.dataset.test, pending: c.classList.contains('pending'), text: c.innerText.replace(/\s+/g, ' ').trim(), play: !!c.querySelector('button'),
    })));
    const index = await page.evaluate(async () => (await (await fetch('./models/tests/index.json')).json()).map((i) => i.id));
    need(cards.length === index.length && cards.every((c, i) => c.id === index[i]), `[${label}] cards ${cards.map((c) => c.id)} != index ${index}`);
    for (const c of cards) {
      const should = ready.includes(c.id);
      if (should || exact) need(c.pending !== should, `[${label}] ${c.id}: ${should ? 'should be ready' : 'should be pending'}: ${c.text}`);
      if (c.pending) need(c.text.includes('En preparación') && !c.play, `[${label}] ${c.id} pending card: ${c.text}`);
      else need(/Creación .* · Revisión .* · Publicación .* · Total /.test(c.text) && /Cambios en la revisión: /.test(c.text), `[${label}] ${c.id} cost lines: ${c.text}`);
    }
    console.log(label, 'cards:', cards.map((c) => `${c.id}${c.pending ? ' (en preparación)' : ''}`).join(', '));
    need(!asked.some((f) => f.endsWith('.glb')), `[${label}] a GLB was fetched before any play: ${asked}`);
    const small = await page.evaluate(() => [...document.querySelectorAll('#panel button, #panel summary')]
      .filter((b) => b.offsetParent && b.getBoundingClientRect().height < 43.5).map((b) => b.textContent.trim().slice(0, 30)));
    need(!small.length, `[${label}] touch targets under 44 px: ${small}`);
    await page.screenshot({ path: join(outDir, `prueba_${label}_list.png`) });
    if (label === 'desktop' && ready.length) {
      const id = ready[0];
      await page.click(`#tests .test[data-test="${id}"] button`);
      await page.waitForFunction(() => window.morfi.status.scene && window.morfi.status.scene.t > 1.5, null, { timeout: 90000 });
      const st = await page.evaluate(() => window.morfi.status);
      need(Math.abs(st.scene.t - st.sceneTime) < 0.15, `scene time ${st.scene.t} vs body time ${st.sceneTime}`);
      need(asked.some((f) => f === `${id}.glb`), `the GLB of ${id} was not fetched on play: ${asked}`);
      need(await page.evaluate((k) => document.querySelector(`button[data-scene="${k}"]`)?.classList.contains('on'), st.scene.key), 'the playing card is not marked');
      await page.screenshot({ path: join(outDir, `prueba_${label}_playing.png`) });
      console.log('playing', st.scene.key, 'title', JSON.stringify(st.scene.title), 't', st.scene.t.toFixed(2), 'cinema', st.cinema);
      await page.evaluate(() => window.morfi.stop());
      await page.waitForTimeout(1500);
      need((await page.evaluate(() => window.morfi.status.playing)) === 'Idle', 'Morfi did not go back to Idle');
    }
    await page.close();
  }
} catch (e) {
  ok = false;
  console.error(e);
} finally {
  await browser.close();
}
if (errors.length) { ok = false; console.error('console errors:\n' + errors.join('\n')); }
console.log(ok ? 'PRUEBA TEST PASSED' : 'PRUEBA TEST FAILED', '->', outDir);
process.exit(ok ? 0 : 1);
