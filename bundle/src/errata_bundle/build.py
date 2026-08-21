"""Drive a real audit into an Evidence Bundle.

This is the seam between the product (``errata_audit``) and the frontend (``web/console``). It is
the only module in this package that imports the audit pipeline, and it is deliberately thin: it
translates domain objects into the wire shapes ``bundle.py`` writes, and does no analysis of its
own. Anything clever that happened here would be analysis the console could not reproduce and the
ledger would not record.

No data is invented. Every value, span, header, confidence and declined-reason below comes out of
an actual ``audit_sku`` run against an actual document. Where the pipeline declines, the bundle
records the decline; where a blast-radius factor is not computed, the field is absent rather than
defaulted to something that looks like a measurement (L-4).

Run it::

    python -m errata_bundle.build --catalog var/scale/catalog.csv \\
        --datasheet var/spike/datasheets/abb-s200-2CDC002142D0207.pdf --limit 12
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .bundle import BundleWriter, verify

__all__ = ["build_bundles", "main"]


def _evidence_dicts(items) -> list[dict[str, Any]]:
    out = []
    for ev in items or ():
        out.append(
            {
                "page": getattr(ev, "page", None),
                "char_span": list(getattr(ev, "char_span", ()) or ()),
                "snippet": getattr(ev, "snippet", "") or "",
                "table_cell": getattr(ev, "table_cell", "") or "",
                # FR-7.3: a number in an engineering table means nothing without its headers.
                "row_header": getattr(ev, "row_header", "") or "",
                "column_header": getattr(ev, "column_header", "") or "",
                "bbox": getattr(ev, "bbox", None),
                "layer_version": getattr(ev, "extraction_layer_version", "") or "",
            }
        )
    return out


def _blast_factors(redline) -> dict[str, Any]:
    """FR-8.4: each factor separately. A reviewer shown one score has a number, not a reason.

    Absent factors stay absent. A default of 1.0 rendered in the console is indistinguishable from
    a measured 1.0, and that is exactly the class of thing L-4 exists to prevent.
    """
    blast = getattr(redline, "blast_radius", None)
    if blast is None:
        return {}
    factors = {}
    for name in (
        "revenue_weight",
        "safety_class_multiplier",
        "propagation_count",
        "record_multiplicity",
    ):
        value = getattr(blast, name, None)
        if value is not None:
            factors[name] = value
    score = getattr(blast, "score", None)
    if score is not None:
        factors["score"] = round(float(score), 4)
    return factors


def _outcome_dict(outcome) -> dict[str, Any]:
    redline = getattr(outcome, "redline", None)
    attribute = getattr(outcome, "attribute", None)
    counter = getattr(redline, "counter_evidence", None) if redline else None

    record: dict[str, Any] = {
        "attribute": getattr(attribute, "key", "") or "",
        "label": getattr(attribute, "label", "") or getattr(attribute, "key", "") or "",
        "unit": getattr(attribute, "unit", "") or "",
        "catalog_value": getattr(outcome, "catalog_value", None),
        "derived_value": getattr(outcome, "derived_value", None),
        "outcome": getattr(outcome, "outcome", ""),
        "evidence": _evidence_dicts(getattr(redline, "evidence", None) if redline else None),
        "counter_evidence": _evidence_dicts(
            getattr(counter, "supporting", None) if counter else None
        ),
        # FR-7.4: never empty and never absent. When nothing supports the catalog, the bundle says
        # so in words, because a missing section and "we looked and found nothing" are different
        # claims and the reviewer must be able to tell them apart.
        "counter_summary": (
            getattr(counter, "summary", "") if counter else ""
        ) or "No supporting evidence found for the catalog value.",
        "blast": _blast_factors(redline) if redline else {},
    }

    confidence = getattr(outcome, "confidence", None)
    value = getattr(confidence, "value", None) if confidence else None
    if value is not None:
        record["confidence"] = round(float(value), 4)
    if redline is not None:
        erv = getattr(redline, "expected_review_value", None)
        if erv is not None:
            record["expected_review_value"] = round(float(erv), 6)
    # The canonical Redline, verbatim, so the console's decision can be replayed into
    # `Ledger.adjudicate` without re-running the audit. FR-7.8 says evidence is reconstructible
    # from stored state; an adjudication that needed the pipeline back in memory to be recorded
    # would make that false at the one moment it matters most.
    if redline is not None and hasattr(redline, "model_dump_json"):
        import json as _json

        record["redline"] = _json.loads(redline.model_dump_json())
        record["requires_two_signatures"] = bool(
            getattr(redline, "requires_two_signatures", False)
        )

    reason = getattr(outcome, "declined_reason", None)
    if reason is not None:
        record["declined_reason"] = getattr(reason, "value", str(reason))
    detail = getattr(outcome, "detail", "")
    if detail:
        record["detail"] = detail
    return record


def _resolve_etim(root: Path | None) -> Path | None:
    """Mirror ``errata_audit.cli._default_etim``: prefer the extracted directory, else the archive.

    Duplicated rather than imported because it is private to the CLI, and reaching into another
    distribution's private helper is how two things start disagreeing about where data lives. If it
    ever becomes public, this should call it.
    """
    root = root or Path("var/reference/etim")
    if not root.exists():
        return None
    if (root / "ETIMARTCLASS.csv").exists():
        return root
    extracted = root / "extracted"
    if (extracted / "ETIMARTCLASS.csv").exists():
        return extracted
    archives = sorted(p for p in root.glob("*.zip") if not p.name.startswith("_"))
    return archives[0] if archives else None


def build_bundles(
    *,
    catalog: Path,
    datasheet: Path,
    out_root: Path,
    blobs: Path,
    etim_archive: Path | None = None,
    etim_release: str = "10.0",
    limit: int = 12,
) -> list[Path]:
    """Audit ``limit`` records and write one bundle per record that produced a finding."""
    from errata_audit.attributes import load_attributes
    from errata_audit.audit import audit_sku
    from errata_audit.classify import load_scope
    from errata_audit.confidence import load_calibration
    from errata_audit.documents import BlobStore, ingest_document
    from errata_audit.etim import load_etim
    from errata_audit.ingest import load_catalog
    from errata_spec import DocumentRegister

    # Wired exactly as `errata-audit catalog` wires it (cli.py:289). Deliberately not a simplified
    # path: a bundle built by a different pipeline from the one that ships is a bundle that proves
    # nothing about what a reviewer will see.
    attributes = load_attributes()
    register = DocumentRegister()
    store = BlobStore(blobs)
    calibration = load_calibration()
    scope = load_scope(None)
    archive = _resolve_etim(etim_archive)
    etim = (
        load_etim(archive, release=etim_release, class_ids=scope.as_set) if archive else None
    )
    if etim is None:
        raise FileNotFoundError(
            "no ETIM release available. Pass --etim, or run scripts/fetch_reference_data.sh. "
            "The model is free (ODC-By) and needs no login."
        )

    document = ingest_document(str(datasheet), register=register, store=store)
    records = list(load_catalog(catalog))[:limit]

    writer = BundleWriter(root=out_root)
    written: list[Path] = []
    index: list[dict[str, Any]] = []

    for record in records:
        audit = audit_sku(
            record,
            document,
            etim=etim,
            scope=scope,
            attributes=attributes,
            calibration=calibration,
        )
        findings = [_outcome_dict(o) for o in audit.findings]
        if not findings:
            # Bundles are built for records a reviewer will actually be shown. A record with no
            # finding has nothing to adjudicate, and writing a bundle for it would put 1.2M
            # directories on disk to hold nothing.
            continue

        resolved = [_outcome_dict(o) for o in audit.resolved]
        declined = [
            _outcome_dict(o)
            for o in audit.outcomes
            if getattr(o, "declined_reason", None) is not None
        ]

        path = writer.write(
            sku=record.sku_id,
            document_path=Path(document.path),
            document_sha256=document.sha256,
            document_name=Path(str(datasheet)).name,
            findings=findings,
            resolved=resolved,
            declined=declined,
            versions={
                "layout": audit.layout_version,
                "tables": audit.tables_version,
                "derive": audit.derive_version,
            },
            note=(
                "Built from a real audit run. No values in this bundle were invented. "
                "The source PDF is not included (FR-9.5); only its SHA-256."
            ),
        )
        ok, problems = verify(path)
        if not ok:
            raise RuntimeError(f"bundle {path} failed self-verification: {problems}")

        written.append(path)
        index.append(
            {
                "sku": record.sku_id,
                "mpn": getattr(record, "mpn", ""),
                "manufacturer": getattr(record, "manufacturer", ""),
                "row_number": getattr(record, "row_number", None),
                "findings": len(findings),
                "resolved": len(resolved),
                "declined": len(declined),
                "document": Path(str(datasheet)).name,
                "top": findings[0]["attribute"] if findings else "",
            }
        )

    from .bundle import canonical_json

    (out_root / "index.json").write_bytes(
        canonical_json(
            {
                "generated_from": {
                    "catalog": str(catalog),
                    "datasheet": Path(str(datasheet)).name,
                    "records_audited": len(records),
                },
                "bundles": index,
            }
        )
    )
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="errata-bundle",
        description="Audit a catalog and write one Evidence Bundle per finding.",
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--datasheet", type=Path, required=True)
    parser.add_argument("--blobs", type=Path, default=Path("var/audit/blobs"))
    parser.add_argument("--out", type=Path, default=Path("var/fe25/bundles"))
    parser.add_argument("--etim", type=Path, default=None, help="ETIM release archive or directory")
    parser.add_argument("--etim-release", default="10.0")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    written = build_bundles(
        catalog=args.catalog,
        datasheet=args.datasheet,
        out_root=args.out,
        blobs=args.blobs,
        etim_archive=args.etim,
        etim_release=args.etim_release,
        limit=args.limit,
    )
    for path in written:
        print(f"wrote {path}")
    print(f"\n{len(written)} bundle(s), all self-verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
