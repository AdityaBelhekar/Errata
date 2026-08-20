"""Score an extractor on the FR-0.3 corpus, stratified, with the coverage next to the rate.

**The finding this module exists to report.** R0 gate 2 publishes 46.34% word-level grounding F1
against ExtractBench's 46.4% and calls it a dead heat. That number came from ``spike/predict.py``.
Scoring ``errata_audit.derive`` -- the extractor this repository ships -- on the same corpus turns
out to need two runs, not one, because the obvious run produces a tautology:

* **as it ships (``r1``): 100.00%.** Gold is the cell under a named column in the row whose
  identity is the type designation, and ``derive`` prefers exactly that cell. The two are the same
  act performed twice. This is not a result and this module refuses to print it as one.
* **with table structure withheld (``r1-textwindow``): 2.05% over the corpus, 11.76% over the
  records it answers, on 9.5% coverage.** That path shares no mechanism with gold, so it is a real
  measurement -- and it is the configuration most comparable to ExtractBench, whose systems read
  documents rather than parsed table structure.

**Why the shipped extractor scores so much lower than the baseline on the same path.** The two use
the same window (eight words either side of the MPN) over the same documents. They differ in what
they do when the window is ambiguous. The baseline takes the nearest match in reading order. R1
abstains, on 1,196 of 1,426 records, because nearest-in-reading-order is a tie-break rather than
evidence and a value picked by tie-break becomes a confident accusation two steps later -- this is
finding N12, found on the S200 M UC datasheet whose running text reads ``0.2 A 0.3 A 0.5 A`` and
whose fallback returned 0.3 for a 0.2 A device.

So the honest statement of gate 2 is not "we tie ExtractBench". It is:

    46.34% is the score of a system that guesses when the evidence is ambiguous. The system this
    repository ships declines those records instead, and publishes the coverage it gave up to do
    it.

Which is why every number here is printed beside its coverage, and why :func:`render_score` will
not emit a grounding F1 without one. The README already states the rule for gate 1 -- "a comparator
can flatter its false-positive rate by refusing to commit" -- and the converse is just as true: an
extractor can flatter its grounding F1 by refusing to abstain.
"""

from __future__ import annotations

import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from errata_bench.operating_point import (
    EXTRACTBENCH_WORD_GROUNDING_F1,
    GroundingLevel,
    MCBRecord,
    RateResult,
    grounding_f1,
    load_corpus,
    value_f1,
)

__all__ = [
    "ExtractorScore",
    "Stratum",
    "render_score",
    "score_corpus",
]


@dataclass(frozen=True, slots=True)
class Stratum:
    """One slice of a score, and whether it may be compared to anything.

    ``comparable`` is the field that matters. A stratum whose predictions were found by the same
    mechanism that produced gold agrees partly by construction, and a reader who does not know
    which stratum they are looking at cannot tell a measurement from a tautology.
    """

    method: str
    records: int
    grounding: RateResult
    value: RateResult
    comparable: bool
    why: str


@dataclass(frozen=True, slots=True)
class ExtractorScore:
    extractor: str
    corpus_name: str
    records: int
    answered: int
    grounding: RateResult
    value: RateResult
    strata: tuple[Stratum, ...]
    notes: tuple[str, ...]

    @property
    def coverage(self) -> float:
        """Fraction of gold records the extractor committed to.

        Never printed apart from a rate. An extractor that abstains everywhere has an undefined
        grounding F1 and a very defensible one; an extractor that never abstains has a flattering
        one. Neither is readable alone.
        """
        return self.answered / self.records if self.records else 0.0

    @property
    def grounding_on_answered(self) -> float:
        """Grounding F1 recomputed over only the records this extractor answered.

        The corpus-wide F1 charges every abstention as a miss, which is right for "how much of this
        catalog can it ground" and wrong for "when it commits, is it correct". Both are reported
        because they answer different questions and quoting either alone misleads.
        """
        answered = [s for s in self.strata if s.method != "abstained"]
        hits = sum(s.grounding.true_positives for s in answered)
        return hits / self.answered if self.answered else 0.0


#: Which derivation methods share a mechanism with the gold builder. Gold is read from table
#: structure, so a prediction read from table structure is not independent of it -- however
#: separately the two table engines were written.
_SHARES_MECHANISM_WITH_GOLD = {"table_cell"}

