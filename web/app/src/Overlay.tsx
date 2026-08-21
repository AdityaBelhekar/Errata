/* ═══════════════════════════════════════════════════════════════════════════
   THE DOM LAYER — HUD, the five acts, and Room III.

   L-7: all copy is real DOM, all navigation is keyboard-reachable, WebGL is
   enhancement and never structure. Delete the canvas and this file is still a
   complete, readable page — which is what `?nogl=1` proves rather than claims.

   Scroll progress is written to CSS custom properties on <html> from ONE rAF
   subscriber. React does not re-render on scroll: a 60Hz React render of five
   acts is how a scroll page starts dropping frames, and CSS can interpolate an
   opacity without any of us being involved.
   ═══════════════════════════════════════════════════════════════════════════ */

import { useEffect, useRef, useState } from 'react';
import { clamp01, ease, scroll, span } from './lib';

const ACTS = [
  { id: 'I', name: 'Approach', from: 0.0, to: 0.16 },
  { id: 'II', name: 'Compression', from: 0.14, to: 0.32 },
  { id: 'III', name: 'Blacklight', from: 0.30, to: 0.58 },
  { id: 'IV', name: 'The archive', from: 0.56, to: 0.86 },
  { id: 'V', name: 'The queue', from: 0.84, to: 1.0 },
];

/** Opacity for an act: up over the first fifth of its span, down over the last.
 *  Cross-fades rather than cuts, so nothing pops at a boundary.
 *
 *  The FIRST and LAST acts are exceptions, and both have to be. An act that
 *  begins at scroll 0 has no room to fade in, and one that ends at scroll 1 has
 *  no room to fade out — the general formula gave the hero zero opacity at the
 *  top of the page and the queue zero opacity at the bottom, so a visitor who
 *  scrolled all the way to the product panel arrived at an empty room.
 *
 *  The same mistake at both ends, found separately, which is the argument for
 *  fixing the rule rather than the symptom. */
function actOpacity(t: number, from: number, to: number) {
  const inn = from <= 0 ? 1 : ease(span(t, from, from + (to - from) * 0.22));
  const out = to >= 1 ? 1 : 1 - ease(span(t, to - (to - from) * 0.22, to));
  return Math.min(inn, out);
}

