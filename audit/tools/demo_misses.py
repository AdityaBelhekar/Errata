"""List the demonstration rows whose outcome differs from what the injection intended.

A companion to ``demo_sweep.py``, and the more useful of the two: the aggregate says the audit
missed five defects, and only this says which five and why. Every disagreement between intent and
outcome is either a finding about the code or a finding about the injection, and both need naming.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "audit" / "src"))

import yaml  # noqa: E402

from errata_audit.audit import audit_sku  # noqa: E402
from errata_audit.classify import load_scope  # noqa: E402
from errata_audit.confidence import load_calibration  # noqa: E402
from errata_audit.documents import BlobStore, ingest_document  # noqa: E402
from errata_audit.etim import load_etim  # noqa: E402
from errata_audit.ingest import load_catalog  # noqa: E402
from errata_spec import DocumentRegister  # noqa: E402

DEMO = ROOT / "audit" / "src" / "errata_audit" / "demo"
ETIM = ROOT / "var" / "reference" / "etim" / "ETIM-10.0-ALL-SECTORS-CSV-METRIC-EI-2024-12-05.zip"


def main() -> int:
    register = DocumentRegister()
    store = BlobStore(ROOT / "var" / "audit" / "blobs")
    documents = {
        path.name: ingest_document(path, register=register, store=store)
        for path in sorted((ROOT / "var" / "spike" / "datasheets").glob("*.pdf"))
    }
    scope = load_scope()
    etim = load_etim(ETIM, release="10.0", class_ids=scope.as_set)
    calibration = load_calibration()
    provenance = yaml.safe_load((DEMO / "provenance.yaml").read_text("utf-8"))
    kinds = {row["sku"]: (row["kind"], row["expected"]) for row in provenance["rows"]}

    for record in load_catalog(DEMO / "catalog.csv"):
        kind, expected = kinds.get(record.sku_id, ("?", ""))
        document = documents.get(Path(record.datasheet).name)
        if document is None:
            continue
        result = audit_sku(record, document, etim=etim, scope=scope, calibration=calibration)
        raised = bool(result.findings)
        should_raise = kind in {"defect", "gap"}
        if raised == should_raise and kind != "declined_expected":
            continue
        print(f"== {record.sku_id}  kind={kind}  raised={raised}")
        print(f"   intent: {expected}")
        for outcome in result.outcomes:
            print(
                f"   - {outcome.attribute.key:15s} {outcome.outcome:12s} "
                f"cat={outcome.catalog_value!r} doc={outcome.derived_value!r} "
                f"{outcome.comparison.disagreement_class.value if outcome.comparison else ''} "
                f"{outcome.declined_reason.value if outcome.declined_reason else ''}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
