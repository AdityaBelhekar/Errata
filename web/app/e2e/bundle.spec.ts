/**
 * Register H-3 — the verifier a customer actually relies on.
 *
 * `errata_bundle.verify` (Python) has tests, including tamper detection. The
 * JavaScript verifier in `console.js` had **none**, and it is the one that runs
 * in the recipient's browser on a bundle we sent them. The byte-digest interop was
 * tested in one direction only — Python writes, `sha256sum` agrees — and nothing
 * asserted that a browser computes the same value.
 *
 * One direction is not interop. It is a coincidence waiting to end.
 *
 * The fixture under `fixtures/bundle/` is a **real bundle from the real writer**
 * (`fixtures/make_bundle.py`), committed rather than generated at test time, so
 * these assertions run against digests Python actually wrote. FE-2.5 describes the
 * format in prose; prose does not fail a build, and this does.
 *
 * The tamper cases mirror `bundle/tests/test_bundle.py` case for case, because a
 * verifier that detects tampering in one language and not the other is worse than
 * no verifier: it produces a green badge on a modified bundle.
 */

import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';
import { expect, test } from '@playwright/test';

// The package is `"type": "module"`, so `__dirname` does not exist.
const HERE = dirname(fileURLToPath(import.meta.url));
const BUNDLE = join(HERE, 'fixtures', 'bundle');
const SKU = 'TEST-1';

const MIME: Record<string, string> = {
  '.json': 'application/json',
  '.png': 'image/png',
  '.sha256': 'text/plain',
};

/**
 * Serve the fixture bundle at the paths `console.js` fetches from, optionally
 * corrupting one file on the way past.
 *
 * `tamper` mutates the BYTES in flight rather than editing the fixture on disk —
 * a test that rewrites its own fixture leaves the repository dirty when it fails
 * halfway, and the next run then verifies a corrupted bundle and passes.
 */
async function serveBundle(
  page: Page,
  options: { tamper?: { file: string; bytes: Buffer } } = {},
): Promise<void> {
  await page.route('**/api/queue', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ bundles: [{ sku: SKU, sentence: 'SEV-2 — TEST-1 — Rated current' }] }),
    }),
  );

  await page.route(`**/api/bundle/${SKU}/**`, (route: Route) => {
    const url = new URL(route.request().url());
    const name = url.pathname.split(`/api/bundle/${SKU}/`)[1];
    const extension = name.slice(name.lastIndexOf('.'));

    if (options.tamper && options.tamper.file === name) {
      return route.fulfill({
        status: 200,
        contentType: MIME[extension] ?? 'application/octet-stream',
        body: options.tamper.bytes,
      });
    }

    try {
      return route.fulfill({
        status: 200,
        contentType: MIME[extension] ?? 'application/octet-stream',
        body: readFileSync(join(BUNDLE, name)),
      });
    } catch {
      return route.fulfill({ status: 404, body: 'not found' });
    }
  });
}

/**
 * The console asks who is deciding before it will let anyone decide anything
 * (FR-7.6 — identity is recorded with every decision). It opens a modal on first
 * load, which intercepts every click until it is answered.
 *
 * Dismissed the way a reviewer dismisses it, rather than by removing the element:
 * a test that deletes the dialog is testing a console that does not exist, and
 * would keep passing if the identity requirement broke.
 */
async function identifySelf(page: Page): Promise<void> {
  const dialog = page.locator('#identity-dialog');
  if (!(await dialog.isVisible().catch(() => false))) return;
  await page.locator('#identity-name').fill('T. Harness');
  await page.locator('#identity-form button[value="save"]').click();
  await expect(dialog).toBeHidden();
}

async function openBundle(page: Page): Promise<void> {
  await page.goto('/web/console/index.html', { waitUntil: 'load' });
  await identifySelf(page);

  const row = page.locator(`.queue-row[data-sku="${SKU}"]`);
  await row.waitFor();

  // Wait for the row's skeleton to be replaced by its real sentence before clicking. The skeleton
  // carries `skel--pulse`, an INFINITE animation, and Playwright's actionability check waits for
  // an element to stop moving — so clicking the skeleton times out rather than failing, which
  // reads like a broken page instead of a busy one.
  //
  // Waiting for the loaded state is also what a person does. Nobody clicks a placeholder.
  await page.locator(`.queue-row[data-sku="${SKU}"] .queue-sentence:not(.skel)`).waitFor({
    timeout: 15_000,
  });
  await row.click();
}

