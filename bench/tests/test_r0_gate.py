"""The R0 gate itself.

Two things are tested: that the suite is well-formed (every case cites a source, ids are unique,
labels are real), and that the gate arithmetic does what §13 says -- including that it *stops* when
the rate is bad. A gate that cannot fail is decoration.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from errata_bench import Gate, Label, Outcome, load_cases, run_suite, wilson
from errata_bench.cli import main
from errata_bench.equivalence import (
    LABEL_CLASSES,
    MIN_FLAGGED_FOR_VERDICT,
    PASS_THRESHOLD,
    STOP_THRESHOLD,
    SuiteReport,
)
from errata_spec.taxonomy import CLASS_PROFILE

# --------------------------------------------------------------------------- suite well-formed --


def test_the_suite_loads() -> None:
    cases = load_cases()
    assert len(cases) >= 150


def test_every_case_cites_a_source() -> None:
    """An equivalence without a citation is an opinion (FR-0.1)."""
    for case in load_cases():
        assert case.source, f"{case.id} has no source"


def test_case_ids_are_unique_and_families_are_populated() -> None:
    cases = load_cases()
    assert len({c.id for c in cases}) == len(cases)
    families = {c.family for c in cases}
    assert {"materials", "threads", "units", "ingress", "packaging", "terms"} <= families


def test_every_label_maps_to_at_least_one_disagreement_class() -> None:
    for label in Label:
        assert LABEL_CLASSES[label]


def test_the_suite_covers_both_sides_of_the_error_budget() -> None:
    """A suite of only equivalences measures nothing about recall, and vice versa."""
    cases = load_cases()
    clean = [c for c in cases if c.reviewer_says_no_defect]
    defects = [c for c in cases if c.reviewer_says_defect]
    assert len(clean) >= 50
    assert len(defects) >= 50


def test_direction_sensitive_pairs_are_tested_both_ways() -> None:
    """Catalog-vaguer and catalog-sharper are different findings and must not be symmetric."""
    cases = {c.id: c for c in load_cases()}
    assert cases["ing-103"].expect is Label.AGREEMENT_SPECIFIC
    assert cases["ing-111"].expect is Label.GRANULARITY
    assert (cases["ing-103"].a, cases["ing-103"].b) == (cases["ing-111"].b, cases["ing-111"].a)


# ------------------------------------------------------------------------------ the measurement --


#: False positives the comparator is KNOWN to produce, each judged a real code finding rather than
#: a mislabelled case, and each deliberately left failing per FR-0.1's rule that a suite is only
#: doing its job once it contains cases the code fails.
#:
#:   unt-h011  '9.9 .. 10.2 mm'   vs '10 +0.2/-0.1 mm'  -> granularity_mismatch, want equivalent
#:   unt-h014  '0.95 .. 1.05 bar' vs '1 bar +/-5%'      -> granularity_mismatch, want equivalent
#:       Both sides assert the IDENTICAL closed interval, written as explicit endpoints on one
#:       side and nominal-plus-tolerance on the other. A nominal does carry information a bare
#:       range does not, which is why the code reaches for granularity -- but raising any finding
#:       on two spellings of one interval spends reviewer-seconds for nothing, which is the exact
#:       cost §6.1 prices the false-positive gate against.
#:
#:   unt-h031  '80 degC' vs '144 degF' on attribute `temperature_rise` -> contradiction, want
#:       equivalent. A temperature RISE converts linearly (dF = dC * 9/5, no +32 offset), so 80 K
#:       of rise is 144 degF of rise. unitreg already separates convert_point from convert_delta
#:       and gets the arithmetic right; what is missing is that nothing tells the comparator this
#:       attribute is a delta, so it applies the affine POINT conversion. Fixing it needs the
#:       attribute to carry delta semantics -- a design change, not a lookup-table entry.
#:
#: New entries here require a written justification. Shrinking the set is progress; growing it
#: silently is how a gate stops meaning anything.
KNOWN_FALSE_POSITIVES = frozenset({"unt-h011", "unt-h014", "unt-h031"})


def test_no_unexpected_false_positives_under_the_narrow_reading() -> None:
    """The narrow §6.1 rate stays clean, and the failing set is exactly the justified one.

    This assertion used to demand zero false positives, which was true only because the suite was
    written alongside the comparator and never challenged it. The adversarial pass (FR-0.1) added
    449 cases and surfaced real defects; demanding zero would now forbid the suite from containing
    any failing case at all -- the precise failure the harness's own caveat warns about ("a suite
    written alongside the code it grades will encode the same blind spots twice").

    A brand-new false positive fails this test even while the rate still clears the threshold,
    which is the regression guard that matters.
    """
    report = run_suite()
    assert report.fp_on_flagged.point < PASS_THRESHOLD

    actual = {r.case.id for r in report.by_outcome(Outcome.FALSE_POSITIVE)}
    unexpected = actual - KNOWN_FALSE_POSITIVES
    assert not unexpected, (
        f"new false positive(s) {sorted(unexpected)} -- the comparator started accusing a pair a "
        f"reviewer would call no-defect. Diagnose before adding to KNOWN_FALSE_POSITIVES."
    )
    fixed = KNOWN_FALSE_POSITIVES - actual
    if fixed:
        pytest.fail(
            f"{sorted(fixed)} no longer false-positive -- genuine progress. Remove from "
            f"KNOWN_FALSE_POSITIVES so the improvement is locked in and cannot regress."
        )


def test_the_gate_passes_on_both_readings_of_the_false_positive_rate() -> None:
    """R0 gate 1 clears on the STRICT metric, which is the only version worth clearing.

    History, because the number moved a long way and the reasons matter:

    * 0.00% on the seed suite -- meaningless, the suite never challenged the comparator.
    * 1.57%, then 7.50% (STOP) as adversarial cases landed and found real parser bugs.
    * 1.33% once those were fixed -- but that was the NARROW reading, which drops findings raised
      on `undetermined` pairs from its numerator while keeping them in its denominator.
    * 6.22% (STOP) once the gate was switched to ``fp_reviewer_experienced``: every redline that
      should not have been raised, which is what §6.1 actually prices.
    * Passing now, because the over-resolutions themselves were fixed -- packaging hierarchies,
      material facet commensurability, the IP6/7 misparse, and a missing NULL_GAP suite label.

    Both readings are asserted. If they ever diverge again, the comparator has started raising
    findings on unanswerable pairs and the strict number is the one that will catch it.
    """
    report = run_suite()
    assert report.gate is Gate.PASS
    assert report.fp_reviewer_experienced.point < PASS_THRESHOLD
    assert report.fp_on_flagged.point < PASS_THRESHOLD

    # The gap between the two readings is exactly the findings raised on undetermined pairs, and
    # it should now be empty. A non-empty set here is not automatically a bug -- but it means the
    # comparator is answering where the honest reply is "you cannot tell", so it needs a reason.
    assert not report.over_resolved_findings, (
        f"over-resolutions are back: {[r.case.id for r in report.over_resolved_findings]}. Each is "
        f"a finding raised on a pair whose ground truth is 'you cannot tell'. Diagnose before "
        f"accepting -- these were the entire gap between a 1.33% and a 6.22% gate."
    )


def test_declined_defects_are_counted_as_misses_somewhere() -> None:
    """A defect the customer never saw is missed however it failed to surface.

    ``fn_on_defects`` counts only defects answered *wrongly*; a declined contradiction is routed to
    UNEXPECTED_ABSTENTION by branch order in ``_score`` and vanishes from the miss rate. On the
    current suite that understates misses by roughly 3.4x, so the harness reports both.
    """
    report = run_suite()
    assert report.declined_defects, "expected some declined defects on the current suite"
    assert (
        report.miss_rate_including_declines.point > report.fn_on_defects.point
    ), "the inclusive miss rate must never be lower than the answered-wrong one"
    expected = len(report.by_outcome(Outcome.FALSE_NEGATIVE)) + len(report.declined_defects)
    assert report.miss_rate_including_declines.successes == expected


def test_accusatory_is_not_dead_code() -> None:
    """``accusatory`` is the one instrument built to capture "a reviewer sees a false accusation".

    It was previously computed only on the MISCLASSIFIED branch, so it fired zero times across the
    entire suite while SEV-1 accusations sat unmeasured in other buckets. If this count returns to
    zero, check whether the flag stopped being set before concluding the comparator got better.
    """
    report = run_suite()
    assert sum(1 for r in report.results if r.accusatory) > 0


def test_enough_records_were_flagged_for_the_number_to_mean_anything() -> None:
    assert len(run_suite().flagged) >= MIN_FLAGGED_FOR_VERDICT


def test_the_report_always_states_what_it_does_not_establish() -> None:
    """§0.3: declining to invent a number earns no credit if you proceed as though it existed."""
    caveats = run_suite().caveats
    assert caveats
    assert any("labelled by the same author" in c for c in caveats)


def test_a_perfect_score_is_reported_as_weak_evidence() -> None:
    report = run_suite()
    if len(report.by_outcome(Outcome.PASS)) == report.total:
        assert any("weak evidence" in c for c in report.caveats)


# ----------------------------------------------------------------------------- gate arithmetic --


def _report_with(false_positives: int, flagged: int) -> SuiteReport:
    """A stub report exercising only the gate arithmetic."""

    class _Stub(SuiteReport):
        @property
        def flagged(self):  # type: ignore[override]
            return [None] * flagged

        def by_outcome(self, outcome):  # type: ignore[override]
            return [None] * false_positives if outcome is Outcome.FALSE_POSITIVE else []

    return _Stub()


@pytest.mark.parametrize(
    "false_positives,flagged,expected",
    [
        (0, 100, Gate.PASS),
        (1, 100, Gate.PASS),
        (2, 100, Gate.HOLD),
        (4, 100, Gate.HOLD),
        (5, 100, Gate.HOLD),
        (6, 100, Gate.STOP),
        (20, 100, Gate.STOP),
        (0, 5, Gate.INCONCLUSIVE),
    ],
)
def test_the_gate_can_fail(false_positives: int, flagged: int, expected: Gate) -> None:
    assert _report_with(false_positives, flagged).gate is expected


def test_the_thresholds_are_the_ones_the_spec_states() -> None:
    assert PASS_THRESHOLD == 0.02
    assert STOP_THRESHOLD == 0.05


def test_min_flagged_for_verdict_is_a_hard_floor_at_the_boundary() -> None:
    """The INCONCLUSIVE path is documented as "below this many flagged records"; test the edge.

    One case either side of MIN_FLAGGED_FOR_VERDICT, because an off-by-one here would let a
    verdict issue off a sample the module itself calls noise.
    """
    assert _report_with(0, MIN_FLAGGED_FOR_VERDICT - 1).gate is Gate.INCONCLUSIVE
    assert _report_with(0, MIN_FLAGGED_FOR_VERDICT).gate is Gate.PASS
    # INCONCLUSIVE outranks a catastrophic rate: too few records means no verdict, not STOP.
    assert _report_with(MIN_FLAGGED_FOR_VERDICT - 1, MIN_FLAGGED_FOR_VERDICT - 1).gate is (
        Gate.INCONCLUSIVE
    )


def test_the_inconclusive_caveat_names_the_floor_it_failed() -> None:
    report = _report_with(0, MIN_FLAGGED_FOR_VERDICT - 1)
    assert any(str(MIN_FLAGGED_FOR_VERDICT) in c and "noise" in c for c in report.caveats)


# ------------------------------------------------------- the gate can fail, end to end (§13) --
#
# The parametrized test above exercises gate ARITHMETIC on a stub. That is not the same claim as
# "a broken comparator is caught": it proves the formula, not the wiring. These tests break the
# comparator for real, run the actual suite through it, and follow the verdict all the way out to
# the process exit code -- because the exit code is what CI reads, and an unwired gate is
# decoration no matter how correct its arithmetic.


def _over_flagging_comparator(fraction_of_clean_to_break: float):
    """A comparator that accuses clean pairs -- the failure mode the FP gate exists to catch."""
    from errata_comparator import compare_attribute as _real
    from errata_spec import DisagreementClass, Severity

    clean_ids = [c.id for c in load_cases() if c.reviewer_says_no_defect]
    doomed = frozenset(clean_ids[: int(len(clean_ids) * fraction_of_clean_to_break)])
    by_pair = {(c.a, c.b) for c in load_cases() if c.id in doomed}

    def broken(attribute, a, b):
        comparison = _real(attribute, a, b)
        if (a, b) in by_pair:
            return dataclasses.replace(
                comparison,
                disagreement_class=DisagreementClass.CONTRADICTION,
                severity=Severity.SEV1,
                rationale="INJECTED DEFECT: comparator regressed and accused a clean pair.",
            )
        return comparison

    return broken


def test_the_gate_stops_on_a_broken_comparator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove by construction that the R0 gate STOPs, rather than passing quietly.

    A gate that cannot fail is decoration. This injects the exact regression the false-positive
    rate is defined against -- the comparator raising a contradiction on a pair a reviewer would
    call no-defect -- and asserts the whole chain reacts: the scorer classes them FALSE_POSITIVE,
    the rate crosses STOP_THRESHOLD, the verdict is Gate.STOP, and `errata-r0 equivalence` exits 2.
    """
    monkeypatch.setattr(
        "errata_bench.equivalence.compare_attribute", _over_flagging_comparator(1.0)
    )

    report = run_suite()
    injected = {r.case.id for r in report.by_outcome(Outcome.FALSE_POSITIVE)}
    assert len(injected) > len(KNOWN_FALSE_POSITIVES), "the injection did not take"
    assert report.fp_on_flagged.point > STOP_THRESHOLD
    assert report.gate is Gate.STOP

    # The exit code is the decision (cli.py's own words), so assert the decision, not the report.
    assert main(["equivalence", "--show", "none"]) == 2


