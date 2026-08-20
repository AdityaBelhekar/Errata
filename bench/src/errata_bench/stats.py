"""Interval estimates for small samples.

A false-positive rate quoted as a bare percentage on a few hundred cases is a number pretending to
be a measurement. 0/40 is not "0%" -- it is "somewhere under about 9%, with 95% confidence", and on
a gate whose stop condition is 5% that distinction decides whether the project continues.

The Wilson score interval is used rather than the normal approximation because it stays sensible at
the extremes, which is exactly where this metric lives.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["Proportion", "wilson"]

#: Two-sided 95% normal quantile.
_Z95 = 1.959963984540054


@dataclass(frozen=True, slots=True)
class Proportion:
    """A measured rate with an interval, and the honesty to render itself as one."""

    successes: int
    total: int
    lo: float
    hi: float
    confidence: float = 0.95

    @property
    def point(self) -> float:
        return self.successes / self.total if self.total else 0.0

    @property
    def percent(self) -> float:
        return 100.0 * self.point

    def render(self) -> str:
        if self.total == 0:
            return "n/a (no cases)"
        return (
            f"{self.percent:.2f}%  [{100 * self.lo:.2f}%, {100 * self.hi:.2f}%]  "
            f"({self.successes}/{self.total})"
        )

    def render_short(self) -> str:
        if self.total == 0:
            return "n/a"
        return f"{self.percent:.2f}% ({self.successes}/{self.total})"


def wilson(successes: int, total: int, z: float = _Z95) -> Proportion:
    """Wilson score interval for a binomial proportion."""
    if total <= 0:
        return Proportion(successes=successes, total=0, lo=0.0, hi=0.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = (z / denominator) * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return Proportion(
        successes=successes,
        total=total,
        lo=max(0.0, centre - spread),
        hi=min(1.0, centre + spread),
    )
