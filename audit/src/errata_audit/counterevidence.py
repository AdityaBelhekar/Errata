"""FR-7.4 -- the counter-evidence panel: the best case *for* the value we are disagreeing with.

    "Never empty and never absent. A disagreement with no counter-evidence section fails review."

This is the component competitors will not build, and the reason to build it is not fairness, it is
retention. An auditor that only shows evidence for its own conclusion is a prosecutor, and a
reviewer learns to distrust a prosecutor by the third screen. Sometimes the counter-evidence is
strong enough that the reviewer keeps the catalog value -- that is the feature working. §5.4 goes
further: a *Keep catalog* decision against an empty counter-evidence panel is the highest-signal
event in the system, because the reviewer knows something the corpus does not.

**Ordering matters, and is structural.** This module runs *after* re-derivation, takes the derived
claim as an input it cannot influence, and returns only a panel. It is the one place in the
pipeline that is allowed to look for the catalog's own value in the document -- and it is a
separate module precisely so that capability can never leak into ``derive``, where it would break
FR-3.4 and make every agreement meaningless.

**"No supporting evidence" is a finding, not a blank.** The summary sentence is mandatory
(``CounterEvidence`` refuses an empty one), so the panel says *"no independent evidence supports
the catalog value of '63 A'"* rather than rendering nothing and letting the reviewer supply the
explanation themselves.
"""

from __future__ import annotations

import re

from errata_spec import BBox, CounterEvidence, Evidence

from .layout import TextLayer, Word

__all__ = ["MAX_SUPPORTING", "find_counter_evidence"]

#: How many supporting spans to carry. A panel with forty boxes is a panel nobody reads; three is
#: enough to show whether the catalog's value appears at all and in what context.
MAX_SUPPORTING = 3

#: How far from an anchor a supporting mention still counts as being about this product. Same
#: reasoning as the derivation window, and deliberately the same order of magnitude: a mention of
#: "63" forty words away from the MPN is a mention of some other product's rating.
NEAR = 40

_NUMERIC = re.compile(r"\d")


def find_counter_evidence(
    layer: TextLayer,
    *,
    catalog_value: str,
    mpn: str,
    doc_id: str,
    revision_sha256: str,
    from_audited_feed: bool = False,
) -> CounterEvidence:
    """Look for the catalog's value in the document, and say plainly what was found.

    ``from_audited_feed`` marks a corpus that is downstream of the feed under audit -- a
    distributor page built from the same data. Support from there is not independent corroboration
    and presenting it as such would be circular, so it is carried with ``independent=False`` and
    the summary says why.
    """
    value = catalog_value.strip()
    if not value:
        return CounterEvidence(
            supporting=(),
            independent=False,
            summary=(
                "The catalog states no value for this attribute, so there is nothing to support: "
                "this is a gap in the catalog rather than a disputed value."
            ),
        )

    tokens = [t for t in re.split(r"\s+", value) if t]
    head = tokens[0]
    anchors = [i for i, w in enumerate(layer.words) if w.text == mpn]
    hits: list[tuple[int, Word]] = []

    for index, word in enumerate(layer.words):
        if word.text != head:
            continue
        distance = min((abs(index - a) for a in anchors), default=NEAR + 1)
        if anchors and distance > NEAR:
            continue
        hits.append((distance, word))

    if not hits:
        return CounterEvidence.none_found(catalog_value)

    hits.sort(key=lambda item: (item[0], item[1].start))
    supporting = tuple(
        Evidence(
            doc_id=doc_id,
            doc_revision_sha256=revision_sha256,
            page=word.page,
            char_span=word.span,
            bbox=BBox(x0=word.x0, y0=word.y0, x1=word.x1, y1=word.y1),
            snippet=layer.snippet(word.start, word.end),
            extraction_layer_version=layer.layout_version,
            row_header=mpn,
        )
        for _distance, word in hits[:MAX_SUPPORTING]
    )

    where = "in the manufacturer's own document"
    qualifier = (
        " -- but this corpus is derived from the feed under audit, so it is not independent "
        "corroboration"
        if from_audited_feed
        else ""
    )
    plural = "s" if len(supporting) != 1 else ""
    numeric_note = (
        " The match is on the leading token only; a bare number can appear for another reason, "
        "and the box shows where."
        if _NUMERIC.search(head)
        else ""
    )
    return CounterEvidence(
        supporting=supporting,
        independent=not from_audited_feed,
        summary=(
            f"The catalog value {catalog_value!r} does appear {where} -- "
            f"{len(supporting)} span{plural} near {mpn}{qualifier}.{numeric_note}"
        ),
    )