export default function Overlay() {
  const [ready, setReady] = useState(false);
  const [act, setAct] = useState(0);
  const lens = useRef<HTMLDivElement>(null);
  const sheet = useRef<HTMLDivElement>(null);

  /* ── the single scroll subscriber ────────────────────────────────────── */
  useEffect(() => {
    const root = document.documentElement;
    let frame = 0;
    let current = 0;

    const unsubscribe = scroll.subscribe((p) => {
      current = p;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        root.style.setProperty('--p', current.toFixed(5));
        ACTS.forEach((a, i) => {
          root.style.setProperty(`--a${i}`, actOpacity(current, a.from, a.to).toFixed(4));
        });
        // Room III is DOM, so the canvas has to get out of its way: it drops to
        // 30% and the paper owns the frame (§11.5).
        const blacklight = actOpacity(current, 0.30, 0.58);
        root.style.setProperty('--gl-dim', String(1 - blacklight * 0.7));
        const next = ACTS.findIndex((a) => current >= a.from && current < a.to);
        setAct((prev) => (next >= 0 && next !== prev ? next : prev));
      });
    });
    return () => {
      unsubscribe();
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  /* ── preloader ────────────────────────────────────────────────────────
     Waits on document.fonts.ready AND a compiled first frame, so there is no
     shader hitch and no FOUT (§12.1). A preloader that only waits on the
     network is a preloader that hands over a page which is about to stutter. */
  useEffect(() => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      setReady(true);
    };
    Promise.race([
      Promise.all([
        document.fonts?.ready ?? Promise.resolve(),
        new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))),
      ]),
      // Never hold the page hostage to a font that will not arrive.
      new Promise((r) => setTimeout(r, 2500)),
    ]).then(finish);
  }, []);

  /* ── Room III · the blacklight ────────────────────────────────────────
     Pointer drives a radial mask on the clean PIM export, revealing the true
     datasheet beneath. The lens is a real element with a rim light and a warm
     drop shadow, because a mask with no glass reads as a hole rather than as
     an instrument.

     Keyboard path: Tab cycles the disputed rows and the lens SNAPS to the
     focused row. The interaction is not mouse-only — that was F-12, and a
     procession you cannot operate from the keyboard is a procession that
     excludes people from the argument. */
  useEffect(() => {
    const node = sheet.current;
    if (!node) return;

    const move = (x: number, y: number) => {
      node.style.setProperty('--mx', `${x}px`);
      node.style.setProperty('--my', `${y}px`);
      if (lens.current) {
        lens.current.style.transform = `translate3d(${x - 92}px, ${y - 92}px, 0)`;
      }
    };

    const onPointer = (e: PointerEvent) => {
      const r = node.getBoundingClientRect();
      move(e.clientX - r.left, e.clientY - r.top);
    };
    const onFocus = (e: FocusEvent) => {
      const row = e.target as HTMLElement;
      if (!row.classList?.contains('span-hl')) return;
      const r = node.getBoundingClientRect();
      const b = row.getBoundingClientRect();
      move(b.left - r.left + b.width / 2, b.top - r.top + b.height / 2);
    };

    node.addEventListener('pointermove', onPointer);
    node.addEventListener('focusin', onFocus);
    move(node.clientWidth * 0.62, node.clientHeight * 0.42);
    return () => {
      node.removeEventListener('pointermove', onPointer);
      node.removeEventListener('focusin', onFocus);
    };
  }, [ready]);

  /* ── Esc skips the procession (§12.1) ─────────────────────────────────── */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') scroll.skipToEnd();
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, []);

  return (
    <>
      {!ready && (
        <div className="preloader" role="status" aria-live="polite">
          <Counter />
          <div className="preload-rail"><i /></div>
          <span className="t-micro">Errata — loading evidence</span>
        </div>
      )}

      {/* ── HUD (§12.1). Instrumentation, not chrome: everything in it is a
             fact you could go and check. ─────────────────────────────────── */}
      <div className="hud hud--tl t-meta">
        ERRATA<br /><span className="u-dimmer">Verification layer</span>
      </div>
      <div className="hud hud--tr t-meta">
        ExtractBench 46.4 GF1<br /><span className="u-dimmer">The 49-point gap</span>
      </div>
      <div className="hud hud--bl t-meta" aria-hidden="true">
        <span>Act {ACTS[act].id} / V</span>
        <span className="rail"><i /></span>
        <span className="u-dimmer">{ACTS[act].name}</span>
      </div>

      <main id="procession">
        {/* ── ACT I ─────────────────────────────────────────────────────── */}
        <section className="act act--1" aria-label="Act I — approach">
          <h1 className="t-d1 hero-line">
            Your catalog is a <span className="degraded">reflection</span>.
          </h1>
          <p className="t-meta hero-sub">We checked it against the thing it claims to reflect.</p>
          <p className="t-micro u-dimmer scroll-cue">Scroll · <kbd>Esc</kbd> skips to the product</p>
        </section>

        {/* ── ACT II ────────────────────────────────────────────────────── */}
        <section className="act act--2" aria-label="Act II — compression">
          <div className="act-copy">
            <h2 className="t-d3">The page you were shown.<br />The page <em>underneath</em> it.</h2>
            <p className="t-body u-dim">
              A catalog is a copy of a copy. Every hop between systems is a chance for a value to
              change, and nothing between them ever checks.
            </p>
          </div>
        </section>

        {/* ── ACT III · THE BLACKLIGHT — DOM, not WebGL (§11.5 LAW) ─────── */}
        <section className="act act--3" aria-label="Act III — the evidence underneath">
          <div className="act-copy">
            <h2 className="t-d3">Hold it up to the light.</h2>
            <p className="t-body u-dim">
              Above: the catalog export. Beneath: the manufacturer’s datasheet. Move the lens — or
              press <kbd>Tab</kbd> to walk the disputed values.
            </p>
            <p className="t-micro u-dimmer">
              This surface is made of type, so it is rendered as DOM at device resolution and never
              as a texture (L-6). It is the single biggest quality jump available.
            </p>
          </div>

          <div className="sheet-stack" ref={sheet}>
            {/* BENEATH — the true datasheet */}
            <div className="doc doc--truth" aria-hidden="true">
              <div className="t-col doc-head">Datasheet 4C-M · page 2 · table 3</div>
              <table className="doc-table">
                <tbody>
                  <tr><th>Ingress protection</th><td>IP66</td></tr>
                  <tr><th>Rated voltage</th><td>400 V</td></tr>
                  <tr><th>Rated current</th><td>16 A</td></tr>
                  <tr><th>Breaking capacity</th><td>10 000 A</td></tr>
                </tbody>
              </table>
            </div>

            {/* ABOVE — the clean export, masked away under the lens */}
            <div className="doc doc--claim">
              <div className="t-col doc-head">PIM export · 4C-M-16-66</div>
              <table className="doc-table">
                <tbody>
                  <tr><th>Ingress protection</th>
                    <td><span className="span-hl" tabIndex={0}>IP54</span></td></tr>
                  <tr><th>Rated voltage</th><td>400 V</td></tr>
                  <tr><th>Rated current</th>
                    <td><span className="span-hl" tabIndex={0}>10 A</span></td></tr>
                  <tr><th>Breaking capacity</th><td>10 000 A</td></tr>
                </tbody>
              </table>
              <p className="t-micro doc-foot">Span offsets 1184–1188 · 1226–1230</p>
            </div>

            <div className="lens" ref={lens} aria-hidden="true" />
          </div>
        </section>

        {/* ── ACT IV ────────────────────────────────────────────────────── */}
        <section className="act act--4" aria-label="Act IV — the archive">
          <div className="act-copy act-copy--wide">
            <p className="t-d2 count">41,206<span className="u-dimmer"> ⁄ 1.2M</span></p>
            <p className="t-d4">records disagree with their own evidence.</p>
            <p className="t-micro u-dimmer">
              3.43% of the catalog. Every hot point in the fall is one of them, and the proportion
              on screen is the claim rather than a number chosen to look right.
            </p>
          </div>
        </section>

        {/* ── ACT V ─────────────────────────────────────────────────────── */}
        <section className="act act--5" aria-label="Act V — the queue">
          <div className="queue-panel">
            <div className="t-col u-dimmer">Triage queue · ranked by expected review value</div>
            <div className="queue-row" data-state="disputed">
              <span className="queue-sentence t-body">
                <span className="sku">S201M-B16UC</span> says rated current is{' '}
                <span className="val was">61&nbsp;A</span>. <span className="loc">Page&nbsp;8</span>,
                column “Rated current I n A” says <span className="val">16&nbsp;A</span>.
              </span>
              <span className="blast t-micro">
                <span data-safety="true">Safety class<span className="f">×25</span></span>
                <span>Blast radius<span className="f">25</span></span>
                <span>Expected review value<span className="f">12.5</span></span>
              </span>
            </div>
            <div className="queue-row" data-state="declined">
              <span className="queue-sentence t-body">
                <span className="sku">S201M-B16UC</span> claims a packaging unit of{' '}
                <span className="val">10&nbsp;pcs</span>. <strong>We did not check it.</strong>
              </span>
              <span className="declined-why t-micro">
                Declined — <span className="fact">value_outside_known_grammar</span>. A value picked
                by tie-break becomes a confident accusation two steps later.
              </span>
            </div>
            <div className="queue-actions">
              <a className="btn btn--lg" href="/web/console/">Open the console</a>
              <a className="btn btn--lg btn--quiet" href="/web/site/">Read the argument</a>
            </div>
            <p className="t-micro u-dimmer">
              Both rows are real output from an audit of{' '}
              <span className="fact">abb-s200-2CDC002142D0207.pdf</span>. Nothing here is
              placeholder data (L-4).
            </p>
          </div>
        </section>
      </main>
    </>
  );
}

/** The preloader counter. 000 → 100 in Redaction 20 (§12.1). */
function Counter() {
  const [n, setN] = useState(0);
  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const v = clamp01((now - start) / 1400);
      setN(Math.round(v * 100));
      if (v < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  return <span className="preload-count">{String(n).padStart(3, '0')}</span>;
}
