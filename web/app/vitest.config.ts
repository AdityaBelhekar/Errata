import { defineConfig } from 'vitest/config';

/**
 * Unit tests for `lib.ts` — the pure functions the whole procession rests on.
 *
 * Separate from `vite.config.ts` on purpose: that file carries the production
 * build's `base`, `outDir` and manual chunking, none of which a test run should
 * inherit or be able to disturb.
 *
 * `jsdom` rather than `node` because `tier()` reads `location`, `matchMedia`,
 * `navigator` and a canvas context. Those are exactly the branches that have
 * never executed on real hardware, so a test environment that cannot express
 * them would leave the untested part untested.
 */
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/lib.ts'],
      // Reported, not gated. A coverage threshold introduced at the same time as
      // the first tests is a number nobody has calibrated, and the usual result
      // is tests written to move it rather than to catch anything.
      reporter: ['text', 'json-summary'],
    },
  },
});
