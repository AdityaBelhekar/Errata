/**
 * The floor: every surface loads, says nothing to the console, and asks for
 * nothing it cannot have.
 *
 * Register B-1. These are the assertions that were previously made by looking
 * at the page — which cannot see a console error, cannot see a 404 for a
 * stylesheet that happens to be cached, and cannot be run by anyone else.
 *
 * The console-error assertion is also what makes the CSP tightening in
 * `errata_audit.web` safe: a blocked inline script reports as a console error,
 * so a policy that breaks a page fails here instead of in production.
 */

import { expect, test } from '@playwright/test';

import { stubBundleApi } from './stub';
import { isKnownMissing, SURFACES } from './surfaces';

for (const surface of SURFACES) {
  test.describe(surface.id, () => {
    test('loads without console errors or failed requests', async ({ page }) => {
      const consoleErrors: string[] = [];
      const failed: string[] = [];

      page.on('console', (message) => {
        if (message.type() !== 'error') return;
        // A failed subresource reports twice: once as a `requestfailed`/4xx response carrying the
        // URL, and once as a console error whose *text* is the generic "Failed to load resource".
        // The allow-list has to be applied to the message's own location, or the known-missing
        // fonts come back through this channel after being filtered out of the other one.
        // Where the URL turns up is engine-specific. Chromium puts it in the message's location
        // and leaves the text generic ("Failed to load resource"); Firefox leaves the location
        // empty and names the URL inside the text. Checking only one of the two makes the
        // allow-list work in one browser and silently fail in another — which is exactly the
        // class of difference the cross-browser matrix exists to surface.
        const from = message.location()?.url ?? '';
        const text = message.text();
        if (isKnownMissing(from) || isKnownMissing(text)) return;
        consoleErrors.push(`${text} (${from || 'no source'})`);
      });
      page.on('pageerror', (error) => consoleErrors.push(`uncaught: ${error.message}`));
      page.on('requestfailed', (request) => {
        if (!isKnownMissing(request.url())) failed.push(request.url());
      });
      page.on('response', (response) => {
        if (response.status() >= 400 && !isKnownMissing(response.url())) {
          failed.push(`${response.status()} ${response.url()}`);
        }
      });

      await stubBundleApi(page);

      await page.goto(surface.path, { waitUntil: 'load' });

      if (surface.expect.selector) {
        await expect(page.locator(surface.expect.selector).first()).toBeVisible();
      }

      expect(consoleErrors, `console errors on ${surface.path}`).toEqual([]);
      expect(failed, `failed requests on ${surface.path}`).toEqual([]);
    });

    test('has a title and a language', async ({ page }) => {
      // `lang` is not decoration: a screen reader picks its pronunciation from it, and §15
      // requires WCAG 2.2 AA. Q6 (locale) is unresolved, so this asserts the attribute exists
      // and is non-empty rather than asserting it is `en` — which would pin a decision nobody
      // has made yet.
      await page.goto(surface.path);
      await expect(page).toHaveTitle(/\S/);
      const lang = await page.locator('html').getAttribute('lang');
      expect(lang, `${surface.path} has no lang attribute`).toBeTruthy();
    });

    test('does not scroll horizontally at a phone width', async ({ page }) => {
      // The register records the console's stacked layout as never having been opened on a
      // phone. A horizontal scrollbar is the cheapest detectable symptom of a layout that has
      // not been looked at below 400px.
      await page.setViewportSize({ width: 375, height: 812 });
      await page.goto(surface.path);
      const overflows = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      );
      expect(overflows, `${surface.path} scrolls sideways at 375px`).toBe(false);
    });
  });
}

test.describe('the primary nav is actually painted', () => {
  // The test that did not exist when it was needed.
  //
  // The site nav was a `<details>` disclosure whose `<summary>` was hidden above the mobile
  // breakpoint. A CLOSED `<details>` gets a zero-size box from the UA stylesheet, so eight links
  // laid out at 25x24 each inside a container 0 pixels WIDE and painted nothing. The entire
  // navigation was invisible on desktop.
  //
  // None of the existing tests caught it, and the reason is worth stating: they all asked about
  // the LINKS. The links were fine — present, non-zero, focusable, big enough for
  // WCAG target-size. It was their CONTAINER that had collapsed. So this asserts the container,
  // and asserts it the way a reader experiences it: is the row wide enough to hold what is in it.

  for (const path of ['/web/site/', '/web/site/method.html', '/web/site/404.html']) {
    test(`${path} — the nav row has real width and every link is inside it`, async ({ page }) => {
      await page.goto(path, { waitUntil: 'load' });

      const nav = page.locator('.nav-links');
      await expect(nav).toBeVisible();

      const geometry = await page.evaluate(() => {
        const row = document.querySelector('.nav-links');
        if (!row) return null;
        const box = row.getBoundingClientRect();
        const links = [...row.querySelectorAll('a')];
        return {
          width: box.width,
          height: box.height,
          count: links.length,
          // A link painted outside its own container is a link nobody sees, whatever its rect says.
          escaping: links.filter((a) => {
            const r = a.getBoundingClientRect();
            return r.right > box.right + 1 || r.left < box.left - 1;
          }).length,
        };
      });

      expect(geometry, `${path} has no .nav-links`).not.toBeNull();
      expect(geometry!.count, 'the nav lost its links').toBeGreaterThan(3);
      // The collapsed case measured 0. Anything narrower than one label is collapsed.
      expect(geometry!.width, 'the nav row collapsed — its links are laid out but not painted')
        .toBeGreaterThan(200);
      expect(geometry!.height, 'the nav row has no height').toBeGreaterThan(10);
      expect(geometry!.escaping, 'links are painting outside their own container').toBe(0);
    });
  }

  test('the nav wraps rather than collapsing at a phone width', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/web/site/', { waitUntil: 'load' });
    const box = await page.locator('.nav-links').boundingBox();
    // Wrapped to more than one line, and still inside the viewport.
    expect(box!.height).toBeGreaterThan(30);
    expect(box!.width).toBeLessThanOrEqual(375);
  });

  test('the current page is marked in the nav', async ({ page }) => {
    // `aria-current` is how a screen-reader user knows where they are. It is generated, so a
    // generator change that dropped it would be silent.
    await page.goto('/web/site/method.html', { waitUntil: 'load' });
    await expect(page.locator('.nav-links a[aria-current="page"]')).toHaveText('Method');
  });
});

test.describe('the degradation ladder', () => {
  test('?nogl=1 renders the page with no canvas at all (L-7)', async ({ page }) => {
    // The claim L-7 makes is that the page is a complete document with the canvas deleted, not
    // that it degrades gracefully. So the assertion is zero canvases and readable copy — not
    // "still looks fine".
    await page.goto('/web/landing/index.html?nogl=1');
    await expect(page.locator('h1').first()).toBeVisible();
    expect(await page.locator('canvas').count()).toBe(0);
  });
});
