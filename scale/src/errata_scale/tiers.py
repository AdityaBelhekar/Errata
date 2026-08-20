"""FR-8.7 -- tiered execution, and the cost report that has to prove it.

    "T0 structural (all records) -> T1 grounded (documented records) -> T2 deep (disagreements
    only) -> T3 human. Cost report shows T2/T3 volume scaling with error count, not SKU count."

The commercial argument for auditing rather than extracting rests entirely on this shape. Running
the expensive machinery over every record of a 400,000-SKU catalog is what makes AI data work
priced per row, and priced per row it is a cost centre. Running it only where a cheap check already
found a disagreement makes the bill track the customer's *error count*, which is a number that goes
down as they improve -- so the vendor and the customer want the same thing.

That is a nice story and it is trivially falsifiable, so the cost report does not assert it. Every
number below is a **count of operations that actually happened** during the run:

* ``T0`` -- one structural pass per record. Grows with catalog size, and is meant to.
* ``T1`` -- one document parse and one re-derivation per *groundable* record. Grows with the
  groundable fraction (FR-8.1), not with the catalog.
* ``T2`` -- one counter-evidence search per disagreement. In :mod:`errata_audit.audit` this call
  sits behind ``comparison.raises_finding``, so the tier boundary is enforced by the code path
  rather than by a diagram.
* ``T3`` -- one queue row per finding a human is asked to look at.

:meth:`CostReport.scales_with_error_count` states the property as an assertion over these counts,
and a test runs the same catalog twice -- once padded with clean records -- to show T2 and T3 do
not move. A claim about scaling that is only ever measured at one size is not a measurement.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

__all__ = ["CostReport", "Tier", "TierCost"]


class Tier(str, enum.Enum):
    """The four tiers, in the order a record passes through them."""

    T0_STRUCTURAL = "T0"
    T1_GROUNDED = "T1"
    T2_DEEP = "T2"
    T3_HUMAN = "T3"

    @property
    def description(self) -> str:
        return {
            Tier.T0_STRUCTURAL: "structural checks, every record, no source document required",
            Tier.T1_GROUNDED: "re-derivation against a source document, groundable records only",
            Tier.T2_DEEP: "counter-evidence and calibration, disagreements only",
            Tier.T3_HUMAN: "a reviewer, queue rows only",
        }[self]

    @property
    def scales_with(self) -> str:
        return {
            Tier.T0_STRUCTURAL: "catalog size",
            Tier.T1_GROUNDED: "groundable fraction",
            Tier.T2_DEEP: "error count",
            Tier.T3_HUMAN: "error count",
        }[self]


@dataclass(frozen=True, slots=True)
class TierCost:
    """One tier's measured volume."""

    tier: Tier
    records_entered: int
    work_units: int
    unit: str
    note: str = ""

    def text(self) -> str:
        return (
            f"  {self.tier.value}  {self.records_entered:9,d} record(s) entered   "
            f"{self.work_units:9,d} {self.unit}   scales with {self.tier.scales_with}"
        )


@dataclass(frozen=True, slots=True)
class CostReport:
    """The measured cost of one run, tier by tier."""

    tiers: tuple[TierCost, ...]
    records: int
    error_count: int
    groundable: int

    def of(self, tier: Tier) -> TierCost:
        for cost in self.tiers:
            if cost.tier is tier:
                return cost
        raise KeyError(tier)

    def scales_with_error_count(self) -> bool:
        """FR-8.7's acceptance criterion, stated as a property of this run's own counts.

        T2 does exactly one counter-evidence search per disagreement and T3 offers exactly one
        queue row per finding, so both are bounded by the error count and neither is bounded by the
        record count. The inequality is what a second run at a different catalog size then has to
        preserve, and a test does that rather than trusting this method alone.
        """
        deep = self.of(Tier.T2_DEEP)
        human = self.of(Tier.T3_HUMAN)
        return deep.work_units <= self.error_count and human.work_units <= self.error_count

    def per_error(self) -> dict[str, float]:
        if not self.error_count:
            return {tier.tier.value: 0.0 for tier in self.tiers}
        return {
            tier.tier.value: round(tier.work_units / self.error_count, 4) for tier in self.tiers
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "records": self.records,
            "groundable": self.groundable,
            "error_count": self.error_count,
            "scales_with_error_count": self.scales_with_error_count(),
            "tiers": [
                {
                    "tier": cost.tier.value,
                    "description": cost.tier.description,
                    "records_entered": cost.records_entered,
                    "work_units": cost.work_units,
                    "unit": cost.unit,
                    "scales_with": cost.tier.scales_with,
                    "note": cost.note,
                }
                for cost in self.tiers
            ],
        }

    def text(self) -> str:
        lines = [
            f"TIERED EXECUTION -- {self.records:,} record(s), {self.error_count:,} disagreement(s)",
            "",
        ]
        lines.extend(cost.text() for cost in self.tiers)
        lines.append("")
        lines.append(
            "  T2 and T3 volume is bounded by the disagreement count, not the record count: "
            f"{self.scales_with_error_count()}"
        )
        for cost in self.tiers:
            if cost.note:
                lines.append(f"  {cost.tier.value}: {cost.note}")
        return "\n".join(lines)