_WHY = {
    "table_cell": (
        "gold is a table cell and so is this prediction, from two independently written table "
        "engines. Agreement is partly structural. NOT comparable to ExtractBench."
    ),
    "text_window": (
        "found by proximity in reading order, with no access to cells or columns. Shares no "
        "mechanism with gold, so this IS comparable to ExtractBench's word-level grounding F1."
    ),
    "abstained": (
        "the extractor declined. Counted as a miss in the corpus-wide rate and excluded from the "
        "on-answered rate, because an abstention is not a wrong answer -- it is the absence of one."
    ),
}


def _records_of(document: dict[str, Any]) -> tuple[tuple[MCBRecord, ...], dict[str, str]]:
    """Load a built corpus through ``errata_bench``'s own loader rather than constructing records.

    Going through the file is deliberate. The loader is what every published number in this
    repository was produced by, and a scorer that built ``MCBRecord`` objects directly could drift
    from it -- silently, and in the direction of whatever it was trying to show.
    """
    tmp = Path(tempfile.mkdtemp(prefix="errata-corpus-")) / "corpus.yaml"
    tmp.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    corpus = load_corpus(tmp)
    method_by_id = {
        str(row["attribute_id"]): str(row.get("method", "unknown")) for row in document["records"]
    }
    return corpus.records, method_by_id


def score_corpus(document: dict[str, Any]) -> ExtractorScore:
    """Score a corpus built by :func:`errata_ecosystem.corpusbuild.build_corpus`."""
    records, method_by_id = _records_of(document)
    counts: Counter[str] = Counter(method_by_id.values())

    strata: list[Stratum] = []
    for method in sorted(counts):
        subset = [r for r in records if method_by_id[r.attribute_id] == method]
        strata.append(
            Stratum(
                method=method,
                records=len(subset),
                grounding=grounding_f1(subset, level=GroundingLevel.WORD),
                value=value_f1(subset),
                comparable=method not in _SHARES_MECHANISM_WITH_GOLD and method != "abstained",
                why=_WHY.get(method, "unrecognised derivation method"),
            )
        )

    return ExtractorScore(
        extractor=str(document.get("name", "unnamed")),
        corpus_name=str(document.get("name", "unnamed")),
        records=len(records),
        answered=sum(1 for r in records if r.predicted_value is not None),
        grounding=grounding_f1(records, level=GroundingLevel.WORD),
        value=value_f1(records),
        strata=tuple(strata),
        notes=tuple(str(n) for n in document.get("notes", ())),
    )


_RULE = "-" * 96


def render_score(score: ExtractorScore) -> str:
    """The report. Every rate carries its coverage and every stratum says whether it counts."""
    lines: list[str] = [
        _RULE,
        f"EXTRACTOR SCORE -- {score.extractor}",
        _RULE,
        "",
        f"  records            {score.records}",
        f"  answered           {score.answered}  ({score.coverage:.1%} coverage)",
        f"  abstained          {score.records - score.answered}",
        "",
        f"  word grounding F1  {score.grounding.f1:.2%}   over the whole corpus "
        "(every abstention charged as a miss)",
        f"                     {score.grounding_on_answered:.2%}   over the records it answered",
        f"  value F1           {score.value.f1:.2%}",
        "",
        f"  ExtractBench's best published word-level grounding F1: {EXTRACTBENCH_WORD_GROUNDING_F1}%",
        "",
        "  BY DERIVATION METHOD -- read the `comparable` column before quoting anything:",
        "",
    ]

    for stratum in score.strata:
        flag = "COMPARABLE" if stratum.comparable else "NOT comparable"
        lines.append(
            f"    {stratum.method:14s} n={stratum.records:5d}  "
            f"grounding F1 {stratum.grounding.f1:7.2%}  value F1 {stratum.value.f1:7.2%}  [{flag}]"
        )
        lines.append(f"                   {stratum.why}")
        lines.append("")

    comparable = [s for s in score.strata if s.comparable]
    if not comparable:
        lines += [
            "  NO STRATUM OF THIS RUN IS COMPARABLE TO EXTRACTBENCH.",
            "  Every prediction was read from the same table structure that produced gold, so the",
            "  score above is the same act performed twice and measures nothing. Run the extractor",
            "  with table structure withheld to get a number that means something.",
            "",
        ]

    lines.append("  WHAT THIS CORPUS DOES NOT ESTABLISH:")
    lines.extend(f"    - {note}" for note in score.notes)
    lines.append(_RULE)
    return "\n".join(lines)
