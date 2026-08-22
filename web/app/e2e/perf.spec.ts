/**
 * §11.9 states its budgets as "spec, not aspiration". **Not one had ever been
 * recorded** — the test register's §4.1 said so, and FE-5's actual gate ("perf
 * budget met *before* integration") was therefore not met, because materials were
 * integrated first.
 *
 * This file records them. Two rules govern how, both of which exist because a
 * performance suite is unusually easy to make meaningless:
 *
 * 1. **Ceilings come from the measurement, not from the aspiration.** A budget
 *    nobody can meet gets switched off within a week — the same reasoning
 *    `scripts/ci.sh` already applies to mypy. Each ceiling below is the observed
 *    value plus stated headroom, so it catches a regression rather than
 *    re-litigating the current design.
 * 2. **A budget must not be met by breaking the page.** Every ceiling here is
 *    paired with an assertion that the thing still works, because the cheapest way
 *    to pass a bundle budget is to lazy-load something first paint needs.
 *
 * Measured on one machine, one run, headless Chromium. That is stated rather than
 * implied: these numbers are a regression tripwire, not a benchmark, and the
 * absolute values will differ on a runner. Anything quoted externally needs a
 * controlled measurement this is not.
 */

import { expect, test } from '@playwright/test';

// One project only, enforced in playwright.config.ts via `testIgnore` rather than here. A
// `browserName !== 'chromium'` guard does NOT skip the `mobile` project, which is also Chromium —
// so the desktop budgets ran against a phone profile and failed for a reason that was about the
// harness. The same mistake was made once in visual.spec.ts; it is made in one place now.
test.describe('§11.9 — the budgets, recorded', () => {

  test('initial transfer stays under budget, and the page still renders', async ({ page }) => {
    // The INITIAL load only: three.js and the scene are dynamically imported, so counting them
    // here would measure something no visitor waits for before seeing the page.
    const transferred = new Map<string, number>();

    page.on('response', async (response) => {
      const url = response.url();
      if (!url.includes('/web/landing/')) return;
      try {
        const body = await response.body();
        transferred.set(url, body.length);
      } catch {
        /* redirects and aborted requests have no body; they cost nothing to download */
      }
    });

    await page.goto('/web/landing/index.html', { waitUntil: 'load' });

    // The document, its stylesheet, the runtime, react and the entry chunk — everything the
    // browser needs before the first frame. The scene chunk arrives later, on its own budget.
    const initial = [...transferred.entries()]
      .filter(([url]) => !url.includes('Scene-') && !url.includes('three-'))
      .reduce((total, [, bytes]) => total + bytes, 0);

    // eslint-disable-next-line no-console
    console.log(`PERF initial_transfer_uncompressed_bytes=${initial}`);

    // ~78 KB gzipped / ~340 KB raw at the time of writing. 450 KB raw leaves room for copy and a
    // component or two without letting the engine creep into the first paint.
    expect(initial, 'initial payload grew past its budget').toBeLessThan(450_000);

    // The paired assertion: the budget must not be met by shipping a page that does not work.
    await expect(page.locator('h1').first()).toBeVisible();
  });

  test('LCP and CLS are recorded, and CLS stays near zero', async ({ page }) => {
    await page.goto('/web/landing/index.html', { waitUntil: 'load' });

    const vitals = await page.evaluate(
      () =>
        new Promise<{ lcp: number; cls: number }>((resolve) => {
          let lcp = 0;
          let cls = 0;

          new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) lcp = entry.startTime;
          }).observe({ type: 'largest-contentful-paint', buffered: true });

          new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
              // Layout shifts within 500ms of a user input are that input's consequence, not a
              // defect. Nothing here generates input, but the guard keeps the number comparable
              // to the field metric it is named after.
              const shift = entry as LayoutShift;
              if (!shift.hadRecentInput) cls += shift.value;
            }
          }).observe({ type: 'layout-shift', buffered: true });

          setTimeout(() => resolve({ lcp, cls }), 2500);
        }),
    );

    // eslint-disable-next-line no-console
    console.log(`PERF lcp_ms=${vitals.lcp.toFixed(0)} cls=${vitals.cls.toFixed(4)}`);

    // **The blueprint's 0.00 CLS is a TARGET and is not asserted here.** It cannot honestly be
    // claimed until the specified type families land and their `size-adjust` / ascent / descent
    // overrides are measured from the real files (web/datum/fonts/README.md step 3). Every page
    // currently renders in a fallback face with those three properties absent, so a 0.00 measured
    // today is 0.00 for a page nobody will ship.
    //
    // 0.1 is the Core Web Vitals "good" threshold. It is a floor against regression, not a claim
    // of having met §11.9.
    expect(vitals.cls, 'layout shift regressed').toBeLessThan(0.1);
    expect(vitals.lcp, 'LCP regressed').toBeLessThan(4000);
  });

  test('the shader compile cost and the steady frame time are measured separately', async ({
    page,
  }) => {
    await page.goto('/web/landing/index.html', { waitUntil: 'load' });

    const canvasAppeared = await page
      .waitForSelector('canvas', { timeout: 15_000 })
      .then(() => true)
      .catch(() => false);

    if (!canvasAppeared) {
      // Not a failure: this machine may fall to the `off` or `lite` tier, which is a designed
      // outcome (L-7 — the page is complete with the canvas deleted). Say which happened rather
      // than reporting a pass that means something else.
      // eslint-disable-next-line no-console
      console.log('PERF scene=absent (degradation ladder chose off/lite; see tier() in lib.ts)');
      await expect(page.locator('h1').first()).toBeVisible();
      return;
    }

    const timings = await page.evaluate(
      () =>
        new Promise<{ first: number; steady: number; worst: number }>((resolve) => {
          const samples: number[] = [];
          let previous = performance.now();
          let count = 0;

          const tick = () => {
            const now = performance.now();
            samples.push(now - previous);
            previous = now;
            count += 1;
            if (count < 40) requestAnimationFrame(tick);
            else {
              // The first sample is kept separate from the rest, but see the note below: it is
              // NOT the shader compile. By the time this observer attaches, the scene has
              // already drawn.
              const [first, ...rest] = samples;
              // Discard the next few: program link and texture upload trail the first frame.
              const warm = rest.slice(5).sort((a, b) => a - b);
              resolve({
                first,
                steady: warm[Math.floor(warm.length / 2)],
                worst: warm[warm.length - 1],
              });
            }
          };
          requestAnimationFrame(tick);
        }),
    );

    // eslint-disable-next-line no-console
    console.log(
      `PERF first_observed_frame_ms=${timings.first.toFixed(1)} ` +
        `steady_frame_median_ms=${timings.steady.toFixed(2)} ` +
        `steady_frame_worst_ms=${timings.worst.toFixed(2)}`,
    );

    // ── SHADER COMPILE IS NOT MEASURED HERE, and the name it used to carry was wrong. ────────
    //
    // An earlier version of this test labelled its first sample `shader_compile_first_frame_ms`
    // and reported 1.0ms. That number is real and it is not a compile: this observer attaches
    // after `waitForSelector('canvas')`, by which time the scene has already drawn its first
    // frame and paid the cost. (Measuring from page load instead gave 554ms — which IS roughly
    // the compile, and was mislabelled the other way, as a steady frame time.)
    //
    // Publishing 1.0ms as a measured shader-compile time would be precisely the failure FR-9.1
    // exists to prevent: a number that is arithmetically true and describes something other than
    // its label. §11.9's shader-compile budget therefore remains **UNMEASURED**, and closing it
    // needs `performance.mark()` around the program link inside Scene.tsx — app-side
    // instrumentation, not something a test can observe from outside.

    // Both ceilings are deliberately loose. A headless runner shares a GPU with whatever else the
    // machine is doing and this suite runs 8 workers in parallel, so a tight budget here would
    // fail for reasons that have nothing to do with the code. These catch a scene that has
    // stopped rendering or fallen back to software — not one that is a few milliseconds slower.
    //
    expect(timings.first, 'first observed frame regressed sharply').toBeLessThan(3000);
    expect(timings.steady, 'steady frame time collapsed — check for software rendering').toBeLessThan(
      120,
    );
  });

  test('?nogl=1 costs nothing — no engine bytes at all (L-7)', async ({ page }) => {
    const engineBytes: string[] = [];
    page.on('response', (response) => {
      const url = response.url();
      if (url.includes('three-') || url.includes('Scene-')) engineBytes.push(url);
    });

    await page.goto('/web/landing/index.html?nogl=1', { waitUntil: 'load' });
    await page.waitForTimeout(1500);

    await expect(page.locator('h1').first()).toBeVisible();
    expect(await page.locator('canvas').count()).toBe(0);
    // The claim L-7 makes is not "degrades gracefully" — it is that the engine is never fetched.
    // A page that downloads 183 KB of three.js and then does not use it has not honoured it.
    expect(engineBytes, '?nogl=1 still downloaded the engine').toEqual([]);
  });
});

// Minimal shape for the layout-shift entry, which TS's DOM lib does not carry.
interface LayoutShift extends PerformanceEntry {
  value: number;
  hadRecentInput: boolean;
}
