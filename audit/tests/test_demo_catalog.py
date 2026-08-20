"""The demonstration catalog, and the properties that keep it from becoming a lie.

`bench/tests/test_demo.py` fences the R0 demo the same way and for the same reason: a demo is the
artefact most likely to drift into flattery, because nobody's build breaks when it does.

Two kinds of test here.

**Integrity.** Every row's SKU exists in the datasheet, the provenance file says out loud that the
catalog is constructed, and the mutation is reproducible from the SKU list alone.

**The sweep.** The audit is run over all 278 rows and the outcome is compared against what each
row's injection intended. It takes about twenty seconds and it is the single most informative test
in the package, because it pins the two numbers that matter in opposite directions: **every
injected defect is raised, and nothing else is.** The equivalence traps are the point -- a weight in
grams, a pole count written ``1P``, ``Each`` against a pack of one. A detection demo with no traps
reports a precision that has never been tested.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml
from conftest import ABB_S200, DATASHEETS, etim_archive, requires_datasheets, requires_etim

import errata_audit
from errata_audit.attributes import load_attributes
from errata_audit.audit import audit_sku
from errata_audit.classify import load_scope
from errata_audit.documents import BlobStore, ingest_document
from errata_audit.etim import load_etim
from errata_audit.ingest import load_catalog
from errata_audit.tables import extract_tables
from errata_spec import DocumentRegister

DEMO = Path(errata_audit.__file__).parent / "demo"
CATALOG = DEMO / "catalog.csv"
PROVENANCE = DEMO / "provenance.yaml"


@pytest.fixture(scope="module")
def provenance() -> dict:
    return yaml.safe_load(PROVENANCE.read_text("utf-8"))


def test_the_provenance_file_says_the_catalog_is_constructed(provenance) -> None:
    warning = provenance["warning"]
    assert "THE CATALOG IS CONSTRUCTED" in warning
    assert "hash-registered" in warning
    assert provenance["source_document"]


def test_every_row_declares_what_a_reviewer_should_say_about_it(provenance) -> None:
    """The ground truth the sweep is scored against. A row whose intent is only inferable from the
    generator's source is a row nobody can check."""
    for row in provenance["rows"]:
        assert row["kind"] in {"correct", "defect", "equivalent", "gap", "declined_expected"}
        assert row["expected"].strip()


def test_the_catalog_and_the_provenance_describe_the_same_rows(provenance) -> None:
    catalog = {record.sku_id for record in load_catalog(CATALOG)}
    assert catalog == {row["sku"] for row in provenance["rows"]}


def test_the_traps_are_present_and_numerous(provenance) -> None:
    """FR-5.3 calls semantic equivalence the highest-consequence requirement in the PRD. A demo
    that contained no equivalence traps would report a precision nobody had tested."""
    kinds = Counter(row["kind"] for row in provenance["rows"])
    assert kinds["equivalent"] >= 20
    assert kinds["defect"] >= 20
    assert kinds["declined_expected"] >= 3


@requires_datasheets
def test_every_catalog_sku_exists_in_the_datasheet() -> None:
    """Except the three that are supposed not to. A demo SKU that quietly does not exist would
    make the audit look like it declined for a subtle reason when it declined for a silly one."""
    known = {
        cell.text
        for table in extract_tables(ABB_S200)
        if "Type" in table.column_headers
        for cell in table.cells
        if cell.column_header == "Type"
    }
    provenance = yaml.safe_load(PROVENANCE.read_text("utf-8"))
    expected_missing = {
        row["sku"] for row in provenance["rows"] if row["kind"] == "declined_expected"
    }
    for record in load_catalog(CATALOG):
        if record.sku_id in expected_missing:
            continue
        assert record.sku_id in known, f"{record.sku_id} is not in the datasheet"


@requires_etim
@requires_datasheets
def test_the_sweep_raises_every_injected_defect_and_nothing_else() -> None:
    register = DocumentRegister()
    store = BlobStore(Path(errata_audit.__file__).parents[3] / "var" / "audit" / "blobs")
    documents = {
        path.name: ingest_document(path, register=register, store=store)
        for path in sorted(DATASHEETS.glob("*.pdf"))
    }
    scope = load_scope()
    etim = load_etim(etim_archive(), release="10.0", class_ids=scope.as_set)
    attributes = load_attributes()
    provenance = yaml.safe_load(PROVENANCE.read_text("utf-8"))
    kinds = {row["sku"]: row["kind"] for row in provenance["rows"]}

    raised: list[str] = []
    silent: list[str] = []
    declined_reasons: Counter[str] = Counter()

    for record in load_catalog(CATALOG):
        document = documents.get(Path(record.datasheet).name)
        if document is None:
            continue
        result = audit_sku(
            record, document, etim=etim, scope=scope, attributes=attributes
        )
        (raised if result.findings else silent).append(record.sku_id)
        for outcome in result.declined:
            declined_reasons[outcome.declined_reason.value] += 1

    false_positives = [
        sku for sku in raised if kinds[sku] in {"correct", "equivalent", "declined_expected"}
    ]
    misses = [sku for sku in silent if kinds[sku] in {"defect", "gap"}]

    assert false_positives == [], (
        "the audit raised a finding on rows a competent reviewer would call correct: "
        f"{false_positives}. Ground rule 7 -- a fix that softens a real defect is worse than the "
        "bug it removed, and a false accusation is worse than both."
    )
    assert misses == [], f"injected defects the audit did not raise: {misses}"

    # Every decline carries a reason, and the reasons are the ones the design predicts: an order
    # code has no grammar, one datasheet's tables do not resolve, one SKU is not in its document.
    assert set(declined_reasons) <= {
        "value_outside_known_grammar",
        "no_source_document",
        "layout_unreadable",
        "no_span_available",
    }
    assert declined_reasons["layout_unreadable"] > 0, (
        "the S200 M UC datasheet's ordering tables do not resolve into columns and the running "
        "text offers competing values; that must decline, not pick one (finding N12)"
    )
