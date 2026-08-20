"""FR-9.1 and FR-9.2 -- the benchmark's axes, each one runnable on its own.

Six axes. One of them is somebody else's metric, reused verbatim so our number can be put next to
theirs; five are axes no published benchmark scores, which is the reason this file exists.

    grounding              FR-9.1  ExtractBench's word-level grounding F1 at IoU 0.5
    class_assignment       FR-9.2  ETIM class resolution, including the must-abstain cases
    compound_values        FR-9.2  compound-value normalization
    crosswalk              FR-9.2  cross-standard mapping -- and refusal to map
    supersession           FR-9.2  which claim is current, and what a broken history does
    abstention             FR-9.2  risk-coverage, AURC, selective accuracy at fixed coverage

**FR-9.1 is not implemented here.** ``errata_bench.operating_point.grounding_f1`` carries
ExtractBench's definition, was written against the paper, and is pinned by R0's tests. This module
calls it. A benchmark that re-implements the metric it claims to reuse verbatim has not reused it
verbatim -- it has written a second opinion and named it after the first.

**Every axis reports its provenance and its n.** An axis over 20 labelled cases says so next to
its rate, because the alternative -- a bare percentage from twenty cases -- is the specific way
benchmark tables mislead. And an axis with no data reports ``NOT_MEASURED`` rather than a number,
which is R0's rule (ground rule 5) applied to the benchmark that succeeded R0.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from errata_audit.ledger import LedgerEvent
from errata_bench.equivalence import Outcome, load_cases, run_suite
from errata_bench.operating_point import (
    EXTRACTBENCH_CITATION,
    EXTRACTBENCH_VALUE_F1,
    EXTRACTBENCH_WORD_GROUNDING_F1,
    GROUNDING_IOU_THRESHOLD,
    GroundingLevel,
    MCBCorpus,
    Provenance,
    aurc,
    grounding_f1,
    load_corpus,
    risk_coverage_curve,
    selective_accuracy_at_coverage,
    value_f1,
)
from errata_bench.stats import wilson
from errata_valuesem import Kind, normalize

__all__ = [
    "AXES",
    "DEFAULT_CORPUS",
    "AxisResult",
    "AxisStatus",
    "axis_ids",
    "run_all",
    "run_axis",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORPUS = REPO_ROOT / "var" / "spike" / "corpus.yaml"

#: The kinds that make a value *compound* -- more than one number, or a number that is an
#: interval. Decided by parsing the value rather than by matching its surface form: "16/25 A" and
#: "16 ... 25 A" look different and are the same problem, and a regex over the string would pick
#: the axis's population by typography.
COMPOUND_KINDS = frozenset({Kind.RANGE, Kind.QUANTITY_SET})


class AxisStatus(str, enum.Enum):
    MEASURED = "MEASURED"
    NOT_MEASURED = "NOT_MEASURED"


@dataclass(frozen=True, slots=True)
class AxisResult:
    """One axis's number, with everything needed to read it honestly."""

    axis: str
    title: str
    requirement: str
    status: AxisStatus
    headline: str
    n: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    provenance: str = ""
    caveats: tuple[str, ...] = ()
    comparable_to: str = ""

    def text(self) -> str:
        lines = [
            f"{self.axis}  [{self.requirement}]  {self.status.value}",
            f"  {self.title}",
            f"  {self.headline}",
        ]
        if self.n:
            lines.append(f"  n = {self.n}   provenance: {self.provenance or 'unstated'}")
        for key, value in self.metrics.items():
            lines.append(f"    {key:<34} {value}")
        if self.comparable_to:
            lines.append(f"  comparable to: {self.comparable_to}")
        for caveat in self.caveats:
            lines.append(f"  CAVEAT: {caveat}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "title": self.title,
            "requirement": self.requirement,
            "status": self.status.value,
            "headline": self.headline,
            "n": self.n,
            "metrics": self.metrics,
            "provenance": self.provenance,
            "caveats": list(self.caveats),
            "comparable_to": self.comparable_to,
        }


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _corpus(path: Path | str | None) -> MCBCorpus | None:
    candidate = Path(path) if path is not None else DEFAULT_CORPUS
    if not candidate.exists():
        return None
    return load_corpus(candidate)


