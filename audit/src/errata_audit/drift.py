"""NFR-4 -- the calibration drift alarm, and the fixture that proves it fires.

    "Calibration drift alarm. Fires on calibration degradation, not just accuracy degradation.
    Alarm triggers on a synthetic drift fixture."

**Read the requirement's second clause twice, because it is the whole design.** A monitor that
watches accuracy is easy and does not satisfy this. The failure NFR-4 names is a model that is
*just as good at ranking as it ever was* and has stopped meaning what it says: every probability
drifts up by fifteen points, the ordering is untouched, AUC does not move, and ``0.9`` now means
seven-in-ten. Nothing that watches accuracy sees that. It is also the failure that matters most
here, because FR-6.1's entire promise is the sentence *"calibrated_p = 0.9 means approximately
9-in-10 on held-out data"* -- and a reviewer who learns that 90% means 70% has learned it
permanently.

So this alarm watches **the gap between what was said and what happened**, and it is deliberately
possible for it to stay silent while accuracy collapses. :func:`degraded_but_calibrated` is a
fixture built to do exactly that, and a test asserts the alarm does NOT fire on it. An alarm that
fired on everything bad would be an alarm nobody could act on.

**No threshold is tuned.** A bin trips when the probability it promised falls outside the Wilson
interval of what actually happened in it -- so the sensitivity comes from the sample size, which
is the honest source. A quiet bin with four observations cannot trip; a bin with four hundred trips
on a small gap, correctly, because with four hundred observations a small gap is real. The one
magic number is :data:`MIN_OBSERVATIONS`, and it is a floor on saying anything at all rather than a
sensitivity dial.

**Why synthetic input is right here and does not break ground rule 5.** The rule says gates stay
``NOT_MEASURED`` on synthetic input, because a gate measures the product against the world.
This is not a gate. NFR-4's own acceptance criterion is *"alarm triggers on a synthetic drift
fixture"* -- the thing under test is the alarm, and the only way to test an alarm is to cause the
condition it watches for. What would break the rule is reporting a *calibration quality* from
synthetic data, and nothing here does: :func:`monitor` reports whether the alarm fired, never how
well calibrated anything is.

**What is still blocked, and it is not this.** There is no calibration set: calibration wants
reviewer decisions and nobody has made any (see :mod:`errata_audit.confidence`). So the alarm has
nothing real to watch yet. That is a dependency on FR-7.6, not on NFR-4, and building the alarm
now means the day a calibration set exists it is already being watched -- rather than the alarm
being written six months later by somebody reconstructing what the reference distribution was.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Sequence
from dataclasses import dataclass

from .confidence import CalibrationModel, ReliabilityBin, reliability_diagram

__all__ = [
    "MIN_OBSERVATIONS",
    "BinFinding",
    "DriftReport",
    "DriftVerdict",
    "degraded_but_calibrated",
    "drifted_overconfident",
    "monitor",
    "stable",
]

#: Below this many observations in a window, the alarm says ``INSUFFICIENT_DATA`` and nothing else.
#:
#: Not a sensitivity setting. An alarm that fires on thirty records will fire constantly on noise,
#: be muted within a week, and then not fire on the drift it existed for -- which is worse than
#: not having one. Set to the same order as ``MIN_DECISIONS`` in the reviewer protocol and for the
#: same reason: below it, the number is not wrong so much as not yet a number.
MIN_OBSERVATIONS = 100

#: 95%, two-sided. The same z the R0 harness uses for every proportion it publishes, so an interval
#: here means what an interval means everywhere else in the repository.
_Z95 = 1.959963984540054


def _wilson(successes: int, total: int, z: float = _Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Implemented here rather than imported from ``errata_bench.stats``, which has one. That import
    is forbidden -- ``audit/tests/test_boundaries.py`` asserts the product never imports its own
    scorer, because "a product that imported its own scorer would be a product that could be tuned
    against it". Twelve lines of arithmetic is the right price for that boundary, and a test pins
    this implementation against the bench one so the two cannot diverge.
    """
    if total <= 0:
        return (0.0, 1.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


class DriftVerdict(str, enum.Enum):
    STABLE = "stable"
    """Everything the model promised is inside what happened. No action."""

    DRIFTED = "drifted"
    """At least one bin promised a probability the outcomes rule out. **Fire.**"""

    INSUFFICIENT_DATA = "insufficient_data"
    """Fewer than :data:`MIN_OBSERVATIONS`. Not "stable" -- a different statement, and collapsing
    the two is how a monitor goes quiet without anybody deciding it should."""


@dataclass(frozen=True, slots=True)
class BinFinding:
    """One bin of the current window, and whether what it promised survived contact."""

    lower: float
    upper: float
    count: int
    predicted: float
    observed: float
    interval: tuple[float, float]

    @property
    def tripped(self) -> bool:
        low, high = self.interval
        return not (low <= self.predicted <= high)

    @property
    def overconfident(self) -> bool:
        """Promised more than happened. The dangerous direction: an over-confident bin sends a
        reviewer a redline it says is near-certain, and that is how trust is spent."""
        return self.predicted > self.interval[1]

    def sentence(self) -> str:
        direction = "over-confident" if self.overconfident else "under-confident"
        return (
            f"[{self.lower:.2f}, {self.upper:.2f}) n={self.count}: promised {self.predicted:.3f}, "
            f"observed {self.observed:.3f} (95% CI {self.interval[0]:.3f}-{self.interval[1]:.3f})"
            + (f" -- {direction}" if self.tripped else "")
        )


@dataclass(frozen=True, slots=True)
class DriftReport:
    verdict: DriftVerdict
    n: int
    bins: tuple[BinFinding, ...]
    reference_ece: float
    observed_ece: float
    accuracy: float
    """Fraction of the window whose outcome was positive at a 0.5 threshold. Reported **next to**
    the verdict and never used to reach it -- it is here so a reader can see the two moving
    independently, which is the distinction NFR-4 turns on."""

    @property
    def fired(self) -> bool:
        return self.verdict is DriftVerdict.DRIFTED

    @property
    def tripped_bins(self) -> tuple[BinFinding, ...]:
        return tuple(b for b in self.bins if b.tripped)

    def text(self) -> str:
        lines = [
            f"NFR-4 CALIBRATION DRIFT -- {self.verdict.value.upper()}",
            "",
            f"  observations        {self.n}",
            f"  reference ECE       {self.reference_ece:.4f}",
            f"  observed ECE        {self.observed_ece:.4f}",
            f"  accuracy in window  {self.accuracy:.4f}   "
            "(reported, NOT used to reach the verdict)",
            "",
        ]
        lines += [f"    {b.sentence()}" for b in self.bins]
        lines.append("")
        if self.verdict is DriftVerdict.DRIFTED:
            lines.append(
                f"  {len(self.tripped_bins)} bin(s) promised a probability the outcomes rule out. "
                "calibrated_p no longer means what FR-6.1 says it means; stop quoting it and "
                "refit against a current calibration set."
            )
        elif self.verdict is DriftVerdict.INSUFFICIENT_DATA:
            lines.append(
                f"  fewer than {MIN_OBSERVATIONS} observations. This is NOT 'stable' -- nothing "
                "has been checked."
            )
        else:
            lines.append("  every bin's promise is inside its outcomes' interval.")
        return "\n".join(lines)


def monitor(
    observations: Sequence[tuple[float, bool]],
    reference: CalibrationModel | None = None,
    *,
    bins: int = 5,
) -> DriftReport:
    """Watch a window of ``(calibrated_p, outcome)`` pairs for calibration drift.

    ``reference`` is the model whose promises are being checked. It is optional because the
    interesting comparison is between the probabilities *as issued* and the outcomes -- the
    reference contributes its ECE for context, not the decision. A window can drift away from a
    model that was never fitted here, and refusing to look until one is supplied would make the
    alarm depend on the thing it is meant to survive.
    """
    n = len(observations)
    reference_ece = reference.expected_calibration_error if reference is not None else 0.0

    current: tuple[ReliabilityBin, ...] = reliability_diagram(observations, bins=bins)
    findings = tuple(
        BinFinding(
            lower=b.lower,
            upper=b.upper,
            count=b.count,
            predicted=b.mean_predicted,
            observed=b.observed_rate,
            interval=_wilson(round(b.observed_rate * b.count), b.count),
        )
        for b in current
    )

    total = sum(b.count for b in current) or 1
    observed_ece = sum(b.count * abs(b.gap) for b in current) / total
    accuracy = sum(1 for p, y in observations if (p >= 0.5) == y) / n if n else 0.0

    if n < MIN_OBSERVATIONS:
        verdict = DriftVerdict.INSUFFICIENT_DATA
    elif any(f.tripped for f in findings):
        verdict = DriftVerdict.DRIFTED
    else:
        verdict = DriftVerdict.STABLE

    return DriftReport(
        verdict=verdict,
        n=n,
        bins=findings,
        reference_ece=reference_ece,
        observed_ece=observed_ece,
        accuracy=accuracy,
    )


# ------------------------------------------------------------------------------------------------
# The synthetic fixtures NFR-4's acceptance criterion asks for
#
# Three, not one. A fixture that makes an alarm fire proves only that it can fire. What has to be
# proved is that it fires on the RIGHT thing, which needs a case it fires on, a case it stays quiet
# on, and -- the one that matters -- a case that is genuinely bad in a way it is supposed to ignore.
# ------------------------------------------------------------------------------------------------


def stable(n: int = 400, *, seed: int = 20260821) -> list[tuple[float, bool]]:
    """A well-calibrated window: a record predicted at ``p`` is positive with probability ``p``.

    The negative control. An alarm that cannot be silent is not an alarm.
    """
    import random

    rng = random.Random(seed)
    out = []
    for _ in range(n):
        p = rng.uniform(0.05, 0.95)
        out.append((p, rng.random() < p))
    return out


def drifted_overconfident(
    n: int = 400, *, shift: float = 0.20, seed: int = 20260821
) -> list[tuple[float, bool]]:
    """The failure NFR-4 exists for: probabilities shifted up, ordering untouched.

    Outcomes are drawn from the TRUE probability and the model reports ``p + shift``. Discrimination
    is identical -- the ranking is a monotone function of the truth, so AUC does not move by a
    thousandth -- and every promise is now twenty points too high. An accuracy monitor sees nothing.
    """
    import random

    rng = random.Random(seed)
    out = []
    for _ in range(n):
        true_p = rng.uniform(0.05, 0.75)
        out.append((min(1.0, true_p + shift), rng.random() < true_p))
    return out


def degraded_but_calibrated(n: int = 400, *, seed: int = 20260821) -> list[tuple[float, bool]]:
    """Accuracy collapses; calibration is perfect. **The alarm must stay silent.**

    Every record is predicted at the base rate, so the model has lost all discriminating power --
    it can no longer tell a defect from a clean record at all. And it is telling the exact truth
    about that: it promises 0.5 and is right half the time. That is a model saying "I do not know",
    honestly.

    This is the fixture that proves the alarm measures calibration rather than quality. NFR-4 says
    "fires on calibration degradation, **not just** accuracy degradation"; a monitor that fired
    here would be an accuracy monitor with a calibration label on it.
    """
    import random

    rng = random.Random(seed)
    return [(0.5, rng.random() < 0.5) for _ in range(n)]
