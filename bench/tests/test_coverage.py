"""Tests for R0 kill test 3 -- the calibration-coverage arithmetic (FR-0.4).

bench/src/errata_bench/coverage.py shipped with zero tests despite being 1,300+ lines and the
module the §13 kill-condition table points at. This file exercises the promises the module makes
about itself:

  * the label floor is derived correctly for known alpha/tolerance/confidence combinations, and
    moves the right way (never down) as the target tightens;
  * synthetic_distribution() is genuinely deterministic -- no seed parameter, no RNG -- which is
    what NFR-1 (byte-identical reruns) and NFR-8 (no RNG in this layer) require, checked rather
    than trusted;
  * GREEDY's dominance over PROPORTIONAL and EQUAL on SKU coverage is the module's single
    load-bearing claim and is asserted directly, budget by budget;
  * coverage is monotone non-decreasing in budget;
  * hierarchical pooling measurably converts some previously-unreachable classes into cleared ones;
  * the NOT_MEASURED gate on synthetic input is unconditional -- true even when the synthetic
    numbers look excellent -- because that is the only thing standing between an honest kill test
    and a project that quietly starts trusting made-up numbers; and
  * a file-backed (non-synthetic) distribution can genuinely reach RESCOPE/NARROW/PASS, so the gate
    is provenance-driven rather than hardcoded to never let a verdict through.

It also regression-guards the two bugs found and fixed in this pass: DEFAULT_HEADLINE_BUDGET
(50,000) did not reproduce the module's own headline finding on its own default synthetic
distribution (it gave 38.05% class coverage, not "the single digits"), and the LabelFloor
docstring's illustrative number ("near 60 labels per class") did not match what label_floor()
actually computes for the same parameters (15).
"""

from __future__ import annotations

import inspect
import math
from pathlib import Path

import pytest

from errata_bench import coverage as cov

FIXTURES = Path(__file__).parent / "fixtures"


# ================================================================================================
# label_floor
# ================================================================================================


def test_feasibility_floor_matches_the_closed_form() -> None:
    """n >= ceil(1/alpha - 1); alpha=0.1 -> 9, the exact number the module's own docstring uses."""
    floor = cov.label_floor(alpha=0.1, tolerance=0.0, confidence=0.9)
    assert floor.feasibility_floor == 9


@pytest.mark.parametrize(
    ("alpha", "expected_feasibility"),
    [(0.1, 9), (0.2, 4), (0.05, 19), (0.5, 1)],
)
def test_feasibility_floor_for_known_alphas(alpha: float, expected_feasibility: int) -> None:
    floor = cov.label_floor(alpha=alpha, tolerance=0.0, confidence=0.5)
    assert floor.feasibility_floor == expected_feasibility


def test_default_tolerance_floor_is_15() -> None:
    """Regression guard for the docstring-vs-arithmetic drift bug fixed in this pass: the
    LabelFloor class docstring used to claim "near 60 labels per class" at these exact parameters.
    The derivation was always correct -- this is what it actually produces, verified independently
    against the closed-form Beta(a, 1) CDF (x**a) during the investigation -- only the illustrative
    prose number in the docstring was stale. It now cites 15."""
    floor = cov.label_floor(alpha=0.1, tolerance=0.05, confidence=0.9, cells_per_class=1)
    assert floor.tolerance_floor == 15
    assert floor.skus_per_class == 15
    assert floor.labels_per_class == 15


def test_zero_tolerance_falls_back_to_feasibility_floor() -> None:
    floor = cov.label_floor(alpha=0.1, tolerance=0.0, confidence=0.9)
    assert floor.tolerance_floor == floor.feasibility_floor


def test_cells_per_class_multiplies_labels_but_not_the_sku_floor() -> None:
    one = cov.label_floor(cells_per_class=1)
    four = cov.label_floor(cells_per_class=4)
    assert four.labels_per_class == one.labels_per_class * 4
    assert four.skus_per_class == one.skus_per_class


