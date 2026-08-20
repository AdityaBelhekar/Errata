"""R2 must not have changed R1's answers.

The most dangerous thing a scale release can do is quietly improve, or quietly degrade, the audit it
wraps. `errata_scale.run_catalog` calls `errata_audit.audit_sku` unchanged and extracts each
document's text layer and tables once rather than once per record; that is a performance change, and
performance changes are exactly the kind that alter results by accident.

So this file re-runs the T1 tier over the R1 demonstration catalog and asserts the numbers
`docs/R1-report.md` publishes: **56 injected defects, 11 fill-rate gaps, 67 findings in total,
79.4% coverage over the records that had a document.** If R2 ever moves one of them, that is a
finding about R2 and not a new number for R1.

Skips when the corpus has not been fetched -- a clean clone has no `var/`.
"""

from __future__ import annotations

import pytest
from scalefixtures import ABB_S200, ETIM_DIR, R1_CATALOG

from errata_scale import Tier, run_catalog

pytestmark = pytest.mark.skipif(
    not (ABB_S200.exists() and (ETIM_DIR / "extracted" / "ETIMARTCLASS.csv").exists()),
    reason="the ABB datasheets or the ETIM release are not present; run scripts/fetch_reference_data.sh",
)


@pytest.fixture(scope="module")
def r1_run():
    from errata_audit import (
        BlobStore,
        ingest_document,
        load_calibration,
        load_etim,
        load_scope,
    )
    from errata_spec import DocumentRegister

    scope = load_scope()
    etim = load_etim(ETIM_DIR / "extracted", release="10.0", class_ids=scope.as_set)
    register = DocumentRegister()
    store = BlobStore(ABB_S200.parent.parent / "audit" / "blobs")
    documents = {
        path.name: ingest_document(str(path), register=register, store=store)
        for path in sorted(ABB_S200.parent.glob("*.pdf"))
    }
    return run_catalog(
        R1_CATALOG,
        documents,
        etim=etim,
        scope=scope,
        calibration=load_calibration(),
    )


def test_the_r2_pipeline_reproduces_r1s_findings(r1_run):
    assert r1_run.grounded_findings == 67
    assert r1_run.structural_findings == 0, (
        "the R1 catalog has one row per part number, so T0 has nothing to compare -- a structural "
        "finding here would mean T0 had invented one"
    )


def test_the_r2_pipeline_reproduces_r1s_coverage(r1_run):
    assert round(r1_run.grounded_coverage, 3) == 0.794


def test_t1_ran_only_on_the_groundable_records(r1_run):
    assert r1_run.groundable.groundable == 277
    assert r1_run.cost.of(Tier.T1_GROUNDED).records_entered == 277
    # the deliberately undocumented SKU is a recovery lead, not a finding and not a silent drop
    assert r1_run.groundable.recovery_leads() == (("abb-s200-does-not-exist.pdf", 1),)


def test_the_grounded_findings_carry_page_evidence_rather_than_feed_evidence(r1_run):
    """T1's evidence is a span in the manufacturer's PDF with a bounding box; T0's is a span in the
    feed with none. Mixing them up would be the quiet way a structural finding got presented as a
    grounded one."""
    grounded = [entry for entry in r1_run.triage.entries if entry.tier == Tier.T1_GROUNDED.value]
    assert grounded
    for entry in grounded:
        for evidence in entry.redline.evidence:
            assert evidence.doc_id.endswith(".pdf")
            assert evidence.bbox is not None
