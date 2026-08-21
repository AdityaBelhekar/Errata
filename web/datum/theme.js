/* ═══════════════════════════════════════════════════════════════════════════
   DATUM — theme.js
   Blueprint §6.6. Three states: system / light / dark.

   The no-flash half of this lives INLINE in every page's <head> (see
   `INLINE_HEAD` below, which is the literal text to paste). It must run before
   first paint, so it cannot be in this file. This file carries the toggle
   behaviour, which may load whenever it likes.
   ═══════════════════════════════════════════════════════════════════════════ */

/*
INLINE_HEAD — paste verbatim into <head>, before any stylesheet link:

<script>
(function () {
  try {
    var t = localStorage.getItem('errata-theme');
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
    if (new URLSearchParams(location.search).get('nogl') === '1')
      document.documentElement.setAttribute('data-gl', 'off');
  } catch (e) {}
})();
</script>
*/

(function () {
  'use strict';

  var KEY = 'errata-theme';
  var root = document.documentElement;

  function stored() {
    try { return localStorage.getItem(KEY) || 'system'; } catch (e) { return 'system'; }
  }

  function resolved(mode) {
    if (mode === 'light' || mode === 'dark') return mode;
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function paintMeta(mode) {
    // <meta name="theme-color"> is updated on switch (§6.6). The value is read
    // out of the live computed style so that the browser chrome and the page
    // ground can never disagree — there is no second copy of the colour to
    // drift, which is the whole point of LAW §17.
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.setAttribute('name', 'theme-color');
      document.head.appendChild(meta);
    }
    meta.setAttribute('content', getComputedStyle(document.body).backgroundColor);
  }

  function apply(mode) {
    if (mode === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', mode);
    try { localStorage.setItem(KEY, mode); } catch (e) {}
    document.querySelectorAll('[data-theme-toggle] button').forEach(function (b) {
      b.setAttribute('aria-checked', String(b.dataset.mode === mode));
    });
    paintMeta(resolved(mode));
    root.dispatchEvent(new CustomEvent('datum:theme', {
      detail: { mode: mode, resolved: resolved(mode) }
    }));
  }

  function mount() {
    document.querySelectorAll('[data-theme-toggle]').forEach(function (group) {
      group.setAttribute('role', 'radiogroup');
      group.setAttribute('aria-label', 'Colour theme');
      group.querySelectorAll('button').forEach(function (b) {
        b.setAttribute('role', 'radio');
        b.addEventListener('click', function () { apply(b.dataset.mode); });
        // Arrow-key traversal, so the group behaves like one control rather
        // than three tab stops (§15: keyboard path verified for every
        // interaction).
        b.addEventListener('keydown', function (e) {
          if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
          e.preventDefault();
          var all = Array.prototype.slice.call(group.querySelectorAll('button'));
          var i = all.indexOf(b);
          var next = all[(i + (e.key === 'ArrowRight' ? 1 : all.length - 1)) % all.length];
          next.focus();
          apply(next.dataset.mode);
        });
      });
    });
    apply(stored());

    // When the choice is "system", follow the OS live.
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (stored() === 'system') apply('system');
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