def test_tighter_tolerance_never_decreases_the_floor() -> None:
    for alpha in (0.05, 0.1, 0.2):
        prev = None
        for tolerance in (0.30, 0.20, 0.10, 0.08, 0.05, 0.03, 0.02, 0.01):
            if tolerance >= 1 - alpha:
                continue
            floor = cov.label_floor(alpha=alpha, tolerance=tolerance, confidence=0.9)
            if prev is not None:
                assert floor.skus_per_class >= prev, (alpha, tolerance)
            prev = floor.skus_per_class


def test_higher_confidence_never_decreases_the_floor() -> None:
    for alpha in (0.05, 0.1, 0.2):
        prev = None
        for confidence in (0.5, 0.7, 0.8, 0.9, 0.95, 0.97, 0.99):
            floor = cov.label_floor(alpha=alpha, tolerance=0.05, confidence=confidence)
            if prev is not None:
                assert floor.skus_per_class >= prev, (alpha, confidence)
            prev = floor.skus_per_class


def test_label_floor_rejects_degenerate_alpha() -> None:
    with pytest.raises(ValueError):
        cov.label_floor(alpha=0.0)
    with pytest.raises(ValueError):
        cov.label_floor(alpha=1.0)


def test_label_floor_rejects_bad_cells_per_class() -> None:
    with pytest.raises(ValueError):
        cov.label_floor(cells_per_class=0)


# ================================================================================================
# synthetic_distribution
# ================================================================================================


def test_synthetic_distribution_has_no_seed_parameter() -> None:
    """NFR-8: no RNG anywhere in this module. If this ever grows a `seed` kwarg, the determinism
    tests below stop being sufficient on their own to prove NFR-8 -- fail loudly here so whoever
    adds one notices the obligation."""
    params = inspect.signature(cov.synthetic_distribution).parameters
    assert "seed" not in params


def test_synthetic_distribution_is_deterministic() -> None:
    """Same params, same bytes out (NFR-1): two independent calls, not two references to one
    object, must compare equal field-for-field."""
    first = cov.synthetic_distribution()
    second = cov.synthetic_distribution()
    assert first is not second
    assert first == second
    assert first.entries == second.entries


def test_synthetic_distribution_is_deterministic_for_nondefault_params() -> None:
    a = cov.synthetic_distribution(classes=37, skus=10_000, zipf_exponent=1.4, groups=5)
    b = cov.synthetic_distribution(classes=37, skus=10_000, zipf_exponent=1.4, groups=5)
    assert a == b


def test_synthetic_distribution_totals_are_exact() -> None:
    """Largest-remainder allocation must hit the requested totals exactly, not approximately."""
    dist = cov.synthetic_distribution(classes=137, skus=50_000)
    assert dist.class_count == 137
    assert dist.sku_total == 50_000


def test_synthetic_distribution_is_marked_synthetic() -> None:
    dist = cov.synthetic_distribution()
    assert dist.provenance is cov.Provenance.SYNTHETIC
    assert dist.is_synthetic


def test_synthetic_distribution_rejects_impossible_params() -> None:
    with pytest.raises(ValueError):
        cov.synthetic_distribution(classes=0)
    with pytest.raises(ValueError):
        cov.synthetic_distribution(classes=100, skus=10)  # fewer SKUs than classes


# ================================================================================================
# allocate
# ================================================================================================


def _assess_all_strategies(
    dist: cov.ClassDistribution,
    budget: int,
    floor: cov.LabelFloor,
    pooling: cov.PoolingModel = cov.PoolingModel(),
) -> dict[cov.Strategy, cov.CoveragePoint]:
    return {
        strategy: cov.assess(dist, cov.allocate(dist, budget, floor, strategy, pooling))
        for strategy in cov.Strategy
    }


def test_strategies_allocate_differently() -> None:
    dist = cov.synthetic_distribution()
    floor = cov.label_floor()
    points = _assess_all_strategies(dist, 25_000, floor)
    coverages = {s: p.class_coverage for s, p in points.items()}
    assert len(set(coverages.values())) > 1, coverages


