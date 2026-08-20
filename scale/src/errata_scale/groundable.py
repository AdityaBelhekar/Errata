"""FR-8.1 -- the Groundable Fraction Report: what *can* be audited, stated before anything is.

    "Catalog inventoried against retrievable evidence before any audit, broken down by source type
    and reason." -- "Percentages sum; every bucket is enumerable to record level."

This is the first thing R2 runs and it is deliberately the first thing a customer sees, because
the number it produces is the one an audit vendor is most tempted to leave out. A report that says
*"we found 412 defects"* over a catalog where 94% of records had no retrievable document has told
the customer almost nothing: they cannot tell whether the remaining 6% was the healthy part of the
catalog or the sick one, and they cannot tell what buying more coverage would cost.

So the inventory runs **before** the audit, over the whole feed, and it is arithmetic rather than
judgment: every record lands in exactly one bucket, the buckets are enumerable to record level,
and the counts sum to the record count. There is no "other".

Three design rules, each of which someone will eventually propose relaxing:

* **A record with no retrievable document is not dropped and is not a defect.** It is a
  *document-recovery lead* (SS2.3): the highest-value thing a customer can do to raise their own
  coverage, and a number they can act on. Reporting it as a data-quality finding would be blaming
  the customer for a gap in our inputs.
* **Buckets are assigned from what is in hand, not from what a URL promises.** A record naming a
  datasheet nobody supplied is ``DOCUMENT_NAMED_NOT_SUPPLIED``, never ``GROUNDABLE``, because a
  groundable fraction computed from intentions is a forecast wearing a measurement's clothes.
* **Readability is probed, not assumed.** A PDF whose bytes are in the blob store but which
  carries no text layer is a scan, and R1 declines scans (FR-1.4). Counting it as groundable
  would overstate the fraction by exactly the population that will later decline.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from errata_audit import CatalogRecord, DocumentSource
from errata_spec import DeclinedReason

__all__ = [
    "GroundableFractionReport",
    "GroundingStatus",
    "RecordGrounding",
    "SourceType",
    "inventory",
    "text_layer_probe",
]


class SourceType(str, enum.Enum):
    """Where a record's evidence would come from. FR-8.1 asks for the breakdown by source type."""

    MANUFACTURER_DOCUMENT = "manufacturer_document"
    """A datasheet, ordering table or manual published by the maker of the product."""

    NONE_NAMED = "none_named"
    """The feed points at nothing. Not the same as pointing at something we do not have."""


class GroundingStatus(str, enum.Enum):
    """Exactly one per record. The set is closed and there is no ``other`` bucket."""

    GROUNDABLE = "groundable"
    """A document is named, its bytes are in hand, and it carries a readable text layer."""

    DOCUMENT_NAMED_NOT_SUPPLIED = "document_named_not_supplied"
    """The feed names a document that was not supplied to the run. A recovery lead, not a defect."""

    DOCUMENT_UNREADABLE = "document_unreadable"
    """Bytes in hand, no text layer -- a scan. R1 declines these, and so must the forecast."""

    NO_DOCUMENT_NAMED = "no_document_named"
    """The feed carries no pointer and no single document covers the run."""

    @property
    def declined_reason(self) -> DeclinedReason | None:
        """The reason the audit would give for this record, so forecast and audit speak one language."""
        return {
            GroundingStatus.DOCUMENT_NAMED_NOT_SUPPLIED: DeclinedReason.NO_SOURCE_DOCUMENT,
            GroundingStatus.NO_DOCUMENT_NAMED: DeclinedReason.NO_SOURCE_DOCUMENT,
            GroundingStatus.DOCUMENT_UNREADABLE: DeclinedReason.LAYOUT_UNREADABLE,
        }.get(self)

    @property
    def sentence(self) -> str:
        return {
            GroundingStatus.GROUNDABLE: "a source document is in hand and readable",
            GroundingStatus.DOCUMENT_NAMED_NOT_SUPPLIED: (
                "the feed names a document that was not supplied to this run"
            ),
            GroundingStatus.DOCUMENT_UNREADABLE: (
                "in hand but with no text layer -- a scan, and there is no OCR"
            ),
            GroundingStatus.NO_DOCUMENT_NAMED: "the feed names no source document for this record",
        }[self]


