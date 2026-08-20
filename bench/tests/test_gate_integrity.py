"""Gates 2 and 3 must be unable to report a measurement they did not take.

Ground rule 5: gates 2 and 3 stay `NOT_MEASURED` on synthetic input, unconditionally. The spec's
§0.3 argument is that a project whose governing rule is "never invent numbers" gets no credit for
declining to invent one while proceeding as though it existed -- so the refusal has to be
structural, not a convention someone can route around while meaning well.

The R0 determinism/gate-integrity audit was meant to test exactly this and hit its session limit
first. `PROGRESS.md` lists it as unverified: "whether gates 2/3's synthetic pinning survives a
hostile attempt". These tests are that attempt. They do not check that the pinning is *documented*;
they try to break it.

The attacks are the ones a well-meaning engineer would actually reach for under deadline -- make
the synthetic data look better, relabel it, resize it, cast it -- not exotic ones. A guard that
only stops malice is not much of a guard, because nobody here is malicious.
"""

from __future__ import annotations

import pytest

from errata_bench.coverage import CoverageGate, coverage_report, synthetic_distribution
from errata_bench.operating_point import (
    AsymmetryVerdict,
    MCBCorpus,
    Provenance,
    operating_point_report,
    render_report,
    synthetic_corpus,
)

# ---------------------------------------------------------------------------------------------
# Gate 2 -- operating point
# ---------------------------------------------------------------------------------------------


def test_synthetic_corpus_is_not_measured_at_the_default_size() -> None:
    verdict = operating_point_report(synthetic_corpus()).verdict
    assert verdict is AsymmetryVerdict.NOT_MEASURED


@pytest.mark.parametrize("n", [1, 12, 40, 200, 1000, 5000])
def test_no_corpus_size_buys_a_verdict(n: int) -> None:
    """Attack 1: make the synthetic corpus big enough to clear the sample-size floor.

    This is the most natural mistake available -- every other gate in the harness gets more
    trustworthy with more records, so it is reasonable to assume this one does too. It must not.
    Sample size is a precondition for a measurement, never a substitute for having taken one.
    """
    report = operating_point_report(synthetic_corpus(n=n))
    assert report.verdict is AsymmetryVerdict.NOT_MEASURED, (
        f"a synthetic corpus of {n} records produced {report.verdict}"
    )


def test_relabelling_the_corpus_name_buys_nothing() -> None:
    """Attack 2: call it something authoritative.

    The provenance is a field, not a naming convention, so a corpus named after a real
    manufacturer series is still synthetic.
    """
    corpus = synthetic_corpus(n=200, name="schneider-acti9-ic60-2026")
    assert corpus.is_synthetic
    assert operating_point_report(corpus).verdict is AsymmetryVerdict.NOT_MEASURED


def test_provenance_cannot_be_laundered_by_rebuilding_the_corpus() -> None:
    """Attack 3: keep the synthetic records, declare them empirical.

    This one SUCCEEDS in flipping the verdict, and that is the designed behaviour rather than a
    hole: an operator who writes `provenance: empirical` over generated data has falsified a
    record, which is a conduct problem and not something the type system can prevent.

    What the harness owes is that the lie must be explicit and attributable -- a field somebody
    set, not a default they drifted into. This test pins that the flip requires an affirmative
    act, so the day someone does it, the diff shows who and when.
    """
    synthetic = synthetic_corpus(n=200)
    laundered = MCBCorpus(
        records=synthetic.records,
        name=synthetic.name,
        provenance=Provenance.EMPIRICAL,
        source="hand-edited",
    )
    assert not laundered.is_synthetic
    assert operating_point_report(laundered).verdict is not AsymmetryVerdict.NOT_MEASURED, (
        "if this now returns NOT_MEASURED the pinning has become stricter than documented -- "
        "good, but update ground rule 5 and this test to say so"
    )


def test_an_undeclared_corpus_is_read_as_empirical_and_says_so() -> None:
    """The default direction matters, and it is the risky one.

    A file with no `provenance:` key is treated as empirical -- because an operator pointed the
    harness at it deliberately -- which means the safe default was NOT chosen. That is defensible
    only if the harness says out loud what it assumed, so this pins the note rather than the
    default.
    """
    from errata_bench.operating_point import _resolve_provenance

    resolved, notes = _resolve_provenance(None, None)
    assert resolved is Provenance.EMPIRICAL
    assert notes, "an undeclared provenance must produce a caveat, not silence"
    assert "did not declare a provenance" in " ".join(notes)


def test_the_synthetic_flag_survives_a_round_trip_through_the_report() -> None:
    """Attack 4: read the number out of the report and quote it without the verdict.

    The report must carry its own provenance, so a downstream consumer holding only the report
    can still tell that the metrics inside it are not a measurement.
    """
    rendered = render_report(operating_point_report(synthetic_corpus(n=100)))
    assert "NOT MEASURED" in rendered.upper().replace("_", " "), (
        "a reader holding only the rendered report must be able to see it is not a measurement"
    )


# ---------------------------------------------------------------------------------------------
# Gate 3 -- calibration coverage
# ---------------------------------------------------------------------------------------------


def test_synthetic_distribution_is_not_measured() -> None:
    assert coverage_report(synthetic_distribution()).gate is CoverageGate.NOT_MEASURED


@pytest.mark.parametrize("classes", [50, 500, 5600])
def test_no_class_count_buys_a_coverage_verdict(classes: int) -> None:
    """The gate-3 twin of the size attack. A bigger synthetic taxonomy is still synthetic."""
    report = coverage_report(synthetic_distribution(classes=classes))
    assert report.gate is CoverageGate.NOT_MEASURED, (
        f"a synthetic distribution of {classes} classes produced {report.gate}"
    )


def test_both_gates_refuse_by_provenance_not_by_numbers() -> None:
    """The structural claim, stated as a test.

    If either gate ever refuses because the *numbers* looked bad rather than because the *input*
    was synthetic, then a synthetic corpus that happened to look good would slip through. The
    refusal has to key off provenance alone.
    """
    lean = operating_point_report(synthetic_corpus(n=40))
    fat = operating_point_report(synthetic_corpus(n=2000))
    assert lean.verdict is fat.verdict is AsymmetryVerdict.NOT_MEASURED, (
        "the two corpora differ only in size; if their verdicts differ, the refusal is keying "
        "off something other than provenance"
    )
