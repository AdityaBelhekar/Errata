"""NFR-5 -- the commercial argument, with a price attached.

    "Per-run cost by tier, per page and per record. Run report includes measured cost;
    ExtractBench's 8.1c/page is the T1 reference point."

R2 already proved the property that matters -- T2 and T3 volume is bounded by the error count, not
the row count -- and proved it in **work units**. "67 counter-evidence searches over 10,001
records" is the right shape, and a buyer cannot put it next to 8.1 cents. There was no currency and
no seconds anywhere in the repository.

What these tests hold:

* seconds are **measured** and money is **modelled**, and the report never lets a reader forget
  which is which;
* a rate with no source cannot be used to multiply anything;
* T3 is priced at zero **and says so**, because pricing a queue row needs reviewer-seconds and
  FR-9.3 reports NOT MEASURED;
* the per-page figure is never presented without the denominator that makes it honest.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from errata_scale.costing import (
    DEFAULT_RATE_CARD,
    PricedCost,
    Rate,
    Timer,
    load_rate_card,
    price_run,
)
from errata_scale.tiers import CostReport, Tier, TierCost

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cost_report(*, records: int, errors: int, groundable: int) -> CostReport:
    return CostReport(
        records=records,
        error_count=errors,
        groundable=groundable,
        tiers=(
            TierCost(Tier.T0_STRUCTURAL, records, records * 5, "cell checks"),
            TierCost(Tier.T1_GROUNDED, groundable, groundable * 5, "re-derivations"),
            TierCost(Tier.T2_DEEP, errors, errors, "counter-evidence searches"),
            TierCost(Tier.T3_HUMAN, errors, errors, "queue rows offered"),
        ),
    )


@pytest.fixture
def timer() -> Timer:
    clock = Timer()
    for tier in (Tier.T0_STRUCTURAL, Tier.T1_GROUNDED, Tier.T2_DEEP):
        with clock.measure(tier):
            pass
    return clock


# ------------------------------------------------------------------------------------------------
# The rate card
# ------------------------------------------------------------------------------------------------


def test_the_shipped_rate_card_loads_and_every_rate_names_its_source() -> None:
    card = load_rate_card()
    assert card.rates, "the rate card is empty"
    for rate in card.rates.values():
        assert rate.source and rate.read_on, f"{rate.key} has no provenance"


def test_a_rate_without_a_source_cannot_be_constructed() -> None:
    """A price nobody can check is a number this module will not multiply anything by."""
    with pytest.raises(ValueError, match="no source or no date"):
        Rate(key="invented", cents=1.0, per="second", source="", read_on="")


def test_an_unknown_rate_raises_rather_than_defaulting_to_zero() -> None:
    """A tier priced at nothing is a tier that looks free."""
    card = load_rate_card()
    with pytest.raises(KeyError, match=r"[Aa]dd it with a source"):
        card.rate("gpu_second")


def test_the_reference_point_matches_the_benchmarks_copy_of_it() -> None:
    """Two copies of one number, pinned equal so they cannot drift.

    ``errata_scale`` must not import ``errata_bench`` -- the product importing its own scorer is
    exactly what ``audit/tests/test_boundaries.py`` forbids -- so the ExtractBench reference figure
    is duplicated into the rate card. The duplication is the lesser problem; an undetected
    divergence between the cost report's reference point and the benchmark's would be the greater
    one, and this test is the price of the boundary.
    """
    from errata_bench.operating_point import EXTRACTBENCH_COST_CENTS_PER_PAGE

    assert load_rate_card().reference_cents_per_page == EXTRACTBENCH_COST_CENTS_PER_PAGE


def test_the_rate_card_is_valid_yaml_with_the_keys_the_loader_needs() -> None:
    document = yaml.safe_load(DEFAULT_RATE_CARD.read_text("utf-8"))
    assert {"rate_card_id", "currency", "rates", "caveats"} <= set(document)


# ------------------------------------------------------------------------------------------------
# Pricing
# ------------------------------------------------------------------------------------------------


def test_a_priced_run_reports_per_record_per_page_and_per_error(timer: Timer) -> None:
    priced = price_run(
        _cost_report(records=10_001, errors=67, groundable=277),
        timer,
        pages_processed=25,
        machine="test",
    )
    assert priced.records == 10_001
    assert priced.pages_processed == 25
    assert priced.cents_per_record >= 0.0
    assert priced.cents_per_page >= 0.0
    assert priced.cents_per_error >= 0.0
    assert priced.total_seconds > 0.0, "no seconds were measured at all"


def test_t3_is_not_priced_and_the_report_says_why(timer: Timer) -> None:
    """The honest price of a queue row is reviewer-seconds, and nobody has ever been timed.

    Zero here is not "free". It is "not measured", which is a different claim, and the basis
    string has to carry it -- a zero in a cost table with no explanation reads as free labour.
    """
    priced = price_run(
        _cost_report(records=100, errors=10, groundable=10),
        timer,
        pages_processed=3,
        machine="test",
    )
    t3 = next(t for t in priced.tiers if t.tier is Tier.T3_HUMAN)
    assert t3.cents == 0.0
    assert "NOT PRICED" in t3.basis
    assert "FR-9.3" in t3.basis


def test_a_run_with_no_groundable_records_has_no_per_page_cost(timer: Timer) -> None:
    """Zero pages is a fact about the catalog, not a value to interpolate."""
    priced = price_run(
        _cost_report(records=500, errors=4, groundable=0),
        timer,
        pages_processed=0,
        machine="test",
    )
    assert priced.cents_per_page == 0.0


# ------------------------------------------------------------------------------------------------
# The comparison, and the ways it could mislead
# ------------------------------------------------------------------------------------------------


def test_the_comparison_carries_both_denominators(timer: Timer) -> None:
    """Per page and per catalog record, labelled, because only one of them is like-for-like.

    Errata opens a document for the groundable fraction only. A per-page figure quoted alone
    compares our 2.77% against extraction's 100% without saying so.
    """
    priced = price_run(
        _cost_report(records=10_001, errors=67, groundable=277),
        timer,
        pages_processed=25,
        machine="test",
    )
    comparison = priced.versus_extractbench()

    assert comparison["reference_cents_per_page"] == 8.1
    assert "errata_cents_per_page_processed" in comparison
    assert "errata_cents_per_catalog_record" in comparison
    assert comparison["pages_processed"] == 25
    assert comparison["catalog_records"] == 10_001
    assert "NOT the customer's bill" in comparison["note"]


def test_every_priced_report_states_that_the_money_is_modelled(timer: Timer) -> None:
    """The single most quotable fabricated number in this repository would be a price with no
    invoice behind it. So every report carries the fact that there is no invoice."""
    priced = price_run(
        _cost_report(records=10, errors=1, groundable=1),
        timer,
        pages_processed=1,
        machine="a-named-machine",
    )
    caveats = " ".join(priced.caveats())
    assert "MODELLED, NOT BILLED" in caveats
    assert "a-named-machine" in caveats, "the machine the seconds came from is not recorded"
    assert "NOT AN 8,000x SAVING" in caveats, (
        "the report no longer warns that the per-page gap is a consequence of calling no model "
        "rather than of being efficient at the same job. That warning is the difference between "
        "a cost measurement and a misleading sales figure."
    )


def test_the_shape_of_the_curve_survives_the_rates_being_wrong(timer: Timer) -> None:
    """FR-8.7's claim is about the shape, and the shape is what the rate card cannot break.

    Ten times the catalog at the same error count must not move T2 or T3 volume. Priced or
    unpriced, that is the commercial argument, and this is the assertion that says the money
    layer did not quietly become the thing being claimed.
    """
    small = _cost_report(records=1_000, errors=67, groundable=277)
    large = _cost_report(records=10_000, errors=67, groundable=277)

    assert small.of(Tier.T2_DEEP).work_units == large.of(Tier.T2_DEEP).work_units
    assert small.of(Tier.T3_HUMAN).work_units == large.of(Tier.T3_HUMAN).work_units
    assert large.of(Tier.T0_STRUCTURAL).work_units > small.of(Tier.T0_STRUCTURAL).work_units


# ------------------------------------------------------------------------------------------------
# The timer
# ------------------------------------------------------------------------------------------------


def test_the_timer_accumulates_across_calls() -> None:
    clock = Timer()
    for _ in range(3):
        with clock.measure(Tier.T1_GROUNDED):
            pass
    entry = clock.timings[Tier.T1_GROUNDED]
    assert entry.calls == 3
    assert entry.seconds >= 0.0
    assert entry.seconds_per_call == pytest.approx(entry.seconds / 3)


def test_the_timer_records_time_even_when_the_body_raises() -> None:
    """A tier that blew up still consumed the seconds it consumed."""
    clock = Timer()
    with pytest.raises(RuntimeError), clock.measure(Tier.T2_DEEP):
        raise RuntimeError("boom")
    assert clock.timings[Tier.T2_DEEP].calls == 1


def test_priced_cost_serialises_with_its_caveats(timer: Timer) -> None:
    priced: PricedCost = price_run(
        _cost_report(records=10, errors=1, groundable=1),
        timer,
        pages_processed=1,
        machine="test",
    )
    payload = priced.as_dict()
    assert payload["measured"] is False, (
        "as_dict() claims the money was measured. It is modelled from a rate card and the flag is "
        "how a downstream consumer knows that without reading the caveats."
    )
    assert payload["caveats"]
