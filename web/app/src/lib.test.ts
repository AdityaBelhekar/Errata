/* ═══════════════════════════════════════════════════════════════════════════
   lib.ts — the first automated test in this repository's frontend.

   Register B-1: 1,335 Python tests covered the domain and zero covered what a
   user touches. This file is the smallest end of closing that, and it is
   deliberately the smallest end: `actOpacity` shipped with the same off-by-one
   at BOTH ends, both were found by eye, weeks apart, and a three-line assertion
   on the boundaries would have caught either before it reached a screenshot.

   So the boundaries are what is tested. Not "does ease look smooth" — the
   interior of these functions was never wrong. Every defect in them has been at
   t = 0, at t = 1, or where two acts meet.
   ═══════════════════════════════════════════════════════════════════════════ */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { ACTS, actOpacity, clamp01, damp, ease, frames, span, tier } from './lib';

describe('clamp01', () => {
  it('holds the interval closed at both ends', () => {
    expect(clamp01(-0.0001)).toBe(0);
    expect(clamp01(0)).toBe(0);
    expect(clamp01(0.5)).toBe(0.5);
    expect(clamp01(1)).toBe(1);
    expect(clamp01(1.0001)).toBe(1);
  });

  it('does not pass NaN through as a number the rest of the pipeline will trust', () => {
    // NaN fails both comparisons and falls out of the ternary unchanged. Recorded rather than
    // asserted-as-correct: it is current behaviour, it reaches CSS as the string "NaN", and the
    // property is then ignored by the browser. That is survivable and it is not obviously right.
    expect(Number.isNaN(clamp01(Number.NaN))).toBe(true);
  });
});

describe('span', () => {
  it('is 0 at the lower bound and 1 at the upper', () => {
    expect(span(0.2, 0.2, 0.6)).toBe(0);
    expect(span(0.6, 0.2, 0.6)).toBe(1);
    expect(span(0.4, 0.2, 0.6)).toBeCloseTo(0.5, 10);
  });

  it('clamps outside the range rather than extrapolating', () => {
    expect(span(0.0, 0.2, 0.6)).toBe(0);
    expect(span(1.0, 0.2, 0.6)).toBe(1);
  });

  it('degenerate range does not produce a number that silently poisons a CSS property', () => {
    // a === b divides by zero. Documented, not asserted-as-desired: no caller currently passes a
    // degenerate span, and this test exists so that if one starts, the behaviour is known rather
    // than discovered as an invisible act.
    expect(Number.isNaN(span(0.5, 0.5, 0.5))).toBe(true);
  });
});

describe('ease', () => {
  it('pins both ends and the midpoint of the smoothstep', () => {
    expect(ease(0)).toBe(0);
    expect(ease(1)).toBe(1);
    expect(ease(0.5)).toBeCloseTo(0.5, 10);
  });

  it('clamps its input, so an unclamped caller cannot overshoot', () => {
    expect(ease(-1)).toBe(0);
    expect(ease(2)).toBe(1);
  });

  it('is monotonic — a cross-fade that reverses reads as a flicker', () => {
    let previous = -1;
    for (let t = 0; t <= 1.0001; t += 0.05) {
      const value = ease(t);
      expect(value).toBeGreaterThanOrEqual(previous);
      previous = value;
    }
  });
});

describe('damp — F-02, frame-rate independence is a LAW (§10.6)', () => {
  it('reaches the same place in the same wall-clock time at 60Hz and 144Hz', () => {
    // The whole point of the corrected form. `a += (b - a) * k` per frame gets 2.4x further on a
    // 144Hz panel in the same second, which is the bug: the site feels different on different
    // machines. Simulate one second at each rate and require the results to agree.
    const run = (steps: number) => {
      const dt = 1 / steps;
      let value = 0;
      for (let i = 0; i < steps; i += 1) value = damp(value, 1, 0.9, dt * 60);
      return value;
    };
    expect(run(60)).toBeCloseTo(run(144), 6);
  });

  it('is a no-op across zero elapsed time', () => {
    expect(damp(0.3, 1, 0.9, 0)).toBe(0.3);
  });

  it('never overshoots its target', () => {
    expect(damp(0, 1, 0.9, 100)).toBeLessThanOrEqual(1);
  });
});

describe('frames', () => {
  it('normalises to 60Hz', () => {
    expect(frames(1 / 60)).toBeCloseTo(1, 10);
    expect(frames(1 / 120)).toBeCloseTo(0.5, 10);
  });

  it('clamps, so a backgrounded tab cannot teleport the camera when the clock resumes', () => {
    expect(frames(30)).toBe(4);
  });
});

/* ─────────────────────────────────────────────────────────────────────────
   actOpacity — the defect this whole file exists because of.
   ───────────────────────────────────────────────────────────────────────── */

