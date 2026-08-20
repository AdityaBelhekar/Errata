"""Finding 17: dual-labelling must not be able to launder a defect into a PASS.

``Case.accepted`` unions the disagreement classes of every label a case carries, so a case
labelled ``equivalent`` *and* ``contradiction`` scores PASS whichever way the comparator answers.
That is reasonable when the alternatives are adjacent readings a reviewer might genuinely go
either way on. It is not reasonable when the two readings straddle "raise nothing" and "raise a
SEV-1 finding", because those have opposite consequences for the person reading the queue.

The measured exposure, 2026-08-19: the gate reports **1.30%** and the same suite reports
**4.78%** once every contested finding is resolved against the comparator. 4.78% is above the 2%
PASS threshold and its upper bound is above the 5% STOP threshold. **The headline PASS is real
but conditional**, and the condition is a set of judgment calls made by the same author who wrote
the comparator -- which is exactly what FR-0.1's independent dual-labelling exists to settle.

These tests do not decide which reading is right. That is a domain judgment and it belongs to the
independent labeller. They pin the exposure so it cannot grow quietly, in the same spirit as
``KNOWN_FALSE_POSITIVES`` in ``test_r0_gate.py``: shrinking this set is progress, growing it
silently is how a gate stops meaning anything.
"""

from __future__ import annotations

import pytest

from errata_bench.equivalence import (
    PASS_THRESHOLD,
    Gate,
    Label,
    SuiteReport,
    load_cases,
    run_suite,
)

#: Every case currently carrying a second label that says "raise nothing", where the comparator
#: raises something. Frozen 2026-08-19. A new entry means either a new over-resolution or a new
#: laundered label, and both want a human decision before the build goes green.
KNOWN_CONTESTED = {
    # The sharp ones: `equivalent` against `contradiction`. The quantities MATCH on all four --
    # twelve against twelve, two against two, a hundred against a hundred -- so the SEV-1
    # packaging-frame error's own stated harm (the line is priced wrong) cannot apply. These are
    # the four HANDOFF section 6 names.
    "pkg-010",   # 'Dozen'   vs 'Box of 12'
    "pkg-h026",  # 'Pair'    vs 'Box of 2'
    "pkg-h031",  # 'Dozen'   vs 'Case of 12'
    "pkg-h035",  # 'Hundred' vs 'Box of 100'
    # Softer: the alternative is `undetermined` or `agreement_specific` rather than `equivalent`,
    # so the contest is between "raise a finding" and "decline", not between a finding and
    # nothing at all. Still counted, because a reviewer who should have seen nothing saw a row.
    "mat-202",   # '316' vs '316L'
    "trm-105",   # '4P' vs '3P+N'
    "trm-h071",  # 'Circuit breaker' vs 'RCBO'
    "trm-h072",  # 'Circuit breaker' vs 'RCCB'
}

#: The subset where one accepted label is `equivalent` outright -- the strongest form of the
#: problem, because `equivalent` means the record should never have reached a human at all.
KNOWN_CONTESTED_AT_ZERO_DEFECT = {"pkg-010", "pkg-h026", "pkg-h031", "pkg-h035"}


@pytest.fixture(scope="module")
def report() -> SuiteReport:
    return run_suite(load_cases())


def test_the_contested_set_has_not_grown(report: SuiteReport) -> None:
    observed = {r.case.id for r in report.contested_findings}
    new = observed - KNOWN_CONTESTED
    assert not new, (
        f"new contested finding(s): {sorted(new)}. Either the comparator started raising on a "
        "dual-labelled case it used to leave alone, or a case gained a second label that lets a "
        "finding score PASS. Decide which, in the open."
    )


def test_the_contested_set_is_pinned_honestly(report: SuiteReport) -> None:
    """If the set shrinks, that is progress -- but the constant must be updated to say so,
    otherwise the next reader believes a stale number."""
    observed = {r.case.id for r in report.contested_findings}
    gone = KNOWN_CONTESTED - observed
    assert not gone, (
        f"{sorted(gone)} no longer contested -- good. Remove them from KNOWN_CONTESTED and "
        "record what changed in PROGRESS.md."
    )


