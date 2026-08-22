/* ═══════════════════════════════════════════════════════════════════════════
   The four things the procession needs before it can have a single room.

   Every one of them is a direct answer to a post-mortem finding in §1.1 of the
   blueprint. They are here, together, at the bottom of the dependency graph,
   because each was previously scattered and that is how they drifted.
   ═══════════════════════════════════════════════════════════════════════════ */

import Lenis from 'lenis';

/* ── F-02 · frame-rate-independent damping — LAW (§10.6) ───────────────────
   `p += (target - p) * 0.072` runs 2.4x faster on a 144Hz panel than on 60Hz:
   the site literally feels different on different machines. The corrected form
   raises the retention per frame to the power of elapsed frames, so the HALF
   LIFE is what is specified, not the per-frame step.

   A fixed `a += (b - a) * k` anywhere in this codebase is a merge blocker. */
export const damp = (a: number, b: number, k: number, dt: number): number =>
  a + (b - a) * (1 - Math.pow(1 - k, dt));

/** Frames elapsed, normalised to 60Hz, clamped so a tab-out cannot teleport
 *  the camera when the clock resumes. */
export const frames = (delta: number): number => Math.min(4, delta * 60);

export const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);

/** Progress within [a, b], clamped. The rooms are defined as scroll ranges in
 *  §11.2, so every room asks the same question of the same number. */
export const span = (t: number, a: number, b: number): number =>
  clamp01((t - a) / (b - a));

/** Smoothstep. Used for room cross-fades so nothing pops at a boundary. */
export const ease = (t: number): number => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};

/* ── The five acts, and their cross-fade — §11.2 ───────────────────────
   Moved here from Overlay.tsx so it can be TESTED. `actOpacity` shipped with
   the same off-by-one at both ends — the hero invisible at scroll 0 and the
   queue invisible at scroll 1 — and both were found by eye, separately. A
   three-line unit test on the boundaries would have caught either one before it
   reached a screenshot; there was nowhere to put one, because the function
   lived inside a component and was never exported.

   That is the actual lesson, and it is why this moved rather than being fixed
   in place: a function whose boundaries matter belongs where its boundaries can
   be asserted. */

export interface Act {
  id: string;
  name: string;
  from: number;
  to: number;
}

