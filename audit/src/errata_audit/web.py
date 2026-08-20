"""FR-7.1 / FR-7.6 -- the reviewer console as a local web application.

The static HTML report (`console.py`) is a good artefact and a bad *console*: FR-7.1 says a reviewer
adjudicates "without leaving the screen", and a file cannot accept a decision. This module is the
same three panes with the loop closed -- a form to run an audit, a queue to work through, evidence
boxed on the page image, and Accept / Keep catalog / Escalate buttons that write to the append-only
ledger and come back with the decision recorded.

Closing that loop is not cosmetic. Three requirements only become real when a human can act:

* **FR-7.6** — decision, actor, timestamp and note persisted immutably. The buttons write claims.
* **FR-6.1** — calibration needs labels, and labels are adjudications. The dashboard shows how many
  decisions exist and what is still missing before a probability can honestly be printed.
* **FR-9.3** — reviewer-seconds per verified attribute, the metric a buyer actually pays for and
  nobody publishes. The page times itself and submits the number with the decision.

**Deliberately built on the standard library.** No web framework, no CDN, no build step: the whole
console is one Python module and inline CSS, so it runs from a clean clone with no signup (FR-7.9's
constraint, applied to the UI). It is a *local operator tool* -- it binds to 127.0.0.1, it has no
authentication, and binding it anywhere else requires an explicit flag that says so out loud. A
reviewer console shows a customer's catalog next to a manufacturer's document; putting that on a
network interface is a decision somebody should have to make deliberately.

**What it will not do:** it never writes to a catalog (ADR-001). Accepting a redline writes a
*claim* to Errata's own ledger saying a human accepted it. Nothing leaves this process for the
customer's PIM, and there is no code path that could.
"""

from __future__ import annotations

import html
import threading
import traceback
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from errata_spec import Decision, DocumentRegister, Redline

from .attributes import AttributeMap, load_attributes
from .audit import AttributeOutcome, SkuAudit, audit_sku
from .classify import ClassScope
from .confidence import CalibrationModel, aurc, load_calibration, risk_coverage_curve
from .console import _CSS, PageImage, render_page
from .documents import BlobStore, DocumentSource, ingest_document
from .etim import EtimModel
from .ingest import CatalogRecord, load_catalog
from .layout import extract_layer
from .ledger import Ledger, calibration_examples

__all__ = ["AuditService", "serve"]

#: How many catalog rows the dashboard audits on first load. The whole catalog takes ~20 seconds,
#: which is a bad first impression and a worse timeout; the queue says how far it has scanned and
#: the operator asks for more. Progress a reviewer can see beats a spinner that hides it.
DEFAULT_SCAN = 40


# ------------------------------------------------------------------------------------------------
# The service -- everything the pages need, with the audits cached
# ------------------------------------------------------------------------------------------------