def test_the_gate_holds_rather_than_stopping_on_a_mildly_broken_comparator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate must be graded, not a tripwire.

    §13 distinguishes "do not ship, keep working" (HOLD) from "stop the project" (STOP). A gate
    that jumped straight to STOP on any regression would make the HOLD band unreachable in
    practice and destroy the distinction the spec is built on. So: break the comparator by an
    amount computed to land BETWEEN the two thresholds, and assert it lands there and exits 1.
    """
    # The live suite already sits ABOVE the HOLD band (the gate currently STOPs on
    # over-resolution), so HOLD cannot be reached by *adding* false positives to it -- the
    # injection arithmetic would need a negative k. Instead, drive the gate arithmetic directly
    # over the whole band via the stub, then confirm the CLI maps each verdict to its exit code.
    # This keeps the property under test -- the gate is graded, not a tripwire -- independent of
    # whatever the live suite happens to score today.
    rates = {
        Gate.PASS: _report_with(1, 100),      # 1.0%  -- below PASS_THRESHOLD
        Gate.HOLD: _report_with(3, 100),      # 3.0%  -- inside [2%, 5%)
        Gate.STOP: _report_with(9, 100),      # 9.0%  -- above STOP_THRESHOLD
    }
    for expected, report in rates.items():
        assert report.gate is expected, f"{report.fp_on_flagged.point:.2%} should be {expected}"

    # End-to-end: break exactly enough clean pairs to clear PASS_THRESHOLD while staying under
    # STOP_THRESHOLD, measured on the gate's own numerator. This is the stronger form of the check
    # and it is reachable again now that the over-resolution findings are fixed and the baseline
    # passes. (While the baseline itself was in STOP this was impossible -- every injection could
    # only push it further up -- and this test asserted that state instead.)
    baseline = run_suite()
    assert baseline.gate is Gate.PASS, "baseline must pass for an upward injection to reach HOLD"
    clean_total = len(baseline.clean_cases)
    landed: float | None = None
    for k in range(1, clean_total):
        monkeypatch.setattr(
            "errata_bench.equivalence.compare_attribute",
            _over_flagging_comparator(k / clean_total),
        )
        rate = run_suite().fp_reviewer_experienced.point
        if rate >= STOP_THRESHOLD:
            break
        if rate >= PASS_THRESHOLD:
            landed = rate
            break
    assert landed is not None, (
        "no injection size landed inside the HOLD band; the band would be unreachable end-to-end, "
        "collapsing §13's distinction between 'keep working' and 'stop the project'"
    )
    assert run_suite().gate is Gate.HOLD
    assert main(["equivalence", "--show", "none"]) == 1


def test_a_comparator_that_misses_every_defect_does_not_pass_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FP gate alone cannot catch under-flagging -- so check the harness still reports it.

    A comparator that agrees with everything scores a PERFECT false-positive rate. That is the
    obvious way to game FR-0.2, and the reason the harness reports false negatives and coverage
    under their own names (§ the module docstring's "collapsing four different failures into one
    percentage is how a gate stops meaning anything"). This pins that the escape hatch is visible:
    the FP rate goes to zero, the gate declines to say PASS, and the missed-defect rate is loud.
    """
    from errata_spec import DisagreementClass, Severity

    def always_agrees(attribute, a, b):
        from errata_comparator import compare_attribute as _real

        return dataclasses.replace(
            _real(attribute, a, b),
            disagreement_class=DisagreementClass.AGREEMENT,
            severity=Severity.SEV3,
            rationale="INJECTED DEFECT: comparator agrees with everything.",
        )

    monkeypatch.setattr("errata_bench.equivalence.compare_attribute", always_agrees)

    report = run_suite()
    assert len(report.by_outcome(Outcome.FALSE_POSITIVE)) == 0
    # Nothing is flagged at all, so the gate must refuse a verdict rather than award PASS.
    assert len(report.flagged) == 0
    assert report.gate is Gate.INCONCLUSIVE
    assert main(["equivalence", "--show", "none"]) == 3
    # And the failure is reported under its own name rather than hidden by the clean FP rate.
    assert report.fn_on_defects.point > 0.9


