"""FR-7.1 - FR-7.8 -- the reviewer console: queue, evidence, claim history.

The console is where the product either earns a reviewer's trust or loses it, and the requirements
are unusually specific about *how* rather than *what*. Four of them are load-bearing and all four
are honoured here structurally rather than stylistically:

**FR-7.5 -- a queue row is a sentence, never a bare confidence percentage.** No surface in this
module renders a raw score as the primary signal. The sentence comes from ``Redline.queue_sentence``
in ``errata_spec``, so the wording is the same in the CLI, the HTML and anything built later.

**FR-7.2 / FR-7.3 -- the box lands on the words, and the headers come with it.** The value's words
are outlined in one colour and its row and column headers in a second. A number in an engineering
table is not a fact without its headers, and a console that boxed ``16`` and not
*Rated current In A* would be asking the reviewer to supply the meaning themselves.

**FR-7.4 -- the counter-evidence panel is never empty and never absent.** It is rendered for every
finding, including when it says that nothing supports the catalog. That sentence is the finding.

**FR-7.8 -- what the reviewer saw is reconstructible from stored state.** Boxes are drawn from the
``Evidence`` records on the claim -- the stored char span and its projected bbox -- not by re-running
the extractor at view time. The page image is the only thing regenerated, and it is regenerated from
the exact bytes named by ``doc_revision_sha256``, which the register can always produce.

The HTML is one self-contained file with the page images inlined, so it can be mailed to somebody
who has none of this software. That is deliberate: the first reviewer is usually not the buyer.
"""

from __future__ import annotations

import base64
import html
import io
from dataclasses import dataclass

import pymupdf

from errata_spec import Evidence, Severity

from .audit import AttributeOutcome, SkuAudit
from .layout import TextLayer

__all__ = ["PAGE_ZOOM", "PageImage", "render_html", "render_text"]

#: Render scale for the evidence page. 2x keeps 8pt table text legible in a browser without making
#: a single-SKU report bigger than an email will carry.
PAGE_ZOOM = 2.0