@dataclass
class AuditService:
    """Holds the loaded model and caches audits, so a page load is not a re-extraction.

    The cache is keyed on ``(sku, document sha256)``: a revised datasheet is a different key, which
    is the same rule the layout cache and the document register already use. Nothing here is a
    performance trick that could serve a stale answer for changed bytes.
    """

    catalog: tuple[CatalogRecord, ...]
    documents: dict[str, DocumentSource]
    etim: EtimModel
    scope: ClassScope
    attributes: AttributeMap
    ledger: Ledger
    calibration: CalibrationModel | None = None
    catalog_path: str = ""
    missing_documents: tuple[str, ...] = ()
    """Datasheets a record names that were not supplied to this server.

    Kept rather than raised on. A catalog naming a document nobody has is an ordinary operational
    fact -- it is what FR-6.2's ``no_source_document`` exists for -- and a console that refused to
    start because one row pointed at a missing PDF would be unusable on any real feed."""

    _cache: dict[tuple[str, str], SkuAudit] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _scanned: set[str] = field(default_factory=set)

    # -- lookup ---------------------------------------------------------------------------

    def record(self, sku_id: str) -> CatalogRecord | None:
        return next(
            (r for r in self.catalog if r.sku_id == sku_id or r.mpn == sku_id), None
        )

    def document_for(self, record: CatalogRecord) -> DocumentSource | None:
        """Same rule as the CLI: a record that names a datasheet gets that one or nothing.

        Auditing a record against a document it did not name would be the worst failure this system
        could have, so "several available and none named" resolves on evidence -- the document whose
        text contains the type designation -- and declines when that is ambiguous.
        """
        if record.datasheet:
            wanted = Path(record.datasheet).name
            return self.documents.get(wanted)
        if len(self.documents) == 1:
            return next(iter(self.documents.values()))
        mpn = record.mpn or record.sku_id
        matches = [
            document
            for document in self.documents.values()
            if any(
                word.text == mpn
                for word in extract_layer(
                    document.path, document_sha256=document.sha256
                ).words
            )
        ]
        return matches[0] if len(matches) == 1 else None

    # -- auditing -------------------------------------------------------------------------

    def audit(self, sku_id: str) -> SkuAudit | None:
        record = self.record(sku_id)
        if record is None:
            return None
        document = self.document_for(record)
        if document is None:
            return None
        key = (record.sku_id, document.sha256)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = audit_sku(
            record,
            document,
            etim=self.etim,
            scope=self.scope,
            attributes=self.attributes,
            calibration=self.calibration,
        )
        with self._lock:
            self._cache[key] = result
            self._scanned.add(record.sku_id)
        return result

    def scan(self, limit: int) -> tuple[SkuAudit, ...]:
        """Audit the first ``limit`` records, reusing anything already cached."""
        out: list[SkuAudit] = []
        for record in self.catalog[: max(0, limit)]:
            result = self.audit(record.sku_id)
            if result is not None:
                out.append(result)
        return tuple(out)

    @property
    def scanned(self) -> int:
        with self._lock:
            return len(self._scanned)

    def queue(self, limit: int) -> tuple[tuple[SkuAudit, AttributeOutcome], ...]:
        rows = [
            (result, outcome)
            for result in self.scan(limit)
            for outcome in result.findings
        ]
        rows.sort(
            key=lambda pair: -(
                pair[1].redline.expected_review_value if pair[1].redline else 0.0
            )
        )
        return tuple(rows)

    def undecided(self, limit: int) -> tuple[tuple[SkuAudit, AttributeOutcome], ...]:
        decided = self.decided_ids()
        return tuple(
            (result, outcome)
            for result, outcome in self.queue(limit)
            if outcome.redline and str(outcome.redline.redline_id) not in decided
        )

    # -- decisions ------------------------------------------------------------------------

    def decided_ids(self) -> set[str]:
        return {
            str(event.payload.get("redline_id"))
            for event in self.ledger.of_kind("adjudication")
        }

    def find_redline(self, redline_id: str) -> tuple[SkuAudit, AttributeOutcome] | None:
        """Find a redline among the cached audits, then in the ledger.

        The ledger fallback is what makes redline ids stable across restarts worth having: a
        decision can be recorded against a finding this process has not audited in *this* session,
        because the id is derived from the finding's content rather than from when it was created.
        """
        with self._lock:
            cached = list(self._cache.values())
        for result in cached:
            for outcome in result.findings:
                if outcome.redline and str(outcome.redline.redline_id) == redline_id:
                    return result, outcome
        for event in self.ledger.of_kind("redline"):
            if str(event.payload.get("redline_id")) == redline_id:
                result = self.audit(str(event.payload.get("sku_id", "")))
                if result is None:
                    continue
                for outcome in result.findings:
                    if outcome.redline and str(outcome.redline.redline_id) == redline_id:
                        return result, outcome
        return None

    def adjudicate(
        self,
        redline_id: str,
        *,
        decision: Decision,
        decided_by: str,
        note: str = "",
        second_adjudicator: str = "",
        seconds: float | None = None,
        evidence_accepted: bool | None = None,
        decided_by_role: str = "",
        presented_utc: str = "",
        decided_utc: str = "",
    ) -> tuple[Redline, str]:
        """Record one decision. Returns the redline and a sentence for the reviewer."""
        found = self.find_redline(redline_id)
        if found is None:
            raise KeyError(f"no redline {redline_id} in this run or in the ledger")
        _result, outcome = found
        redline = outcome.redline
        assert redline is not None

        # Persist the finding itself before the decision, so the ledger can always answer "what was
        # this person looking at" (FR-7.8) without re-running the audit.
        if str(redline.redline_id) not in {
            str(e.payload.get("redline_id")) for e in self.ledger.of_kind("redline")
        }:
            self.ledger.append_redline(redline)
            self.ledger.append(
                "score",
                {
                    "redline_id": str(redline.redline_id),
                    "sku_id": redline.sku_id,
                    "attribute_uri": redline.attribute_uri,
                    "raw_score": outcome.confidence.raw_score,
                    "calibrated_p": outcome.confidence.calibrated_p,
                    "method": outcome.derivation.method if outcome.derivation else "",
                },
            )

        self.ledger.adjudicate(
            redline,
            decision=decision,
            decided_by=decided_by,
            note=note,
            second_adjudicator=second_adjudicator,
            seconds_to_decision=seconds,
            evidence_accepted=evidence_accepted,
            raw_score=outcome.confidence.raw_score,
            decided_by_role=decided_by_role,
            presented_utc=presented_utc,
            decided_utc=decided_utc,
        )

        sentence = (
            f"Recorded: {decision.value.replace('_', ' ')} on {redline.sku_id} / "
            f"{redline.attribute_label or redline.attribute_uri}, by {decided_by}."
        )
        if decision is Decision.KEEP_CATALOG and not redline.counter_evidence.supporting:
            sentence += (
                " Noted: kept against an empty counter-evidence panel — §5.4 calls that the "
                "highest-signal event in the system, because the reviewer knows something the "
                "corpus does not."
            )
        return redline, sentence

    # -- calibration ----------------------------------------------------------------------

    def calibration_state(self) -> tuple[int, int, int, str]:
        """``(decisions, accepted, kept, sentence)`` — what stands between here and FR-6.1."""
        examples = calibration_examples(self.ledger)
        accepted = sum(1 for _score, label in examples if label)
        kept = len(examples) - accepted
        if self.calibration is not None:
            sentence = (
                f"Calibrated on {self.calibration.n} decisions "
                f"({self.calibration.method}, set {self.calibration.calibration_set_id}); "
                f"expected calibration error {self.calibration.expected_calibration_error:.3f}."
            )
        elif accepted and kept:
            sentence = (
                f"{len(examples)} usable decisions of both kinds. Run "
                "<code>errata-audit calibrate --out .../config/calibration.yaml</code> and restart "
                "to turn raw scores into probabilities."
            )
        else:
            missing = "kept-catalog" if accepted and not kept else "accepted"
            sentence = (
                f"Not calibrated. {len(examples)} usable decision(s); a fit needs decisions of "
                f"<strong>both</strong> kinds and there are no {missing} ones yet. Until then every "
                "confidence here is a raw evidence-quality score and is labelled as one."
            )
        return len(examples), accepted, kept, sentence

    def risk_curve(self):
        scored = [
            (
                float(event.payload.get("raw_score") or 0.0),
                event.payload.get("decision") == Decision.ACCEPT_REDLINE.value,
            )
            for event in self.ledger.of_kind("adjudication")
            if event.payload.get("raw_score") is not None
            and event.payload.get("decision")
            in {Decision.ACCEPT_REDLINE.value, Decision.KEEP_CATALOG.value}
        ]
        return risk_coverage_curve(scored)


