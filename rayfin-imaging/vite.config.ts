import { rayfinLocalDev } from '@microsoft/rayfin-local-dev/vite';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { createReadStream, readdirSync, readFileSync } from 'fs';
import { defineConfig, loadEnv, type Plugin } from 'vite';
import { resolve } from 'path';

import { localMode } from './local/plugin';

const projectRoot = process.env.PROJECT_ROOT || import.meta.dirname;

// PDF.js loads its image decoders (CCITT/JBIG2, JPEG 2000, colour profiles) and the standard PDF fonts from directory
// URLs at runtime, so the files keep their names: served from node_modules in dev and copied to dist/pdfjs/ on build.
function pdfjsAssets(): Plugin {
  const root = resolve(projectRoot, 'node_modules/pdfjs-dist');
  const dirs: Record<string, (name: string) => boolean> = {
    wasm: (n) => /^(jbig2|openjpeg|qcms_bg)(\.wasm|_nowasm_fallback\.js)$/.test(n),
    standard_fonts: (n) => /\.(pfb|ttf)$/.test(n),
  };
  const files = () => Object.entries(dirs).flatMap(([dir, keep]) => readdirSync(resolve(root, dir)).filter(keep).map((n) => `${dir}/${n}`));
  const types: Record<string, string> = { wasm: 'application/wasm', js: 'text/javascript', pfb: 'application/octet-stream', ttf: 'font/ttf' };
  return {
    name: 'pdfjs-assets',
    configureServer(server) {
      const served = new Set(files());
      server.middlewares.use('/pdfjs', (req, res, next) => {
        const name = (req.url ?? '').split('?')[0].replace(/^\//, '');
        if (!served.has(name)) return next();
        res.setHeader('Content-Type', types[name.split('.').pop() ?? ''] ?? 'application/octet-stream');
        createReadStream(resolve(root, name)).pipe(res);
      });
    },
    generateBundle() {
      for (const name of files()) this.emitFile({ type: 'asset', fileName: `pdfjs/${name}`, source: readFileSync(resolve(root, name)) });
    },
  };
}

// https://vite.dev/config/
export default defineConfig(({ mode, command }) => {
  // Pin the dev server to Rayfin's per-project port (VITE_PORT, mapped from
  // RAYFIN_PUBLIC_FRONTEND_PORT in .env.local) so multiple local frontends
  // don't collide and the deployed backend can allow-list one stable origin.
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const port = env.VITE_PORT ? Number(env.VITE_PORT) : undefined;
  // Fail the production build early when the Rayfin publishable key is missing
  // for a remote backend. Vite statically inlines `import.meta.env.*`, so an
  // unset key would otherwise ship as `undefined` and only crash at runtime.
  // A localhost API URL resolves to the local-dev path, which needs no key.
  if (command === 'build') {
    const apiUrl = env.VITE_RAYFIN_API_URL;
    const isRemoteBackend =
      !!apiUrl && !/^https?:\/\/(localhost|127\.0\.0\.1)([:/]|$)/.test(apiUrl);
    if (isRemoteBackend && !env.VITE_RAYFIN_PUBLISHABLE_KEY) {
      throw new Error(
        'Missing required Rayfin client environment variable: VITE_RAYFIN_PUBLISHABLE_KEY.\n' +
          'Regenerate .env.local from rayfin/.env with: rayfin env --framework vite\n' +
          '(run `rayfin up` first if rayfin/.env has not been populated yet).'
      );
    }
  }
  // Local mode (`npm run dev:local`, .env.localdata): no Fabric; the dev server serves the data from work/.
  const localData = env.VITE_LOCAL_DATA === '1';
  return {
    plugins: [react(), tailwindcss(), localData ? localMode(projectRoot) : rayfinLocalDev(), pdfjsAssets()],
    resolve: {
      alias: {
        '@': resolve(projectRoot, 'src'),
      },
    },
    ...(port ? { server: { port, strictPort: true } } : {}),
    build: {
      // Target ES2022 for modern JavaScript decorators
      target: 'es2022',
    },
    esbuild: {
      target: 'es2022',
    },
    optimizeDeps: {
      esbuildOptions: {
        target: 'es2022',
      },
    },
  };
});
