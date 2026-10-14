import { execSync } from 'node:child_process';
import { defineConfig } from 'vite';

// which version of the model the page shows (Vercel sets the commit env vars)
function commit() {
  if (process.env.VERCEL_GIT_COMMIT_SHA) return process.env.VERCEL_GIT_COMMIT_SHA.slice(0, 7);
  try { return execSync('git rev-parse --short HEAD').toString().trim(); } catch { return 'local'; }
}

export default defineConfig({
  base: './',
  build: { outDir: 'dist', assetsInlineLimit: 0, chunkSizeWarningLimit: 1200 },
  server: { host: true },
  define: {
    __BUILD_INFO__: JSON.stringify({ commit: commit(), date: new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC' }),
  },
});