@pytest.mark.parametrize(
    "budget", [0, 1_000, 5_000, 25_000, 50_000, 100_000, 400_000, 10_000_000]
)
def test_greedy_never_underperforms_proportional_or_equal_on_sku_coverage(budget: int) -> None:
    """The load-bearing claim: greedy-by-SKU-count provably dominates PROPORTIONAL and EQUAL on
    SKU coverage for the same budget. If this regresses, the module's headline finding is false."""
    dist = cov.synthetic_distribution()
    floor = cov.label_floor()
    points = _assess_all_strategies(dist, budget, floor)
    greedy_sku = points[cov.Strategy.GREEDY].sku_coverage
    assert greedy_sku >= points[cov.Strategy.PROPORTIONAL].sku_coverage - 1e-12
    assert greedy_sku >= points[cov.Strategy.EQUAL].sku_coverage - 1e-12


def test_budget_zero_allocates_nothing_and_does_not_error() -> None:
    dist = cov.synthetic_distribution()
    floor = cov.label_floor()
    for strategy in cov.Strategy:
        point = cov.assess(dist, cov.allocate(dist, 0, floor, strategy))
        assert point.classes_cleared == 0
        assert point.labels_spent == 0


def test_budget_far_larger_than_total_need_clears_every_reachable_class_without_error() -> None:
    dist = cov.synthetic_distribution()
    floor = cov.label_floor()
    huge = dist.sku_total * floor.labels_per_class  # verified empirically to saturate all 3
    for strategy in cov.Strategy:
        point = cov.assess(dist, cov.allocate(dist, huge, floor, strategy))
        assert point.classes_cleared + point.classes_unreachable == point.classes_total, strategy


def test_negative_budget_is_rejected() -> None:
    dist = cov.synthetic_distribution()
    floor = cov.label_floor()
    with pytest.raises(ValueError):
        cov.allocate(dist, -1, floor)


@pytest.mark.parametrize("budget", [0, 5_000, 50_000, 250_000])
@pytest.mark.parametrize("strategy", list(cov.Strategy))
def test_class_accounting_never_overruns_the_total(
    budget: int, strategy: cov.Strategy
) -> None:
    """classes_cleared and classes_unreachable are mutually exclusive -- a class cannot be both
    funded to its floor and structurally incapable of ever reaching it (funding is always capped
    at capacity, and capacity < floor is exactly what "unreachable" means) -- so their sum can
    never exceed classes_total. classes_pooled_cleared is a *subset* of classes_cleared (pooled
    AND cleared), not an independent bucket, so it must never exceed classes_cleared either."""
    dist = cov.synthetic_distribution()
    floor = cov.label_floor()
    point = cov.assess(dist, cov.allocate(dist, budget, floor, strategy))
    assert point.classes_cleared + point.classes_unreachable <= point.classes_total
    assert 0 <= point.classes_pooled_cleared <= point.classes_cleared
    assert point.classes_cleared <= point.classes_total
    assert point.classes_unreachable <= point.classes_total


# ================================================================================================
# sweep
# ================================================================================================


@pytest.mark.parametrize("strategy", list(cov.Strategy))
def test_coverage_is_monotone_nondecreasing_in_budget(strategy: cov.Strategy) -> None:
    dist = cov.synthetic_distribution()
    floor = cov.label_floor()
    points = cov.sweep(dist, cov.DEFAULT_BUDGETS, floor, strategies=(strategy,))
    ordered = sorted(points, key=lambda p: p.budget)
    class_series = [p.class_coverage for p in ordered]
    sku_series = [p.sku_coverage for p in ordered]
    assert class_series == sorted(class_series)
    assert sku_series == sorted(sku_series)


def test_sweep_deduplicates_and_sorts_budgets() -> None:
    dist = cov.synthetic_distribution(classes=20, skus=2_000)
    floor = cov.label_floor()
    points = cov.sweep(dist, [500, 100, 500, 100], floor, strategies=(cov.Strategy.GREEDY,))
    assert [p.budget for p in points] == [100, 500]


# ================================================================================================
# pooling
# ================================================================================================