def test_the_zero_defect_contests_are_all_packaging_frame_errors(report: SuiteReport) -> None:
    """The four sharpest cases share one root cause, which is what makes them a finding
    rather than four coincidences: a quantity word against a container noun at the SAME
    quantity, resolved as a SEV-1 frame error."""
    for r in report.contested_findings:
        if r.case.id in KNOWN_CONTESTED_AT_ZERO_DEFECT:
            assert Label.EQUIVALENT in r.case.labels
            assert r.actual.value == "packaging_frame_error", (
                f"{r.case.id} used to resolve as a packaging-frame error and now resolves as "
                f"{r.actual.value}; the finding-17 analysis needs redoing"
            )


def test_the_adversarial_rate_is_reported_and_is_worse_than_the_gate(report: SuiteReport) -> None:
    """The whole point of the metric: it must be able to disagree with the headline.

    A sensitivity band that cannot move is decoration. This asserts the two numbers are
    genuinely different, so that if someone later makes them identical by construction the
    test says so.
    """
    assert report.fp_adversarial.point > report.fp_reviewer_experienced.point
    assert report.fp_adversarial.successes == (
        len(report.contested_findings)
        + report.fp_reviewer_experienced.successes
    )
    assert report.fp_adversarial.total == report.fp_reviewer_experienced.total


def test_the_gate_still_judges_on_the_strict_metric_not_the_adversarial_one(
    report: SuiteReport,
) -> None:
    """Ground rule 8. The band informs; it does not silently become the verdict.

    Changing which metric the gate reads is a decision for a human, not a side effect of adding
    an instrument. This test exists so that such a change cannot happen by accident.
    """
    assert report.fp_adversarial.point > PASS_THRESHOLD, (
        "the adversarial reading no longer exceeds the PASS threshold -- if the contested cases "
        "were resolved, update this test and PROGRESS.md; if the threshold moved, stop"
    )
    assert report.gate is Gate.PASS, (
        "the gate verdict must still come from fp_reviewer_experienced"
    )


def test_every_contested_case_is_actually_dual_labelled(report: SuiteReport) -> None:
    """Guards the metric against catching single-labelled cases, which `over_resolved_findings`
    already counts -- double-counting would inflate the band and make it easy to dismiss."""
    for r in report.contested_findings:
        assert r.case.is_dual_labelled
        assert len(r.case.labels) >= 2


# ---------------------------------------------------------------------------------------------
# Finding 18: the straddling cases and the denominators they fall out of.
# ---------------------------------------------------------------------------------------------

#: Cases whose labels straddle defect and no-defect, so they appear in neither supporting
#: denominator. Frozen 2026-08-19. Every one is dual-labelled -- that is the only way to be in
#: both camps at once.
KNOWN_STRADDLING = {
    "mat-202", "pkg-010", "pkg-h026", "pkg-h031", "pkg-h035",
    "tol-007", "trm-105", "trm-h071", "trm-h072", "uni-306", "unt-h032",
}


def test_the_straddling_set_is_exactly_what_was_measured(report: SuiteReport) -> None:
    observed = {r.case.id for r in report.cases_in_neither_denominator}
    assert observed == KNOWN_STRADDLING, (
        f"straddling set changed: added {sorted(observed - KNOWN_STRADDLING)}, "
        f"removed {sorted(KNOWN_STRADDLING - observed)}"
    )


def test_the_denominators_reconcile_to_the_case_count(report: SuiteReport) -> None:
    """FR-8.1's discipline -- percentages sum, every bucket enumerable -- applied to the gate's
    own report.

    This is the whole of finding 18. The two supporting rates quote denominators of 348 and 265
    next to a case count of 624, and nothing said where the other 11 went. A reader is entitled
    to assume the worst about a number that does not add up, and they would have been wrong,
    which is the most annoying kind of doubt to leave lying around.
    """
    assert (
        report.fp_on_clean.total
        + report.fn_on_defects.total
        + len(report.cases_in_neither_denominator)
        == report.total
    )


def test_every_straddling_case_is_dual_labelled(report: SuiteReport) -> None:
    """A single-labelled case cannot straddle: one label is either a defect reading or it is not.
    If this ever fails, `reviewer_says_defect` / `reviewer_says_no_defect` have drifted apart and
    a whole class of case is silently uncounted."""
    for r in report.cases_in_neither_denominator:
        assert r.case.is_dual_labelled, (
            f"{r.case.id} is single-labelled yet sits in neither denominator -- the two "
            f"predicates no longer partition the label space"
        )


def test_the_caveat_names_the_straddling_count(report: SuiteReport) -> None:
    """The number has to reach the reader, not just the test suite."""
    joined = " ".join(report.caveats)
    assert "NEITHER supporting denominator" in joined
    assert str(len(report.cases_in_neither_denominator)) in joined