def build_service(
    *,
    catalog: Path | str,
    datasheets: list[Path | str],
    etim: EtimModel,
    scope: ClassScope,
    ledger: Path | str,
    blobs: Path | str,
    attributes: AttributeMap | None = None,
) -> AuditService:
    register = DocumentRegister()
    store = BlobStore(blobs)
    documents: dict[str, DocumentSource] = {}
    missing: list[str] = []
    for path in datasheets:
        try:
            source = ingest_document(path, register=register, store=store)
        except FileNotFoundError:
            missing.append(Path(str(path)).name)
            continue
        documents[Path(str(path)).name] = source
    if not documents:
        raise FileNotFoundError(
            "none of the named datasheets could be read: " + ", ".join(missing or ["(none given)"])
        )
    return AuditService(
        catalog=load_catalog(catalog),
        documents=documents,
        etim=etim,
        scope=scope,
        attributes=attributes or load_attributes(),
        ledger=Ledger(ledger),
        calibration=load_calibration(),
        catalog_path=str(catalog),
        missing_documents=tuple(missing),
    )


# ------------------------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------------------------

_WEB_CSS = """
body { background: var(--paper); }
nav { display: flex; gap: 18px; align-items: baseline; padding: 10px 24px;
      border-bottom: 1px solid var(--line); font-size: 13px; }
nav a { color: var(--ink); text-decoration: none; border-bottom: 2px solid transparent;
        padding-bottom: 4px; }
nav a.on, nav a:hover { border-bottom-color: var(--sev1); }
nav .brand { font-weight: 700; letter-spacing: -0.01em; margin-right: 8px; }
nav .spacer { flex: 1; }
main { padding: 20px 24px; }
.flash { margin: 0 24px 16px; padding: 10px 14px; border-left: 3px solid var(--counter-box);
         background: #f2f9f2; font-size: 13px; }
.flash.bad { border-left-color: var(--sev1); background: #fdf3f2; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px;
         margin-bottom: 20px; }
.card { border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; background: var(--panel); }
.card .n { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }
.card .k { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
form.run { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 18px; }
input[type=text], input[type=number], select, textarea {
  font: inherit; padding: 6px 8px; border: 1px solid var(--line); border-radius: 4px;
  background: var(--paper); color: var(--ink); }
textarea { width: 100%; min-height: 56px; }
button { font: inherit; padding: 6px 12px; border: 1px solid var(--line); border-radius: 4px;
         background: var(--ink); color: var(--paper); cursor: pointer; }
button.secondary { background: var(--paper); color: var(--ink); }
button.accept { background: var(--sev1); border-color: var(--sev1); }
button.keep { background: var(--counter-box); border-color: var(--counter-box); }
button.escalate { background: var(--sev2); border-color: var(--sev2); }
a.row { display: block; color: inherit; text-decoration: none; }
a.row:hover .row { outline: 2px solid var(--header-box); }
.decided { opacity: .55; }
.badge { display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 10px;
         border: 1px solid var(--line); color: var(--muted); margin-left: 6px; }
table.grid { width: 100%; border-collapse: collapse; font-size: 13px; }
table.grid th, table.grid td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }
table.grid th { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
fieldset { border: 1px solid var(--line); border-radius: 6px; padding: 12px; margin: 12px 0; }
legend { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
label.field { display: block; font-size: 12px; color: var(--muted); margin: 8px 0 2px; }
.curve { display: flex; align-items: flex-end; gap: 2px; height: 60px; }
.curve i { display: block; width: 6px; background: var(--header-box); }
"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _page(
    title: str,
    body: str,
    *,
    active: str = "",
    flash: str = "",
    bad: bool = False,
    wrap: bool = True,
) -> bytes:
    nav = "".join(
        f"<a href='{href}' class='{'on' if active == key else ''}'>{label}</a>"
        for key, href, label in (
            ("queue", "/", "Queue"),
            ("ledger", "/ledger", "Decisions"),
            ("status", "/status", "What this does not claim"),
        )
    )
    flash_html = (
        f"<div class='flash{' bad' if bad else ''}'>{flash}</div>" if flash else ""
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Errata — {_e(title)}</title><style>{_CSS}{_WEB_CSS}</style></head><body>"
        f"<nav><span class='brand'>ERRATA</span>{nav}<span class='spacer'></span>"
        "<span class='badge'>R1 · local reviewer console</span></nav>"
        + (f"{flash_html}<main>{body}</main>" if wrap else f"{flash_html}{body}")
        + "</body></html>"
    ).encode("utf-8")


def _queue_row_html(result: SkuAudit, outcome: AttributeOutcome, *, decided: bool) -> str:
    redline = outcome.redline
    assert redline is not None
    severity = f"sev{int(redline.severity)}"
    factors = "".join(f"<li>{_e(line)}</li>" for line in redline.blast_radius.explain())
    return (
        f"<a class='row' href='/sku/{urllib.parse.quote(result.record.sku_id)}"
        f"#{_e(redline.redline_id)}'>"
        f"<div class='row {severity}{' decided' if decided else ''}'>"
        f"<div class='head'>SEV-{int(redline.severity)} · {_e(result.record.sku_id)} · "
        f"{_e(redline.attribute_label)}"
        + ("<span class='badge'>decided</span>" if decided else "")
        + (
            "<span class='badge'>two signatures</span>"
            if redline.requires_two_signatures
            else ""
        )
        + "</div>"
        f"<div class='body'>Catalog says <strong>{_e(redline.catalog_value)}</strong>. "
        f"The evidence says <strong>{_e(redline.proposed_value)}</strong> "
        f"({_e(redline.disagreement_class.value.replace('_', ' '))}).</div>"
        + (f"<ul class='factors'>{factors}</ul>" if factors else "")
        + "</div></a>"
    )


def _dashboard(service: AuditService, *, limit: int) -> str:
    rows = service.queue(limit)
    decided = service.decided_ids()
    scanned = service.scanned
    total = len(service.catalog)
    open_rows = [r for r in rows if str(r[1].redline.redline_id) not in decided]
    decisions, _accepted, _kept, calibration_sentence = service.calibration_state()

    cards = [
        ("findings open", len(open_rows)),
        ("findings decided", len(rows) - len(open_rows)),
        ("records scanned", f"{scanned} / {total}"),
        ("decisions recorded", decisions),
    ]
    cards_html = "".join(
        f"<div class='card'><div class='n'>{_e(value)}</div><div class='k'>{_e(key)}</div></div>"
        for key, value in cards
    )

    curve = service.risk_curve()
    curve_html = ""
    if curve:
        bars = "".join(
            f"<i style='height:{max(2, round(point.risk * 60))}px' "
            f"title='coverage {point.coverage:.0%}, risk {point.risk:.0%}'></i>"
            for point in curve
        )
        curve_html = (
            "<fieldset><legend>Risk against coverage (FR-6.3)</legend>"
            f"<div class='curve'>{bars}</div>"
            f"<p class='body'>AURC {aurc(curve):.4f} over {len(curve)} decided findings. "
            "Risk here is the rate at which a reviewer <em>rejected</em> what the audit raised, "
            "answering most-confident-first. It is computed from decisions, never from the audit "
            "grading its own homework.</p></fieldset>"
        )

    return (
        "<h1 style='margin:0 0 4px;font-size:20px'>Review queue</h1>"
        f"<p class='body' style='color:var(--muted);margin-top:0'>{_e(service.catalog_path)} · "
        f"{len(service.documents)} document(s) · ranked by expected review value "
        "(P(catalog wrong) × blast radius), never by confidence.</p>"
        f"<div class='cards'>{cards_html}</div>"
        + (
            "<div class='flash bad'>"
            + _e(
                f"{len(service.missing_documents)} datasheet(s) named by the catalog were not "
                f"supplied: {', '.join(service.missing_documents)}. Records pointing at them "
                "decline with no_source_document and join the document-recovery queue; they are "
                "not audited against a different document."
            )
            + "</div>"
            if service.missing_documents
            else ""
        )
        + "<form class='run' method='get' action='/audit'>"
        "<input type='text' name='sku' placeholder='SKU or MPN, e.g. S201M-B16UC' size='28'>"
        "<button type='submit'>Audit this SKU</button>"
        "<a href='/audit?random=1'><button type='button' class='secondary'>Pick one at "
        "runtime</button></a>"
        f"<a href='/?limit={limit + 60}'><button type='button' class='secondary'>Scan 60 "
        "more</button></a></form>"
        "<div class='caveat'><strong>Read this with the queue.</strong> The datasheet is the "
        "manufacturer's own and hash-registered; the values Errata re-derives and the boxes it "
        "draws are read from it. <strong>The catalog under audit is constructed</strong> — no "
        "public feed for these products is available, so defects were injected on purpose. "
        f"{calibration_sentence}</div>"
        + curve_html
        + (
            "".join(
                _queue_row_html(
                    result, outcome, decided=str(outcome.redline.redline_id) in decided
                )
                for result, outcome in rows
            )
            or "<p class='body'>Nothing raised in the rows scanned so far.</p>"
        )
    )


def _evidence_html(result: SkuAudit, outcome: AttributeOutcome) -> str:
    redline = outcome.redline
    assert redline is not None
    images: dict[int, PageImage] = {}
    for evidence in (*redline.evidence, *redline.counter_evidence.supporting):
        if evidence.page not in images:
            images[evidence.page] = render_page(result.document.path, evidence.page)

    value_boxes = [
        e for e in redline.evidence if not e.column_header or e.table_cell != e.column_header
    ]
    header_boxes = [
        e for e in redline.evidence if e.table_cell and e.table_cell == e.column_header
    ]

    out = [
        "<div class='legend'>"
        "<span><i class='swatch' style='background:var(--value-box)'></i>the value</span>"
        "<span><i class='swatch' style='background:var(--header-box)'></i>its headers</span>"
        "<span><i class='swatch' style='background:var(--counter-box)'></i>counter-evidence</span>"
        "</div>"
    ]
    for page_number, image in sorted(images.items()):
        overlays = []
        for evidence in value_boxes:
            if evidence.page == page_number and evidence.bbox:
                overlays.append(_box(image, evidence, ""))
        for evidence in header_boxes:
            if evidence.page == page_number and evidence.bbox:
                overlays.append(_box(image, evidence, "header"))
        for evidence in redline.counter_evidence.supporting:
            if evidence.page == page_number and evidence.bbox:
                overlays.append(_box(image, evidence, "counter"))
        out.append(
            f"<div class='evidence-figure'><img alt='page {page_number}' src='{image.data_uri}'>"
            + "".join(overlays)
            + "</div>"
        )

    for evidence in redline.evidence:
        headers = ", ".join(
            part
            for part in (
                f"column <strong>{_e(evidence.column_header)}</strong>"
                if evidence.column_header
                else "",
                f"row <strong>{_e(evidence.row_header)}</strong>" if evidence.row_header else "",
            )
            if part
        )
        out.append(
            f"<p class='body'>page {evidence.page}, chars {evidence.char_span[0]}–"
            f"{evidence.char_span[1]}"
            + (f" · {headers}" if headers else "")
            + (f"<br><code>{_e(evidence.snippet.strip())}</code>" if evidence.snippet else "")
            + "</p>"
        )

    counter = redline.counter_evidence
    out.append(
        "<div class='counter'><strong>Counter-evidence — the case for the catalog</strong>"
        f"<div>{_e(counter.summary)}</div></div>"
    )
    out.append(f"<p class='body'>{_e(redline.rationale)}</p>")
    return "".join(out)


def _box(image: PageImage, evidence, kind: str) -> str:
    left, top, width, height = image.place(
        (evidence.bbox.x0, evidence.bbox.y0, evidence.bbox.x1, evidence.bbox.y1)
    )
    classes = f"box {kind}".strip()
    return (
        f"<div class='{classes}' style='left:{left:.3f}%;top:{top:.3f}%;"
        f"width:{width:.3f}%;height:{height:.3f}%'></div>"
    )


def _adjudication_form(result: SkuAudit, outcome: AttributeOutcome, *, decided: bool) -> str:
    redline = outcome.redline
    assert redline is not None
    if decided:
        return (
            "<fieldset><legend>Adjudication</legend><p class='body'>A decision is already recorded "
            "for this finding. Nothing is ever overwritten — see <a href='/ledger'>Decisions</a>."
            "</p></fieldset>"
        )
    second = (
        "<label class='field'>Second adjudicator (required — safety-class attribute, FR-8.9)</label>"
        "<input type='text' name='second' required size='24'>"
        if redline.requires_two_signatures
        else ""
    )
    return (
        "<fieldset><legend>Adjudication (FR-7.6)</legend>"
        f"<form method='post' action='/adjudicate' id='adj-{_e(redline.redline_id)}'>"
        f"<input type='hidden' name='redline_id' value='{_e(redline.redline_id)}'>"
        f"<input type='hidden' name='sku' value='{_e(result.record.sku_id)}'>"
        "<input type='hidden' name='seconds' value='' class='seconds'>"
        "<input type='hidden' name='presented_utc' value='' class='presented'>"
        "<input type='hidden' name='decided_utc' value='' class='decided'>"
        "<label class='field'>Your name</label>"
        "<input type='text' name='by' required size='24'>"
        "<label class='field'>Your role (decides whether this session can be measured)</label>"
        "<select name='role' required>"
        "<option value=''>-- state your role --</option>"
        "<option value='domain_reviewer'>Domain reviewer -- I judge product data for a living "
        "and I did not build this tool</option>"
        "<option value='implementer'>Implementer -- I worked on Errata</option>"
        "<option value='other'>Other</option>"
        "</select>"
        f"{second}"
        "<label class='field'>Did the box support the claim? (FR-9.4)</label>"
        "<select name='evidence_accepted'>"
        "<option value=''>not stated</option><option value='yes'>yes</option>"
        "<option value='no'>no</option></select>"
        "<label class='field'>Note</label><textarea name='note'></textarea>"
        "<div style='display:flex;gap:8px;margin-top:10px;flex-wrap:wrap'>"
        "<button class='accept' name='decision' value='accept'>Accept redline</button>"
        "<button class='keep' name='decision' value='keep'>Keep catalog</button>"
        "<button class='escalate' name='decision' value='escalate'>Escalate</button>"
        "</div>"
        "<p class='body' style='color:var(--muted);margin-bottom:0'>Accepting writes a claim to "
        "Errata's ledger. <strong>Nothing is written to any catalog</strong> (ADR-001).</p>"
        "</form></fieldset>"
    )


def _sku_page(service: AuditService, result: SkuAudit, *, focus_id: str = "") -> str:
    decided = service.decided_ids()
    findings = result.findings
    focus = next(
        (o for o in findings if o.redline and str(o.redline.redline_id) == focus_id),
        findings[0] if findings else None,
    )

    left = ["<div class='pane'><h2>Queue</h2>"]
    if not findings:
        left.append(
            "<p class='body'>No findings. Every attribute the audit could check is supported by "
            "the document.</p>"
        )
    for outcome in findings:
        left.append(
            _queue_row_html(
                result, outcome, decided=str(outcome.redline.redline_id) in decided
            )
        )
    if result.declined:
        left.append("<h2>Declined</h2><ul class='declined'>")
        for outcome in result.declined:
            reason = outcome.declined_reason.value if outcome.declined_reason else "unspecified"
            left.append(
                f"<li><strong>{_e(outcome.attribute.label)}</strong><br>"
                f"<span class='reason'>{_e(reason)}</span><br>{_e(outcome.detail)}</li>"
            )
        left.append("</ul>")
    if result.resolved:
        left.append("<h2>Checked and supported</h2><ul class='declined'>")
        for outcome in result.resolved:
            klass = outcome.comparison.disagreement_class.value if outcome.comparison else ""
            left.append(
                f"<li>{_e(outcome.attribute.label)}: {_e(str(outcome.catalog_value))} / "
                f"{_e(str(outcome.derived_value))} <span class='reason'>{_e(klass)}</span></li>"
            )
        left.append("</ul>")
    left.append("</div>")

    middle = ["<div class='pane'><h2>Evidence</h2>"]
    if focus is None:
        middle.append(
            "<p class='body'>Nothing to adjudicate on this record. Evidence is shown for the "
            "finding under review, and there is none.</p>"
        )
    else:
        middle.append(_evidence_html(result, focus))
    middle.append("</div>")

    resolution = result.resolution
    candidates = "".join(
        f"<tr><td>{_e(c.class_id)}</td><td>{_e(c.description)}</td><td>{c.score:.3f}</td></tr>"
        for c in resolution.top5
    )
    history = service.ledger.history(result.record.sku_id)
    history_rows = "".join(
        f"<tr><td>{_e(str(event.get('recorded_utc', ''))[:19])}</td>"
        f"<td>{_e(event.kind)}</td>"
        f"<td>{_e(str(event.payload.get('attribute_uri', '')))}<br>"
        f"{_e(str(event.payload.get('decision', event.payload.get('value_raw', ''))))}</td></tr>"
        for event in history
    )
    right = [
        "<div class='pane'><h2>Claim history</h2>",
        (
            f"<table class='history'>{history_rows}</table>"
            if history_rows
            else "<p class='body'>No decisions recorded for this SKU yet. Every adjudication is "
            "appended and nothing is ever overwritten.</p>"
        ),
        (
            _adjudication_form(
                result, focus, decided=str(focus.redline.redline_id) in decided
            )
            if focus and focus.redline
            else ""
        ),
        "<details open><summary>Class resolution — three stages</summary>"
        f"<p class='body'>retrieved {len(resolution.retrieved)} → reranked to "
        f"{len(resolution.top5)} → selected by <code>{_e(resolution.selector)}</code>; retrieval "
        f"method <code>{_e(resolution.retrieval_method)}</code>.</p>"
        f"<table class='history'>{candidates}</table>"
        + (f"<p class='body'>{_e(resolution.detail)}</p>" if resolution.detail else "")
        + "</details>",
        "<details><summary>Document</summary>"
        f"<p class='body'><code>{_e(result.document.doc_id)}</code><br>"
        f"sha256 <code>{_e(result.document.sha256)}</code><br>"
        f"{_e(result.layout_version)} · {_e(result.tables_version)} · "
        f"{_e(result.derive_version)}</p></details>",
        "</div>",
    ]

    header = (
        f"<h1 style='margin:0 0 4px;font-size:20px'>{_e(result.record.sku_id)}"
        f"<span class='badge'>{_e(result.class_uri or 'class not resolved')}</span></h1>"
        f"<p class='body' style='color:var(--muted);margin-top:0'>audited against "
        f"{_e(result.document.doc_id)} · coverage {result.coverage:.0%} · "
        f"{len(findings)} finding(s), {len(result.resolved)} supported, "
        f"{len(result.declined)} declined</p>"
    )
    timer = (
        # FR-9.3. The elapsed seconds AND the two endpoints they were computed from. An elapsed
        # number on its own cannot be audited -- nothing about "47.3" says when it started or
        # whether the tab sat open over lunch. Two ISO timestamps can be read, checked against the
        # ledger's own event time, and thrown out if they disagree.
        "<script>document.addEventListener('DOMContentLoaded',function(){"
        "var t=Date.now();var iso=new Date(t).toISOString();"
        "document.querySelectorAll('form').forEach(function(f){f.addEventListener('submit',"
        "function(){var now=Date.now();"
        "var s=f.querySelector('.seconds');if(s){s.value=((now-t)/1000).toFixed(1);}"
        "var p=f.querySelector('.presented');if(p){p.value=iso;}"
        "var d=f.querySelector('.decided');if(d){d.value=new Date(now).toISOString();}"
        "});});});</script>"
    )
    return (
        f"<main>{header}</main>"
        + "<div class='panes'>"
        + "".join(left)
        + "".join(middle)
        + "".join(right)
        + "</div>"
        + timer
    )


def _status_page(service: AuditService) -> str:
    decisions, accepted, kept, sentence = service.calibration_state()
    rows = [
        (
            "FR-2.2 embedding retrieval + cross-encoder",
            "interfaces only — retrieval is lexical, and every resolution says so",
        ),
        (
            "FR-2.2 LLM selector",
            "an interface, capped at five candidates by a function that raises. Measured cost of "
            "its absence: top-1 47.1% against top-5 100% on the labelled set",
        ),
        ("FR-6.1 calibration set", sentence),
        ("FR-1.4 OCR", "not built — born-digital documents only; a scan is declined with a reason"),
        (
            "R0 gate 3",
            "NOT MEASURED by decision D-1. R1 was entered on an explicit recorded waiver (D-3), "
            "not on a met entry criterion",
        ),
        (
            "The catalog under audit",
            "constructed — no public feed for these products exists, so defects were injected on "
            "purpose. The datasheet, the spans and the boxes are real",
        ),
    ]
    body = "".join(
        f"<tr><td><strong>{_e(what)}</strong></td><td>{state}</td></tr>" for what, state in rows
    )
    return (
        "<h1 style='margin:0 0 4px;font-size:20px'>What this does not claim</h1>"
        "<p class='body' style='color:var(--muted);margin-top:0'>A console that only lists what it "
        "can do is a sales page. This is the other list, and it is reachable from every screen.</p>"
        f"<table class='grid'>{body}</table>"
        f"<p class='body'>Decisions recorded: {decisions} ({accepted} accepted, {kept} kept).</p>"
    )


def _ledger_page(service: AuditService) -> str:
    events = list(service.ledger.events())[-200:]
    rows = "".join(
        f"<tr><td>{_e(str(event.get('recorded_utc', ''))[:19])}</td><td>{_e(event.kind)}</td>"
        f"<td>{_e(str(event.payload.get('sku_id', '')))}</td>"
        f"<td>{_e(str(event.payload.get('attribute_uri', '')))}</td>"
        f"<td>{_e(str(event.payload.get('decision', '')))}</td>"
        f"<td>{_e(str(event.payload.get('decided_by', '')))}</td>"
        f"<td>{_e(str(event.payload.get('seconds_to_decision', '') or ''))}</td></tr>"
        for event in reversed(events)
    )
    return (
        "<h1 style='margin:0 0 4px;font-size:20px'>Decisions</h1>"
        f"<p class='body' style='color:var(--muted);margin-top:0'>{_e(service.ledger.path)} — "
        "append-only. There is no update method and no delete method, which is what makes reversing "
        "a batch a query rather than a recovery project (§4.3).</p>"
        "<table class='grid'><tr><th>when</th><th>event</th><th>sku</th><th>attribute</th>"
        f"<th>decision</th><th>by</th><th>seconds</th></tr>{rows}</table>"
    )


# ------------------------------------------------------------------------------------------------
# The server
# ------------------------------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    service: AuditService
    server_version = "errata-audit"
    sys_version = ""

    def log_message(self, format: str, *args) -> None:
        # One line per request, to stderr, without the default's date duplication.
        print(f"  {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)

    # -- helpers --------------------------------------------------------------------------

    def _send(self, payload: bytes, *, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        # This console renders a manufacturer's document and a customer's catalog. It has no
        # business being embedded in someone else's page, and no business talking to anything
        # off-origin -- there is nothing off-origin to talk to.
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; form-action 'self'",
        )
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- routing --------------------------------------------------------------------------

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            path = parsed.path.rstrip("/") or "/"

            if path == "/":
                limit = int(query.get("limit", [DEFAULT_SCAN])[0])
                flash = html.escape(query.get("flash", [""])[0])
                self._send(
                    _page(
                        "Review queue",
                        _dashboard(self.service, limit=limit),
                        active="queue",
                        flash=flash,
                    )
                )
                return

            if path == "/audit":
                if query.get("random"):
                    import random

                    record = random.choice(self.service.catalog)
                    self._redirect(f"/sku/{urllib.parse.quote(record.sku_id)}")
                    return
                sku = (query.get("sku", [""])[0]).strip()
                if not sku:
                    self._redirect("/?flash=Enter+a+SKU%2C+or+let+one+be+picked+at+runtime.")
                    return
                self._redirect(f"/sku/{urllib.parse.quote(sku)}")
                return

            if path.startswith("/sku/"):
                sku = urllib.parse.unquote(path[len("/sku/") :])
                result = self.service.audit(sku)
                if result is None:
                    self._send(
                        _page(
                            "Not audited",
                            _not_audited(self.service, sku),
                            active="queue",
                            flash="This record was not audited. The reason is below, and it is a "
                            "stated reason rather than a silent skip.",
                            bad=True,
                        ),
                        status=404,
                    )
                    return
                focus = query.get("finding", [""])[0]
                flash = html.escape(query.get("flash", [""])[0])
                self._send(
                    _page(
                        result.record.sku_id,
                        _sku_page(self.service, result, focus_id=focus),
                        active="queue",
                        flash=flash,
                        wrap=False,
                    )
                )
                return

            if path == "/status":
                self._send(_page("Status", _status_page(self.service), active="status"))
                return

            if path == "/ledger":
                self._send(_page("Decisions", _ledger_page(self.service), active="ledger"))
                return

            self._send(_page("Not found", "<p class='body'>No such page.</p>"), status=404)
        except Exception:  # pragma: no cover - defensive; a console must not die on one bad URL
            self._send(
                _page("Error", f"<pre>{html.escape(traceback.format_exc())}</pre>"), status=500
            )

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))

            def field(name: str, default: str = "") -> str:
                return (form.get(name, [default])[0] or "").strip()

            if urllib.parse.urlparse(self.path).path.rstrip("/") != "/adjudicate":
                self._send(_page("Not found", "<p class='body'>No such endpoint.</p>"), status=404)
                return

            decision = {
                "accept": Decision.ACCEPT_REDLINE,
                "keep": Decision.KEEP_CATALOG,
                "escalate": Decision.ESCALATE,
            }.get(field("decision"))
            sku = field("sku")
            if decision is None:
                self._redirect(f"/sku/{urllib.parse.quote(sku)}?flash=Unknown+decision.")
                return

            evidence = field("evidence_accepted")
            seconds = field("seconds")
            try:
                _redline, sentence = self.service.adjudicate(
                    field("redline_id"),
                    decision=decision,
                    decided_by=field("by") or "unnamed reviewer",
                    note=field("note"),
                    second_adjudicator=field("second"),
                    seconds=float(seconds) if seconds else None,
                    evidence_accepted=None if not evidence else evidence == "yes",
                    decided_by_role=field("role"),
                    presented_utc=field("presented_utc"),
                    decided_utc=field("decided_utc"),
                )
            except (ValueError, KeyError) as error:
                message = str(error).splitlines()[0]
                self._redirect(
                    f"/sku/{urllib.parse.quote(sku)}?flash={urllib.parse.quote(message[:300])}"
                )
                return

            self._redirect(f"/sku/{urllib.parse.quote(sku)}?flash={urllib.parse.quote(sentence)}")
        except Exception:  # pragma: no cover - defensive
            self._send(
                _page("Error", f"<pre>{html.escape(traceback.format_exc())}</pre>"), status=500
            )


def _not_audited(service: AuditService, sku: str) -> str:
    record = service.record(sku)
    if record is None:
        return (
            f"<p class='body'>No record <code>{_e(sku)}</code> in "
            f"<code>{_e(service.catalog_path)}</code>.</p>"
        )
    return (
        f"<p class='body'><strong>{_e(record.sku_id)}</strong> names "
        f"<code>{_e(record.datasheet or '(no datasheet)')}</code>, and it was not supplied to this "
        "server. Declined with <code>no_source_document</code> (FR-6.2): this record joins the "
        "document-recovery queue. It is <em>not</em> audited against a different manufacturer's "
        "PDF, and it is not silently skipped.</p>"
    )


def serve(
    service: AuditService,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Start the console. Returns the server; the caller decides whether to block."""
    handler = type("_BoundHandler", (_Handler,), {"service": service})
    return ThreadingHTTPServer((host, port), handler)