def _corpus_caveats(corpus: MCBCorpus) -> tuple[str, ...]:
    caveats = tuple(corpus.notes[:2]) if getattr(corpus, "notes", None) else ()
    if corpus.provenance is not Provenance.EMPIRICAL:
        caveats = (
            f"corpus provenance is {corpus.provenance.value} -- this is not a field measurement",
            *caveats,
        )
    return caveats


# ================================================================================================
# FR-9.1 -- grounding, ExtractBench's metric, called rather than re-implemented
# ================================================================================================


def axis_grounding(*, corpus: Path | str | None = None, **_: Any) -> AxisResult:
    loaded = _corpus(corpus)
    if loaded is None or not loaded.records:
        return AxisResult(
            axis="grounding",
            title="Word-level grounding F1 at IoU 0.5 -- ExtractBench's metric, verbatim",
            requirement="FR-9.1",
            status=AxisStatus.NOT_MEASURED,
            headline=(
                "no corpus. Build one with the P3 spike, or pass --corpus; this axis does not "
                "score a synthetic stand-in"
            ),
        )

    records = loaded.records
    word = grounding_f1(records, level=GroundingLevel.WORD, iou_threshold=GROUNDING_IOU_THRESHOLD)
    page = grounding_f1(records, level=GroundingLevel.PAGE)
    value = value_f1(records)
    margin = word.f1 * 100 - EXTRACTBENCH_WORD_GROUNDING_F1

    return AxisResult(
        axis="grounding",
        title="Word-level grounding F1 at IoU 0.5 -- ExtractBench's metric, verbatim",
        requirement="FR-9.1",
        status=AxisStatus.MEASURED,
        headline=(
            f"word-level grounding F1 {_pct(word.f1)} against ExtractBench's published "
            f"{EXTRACTBENCH_WORD_GROUNDING_F1}% -- margin {margin:+.2f}pp"
        ),
        n=len(records),
        metrics={
            "word_grounding_f1": _pct(word.f1),
            "word_grounding_precision": word.precision.render(),
            "word_grounding_recall": word.recall.render(),
            "page_grounding_f1": _pct(page.f1),
            "value_f1": _pct(value.f1),
            "conservative_word_f1": _pct(word.conservative_f1),
            "iou_threshold": GROUNDING_IOU_THRESHOLD,
            "extractbench_word_f1": EXTRACTBENCH_WORD_GROUNDING_F1,
            "extractbench_value_f1": EXTRACTBENCH_VALUE_F1,
            "margin_pp": round(margin, 2),
        },
        provenance=loaded.provenance.value,
        caveats=(
            *_corpus_caveats(loaded),
            "the metric is computed by errata_bench.operating_point.grounding_f1, which is R0's "
            "implementation of the published definition -- this axis does not re-implement it",
        ),
        comparable_to=EXTRACTBENCH_CITATION.strip().splitlines()[0],
    )


# ================================================================================================
# FR-9.2 -- ETIM class assignment
# ================================================================================================


def axis_class_assignment(**_: Any) -> AxisResult:
    from errata_audit import load_etim, load_scope, resolve_class

    etim_dir = REPO_ROOT / "var" / "reference" / "etim" / "extracted"
    labels = REPO_ROOT / "audit" / "src" / "errata_audit" / "demo" / "class-labels.yaml"
    if not etim_dir.exists() or not labels.exists():
        return AxisResult(
            axis="class_assignment",
            title="ETIM class assignment, including the cases that must abstain",
            requirement="FR-9.2",
            status=AxisStatus.NOT_MEASURED,
            headline="no ETIM release present; run scripts/fetch_reference_data.sh",
        )

    import yaml

    document = yaml.safe_load(labels.read_text(encoding="utf-8"))
    cases = document.get("cases", [])
    scope = load_scope()
    model = load_etim(etim_dir, release="10.0", class_ids=scope.as_set)

    labelled = [c for c in cases if c.get("class_id")]
    must_abstain = [c for c in cases if not c.get("class_id")]

    top1 = top5 = 0
    for case in labelled:
        resolution = resolve_class(case["query"], model, scope=scope)
        candidates = [c.class_id for c in resolution.top5]
        if resolution.class_id == case["class_id"]:
            top1 += 1
        if case["class_id"] in candidates:
            top5 += 1

    held = sum(
        1 for case in must_abstain if resolve_class(case["query"], model, scope=scope).abstained
    )

    n = len(labelled)
    interval = wilson(top1, n) if n else None
    return AxisResult(
        axis="class_assignment",
        title="ETIM class assignment, including the cases that must abstain",
        requirement="FR-9.2",
        status=AxisStatus.MEASURED,
        headline=(
            f"top-1 {_pct(top1 / n)} and top-5 {_pct(top5 / n)} on {n} labelled queries; "
            f"{held} of {len(must_abstain)} must-abstain cases held"
        ),
        n=n,
        metrics={
            "top_1": _pct(top1 / n) if n else "n/a",
            "top_5": _pct(top5 / n) if n else "n/a",
            "top_1_95ci": (
                f"[{_pct(interval.lo)}, {_pct(interval.hi)}]" if interval else "n/a"
            ),
            "must_abstain_held": f"{held}/{len(must_abstain)}",
            "classes_in_scope": len(scope.as_set),
        },
        provenance="constructed queries, single-labelled by the implementer",
        caveats=(
            str(document.get("caveat", "")).strip(),
            "a four-way choice against an allow-list is an easy problem; the abstentions and the "
            "wrong answers are the informative rows, not the rate",
        ),
    )