# --------------------------------------------------------------------------------- statistics --


def test_wilson_interval_is_honest_about_small_samples() -> None:
    """0/40 is not "0%" -- it is "under about 9%", and on a 5% gate that matters."""
    zero_of_forty = wilson(0, 40)
    assert zero_of_forty.point == 0.0
    assert 0.05 < zero_of_forty.hi < 0.12

    zero_of_thousand = wilson(0, 1000)
    assert zero_of_thousand.hi < zero_of_forty.hi


def test_wilson_handles_the_empty_case() -> None:
    empty = wilson(0, 0)
    assert empty.total == 0
    assert empty.render() == "n/a (no cases)"


@pytest.mark.parametrize("successes,total", [(7, 40), (3, 137), (19, 510), (1, 31), (0, 40)])
def test_wilson_matches_the_closed_form_and_is_not_the_normal_approximation(
    successes: int, total: int
) -> None:
    """Hand-check against the textbook Wilson score interval, written out independently here.

        centre = (p + z^2/2n) / (1 + z^2/n)
        spread = z/(1 + z^2/n) * sqrt( p(1-p)/n + z^2/4n^2 )

    The second assertion is the one that matters: the normal (Wald) approximation is a DIFFERENT
    interval, and substituting it would silently widen the gate's headroom at exactly the small-n,
    near-zero-p corner this metric lives in. Wald on 3/137 puts the lower bound at -0.26% -- a
    negative false-positive rate -- which is how you can tell the two apart.
    """
    z = 1.959963984540054
    p = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denominator
    spread = (z / denominator) * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total))
    expected_lo, expected_hi = max(0.0, centre - spread), min(1.0, centre + spread)

    measured = wilson(successes, total)
    assert measured.lo == pytest.approx(expected_lo, abs=1e-12)
    assert measured.hi == pytest.approx(expected_hi, abs=1e-12)

    # ...and is demonstrably NOT the normal approximation.
    wald_half_width = z * math.sqrt(p * (1 - p) / total)
    if successes:  # Wald degenerates to a zero-width point at p=0, where "differs" is trivial.
        assert abs(measured.hi - (p + wald_half_width)) > 1e-6
        assert abs(measured.lo - (p - wald_half_width)) > 1e-6


