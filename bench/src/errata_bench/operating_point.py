"""R0 kill test 2 -- the operating-point measurement (FR-0.3).

Section 0.3 of phase4-full-spec.md names the load-bearing unproven assumption everything
downstream of the product rests on:

    that auditing has a materially better precision/coverage operating point than extraction
    does at the same grounding quality.

Two mechanisms are proposed and neither has been measured:

    1. An audit runs at low coverage by choice -- it only has to be right about the
       disagreements it raises, and may abstain on everything else.
    2. An audit starts from a candidate value -- confirming a known value at a known location is
       span *confirmation*, an easier retrieval problem than open-field span discovery.

FR-0.3 (prd-errata.md) turns that into a testable acceptance criterion: 200 hand-labelled MCB
records; disagreement-detection precision and word-level grounding F1 at IoU 0.5, at 20/40/60%
coverage; a risk-coverage curve; compared explicitly against ExtractBench's published 46.43
word-level / 95.6 value F1 at full coverage.

Section 6.2 makes the reuse of ExtractBench's grounding metric a *deliberate* choice, not a
technical afterthought: "Reuse ExtractBench's grounding metric verbatim ... You do not want a
metric of your own that nobody can check you against." :func:`grounding_f1` in this module is
that metric, implemented to match, including the exact ">=" at the IoU 0.5 boundary.

WHAT THIS MODULE IS NOT
------------------------
It is not a measurement. There is no labelled MCB corpus in this repository and no grounding
pipeline (FR-1.2 .. FR-1.5) that could produce a predicted box for a real document. This module is
the ruler: the metric definitions, the corpus record format, and the report/verdict machinery FR-
0.3 needs the day a real corpus and a real pipeline exist. :func:`synthetic_corpus` builds a small,
deterministic, index-driven fixture purely so the metric code paths can be exercised end to end;
every report built from it carries :data:`SYNTHETIC_BANNER` and :func:`asymmetry_verdict` is pinned
to :attr:`AsymmetryVerdict.NOT_MEASURED` no matter how the numbers land -- there is no code path
through which a synthetic corpus can produce ``ASYMMETRY_CONFIRMED`` or ``ASYMMETRY_NOT_CONFIRMED``.

Load a real corpus with :func:`load_corpus` and the verdict becomes live.

DETERMINISM
------------
No model call, no network call, no RNG. Same inputs, same bytes out. :func:`load_corpus` reads a
local file; nothing here fetches anything.
"""

from __future__ import annotations

import csv
import enum
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

from .stats import Proportion, wilson

__all__ = [
    "DEFAULT_COVERAGE_POINTS",
    "EXTRACTBENCH_CITATION",
    "EXTRACTBENCH_COST_CENTS_PER_PAGE",
    "EXTRACTBENCH_PAGE_GROUNDING_F1",
    "EXTRACTBENCH_SYSTEMS_AT_ZERO_GROUNDING",
    "EXTRACTBENCH_SYSTEMS_EVALUATED",
    "EXTRACTBENCH_VALUE_F1",
    "EXTRACTBENCH_WORD_GROUNDING_F1",
    "EXTRACTBENCH_WORD_GROUNDING_F1_REDUCTO",
    "EXTRACTBENCH_WORD_GROUNDING_F1_SECOND",
    "GATE_EXIT_CODES",
    "GROUNDING_IOU_THRESHOLD",
    "MIN_RECORDS_FOR_VERDICT",
    "SYNTHETIC_BANNER",
    "TARGET_CORPUS_SIZE",
    "AsymmetryVerdict",
    "BoundingBox",
    "CoverageRow",
    "GroundingLevel",
    "MCBCorpus",
    "MCBRecord",
    "OperatingPointReport",
    "Provenance",
    "RateResult",
    "RiskCoveragePoint",
    "asymmetry_verdict",
    "aurc",
    "grounding_f1",
    "load_corpus",
    "operating_point_report",
    "precision_at_coverage",
    "render_report",
    "report_as_dict",
    "risk_coverage_curve",
    "selective_accuracy_at_coverage",
    "synthetic_corpus",
    "value_f1",
]


# ================================================================================================
# ExtractBench baseline -- cited verbatim, never re-derived
# ================================================================================================

# VERIFIED AGAINST THE PAPER, 2026-08-19 (P3 task 3.10).
#
# HANDOFF §7 listed the grounding table as the one carried-forward claim never re-checked: "the
# arXiv PDF is 5.9MB of compressed streams and no PDF text library was available locally". One is
# available now. The paper was fetched, hash-registered in data/reference/manifest.json, and read.
#
# Every figure below is confirmed -- and FOUR OF THEM CARRIED A DECIMAL THE PAPER DOES NOT
# PUBLISH. Table 3 (page 9) prints one decimal place:
#
#     System            Word-level F1   Page-level F1
#     LE Agentic Plus       46.4            84.9
#     LE Agentic            44.1            66.1
#     Reducto Deep          43.3            71.7
#     All other systems      0.0             0.0
#
# The repo carried 46.43 / 44.14 / 43.30 / 84.92. The substance was right and the precision was
# invented: 46.43 is not a number this paper contains, and anyone reading it would reasonably
# believe two decimals had been published. That is the §7 signature at the second decimal place --
# disciplined about the fact, careless about the digit nobody was expected to check. Corrected to
# what Table 3 actually prints.
#
# The correction does not move any conclusion: 46.34% measured against 46.4% is the same dead heat
# it was against 46.43%.

EXTRACTBENCH_CITATION = (
    "ExtractBench (arXiv 2607.29677), Table 3 p.9 and §3.2 p.7. Read from the paper 2026-08-19; "
    "PDF sha256 533891e9...e982d, registered in data/reference/manifest.json."
)

EXTRACTBENCH_WORD_GROUNDING_F1 = 46.4
"""Best word-level grounding F1, percent -- LlamaExtract Agentic Plus, at full (100%) coverage.

Table 3, page 9, verified 2026-08-19. A field counts as grounded-correct only when its value is
accepted AND its predicted box overlaps an accepted evidence box at IoU >= 0.5 -- the table's own
caption states exactly that. The paper's conclusion (page 11) restates it: "word-level grounding
F1 remains at 46.4% even for specialized systems that return boxes"."""

EXTRACTBENCH_WORD_GROUNDING_F1_SECOND = 44.1
"""Second-best published word-level grounding F1, percent -- LE Agentic. Table 3, p.9."""

EXTRACTBENCH_WORD_GROUNDING_F1_REDUCTO = 43.3
"""Reducto Deep Extract's published word-level grounding F1, percent. Table 3, p.9."""

EXTRACTBENCH_SYSTEMS_AT_ZERO_GROUNDING = 8
"""Systems scoring 0.0 on grounding -- they return no evidence at all.

Verified by arithmetic on Table 3: six systems are named individually and the final row reads
"All other systems 0.0", against :data:`EXTRACTBENCH_SYSTEMS_EVALUATED` = 14 evaluated. 14 - 6 = 8.
The paper states the cause on page 3: "commercial VLMs and coding agents do not return word-level
boxes"."""

EXTRACTBENCH_SYSTEMS_EVALUATED = 14
"""Total systems evaluated. Paper §1, p.3: "We compare 14 systems spanning commercial VLMs, OSS
pipelines, coding agents, and specialized APIs"."""

EXTRACTBENCH_PAGE_GROUNDING_F1 = 84.9
"""Best published page-level grounding F1, percent -- citing the correct page instead of an IoU
test. Table 3, p.9, verified 2026-08-19."""

EXTRACTBENCH_VALUE_F1 = 95.6
"""Best published value F1, percent -- value correctness alone, ignoring grounding. LlamaExtract
Agentic Plus, at full coverage. See :data:`EXTRACTBENCH_CITATION`."""

EXTRACTBENCH_COST_CENTS_PER_PAGE = 8.1
"""Cost, in US cents per page, of the system posting :data:`EXTRACTBENCH_VALUE_F1`. See
:data:`EXTRACTBENCH_CITATION`."""