# ================================================================================================
# FR-9.2 -- compound-value normalization
# ================================================================================================


def _is_compound(text: str) -> bool:
    parsed = normalize(text)
    return getattr(parsed, "kind", None) in COMPOUND_KINDS


def axis_compound_values(**_: Any) -> AxisResult:
    cases = [c for c in load_cases() if _is_compound(c.a) or _is_compound(c.b)]
    if not cases:
        return AxisResult(
            axis="compound_values",
            title="Compound-value normalization -- ranges, quantity sets, composed values",
            requirement="FR-9.2",
            status=AxisStatus.NOT_MEASURED,
            headline="no compound cases in the loaded suite",
        )

    report = run_suite(cases)
    passes = len(report.by_outcome(Outcome.PASS))
    false_positives = len(report.by_outcome(Outcome.FALSE_POSITIVE))
    abstentions = len(report.by_outcome(Outcome.UNEXPECTED_ABSTENTION))
    misclassified = len(report.by_outcome(Outcome.MISCLASSIFIED))
    false_negatives = len(report.by_outcome(Outcome.FALSE_NEGATIVE))
    n = len(cases)
    interval = wilson(passes, n)

    resolved = sum(1 for c in cases if not isinstance(normalize(c.a), type(None)))
    return AxisResult(
        axis="compound_values",
        title="Compound-value normalization -- ranges, quantity sets, composed values",
        requirement="FR-9.2",
        status=AxisStatus.MEASURED,
        headline=(
            f"{passes} of {n} compound pairs decided correctly ({_pct(passes / n)}), "
            f"{false_positives} false positive(s), {abstentions} unexpected abstention(s)"
        ),
        n=n,
        metrics={
            "correct": f"{passes}/{n}",
            "correct_95ci": f"[{_pct(interval.lo)}, {_pct(interval.hi)}]",
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "misclassified": misclassified,
            "unexpected_abstentions": abstentions,
            "parsed_side_a": resolved,
        },
        provenance="the R0 equivalence suite, filtered to pairs whose parsed kind is compound",
        caveats=(
            f"n = {n}. Twenty-odd cases decide nothing on their own -- this is a regression "
            "signal with an interval, not a published rate.",
            "the labels are the equivalence suite's, and carry its known weakness: single-labelled "
            "by the author of the comparator (FR-0.1).",
        ),
    )


# ================================================================================================
# FR-9.2 -- cross-standard mapping
# ================================================================================================

#: UNSPSC commodity codes inside the bridge's own scope (class 39121600, circuit protection) that
#: the bridge deliberately does not map. A crosswalk is judged on these as much as on its hits:
#: the failure mode of every published mapping table is the row that guesses.
OUT_OF_BRIDGE_CODES: tuple[tuple[str, str], ...] = (
    ("39121602", "Magnetic circuit breakers"),
    ("39121615", "Air circuit breakers"),
    ("39121633", "Circuit interruptor"),
)


