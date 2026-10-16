import { execSync } from 'node:child_process';
import { resolve } from 'node:path';
import { defineConfig } from 'vite';

// which version of the model the page shows (Vercel sets the commit env vars)
function commit() {
  if (process.env.VERCEL_GIT_COMMIT_SHA) return process.env.VERCEL_GIT_COMMIT_SHA.slice(0, 7);
  try { return execSync('git rev-parse --short HEAD').toString().trim(); } catch { return 'local'; }
}

export default defineConfig({
  base: './',
  build: {
    outDir: 'dist', assetsInlineLimit: 0, chunkSizeWarningLimit: 1200,
    // two pages: the technical viewer of the procedural model and Morfi en vivo
    rollupOptions: { input: { main: resolve(__dirname, 'index.html'), live: resolve(__dirname, 'live.html') } },
  },
  server: { host: true },
  define: {
    __BUILD_INFO__: JSON.stringify({ commit: commit(), date: new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC' }),
  },
});
