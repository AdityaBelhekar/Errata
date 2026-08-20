"""FR-8.1 -- the Groundable Fraction Report.

    "Percentages sum; every bucket is enumerable to record level."

Both halves of that acceptance criterion are load-bearing and both are tested here. The first is
arithmetic and is checked on exact rationals rather than floats, because a report whose buckets
sum to 99.97% has a bucket it is not telling you about. The second is what stops the report being
a dashboard: a customer who is told 9,723 records have no document must be able to get the list.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest
from scalefixtures import catalog_of, row  # noqa: F401

from errata_audit import DocumentSource, load_catalog
from errata_scale import GroundingStatus, SourceType, inventory
from errata_spec import DeclinedReason, DocumentRevision, sha256_bytes


def _document(path: Path, name: str = "sheet.pdf") -> DocumentSource:
    payload = f"%PDF-1.4 {name}".encode()
    path.write_bytes(payload)
    return DocumentSource(
        doc_id=name,
        revision=DocumentRevision(
            sha256=sha256_bytes(payload),
            doc_id=name,
            byte_length=len(payload),
            media_type="application/pdf",
        ),
        path=path,
        source_url=f"https://example.invalid/{name}",
    )


def test_every_record_lands_in_exactly_one_bucket_and_the_counts_sum(catalog_of, tmp_path):
    catalog = catalog_of(
        [
            row("A", datasheet="sheet.pdf"),
            row("B", datasheet="missing.pdf"),
            row("C"),
            row("D"),
        ]
    )
    records = load_catalog(catalog)
    report = inventory(
        records,
        {"sheet.pdf": _document(tmp_path / "sheet.pdf")},
        catalog=catalog.name,
        probe=lambda _document: True,
    )

    assert report.total == 4
    assert sum(report.counts().values()) == 4
    assert report.percentages_sum()
    assert sum(report.exact_fractions().values()) == Fraction(1)


def test_percentages_sum_exactly_on_a_population_floats_cannot_represent(catalog_of, tmp_path):
    """Three records is the classic case: 1/3 is not representable and 33.33% x 3 is not 100%."""
    catalog = catalog_of([row("A", datasheet="sheet.pdf"), row("B"), row("C")])
    report = inventory(
        load_catalog(catalog),
        {"sheet.pdf": _document(tmp_path / "sheet.pdf")},
        probe=lambda _document: True,
    )
    assert report.percentages_sum()
    assert sum(report.exact_fractions().values()) == Fraction(1)


def test_every_bucket_is_enumerable_to_record_level(catalog_of, tmp_path):
    catalog = catalog_of(
        [row("A", datasheet="sheet.pdf"), row("B", datasheet="gone.pdf"), row("C")]
    )
    # Two documents supplied, so the single-document convenience below is off and a record naming
    # nothing genuinely has nothing.
    report = inventory(
        load_catalog(catalog),
        {
            "sheet.pdf": _document(tmp_path / "sheet.pdf"),
            "other.pdf": _document(tmp_path / "other.pdf", "other.pdf"),
        },
        probe=lambda _document: True,
    )

    assert [r.sku_id for r in report.records_in(GroundingStatus.GROUNDABLE)] == ["A"]
    assert [
        r.sku_id for r in report.records_in(GroundingStatus.DOCUMENT_NAMED_NOT_SUPPLIED)
    ] == ["B"]
    assert [r.sku_id for r in report.records_in(GroundingStatus.NO_DOCUMENT_NAMED)] == ["C"]
    # and the enumeration carries what a recovery lead needs to be actionable
    assert report.records_in(GroundingStatus.DOCUMENT_NAMED_NOT_SUPPLIED)[0].named == "gone.pdf"


def test_a_named_but_unsupplied_document_is_never_counted_as_groundable(catalog_of):
    """A groundable fraction computed from intentions is a forecast wearing a measurement's coat."""
    catalog = catalog_of([row("A", datasheet="https://example.invalid/never-fetched.pdf")])
    report = inventory(load_catalog(catalog), {})
    assert report.groundable == 0
    assert report.counts()[GroundingStatus.DOCUMENT_NAMED_NOT_SUPPLIED] == 1
    assert report.by_source_type()[SourceType.MANUFACTURER_DOCUMENT] == 1