GROUNDING_IOU_THRESHOLD = 0.5
"""ExtractBench's stated word-level grounding threshold (phase4-full-spec.md §0.3, V7): a
predicted box counts only when it overlaps an accepted evidence box at IoU >= 0.5. The comparison
is ``>=``, not ``>`` -- pinned exactly here because an off-by-this error would silently invalidate
every published comparison built on this module. See :class:`BoundingBox` for the boundary tests.
"""


# ================================================================================================
# Provenance -- decides whether a verdict may be issued
# ================================================================================================


class Provenance(str, enum.Enum):
    """Where an MCB corpus came from. This decides whether :func:`asymmetry_verdict` may fire."""

    EMPIRICAL = "empirical"
    """Real hand-labelled records from public manufacturer datasheets -- FR-0.3 asks for 200. The
    verdict may issue ASYMMETRY_CONFIRMED or ASYMMETRY_NOT_CONFIRMED."""

    SYNTHETIC = "synthetic"
    """A generated fixture built to exercise the metric code. :func:`asymmetry_verdict` reports
    NOT_MEASURED regardless of how the numbers land -- there is no path around this."""


# ================================================================================================
# Bounding boxes and IoU
# ================================================================================================


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """An axis-aligned box in page coordinates.

    Units are whatever the caller's layout map uses -- this module does not care, as long as gold
    and predicted boxes for the same record share units. ``(x0, y0)`` is the top-left corner,
    ``(x1, y1)`` the bottom-right; ``x1 >= x0`` and ``y1 >= y0`` are required, but a zero-width or
    zero-height box (a point or a line) is allowed rather than rejected -- some layout extractors
    legitimately emit degenerate boxes for single-character tokens.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError(
                f"malformed box ({self.x0}, {self.y0}, {self.x1}, {self.y1}): "
                "requires x1 >= x0 and y1 >= y0"
            )

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def intersection_area(self, other: BoundingBox) -> float:
        ix0 = max(self.x0, other.x0)
        iy0 = max(self.y0, other.y0)
        ix1 = min(self.x1, other.x1)
        iy1 = min(self.y1, other.y1)
        width = max(0.0, ix1 - ix0)
        height = max(0.0, iy1 - iy0)
        return width * height

    def iou(self, other: BoundingBox) -> float:
        """Intersection-over-union, the standard definition.

        ``union = area(self) + area(other) - intersection``. When the union is zero -- both boxes
        are degenerate (zero area) -- the ratio is 0/0 in the strict definition. This returns
        ``0.0`` rather than raising or returning ``1.0``: a box with no area cannot be said to
        genuinely support a claim, so a zero-area box never counts as a match, not even against an
        identical zero-area box. That is a deliberate, documented choice, not an accident of the
        arithmetic -- see the boundary tests in test_operating_point.py.
        """
        intersection = self.intersection_area(other)
        union = self.area + other.area - intersection
        if union <= 0.0:
            return 0.0
        return intersection / union


# ================================================================================================
# Grounding levels
# ================================================================================================


class GroundingLevel(str, enum.Enum):
    """Word-level vs page-level grounding, ExtractBench's two published axes (V7)."""

    WORD = "word"
    """A predicted box must overlap an accepted gold evidence box at IoU >= 0.5. The harder axis --
    ExtractBench's best system clears only :data:`EXTRACTBENCH_WORD_GROUNDING_F1` percent here."""

    PAGE = "page"
    """The predicted page number must equal the gold page -- no IoU test. The easier axis -- best
    published score is :data:`EXTRACTBENCH_PAGE_GROUNDING_F1` percent."""


# ================================================================================================
# The corpus record -- the FR-0.3 input format
# ================================================================================================


@dataclass(frozen=True, slots=True)
class MCBRecord:
    """One hand-labelled field: what is true, and what the audit predicted.

    This is the FR-0.3 corpus record: "200 hand-labelled MCB records from public datasheets"
    (prd-errata.md), one record per audited attribute. Written so that the day a real labelled
    corpus exists, every function in this module runs unchanged against it.
    """

    attribute_id: str
    """Unique id for this field observation, e.g. ``schneider-lc1d09-rated_current``."""

    gold_value: str
    """The value a competent domain reviewer would accept, read from the datasheet."""

    gold_evidence_boxes: tuple[BoundingBox, ...]
    """Boxes on the gold page that support :attr:`gold_value`. A field's evidence may legitimately
    span more than one box -- e.g. a value and its unit on separate lines of a table cell -- so this
    is a list, and a predicted box grounds the field if it overlaps ANY box in it at IoU >= 0.5."""

    gold_page: int
    """The page (0- or 1-indexed, consistently within a corpus) the evidence lives on."""

    predicted_value: str | None
    """What the audit predicted. ``None`` means the audit abstained on this field -- distinct from
    predicting an empty string, which is a (almost certainly wrong) value prediction."""

    predicted_box: BoundingBox | None
    """The audit's word-level evidence box, or ``None`` if it did not cite one."""

    predicted_page: int | None
    """The audit's page-level citation, or ``None`` if it did not cite one."""

    confidence: float
    """The audit's confidence in this prediction, in ``[0, 1]``. Drives the risk-coverage sweep --
    higher confidence is acted on first."""

    is_disagreement_predicted: bool
    """Whether the audit raised this field as a catalog/datasheet disagreement."""

    is_disagreement_actual: bool
    """Whether a competent domain reviewer would agree a genuine disagreement exists here."""

    value_equivalent: bool | None = None
    """Whether the corpus has ALREADY resolved ``predicted_value`` against ``gold_value`` through
    the comparator, and what it decided. ``None`` means it has not, and :attr:`value_accepted`
    falls back to exact string match.

    This field is what :attr:`value_accepted`'s docstring has always asked for. Exact match is a
    fine default for a corpus whose two sides share a value convention, and a silently wrong
    instrument for one whose sides do not. R1's extractor composes the unit its column header
    states -- ``16`` under *Rated current I n A* is emitted as ``16 A``, because FR-4.3 says a bare
    number in a cell is not a fact -- while the published gold set records the cell text exactly as
    printed. Scored on exact match the two disagree on 859 of 1,426 records and R1 reports 39.76%,
    a number that measures a punctuation convention and nothing else.

    Deliberately three-valued rather than defaulted to ``False``. A corpus that has not run the
    comparator must not be able to claim it did, and an absent judgment is a different statement
    from a negative one -- the same distinction FR-3.3 draws between an abstention and a value.

    Nothing about the published gate-2 numbers moves: no existing corpus file carries this key, so
    every one of them still resolves through exact match.
    """

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"{self.attribute_id}: confidence must be in [0, 1], got {self.confidence}"
            )
        if self.gold_page < 0:
            raise ValueError(f"{self.attribute_id}: gold_page must be >= 0, got {self.gold_page}")
        if self.predicted_page is not None and self.predicted_page < 0:
            raise ValueError(
                f"{self.attribute_id}: predicted_page must be >= 0, got {self.predicted_page}"
            )

    @property
    def value_accepted(self) -> bool:
        """Does the predicted value match gold.

        Deliberately simple: exact match after stripping surrounding whitespace. This module is
        not the comparator -- FR-0.1/FR-0.2 (equivalence.py) already own semantic-equivalence
        judgment ("10mm" == "10 mm" == "0.010m"), and re-implementing a second, looser notion of
        "accepted" here would let this gate's numbers drift from that one for reasons that have
        nothing to do with grounding. A real FR-0.3 corpus should have its ``predicted_value`` /
        ``gold_value`` pair already resolved through the same comparator equivalence.py measures,
        so that "accepted" means the same thing everywhere in this repository.

        :attr:`value_equivalent` is how a corpus does exactly that. When it is set, this property
        returns it -- the comparator's judgment, made by the component that owns equivalence,
        rather than a second and looser notion of "accepted" reimplemented here. An abstention is
        still never accepted: there is no value to have been right about.
        """
        if self.predicted_value is None:
            return False
        if self.value_equivalent is not None:
            return self.value_equivalent
        return self.predicted_value.strip() == self.gold_value.strip()

    def grounded(
        self, level: GroundingLevel, iou_threshold: float = GROUNDING_IOU_THRESHOLD
    ) -> bool:
        """Is the prediction grounded at ``level`` -- independent of whether the value is right.

        Word-level: ``False`` whenever there is no predicted box or no gold evidence at all (an
        empty gold-evidence list can never be matched -- there is nothing to overlap, and this
        resolves to "not grounded" rather than raising, since ``any(())`` is simply ``False``: no
        division, no special case needed). Otherwise ``True`` iff the predicted box overlaps *any*
        box in :attr:`MCBRecord.gold_evidence_boxes` at IoU >= ``iou_threshold``.

        Page-level: ``True`` iff a page was predicted and it equals :attr:`MCBRecord.gold_page`.
        """
        if level is GroundingLevel.WORD:
            if self.predicted_box is None or not self.gold_evidence_boxes:
                return False
            return any(
                self.predicted_box.iou(gold_box) >= iou_threshold
                for gold_box in self.gold_evidence_boxes
            )
        if self.predicted_page is None:
            return False
        return self.predicted_page == self.gold_page

    def grounded_correct(
        self, level: GroundingLevel, iou_threshold: float = GROUNDING_IOU_THRESHOLD
    ) -> bool:
        """ExtractBench's grounded-correct condition, verbatim: value accepted AND grounded."""
        return self.value_accepted and self.grounded(level, iou_threshold)


