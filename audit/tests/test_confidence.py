"""FR-6.1 / FR-6.3 -- calibration, and the refusals that keep it meaningful.

    "``calibrated_p = 0.9`` means approximately 9-in-10 on held-out data."

Everything here exists to stop a number being printed that does not mean that. The two most
important tests are refusals: a calibration set with one outcome cannot be fitted, and a score
outside the set's support does not get a probability. Both have an obvious, tempting wrong
implementation -- return 1.0, extrapolate the sigmoid -- and both produce a confident number about
a region nobody measured.
"""

from __future__ import annotations

import math

import pytest

from errata_audit.confidence import (
    aurc,
    calibrate,
    fit_platt,
    load_calibration,
    reliability_diagram,
    risk_coverage_curve,
)
from errata_spec import DeclinedReason

SEPARABLE = [(0.9, True), (0.85, True), (0.8, True), (0.3, False), (0.2, False), (0.1, False)]


def test_a_fitted_model_is_monotone_in_the_score() -> None:
    model = fit_platt(SEPARABLE, calibration_set_id="t")
    probabilities = [model.probability(s) for s in (0.1, 0.3, 0.5, 0.7, 0.9)]
    assert probabilities == sorted(probabilities)


def test_the_fit_is_deterministic() -> None:
    """No randomness anywhere: two runs on the same labels give the same model, or an audit's
    reported probability changes between runs of identical data."""
    first = fit_platt(SEPARABLE, calibration_set_id="t")
    second = fit_platt(SEPARABLE, calibration_set_id="t")
    assert (first.a, first.b) == (second.a, second.b)


def test_a_single_outcome_set_is_refused() -> None:
    """Every fitted probability would be 1.0 regardless of the score. Returning a model here is how
    a system ends up reporting 99% confidence on a population it has never been wrong about because
    it has never been tested."""
    with pytest.raises(ValueError, match="only one outcome"):
        fit_platt([(0.9, True), (0.8, True)], calibration_set_id="t")


def test_a_set_of_one_is_refused() -> None:
    with pytest.raises(ValueError, match="fewer than two"):
        fit_platt([(0.9, True)], calibration_set_id="t")


def test_a_calibrated_confidence_names_its_method_and_its_set() -> None:
    """``errata_spec.Confidence`` refuses a probability with no provenance, so a number nobody can
    trace cannot be stored in the first place."""
    model = fit_platt(SEPARABLE, calibration_set_id="ledger-2026-08")
    confidence = calibrate(0.85, model)
    assert confidence.calibrated_p is not None
    assert confidence.method == "platt"
    assert confidence.calibration_set_id == "ledger-2026-08"


def test_a_score_outside_the_support_declines_instead(  # FR-6.2
) -> None:
    model = fit_platt(SEPARABLE, calibration_set_id="t")
    confidence = calibrate(0.999, model)
    assert confidence.calibrated_p is None
    assert confidence.abstained
    assert confidence.abstain_reason is DeclinedReason.CALIBRATION_OUT_OF_DISTRIBUTION


def test_no_model_means_a_raw_score_and_no_probability() -> None:
    confidence = calibrate(0.74, None)
    assert confidence.raw_score == 0.74
    assert confidence.calibrated_p is None


def test_no_calibration_set_ships_with_the_package() -> None:
    """R1 reports raw scores because calibration needs reviewer decisions and none have been made.
    Shipping a fitted set built from the constructed demo population would be a number with the
    authority of a measurement and the content of an assumption."""
    assert load_calibration() is None


def test_the_reliability_diagram_omits_empty_bins() -> None:
    """A bin nobody landed in says nothing about calibration, and drawing it at zero observed makes
    a model look over-confident where it is merely untested."""
    bins = reliability_diagram([(0.05, False), (0.95, True)], bins=5)
    assert {(b.lower, b.upper) for b in bins} == {(0.0, 0.2), (0.8, 1.0)}


def test_expected_calibration_error_is_reported_next_to_the_diagram() -> None:
    model = fit_platt(SEPARABLE, calibration_set_id="t")
    assert 0.0 <= model.expected_calibration_error <= 1.0
    assert model.bins


# ------------------------------------------------------------------------------------------------
# FR-6.3 -- risk against coverage
# ------------------------------------------------------------------------------------------------


def test_a_perfect_ranking_has_zero_risk_until_the_errors_appear() -> None:
    curve = risk_coverage_curve([(0.9, True), (0.8, True), (0.2, False), (0.1, False)])
    assert curve[0].risk == 0.0
    assert curve[1].risk == 0.0
    assert curve[-1].risk == 0.5


def test_coverage_reaches_one_and_counts_every_record() -> None:
    curve = risk_coverage_curve([(0.5, True), (0.4, False), (0.3, True)])
    assert math.isclose(curve[-1].coverage, 1.0)
    assert curve[-1].n == 3


def test_ties_are_broken_deterministically() -> None:
    """Random tie-breaking would make an audit report a different AURC on every run of identical
    data -- the kind of small dishonesty that costs trust in the whole report."""
    scored = [(0.5, True), (0.5, False), (0.5, True)]
    assert risk_coverage_curve(scored) == risk_coverage_curve(scored)


def test_aurc_is_lower_for_a_better_ranking() -> None:
    good = aurc(risk_coverage_curve([(0.9, True), (0.8, True), (0.2, False)]))
    bad = aurc(risk_coverage_curve([(0.9, False), (0.8, True), (0.2, True)]))
    assert good < bad


def test_an_empty_curve_is_empty_rather_than_flattering() -> None:
    assert risk_coverage_curve([]) == ()
    assert aurc(()) == 0.0
