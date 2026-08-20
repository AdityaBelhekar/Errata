"""NFR-5 -- cost in money and seconds, not work units.

    "Per-run cost by tier, per page and per record. Run report includes measured cost;
    ExtractBench's 8.1c/page is the T1 reference point."

R2 counts operations per tier and proves the property that matters -- T2 and T3 volume is bounded
by the error count, not the row count. That is the commercial argument, and until now it had **no
currency and no seconds anywhere**. "67 counter-evidence searches over 10,001 records" is the right
shape and it cannot be compared to 8.1c/page, which is what a buyer will actually put it next to.

**Two kinds of number live here and they are never mixed.**

*Measured.* Wall-clock seconds per tier, taken during the run. Real, reproducible on the machine
that produced them, and carrying the machine's own description because a second on a laptop is not
a second on a build agent.

*Modelled.* Money. We have no cloud bill: this repository has never run in production, and a price
per record derived from nothing would be the single most quotable fabricated number in it. So money
is computed from a **rate card** -- a file of published third-party prices, each with its source
and the date it was read -- multiplied by measured seconds and measured counts. Every priced figure
carries the rate card's id, and :meth:`PricedCost.caveats` states in the report itself that these
are list prices for a workload nobody has run at scale.

**Why that is still worth doing rather than saying "unknown".** The claim under test is not "Errata
costs X". It is *"cost tracks errors, not rows"* -- a statement about the SHAPE of the curve, and
the shape survives being wrong about the absolute rates. Double every rate and T2 still does not
grow with catalog size. So the honest deliverable is a price with its assumptions attached and a
sensitivity the reader can apply themselves, which is what :meth:`per_page` and
:meth:`versus_extractbench` are for.

**The comparison that actually matters.** ExtractBench's 8.1c/page is the cost of extracting from
*every page*. Errata's T1 is the only tier that opens a document at all, and it runs on the
groundable fraction -- 2.77% of the R2 demonstration catalog. A per-page comparison that ignored
that would flatter us enormously, so :meth:`versus_extractbench` reports both: cost per page
*processed* (the like-for-like number) and cost per catalog record (the number a buyer signs), and
says which is which.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .tiers import CostReport, Tier

__all__ = [
    "DEFAULT_RATE_CARD",
    "PricedCost",
    "RateCard",
    "TierTiming",
    "Timer",
    "load_rate_card",
    "price_run",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RATE_CARD = REPO_ROOT / "data" / "costing" / "rate-card.yaml"


# ------------------------------------------------------------------------------------------------
# Measured: seconds
# ------------------------------------------------------------------------------------------------


@dataclass
class TierTiming:
    """Wall-clock seconds spent in one tier, accumulated across every record that entered it."""

    tier: Tier
    seconds: float = 0.0
    calls: int = 0

    @property
    def seconds_per_call(self) -> float:
        return self.seconds / self.calls if self.calls else 0.0


@dataclass
class Timer:
    """Accumulates wall-clock time per tier during a run.

    ``perf_counter`` rather than ``process_time``: the question a buyer asks is how long the job
    takes, and a pipeline that spends its life waiting on a disk read has really spent that time.
    Process time would flatter every I/O-bound tier, which is all of them that open a document.

    Timings are **excluded from the determinism payload** -- ``NFR-1`` compares claims, and a
    duration is not a claim. Keeping them on this object rather than inside a claim is what makes
    that separation structural instead of a filter.
    """

    timings: dict[Tier, TierTiming] = field(default_factory=dict)

    @contextmanager
    def measure(self, tier: Tier) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - started
            entry = self.timings.setdefault(tier, TierTiming(tier=tier))
            entry.seconds += elapsed
            entry.calls += 1

    def seconds(self, tier: Tier) -> float:
        entry = self.timings.get(tier)
        return entry.seconds if entry else 0.0

    @property
    def total_seconds(self) -> float:
        return sum(t.seconds for t in self.timings.values())


# ------------------------------------------------------------------------------------------------
# Modelled: money
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rate:
    """One price, and where it came from. A rate with no source is not usable here."""

    key: str
    cents: float
    per: str
    source: str
    read_on: str

    def __post_init__(self) -> None:
        if not self.source or not self.read_on:
            raise ValueError(
                f"rate {self.key!r} has no source or no date. A price nobody can check is a "
                "number this module will not multiply anything by."
            )


@dataclass(frozen=True, slots=True)
class RateCard:
    rate_card_id: str
    currency: str
    rates: dict[str, Rate]
    caveats: tuple[str, ...]
    reference_cents_per_page: float = 0.0
    reference_source: str = """"""

    def rate(self, key: str) -> Rate:
        try:
            return self.rates[key]
        except KeyError:
            raise KeyError(
                f"no rate named {key!r} in rate card {self.rate_card_id!r}. Add it with a source "
                "and a date rather than defaulting it to zero -- a tier priced at nothing is a "
                "tier that looks free."
            ) from None


def load_rate_card(path: Path | str = DEFAULT_RATE_CARD) -> RateCard:
    document = yaml.safe_load(Path(path).read_text("utf-8"))
    return RateCard(
        rate_card_id=str(document["rate_card_id"]),
        currency=str(document.get("currency", "USD")),
        rates={
            str(key): Rate(
                key=str(key),
                cents=float(entry["cents"]),
                per=str(entry["per"]),
                source=str(entry.get("source", "")),
                read_on=str(entry.get("read_on", "")),
            )
            for key, entry in document["rates"].items()
        },
        caveats=tuple(str(c) for c in document.get("caveats", ())),
        reference_cents_per_page=float(document.get("reference_cents_per_page", 0.0)),
        reference_source=str(document.get("reference_source", "")),
    )


@dataclass(frozen=True, slots=True)
class TierPrice:
    tier: Tier
    seconds: float
    work_units: int
    cents: float
    basis: str


@dataclass(frozen=True, slots=True)
class PricedCost:
    """What one run cost, in the currency of the rate card. See the module docstring."""

    rate_card_id: str
    currency: str
    machine: str
    records: int
    pages_processed: int
    error_count: int
    tiers: tuple[TierPrice, ...]
    rate_card_caveats: tuple[str, ...]
    reference_cents_per_page: float = 0.0
    reference_source: str = ""

    @property
    def total_cents(self) -> float:
        return sum(t.cents for t in self.tiers)

    @property
    def total_seconds(self) -> float:
        return sum(t.seconds for t in self.tiers)

    @property
    def cents_per_record(self) -> float:
        """The number a buyer signs: total cost divided by the whole catalog."""
        return self.total_cents / self.records if self.records else 0.0

    @property
    def cents_per_page(self) -> float:
        """The like-for-like number against ExtractBench: cost per page actually opened.

        Zero pages means the run never opened a document, and this returns 0.0 rather than
        dividing -- a run with no groundable records has no per-page cost, which is a fact about
        the catalog rather than a value to interpolate.
        """
        return self.total_cents / self.pages_processed if self.pages_processed else 0.0

    @property
    def cents_per_error(self) -> float:
        return self.total_cents / self.error_count if self.error_count else 0.0

    def versus_extractbench(self, reference_cents_per_page: float | None = None) -> dict[str, Any]:
        """Both comparisons, labelled, because only one of them is like-for-like.

        Extraction is priced per page over *every* page of *every* document. Errata opens a
        document only for the groundable fraction, so the number a buyer's spreadsheet ends up
        with is cost per catalog record -- and quoting only the per-page figure would compare our
        2.77% against their 100% without saying so.
        """
        reference = (
            self.reference_cents_per_page
            if reference_cents_per_page is None
            else reference_cents_per_page
        )
        return {
            "reference_cents_per_page": reference,
            "reference_source": self.reference_source,
            "errata_cents_per_page_processed": round(self.cents_per_page, 4),
            "errata_cents_per_catalog_record": round(self.cents_per_record, 6),
            "pages_processed": self.pages_processed,
            "catalog_records": self.records,
            "note": (
                "cents_per_page_processed is the like-for-like figure and is NOT the customer's "
                "bill: Errata opens a document only for groundable records, so the per-page rate "
                "applies to a small fraction of the catalog. cents_per_catalog_record is what a "
                "buyer signs. Both are modelled from a rate card, not measured from an invoice."
            ),
        }

    def caveats(self) -> tuple[str, ...]:
        return (
            "THIS IS NOT AN 8,000x SAVING AND MUST NOT BE QUOTED AS ONE. Errata's per-page figure "
            "is three orders of magnitude below ExtractBench's 8.1c because Errata CALLS NO "
            "MODEL: R1's extractor is rule-based, so the per-page cost is CPU seconds and nothing "
            "else. It is also not doing the same job -- it reads born-digital tables in a known "
            "layout, does no OCR, and its fallback path abstains on the large majority of records "
            "rather than guessing. A cost comparison between a system that answers and a system "
            "that declines is not a comparison. The number below is what this pipeline costs; it "
            "is not what a pipeline of equivalent capability would cost.",
            "PAGES ARE PARSED ONCE, NOT ONCE PER RECORD. FR-1.4 caches the text layer on content "
            "hash, so a datasheet covering hundreds of SKUs is opened a single time and every "
            "record after the first re-derives against a layer already in memory. That is a real "
            "and defensible property of auditing a catalog rather than extracting a document, and "
            "it means 'per page processed' counts distinct pages, not extraction events.",
            "MONEY HERE IS MODELLED, NOT BILLED. This repository has never run in production. "
            f"Every figure is measured seconds and measured counts multiplied by rate card "
            f"{self.rate_card_id}, whose entries are published third-party list prices with their "
            "sources and dates. Treat them as an order of magnitude with a method attached.",
            "SECONDS ARE MEASURED AND MACHINE-SPECIFIC. They were taken on: "
            f"{self.machine}. A second on a laptop is not a second on a build agent.",
            "THE CLAIM UNDER TEST SURVIVES THE RATES BEING WRONG. FR-8.7 asserts that cost tracks "
            "errors rather than rows. That is a statement about the shape of the curve: double "
            "every rate and T2 still does not grow with catalog size.",
            *self.rate_card_caveats,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "rate_card_id": self.rate_card_id,
            "currency": self.currency,
            "machine": self.machine,
            "measured": False,
            "total_cents": round(self.total_cents, 4),
            "total_seconds": round(self.total_seconds, 4),
            "cents_per_record": round(self.cents_per_record, 6),
            "cents_per_page_processed": round(self.cents_per_page, 4),
            "cents_per_error": round(self.cents_per_error, 4),
            "tiers": [
                {
                    "tier": t.tier.value,
                    "seconds": round(t.seconds, 4),
                    "work_units": t.work_units,
                    "cents": round(t.cents, 4),
                    "basis": t.basis,
                }
                for t in self.tiers
            ],
            "caveats": list(self.caveats()),
        }

    def text(self, reference_cents_per_page: float | None = None) -> str:
        reference = (
            self.reference_cents_per_page
            if reference_cents_per_page is None
            else reference_cents_per_page
        )
        lines = [
            f"COST -- rate card {self.rate_card_id}, {self.currency}",
            "",
            f"  {'tier':6s} {'seconds':>10s} {'work units':>12s} {'cents':>10s}   basis",
        ]
        for t in self.tiers:
            lines.append(
                f"  {t.tier.value:6s} {t.seconds:10.3f} {t.work_units:12,d} {t.cents:10.4f}   "
                f"{t.basis}"
            )
        lines += [
            "",
            f"  total                {self.total_seconds:10.3f} s   {self.total_cents:10.4f} c",
            "",
            f"  per catalog record   {self.cents_per_record:.6f} c    <- what a buyer signs",
            f"  per page processed   {self.cents_per_page:.4f} c    <- like-for-like vs "
            f"ExtractBench's {reference} c/page",
            f"  per disagreement     {self.cents_per_error:.4f} c",
            "",
            f"  pages opened {self.pages_processed:,} of a {self.records:,}-record catalog. "
            "The per-page rate applies to that fraction, never to the catalog.",
            "",
        ]
        lines += [f"  ! {caveat}" for caveat in self.caveats()]
        return "\n".join(lines)


def price_run(
    cost: CostReport,
    timer: Timer,
    *,
    pages_processed: int,
    machine: str,
    rate_card: RateCard | None = None,
) -> PricedCost:
    """Turn measured seconds and measured counts into money, tier by tier.

    Every tier is priced on **compute seconds**, because that is what all four of them actually
    consume -- none of them calls a paid model today. That is worth saying rather than leaving
    implied: the day an LLM selector is wired into T2, this function needs a per-token rate and
    the T2 line will move by an order of magnitude. The rate card has the entry waiting and
    :data:`Rate` will refuse it without a source.
    """
    card = rate_card or load_rate_card()
    compute = card.rate("compute_second")
    reviewer = card.rate("reviewer_second")

    prices: list[TierPrice] = []
    for tier in (Tier.T0_STRUCTURAL, Tier.T1_GROUNDED, Tier.T2_DEEP, Tier.T3_HUMAN):
        seconds = timer.seconds(tier)
        units = cost.of(tier).work_units

        if tier is Tier.T3_HUMAN:
            # T3 is a person, and the honest price of a queue row is the reviewer-seconds it takes
            # to clear -- which FR-9.3 says NOT MEASURED, because nobody has been timed. So this
            # line is priced at zero and says so, rather than inventing a plausible minute.
            prices.append(
                TierPrice(
                    tier=tier,
                    seconds=seconds,
                    work_units=units,
                    cents=0.0,
                    basis=(
                        f"NOT PRICED. {units:,} queue row(s) at {reviewer.cents}c/reviewer-second "
                        "would need seconds-per-row, and FR-9.3 reports NOT MEASURED because no "
                        "reviewer has ever been timed. Priced at zero and flagged, not estimated."
                    ),
                )
            )
            continue

        prices.append(
            TierPrice(
                tier=tier,
                seconds=seconds,
                work_units=units,
                cents=seconds * compute.cents,
                basis=f"{seconds:.3f}s x {compute.cents}c/s ({compute.source})",
            )
        )

    return PricedCost(
        reference_cents_per_page=card.reference_cents_per_page,
        reference_source=card.reference_source,
        rate_card_id=card.rate_card_id,
        currency=card.currency,
        machine=machine,
        records=cost.records,
        pages_processed=pages_processed,
        error_count=cost.error_count,
        tiers=tuple(prices),
        rate_card_caveats=card.caveats,
    )
