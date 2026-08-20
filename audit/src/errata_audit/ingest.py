"""FR-1.1 -- catalog ingest, with the original strings preserved exactly.

    "Round-trips without value mutation; original strings preserved verbatim."

That acceptance criterion is stricter than it sounds and it is the reason this module does almost
nothing. Every tempting convenience -- stripping whitespace, upper-casing a unit, collapsing
``6.0`` to ``6``, reading ``1,000`` as a thousand -- destroys the evidence the audit is about to
be asked to judge. A catalog value with a trailing non-breaking space *is a defect*, and an
ingester that tidies it away has hidden the finding and then reported that nothing was wrong.

So: values arrive as strings and are stored as strings, byte for byte. Normalisation happens
exactly once, later, inside ``errata_valuesem``, where it is deterministic, versioned and
reversible to the raw form (:attr:`CatalogRecord.raw`) that produced it.

The one thing this module does decide is **which columns are attributes**. Identity columns
(``sku``, ``mpn``, ``manufacturer``) and the optional ``datasheet`` pointer are structural; every
other column is an attribute under audit. Anything the reader might expect to be inferred -- units
from a header, a class from a description -- is not inferred here.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "IDENTITY_FIELDS",
    "CatalogRecord",
    "load_catalog",
    "record_from_mapping",
]

#: Columns that describe *which product this is* rather than *what it claims about itself*.
#: Everything outside this set is an attribute under audit, which is why the set is small,
#: explicit, and not extensible by configuration: a customer able to declare a column
#: "structural" could quietly exclude the attribute their catalog is worst at.
IDENTITY_FIELDS: frozenset[str] = frozenset({"sku", "sku_id", "mpn", "manufacturer", "datasheet"})


class CatalogRecord(BaseModel):
    """One product as the catalog states it. The thing under audit -- never modified."""

    model_config = ConfigDict(frozen=True)

    sku_id: str
    mpn: str = ""
    manufacturer: str = ""

    attributes: dict[str, str] = Field(default_factory=dict)
    """Attribute key -> the catalog's own string, verbatim. Values are never coerced to numbers:
    a catalog holding ``"06"`` and a catalog holding ``"6"`` are making two different statements
    about how carefully it was maintained, and both survive to the comparator."""

    datasheet: str = ""
    """Optional per-row pointer to the source document. A URL or a path; resolved at ingest time
    by :func:`errata_audit.documents.ingest_document`, not here."""

    feed: str = ""
    row_number: int | None = None
    """Where this came from, for the ledger. A finding a customer disputes has to be traceable to
    a line of a file they sent."""

    @model_validator(mode="after")
    def _identity_is_present(self) -> CatalogRecord:
        if not self.sku_id.strip():
            raise ValueError(
                "a catalog record needs an identifier: without one, a redline cannot be addressed "
                "to a product and a claim cannot be filed against anything"
            )
        return self

    @property
    def raw(self) -> dict[str, str]:
        """The attribute map exactly as ingested. Named to be obvious at the call site."""
        return dict(self.attributes)

    def value(self, attribute: str) -> str | None:
        """The catalog's string for one attribute, or ``None`` when the column is absent.

        ``None`` (column absent) and ``""`` (column present and blank) are different facts: the
        first is a catalog that never carried the attribute, the second is a catalog that carries
        it and left it empty, and only the second is a fill-rate finding
        (``CATALOG_NULL_EVIDENCE_PRESENT``). Collapsing them would silently convert a schema gap
        into a data defect.
        """
        return self.attributes.get(attribute)


def record_from_mapping(
    row: Mapping[str, Any], *, feed: str = "", row_number: int | None = None
) -> CatalogRecord:
    """Build a record from one CSV row or JSON object.

    Keys are matched case-insensitively -- feeds disagree about ``SKU`` versus ``sku`` and that is
    not a data quality signal -- but *values* are untouched.
    """
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    attributes = {
        str(key): _as_text(value)
        for key, value in row.items()
        if str(key).strip().lower() not in IDENTITY_FIELDS
    }
    return CatalogRecord(
        sku_id=_as_text(lowered.get("sku_id") or lowered.get("sku") or lowered.get("mpn") or ""),
        mpn=_as_text(lowered.get("mpn", "")),
        manufacturer=_as_text(lowered.get("manufacturer", "")),
        datasheet=_as_text(lowered.get("datasheet", "")),
        attributes=attributes,
        feed=feed,
        row_number=row_number,
    )


def load_catalog(path: Path | str, *, feed: str = "") -> tuple[CatalogRecord, ...]:
    """Load a catalog from CSV, JSON, JSON Lines or YAML.

    The format is chosen by suffix. A file whose suffix promises one thing and whose contents are
    another fails here rather than producing an empty catalog and a clean exit -- an audit that
    silently found no products to audit is the worst possible success.
    """
    path = Path(path)
    label = feed or path.name
    suffix = path.suffix.lower()

    if suffix in {".csv", ".tsv"}:
        return tuple(_load_delimited(path, feed=label))
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return tuple(_load_json(path, feed=label))
    if suffix in {".yaml", ".yml"}:
        return tuple(_load_yaml(path, feed=label))
    raise ValueError(
        f"unsupported catalog format {suffix!r} for {path}; expected .csv, .tsv, .json, .jsonl "
        "or .yaml"
    )


def _load_delimited(path: Path, *, feed: str) -> Iterator[CatalogRecord]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    # newline="" per the csv module's contract; utf-8-sig because a catalog exported from Excel
    # carries a BOM and a first column named "﻿sku" matches nothing.
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle, delimiter=delimiter), start=1):
            yield record_from_mapping(row, feed=feed, row_number=index)


def _load_json(path: Path, *, feed: str) -> Iterator[CatalogRecord]:
    text = path.read_text("utf-8")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows: list[Any] = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        payload = json.loads(text)
        rows = payload if isinstance(payload, list) else [payload]
    for index, row in enumerate(rows, start=1):
        yield record_from_mapping(row, feed=feed, row_number=index)


def _load_yaml(path: Path, *, feed: str) -> Iterator[CatalogRecord]:
    payload = yaml.safe_load(path.read_text("utf-8")) or []
    rows = payload if isinstance(payload, list) else [payload]
    for index, row in enumerate(rows, start=1):
        yield record_from_mapping(row, feed=feed, row_number=index)


def _as_text(value: Any) -> str:
    """Every ingested value becomes a string, and nothing else happens to it.

    ``None`` becomes ``""`` -- a JSON null and an empty CSV cell are the same statement, "this
    field is blank" -- and a number that arrived as a number keeps the shape JSON gave it. Note
    that a JSON ``6.0`` is already lossy before this code sees it; a feed that cares about the
    difference should send strings, and the run report says so.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
