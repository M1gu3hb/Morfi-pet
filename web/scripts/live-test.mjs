// Headless test of "Morfi en vivo" (index.html, the landing page): loads the real GLB, plays every
// animation (props must show up in Tablet / Calculator), layers every facial expression, makes him
// speak (text and the real voice), plays a full scene in sync with its audio, toggles the outline,
// opens and closes the panels on a phone, screenshots desktop and mobile, and fails on any console error.
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
const browser = await chromium.launch({ executablePath: exe, args: [...gl, '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required'] });
const errors = [];
let ok = true;
try {
  for (const [label, vp] of [['desktop', { width: 1280, height: 800 }], ['mobile', { width: 390, height: 844 }]]) {
    const page = await browser.newPage({ viewport: vp, deviceScaleFactor: 1 });
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${label}] ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`[${label}] ${e.message}`));
    page.setDefaultTimeout(180000);
    await page.goto('http://localhost:4318/index.html', { waitUntil: 'load' });
    await page.waitForFunction(() => window.__morfiReady === true, null, { timeout: 180000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: join(outDir, `${label}_idle.png`) });
    if (label === 'mobile') {
      // touch-first panels: the toolbar toggle opens the sheet, its close button hides it
      await page.click('#panel-toggle');
      await page.waitForTimeout(500);
      await page.screenshot({ path: join(outDir, `${label}_panel.png`) });
      const open = await page.evaluate(() => !document.getElementById('panel').classList.contains('collapsed'));
      if (!open) throw new Error('the Controles sheet did not open on mobile');
      const small = await page.evaluate(() => [...document.querySelectorAll('#panel button')]
        .filter((b) => b.offsetParent && b.getBoundingClientRect().height < 43.5).map((b) => b.textContent.trim()));
      if (small.length) throw new Error(`touch targets under 44 px: ${small.slice(0, 8)}`);
      continue;
    }
    const actions = await page.evaluate(() => window.morfi.actions);
    const baked = await page.evaluate(async () => Object.keys((await (await fetch('./models/morfi_live_anims.json')).json()).actions));
    if (actions.length < 26 || actions.length !== baked.length) throw new Error(`expected ${baked.length} animations (>= 26), got ${actions.length}`);
    const raw = await page.evaluate(() => [...document.querySelectorAll('button[data-anim]')]
      .filter((b) => b.textContent.trim() === b.dataset.anim).map((b) => b.dataset.anim));
    if (raw.length) throw new Error(`buttons without a Spanish label: ${raw}`);
    const LONG = { Wave: 1300, Tablet: 2700, Calculator: 2300, Count_123: 2200, Think: 1800, Scared: 1500, Sad: 2000, Scratch_Head: 1600, Facepalm: 1500 };
    for (const name of actions) {
      await page.evaluate((n) => window.morfi.play(n), name);
      await page.waitForTimeout(LONG[name] ?? 1100);
      await page.screenshot({ path: join(outDir, `${label}_${name}.png`) });
    }
    // the props are only visible while their clip plays (bone scale 0 otherwise)
    const propScale = (n) => page.evaluate((nm) => {
      let s = -1;
      document.querySelector('canvas');
      window.__morfiScene?.traverse((o) => { if (o.name === nm) s = o.getWorldScale(new o.position.constructor()).x; });
      return s;
    }, n);
    await page.evaluate(() => window.morfi.play('Idle'));
    await page.waitForTimeout(900);
    const hidden = await propScale('Prop_Tablet');
    await page.evaluate(() => window.morfi.play('Tablet'));
    await page.waitForTimeout(1500);
    const shown = await propScale('Prop_Tablet');
    if (!(hidden >= 0 && hidden < 0.01 && shown > 0.9)) throw new Error(`tablet scale idle ${hidden}, in clip ${shown}`);
    // facial expressions layered on Idle: each must change the face
    await page.evaluate(() => window.morfi.play('Idle'));
    await page.waitForTimeout(800);
    const exprs = await page.evaluate(() => window.morfi.expressions);
    if (exprs.length < 18) throw new Error(`expected 18 expressions, got ${exprs.length}`);
    await page.evaluate(() => window.morfi.follow(false));
    for (const e of exprs) {
      await page.evaluate((n) => window.morfi.expression(n), e);
      await page.waitForTimeout(650);
      await page.screenshot({ path: join(outDir, `${label}_expr_${e}.png`), clip: { x: 340, y: 60, width: 520, height: 420 } });
    }
    await page.evaluate(() => window.morfi.expression('neutral'));
    await page.waitForTimeout(700);
    const n0 = await page.screenshot({ clip: { x: 340, y: 60, width: 520, height: 420 } });
    await page.evaluate(() => window.postMessage({ type: 'expression', name: 'surprised' }, '*'));
    await page.waitForTimeout(700);
    const n1 = await page.screenshot({ clip: { x: 340, y: 60, width: 520, height: 420 } });
    if (n0.equals(n1)) throw new Error('the expression did not change the face');
    await page.evaluate(() => { window.morfi.expression('neutral'); window.morfi.follow(true); });
    // speech must move the mouth (decal pixels change between two instants)
    const dur = await page.evaluate(() => window.morfi.speak('¡Hola! Soy Morfi. ¿En qué te ayudo hoy?'));
    if (!(dur > 1)) throw new Error(`speak returned ${dur}`);
    await page.waitForTimeout(700);
    const a = await page.screenshot({ path: join(outDir, `${label}_speak_a.png`) });
    await page.waitForTimeout(170);
    const b = await page.screenshot({ path: join(outDir, `${label}_speak_b.png`) });
    if (a.equals(b)) throw new Error('the face did not change while speaking');
    // the real voice: a preset phrase plays its mp3 and the mouth follows the audio clock
    await page.evaluate(() => window.morfi.say('hola'));
    // the mp3 may take a moment to load on a busy machine: wait for the audio clock instead of a fixed delay
    await page.waitForFunction(() => window.morfi.status.audioTime > 0.3, null, { timeout: 8000 }).catch(() => {});
    const st = await page.evaluate(() => window.morfi.status);
    if (st.saying !== 'hola' || !(st.audioTime > 0.3)) throw new Error(`say(): ${JSON.stringify(st)}`);
    const sa = await page.screenshot({ clip: { x: 340, y: 60, width: 520, height: 420 } });
    await page.waitForTimeout(140);
    const sb = await page.screenshot({ path: join(outDir, `${label}_say.png`), clip: { x: 340, y: 60, width: 520, height: 420 } });
    if (sa.equals(sb)) throw new Error('the mouth did not move with the voice');
    await page.waitForTimeout(2500);
    // a full scene: the body's time is the audio's time
    const scenes = await page.evaluate(async () => { await window.morfi.scene('__none__'); return window.morfi.scenes; });
    if (!scenes.length) throw new Error('no scenes loaded');
    for (const sc of [scenes.find((x) => x.group === 'scene') ?? scenes[0], scenes.find((x) => x.group === 'video')].filter(Boolean)) {
      if (!(await page.evaluate((k) => window.morfi.scene(k), sc.key))) throw new Error(`scene ${sc.key} did not start`);
      await page.waitForTimeout(3000);
      const ss = await page.evaluate(() => window.morfi.status);
      if (!ss.scene || !(ss.scene.t > 2) || Math.abs(ss.scene.t - ss.sceneTime) > 0.1) throw new Error(`scene ${sc.key}: ${JSON.stringify(ss)}`);
      await page.screenshot({ path: join(outDir, `${label}_scene_${sc.key}.png`) });
      await page.evaluate(() => window.morfi.stop());
      await page.waitForTimeout(800);
    }
    // the outline ("Estilo") can be turned off and on
    await page.evaluate(() => window.morfi.play('Idle'));
    await page.waitForTimeout(600);
    await page.evaluate(() => window.morfiStyle.outline(false));
    await page.waitForTimeout(300);
    const o0 = await page.screenshot({ path: join(outDir, `${label}_outline_off.png`) });
    await page.evaluate(() => window.morfiStyle.outline(true));
    await page.waitForTimeout(300);
    const o1 = await page.screenshot({ path: join(outDir, `${label}_outline_on.png`) });
    if (o0.equals(o1)) throw new Error('the outline switch changed nothing');
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