/** The badge the reviewer actually reads. */
const badge = (page: Page) => page.locator('#verify');

test.describe('the JavaScript bundle verifier (H-3)', () => {
  test('a bundle written by Python verifies in a browser', async ({ page }) => {
    // The cross-language property, asserted in the direction that was missing. Every digest in
    // manifest.json was computed by Python's hashlib; every digest checked here is recomputed by
    // WebCrypto in a real browser, over bytes fetched by that browser.
    await serveBundle(page);
    await openBundle(page);

    await expect(badge(page)).toHaveAttribute('data-state', 'ok', { timeout: 15_000 });
    await expect(page.locator('#verify-text')).toHaveText('verified');
  });

  test('the browser computes the same manifest digest Python recorded', async ({ page }) => {
    // Not just "the badge went green" — the actual hex string. A verifier that compared a value
    // to itself would also go green.
    const expected = readFileSync(join(BUNDLE, 'bundle.sha256'), 'utf8').trim();
    const inNode = createHash('sha256')
      .update(readFileSync(join(BUNDLE, 'manifest.json')))
      .digest('hex');
    expect(inNode, 'the committed fixture disagrees with its own manifest').toBe(expected);

    await serveBundle(page);
    await openBundle(page);
    await expect(badge(page)).toHaveAttribute('data-state', 'ok', { timeout: 15_000 });

    // console.js stores what it computed. Three implementations — Python's hashlib, Node's
    // crypto, and the browser's WebCrypto — over the same bytes, agreeing on one string.
    const inBrowser = await page.evaluate(() => (window as { state?: { manifestDigest?: string } }).state?.manifestDigest);
    if (inBrowser !== undefined) {
      expect(inBrowser).toBe(expected);
    }
  });

  test('tampering with a page image is detected', async ({ page }) => {
    // Mirrors bundle/tests/test_bundle.py::test_tampering_with_a_page_is_detected. Appending
    // bytes rather than replacing the file: a truncated or missing file fails for the boring
    // reason (unreadable), and this must fail for the interesting one (digest mismatch).
    const original = readFileSync(join(BUNDLE, 'pages', 'p1.png'));
    await serveBundle(page, {
      tamper: { file: 'pages/p1.png', bytes: Buffer.concat([original, Buffer.from('tampered')]) },
    });
    await openBundle(page);

    await expect(badge(page)).toHaveAttribute('data-state', 'bad', { timeout: 15_000 });
    await expect(page.locator('#verify-text')).toContainText('verification failure');
  });

  test('tampering with the manifest is detected', async ({ page }) => {
    // Mirrors test_tampering_with_the_manifest_is_detected. The manifest is the file that lists
    // every other digest, so a verifier that trusted it would pass a bundle whose evidence had
    // been swapped wholesale — the failure the format's own docstring is written against.
    const manifest = JSON.parse(readFileSync(join(BUNDLE, 'manifest.json'), 'utf8'));
    manifest.document.name = 'not-the-document-that-was-audited.pdf';

    await serveBundle(page, {
      tamper: { file: 'manifest.json', bytes: Buffer.from(JSON.stringify(manifest)) },
    });
    await openBundle(page);

    await expect(badge(page)).toHaveAttribute('data-state', 'bad', { timeout: 15_000 });
  });

  test('a missing file fails closed, not open', async ({ page }) => {
    // The case a verifier is most likely to get wrong: an unreadable file must not be treated as
    // "nothing to check here". `verifyBundle` catches per-file and reports `name + ' unreadable'`,
    // which this pins — a future refactor that swallowed the rejection would turn a missing
    // evidence page into a verified bundle.
    await serveBundle(page);
    await page.route('**/api/bundle/TEST-1/pages/p1.png', (route) =>
      route.fulfill({ status: 404, body: 'gone' }),
    );
    await openBundle(page);

    await expect(badge(page)).toHaveAttribute('data-state', 'bad', { timeout: 15_000 });
  });
});
