// Headless browser test of the viewer: loads the real GLB, exercises every
// control, captures screenshots and fails on console errors.
import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import { mkdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, '..', '..', 'renders', 'viewer');
mkdirSync(outDir, { recursive: true });
const pw = process.env.PLAYWRIGHT_BROWSERS_PATH ?? '';
const exe = [join(pw, 'chromium_headless_shell-1243', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe'), '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell', '/opt/pw-browsers/chromium_headless_shell-1194/chrome-headless-shell-linux64/chrome-headless-shell', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
// vite through node itself (no npx / shell: works the same on Windows)
const server = spawn(process.execPath, [join(here, '..', 'node_modules', 'vite', 'bin', 'vite.js'), 'preview', '--port', '4317', '--strictPort'], { cwd: join(here, '..'), stdio: 'pipe' });
await new Promise((r) => setTimeout(r, 2500));
const browser = await chromium.launch({ executablePath: exe, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const errors = [];
let ok = true;
try {
  for (const [label, vp] of [['desktop', { width: 1100, height: 760 }], ['mobile', { width: 390, height: 844 }]]) {
    const page = await browser.newPage({ viewport: vp, deviceScaleFactor: 1 });
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${label}] ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`[${label}] ${e.message}`));
    page.setDefaultTimeout(180000);
    await page.goto('http://localhost:4317/tecnico.html?lowpower=1', { waitUntil: 'load' });
    await page.waitForFunction(() => window.__morfiReady === true, null, { timeout: 180000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: join(outDir, `${label}_front.png`) });
    if (label === 'desktop') {
      for (const v of ['three_quarter_front', 'profile_left', 'back']) {
        await page.click(`#views button[data-view="${v}"]`);
        await page.waitForTimeout(800);
        await page.screenshot({ path: join(outDir, `${label}_${v}.png`) });
      }
      // back view with the light rig fixed in the world (darker, like before the product lighting)
      await page.click('#lightsFollow');
      await page.waitForTimeout(500);
      await page.screenshot({ path: join(outDir, `${label}_back_world_lights.png`) });
      await page.click('#lightsFollow');
      await page.click('#views button[data-view="front"]');
      await page.selectOption('#anim', 'Pose_Hero');
      await page.waitForTimeout(1200);
      await page.screenshot({ path: join(outDir, `${label}_hero.png`) });
      await page.selectOption('#anim', 'Walk');
      await page.waitForTimeout(700);
      await page.screenshot({ path: join(outDir, `${label}_walk.png`) });
      await page.selectOption('#anim', 'Pose_Neutral');
      await page.click('#preset-base');
      await page.waitForTimeout(600);
      await page.screenshot({ path: join(outDir, `${label}_base_body.png`) });
      await page.click('#preset-full');
      await page.click('#modes button[data-mode="clay"]');
      await page.waitForTimeout(600);
      await page.screenshot({ path: join(outDir, `${label}_clay.png`) });
      await page.click('#modes button[data-mode="wire"]');
      await page.waitForTimeout(600);
      await page.screenshot({ path: join(outDir, `${label}_wire.png`) });
      await page.click('#modes button[data-mode="material"]');
      await page.click('#bgs button[data-bg="dark"]');
      await page.waitForTimeout(600);
      await page.screenshot({ path: join(outDir, `${label}_dark.png`) });
      await page.click('#bgs button[data-bg="light"]');
      // physical shader, then back to the photo-matched one
      await page.click('#shading button[data-shading="pbr"]');
      await page.waitForTimeout(600);
      await page.screenshot({ path: join(outDir, `${label}_pbr.png`) });
      await page.click('#shading button[data-shading="ref"]');
      // compare with the reference photo, every mode, on the profile (face cheat morph)
      await page.click('#views button[data-view="profile_left"]');
      for (const m of ['overlay', 'wipe', 'diff', 'side']) {
        await page.click(`#compare-modes button[data-cmp="${m}"]`);
        await page.waitForTimeout(700);
        await page.screenshot({ path: join(outDir, `${label}_compare_${m}.png`) });
      }
      await page.click('#compare-modes button[data-cmp="off"]');
      await page.click('#views button[data-view="front"]');
      // sound: music on / off, and poke Morfi (boop + bounce)
      await page.click('#music');
      await page.waitForTimeout(300);
      await page.click('#music');
      const box = await page.locator('#view').boundingBox();
      await page.mouse.click(box.x + box.width / 2, box.y + box.height * 0.3);
      await page.waitForTimeout(300);
      const [dl] = await Promise.all([page.waitForEvent('download'), page.click('#shot')]);
      await dl.saveAs(join(outDir, 'capture_from_viewer.png'));
      const stats = await page.textContent('#stats');
      console.log('stats:', stats);
    }
    await page.close();
  }
} catch (e) {
  ok = false;
  console.error('FAILED', e);
} finally {
  await browser.close();
  server.kill();
}
if (errors.length) { console.error('console errors:\n' + errors.join('\n')); ok = false; }
console.log(ok ? 'SMOKE TEST PASSED' : 'SMOKE TEST FAILED');
process.exit(ok ? 0 : 1);