def test_pooling_measurably_increases_classes_pooled_cleared() -> None:
    """Confirmed manually during investigation: at budget=50,000 with GREEDY on the default
    synthetic distribution, pooling converts 1,506 previously-unreachable classes into cleared
    ones (2,131 -> 3,637) by discounting their floor once their parent group has enough
    accumulated funding. Written here as a real assertion rather than a spot-check."""
    dist = cov.synthetic_distribution()
    floor = cov.label_floor()
    budget = 50_000
    off = cov.assess(
        dist, cov.allocate(dist, budget, floor, cov.Strategy.GREEDY, cov.PoolingModel(enabled=False))
    )
    on = cov.assess(
        dist, cov.allocate(dist, budget, floor, cov.Strategy.GREEDY, cov.PoolingModel(enabled=True))
    )
    assert off.classes_pooled_cleared == 0
    assert on.classes_pooled_cleared > off.classes_pooled_cleared
    assert on.classes_cleared > off.classes_cleared


# ================================================================================================
# coverage_report -- the gate
# ================================================================================================


def test_gate_is_not_measured_for_synthetic_input_regardless_of_how_good_the_numbers_look() -> None:
    """The single most important test in this file. Build a tiny, easy-to-clear synthetic
    distribution where class coverage lands above 90% -- a PASS by any numeric reading -- and
    confirm the gate still reports NOT_MEASURED. Provenance decides the gate, never the numbers."""
    easy = cov.synthetic_distribution(classes=5, skus=100_000, zipf_exponent=0.1, groups=1)
    report = cov.coverage_report(easy, headline_budget=250_000)
    assert report.best_class_coverage > 0.9  # the numbers really do look good
    assert report.gate is cov.CoverageGate.NOT_MEASURED


def test_gate_is_not_measured_on_the_module_default_report() -> None:
    report = cov.coverage_report()
    assert report.distribution.provenance is cov.Provenance.SYNTHETIC
    assert report.gate is cov.CoverageGate.NOT_MEASURED


def test_default_headline_budget_reproduces_the_stated_finding() -> None:
    """Regression guard for the headline-budget bug fixed in this pass: DEFAULT_HEADLINE_BUDGET
    must actually reproduce the module's own headline claim (module docstring, Strategy.GREEDY
    docstring) -- "greedy dominates on SKU coverage and still lands in the single digits on class
    coverage" -- against the module's own default synthetic distribution. Before the fix, 50,000
    gave 38.05% class coverage (NARROW territory), not single digits."""
    dist = cov.synthetic_distribution()
    floor = cov.label_floor()
    point = cov.assess(
        dist, cov.allocate(dist, cov.DEFAULT_HEADLINE_BUDGET, floor, cov.Strategy.GREEDY)
    )
    # "single digits" is the module's own RESCOPE_BELOW definition (see CoverageReport.caveats).
    assert point.class_coverage < cov.RESCOPE_BELOW
    assert point.sku_coverage > 0.5  # "dominates ... on SKU coverage"


def test_headline_budget_is_folded_into_the_swept_budgets() -> None:
    report = cov.coverage_report(headline_budget=12_345, budgets=(1, 2, 3))
    assert 12_345 in report.budgets
    assert report.headline() != ()


def test_render_report_contains_synthetic_banner_when_synthetic() -> None:
    report = cov.coverage_report()
    text = cov.render_report(report)
    assert cov.SYNTHETIC_BANNER in text


def test_render_report_omits_synthetic_banner_when_empirical() -> None:
    dist = cov.load_distribution(FIXTURES / "sample_distribution.csv")
    report = cov.coverage_report(dist, headline_budget=1_000)
    text = cov.render_report(report)
    assert cov.SYNTHETIC_BANNER not in text
    assert "STRUCTURAL RESULT" not in text  # the banner block itself is entirely absent