@dataclass(frozen=True, slots=True)
class PageImage:
    """One rendered page, plus the transform that puts a PDF box onto it."""

    page: int
    width: int
    height: int
    data_uri: str
    zoom: float = PAGE_ZOOM

    def place(self, box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        """PDF user-space box -> percentage rectangle on the rendered image.

        Percentages rather than pixels so the image can be scaled to fit a screen without the
        boxes drifting off the words -- the one failure that would make the whole panel worthless.
        """
        x0, y0, x1, y1 = box
        return (
            100.0 * x0 * self.zoom / self.width,
            100.0 * y0 * self.zoom / self.height,
            100.0 * (x1 - x0) * self.zoom / self.width,
            100.0 * (y1 - y0) * self.zoom / self.height,
        )


def render_page(path, page_number: int, *, zoom: float = PAGE_ZOOM) -> PageImage:
    """Render one page of the stored document to an inline PNG.

    The document is opened from the blob store by content hash, so the image is of the exact bytes
    the claim was made against -- not of whatever is at the supplier's URL today.
    """
    document = pymupdf.open(path)
    page = document[page_number - 1]
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    buffer = io.BytesIO(pixmap.tobytes("png"))
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return PageImage(
        page=page_number,
        width=pixmap.width,
        height=pixmap.height,
        data_uri=f"data:image/png;base64,{encoded}",
        zoom=zoom,
    )


# ------------------------------------------------------------------------------------------------
# Text -- FR-7.9's CLI output
# ------------------------------------------------------------------------------------------------


def render_text(audit: SkuAudit, *, show_resolved: bool = True) -> str:
    """The CLI's redline, or its honest abstention."""
    lines: list[str] = []
    record = audit.record
    lines.append("=" * 78)
    lines.append(f"ERRATA -- audit of {record.sku_id}" + (f" ({record.manufacturer})" if record.manufacturer else ""))
    lines.append("=" * 78)
    lines.append(f"document      {audit.document.doc_id}")
    lines.append(f"revision      sha256:{audit.document.sha256}")
    if audit.document.source_url:
        lines.append(f"source        {audit.document.source_url}")
    lines.append(f"text layer    {audit.layout_version}   tables {audit.tables_version}")

    resolution = audit.resolution
    if resolution.class_id:
        lines.append(
            f"class         {audit.class_uri}  (retrieve {len(resolution.retrieved)} -> rerank "
            f"{len(resolution.top5)} -> {resolution.selector}, margin {resolution.margin:.3f})"
        )
    else:
        lines.append(
            f"class         NOT RESOLVED -- {resolution.declined_reason.value if resolution.declined_reason else 'unknown'}"
        )
        lines.append(f"              {resolution.detail}")

    findings = audit.findings
    lines.append("")
    lines.append(
        f"{len(findings)} finding(s) - {len(audit.resolved)} checked and supported - "
        f"{len(audit.declined)} declined - coverage {audit.coverage:.0%}"
    )

    if findings:
        lines.append("")
        lines.append("-" * 78)
        lines.append("FINDINGS -- ranked by expected review value (P(wrong) x blast radius)")
        lines.append("-" * 78)
    for outcome in findings:
        lines.extend(_finding_text(outcome))

    if audit.declined:
        lines.append("")
        lines.append("-" * 78)
        lines.append("DECLINED -- looked at, not audited. Every row has exactly one reason.")
        lines.append("-" * 78)
        for outcome in audit.declined:
            reason = outcome.declined_reason.value if outcome.declined_reason else "unspecified"
            lines.append(f"  {outcome.attribute.label} ({reason})")
            lines.append(f"    {outcome.detail}")

    if show_resolved and audit.resolved:
        lines.append("")
        lines.append("-" * 78)
        lines.append("CHECKED AND SUPPORTED -- recorded, not shown to a reviewer")
        lines.append("-" * 78)
        for outcome in audit.resolved:
            klass = outcome.comparison.disagreement_class.value if outcome.comparison else ""
            lines.append(
                f"  {outcome.attribute.label}: catalog {outcome.catalog_value!r} / document "
                f"{outcome.derived_value!r} -- {klass}"
            )

    if audit.not_in_feed:
        lines.append("")
        lines.append(
            "NOT IN FEED: "
            + ", ".join(o.attribute.label for o in audit.not_in_feed)
            + " -- the class declares these and the catalog has no column for them."
        )

    return "\n".join(lines)


def _finding_text(outcome: AttributeOutcome) -> list[str]:
    redline = outcome.redline
    assert redline is not None
    lines = ["", redline.queue_sentence()]
    lines.append(f"  why       {redline.rationale}")

    for evidence in redline.evidence:
        lines.append(f"  evidence  {_evidence_line(evidence)}")
        if evidence.snippet:
            lines.append(f"            ...{evidence.snippet.strip()}...")

    counter = redline.counter_evidence
    lines.append(f"  counter   {counter.summary}")
    for evidence in counter.supporting:
        lines.append(f"            {_evidence_line(evidence)}")

    confidence = outcome.confidence
    if confidence.calibrated_p is not None:
        lines.append(
            f"  confidence {confidence.calibrated_p:.2f} calibrated ({confidence.method}, set "
            f"{confidence.calibration_set_id})"
        )
    else:
        lines.append(
            f"  confidence raw {confidence.raw_score:.2f} -- NOT CALIBRATED. No calibration set "
            "exists yet, so this is an evidence-quality score and not a probability."
        )
    return lines


def _evidence_line(evidence: Evidence) -> str:
    box = evidence.bbox
    where = (
        f"page {evidence.page}, chars {evidence.char_span[0]}-{evidence.char_span[1]}"
        + (f", box ({box.x0:.0f},{box.y0:.0f})-({box.x1:.0f},{box.y1:.0f})" if box else "")
    )
    headers = ", ".join(
        part
        for part in (
            f"column {evidence.column_header!r}" if evidence.column_header else "",
            f"row {evidence.row_header!r}" if evidence.row_header else "",
        )
        if part
    )
    return f"{where}" + (f" -- {headers}" if headers else "")


# ------------------------------------------------------------------------------------------------
# HTML -- the three-pane console
# ------------------------------------------------------------------------------------------------

_CSS = """
:root {
  --ink: #16181d; --paper: #ffffff; --muted: #5b6472; --line: #d9dee6;
  --sev1: #b3261e; --sev2: #a35b00; --sev3: #4a5568;
  --value-box: #b3261e; --header-box: #1d6fb8; --counter-box: #2e7d32;
  --panel: #f6f8fa;
}
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif;
       color: var(--ink); background: var(--paper); }
header { padding: 18px 24px; border-bottom: 1px solid var(--line); }
header h1 { margin: 0 0 4px; font-size: 18px; letter-spacing: -0.01em; }
header .meta { color: var(--muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.caveat { margin: 12px 24px; padding: 10px 14px; border-left: 3px solid var(--sev2);
          background: #fff8ec; font-size: 13px; }
.panes { display: grid; grid-template-columns: 340px minmax(420px, 1fr) 340px; gap: 0;
         align-items: start; }
.pane { padding: 16px 20px; border-right: 1px solid var(--line); min-height: 60vh; }
.pane:last-child { border-right: 0; }
.pane h2 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;
           color: var(--muted); margin: 0 0 12px; }
.row { border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; margin-bottom: 10px;
       background: var(--panel); }
.row.sev1 { border-left: 4px solid var(--sev1); }
.row.sev2 { border-left: 4px solid var(--sev2); }
.row.sev3 { border-left: 4px solid var(--sev3); }
.row .head { font-weight: 600; font-size: 13px; margin-bottom: 4px; }
.row .body { font-size: 13px; }
.row .factors { margin: 6px 0 0; padding-left: 18px; color: var(--muted); font-size: 12px; }
.evidence-figure { position: relative; display: inline-block; max-width: 100%; }
.evidence-figure img { width: 100%; display: block; border: 1px solid var(--line); }
.box { position: absolute; border: 2px solid var(--value-box); box-shadow: 0 0 0 2px rgba(255,255,255,.6); }
.box.header { border-color: var(--header-box); border-style: dashed; }
.box.counter { border-color: var(--counter-box); border-style: dotted; }
.legend { font-size: 12px; color: var(--muted); margin: 8px 0 16px; }
.legend span { display: inline-block; margin-right: 14px; }
.swatch { display: inline-block; width: 10px; height: 10px; margin-right: 4px; vertical-align: middle; }
.counter { border: 1px solid var(--counter-box); border-radius: 6px; padding: 10px 12px;
           background: #f2f9f2; font-size: 13px; margin: 12px 0; }
.declined { font-size: 13px; }
.declined li { margin-bottom: 8px; }
.reason { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px;
          color: var(--muted); }
details { margin: 10px 0; font-size: 13px; }
details pre { background: var(--panel); padding: 10px; overflow-x: auto; font-size: 11px;
              max-height: 260px; }
table.history { width: 100%; border-collapse: collapse; font-size: 12px; }
table.history td { border-bottom: 1px solid var(--line); padding: 4px 6px; vertical-align: top; }
footer { padding: 16px 24px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
"""


def render_html(
    audit: SkuAudit,
    *,
    layer: TextLayer | None = None,
    history: tuple[dict, ...] = (),
    etim_attribution: str = "",
) -> str:
    """The three-pane console for one SKU, as one self-contained file."""
    findings = audit.findings
    focus = findings[0] if findings else None
    images: dict[int, PageImage] = {}
    if focus is not None:
        for evidence in (*focus.redline.evidence, *focus.redline.counter_evidence.supporting):
            if evidence.page not in images:
                images[evidence.page] = render_page(audit.document.path, evidence.page)

    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>Errata - {_e(audit.record.sku_id)}</title>",
        f"<style>{_CSS}</style></head><body>",
        _header_html(audit),
        _caveat_html(),
        "<div class='panes'>",
        _queue_pane(audit),
        _evidence_pane(audit, focus, images),
        _history_pane(audit, history),
        "</div>",
        _footer_html(audit, layer, etim_attribution),
        "</body></html>",
    ]
    return "\n".join(parts)


