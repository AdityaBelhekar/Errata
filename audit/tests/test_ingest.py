"""FR-1.1 -- catalog ingest preserves the original strings, exactly.

    "Round-trips without value mutation; original strings preserved verbatim."

Every test here is a tidying-up this module must refuse to do. They look pedantic in isolation and
each one is a defect the audit would otherwise hide: a trailing space that breaks a punchout feed, a
``6.0`` that the customer's ERP writes as ``6``, a thousands separator that means different things
in two locales. The ingester's job is to hand the comparator what the catalog actually says.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from errata_audit.ingest import CatalogRecord, load_catalog, record_from_mapping


def test_values_are_preserved_byte_for_byte() -> None:
    record = record_from_mapping(
        {"sku": "AX-10", "rated_current": "  16 A ", "weight": "0.125000"}
    )
    assert record.value("rated_current") == "  16 A "
    assert record.value("weight") == "0.125000"


def test_a_trailing_space_is_data_not_noise() -> None:
    """A value that differs only by whitespace is a value the feed got wrong somewhere upstream."""
    record = record_from_mapping({"sku": "AX-10", "poles": "1 "})
    assert record.value("poles") != "1"


def test_identity_columns_are_not_attributes() -> None:
    record = record_from_mapping(
        {"sku": "AX-10", "mpn": "AX-10", "manufacturer": "ACME", "datasheet": "x.pdf", "poles": "1"}
    )
    assert set(record.attributes) == {"poles"}
    assert record.mpn == "AX-10"
    assert record.datasheet == "x.pdf"


def test_a_missing_column_and_a_blank_cell_are_different_facts() -> None:
    """A schema gap and a fill-rate defect must never collapse into each other.

    ``None`` means the feed never carried the attribute; ``""`` means it carried it and left it
    empty. Only the second is a finding, and an ingester that returned ``""`` for both would let
    the audit manufacture a SEV-2 out of a customer's decision not to send a column.
    """
    record = record_from_mapping({"sku": "AX-10", "poles": ""})
    assert record.value("poles") == ""
    assert record.value("rated_current") is None


def test_keys_match_case_insensitively_but_values_do_not_change() -> None:
    record = record_from_mapping({"SKU": "AX-10", "MPN": "AX-10", "Rated_Current": "16 A"})
    assert record.sku_id == "AX-10"
    assert record.value("Rated_Current") == "16 A"


def test_a_record_without_an_identifier_is_refused() -> None:
    with pytest.raises(ValueError, match="identifier"):
        record_from_mapping({"rated_current": "16 A"})


def test_csv_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "c.csv"
    path.write_text("sku,rated_current\nAX-10,16 A\nAX-16,\"1,000 A\"\n", "utf-8")
    records = load_catalog(path)
    assert [r.sku_id for r in records] == ["AX-10", "AX-16"]
    assert records[1].value("rated_current") == "1,000 A"
    assert records[0].row_number == 1


def test_an_excel_byte_order_mark_does_not_rename_the_first_column(tmp_path: Path) -> None:
    path = tmp_path / "c.csv"
    path.write_bytes("﻿sku,poles\nAX-10,1\n".encode())
    assert load_catalog(path)[0].sku_id == "AX-10"


def test_json_and_jsonl(tmp_path: Path) -> None:
    rows = [{"sku": "AX-10", "poles": 1}, {"sku": "AX-16", "poles": None}]
    (tmp_path / "c.json").write_text(json.dumps(rows), "utf-8")
    (tmp_path / "c.jsonl").write_text("\n".join(json.dumps(r) for r in rows), "utf-8")

    for name in ("c.json", "c.jsonl"):
        records = load_catalog(tmp_path / name)
        assert [r.sku_id for r in records] == ["AX-10", "AX-16"]
        # A JSON number arrives as a number and is stringified; a null is a blank cell.
        assert records[0].value("poles") == "1"
        assert records[1].value("poles") == ""


def test_an_unknown_format_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "c.xlsx"
    path.write_bytes(b"not a catalog")
    with pytest.raises(ValueError, match="unsupported catalog format"):
        load_catalog(path)


def test_a_record_is_immutable() -> None:
    record = record_from_mapping({"sku": "AX-10", "poles": "1"})
    with pytest.raises(ValidationError):
        record.sku_id = "AX-16"  # type: ignore[misc]


def test_raw_is_a_copy_so_a_caller_cannot_edit_the_catalog_under_audit() -> None:
    record = record_from_mapping({"sku": "AX-10", "poles": "1"})
    raw = record.raw
    raw["poles"] = "4"
    assert record.value("poles") == "1"


def test_the_record_type_carries_provenance() -> None:
    record = CatalogRecord(sku_id="AX-10", feed="acme-2026-08", row_number=42)
    assert (record.feed, record.row_number) == ("acme-2026-08", 42)