def test_report_as_dict_round_trips_key_numeric_fields() -> None:
    dist = cov.synthetic_distribution()
    report = cov.coverage_report(dist)
    payload = cov.report_as_dict(report)

    assert payload["gate"] == report.gate.value
    assert payload["synthetic"] is True
    assert payload["distribution"]["classes"] == dist.class_count
    assert payload["distribution"]["skus"] == dist.sku_total
    assert payload["floor"]["labels_per_class"] == report.floor.labels_per_class
    assert payload["floor"]["skus_per_class"] == report.floor.skus_per_class
    assert payload["headline_budget"] == report.headline_budget

    by_key = {(p["budget"], p["strategy"]): p for p in payload["sweep"]}
    assert len(by_key) == len(report.points)
    for point in report.points:
        entry = by_key[(point.budget, point.strategy.value)]
        assert entry["classes_cleared"] == point.classes_cleared
        assert entry["classes_total"] == point.classes_total
        assert entry["classes_unreachable"] == point.classes_unreachable
        assert entry["labels_spent"] == point.labels_spent
        assert math.isclose(entry["class_coverage"], point.class_coverage)
        assert math.isclose(entry["sku_coverage"], point.sku_coverage)


# ================================================================================================
# load_distribution
# ================================================================================================


def test_load_csv_distribution_is_not_synthetic() -> None:
    dist = cov.load_distribution(FIXTURES / "sample_distribution.csv")
    assert dist.provenance is not cov.Provenance.SYNTHETIC
    assert dist.provenance is cov.Provenance.EMPIRICAL
    assert dist.class_count == 10
    assert dist.sku_total == 185


def test_load_yaml_distribution_is_not_synthetic() -> None:
    dist = cov.load_distribution(FIXTURES / "sample_distribution.yaml")
    assert dist.provenance is not cov.Provenance.SYNTHETIC
    assert dist.provenance is cov.Provenance.EMPIRICAL
    assert dist.name == "fixture-distributor-2026"
    assert dist.class_count == 4
    assert dist.sku_total == 86


def test_loaded_distribution_gate_can_clear_not_measured_and_reach_narrow() -> None:
    """The whole point of this test: the gate must genuinely depend on provenance, not be
    hardcoded to always report NOT_MEASURED. A file-backed distribution must be able to reach a
    real verdict -- here, NARROW, because exactly 3 of the fixture's 10 classes (30%) clear the
    label floor of 15 SKUs."""
    dist = cov.load_distribution(FIXTURES / "sample_distribution.csv")
    report = cov.coverage_report(dist, headline_budget=5_000)
    assert report.gate is not cov.CoverageGate.NOT_MEASURED
    assert report.gate is cov.CoverageGate.NARROW


def test_loaded_distribution_can_reach_pass() -> None:
    """A second file-backed fixture, engineered to clear exactly half its classes (2/4), lands in
    PASS -- confirming the gate moves across its full range for real (non-synthetic) input rather
    than being pinned to one outcome."""
    dist = cov.load_distribution(FIXTURES / "sample_distribution.yaml")
    report = cov.coverage_report(dist, headline_budget=1_000)
    assert report.gate is cov.CoverageGate.PASS


def test_load_distribution_rejects_unknown_extension(tmp_path: Path) -> None:
    bogus = tmp_path / "distribution.txt"
    bogus.write_text("class_id,sku_count\nA,10\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cov.load_distribution(bogus)


def test_load_csv_accepts_column_aliases(tmp_path: Path) -> None:
    aliased = tmp_path / "aliased.csv"
    aliased.write_text("class,skus,group\nA,20,G1\nB,3,G1\n", encoding="utf-8")
    dist = cov.load_distribution(aliased)
    assert dist.class_count == 2
    assert dist.sku_total == 23
    assert {e.class_id for e in dist.entries} == {"A", "B"}


def test_load_distribution_without_declared_provenance_notes_the_assumption() -> None:
    """An operator pointing the harness at an undeclared file is asserting it is real -- but the
    report must say out loud that the file made no claim, so nobody can launder a generated CSV
    into a verdict by omission (see load_distribution's own docstring)."""
    dist = cov.load_distribution(FIXTURES / "sample_distribution.csv")
    assert any("did not declare a provenance" in note for note in dist.notes)