def _header_html(audit: SkuAudit) -> str:
    resolution = audit.resolution
    klass = (
        f"{_e(audit.class_uri)} &middot; resolved by {_e(resolution.selector)}, margin "
        f"{resolution.margin:.3f}"
        if resolution.class_id
        else "<strong>class not resolved</strong> &middot; "
        + _e(resolution.declined_reason.value if resolution.declined_reason else "")
    )
    return (
        "<header>"
        f"<h1>{_e(audit.record.sku_id)} &mdash; audited against {_e(audit.document.doc_id)}</h1>"
        f"<div class='meta'>revision sha256:{_e(audit.document.sha256)}</div>"
        f"<div class='meta'>{klass}</div>"
        f"<div class='meta'>{_e(audit.layout_version)} &middot; {_e(audit.tables_version)} "
        f"&middot; {_e(audit.derive_version)}</div>"
        "</header>"
    )


def _caveat_html() -> str:
    return (
        "<div class='caveat'><strong>Read this with the report.</strong> The datasheet is the "
        "manufacturer's own and is hash-registered; the values Errata re-derives and the boxes it "
        "draws are read from it. <strong>The catalog under audit is constructed</strong> -- no "
        "public feed for these products is available to us, so defects were injected on purpose "
        "(see <code>audit/tools/build_demo_catalog.py</code>). Detection rates from this demo "
        "describe a population we created. Confidences are <strong>raw scores, not calibrated "
        "probabilities</strong>: no calibration set exists yet, because calibration needs reviewer "
        "decisions and nobody has made any.</div>"
    )