def axis_crosswalk(**_: Any) -> AxisResult:
    from .bridge import load_bridge

    try:
        bridge, model = load_bridge()
    except (FileNotFoundError, OSError) as exc:
        return AxisResult(
            axis="crosswalk",
            title="Cross-standard mapping -- UNSPSC to ETIM attributes, and refusal to map",
            requirement="FR-9.2 / FR-9.7",
            status=AxisStatus.NOT_MEASURED,
            headline=f"the bridge could not be loaded: {exc}",
        )

    mapped = sorted({m.unspsc for m in bridge.mappings if m.unspsc and m.carries_attributes})
    delivered = {code: len(bridge.attributes_for(code, model)) for code in mapped}
    empty_deliveries = [code for code, count in delivered.items() if count == 0]

    abstained = [
        code for code, _ in OUT_OF_BRIDGE_CODES if not bridge.attributes_for(code, model)
    ]
    refusals = bridge.refusals

    status = AxisStatus.MEASURED
    return AxisResult(
        axis="crosswalk",
        title="Cross-standard mapping -- UNSPSC to ETIM attributes, and refusal to map",
        requirement="FR-9.2 / FR-9.7",
        status=status,
        headline=(
            f"{len(mapped)} UNSPSC code(s) given an attribute layer "
            f"({min(delivered.values(), default=0)}-{max(delivered.values(), default=0)} ETIM "
            f"features each); {len(abstained)}/{len(OUT_OF_BRIDGE_CODES)} in-scope but unmapped "
            f"codes correctly yield nothing; {len(refusals)} recorded refusals"
        ),
        n=len(bridge.mappings),
        metrics={
            "codes_with_attribute_layer": len(mapped),
            "features_delivered": delivered,
            "codes_delivering_nothing": empty_deliveries or "none",
            "unmapped_codes_abstained": f"{len(abstained)}/{len(OUT_OF_BRIDGE_CODES)}",
            "declined_mappings": len([m for m in refusals if m.relation == "declined"]),
            "no_match_recorded": len([m for m in refusals if m.relation == "no_match"]),
            "etim_release": bridge.etim_release,
        },
        provenance="judged mappings, validated against both published dictionaries",
        caveats=(
            "every mapping is a single judgement by the bridge's author (see its decided_by). "
            "Validation proves the codes and titles exist; it does not prove the judgement is "
            "right, and a second domain judge has not read them.",
            "an axis that scored the bridge against itself would measure nothing: what is scored "
            "here is delivery on mapped codes and silence on unmapped ones.",
        ),
    )


# ================================================================================================
# FR-9.2 -- supersession
# ================================================================================================


def axis_supersession(**_: Any) -> AxisResult:
    from errata_scale.chains import ChainIntegrityError, claim_chains

    cases = _supersession_cases()
    correct = 0
    detail: dict[str, str] = {}
    for name, events, expected in cases:
        try:
            chains = claim_chains(_FixtureLedger(events))
        except ChainIntegrityError:
            outcome = "raised"
        else:
            chain = next(iter(chains.values()), None)
            outcome = chain.head.value_raw if chain and chain.head else "no-head"
        detail[name] = outcome
        if outcome == expected:
            correct += 1

    n = len(cases)
    return AxisResult(
        axis="supersession",
        title="Supersession -- which claim is current, and what a broken history does",
        requirement="FR-9.2",
        status=AxisStatus.MEASURED,
        headline=(
            f"{correct} of {n} supersession cases resolved as required "
            f"({_pct(correct / n)}); a forked, cyclic or orphaned history must raise, not resolve"
        ),
        n=n,
        metrics={"outcomes": detail},
        provenance="constructed ledger fixtures",
        caveats=(
            "CONSTRUCTED. These are ledgers written to exercise each shape of broken history, "
            "not histories observed in a customer's data. What they measure is that the chain "
            "reconstructor refuses the ambiguous ones -- a property of the code, which is what a "
            "constructed fixture can honestly test.",
        ),
    )


class _FixtureLedger:
    """The one method :func:`claim_chains` uses, over real :class:`LedgerEvent` objects.

    Not a mock of the ledger's reading logic -- the events are the same dict subclass the file
    format produces, so the chain reconstructor under test is doing exactly what it does in R2.
    """

    def __init__(self, events: Sequence[LedgerEvent]) -> None:
        self._events = list(events)

    def of_kind(self, kind: str) -> tuple[LedgerEvent, ...]:
        return tuple(e for e in self._events if e.kind == kind)


def _claim(claim_id: str, value: str, supersedes: str | None, at: str) -> LedgerEvent:
    return LedgerEvent({
        "kind": "claim",
        "event_id": f"ev-{claim_id}",
        "payload": {
            "claim_id": claim_id,
            "supersedes": supersedes,
            "sku_id": "SKU-1",
            "attribute_uri": "etim:EF000227",
            "value_raw": value,
            "asserter_kind": "extractor",
            "asserted_at": at,
        },
    })


