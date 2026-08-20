"""Run the audit over every row of the demonstration catalog and report the confusion.

Diagnostic, not a product surface: it exists so that a change to the comparator, the extractor or
the attribute map shows up as a moved number here before anyone notices it in the console. The
population is constructed (see ``build_demo_catalog.py``), so the rates below describe defects we
injected -- they are a regression signal, not a measurement of anything in the world.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "audit" / "src"))

import yaml  # noqa: E402

from errata_audit.audit import Outcome, audit_sku  # noqa: E402
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
    catalog = load_catalog(DEMO / "catalog.csv")
    provenance = yaml.safe_load((DEMO / "provenance.yaml").read_text("utf-8"))
    kinds = {row["sku"]: row["kind"] for row in provenance["rows"]}

    confusion: Counter[tuple[str, str]] = Counter()
    declined: Counter[str] = Counter()
    findings = 0

    for record in catalog:
        document = documents.get(Path(record.datasheet).name)
        if document is None:
            confusion[(kinds.get(record.sku_id, "?"), "no_document")] += 1
            continue
        result = audit_sku(
            record, document, etim=etim, scope=scope, calibration=calibration
        )
        findings += len(result.findings)
        for outcome in result.outcomes:
            if outcome.outcome == Outcome.DECLINED and outcome.declined_reason:
                declined[outcome.declined_reason.value] += 1
        kind = kinds.get(record.sku_id, "?")
        raised = {o.attribute.key for o in result.findings}
        confusion[(kind, "raised" if raised else "silent")] += 1

    print(f"records: {len(catalog)}   findings: {findings}")
    print("\ninjected kind -> did the audit raise anything?")
    for (kind, verdict), count in sorted(confusion.items()):
        print(f"  {kind:20s} {verdict:12s} {count:5d}")
    print("\ndeclined bucket:")
    for reason, count in declined.most_common():
        print(f"  {reason:38s} {count:5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