def _queue_pane(audit: SkuAudit) -> str:
    rows = ["<div class='pane'><h2>Queue</h2>"]
    if not audit.findings:
        rows.append(
            "<p class='body'>No findings. Every attribute the audit could check is supported by "
            "the document.</p>"
        )
    for outcome in audit.findings:
        redline = outcome.redline
        assert redline is not None
        severity = f"sev{int(redline.severity)}" if redline.severity != Severity.NONE else "sev3"
        factors = "".join(f"<li>{_e(line)}</li>" for line in redline.blast_radius.explain())
        rows.append(
            f"<div class='row {severity}'>"
            f"<div class='head'>SEV-{int(redline.severity)} &middot; {_e(redline.attribute_label)}</div>"
            f"<div class='body'>Catalog says <strong>{_e(redline.catalog_value)}</strong>. "
            f"The evidence says <strong>{_e(redline.proposed_value)}</strong> "
            f"({_e(redline.disagreement_class.value.replace('_', ' '))}).</div>"
            + (f"<ul class='factors'>{factors}</ul>" if factors else "")
            + (
                "<div class='reason'>safety class &mdash; acceptance needs a second named "
                "adjudicator</div>"
                if redline.requires_two_signatures
                else ""
            )
            + "</div>"
        )

    if audit.declined:
        rows.append("<h2>Declined</h2><ul class='declined'>")
        for outcome in audit.declined:
            reason = outcome.declined_reason.value if outcome.declined_reason else "unspecified"
            rows.append(
                f"<li><strong>{_e(outcome.attribute.label)}</strong><br>"
                f"<span class='reason'>{_e(reason)}</span><br>{_e(outcome.detail)}</li>"
            )
        rows.append("</ul>")

    if audit.resolved:
        rows.append("<h2>Checked and supported</h2><ul class='declined'>")
        for outcome in audit.resolved:
            klass = outcome.comparison.disagreement_class.value if outcome.comparison else ""
            rows.append(
                f"<li>{_e(outcome.attribute.label)}: {_e(str(outcome.catalog_value))} / "
                f"{_e(str(outcome.derived_value))} <span class='reason'>{_e(klass)}</span></li>"
            )
        rows.append("</ul>")

    rows.append("</div>")
    return "".join(rows)


def _evidence_pane(
    audit: SkuAudit, focus: AttributeOutcome | None, images: dict[int, PageImage]
) -> str:
    if focus is None or focus.redline is None:
        return (
            "<div class='pane'><h2>Evidence</h2><p class='body'>Nothing to adjudicate. Evidence "
            "is shown for the top finding; there is none.</p></div>"
        )

    redline = focus.redline
    value_boxes = [e for e in redline.evidence if not e.column_header or e.table_cell != e.column_header]
    header_boxes = [e for e in redline.evidence if e.table_cell and e.table_cell == e.column_header]

    out = ["<div class='pane'><h2>Evidence</h2>"]
    out.append(
        "<div class='legend'>"
        "<span><i class='swatch' style='background:var(--value-box)'></i>the value</span>"
        "<span><i class='swatch' style='background:var(--header-box)'></i>its headers</span>"
        "<span><i class='swatch' style='background:var(--counter-box)'></i>counter-evidence</span>"
        "</div>"
    )

    for page_number, image in sorted(images.items()):
        overlays = []
        for evidence in value_boxes:
            if evidence.page == page_number and evidence.bbox:
                overlays.append(_box_html(image, evidence, ""))
        for evidence in header_boxes:
            if evidence.page == page_number and evidence.bbox:
                overlays.append(_box_html(image, evidence, "header"))
        for evidence in redline.counter_evidence.supporting:
            if evidence.page == page_number and evidence.bbox:
                overlays.append(_box_html(image, evidence, "counter"))
        out.append(
            f"<div class='evidence-figure'><img alt='page {page_number}' src='{image.data_uri}'>"
            + "".join(overlays)
            + "</div>"
        )

    for evidence in redline.evidence:
        headers = ", ".join(
            part
            for part in (
                f"column <strong>{_e(evidence.column_header)}</strong>" if evidence.column_header else "",
                f"row <strong>{_e(evidence.row_header)}</strong>" if evidence.row_header else "",
            )
            if part
        )
        out.append(
            f"<p class='body'>page {evidence.page}, chars {evidence.char_span[0]}&ndash;"
            f"{evidence.char_span[1]}"
            + (f" &middot; {headers}" if headers else "")
            + (f"<br><code>{_e(evidence.snippet.strip())}</code>" if evidence.snippet else "")
            + "</p>"
        )

    counter = redline.counter_evidence
    out.append(
        "<div class='counter'><strong>Counter-evidence &mdash; the case for the catalog</strong>"
        f"<div>{_e(counter.summary)}</div>"
        + (
            "<div class='reason'>not independent: derived from the feed under audit</div>"
            if counter.supporting and not counter.independent
            else ""
        )
        + "</div>"
    )
    out.append(f"<p class='body'>{_e(redline.rationale)}</p>")
    out.append("</div>")
    return "".join(out)


