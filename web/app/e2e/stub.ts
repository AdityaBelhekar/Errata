import type { Page } from '@playwright/test';

/**
 * The console shell fetches its queue from the bundle server, which exists only when
 * `errata-audit serve` is running. Under the static server these tests use, that is a 404 — and
 * it is a 404 about the harness, not about the page.
 *
 * Stubbed with an empty-but-valid payload rather than allow-listed, because an empty queue is a
 * state the console genuinely has (nothing left to review). That exercises the render path
 * instead of skipping it.
 *
 * What this does NOT test is the integration. That is `audit/tests/test_web.py`, which drives the
 * real server. Kept in one file so the two suites cannot stub it two different ways and disagree
 * about which console they are testing — the same class of drift the site generator exists to
 * prevent.
 */
export async function stubBundleApi(page: Page): Promise<void> {
  await page.route('**/api/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ bundles: [] }),
    }),
  );
}
