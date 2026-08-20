"""FR-6.1 / FR-6.3 -- turning a raw score into a probability, and reporting what it costs.

    "``calibrated_p = 0.9`` means approximately 9-in-10 on held-out data."

That sentence is the whole requirement, and it is the one every product in this space gets wrong:
a softmax output printed with a percent sign is not a probability, it is a monotone transform of an
activation, and a reviewer who learns that "92%" means nothing has learned it permanently.

Three commitments make the number defensible here, and each is enforced by a type rather than by
discipline:

* **A calibrated probability names its method and its calibration set.**
  ``errata_spec.Confidence`` refuses to be constructed with a ``calibrated_p`` and no method, and
  refuses again with no ``calibration_set_id``. So a number nobody can trace cannot be stored.
* **A raw score and a calibrated probability live in different fields.** ``raw_score`` is what the
  extractor observed; it is never rendered as a percentage anywhere in the console (FR-7.5 forbids
  a bare confidence as the primary signal in any case).
* **Outside the calibration set's support, the answer is a decline.** FR-6.2 gives it a name --
  ``calibration_out_of_distribution`` -- and §8.3 warns it is the reason most likely to eat the
  product's coverage. It is still better than a confident number about a region nobody measured.

**No calibration set ships with this package, and that is a result rather than an omission.**
Calibration wants labels: pairs of (score, was-the-catalog-really-wrong) for records the audit
*raised*. Two candidate sources exist and neither works yet.

* **Reviewer adjudications** (FR-7.6) are the right source and there are none, because nobody has
  used the console yet. :func:`errata_audit.ledger.calibration_examples` extracts them the day
  there are, and ``errata-audit calibrate`` fits and writes the model with no code change.
* **The demonstration catalog's injected defects** have ground truth by construction -- and on that
  population the audit raises **no false positives at all**. A calibration set with one outcome
  cannot be fitted: every probability would be 1.0 regardless of the score. :func:`fit_platt`
  refuses it explicitly rather than returning a model that looks fitted.

So R1 ships the machinery, the reliability diagram and the refusal, and reports its confidences as
raw scores until a reviewer has produced labels. A redline with no calibrated probability is not
promoted above one that has it (``Redline.expected_review_value`` ranks it by blast radius alone),
which is the conservative direction. Inventing the number instead would be a two-line change and it
is the exact move ground rule 1 forbids.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import yaml

from errata_spec import Confidence, DeclinedReason

__all__ = [
    "CALIBRATION_CONFIG",
    "CalibrationModel",
    "ReliabilityBin",
    "RiskCoveragePoint",
    "aurc",
    "calibrate",
    "fit_platt",
    "load_calibration",
    "reliability_diagram",
    "risk_coverage_curve",
]

#: Where a fitted calibration set is looked for. **Absent in this repository, deliberately** -- see
#: the module docstring. ``errata-audit calibrate`` writes one here from reviewer adjudications.
CALIBRATION_CONFIG = Path(__file__).parent / "config" / "calibration.yaml"

#: How far outside the calibration set's observed score range a raw score may fall before the
#: record is declined as out of distribution. Not zero: a score a hair above the highest labelled
#: example is not a different population. Not generous either -- the whole point of the reason code
#: is that it fires.
SUPPORT_TOLERANCE = 0.05


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    """One bin of the reliability diagram: what we said, against what happened."""

    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed_rate: float

    @property
    def gap(self) -> float:
        """Predicted minus observed. Positive means over-confident, which is the dangerous sign."""
        return self.mean_predicted - self.observed_rate


@dataclass(frozen=True, slots=True)
class CalibrationModel:
    """A fitted mapping from raw score to probability, with its provenance attached."""

    calibration_set_id: str
    method: str
    """``platt`` here. ``conformal`` is the other value ``errata_spec.Confidence`` permits and is
    not implemented: split conformal needs an exchangeable calibration sample, and the shipped set
    is a constructed population where exchangeability with a customer's catalog is exactly what
    cannot be claimed. Shipping it anyway would be the more impressive-looking wrong answer."""

    a: float
    b: float
    n: int
    positives: int
    score_min: float
    score_max: float
    provenance: str = ""
    bins: tuple[ReliabilityBin, ...] = field(default_factory=tuple)

    def probability(self, raw_score: float) -> float:
        return _sigmoid(self.a * raw_score + self.b)

    def in_support(self, raw_score: float) -> bool:
        return (
            self.score_min - SUPPORT_TOLERANCE
            <= raw_score
            <= self.score_max + SUPPORT_TOLERANCE
        )

    @property
    def base_rate(self) -> float:
        return self.positives / self.n if self.n else 0.0

    @property
    def expected_calibration_error(self) -> float:
        """Weighted mean |predicted - observed| across bins. One number, and it is reported with
        the diagram rather than instead of it: an ECE of 0.04 can hide a bin that is 30 points
        over-confident and holds the records a reviewer actually sees."""
        if not self.bins:
            return 0.0
        total = sum(b.count for b in self.bins) or 1
        return sum(b.count * abs(b.gap) for b in self.bins) / total


def fit_platt(
    labelled: Sequence[tuple[float, bool]],
    *,
    calibration_set_id: str,
    provenance: str = "",
    iterations: int = 100,
) -> CalibrationModel:
    """Fit ``p = sigmoid(a * raw + b)`` by Newton-Raphson on the log-likelihood.

    Platt scaling rather than isotonic regression, for one reason: isotonic fits a step function
    that interpolates the calibration set, and with the sample sizes an audit realistically has
    (tens of adjudications in the first week) it produces confident probabilities of exactly 0 and
    exactly 1. A two-parameter fit cannot.

    Deterministic: fixed initialisation, fixed iteration count, no randomness anywhere.
    """
    if len(labelled) < 2:
        raise ValueError(
            "a calibration set of fewer than two examples cannot produce a probability anyone "
            "should read; leave the confidence uncalibrated instead"
        )
    positives = sum(1 for _, y in labelled if y)
    if positives in (0, len(labelled)):
        raise ValueError(
            "the calibration set contains only one outcome, so every fitted probability would be "
            "0 or 1 regardless of the score. Collect labels of both kinds before calibrating."
        )

    a, b = 0.0, 0.0
    for _ in range(iterations):
        g_a = g_b = h_aa = h_ab = h_bb = 0.0
        for raw, label in labelled:
            p = _sigmoid(a * raw + b)
            residual = p - (1.0 if label else 0.0)
            weight = max(p * (1 - p), 1e-9)
            g_a += residual * raw
            g_b += residual
            h_aa += weight * raw * raw
            h_ab += weight * raw
            h_bb += weight
        determinant = h_aa * h_bb - h_ab * h_ab
        if abs(determinant) < 1e-12:
            break
        step_a = (h_bb * g_a - h_ab * g_b) / determinant
        step_b = (h_aa * g_b - h_ab * g_a) / determinant
        a -= step_a
        b -= step_b
        if abs(step_a) < 1e-9 and abs(step_b) < 1e-9:
            break

    scores = [raw for raw, _ in labelled]
    model = CalibrationModel(
        calibration_set_id=calibration_set_id,
        method="platt",
        a=a,
        b=b,
        n=len(labelled),
        positives=positives,
        score_min=min(scores),
        score_max=max(scores),
        provenance=provenance,
    )
    predicted = [(model.probability(raw), label) for raw, label in labelled]
    return CalibrationModel(
        calibration_set_id=model.calibration_set_id,
        method=model.method,
        a=model.a,
        b=model.b,
        n=model.n,
        positives=model.positives,
        score_min=model.score_min,
        score_max=model.score_max,
        provenance=provenance,
        bins=reliability_diagram(predicted),
    )


def reliability_diagram(
    predicted: Sequence[tuple[float, bool]], *, bins: int = 5
) -> tuple[ReliabilityBin, ...]:
    """FR-6.1's published diagram, as data.

    Empty bins are omitted rather than reported as 0% observed: a bin nobody landed in says nothing
    about calibration, and drawing it at zero makes a model look over-confident where it is merely
    untested.
    """
    edges = [i / bins for i in range(bins + 1)]
    out: list[ReliabilityBin] = []
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        members = [
            (p, y)
            for p, y in predicted
            if (lower <= p < upper) or (index == bins - 1 and p == upper)
        ]
        if not members:
            continue
        out.append(
            ReliabilityBin(
                lower=lower,
                upper=upper,
                count=len(members),
                mean_predicted=sum(p for p, _ in members) / len(members),
                observed_rate=sum(1 for _, y in members if y) / len(members),
            )
        )
    return tuple(out)


def calibrate(raw_score: float | None, model: CalibrationModel | None) -> Confidence:
    """Produce the ``Confidence`` a claim or redline carries.

    Without a model, or outside its support, the result carries ``raw_score`` and **no**
    ``calibrated_p``, plus the abstention reason FR-6.2 names. Downstream code that wants a
    probability then finds ``None`` and has to decide what to do about it -- which is the correct
    outcome and the reason this returns a type rather than a float.
    """
    if raw_score is None:
        return Confidence()
    if model is None:
        return Confidence(raw_score=raw_score)
    if not model.in_support(raw_score):
        return Confidence(
            raw_score=raw_score,
            abstained=True,
            abstain_reason=DeclinedReason.CALIBRATION_OUT_OF_DISTRIBUTION,
        )
    return Confidence(
        raw_score=raw_score,
        calibrated_p=round(model.probability(raw_score), 4),
        calibration_set_id=model.calibration_set_id,
        method="platt",
    )


def load_calibration(path: Path | str | None = None) -> CalibrationModel | None:
    """Load a calibration set and fit it. Returns ``None`` when the file declares no examples.

    ``None`` is a legitimate answer and the pipeline handles it: an audit with no calibration is an
    audit that reports raw scores and declines to call them probabilities.
    """
    path = Path(path or CALIBRATION_CONFIG)
    if not path.exists():
        return None
    document = yaml.safe_load(path.read_text("utf-8")) or {}
    examples = [
        (float(row["raw_score"]), bool(row["catalog_wrong"]))
        for row in document.get("examples", ())
    ]
    if len(examples) < 2:
        return None
    return fit_platt(
        examples,
        calibration_set_id=str(document.get("calibration_set_id", path.stem)),
        provenance=str(document.get("provenance", "")).strip(),
    )


# ------------------------------------------------------------------------------------------------
# FR-6.3 -- risk-coverage and AURC for a run
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RiskCoveragePoint:
    coverage: float
    risk: float
    n: int


def risk_coverage_curve(
    scored: Sequence[tuple[float, bool]],
) -> tuple[RiskCoveragePoint, ...]:
    """Risk against coverage, answering most-confident-first.

    ``scored`` is ``(confidence, was_correct)``. Risk is the error rate among the answers given at
    that coverage -- the number that says whether the confidence signal is worth anything, because
    a system whose risk is flat across coverage has a confidence that ranks nothing.

    Ties are broken by input order, deterministically. Random tie-breaking would make an audit
    report a slightly different AURC on every run of the same data, which is the kind of small
    dishonesty that costs a customer's trust in the whole report.
    """
    if not scored:
        return ()
    ranked = sorted(enumerate(scored), key=lambda item: (-item[1][0], item[0]))
    errors = 0
    points: list[RiskCoveragePoint] = []
    for index, (_, (_score, correct)) in enumerate(ranked, start=1):
        if not correct:
            errors += 1
        points.append(
            RiskCoveragePoint(coverage=index / len(ranked), risk=errors / index, n=index)
        )
    return tuple(points)


def aurc(curve: Sequence[RiskCoveragePoint]) -> float:
    """Area under the risk-coverage curve, by the trapezium rule. Lower is better."""
    if len(curve) < 2:
        return curve[0].risk if curve else 0.0
    area = 0.0
    for previous, point in pairwise(curve):
        area += (point.coverage - previous.coverage) * (point.risk + previous.risk) / 2
    span = curve[-1].coverage - curve[0].coverage
    return area / span if span > 0 else curve[0].risk


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    exp_z = math.exp(z)
    return exp_z / (1.0 + exp_z)