def _box_html(image: PageImage, evidence, kind: str) -> str:
    assert evidence.bbox is not None
    left, top, width, height = image.place(
        (evidence.bbox.x0, evidence.bbox.y0, evidence.bbox.x1, evidence.bbox.y1)
    )
    classes = f"box {kind}".strip()
    return (
        f"<div class='{classes}' style='left:{left:.3f}%;top:{top:.3f}%;"
        f"width:{width:.3f}%;height:{height:.3f}%'></div>"
    )


def _history_pane(audit: SkuAudit, history: tuple[dict, ...]) -> str:
    out = ["<div class='pane'><h2>Claim history</h2>"]
    if not history:
        out.append(
            "<p class='body'>No decisions recorded for this SKU yet. Every adjudication is "
            "appended to the ledger and nothing is ever overwritten.</p>"
        )
    else:
        out.append("<table class='history'>")
        for event in history:
            payload = event.get("payload", {})
            out.append(
                f"<tr><td>{_e(event.get('recorded_utc', ''))}</td>"
                f"<td>{_e(event.get('kind', ''))}</td>"
                f"<td>{_e(str(payload.get('attribute_uri', '')))}<br>"
                f"{_e(str(payload.get('decision', payload.get('value_raw', ''))))}</td></tr>"
            )
        out.append("</table>")

    resolution = audit.resolution
    candidates = "".join(
        f"<tr><td>{_e(c.class_id)}</td><td>{_e(c.description)}</td><td>{c.score:.3f}</td></tr>"
        for c in resolution.top5
    )
    out.append(
        "<details open><summary>Class resolution &mdash; three stages</summary>"
        f"<p class='body'>retrieved {len(resolution.retrieved)} &rarr; reranked to "
        f"{len(resolution.top5)} &rarr; selected by <code>{_e(resolution.selector)}</code>. "
        f"Retrieval method: <code>{_e(resolution.retrieval_method)}</code>.</p>"
        f"<table class='history'>{candidates}</table>"
        + (f"<p class='body'>{_e(resolution.detail)}</p>" if resolution.detail else "")
        + "</details>"
    )
    out.append("</div>")
    return "".join(out)


def _footer_html(audit: SkuAudit, layer: TextLayer | None, etim_attribution: str) -> str:
    parts = [
        "<footer>",
        f"<div>Document register: <code>{_e(audit.document.doc_id)}</code> "
        f"sha256:<code>{_e(audit.document.sha256)}</code>"
        + (f" &middot; fetched from {_e(audit.document.source_url)}" if audit.document.source_url else "")
        + "</div>",
    ]
    if etim_attribution:
        parts.append(f"<div>{_e(etim_attribution)}</div>")
    if layer is not None:
        # FR-7.7: the OCR-layer toggle. A reviewer who cannot see what the machine actually read
        # has to take the box on trust, and the whole product is an argument against doing that.
        text = layer.text[:20000]
        parts.append(
            "<details><summary>What the machine read (canonical text layer, first 20,000 chars)"
            f"</summary><pre>{_e(text)}</pre></details>"
        )
    parts.append(
        "<div>Errata proposes; it does not write. Nothing here has been applied to any catalog "
        "(ADR-001).</div></footer>"
    )
    return "".join(parts)


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
