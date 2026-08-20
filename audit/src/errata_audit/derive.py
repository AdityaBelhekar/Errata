"""FR-3.1 - FR-3.4 -- re-derivation: span-required, schema-constrained, and blind to the catalog.

Four requirements meet in this module and one of them decides whether any of it means anything.

**FR-3.4 -- blind re-derivation.** The extractor must not see the catalog's value. The PRD says
this is the requirement most likely to be quietly broken during optimisation, because passing the
catalog value in as a hint measurably improves grounding and makes every subsequent agreement
meaningless. So it is enforced by the *signature*::

    derive(layer, tables, *, mpn, attribute, klass, ...) -> Derivation

There is no parameter through which a catalog value could arrive -- not a defaulted one, not an
optional one, not a dictionary of "context". A test asserts the signature, and asserts it by
inspecting the function rather than by reading the source, so a keyword added later fails the
build. Knowing *which* product is being audited is not a leak: that is the MPN, it comes from the
catalog record's identity, and an auditor who did not know which row to read would be solving a
different problem.

**FR-3.2 -- span-required extraction.** Every value carries doc id, revision hash, page, char span,
bbox and snippet. This is not enforced here; it is enforced by ``errata_spec.emit_extracted_claim``
raising ``EmptyEvidenceError``, one layer down, where it cannot be argued with.

**FR-3.3 -- abstain rather than value.** When no span can be produced the result is an
``Abstention``, a different type with no value field to misread.

**FR-3.1 -- constrained to the class's schema.** Where ETIM declares a closed value list for the
feature, a re-derived value outside it is rejected *before* it becomes a claim. The rejection is an
abstention with a reason, not a silent drop.

**How a value is actually found, in order of preference.** The table path is the good one: find the
row whose identity cell is the MPN, take the cell under the mapped column, and carry the row and
column headers with it. The text-window path is the fallback for a document whose tables did not
resolve, and it is *worse on purpose* -- it looks near the MPN in reading order, which is what an
extractor without table structure has to do, and it says so in the method it records. When the
window straddles a column boundary (FR-1.6) it abstains rather than guessing which product owns
the value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from errata_spec import (
    Abstention,
    BBox,
    Claim,
    DeclinedReason,
    Evidence,
    ExtractorFingerprint,
    emit_abstention,
    emit_extracted_claim,
)
from errata_valuesem import GRAMMAR_VERSION as VALUESEM_GRAMMAR_VERSION

from .attributes import AuditAttribute
from .etim import EtimClass
from .layout import TextLayer, Word
from .tables import Cell, Table

__all__ = [
    "DERIVE_VERSION",
    "WINDOW",
    "Derivation",
    "derive",
    "fingerprint",
]

DERIVE_VERSION = "errata-derive/1.0.0"

#: How many words either side of the MPN the text-window fallback searches. Wide enough to cross a
#: table row in reading order, narrow enough not to wander into the next product. Chosen from the
#: documents' own row width (seven columns), NOT tuned against how often the audit then agrees with
#: the catalog -- tuning a window until the disagreement rate looks better is fitting the extractor
#: to the thing it is supposed to be measuring.
WINDOW = 8

Method = Literal["table_cell", "text_window"]


def fingerprint(method: str = "") -> ExtractorFingerprint:
    """Everything needed to reproduce this derivation (NFR-1, NFR-2).

    ``params_sha256`` is left empty rather than filled with a hash of nothing: this extractor is
    deterministic and parameterless, and a hash of an empty parameter set would imply parameters
    exist and were captured. ``model_id`` is empty for the same reason -- no model produced this --
    and ``ExtractorFingerprint`` now enforces the pairing: naming a model without the three hashes
    that make its output reconstructible raises (NFR-2).

    The strategy goes in ``method``. It used to go in ``model_id``, which was wrong in a way that
    only mattered later: a derivation method is not a model id, and leaving it there would have
    made the NFR-2 check fire on every rule-based claim in the repository.
    """
    return ExtractorFingerprint(
        name="errata-audit.derive",
        version=DERIVE_VERSION,
        method=method,
        grammar_version=VALUESEM_GRAMMAR_VERSION,
    )


@dataclass(frozen=True, slots=True)
class Derivation:
    """The outcome of re-deriving one attribute of one SKU: a claim, or a declared non-answer."""

    attribute: AuditAttribute
    claim: Claim | None
    abstention: Abstention | None
    method: str = ""
    raw_score: float = 0.0
    """An uncalibrated score from things the extractor can observe -- never a probability. It
    becomes one only in ``confidence.py``, against a named calibration set, and the two are kept in
    different fields so that a raw number can never be printed as though it were calibrated."""

    candidates: int = 0
    distance: int = 0
    evidence: tuple[Evidence, ...] = ()

    @property
    def value(self) -> str | None:
        return self.claim.value_raw if self.claim is not None else None

    @property
    def abstained(self) -> bool:
        return self.claim is None


def derive(
    layer: TextLayer,
    tables: tuple[Table, ...],
    *,
    mpn: str,
    attribute: AuditAttribute,
    klass: EtimClass | None,
    sku_id: str,
    doc_id: str,
    revision_sha256: str,
    class_uri: str = "",
) -> Derivation:
    """Re-derive one attribute for one SKU from one document. Blind to the catalog (FR-3.4)."""
    if not layer.is_born_digital:
        return _abstain(
            attribute,
            sku_id,
            class_uri,
            DeclinedReason.LAYOUT_UNREADABLE,
            f"{doc_id} has no usable text layer ({len(layer.words)} words over "
            f"{layer.page_count} pages); this pipeline does not OCR, and guessing at a scan is "
            "worse than declining it",
        )

    cell, table = _table_cell(tables, mpn=mpn, attribute=attribute)
    if cell is not None and table is not None:
        return _from_cell(
            layer,
            table,
            cell,
            attribute=attribute,
            klass=klass,
            sku_id=sku_id,
            doc_id=doc_id,
            revision_sha256=revision_sha256,
            class_uri=class_uri,
        )

    return _from_text_window(
        layer,
        mpn=mpn,
        attribute=attribute,
        klass=klass,
        sku_id=sku_id,
        doc_id=doc_id,
        revision_sha256=revision_sha256,
        class_uri=class_uri,
    )


# ------------------------------------------------------------------------------------------------
# The table path
# ------------------------------------------------------------------------------------------------


def _table_cell(
    tables: tuple[Table, ...], *, mpn: str, attribute: AuditAttribute
) -> tuple[Cell | None, Table | None]:
    """The cell for this MPN under a column this attribute claims, or ``(None, None)``.

    Row identity is matched **exactly**. A near match -- ``S201M-C16`` against ``S201M-C16UC`` --
    is a different product, and the entire value of an audit rests on never conflating two.
    """
    for table in tables:
        header = next((h for h in table.column_headers if attribute.matches_header(h)), None)
        if header is None:
            continue
        for row in table.rows:
            identity = next(
                (c for c in table.cells if c.row == row and c.text == mpn),
                None,
            )
            if identity is None:
                continue
            cell = table.cell(row, header)
            if cell is not None:
                # The row header carried with the evidence is the cell that *identifies* the row --
                # the type designation we matched -- not the row's leftmost non-empty cell. On
                # these ordering tables the leftmost cell is the merged pole count, and evidence
                # reading "row '16'" would tell a reviewer nothing about which product it came
                # from. The identity is the thing that gives the number its subject.
                return (
                    cell.__class__(
                        text=cell.text,
                        page=cell.page,
                        row=cell.row,
                        column=cell.column,
                        bbox=cell.bbox,
                        role=cell.role,
                        column_header=cell.column_header,
                        row_header=identity.text,
                        is_merged_source=cell.is_merged_source,
                    ),
                    table,
                )
    return None, None


def _from_cell(
    layer: TextLayer,
    table: Table,
    cell: Cell,
    *,
    attribute: AuditAttribute,
    klass: EtimClass | None,
    sku_id: str,
    doc_id: str,
    revision_sha256: str,
    class_uri: str,
) -> Derivation:
    words = layer.words_in_box(cell.page, cell.bbox)
    if not words:
        # The cell has text the canonical layer cannot locate. There is nothing to box, so there
        # is no claim to make: FR-3.2 is not a formality that can be satisfied with the cell
        # rectangle, because a reviewer clicking that box would be shown the column, not the value.
        return _abstain(
            attribute,
            sku_id,
            class_uri,
            DeclinedReason.NO_SPAN,
            f"the cell for {attribute.label!r} states {cell.text!r} but no word in the text layer "
            "falls inside it, so the value cannot be grounded to a span",
        )

    value = attribute.compose(cell.text, cell.column_header)
    rejection = _schema_violation(value, cell.text, attribute, klass)
    if rejection is not None:
        return _abstain(attribute, sku_id, class_uri, *rejection)

    evidence = [
        _evidence(
            layer,
            words,
            doc_id=doc_id,
            revision_sha256=revision_sha256,
            table_cell=cell.text,
            row_header=cell.row_header,
            column_header=cell.column_header,
        )
    ]

    header_cell = table.header_cell(cell.column_header)
    if header_cell is not None:
        header_words = layer.words_in_box(header_cell.page, header_cell.bbox)
        if header_words:
            # FR-7.3: the header is evidence in its own right, not a caption. It is stored as a
            # second Evidence so the console can box it, and so a stored claim still knows what
            # gave its number meaning long after the console has been rewritten.
            evidence.append(
                _evidence(
                    layer,
                    header_words,
                    doc_id=doc_id,
                    revision_sha256=revision_sha256,
                    table_cell=header_cell.text,
                    row_header="",
                    column_header=header_cell.text,
                )
            )

    claim = emit_extracted_claim(
        sku_id=sku_id,
        attribute_uri=attribute.uri,
        value_raw=value,
        evidence=tuple(evidence),
        extractor=fingerprint("table_cell"),
        class_uri=class_uri,
        confidence=_raw_confidence(attribute, method="table_cell", distance=0, candidates=1),
    )
    return Derivation(
        attribute=attribute,
        claim=claim,
        abstention=None,
        method="table_cell",
        raw_score=claim.confidence.raw_score or 0.0,
        candidates=1,
        distance=0,
        evidence=tuple(evidence),
    )


# ------------------------------------------------------------------------------------------------
# The text-window fallback
# ------------------------------------------------------------------------------------------------


def _from_text_window(
    layer: TextLayer,
    *,
    mpn: str,
    attribute: AuditAttribute,
    klass: EtimClass | None,
    sku_id: str,
    doc_id: str,
    revision_sha256: str,
    class_uri: str,
) -> Derivation:
    anchors = [i for i, w in enumerate(layer.words) if w.text == mpn]
    if not anchors:
        return _abstain(
            attribute,
            sku_id,
            class_uri,
            DeclinedReason.NO_SOURCE_DOCUMENT,
            f"{mpn!r} does not appear in {doc_id}; this document is not evidence about this "
            "product, and auditing against it would ground a value in the wrong page",
        )

    matches: list[tuple[int, int, Word]] = []
    for anchor in anchors:
        anchor_word = layer.words[anchor]
        band = layer.column_of(anchor_word)
        lo = max(0, anchor - WINDOW)
        hi = min(len(layer.words), anchor + WINDOW + 1)
        for index in range(lo, hi):
            if index == anchor:
                continue
            word = layer.words[index]
            if word.page != anchor_word.page:
                continue
            if band is not None and not band.contains(word):
                # FR-1.6: the candidate belongs to another column of the page, which means it
                # belongs to another product. Not a candidate -- and if it were the only one, the
                # honest result is an abstention, not the value next door.
                continue
            if attribute.value_pattern.match(word.text):
                matches.append((abs(index - anchor), index, word))

    if not matches:
        return _abstain(
            attribute,
            sku_id,
            class_uri,
            DeclinedReason.NO_SPAN,
            f"no token near {mpn!r} has the shape of a {attribute.label.lower()}; the value may "
            "well be in the document, but nothing here can be grounded",
        )

    distinct = {word.text for _distance, _index, word in matches}
    if len(distinct) > 1:
        # The window offers several different values and there is no table structure to say which
        # row owns them. Nearest-in-reading-order is a tie-break, not evidence, and a value picked
        # by tie-break becomes a *confident accusation* two steps later. This is the failure the
        # repository's ground rules put above all others: a fabricated finding costs the customer,
        # a decline costs coverage, and coverage is a number we publish.
        #
        # Found by the S200 M UC datasheet, whose ordering tables are typeset so that the table
        # pass cannot resolve them into columns: the running text reads "0.2 A 0.3 A 0.5 A ..." and
        # the fallback happily returned 0.3 for a 0.2 A device (finding N12).
        return _abstain(
            attribute,
            sku_id,
            class_uri,
            DeclinedReason.LAYOUT_UNREADABLE,
            f"the tables in {doc_id} did not resolve into columns, and the running text near "
            f"{mpn!r} offers {len(distinct)} competing values for {attribute.label.lower()} "
            f"({', '.join(sorted(distinct)[:5])}); there is nothing here that identifies which "
            "belongs to this product",
        )

    distance, _, word = min(matches, key=lambda m: (m[0], m[1]))
    value = word.text
    rejection = _schema_violation(value, value, attribute, klass)
    if rejection is not None:
        return _abstain(attribute, sku_id, class_uri, *rejection)

    evidence = (
        _evidence(
            layer,
            (word,),
            doc_id=doc_id,
            revision_sha256=revision_sha256,
            table_cell="",
            row_header=mpn,
            column_header="",
        ),
    )
    claim = emit_extracted_claim(
        sku_id=sku_id,
        attribute_uri=attribute.uri,
        value_raw=value,
        evidence=evidence,
        extractor=fingerprint("text_window"),
        class_uri=class_uri,
        confidence=_raw_confidence(
            attribute, method="text_window", distance=distance, candidates=len(matches)
        ),
    )
    return Derivation(
        attribute=attribute,
        claim=claim,
        abstention=None,
        method="text_window",
        raw_score=claim.confidence.raw_score or 0.0,
        candidates=len(matches),
        distance=distance,
        evidence=evidence,
    )


# ------------------------------------------------------------------------------------------------
# Shared parts
# ------------------------------------------------------------------------------------------------


def _evidence(
    layer: TextLayer,
    words: tuple[Word, ...],
    *,
    doc_id: str,
    revision_sha256: str,
    table_cell: str,
    row_header: str,
    column_header: str,
) -> Evidence:
    start = min(w.start for w in words)
    end = max(w.end for w in words)
    return Evidence(
        doc_id=doc_id,
        doc_revision_sha256=revision_sha256,
        page=words[0].page,
        char_span=(start, end),
        bbox=BBox(
            x0=min(w.x0 for w in words),
            y0=min(w.y0 for w in words),
            x1=max(w.x1 for w in words),
            y1=max(w.y1 for w in words),
        ),
        snippet=layer.snippet(start, end),
        extraction_layer_version=layer.layout_version,
        table_cell=table_cell,
        row_header=row_header,
        column_header=column_header,
    )


def _schema_violation(
    value: str, bare: str, attribute: AuditAttribute, klass: EtimClass | None
) -> tuple[DeclinedReason, str] | None:
    """FR-3.1: reject a value outside the class's declared value list before it becomes a claim.

    Only closed lists are checked, and only when the resolved class declares one. ETIM's numeric
    features carry a unit and no enumeration, so there is nothing to check against and pretending
    otherwise -- inventing a plausible range, say -- would be the audit asserting a constraint the
    standard does not state.
    """
    if klass is None or not attribute.etim_feature:
        return None
    feature = klass.feature(attribute.etim_feature)
    if feature is None or not feature.is_closed_list:
        return None

    permitted = {v.description.strip().lower() for v in feature.values}
    if bare.strip().lower() in permitted or value.strip().lower() in permitted:
        return None
    return (
        DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR,
        f"{value!r} is not in the value list ETIM declares for {feature.description!r} on "
        f"{klass.class_id} ({', '.join(sorted(v.description for v in feature.values)[:6])}...); "
        "rejected before it could become a claim (FR-3.1)",
    )


def _raw_confidence(
    attribute: AuditAttribute, *, method: str, distance: int, candidates: int
):
    """A raw score from what the extractor can observe. **Never a probability.**

    Three signals, none of which requires knowing the answer:

    * **where it came from** -- a value read out of the cell whose row is the MPN and whose column
      is the mapped header is a different kind of evidence from a token that happened to be nearby;
    * **pattern specificity** -- ``2CDS271061R0065`` can only be an order code, ``6`` could be four
      different attributes;
    * **distance and contention** in the fallback path -- a token further from the anchor, or one
      of several matching tokens, is a choice rather than a find, and a choice is less certain.

    Deliberately not fitted to the outcome. A score tuned until the risk-coverage curve looked good
    would be reporting how well it was tuned.
    """
    from errata_spec import Confidence

    if method == "table_cell":
        raw = 0.6 + 0.4 * attribute.specificity
    else:
        proximity = 1.0 / (1.0 + 0.25 * distance)
        contention = 1.0 / max(1, candidates) ** 0.5
        raw = 0.6 * attribute.specificity * proximity * contention
    return Confidence(raw_score=round(min(1.0, max(0.0, raw)), 4))


def _abstain(
    attribute: AuditAttribute,
    sku_id: str,
    class_uri: str,
    reason: DeclinedReason,
    detail: str,
) -> Derivation:
    abstention = emit_abstention(
        sku_id=sku_id,
        attribute_uri=attribute.uri,
        reason=reason,
        detail=detail,
        class_uri=class_uri,
        extractor=fingerprint(),
    )
    return Derivation(
        attribute=attribute, claim=None, abstention=abstention, method="", raw_score=0.0
    )