@dataclass(frozen=True, slots=True)
class MCBCorpus:
    """A set of MCB records, plus the provenance that decides what may be claimed from it."""

    records: tuple[MCBRecord, ...]
    name: str = "unnamed"
    provenance: Provenance = Provenance.EMPIRICAL
    source: str = ""
    """Where this came from -- a file, an export, a generator and its parameters."""

    notes: tuple[str, ...] = ()
    """Assumptions a reader must see before quoting anything computed from this corpus."""

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for record in self.records:
            if record.attribute_id in seen:
                raise ValueError(f"duplicate attribute_id {record.attribute_id!r}")
            seen.add(record.attribute_id)

    def __len__(self) -> int:
        return len(self.records)

    @property
    def size(self) -> int:
        return len(self.records)

    @property
    def is_synthetic(self) -> bool:
        return self.provenance is Provenance.SYNTHETIC


TARGET_CORPUS_SIZE = 200
"""FR-0.3: "200 hand-labelled MCB records from public datasheets" (prd-errata.md)."""


# ------------------------------------------------------------------------------------------------
# Loading a real corpus
# ------------------------------------------------------------------------------------------------


def _resolve_provenance(
    declared: str | None, override: Provenance | None
) -> tuple[Provenance, tuple[str, ...]]:
    if override is not None:
        return override, ()
    if declared:
        return Provenance(declared), ()
    return Provenance.EMPIRICAL, (
        "the corpus file did not declare a provenance; it is being read as empirical because an "
        "operator pointed the harness at it. If it was generated, say so in the file.",
    )


def _box_from_value(value: Any) -> BoundingBox | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if len(value) != 4:
            raise ValueError(f"box must have 4 elements [x0, y0, x1, y1], got {value!r}")
        x0, y0, x1, y1 = value
        return BoundingBox(float(x0), float(y0), float(x1), float(y1))
    return BoundingBox(
        x0=float(value["x0"]),
        y0=float(value["y0"]),
        x1=float(value["x1"]),
        y1=float(value["y1"]),
    )