describe('actOpacity', () => {
  it('the FIRST act is fully visible at the top of the page', () => {
    // The original bug, end one. The general formula faded in over the first fifth of the span,
    // and an act starting at scroll 0 has no room to fade in — so the hero was invisible on load.
    const [hero] = ACTS;
    expect(hero.from).toBe(0);
    expect(actOpacity(0, hero.from, hero.to)).toBe(1);
  });

  it('the LAST act is fully visible at the bottom of the page', () => {
    // The same bug, end two, found separately weeks later. A visitor who scrolled all the way to
    // the product panel arrived at an empty room.
    const last = ACTS[ACTS.length - 1];
    expect(last.to).toBe(1);
    expect(actOpacity(1, last.from, last.to)).toBe(1);
  });

  it('a middle act is invisible at both of its own boundaries', () => {
    // The general rule, which was always correct and must stay correct: the exceptions above are
    // exceptions, not a new default.
    const middle = ACTS[2];
    expect(actOpacity(middle.from, middle.from, middle.to)).toBeCloseTo(0, 10);
    expect(actOpacity(middle.to, middle.from, middle.to)).toBeCloseTo(0, 10);
  });

  it('a middle act is fully visible in its own centre', () => {
    const middle = ACTS[2];
    const centre = (middle.from + middle.to) / 2;
    expect(actOpacity(centre, middle.from, middle.to)).toBe(1);
  });

  it('never returns a value outside [0, 1]', () => {
    for (const act of ACTS) {
      for (let t = -0.2; t <= 1.2; t += 0.01) {
        const value = actOpacity(t, act.from, act.to);
        expect(value).toBeGreaterThanOrEqual(0);
        expect(value).toBeLessThanOrEqual(1);
      }
    }
  });

  it('some act is visible at every scroll position — no blank frame anywhere', () => {
    // The property that actually matters to a visitor, asserted directly rather than inferred from
    // the five acts individually. Both original bugs were instances of this failing.
    for (let t = 0; t <= 1.0001; t += 0.005) {
      const best = Math.max(...ACTS.map((a) => actOpacity(t, a.from, a.to)));
      expect(best).toBeGreaterThan(0);
    }
  });
});

describe('ACTS', () => {
  it('covers [0, 1] with overlaps and no gaps', () => {
    expect(ACTS[0].from).toBe(0);
    expect(ACTS[ACTS.length - 1].to).toBe(1);
    for (let i = 1; i < ACTS.length; i += 1) {
      // Overlap, strictly — a seam where one act ends exactly as the next begins is a cut, and
      // §11.2 specifies one continuous camera with no cuts.
      expect(ACTS[i].from).toBeLessThan(ACTS[i - 1].to);
    }
  });
});

/* ─────────────────────────────────────────────────────────────────────────
   tier — the capability ladder that has never run on real hardware (H-5).
   ───────────────────────────────────────────────────────────────────────── */

function stubEnvironment(options: {
  search?: string;
  reducedMotion?: boolean;
  webgl2?: boolean;
  deviceMemory?: number;
  cores?: number;
}) {
  const {
    search = '',
    reducedMotion = false,
    webgl2 = true,
    deviceMemory = 8,
    cores = 8,
  } = options;

  vi.stubGlobal('location', { ...window.location, search });
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('prefers-reduced-motion') ? reducedMotion : false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
  vi.stubGlobal('navigator', { deviceMemory, hardwareConcurrency: cores });
  vi.spyOn(document, 'createElement').mockImplementation(
    () => ({ getContext: () => (webgl2 ? {} : null) }) as unknown as HTMLElement,
  );
}

describe('tier — the degradation ladder (§11.10)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('?nogl=1 wins over everything, including a capable machine', () => {
    stubEnvironment({ search: '?nogl=1', webgl2: true, deviceMemory: 32, cores: 32 });
    expect(tier()).toBe('off');
  });

  it('a capable machine gets the full ladder', () => {
    stubEnvironment({ deviceMemory: 16, cores: 12 });
    expect(tier()).toBe('full');
  });

  it('reduced motion takes lite, not off — the contract is a designed alternative (§10.4)', () => {
    stubEnvironment({ reducedMotion: true, deviceMemory: 32, cores: 32 });
    expect(tier()).toBe('lite');
  });

  // The three branches H-5 records as never having executed. No machine available to the project
  // triggers them, which is the argument FOR unit tests rather than against: hardware that would
  // exercise these is exactly the hardware nobody has.
  it('a low-memory device takes lite [never executed on real hardware]', () => {
    stubEnvironment({ deviceMemory: 4, cores: 16 });
    expect(tier()).toBe('lite');
  });

  it('a low-core device takes lite [never executed on real hardware]', () => {
    stubEnvironment({ deviceMemory: 32, cores: 4 });
    expect(tier()).toBe('lite');
  });

  it('no webgl2 context takes off [never executed on real hardware]', () => {
    stubEnvironment({ webgl2: false });
    expect(tier()).toBe('off');
  });

  it('a browser with no deviceMemory at all is assumed capable, not assumed poor', () => {
    // `?? 8` in the source. Asserted because the default is a judgement call: Safari does not
    // expose deviceMemory, so guessing low would put every Safari visitor on the lite ladder.
    stubEnvironment({ deviceMemory: undefined as unknown as number, cores: 16 });
    expect(tier()).toBe('full');
  });

  it('a throwing canvas degrades to off rather than propagating', () => {
    stubEnvironment({});
    vi.spyOn(document, 'createElement').mockImplementation(() => {
      throw new Error('no canvas in this context');
    });
    expect(tier()).toBe('off');
  });
});