def _supersession_cases() -> tuple[tuple[str, list[LedgerEvent], str], ...]:
    linear = [
        _claim("c1", "16 A", None, "2026-08-01T00:00:00Z"),
        _claim("c2", "20 A", "c1", "2026-08-02T00:00:00Z"),
        _claim("c3", "25 A", "c2", "2026-08-03T00:00:00Z"),
    ]
    out_of_order = [linear[2], linear[0], linear[1]]
    forked = [
        _claim("f1", "16 A", None, "2026-08-01T00:00:00Z"),
        _claim("f2", "20 A", "f1", "2026-08-02T00:00:00Z"),
        _claim("f3", "25 A", "f1", "2026-08-02T00:00:00Z"),
    ]
    cyclic = [
        _claim("y1", "16 A", "y2", "2026-08-01T00:00:00Z"),
        _claim("y2", "20 A", "y1", "2026-08-02T00:00:00Z"),
    ]
    single = [_claim("s1", "16 A", None, "2026-08-01T00:00:00Z")]
    return (
        ("linear chain, head is the last claim", linear, "25 A"),
        ("same chain shuffled -- order comes from supersedes, not file order", out_of_order, "25 A"),
        ("forked history must raise", forked, "raised"),
        ("cyclic history must raise", cyclic, "raised"),
        ("a single claim is its own head", single, "16 A"),
    )


# ================================================================================================
# FR-9.2 -- calibrated abstention
# ================================================================================================


def axis_abstention(*, corpus: Path | str | None = None, **_: Any) -> AxisResult:
    loaded = _corpus(corpus)
    if loaded is None or not loaded.records:
        return AxisResult(
            axis="abstention",
            title="Calibrated abstention -- risk-coverage, AURC, selective accuracy",
            requirement="FR-9.2",
            status=AxisStatus.NOT_MEASURED,
            headline="no corpus; this axis needs per-record confidences and outcomes",
        )

    records = loaded.records
    triples = tuple(
        (r.attribute_id, r.confidence, r.grounded_correct(GroundingLevel.WORD))
        for r in records
    )
    curve = risk_coverage_curve(triples)
    area = aurc(curve)
    selective = {
        f"selective_accuracy_at_{int(c * 100)}pct": selective_accuracy_at_coverage(
            triples, c
        ).render()
        for c in (0.20, 0.40, 0.60)
    }
    risk_at_20 = next((p.risk for p in curve if p.coverage >= 0.20), None)

    return AxisResult(
        axis="abstention",
        title="Calibrated abstention -- risk-coverage, AURC, selective accuracy",
        requirement="FR-9.2",
        status=AxisStatus.MEASURED,
        headline=(
            f"AURC {area:.4f}; risk at 20% coverage "
            f"{_pct(risk_at_20) if risk_at_20 is not None else 'n/a'}"
        ),
        n=len(records),
        metrics={"aurc": round(area, 4), "curve_points": len(curve), **selective},
        provenance=loaded.provenance.value,
        caveats=(
            *_corpus_caveats(loaded),
            "the confidence being ranked is a raw evidence-quality score, not a calibrated "
            "probability: FR-6.1's calibration set does not exist because calibration needs "
            "reviewer decisions and none have been made.",
        ),
    )


# ================================================================================================
# the registry
# ================================================================================================

AXES: dict[str, Callable[..., AxisResult]] = {
    "grounding": axis_grounding,
    "class_assignment": axis_class_assignment,
    "compound_values": axis_compound_values,
    "crosswalk": axis_crosswalk,
    "supersession": axis_supersession,
    "abstention": axis_abstention,
}


def axis_ids() -> tuple[str, ...]:
    return tuple(AXES)


def run_axis(axis: str, **context: Any) -> AxisResult:
    if axis not in AXES:
        raise KeyError(f"unknown axis {axis!r}; known axes are {', '.join(axis_ids())}")
    return AXES[axis](**context)


def run_all(**context: Any) -> tuple[AxisResult, ...]:
    """Every axis, in registry order. Each one independently runnable is the requirement; running
    them together is a convenience, and nothing here shares state between them."""
    return tuple(run_axis(axis, **context) for axis in axis_ids())