def test_an_unreadable_document_is_not_groundable(catalog_of, tmp_path):
    """A scan is in hand and cannot be read. Counting it would overstate the fraction by exactly
    the population that later declines."""
    catalog = catalog_of([row("A", datasheet="scan.pdf")])
    report = inventory(
        load_catalog(catalog),
        {"scan.pdf": _document(tmp_path / "scan.pdf", "scan.pdf")},
        probe=lambda _document: False,
    )
    assert report.groundable == 0
    assert report.counts()[GroundingStatus.DOCUMENT_UNREADABLE] == 1
    assert report.by_reason() == {DeclinedReason.LAYOUT_UNREADABLE.value: 1}


def test_one_supplied_document_covers_records_that_name_none(catalog_of, tmp_path):
    """The same single-document convenience the R1 CLI applies. Kept identical on purpose: a
    forecast that disagreed with the audit about which records have evidence would be worse than
    no forecast."""
    catalog = catalog_of([row("A"), row("B")])
    report = inventory(
        load_catalog(catalog),
        {"sheet.pdf": _document(tmp_path / "sheet.pdf")},
        probe=lambda _document: True,
    )
    assert report.groundable == 2


def test_the_single_document_convenience_is_the_r1_rule_and_is_stated_as_a_trade(
    catalog_of, tmp_path
):
    """One document and a record naming none: the record is groundable.

    This is exactly ``errata_audit.cli``'s rule and exactly what ``run_catalog`` does at T1, and it
    is kept identical so the forecast and the audit cannot disagree about which records have
    evidence. The cost is real and worth naming: a 10,000-row feed with one PDF supplied will
    forecast 10,000 groundable records and then decline most of them at T1. The alternative --
    a forecast that used a different rule from the audit -- is worse, because then neither number
    can be checked against the other.
    """
    catalog = catalog_of([row("A"), row("B", datasheet="named.pdf")])
    report = inventory(
        load_catalog(catalog),
        {"sheet.pdf": _document(tmp_path / "sheet.pdf")},
        probe=lambda _document: True,
    )
    assert [r.sku_id for r in report.records_in(GroundingStatus.GROUNDABLE)] == ["A"]
    assert [
        r.sku_id for r in report.records_in(GroundingStatus.DOCUMENT_NAMED_NOT_SUPPLIED)
    ] == ["B"]


def test_two_supplied_documents_do_not_cover_records_that_name_none(catalog_of, tmp_path):
    """With a choice to make, the inventory refuses to make it. Guessing here would let the audit
    ground a record against another manufacturer's PDF."""
    catalog = catalog_of([row("A")])
    report = inventory(
        load_catalog(catalog),
        {
            "one.pdf": _document(tmp_path / "one.pdf", "one.pdf"),
            "two.pdf": _document(tmp_path / "two.pdf", "two.pdf"),
        },
        probe=lambda _document: True,
    )
    assert report.groundable == 0
    assert report.counts()[GroundingStatus.NO_DOCUMENT_NAMED] == 1


def test_recovery_leads_rank_documents_by_records_unlocked(catalog_of):
    catalog = catalog_of(
        [
            row("A", datasheet="big.pdf"),
            row("B", datasheet="big.pdf"),
            row("C", datasheet="big.pdf"),
            row("D", datasheet="small.pdf"),
        ]
    )
    report = inventory(load_catalog(catalog), {})
    assert report.recovery_leads() == (("big.pdf", 3), ("small.pdf", 1))


def test_an_empty_catalog_does_not_divide_by_zero():
    report = inventory([], {})
    assert report.total == 0
    assert report.groundable_fraction == 0.0
    assert report.percentages_sum()


@pytest.mark.parametrize("status", list(GroundingStatus))
def test_every_status_says_what_it_means_and_names_its_declined_reason(status):
    assert status.sentence
    if status is GroundingStatus.GROUNDABLE:
        assert status.declined_reason is None
    else:
        assert status.declined_reason is not None