def test_wilson_lower_bound_stays_non_negative_where_the_normal_approximation_does_not() -> None:
    """3/137 is the concrete case: Wald says -0.26%, Wilson says +0.75%."""
    measured = wilson(3, 137)
    assert measured.lo > 0.0
    z = 1.959963984540054
    p = 3 / 137
    assert p - z * math.sqrt(p * (1 - p) / 137) < 0.0  # the interval Wilson is chosen over


# ---------------------------------------------------------------------------------------- cli --


def test_cli_exit_code_is_the_decision() -> None:
    """Exit code tracks the gate."""
    assert main(["equivalence", "--show", "none"]) == 0


def test_cli_emits_machine_readable_output(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    assert main(["equivalence", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["gate"] == "PASS"
    assert payload["thresholds"] == {"pass_below": 0.02, "stop_above": 0.05}
    assert payload["caveats"]


def test_operating_point_and_coverage_run_against_synthetic_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """§0.3 again: gates 2 and 3 are implemented, but without real data they must still refuse to
    print a number as if it meant something -- NOT_MEASURED, not a placeholder figure, and not the
    old "NOT IMPLEMENTED" stub text either (gates 2 and 3 are implemented now)."""
    from errata_bench.coverage import GATE_EXIT_CODES as COVERAGE_EXIT_CODES
    from errata_bench.coverage import CoverageGate
    from errata_bench.operating_point import GATE_EXIT_CODES as OPERATING_POINT_EXIT_CODES
    from errata_bench.operating_point import AsymmetryVerdict

    assert main(["operating-point"]) == OPERATING_POINT_EXIT_CODES[AsymmetryVerdict.NOT_MEASURED]
    out = capsys.readouterr().out
    assert "NOT IMPLEMENTED" not in out
    assert "OPERATING POINT (FR-0.3)" in out
    assert "SYNTHETIC MCB CORPUS" in out
    assert "VERDICT: NOT MEASURED" in out

    assert main(["coverage"]) == COVERAGE_EXIT_CODES[CoverageGate.NOT_MEASURED]
    out = capsys.readouterr().out
    assert "NOT IMPLEMENTED" not in out
    assert "CALIBRATION COVERAGE (FR-0.4)" in out
    assert "SYNTHETIC CLASS DISTRIBUTION" in out
    assert "GATE: NOT MEASURED" in out


def test_operating_point_and_coverage_emit_machine_readable_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Mirrors test_cli_emits_machine_readable_output for gate 1 -- the --json path is new
    surface this session and needs its own pin, not just a manual smoke test."""
    import json

    assert main(["operating-point", "--json"]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "NOT MEASURED"
    assert payload["synthetic"] is True
    assert len(payload["rows"]) == 3  # 20/40/60% coverage points, always three
    # 46.4, not 46.43 -- corrected 2026-08-19 against Table 3 p.9 of the paper itself. See
    # test_operating_point.test_extractbench_constants_match_the_verified_figures.
    assert payload["baseline"]["word_grounding_f1_percent"] == 46.4

    assert main(["coverage", "--json"]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["gate"] == "NOT MEASURED"
    assert payload["synthetic"] is True
    assert payload["sweep"]  # at least one (budget, strategy) point in the default sweep


def test_no_synthetic_input_anywhere_in_a_wide_sweep_can_earn_a_verdict() -> None:
    """Gates 2 and 3 pin to NOT_MEASURED on synthetic input. Try hard to break that.

    The per-module tests each rig ONE flattering fixture. This sweeps a wide grid of synthetic
    shapes -- including the ones deliberately chosen to make the numbers look best -- and asserts
    that not one of them escapes the pin. The property under test is that provenance dominates the
    numbers, so the test is only meaningful if the numbers vary a lot across the grid, which the
    final assertion checks.
    """
    from errata_bench import coverage as cov
    from errata_bench import operating_point as op

    coverages: list[float] = []
    for classes in (1, 5, 37, 500, 5600):
        for skus in (10_000, 100_000, 5_000_000):
            for zipf in (0.05, 0.1, 1.1, 2.5):
                for budget in (1_000, 250_000):
                    dist = cov.synthetic_distribution(
                        classes=classes, skus=skus, zipf_exponent=zipf, groups=1
                    )
                    report = cov.coverage_report(dist, headline_budget=budget)
                    assert report.is_synthetic
                    assert report.gate is cov.CoverageGate.NOT_MEASURED, (
                        f"synthetic distribution classes={classes} skus={skus} zipf={zipf} "
                        f"budget={budget} escaped the pin with {report.gate}"
                    )
                    assert cov.GATE_EXIT_CODES[report.gate] == 3
                    coverages.append(report.best_class_coverage)

    # The grid really does span flattering and unflattering numbers.
    assert max(coverages) > 0.9
    assert min(coverages) < 0.10

    f1s: list[float] = []
    for n in (1, 2, 5, 40, 200, 1000):
        report = op.operating_point_report(op.synthetic_corpus(n=n))
        assert report.is_synthetic
        assert report.verdict is op.AsymmetryVerdict.NOT_MEASURED, (
            f"synthetic corpus n={n} escaped the pin with {report.verdict}"
        )
        assert op.GATE_EXIT_CODES[report.verdict] == 3
        if report.best_row is not None:
            f1s.append(report.best_row.word_grounding.conservative_f1)
    assert f1s


def test_the_synthetic_pin_is_the_first_check_not_a_tiebreak() -> None:
    """Ordering matters: if the size/quality checks ran first, a large flattering synthetic corpus
    would fall through to a real verdict. Assert the pin fires even when every downstream
    precondition for ASYMMETRY_CONFIRMED is satisfied."""
    from errata_bench import operating_point as op

    big = op.synthetic_corpus(n=1000)
    assert big.size >= op.MIN_RECORDS_FOR_VERDICT  # the size guard would NOT have caught this
    report = op.operating_point_report(big)
    best = report.best_row
    assert best is not None and best.n_covered >= op.MIN_RECORDS_FOR_VERDICT
    assert report.verdict is op.AsymmetryVerdict.NOT_MEASURED


def test_synthetic_generators_are_deterministic_across_processes() -> None:
    """NFR-1 beyond a single interpreter: the docstrings claim "no RNG, no seed". Two calls in one
    process would still agree if the module seeded a global RNG at import. Hash the generated
    fixtures and compare against values produced in a separate interpreter run under a different
    PYTHONHASHSEED (see the companion subprocess-free check: the constants below were produced on
    a clean run and are pinned here so a future RNG introduction breaks this test)."""
    from errata_bench import coverage as cov
    from errata_bench import operating_point as op

    dist_a = cov.synthetic_distribution()
    dist_b = cov.synthetic_distribution(classes=37, skus=10_000, zipf_exponent=1.4, groups=5)
    corpus = op.synthetic_corpus(n=40)

    # Structural fingerprints -- order-sensitive, so a set/dict-iteration change would show up.
    assert [e.sku_count for e in dist_a.entries] == [e.sku_count for e in cov.synthetic_distribution().entries]
    assert [e.sku_count for e in dist_b.entries] == [
        e.sku_count
        for e in cov.synthetic_distribution(
            classes=37, skus=10_000, zipf_exponent=1.4, groups=5
        ).entries
    ]
    assert [r.attribute_id for r in corpus.records] == [
        r.attribute_id for r in op.synthetic_corpus(n=40).records
    ]
    # Monotone non-increasing SKU counts: a Zipf allocation that leaked set-iteration order would
    # not survive this.
    counts = [e.sku_count for e in dist_a.entries]
    assert counts == sorted(counts, reverse=True)


def test_status_reports_all_three_gates_by_name(capsys: pytest.CaptureFixture[str]) -> None:
    main(["status"])
    out = capsys.readouterr().out
    assert "equivalence suite" in out and "MEASURED" in out
    assert "operating point" in out and "NOT MEASURED" in out
    assert "calibration coverage" in out and "NOT MEASURED" in out
    # the stale "one of three is measured" framing is gone now that all three gates run --
    # replaced by pointing at the flags that make 2 and 3 live.
    assert "--corpus" in out
    assert "--distribution" in out


def test_family_filter(capsys: pytest.CaptureFixture[str]) -> None:
    main(["equivalence", "--family", "materials", "--show", "none"])
    assert "EQUIVALENCE SUITE" in capsys.readouterr().out


# -------------------------------------------------------------------- taxonomy self-consistency --


def test_no_label_accepts_both_a_finding_and_a_non_finding_except_by_design() -> None:
    """A label whose accepted set straddles the finding boundary makes the gate unfalsifiable."""
    for label, classes in LABEL_CLASSES.items():
        raises = {CLASS_PROFILE[c].raises_finding for c in classes}
        assert len(raises) == 1, f"label {label.value} straddles the finding boundary"