def _boxes_from_value(value: Any) -> tuple[BoundingBox, ...]:
    if not value:
        return ()
    return tuple(_box_from_value(v) for v in value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _optional_bool(value: Any) -> bool | None:
    """``None`` stays ``None``. Absence is not ``False`` -- see ``MCBRecord.value_equivalent``."""
    return None if value is None else bool(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None or value == "" else int(value)


def _record_from_mapping(row: dict[str, Any]) -> MCBRecord:
    return MCBRecord(
        attribute_id=str(row["attribute_id"]),
        gold_value=str(row["gold_value"]),
        gold_evidence_boxes=_boxes_from_value(row.get("gold_evidence_boxes")),
        gold_page=int(row["gold_page"]),
        predicted_value=_optional_str(row.get("predicted_value")),
        predicted_box=_box_from_value(row.get("predicted_box")),
        predicted_page=_optional_int(row.get("predicted_page")),
        confidence=float(row["confidence"]),
        is_disagreement_predicted=bool(row.get("is_disagreement_predicted", False)),
        is_disagreement_actual=bool(row.get("is_disagreement_actual", False)),
        value_equivalent=_optional_bool(row.get("value_equivalent")),
    )


def load_corpus(
    path: str | Path,
    *,
    name: str | None = None,
    provenance: Provenance | None = None,
) -> MCBCorpus:
    """Load an MCB corpus from CSV/TSV, YAML or JSON.

    YAML/JSON::

        name: mcb-pilot-200
        provenance: empirical
        source: hand-labelled from public Schneider/ABB/Siemens/Legrand/Eaton/Rockwell datasheets
        notes:
          - dual-labelled where the row/column header attribution was ambiguous
        records:
          - attribute_id: schneider-lc1d09-rated_current
            gold_value: "16 A"
            gold_page: 3
            gold_evidence_boxes:
              - {x0: 100, y0: 200, x1: 140, y1: 215}
            predicted_value: "16 A"
            predicted_page: 3
            predicted_box: {x0: 101, y0: 199, x1: 141, y1: 216}
            confidence: 0.93
            is_disagreement_predicted: false
            is_disagreement_actual: false

    A box may also be given as a 4-element list ``[x0, y0, x1, y1]``.

    CSV/TSV: a header row naming ``attribute_id, gold_value, gold_page, predicted_value,
    predicted_page, confidence`` at minimum. ``gold_evidence_boxes`` and ``predicted_box`` encode a
    box as ``x0:y0:x1:y1``; multiple gold evidence boxes are separated by ``|``. Booleans accept
    true/false/yes/no/1/0 (case-insensitive; blank means false).

    Provenance defaults to EMPIRICAL when the file does not declare one -- an operator who points
    this at a file is asserting it is real -- but the report says out loud that the file made no
    claim, so nobody can launder a generated file into a verdict by omission.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return _load_csv(path, name=name, provenance=provenance)
    if suffix in {".yaml", ".yml"}:
        document: dict[str, Any] = yaml.safe_load(path.read_text("utf-8")) or {}
    elif suffix == ".json":
        document = json.loads(path.read_text("utf-8")) or {}
    else:
        raise ValueError(
            f"unsupported corpus file {path.name!r}: expected .csv, .tsv, .yaml, .yml or .json"
        )

    rows = document.get("records") or document.get("entries") or []
    resolved, notes = _resolve_provenance(document.get("provenance"), provenance)
    records = tuple(_record_from_mapping(row) for row in rows)
    if not records:
        raise ValueError(f"{path.name}: no records found")
    return MCBCorpus(
        records=records,
        name=name or str(document.get("name") or path.stem),
        provenance=resolved,
        source=str(document.get("source") or f"file: {path}"),
        notes=tuple(str(n) for n in document.get("notes", ())) + notes,
    )


_TRUE_STRINGS = {"true", "t", "yes", "y", "1"}
_FALSE_STRINGS = {"false", "f", "no", "n", "0", ""}


def _parse_bool(raw: str) -> bool:
    key = raw.strip().lower()
    if key in _TRUE_STRINGS:
        return True
    if key in _FALSE_STRINGS:
        return False
    raise ValueError(f"cannot parse boolean from {raw!r}")


def _parse_boxes_csv(raw: str) -> tuple[BoundingBox, ...]:
    raw = raw.strip()
    if not raw:
        return ()
    boxes: list[BoundingBox] = []
    for chunk in raw.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        if len(parts) != 4:
            raise ValueError(f"malformed box {chunk!r} in {raw!r}: expected 'x0:y0:x1:y1'")
        x0, y0, x1, y1 = (float(p) for p in parts)
        boxes.append(BoundingBox(x0, y0, x1, y1))
    return tuple(boxes)


def _parse_box_csv(raw: str) -> BoundingBox | None:
    boxes = _parse_boxes_csv(raw)
    if not boxes:
        return None
    if len(boxes) > 1:
        raise ValueError(f"expected exactly one predicted box, got {len(boxes)} in {raw!r}")
    return boxes[0]


def _record_from_csv_row(row: dict[str, str]) -> MCBRecord:
    predicted_value = (row.get("predicted_value") or "").strip()
    predicted_page_raw = (row.get("predicted_page") or "").strip()
    return MCBRecord(
        attribute_id=row["attribute_id"].strip(),
        gold_value=row["gold_value"].strip(),
        gold_evidence_boxes=_parse_boxes_csv(row.get("gold_evidence_boxes", "")),
        gold_page=int(row["gold_page"].strip()),
        predicted_value=predicted_value or None,
        predicted_box=_parse_box_csv(row.get("predicted_box", "")),
        predicted_page=int(predicted_page_raw) if predicted_page_raw else None,
        confidence=float(row["confidence"].strip()),
        is_disagreement_predicted=_parse_bool(row.get("is_disagreement_predicted", "false")),
        is_disagreement_actual=_parse_bool(row.get("is_disagreement_actual", "false")),
    )


def _load_csv(path: Path, *, name: str | None, provenance: Provenance | None) -> MCBCorpus:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"{path.name}: empty file, expected a header row")
        rows = [row for row in reader if any((v or "").strip() for v in row.values())]
    if not rows:
        raise ValueError(f"{path.name}: header parsed but no rows found")
    records = tuple(_record_from_csv_row(row) for row in rows)
    resolved, notes = _resolve_provenance(None, provenance)
    return MCBCorpus(
        records=records, name=name or path.stem, provenance=resolved,
        source=f"file: {path}", notes=notes,
    )


# ------------------------------------------------------------------------------------------------
# The synthetic stand-in
# ------------------------------------------------------------------------------------------------


SYNTHETIC_BANNER = """
================================================================================================
  SYNTHETIC MCB CORPUS -- STRUCTURAL RESULT, NOT AN EMPIRICAL ONE
------------------------------------------------------------------------------------------------
  No manufacturer datasheet was read and no grounding pipeline (FR-1.2 .. FR-1.5) produced these
  boxes. This corpus is a deterministic, index-driven fixture built only to exercise the metric
  code paths end to end.

  FR-0.3 asks for 200 hand-labelled MCB records from public datasheets (prd-errata.md). Until that
  corpus exists and is loaded with load_corpus(), the operating-point comparison stays NOT
  MEASURED, no matter how the numbers below look.
================================================================================================
""".strip()


def synthetic_corpus(*, n: int = 40, name: str = "synthetic-operating-point") -> MCBCorpus:
    """Build an explicitly-synthetic MCB corpus for exercising the metric machinery.

    **This function invents nothing about any real audit.** Every field follows a deterministic,
    index-driven pattern chosen to walk every code path this module has (grounded/ungrounded,
    accepted/rejected values, an abstention, raised/missed disagreements, confidence spanning the
    full range) -- not to look like a plausible or favourable result. Deterministic: no RNG, no
    seed, identical output for identical ``n``.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    records: list[MCBRecord] = []
    gold_box = BoundingBox(0.0, 0.0, 10.0, 10.0)
    off_box = BoundingBox(50.0, 50.0, 60.0, 60.0)  # disjoint from gold_box -- IoU 0.0
    for i in range(n):
        confidence = 1.0 - (i / max(1, n - 1)) * 0.5  # descends from 1.0 to 0.5
        grounded = i % 2 == 0
        value_ok = i % 3 != 0
        abstained = i % 11 == 0  # rare abstention, exercises the recall-without-precision-hit path
        gold_value = "16 A"
        record = MCBRecord(
            attribute_id=f"SYN-{i:04d}",
            gold_value=gold_value,
            gold_evidence_boxes=(gold_box,),
            gold_page=1,
            predicted_value=None if abstained else (gold_value if value_ok else "20 A"),
            predicted_box=None if abstained else (gold_box if grounded else off_box),
            predicted_page=None if abstained else (1 if grounded else 2),
            confidence=confidence,
            is_disagreement_predicted=(i % 4 == 0),
            is_disagreement_actual=(i % 5 == 0),
        )
        records.append(record)
    return MCBCorpus(
        records=tuple(records),
        name=name,
        provenance=Provenance.SYNTHETIC,
        source=f"synthetic_corpus(n={n})",
        notes=(
            "records follow a deterministic, index-driven pattern (grounded/ungrounded, "
            "accepted/rejected, raised/missed disagreements, one abstention in eleven) chosen to "
            "exercise every code path in this module. They are not derived from any datasheet and "
            "carry no information about a real audit's performance.",
        ),
    )


# ================================================================================================
# Precision / recall / F1 -- the shared statistical shape
# ================================================================================================


def _harmonic_mean(a: float, b: float) -> float:
    if a <= 0.0 or b <= 0.0:
        return 0.0
    return 2.0 * a * b / (a + b)


@dataclass(frozen=True, slots=True)
class RateResult:
    """Precision/recall/F1 for a binary "was this correct" condition, against a fixed gold
    population. Shared by :func:`grounding_f1` (word- and page-level) and :func:`value_f1` -- same
    statistical shape, different correctness condition.
    """

    true_positives: int
    predicted_total: int
    """Records where the system emitted a value -- did not abstain. Precision's denominator."""

    gold_total: int
    """Every gold field, answered or not. Recall's denominator: abstaining costs recall and never
    precision, which is the correct incentive for a system that is allowed to decline a field."""

    precision: Proportion
    recall: Proportion

    @property
    def f1(self) -> float:
        """Point-estimate F1: harmonic mean of the precision and recall point estimates."""
        return _harmonic_mean(self.precision.point, self.recall.point)

    @property
    def conservative_f1(self) -> float:
        """A defensible lower bound on F1, for use in a gate -- not the point estimate.

        F1 is monotone increasing in both precision and recall, so substituting a value at or
        below the true precision and a value at or below the true recall can only produce a value
        at or below the true F1, *provided* both substituted values really are lower bounds. Each
        of ``precision.lo`` and ``recall.lo`` individually holds with 95% confidence; by the union
        bound, the chance that *either* fails to lower-bound its true rate is at most 10%, so this
        quantity understates the true F1 with at least ~90% confidence -- not the 95% either
        interval carries alone. That discount is deliberate and stated here so nobody quotes
        ``conservative_f1`` as a 95%-confidence figure.
        """
        return _harmonic_mean(self.precision.lo, self.recall.lo)


def _prf(true_positives: int, predicted_total: int, gold_total: int) -> RateResult:
    return RateResult(
        true_positives=true_positives,
        predicted_total=predicted_total,
        gold_total=gold_total,
        precision=wilson(true_positives, predicted_total),
        recall=wilson(true_positives, gold_total),
    )


def grounding_f1(
    records: Sequence[MCBRecord],
    *,
    level: GroundingLevel = GroundingLevel.WORD,
    iou_threshold: float = GROUNDING_IOU_THRESHOLD,
) -> RateResult:
    """ExtractBench's grounding metric, verbatim (phase4-full-spec.md §6.2, §0.3 V7).

    A field is grounded-correct only when its value is accepted AND (word-level) its predicted box
    overlaps ANY box on the gold evidence list at IoU >= ``iou_threshold``, or (page-level) it
    cites the correct page. This computes precision and recall of that condition -- precision over
    records the system actually answered, recall over every gold field -- and returns an F1, not a
    raw hit rate: a system that abstains on the fields it would get wrong can inflate a bare hit
    rate; F1 does not let it, because abstaining costs recall.
    """
    gold_total = len(records)
    predicted_total = sum(1 for r in records if r.predicted_value is not None)
    true_positives = sum(1 for r in records if r.grounded_correct(level, iou_threshold))
    return _prf(true_positives, predicted_total, gold_total)


def value_f1(records: Sequence[MCBRecord]) -> RateResult:
    """Value-only correctness -- ignores grounding entirely.

    This is the axis ExtractBench reports as "value F1" (:data:`EXTRACTBENCH_VALUE_F1` percent at
    full coverage, best system): was the value right, independent of whether a supporting box was
    ever offered. Kept separate from :func:`grounding_f1` rather than folded into it, because a
    system can be right about the value and wrong about where it came from, and the two failure
    modes have very different consequences for a reviewer's trust (phase4-full-spec.md §6.2,
    "evidence-acceptance rate").
    """
    gold_total = len(records)
    predicted_total = sum(1 for r in records if r.predicted_value is not None)
    true_positives = sum(1 for r in records if r.value_accepted)
    return _prf(true_positives, predicted_total, gold_total)


# ================================================================================================
# Coverage fractions -- shared slicing logic
# ================================================================================================

DEFAULT_COVERAGE_POINTS: tuple[float, ...] = (0.20, 0.40, 0.60)
"""FR-0.3 names these three coverage points explicitly. Do not add or substitute others here --
callers that want a fuller sweep should call the coverage-taking functions directly with their own
values; this constant is what the R0 gate itself is scored against."""


def _coverage_k(n: int, coverage: float) -> int:
    """How many of ``n`` items the top ``coverage`` fraction covers.

    ``coverage <= 0`` (or ``n == 0``) covers nothing -- 0 items, an explicit "act on nothing"
    state, distinct from "act on the single most confident item". Otherwise at least one item is
    always covered, rounding the fractional count up so that e.g. 20% of 3 items covers 1 item
    rather than 0.
    """
    if n <= 0 or coverage <= 0.0:
        return 0
    return min(n, max(1, math.ceil(coverage * n)))


def _require_unit_interval(coverage: float) -> None:
    if not 0.0 <= coverage <= 1.0:
        raise ValueError(f"coverage must be in [0, 1], got {coverage}")


def _top_by_coverage(records: Sequence[MCBRecord], coverage: float) -> tuple[MCBRecord, ...]:
    """The top ``coverage`` fraction of ``records`` by confidence, ties broken by attribute_id."""
    _require_unit_interval(coverage)
    k = _coverage_k(len(records), coverage)
    if k == 0:
        return ()
    ordered = sorted(records, key=lambda r: (-r.confidence, r.attribute_id))
    return tuple(ordered[:k])


# ================================================================================================
# Risk-coverage curve, AURC, selective accuracy
# ================================================================================================


@dataclass(frozen=True, slots=True)
class RiskCoveragePoint:
    """One point on a risk-coverage curve: cover the ``coverage`` fraction of highest-confidence
    items, and ``risk`` is the error rate within that covered subset (the "selective risk")."""

    coverage: float
    risk: float
    n_covered: int
    n_errors: int


def risk_coverage_curve(
    triples: Sequence[tuple[Any, float, bool]],
) -> tuple[RiskCoveragePoint, ...]:
    """Build a risk-coverage curve from ``(prediction, confidence, is_correct)`` triples.

    Sorts by confidence descending (ties keep their input order -- Python's sort is stable), then
    sweeps coverage from 0 to 1 one item at a time: after taking the ``i`` most-confident items,
    coverage is ``i / n`` and risk is the error rate among those ``i`` items. The curve always
    starts at ``(coverage=0, risk=0)`` -- covering nothing has no errors by definition -- and has
    ``n + 1`` points for ``n`` input triples. An empty input returns the single ``(0, 0)`` point.

    A **non-decreasing** curve is the best case, not a general guarantee: it happens exactly when
    confidence tracks correctness perfectly (every correct item outranks every incorrect one), in
    which case risk is 0 while only correct items are covered and then rises monotonically as
    incorrect items are forced in. A worse-calibrated predictor produces a bumpier curve; that
    bumpiness is itself a diagnostic; nothing here should be assumed to always slope one way.
    """
    n = len(triples)
    if n == 0:
        return (RiskCoveragePoint(coverage=0.0, risk=0.0, n_covered=0, n_errors=0),)
    ordered = sorted(triples, key=lambda t: t[1], reverse=True)
    points = [RiskCoveragePoint(coverage=0.0, risk=0.0, n_covered=0, n_errors=0)]
    errors = 0
    for i, (_, _, is_correct) in enumerate(ordered, start=1):
        if not is_correct:
            errors += 1
        points.append(
            RiskCoveragePoint(coverage=i / n, risk=errors / i, n_covered=i, n_errors=errors)
        )
    return tuple(points)


def aurc(curve: Sequence[RiskCoveragePoint]) -> float:
    """Area under the risk-coverage curve, via trapezoidal integration over ``curve``'s points.

    Lower is better -- a perfect predictor that is wrong only on the fraction of items it must
    cover has AURC approaching 0; a predictor no better than random ordering has AURC approaching
    its overall error rate times roughly one half. Trapezoidal integration is exact whenever the
    true risk-coverage relationship is piecewise linear between the given points, which is exactly
    what :func:`risk_coverage_curve` produces (linear between consecutive covered items).
    """
    if len(curve) < 2:
        return 0.0
    area = 0.0
    for a, b in pairwise(curve):
        area += (b.coverage - a.coverage) * (a.risk + b.risk) / 2.0
    return area


def selective_accuracy_at_coverage(
    triples: Sequence[tuple[Any, float, bool]], coverage: float
) -> Proportion:
    """1 - selective risk at exactly ``coverage``, as a Wilson-interval :class:`Proportion`.

    Takes the top ``coverage`` fraction of ``triples`` by confidence (see :func:`_coverage_k` for
    the exact rounding) and reports the accuracy (fraction correct) within that slice. At
    ``coverage=0`` nothing is covered and this returns ``wilson(0, 0)`` -- rendered as "n/a", not
    100% or 0% -- because a rate with no denominator asserts nothing.
    """
    _require_unit_interval(coverage)
    triples = list(triples)
    k = _coverage_k(len(triples), coverage)
    if k == 0:
        return wilson(0, 0)
    ordered = sorted(triples, key=lambda t: t[1], reverse=True)
    top = ordered[:k]
    correct = sum(1 for _, _, is_correct in top if is_correct)
    return wilson(correct, k)


# ================================================================================================
# precision_at_coverage -- disagreement-detection precision, a DIFFERENT question from grounding
# ================================================================================================


def precision_at_coverage(
    triples: Sequence[tuple[bool, float, bool]], coverage: float
) -> Proportion:
    """Disagreement-detection precision within the top ``coverage`` fraction by confidence.

    ``triples`` are ``(predicted_disagreement, confidence, actually_a_disagreement)``. This answers
    "of the disagreements the audit raised, among the records it was confident enough to act on,
    how many were real" -- a different question from :func:`grounding_f1`, which asks "did the
    audit point at the right words". Keeping them separate is deliberate: an audit can cite the
    exact right box for a value it was wrong to flag as a disagreement, and it can correctly flag a
    genuine disagreement while citing nothing that supports it. Conflating the two would hide
    exactly the failure mode phase4-full-spec.md §0.3 exists to catch.

    Restricted first to the top ``coverage`` fraction (by confidence, ties keep input order), then
    to the records within that slice where a disagreement was actually raised -- records where the
    audit did not raise anything do not count for or against precision. At ``coverage=0`` (nothing
    covered) or when nothing was raised within the covered slice, returns ``wilson(0, 0)``, "n/a":
    precision is undefined when there is nothing to be precise about.
    """
    _require_unit_interval(coverage)
    triples = list(triples)
    k = _coverage_k(len(triples), coverage)
    if k == 0:
        return wilson(0, 0)
    ordered = sorted(triples, key=lambda t: t[1], reverse=True)
    top = ordered[:k]
    raised = [t for t in top if t[0]]
    correct = sum(1 for t in raised if t[2])
    return wilson(correct, len(raised))


# ================================================================================================
# The operating-point report
# ================================================================================================

MIN_RECORDS_FOR_VERDICT = 30
"""Below this many records in the corpus, a Wilson interval is wide enough that issuing a
CONFIRMED/NOT_CONFIRMED verdict off it would be exactly the kind of confident-but-meaningless
number this product exists to find in other people's data. Mirrors equivalence.py's
MIN_FLAGGED_FOR_VERDICT."""


@dataclass(frozen=True, slots=True)
class CoverageRow:
    """The audit's numbers at one coverage operating point -- what happens if it only acts on the
    top ``coverage`` fraction of records by confidence."""

    coverage: float
    """The requested coverage fraction, one of :data:`DEFAULT_COVERAGE_POINTS` in the standard
    report."""

    n_covered: int
    n_total: int

    disagreement_precision: Proportion
    """precision_at_coverage() on this slice -- "was there really something wrong here"."""

    selective_accuracy: Proportion
    """selective_accuracy_at_coverage() on word-level grounded-correctness -- 1 minus the
    selective risk of the risk-coverage curve, evaluated at this coverage."""

    word_grounding: RateResult
    """grounding_f1() at word level, restricted to this coverage slice."""

    page_grounding: RateResult
    """grounding_f1() at page level, restricted to this coverage slice."""

    value_accuracy: RateResult
    """value_f1() -- value correctness alone, restricted to this coverage slice. Comparable to
    EXTRACTBENCH_VALUE_F1 the same way word_grounding is comparable to
    EXTRACTBENCH_WORD_GROUNDING_F1."""

    @property
    def actual_coverage(self) -> float:
        """The coverage actually achieved -- may exceed the requested ``coverage`` slightly when
        rounding up to at least one record, especially on a small corpus."""
        return self.n_covered / self.n_total if self.n_total else 0.0


class AsymmetryVerdict(str, enum.Enum):
    """The FR-0.3 decision: does phase4-full-spec.md §0.3's central assumption hold."""

    NOT_MEASURED = "NOT MEASURED"
    """Synthetic corpus. The shape of the answer is reported; no empirical claim is made. This is
    unconditional -- there is no synthetic input for which this module returns anything else."""

    ASYMMETRY_CONFIRMED = "ASYMMETRY CONFIRMED"
    """Real corpus, enough records, and the audit's word-level grounding F1 clears
    EXTRACTBENCH_WORD_GROUNDING_F1 with a margin the Wilson interval does not retract -- §0.3's
    assumption holds, on this corpus, at this coverage. Proceed."""

    ASYMMETRY_NOT_CONFIRMED = "ASYMMETRY NOT CONFIRMED"
    """Real corpus, enough records, and the margin over baseline is not statistically defensible
    (including a point estimate that looks better but whose Wilson lower bound does not clear the
    baseline). Per §13's kill condition: stop, or narrow the project to the value-semantics
    library plus the benchmark."""

    INCONCLUSIVE = "INCONCLUSIVE"
    """Real corpus, but too few records (below MIN_RECORDS_FOR_VERDICT) for a verdict to mean
    anything, or a degenerate coverage slice with no gold fields to score."""


#: Mirrors errata_bench.cli.EXIT_* without importing it -- the CLI owns exit-code policy, exactly
#: as coverage.py does for CoverageGate.
GATE_EXIT_CODES: dict[AsymmetryVerdict, int] = {
    AsymmetryVerdict.ASYMMETRY_CONFIRMED: 0,
    AsymmetryVerdict.ASYMMETRY_NOT_CONFIRMED: 2,
    AsymmetryVerdict.INCONCLUSIVE: 3,
    AsymmetryVerdict.NOT_MEASURED: 3,
}


@dataclass(frozen=True, slots=True)
class OperatingPointReport:
    """Everything FR-0.3 asks for, and the caveats that stop it being over-read."""

    corpus: MCBCorpus
    rows: tuple[CoverageRow, ...]
    grounding_curve: tuple[RiskCoveragePoint, ...]
    """Full risk-coverage curve, word-level grounded-correctness as the correctness condition."""
    grounding_aurc: float
    iou_threshold: float = GROUNDING_IOU_THRESHOLD

    @property
    def is_synthetic(self) -> bool:
        return self.corpus.is_synthetic

    def at(self, coverage: float) -> CoverageRow | None:
        for row in self.rows:
            if math.isclose(row.coverage, coverage, rel_tol=1e-9, abs_tol=1e-9):
                return row
        return None

    @property
    def baseline_word_grounding_f1(self) -> float:
        """EXTRACTBENCH_WORD_GROUNDING_F1 as a fraction in [0, 1], to compare against this
        module's fraction-valued RateResult.f1 / conservative_f1."""
        return EXTRACTBENCH_WORD_GROUNDING_F1 / 100.0

    @property
    def best_row(self) -> CoverageRow | None:
        """The coverage row with the largest conservative-F1 margin over the ExtractBench
        word-level baseline -- the audit's best defensible case. §0.3's mechanism 1 is that an
        audit only needs ONE workable low-coverage operating point to matter, not all three, so the
        verdict is judged on the best of the three, not their average."""
        if not self.rows:
            return None
        return max(self.rows, key=lambda r: r.word_grounding.conservative_f1)

    @property
    def best_margin(self) -> float | None:
        """best_row's conservative F1 minus the ExtractBench baseline, in fraction points.

        .. warning::
           This subtracts a FULL-coverage baseline from a PARTIAL-coverage measurement. Kept
           because the selective operating point is genuinely interesting, but it is **not** the
           verdict comparison and must never be rendered as though it were. See
           :attr:`full_coverage_margin`, which compares like with like.
        """
        best = self.best_row
        if best is None:
            return None
        return best.word_grounding.conservative_f1 - self.baseline_word_grounding_f1

    @property
    def full_coverage_grounding(self) -> RateResult:
        """Word-level grounding over EVERY record -- the reading FR-0.3 actually asks for.

        The requirement's acceptance criterion is explicit: *"compared explicitly against
        ExtractBench's 46.43 word-level / 95.6 value F1 **at full coverage**"*. ExtractBench's
        published figure is what its best system scores while answering every field, so the only
        directly comparable number from this corpus is the one computed the same way.

        This was a real defect, found when gate 2 first ran on real data (finding N9). The verdict
        was taken from :attr:`best_row` -- the most favourable of the 20/40/60% coverage points --
        and compared against the full-coverage baseline. On the ABB S200 corpus that reported a
        52-point win and printed "Proceed", while the like-for-like comparison was a dead heat.
        The caveat naming the mismatch was already in the report, below the verdict, which is
        exactly the shape of R0 findings 1-4: the instrument knew and the verdict routed around it.
        """
        return grounding_f1(
            self.corpus.records, level=GroundingLevel.WORD, iou_threshold=self.iou_threshold
        )

    @property
    def full_coverage_value_f1(self) -> RateResult:
        """Value F1 over every record, for the 95.6% half of the same comparison."""
        return value_f1(self.corpus.records)

    @property
    def full_coverage_margin(self) -> float:
        """The verdict comparison: full-coverage conservative F1 minus the baseline.

        Conservative rather than the point estimate, per FR-0.3's requirement that the margin be
        statistically defensible rather than merely positive.
        """
        return self.full_coverage_grounding.conservative_f1 - self.baseline_word_grounding_f1

    @property
    def verdict(self) -> AsymmetryVerdict:
        return asymmetry_verdict(self)

    @property
    def caveats(self) -> list[str]:
        notes: list[str] = []
        if self.is_synthetic:
            notes.append(
                "the corpus is SYNTHETIC. Every figure here is structural -- it exercises the "
                "metric code, and describes no real audit. FR-0.3 is NOT MEASURED."
            )
        notes.extend(self.corpus.notes)
        if not self.is_synthetic and self.corpus.size < TARGET_CORPUS_SIZE:
            notes.append(
                f"FR-0.3 asks for {TARGET_CORPUS_SIZE} hand-labelled records; this corpus has "
                f"{self.corpus.size}. The Wilson intervals below are the honest width of that "
                "shortfall, not a smaller number pretending to be as certain as 200 would be."
            )
        notes.append(
            "value_accepted is exact string match after whitespace stripping, not semantic "
            "equivalence -- this module is not the comparator FR-0.1/FR-0.2 (equivalence.py) "
            "already measure. A real corpus should resolve gold/predicted value pairs through "
            "that comparator before loading, so 'accepted' means the same thing everywhere."
        )
        notes.append(
            "conservative_f1 combines the Wilson LOWER bounds of precision and recall and "
            "understates true F1 with only ~90% joint confidence (union bound over two 5% tails), "
            "not the 95% either bound alone carries. See RateResult.conservative_f1."
        )
        notes.append(
            f"EXTRACTBENCH_WORD_GROUNDING_F1 ({EXTRACTBENCH_WORD_GROUNDING_F1}) is a FULL-COVERAGE "
            "number -- the best system answering every field. The rows here are computed at "
            "partial coverage by construction (20/40/60%); a favourable comparison at low "
            "coverage should be read next to n_covered/n_total, not in isolation."
        )
        if self.iou_threshold != GROUNDING_IOU_THRESHOLD:
            notes.append(
                f"word-level grounding used iou_threshold={self.iou_threshold}, not ExtractBench's "
                f"stated {GROUNDING_IOU_THRESHOLD}. Comparisons against "
                "EXTRACTBENCH_WORD_GROUNDING_F1 are no longer apples-to-apples."
            )
        return notes


def operating_point_report(
    corpus: MCBCorpus | None = None,
    *,
    coverage_points: Sequence[float] = DEFAULT_COVERAGE_POINTS,
    iou_threshold: float = GROUNDING_IOU_THRESHOLD,
) -> OperatingPointReport:
    """Run FR-0.3 end to end. This is the entry point a CLI should call.

    With no corpus this runs on :func:`synthetic_corpus` and the verdict is pinned to
    ``NOT_MEASURED`` -- which is the correct state of this kill test today.
    """
    corpus = corpus if corpus is not None else synthetic_corpus()
    records = corpus.records
    n_total = len(records)

    word_triples: tuple[tuple[str, float, bool], ...] = tuple(
        (r.attribute_id, r.confidence, r.grounded_correct(GroundingLevel.WORD, iou_threshold))
        for r in records
    )
    disagreement_triples: tuple[tuple[bool, float, bool], ...] = tuple(
        (r.is_disagreement_predicted, r.confidence, r.is_disagreement_actual) for r in records
    )

    rows: list[CoverageRow] = []
    for coverage in coverage_points:
        subset = _top_by_coverage(records, coverage)
        rows.append(
            CoverageRow(
                coverage=coverage,
                n_covered=len(subset),
                n_total=n_total,
                disagreement_precision=precision_at_coverage(disagreement_triples, coverage),
                selective_accuracy=selective_accuracy_at_coverage(word_triples, coverage),
                word_grounding=grounding_f1(
                    subset, level=GroundingLevel.WORD, iou_threshold=iou_threshold
                ),
                page_grounding=grounding_f1(subset, level=GroundingLevel.PAGE),
                value_accuracy=value_f1(subset),
            )
        )

    curve = risk_coverage_curve(word_triples)
    return OperatingPointReport(
        corpus=corpus,
        rows=tuple(rows),
        grounding_curve=curve,
        grounding_aurc=aurc(curve),
        iou_threshold=iou_threshold,
    )


def asymmetry_verdict(report: OperatingPointReport) -> AsymmetryVerdict:
    """Does §0.3's assumption hold: does the audit clear the extraction baseline, by how much,
    and with what confidence.

    NOT_MEASURED unconditionally for a synthetic corpus -- checked first, and nothing below can
    override it. Otherwise INCONCLUSIVE if the corpus is smaller than MIN_RECORDS_FOR_VERDICT.

    That corpus-level check is necessary but not sufficient, and this is the second, load-bearing
    guard: ``best_row`` is chosen as whichever of the three coverage points (20/40/60%) has the
    highest conservative F1, and a coverage POINT can have far fewer records in it than the corpus
    as a whole -- 20% coverage of a 150-record corpus is 30 records, but 20% of a 34-record corpus
    is 7. A corpus that clears MIN_RECORDS_FOR_VERDICT in total can still hand back a "best" row
    built from a double-digit sample, and at n=7 a lucky run of correct answers produces a Wilson
    lower bound that clears the baseline for no reason but small-sample noise -- exactly the
    confident-but-meaningless number this whole module exists to catch in someone else's data.  So
    the row that actually carries the verdict must ALSO clear MIN_RECORDS_FOR_VERDICT on its own
    ``n_covered``, not just inherit credibility from the corpus total. Below that, INCONCLUSIVE,
    even if that row's point estimate looks decisive.

    Otherwise INCONCLUSIVE if there are no gold fields to score. Otherwise ASYMMETRY_CONFIRMED
    only when the **full-coverage** ``conservative_f1`` -- the harmonic mean of the Wilson LOWER
    bounds of precision and recall, not the point estimate -- exceeds the ExtractBench baseline: a
    positive difference between point estimates is not sufficient, by design, per FR-0.3's honesty
    requirement that the margin be statistically defensible rather than merely positive.

    **The comparison is at full coverage, and that is a correction (finding N9, 2026-08-19).**
    This function previously judged on :attr:`OperatingPointReport.best_row` -- the most
    favourable of the 20/40/60% coverage points -- against a baseline that is a full-coverage
    figure. The first real corpus made the consequence visible: the audit answered its easiest
    20% of fields, grounded them almost perfectly, and the gate reported clearing the baseline by
    52 points and printed "Proceed", while the like-for-like number was a dead heat.

    FR-0.3's acceptance criterion says "at full coverage" in as many words, so this is
    requirement conformance rather than a judgment call. The selective rows remain in the report
    -- §0.3's mechanism 1 is that an audit needs only one workable low-coverage operating point
    to be useful, and that argument survives intact -- but a selective number cannot be scored
    against a full-coverage baseline, and the verdict no longer pretends otherwise.
    """
    if report.is_synthetic:
        return AsymmetryVerdict.NOT_MEASURED
    if report.corpus.size < MIN_RECORDS_FOR_VERDICT:
        return AsymmetryVerdict.INCONCLUSIVE
    grounding = report.full_coverage_grounding
    if grounding.gold_total == 0:
        return AsymmetryVerdict.INCONCLUSIVE
    if grounding.conservative_f1 > report.baseline_word_grounding_f1:
        return AsymmetryVerdict.ASYMMETRY_CONFIRMED
    return AsymmetryVerdict.ASYMMETRY_NOT_CONFIRMED


# ================================================================================================
# Rendering
# ================================================================================================

_RULE = "-" * 96


def _pct(x: float) -> str:
    return f"{100 * x:.2f}%"


def render_report(report: OperatingPointReport) -> str:
    """Human-readable FR-0.3 report. Prints the synthetic banner whenever it applies."""
    out: list[str] = []
    add = out.append

    add("")
    add("R0 KILL TEST 2 -- OPERATING POINT (FR-0.3)")
    add(
        f"corpus: {report.corpus.name}   {report.corpus.size} records   "
        f"[{report.corpus.provenance.value}]"
    )
    if report.corpus.source:
        add(f"source: {report.corpus.source}")
    add(_RULE)

    if report.is_synthetic:
        add("")
        add(SYNTHETIC_BANNER)

    add("")
    add("ExtractBench baseline (full coverage) -- " + EXTRACTBENCH_CITATION)
    add(f"  word-level grounding F1   {EXTRACTBENCH_WORD_GROUNDING_F1:.2f}%  "
        f"(2nd {EXTRACTBENCH_WORD_GROUNDING_F1_SECOND:.2f}%, Reducto "
        f"{EXTRACTBENCH_WORD_GROUNDING_F1_REDUCTO:.2f}%; "
        f"{EXTRACTBENCH_SYSTEMS_AT_ZERO_GROUNDING}/{EXTRACTBENCH_SYSTEMS_EVALUATED} systems score "
        f"0.00)")
    add(f"  page-level grounding F1  {EXTRACTBENCH_PAGE_GROUNDING_F1:.2f}%")
    add(f"  value F1                 {EXTRACTBENCH_VALUE_F1:.2f}%  at "
        f"{EXTRACTBENCH_COST_CENTS_PER_PAGE:.1f}¢/page")

    add("")
    add("Operating point vs coverage")
    add(f"{'coverage':>9}  {'n':>9}  {'disagreement':>19}  {'word F1':>19}  "
        f"{'page F1':>10}  {'value F1':>10}  {'sel. acc.':>17}")
    add(f"{'':>9}  {'':>9}  {'precision':>19}  {'(conservative)':>19}  {'':>10}  {'':>10}  {'':>17}")
    add(_RULE)
    for row in report.rows:
        add(
            f"{_pct(row.coverage):>9}  {row.n_covered:>9}  "
            f"{row.disagreement_precision.render_short():>19}  "
            f"{_pct(row.word_grounding.f1)} ({_pct(row.word_grounding.conservative_f1)}){'':>0}  "
            f"{_pct(row.page_grounding.f1):>10}  {_pct(row.value_accuracy.f1):>10}  "
            f"{row.selective_accuracy.render_short():>17}"
        )
    add("")
    add(f"Risk-coverage AURC (word-level grounded-correctness): {report.grounding_aurc:.4f}  "
        f"(lower is better; {len(report.grounding_curve)} points)")

    full = report.full_coverage_grounding
    add("")
    add("FULL COVERAGE -- the only reading directly comparable to the baseline (FR-0.3)")
    add(f"  word-level grounding F1   {_pct(full.f1)}  (conservative {_pct(full.conservative_f1)})"
        f"   vs baseline {EXTRACTBENCH_WORD_GROUNDING_F1:.2f}%")
    add(f"  value F1                  {_pct(report.full_coverage_value_f1.f1)}"
        f"   vs baseline {EXTRACTBENCH_VALUE_F1:.2f}%")
    add("  The 20/40/60% rows above are SELECTIVE. ExtractBench's figures are what its best")
    add("  system scores answering every field, so only this row can be set against them.")

    add("")
    add(_RULE)
    add(f"VERDICT: {report.verdict.value}")
    add(_verdict_sentence(report))

    add("")
    add("What this does not establish")
    for caveat in report.caveats:
        add(f"  - {caveat}")
    add("")
    return "\n".join(out)


def _verdict_sentence(report: OperatingPointReport) -> str:
    verdict = report.verdict
    if verdict is AsymmetryVerdict.NOT_MEASURED:
        return (
            "Synthetic input. This run reports the SHAPE of the answer and no empirical result.\n"
            "To make FR-0.3 live: hand-label 200 MCB records from public datasheets and a "
            "grounding pipeline\n(FR-1.2 .. FR-1.5) to produce predicted boxes, then pass the "
            "result to load_corpus(). Nothing else\nabout this test is blocked."
        )
    if verdict is AsymmetryVerdict.INCONCLUSIVE:
        if report.corpus.size < MIN_RECORDS_FOR_VERDICT:
            return (
                f"Real corpus, but only {report.corpus.size} records total "
                f"(< MIN_RECORDS_FOR_VERDICT={MIN_RECORDS_FOR_VERDICT}). Too small for a Wilson "
                "interval to mean anything -- label more before treating this as an answer."
            )
        best = report.best_row
        if best is not None and best.n_covered < MIN_RECORDS_FOR_VERDICT:
            return (
                f"Real corpus with {report.corpus.size} records overall, but the best coverage "
                f"row ({_pct(best.coverage)} coverage) is only {best.n_covered} records "
                f"(< MIN_RECORDS_FOR_VERDICT={MIN_RECORDS_FOR_VERDICT}). The corpus total clears "
                "the floor; the specific operating point that would carry the verdict does not. "
                "Label more records, or accept a wider coverage point, before treating this as "
                "an answer."
            )
        return (
            "Real corpus, but the best coverage slice has no gold fields to score. Nothing to "
            "measure."
        )
    full = report.full_coverage_grounding
    margin = report.full_coverage_margin
    best = report.best_row
    selective = ""
    if best is not None:
        selective = (
            f"\nSelectively, at {_pct(best.coverage)} coverage it reaches "
            f"{_pct(best.word_grounding.conservative_f1)} on {best.n_covered}/{best.n_total} "
            "records -- interesting, and NOT comparable to a full-coverage baseline."
        )
    if verdict is AsymmetryVerdict.ASYMMETRY_CONFIRMED:
        return (
            f"At FULL coverage, word-level grounding conservative-F1 is "
            f"{_pct(full.conservative_f1)}, clearing the "
            f"{EXTRACTBENCH_WORD_GROUNDING_F1:.2f}% ExtractBench baseline by "
            f"{100 * margin:.2f}pp even under the Wilson lower bound. §0.3's assumption holds "
            f"on this corpus. Proceed.{selective}"
        )
    return (
        f"At FULL coverage -- the comparison FR-0.3 asks for -- word-level grounding "
        f"conservative-F1 is {_pct(full.conservative_f1)} (point estimate {_pct(full.f1)}) "
        f"against a {EXTRACTBENCH_WORD_GROUNDING_F1:.2f}% baseline: a margin of "
        f"{100 * margin:.2f}pp that the Wilson interval does not support as real. On this corpus "
        f"the audit does NOT ground better than published extraction -- it draws with it.{selective}"
        "\nPer §13 this is a stop-or-narrow signal, and per ground rule 4 it is reported as "
        "found. Read it next to the caveats below before acting: one corpus, one manufacturer, "
        "and a deliberately unsophisticated extractor."
    )


def _proportion_dict(p: Proportion) -> dict[str, Any]:
    return {
        "successes": p.successes,
        "total": p.total,
        "point": p.point,
        "lo": p.lo,
        "hi": p.hi,
        "confidence": p.confidence,
    }


def _rate_result_dict(r: RateResult) -> dict[str, Any]:
    return {
        "true_positives": r.true_positives,
        "predicted_total": r.predicted_total,
        "gold_total": r.gold_total,
        "precision": _proportion_dict(r.precision),
        "recall": _proportion_dict(r.recall),
        "f1": r.f1,
        "conservative_f1": r.conservative_f1,
    }


def report_as_dict(report: OperatingPointReport) -> dict[str, Any]:
    """Machine-readable FR-0.3 report. Carries the synthetic flag and banner, not just numbers."""
    return {
        "verdict": report.verdict.value,
        "synthetic": report.is_synthetic,
        "banner": SYNTHETIC_BANNER if report.is_synthetic else "",
        "corpus": {
            "name": report.corpus.name,
            "provenance": report.corpus.provenance.value,
            "source": report.corpus.source,
            "size": report.corpus.size,
            "notes": list(report.corpus.notes),
        },
        "baseline": {
            "citation": EXTRACTBENCH_CITATION,
            "word_grounding_f1_percent": EXTRACTBENCH_WORD_GROUNDING_F1,
            "word_grounding_f1_second_percent": EXTRACTBENCH_WORD_GROUNDING_F1_SECOND,
            "word_grounding_f1_reducto_percent": EXTRACTBENCH_WORD_GROUNDING_F1_REDUCTO,
            "systems_at_zero_grounding": EXTRACTBENCH_SYSTEMS_AT_ZERO_GROUNDING,
            "systems_evaluated": EXTRACTBENCH_SYSTEMS_EVALUATED,
            "page_grounding_f1_percent": EXTRACTBENCH_PAGE_GROUNDING_F1,
            "value_f1_percent": EXTRACTBENCH_VALUE_F1,
            "cost_cents_per_page": EXTRACTBENCH_COST_CENTS_PER_PAGE,
        },
        "iou_threshold": report.iou_threshold,
        "rows": [
            {
                "coverage": row.coverage,
                "actual_coverage": row.actual_coverage,
                "n_covered": row.n_covered,
                "n_total": row.n_total,
                "disagreement_precision": _proportion_dict(row.disagreement_precision),
                "selective_accuracy": _proportion_dict(row.selective_accuracy),
                "word_grounding": _rate_result_dict(row.word_grounding),
                "page_grounding": _rate_result_dict(row.page_grounding),
                "value_accuracy": _rate_result_dict(row.value_accuracy),
            }
            for row in report.rows
        ],
        "grounding_curve": [
            {
                "coverage": p.coverage,
                "risk": p.risk,
                "n_covered": p.n_covered,
                "n_errors": p.n_errors,
            }
            for p in report.grounding_curve
        ],
        "grounding_aurc": report.grounding_aurc,
        "best_row_coverage": report.best_row.coverage if report.best_row else None,
        "best_margin": report.best_margin,
        "caveats": report.caveats,
    }