export const ACTS: readonly Act[] = [
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
export function actOpacity(t: number, from: number, to: number): number {
  const inn = from <= 0 ? 1 : ease(span(t, from, from + (to - from) * 0.22));
  const out = to >= 1 ? 1 : 1 - ease(span(t, to - (to - from) * 0.22, to));
  return Math.min(inn, out);
}

/* ── F-01 · ONE scroll authority — LAW (§10.5) ─────────────────────────────
   The prototype smoothed `window.scrollY` with a lerp while native scroll kept
   running. Two motion systems on one axis produce beat frequencies, which is
   the judder the reviewer felt.

   Lenis owns the scrollbar. Nothing else reads scroll position: the scene
   subscribes to this store, and the token lint fails the build on a stray
   `window.scrollY`. One clock, one authority. */

type Listener = (progress: number) => void;

class ScrollAuthority {
  progress = 0;
  private lenis: Lenis | null = null;
  private listeners = new Set<Listener>();

  start(reduced: boolean) {
    if (reduced) {
      // §10.4 — the reduced-motion contract is a DESIGNED ALTERNATIVE, not a
      // disabled one: Lenis is not started, native scroll is restored, and the
      // rooms render as stills. Progress still updates, so the procession is
      // still navigable; it simply does not glide.
      const onScroll = () => this.set(nativeProgress());
      addEventListener('scroll', onScroll, { passive: true });
      this.set(nativeProgress());
      return;
    }
    this.lenis = new Lenis({
      duration: 1.2,
      smoothWheel: true,
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    });
    // The browser restores scroll before any of this runs, and Lenis then
    // treats the restored offset as the truth and glides back to it — dropping
    // a returning visitor into Act IV. Reset immediately, once, at start.
    this.lenis.scrollTo(0, { immediate: true });
    this.lenis.on('scroll', ({ progress }: { progress: number }) => this.set(progress));
    const raf = (time: number) => {
      this.lenis?.raf(time);
      requestAnimationFrame(raf);
    };
    requestAnimationFrame(raf);
  }

  private set(value: number) {
    this.progress = clamp01(value);
    for (const listener of this.listeners) listener(this.progress);
  }

  subscribe(listener: Listener) {
    this.listeners.add(listener);
    listener(this.progress);
    return () => void this.listeners.delete(listener);
  }

  /** `Esc` skips to the product panel (§12.1). An escape from a scroll-driven
   *  page is not a nicety — a visitor who cannot get out of a procession is
   *  trapped in it, which is F-12 wearing a different hat. */
  skipToEnd() {
    const target = document.body.scrollHeight - innerHeight;
    if (this.lenis) this.lenis.scrollTo(target, { duration: 1.1 });
    else scrollTo({ top: target, behavior: 'smooth' });
  }
}

const nativeProgress = () =>
  clamp01(scrollY / Math.max(1, document.body.scrollHeight - innerHeight));

export const scroll = new ScrollAuthority();

export const prefersReducedMotion = () =>
  matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ── The degradation ladder — LAW (§11.10) ─────────────────────────────────
   The page must work with the canvas deleted (L-7). `?nogl=1` is the explicit
   switch; the rest is capability. Each rung is a decision about what to stop
   doing, taken before the frame budget is missed rather than after. */

export type Tier = 'off' | 'lite' | 'full';

export function tier(): Tier {
  const params = new URLSearchParams(location.search);
  if (params.get('nogl') === '1') return 'off';
  if (prefersReducedMotion()) return 'lite';

  try {
    const probe = document.createElement('canvas');
    const gl = probe.getContext('webgl2');
    if (!gl) return 'off';
    // Integrated graphics and a small memory budget get the lite ladder: fewer
    // points, no reflection render target, no bloom. Measured by device memory
    // and core count because those are the only two signals a browser gives
    // before a frame has been drawn, and guessing after the first dropped
    // frame is guessing too late.
    const memory = (navigator as { deviceMemory?: number }).deviceMemory ?? 8;
    if (memory <= 4 || navigator.hardwareConcurrency <= 4) return 'lite';
    return 'full';
  } catch {
    return 'off';
  }
}

/* ── The plate — F-04, and the one place a texture is legitimate ───────────
   L-6 says any surface whose PRIMARY CONTENT IS TEXT is DOM, never a texture,
   and F-04 names canvas-rendered type as the single largest source of the
   "AI-generated" read.

   §11.3 nonetheless specifies the plate's type as "a high-res baked map", and
   the distinction is real rather than convenient: the datasheet in Room III is
   a document, and it stays DOM. The rating plate is a MANUFACTURED OBJECT
   whose lettering is stamped into metal — the lettering is geometry, it has to
   reflect in water and catch a raking key, and DOM cannot do either.

   So: baked, but baked properly. Rendered at 4x device pixel ratio with real
   metrics, and paired with a matched roughness map so the engraving catches
   the key light differently from the field. A texture at screen resolution
   would be exactly the failure F-04 describes; this is not that. */

export interface PlateSpec {
  ingress: string;
  voltage: string;
  current: string;
}

export function platePaint(spec: PlateSpec, scale = 4) {
  const W = 512;
  const H = 320;
  const canvas = document.createElement('canvas');
  canvas.width = W * scale;
  canvas.height = H * scale;
  const ctx = canvas.getContext('2d')!;
  ctx.scale(scale, scale);

  ctx.fillStyle = '#8d9299';
  ctx.fillRect(0, 0, W, H);

  const mono = '500 30px ui-monospace, "SF Mono", Menlo, monospace';
  const micro = '400 13px ui-monospace, Menlo, monospace';

  // The engraving: a dark pass offset up-left and a light pass offset
  // down-right. The lamp is upper-left (L-5), so the far wall of the cut is
  // what catches it. Two passes, not a blur — a stamped letter has an edge.
  const cut = (text: string, x: number, y: number, font: string, align: CanvasTextAlign) => {
    ctx.font = font;
    ctx.textAlign = align;
    ctx.fillStyle = 'rgba(18,20,24,.62)';
    ctx.fillText(text, x - 1, y - 1);
    ctx.fillStyle = 'rgba(255,255,255,.34)';
    ctx.fillText(text, x + 1, y + 1);
    ctx.fillStyle = 'rgba(34,38,44,.92)';
    ctx.fillText(text, x, y);
  };

  cut('TYPE 4C-M · SERIES II', 34, 46, micro, 'left');
  cut('MADE IN EU', W - 34, 46, micro, 'right');

  const rows: Array<[string, string]> = [
    ['INGRESS', spec.ingress],
    ['RATED VOLTAGE', spec.voltage],
    ['RATED CURRENT', spec.current],
  ];
  rows.forEach(([label, value], i) => {
    const y = 118 + i * 72;
    ctx.strokeStyle = 'rgba(18,20,24,.28)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(34, y - 44);
    ctx.lineTo(W - 34, y - 44);
    ctx.stroke();
    cut(label, 34, y, micro, 'left');
    cut(value, W - 34, y + 6, mono, 'right');
  });

  return canvas;
}
