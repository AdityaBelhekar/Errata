"""errata-audit -- R1: the end-to-end audit of one SKU against one document.

R0 asked whether the idea survives contact with data. R1 asks whether it survives contact with a
reviewer: an ingested catalog record, a hash-registered document, a class resolved in three
inspectable stages, values re-derived **blind to the catalog**, a comparator that refuses to flag
316 SS against A4, a declined bucket where every row states why, and a console where the box lands
on the words and their headers come with them.

    from errata_audit import audit_sku, load_catalog, load_etim, load_scope

    record = load_catalog("catalog.csv")[0]
    result = audit_sku(record, document, etim=etim, scope=load_scope())
    result.findings          # redlines, ranked by P(wrong) x blast radius
    result.declined          # every one with exactly one machine-readable reason
    result.coverage          # read the first number next to this one, always

**What R1 does not claim**, because a package that overstates its own scope is the first thing a
hostile reviewer catches:

* the embedding retriever and cross-encoder of FR-2.2 are **interfaces with no implementation**;
  the shipped retrieval is lexical and every resolution says so in ``retrieval_method``;
* the LLM selector is an interface, capped at five candidates by a function that raises;
* **no calibration set exists** (FR-6.1), because calibration needs reviewer decisions and none
  have been made. Confidences are raw evidence-quality scores and are never printed as
  probabilities;
* there is no OCR: born-digital documents only, and a scan is declined with a reason.

Errata grades; it never enriches, and it never writes to a customer PIM (ADR-001).
"""

from __future__ import annotations

from .attributes import AttributeMap, AuditAttribute, load_attributes
from .audit import AttributeOutcome, AuditRun, Outcome, SkuAudit, audit_sku
from .classify import (
    MAX_SELECT_CANDIDATES,
    ClassCandidate,
    ClassResolution,
    ClassScope,
    load_scope,
    rerank,
    resolve_class,
    retrieve,
    select,
    top_k_accuracy,
)
from .confidence import (
    CalibrationModel,
    aurc,
    calibrate,
    fit_platt,
    load_calibration,
    reliability_diagram,
    risk_coverage_curve,
)
from .console import render_html, render_text
from .counterevidence import find_counter_evidence
from .derive import Derivation, derive
from .documents import BlobStore, DocumentSource, NetworkNotPermittedError, ingest_document
from .etim import EtimClass, EtimFeature, EtimModel, load_etim
from .ingest import CatalogRecord, load_catalog, record_from_mapping
from .layout import LAYOUT_VERSION, TextLayer, Word, extract_layer
from .ledger import Ledger, calibration_examples
from .tables import TABLES_VERSION, Cell, CellRole, Table, extract_tables

__version__ = "0.1.0"

__all__ = [
    "LAYOUT_VERSION",
    "MAX_SELECT_CANDIDATES",
    "TABLES_VERSION",
    "AttributeMap",
    "AttributeOutcome",
    "AuditAttribute",
    "AuditRun",
    "BlobStore",
    "CalibrationModel",
    "CatalogRecord",
    "Cell",
    "CellRole",
    "ClassCandidate",
    "ClassResolution",
    "ClassScope",
    "Derivation",
    "DocumentSource",
    "EtimClass",
    "EtimFeature",
    "EtimModel",
    "Ledger",
    "NetworkNotPermittedError",
    "Outcome",
    "SkuAudit",
    "Table",
    "TextLayer",
    "Word",
    "__version__",
    "audit_sku",
    "aurc",
    "calibrate",
    "calibration_examples",
    "derive",
    "extract_layer",
    "extract_tables",
    "find_counter_evidence",
    "fit_platt",
    "ingest_document",
    "load_attributes",
    "load_calibration",
    "load_catalog",
    "load_etim",
    "load_scope",
    "record_from_mapping",
    "reliability_diagram",
    "render_html",
    "render_text",
    "rerank",
    "resolve_class",
    "retrieve",
    "risk_coverage_curve",
    "select",
    "top_k_accuracy",
]
