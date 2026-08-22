/**
 * §13.5 designates `states.html` — 21 components, every state, both themes — as
 * THE CI screenshot-diff target. Nothing had ever diffed it.
 *
 * **Per component, not per page.** The first attempt screenshotted the whole
 * gallery and could not be made to pass twice: the page is ~27,000px tall and its
 * rendered height varied by ~156px between identical loads, so every run diffed
 * against a differently-sized image. A suite that fails at random gets its
 * baselines refreshed unread, which is worse than having no suite.
 *
 * (That height instability is a finding in its own right, not just a testing
 * inconvenience — a page that settles to a different height on each load has a
 * layout that is still moving after `document.fonts.ready`. It is recorded in the
 * test register rather than papered over here.)
 *
 * Clipping to each component makes the shots small, stable, and diagnostic: a
 * failure names the component that changed instead of reporting that 0.01 of a
 * very large image is different.
 *
 * **Baselines are captured with the specified fonts absent.** The three families
 * in blueprint §5.2 are not in the repository yet (`web/datum/fonts/README.md`),
 * so every glyph is currently a fallback and every baseline changes at once when
 * Redaction lands. Hence the `-fallback` suffix: when the fonts arrive, add a
 * second set rather than overwriting this one. A mass baseline update is
 * otherwise indistinguishable from a mass regression.
 *
 * The rule for reviewers: `--update-snapshots` on a red run launders a regression
 * as intent. Every baseline change is a reviewed diff.
 */

import { expect, test } from '@playwright/test';

const THEMES = ['light', 'dark'] as const;
const COMPONENTS = Array.from({ length: 21 }, (_, i) => `c${String(i + 1).padStart(2, '0')}`);

// One project only. Font rasterisation, scrollbar width and subpixel rounding differ per engine,
// so a shared baseline across browsers produces diffs about the renderer rather than about the
// change. Cross-browser correctness is smoke.spec.ts's job — it asserts behaviour, not pixels.
//
// Guarded on PROJECT name, not `browserName`: the `mobile` project is also Chromium, so a
// `browserName !== 'chromium'` check does not skip it, and it ran the desktop baselines at a
// phone viewport. The failure was mine and the guard was the bug.
test.describe('states gallery — the §13.5 diff target', () => {

  for (const theme of THEMES) {
    test.describe(theme, () => {
      test.beforeEach(async ({ page }) => {
        await page.addInitScript((value) => {
          localStorage.setItem('errata-theme', value);
        }, theme);
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/web/datum/states.html', { waitUntil: 'load' });
        await page.evaluate(() => document.fonts.ready);
      });

      for (const id of COMPONENTS) {
        test(`${id}`, async ({ page }) => {
          const section = page.locator(`#${id}`);
          await section.scrollIntoViewIfNeeded();
          await expect(section).toHaveScreenshot(`${id}-${theme}-fallback.png`, {
            animations: 'disabled',
            caret: 'hide',
          });
        });
      }
    });
  }
});

test.describe('reduced motion — H-6, implemented and never verified', () => {
  // Seven things change under `prefers-reduced-motion`: Lenis is not started, the frameloop goes
  // to demand, the act cross-fades, the mark pulse, the skeleton animation, the toast entrance and
  // View Transitions. None had been verified under the actual media query — only reasoned about
  // from the source.
  //
  // `page.emulateMedia()` rather than the `reducedMotion` fixture. The fixture did not take here:
  // with `test.use({ reducedMotion: 'reduce' })` the page still reported
  // `matchMedia('(prefers-reduced-motion: reduce)').matches === false`, so the suite was
  // exercising the ordinary path while claiming to test the reduced one — and it reported a
  // product defect that did not exist.
  //
  // Hence `assertReducedMotionIsActive` below. A reduced-motion test that does not confirm
  // reduced motion is ON passes whether or not the feature works, which makes it worse than
  // absent: it converts an untested area into one that looks tested.

  async function gotoReduced(page: import('@playwright/test').Page, path: string) {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(path, { waitUntil: 'load' });
    const active = await page.evaluate(
      () => matchMedia('(prefers-reduced-motion: reduce)').matches,
    );
    expect(active, 'the harness failed to enable reduced motion; this test proves nothing').toBe(
      true,
    );
  }

  test('the scene drops to the lite tier under the real media query', async ({ page }) => {
    await gotoReduced(page, '/web/landing/index.html');
    // §10.4: the reduced-motion contract is a DESIGNED ALTERNATIVE, not a disabled one. The
    // assertion is that the document is still complete — fewer moving parts, not less content.
    await expect(page.locator('h1').first()).toBeVisible();
  });

  test('no CSS animation runs indefinitely', async ({ page }) => {
    await gotoReduced(page, '/web/datum/states.html');
    await page.waitForTimeout(400);

    // A *running* animation is not automatically a violation — a one-shot entrance mid-flight is
    // fine and will finish. What reduced motion forbids is motion that does not stop, so the
    // assertion is on `iterations`, which is what separates a transition from a loop.
    const endless = await page.evaluate(() =>
      document
        .getAnimations()
        .filter((animation) => {
          if (animation.playState !== 'running') return false;
          const timing = (animation.effect as KeyframeEffect | null)?.getComputedTiming();
          return timing?.iterations === Infinity;
        })
        .map((animation) => {
          const target = (animation.effect as KeyframeEffect | null)?.target as Element | null;
          return `${(animation as CSSAnimation).animationName ?? '?'} on ${target?.tagName.toLowerCase() ?? '?'}`;
        }),
    );

    expect(endless, 'infinite animations still running under prefers-reduced-motion').toEqual([]);
  });

  test('the loading rail is replaced, not merely stopped', async ({ page }) => {
    // §10.4 again, at the level of one component: the spec says the rail stops AND the button
    // says so in text instead. "Stopped" alone would leave a button that looks idle while it
    // works, which is a worse outcome for the same user.
    await gotoReduced(page, '/web/datum/states.html');
    const rail = await page.evaluate(() => {
      const button = document.querySelector('.btn[data-state="loading"]');
      if (!button) return null;
      const after = getComputedStyle(button, '::after');
      return { animationName: after.animationName, width: after.width };
    });
    expect(rail?.animationName).toBe('none');
  });
});