@dataclass(frozen=True, slots=True)
class RecordGrounding:
    """One record's place in the inventory. Enumerable to record level is a hard requirement."""

    sku_id: str
    row_number: int | None
    status: GroundingStatus
    source_type: SourceType
    document_id: str = ""
    document_sha256: str = ""
    named: str = ""
    """What the feed pointed at, verbatim -- so a recovery lead is actionable rather than a count."""

    @property
    def is_groundable(self) -> bool:
        return self.status is GroundingStatus.GROUNDABLE


def text_layer_probe(document: DocumentSource) -> bool:
    """Default readability probe: does this document yield any text at all?

    Imported lazily so the inventory can be computed, and tested, without exercising PyMuPDF on
    every call site.
    """
    from errata_audit import extract_layer

    try:
        layer = extract_layer(document.path, document_sha256=document.sha256)
    except Exception:
        return False
    return bool(getattr(layer, "text", "").strip())


@dataclass(frozen=True, slots=True)
class GroundableFractionReport:
    """The inventory. Counts, fractions, and the records behind each one."""

    records: tuple[RecordGrounding, ...]
    catalog: str = ""
    documents_supplied: int = 0

    @property
    def total(self) -> int:
        return len(self.records)

    def counts(self) -> dict[GroundingStatus, int]:
        """Every status, including the zeroes. A bucket that vanishes when empty is a bucket the
        reader cannot tell was considered."""
        out = {status: 0 for status in GroundingStatus}
        for record in self.records:
            out[record.status] += 1
        return out

    def records_in(self, status: GroundingStatus) -> tuple[RecordGrounding, ...]:
        """FR-8.1: every bucket is enumerable to record level."""
        return tuple(record for record in self.records if record.status is status)

    def by_source_type(self) -> dict[SourceType, int]:
        out = {source: 0 for source in SourceType}
        for record in self.records:
            out[record.source_type] += 1
        return out

    def by_reason(self) -> dict[str, int]:
        """The declined reasons this inventory forecasts, in the audit's own vocabulary."""
        out: dict[str, int] = {}
        for record in self.records:
            reason = record.status.declined_reason
            if reason is None:
                continue
            out[reason.value] = out.get(reason.value, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    @property
    def groundable(self) -> int:
        return self.counts()[GroundingStatus.GROUNDABLE]

    @property
    def groundable_fraction(self) -> float:
        return self.groundable / self.total if self.total else 0.0

    def exact_fractions(self) -> dict[GroundingStatus, Fraction]:
        """Fractions as exact rationals.

        Float percentages do not sum to 1.0 and never will; the acceptance criterion "percentages
        sum" is therefore checked on rationals, and the rendered percentages are rounded from
        these. A report whose own arithmetic is approximate has no business auditing anyone.
        """
        if not self.total:
            return {status: Fraction(0) for status in GroundingStatus}
        return {status: Fraction(count, self.total) for status, count in self.counts().items()}

    def percentages_sum(self) -> bool:
        return not self.total or sum(self.exact_fractions().values()) == Fraction(1)

    def recovery_leads(self) -> tuple[tuple[str, int], ...]:
        """Named-but-missing documents, by how many records each would unlock.

        This is the SS2.3 document-recovery queue and it is the most actionable output of the whole
        report: one PDF at the top of this list buys more coverage than any model change.
        """
        counts: dict[str, int] = {}
        for record in self.records_in(GroundingStatus.DOCUMENT_NAMED_NOT_SUPPLIED):
            key = record.named or "(unnamed)"
            counts[key] = counts.get(key, 0) + 1
        return tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def as_dict(self) -> dict[str, object]:
        return {
            "catalog": self.catalog,
            "records": self.total,
            "documents_supplied": self.documents_supplied,
            "groundable_fraction": round(self.groundable_fraction, 6),
            "counts": {status.value: count for status, count in self.counts().items()},
            "by_source_type": {
                source.value: count for source, count in self.by_source_type().items()
            },
            "forecast_declined_by_reason": self.by_reason(),
            "recovery_leads": [
                {"document": name, "records_unlocked": count}
                for name, count in self.recovery_leads()[:20]
            ],
            "percentages_sum": self.percentages_sum(),
        }

    def text(self) -> str:
        lines = [
            f"GROUNDABLE FRACTION -- {self.total:,} record(s) from {self.catalog or 'the feed'}",
            f"{self.documents_supplied} document(s) supplied to this run",
            "",
        ]
        counts = self.counts()
        for status in GroundingStatus:
            count = counts[status]
            share = (count / self.total * 100) if self.total else 0.0
            lines.append(f"  {status.value:30s} {count:8,d}  {share:6.2f}%  {status.sentence}")
        lines.append("")
        lines.append(f"  groundable fraction          {self.groundable_fraction:.2%}")
        leads = self.recovery_leads()
        if leads:
            lines.append("")
            lines.append("  document-recovery leads (one document, this many records unlocked)")
            for name, count in leads[:10]:
                lines.append(f"    {count:8,d}  {name}")
        return "\n".join(lines)


def inventory(
    records: Sequence[CatalogRecord],
    documents: Mapping[str, DocumentSource] | Iterable[DocumentSource],
    *,
    catalog: str = "",
    probe: Callable[[DocumentSource], bool] | None = text_layer_probe,
) -> GroundableFractionReport:
    """Inventory a catalog against the evidence actually in hand, before any audit runs.

    ``documents`` is keyed by file name, matching how :mod:`errata_audit.cli` resolves a record's
    ``datasheet`` pointer; an iterable is accepted and keyed the same way. When exactly one
    document is supplied and a record names none, that document covers the record -- the same
    single-document convenience the R1 CLI applies, kept identical here so the forecast and the
    audit cannot drift apart.
    """
    supplied = _key_documents(documents)
    digests = {document.sha256 for document in supplied.values()}
    readable: dict[str, bool] = {}
    if probe is not None:
        for document in supplied.values():
            if document.sha256 not in readable:
                readable[document.sha256] = probe(document)

    only = next(iter(supplied.values())) if len(digests) == 1 else None

    out: list[RecordGrounding] = []
    for record in records:
        named = record.datasheet.strip()
        document: DocumentSource | None = None
        if named:
            document = supplied.get(_basename(named))
        elif only is not None:
            document = only

        if document is None:
            out.append(
                RecordGrounding(
                    sku_id=record.sku_id,
                    row_number=record.row_number,
                    status=(
                        GroundingStatus.DOCUMENT_NAMED_NOT_SUPPLIED
                        if named
                        else GroundingStatus.NO_DOCUMENT_NAMED
                    ),
                    source_type=(
                        SourceType.MANUFACTURER_DOCUMENT if named else SourceType.NONE_NAMED
                    ),
                    named=named,
                )
            )
            continue

        is_readable = readable.get(document.sha256, True)
        out.append(
            RecordGrounding(
                sku_id=record.sku_id,
                row_number=record.row_number,
                status=(
                    GroundingStatus.GROUNDABLE
                    if is_readable
                    else GroundingStatus.DOCUMENT_UNREADABLE
                ),
                source_type=SourceType.MANUFACTURER_DOCUMENT,
                document_id=document.doc_id,
                document_sha256=document.sha256,
                named=named,
            )
        )

    return GroundableFractionReport(
        records=tuple(out), catalog=catalog, documents_supplied=len(digests)
    )


def _key_documents(
    documents: Mapping[str, DocumentSource] | Iterable[DocumentSource],
) -> dict[str, DocumentSource]:
    if isinstance(documents, Mapping):
        return {_basename(key): value for key, value in documents.items()}
    keyed: dict[str, DocumentSource] = {}
    for document in documents:
        keyed[_basename(document.path.name)] = document
        if document.source_url:
            keyed.setdefault(_basename(document.source_url), document)
    return keyed


def _basename(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1].strip()
