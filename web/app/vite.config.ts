import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Builds to `web/landing/`, which the Python console server already serves as
 * static files. One server, one origin, no second runtime — the delivery model
 * stays "a Python process serves everything" (FE-SYSTEM-REVIEW §4, Q1 → C).
 *
 * `base` is absolute because the built page is served from a fixed path rather
 * than a domain root, and a relative base breaks the moment a route nests.
 */
export default defineConfig({
  plugins: [react()],
  base: '/web/landing/',
  build: {
    outDir: '../landing',
    emptyOutDir: true,
    target: 'es2022',
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        // three is ~600KB and changes rarely; splitting it means a copy change
        // does not invalidate the engine in a returning visitor's cache.
        // Vite 8 runs on Rolldown, which takes the FUNCTION form only — the
        // object form fails the build with "manualChunks is not a function".
        manualChunks(id: string) {
          if (id.includes('node_modules/three')) return 'three';
          if (id.includes('node_modules/react')) return 'react';
          return undefined;
        },
      },
    },
  },
});
