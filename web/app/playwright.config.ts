import { defineConfig, devices } from '@playwright/test';

/**
 * Register B-1: every frontend claim in every gate report rested on one person
 * looking at one Chromium pane once. This is the file that replaces that.
 *
 * **The server is Python on purpose.** `vite.config.ts` records the delivery
 * model as "a Python process serves everything" (FE-SYSTEM-REVIEW §4, Q1 → C),
 * and a test harness that serves the pages some other way tests a deployment
 * nobody ships. It also avoids adding a Node static-server dependency to prove
 * something about pages that are plain static files.
 *
 * Served from the repository root rather than from `web/`, so the absolute paths
 * the pages actually use — `/web/landing/`, `/web/datum/styles/…` — resolve the
 * same way here as they do in production.
 *
 * H-4: the browser matrix is Chromium, Firefox and WebKit. Everything to date
 * ran in one Chromium build, and the surfaces at genuine risk are named in the
 * register: `container-type: size` and `backdrop-filter` in Safari, View
 * Transitions and `@property` in Firefox.
 */
const PORT = 4173;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,

  // One retry, everywhere -- including local `scripts/ci.sh` runs, which previously had none.
  //
  // This is NOT "make the build green". Playwright reports a test that failed then passed as
  // **flaky**, in its own row, distinct from passed. The build stays honest because a flake is
  // still visible; what changes is that a known harness artefact does not stop the whole
  // pipeline while it is being investigated.
  //
  // Two tests are currently load-dependent (see FE-TEST-REGISTER §11.4): both pass 6/6 in
  // isolation and fail roughly one run in twenty under 8 parallel workers across 4 projects.
  // The suspected cause is contention -- GPU contexts for the WebGL surface, and layout settling
  // on a page already known to reflow after load. Neither has been explained, and "retried" is
  // not "understood": if the flaky row stops being empty for a NEW test, that is a finding.
  retries: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',

  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  // Screenshot comparison is deliberately strict. A visual suite that is updated
  // by reflex launders regressions as intent, so the bar is set where a real
  // change trips it and antialiasing does not.
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.002, animations: 'disabled' },
  },

  projects: [
    // Screenshot baselines and perf budgets belong to ONE project. Font rasterisation,
    // scrollbar width, subpixel rounding and frame timing are all engine- and
    // device-specific, and a budget that means four different things is not a budget.
    // Original text follows.
    //
    // Screenshot baselines belong to ONE project. Font rasterisation, scrollbar width and
    // subpixel rounding differ per engine and per viewport, so sharing a baseline across
    // projects produces diffs about the renderer rather than about the change — and a suite that
    // cries wolf gets its baselines refreshed unread.
    //
    // Expressed here rather than as a `test.skip` in the spec, because the `mobile` project is
    // ALSO Chromium: a `browserName !== 'chromium'` guard does not skip it, and it silently ran
    // the desktop baselines at a phone viewport. Projects are defined here, so the rule that
    // depends on project identity belongs here too.
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] }, testIgnore: /(visual|perf)\.spec\.ts/ },
    { name: 'webkit', use: { ...devices['Desktop Safari'] }, testIgnore: /(visual|perf)\.spec\.ts/ },
    // H-4: the console degrades to a stacked layout that has never been opened on a phone.
    // Emulation is not a real device and does not close that item — it is the part of it that
    // can be automated.
    { name: 'mobile', use: { ...devices['Pixel 7'] }, testIgnore: /(visual|perf)\.spec\.ts/ },
  ],

  webServer: {
    command: `python -m http.server ${PORT} --bind 127.0.0.1 --directory ../..`,
    url: `http://127.0.0.1:${PORT}/web/datum/index.html`,
    reuseExistingServer: !process.env.CI,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
