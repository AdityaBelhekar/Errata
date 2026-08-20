"""The R2 report: text for a terminal, HTML for everybody else.

One rule governs both renderings and it is the reason this module is not just string formatting:
**no number appears without the number that makes it readable.** A defect count is printed next to
the groundable fraction; a coverage figure is printed next to the population it was computed over;
a cluster size is printed next to the fingerprint that produced it; a ranking is printed next to
the factors that produced the rank, including the ones nobody supplied.

The banner is not decoration either. The demonstration catalog is constructed, and a report that
did not say so on its face would be the exact failure mode this project was built to audit for in
other people's systems.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .groundable import GroundingStatus
from .run import CatalogRun

__all__ = ["render_html", "render_json", "render_text"]

_RULE = "=" * 96


def render_text(run: CatalogRun, *, top: int = 15, banner: str = "") -> str:
    """The terminal report."""
    lines = [
        _RULE,
        f"ERRATA R2 -- catalog audit of {len(run.records):,} record(s)",
        f"{run.catalog}",
        _RULE,
    ]
    if banner:
        lines += ["", banner]
    lines += [
        "",
        run.groundable.text(),
        "",
        run.cost.text(),
        "",
        # NFR-5. Printed immediately after the work-unit table, because the whole point of the
        # work-unit table is a commercial argument and a commercial argument with no currency in
        # it is a shape without a price. Absent only for a run assembled by hand in a test.
        *(
            [run.priced.text(), ""]
            if run.priced is not None
            else []
        ),
        "FINDINGS",
        f"  queue rows                   {run.findings:,}",
        f"    from T0 (feed structure)   {run.structural_findings:,}",
        f"    from T1 (source document)  {run.grounded_findings:,}",
        f"  error signatures             {len(run.clusters):,}",
        f"  coverage, grounded records   {run.grounded_coverage:.1%}"
        f"   (of {run.groundable.groundable:,} groundable record(s))",
        f"  coverage, whole catalog      {run.catalog_coverage:.1%}",
        "",
        "  read the coverage next to the groundable fraction, always: a coverage computed over the",
        "  records that had a document says nothing about the records that did not.",
        "",
        "DECLINED -- every one with exactly one machine-readable reason (FR-6.2)",
    ]
    for reason, count in run.declined_by_reason().items():
        lines.append(f"  {reason:38s} {count:8,d}")

    lines += ["", f"ERROR SIGNATURES -- computed, not asserted (FR-8.5); {len(run.clusters):,} of them"]
    for cluster in run.clusters[:top]:
        lines.append(f"  {cluster.size:8,d}  {cluster.signature.sentence()}")
        lines.append(f"            fingerprint {cluster.signature.fingerprint}")

    lines += ["", f"QUEUE -- ranked by expected review value (FR-8.4), top {top}"]
    for position, entry in enumerate(run.triage.top(top), start=1):
        lines.append("")
        lines.append(f"  [{position}] EV {entry.expected_review_value:,.2f}  ({entry.tier})")
        for sentence in entry.sentence().splitlines():
            lines.append(f"      {sentence}")
        for factor in entry.factors:
            lines.append(f"        - {factor.sentence()}")

    lines += [
        "",
        f"batch {run.batch_id}",
        f"policy {run.policy_version} - attributes {run.attribute_map_version}"
        + (f" - ETIM {run.etim_release}" if run.etim_release else " - ETIM not loaded (T0 only)"),
    ]
    for note in run.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines)


def render_json(run: CatalogRun, *, top: int = 50) -> str:
    return json.dumps(
        {
            "batch_id": run.batch_id,
            "manifest": run.manifest(),
            "groundable_fraction_report": run.groundable.as_dict(),
            "cost_report": run.cost.as_dict(),
            "priced_cost": run.priced.as_dict() if run.priced is not None else None,
            "versus_extractbench": (
                run.priced.versus_extractbench()
                if run.priced is not None
                else None
            ),
            "findings": {
                "total": run.findings,
                "t0_structural": run.structural_findings,
                "t1_grounded": run.grounded_findings,
                "by_severity": run.triage.by_severity(),
                "requiring_two_signatures": len(run.triage.safety_entries()),
            },
            "coverage": {
                "grounded_records": round(run.grounded_coverage, 4),
                "whole_catalog": round(run.catalog_coverage, 4),
            },
            "declined_by_reason": run.declined_by_reason(),
            "clusters": [
                {
                    "signature_id": cluster.signature.signature_id,
                    "fingerprint": cluster.signature.fingerprint,
                    "size": cluster.size,
                    "sentence": cluster.sentence(),
                    "members": list(cluster.members[:25]),
                }
                for cluster in run.clusters
            ],
            "queue": [entry.as_dict() for entry in run.triage.top(top)],
        },
        indent=2,
        default=str,
    )


_CSS = """
:root { color-scheme: light dark; --fg:#16181d; --bg:#fbfbfa; --muted:#5b6270; --line:#d9dce3;
        --sev1:#b3261e; --sev2:#8a6d00; --sev3:#3b5bdb; --ok:#1f7a4d; --card:#ffffff; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e7e9ee; --bg:#14161a; --muted:#9aa2b1; --line:#2a2e37; --card:#1b1e24; } }
* { box-sizing: border-box; }
body { margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
       font:15px/1.55 ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif; }
main { max-width: 1080px; margin: 0 auto; }
h1 { font-size:1.5rem; margin:0 0 .25rem; letter-spacing:-.01em; }
h2 { font-size:1.05rem; margin:2.25rem 0 .6rem; letter-spacing:-.005em; }
p.sub { color:var(--muted); margin:.15rem 0 1.25rem; }
.banner { border:1px solid var(--line); border-left:4px solid var(--sev2); background:var(--card);
          padding:.85rem 1rem; border-radius:6px; margin:1rem 0 1.5rem; }
table { border-collapse:collapse; width:100%; font-size:.92rem; }
th,td { text-align:left; padding:.4rem .55rem; border-bottom:1px solid var(--line);
        vertical-align:top; }
th { color:var(--muted); font-weight:600; }
td.n, th.n { text-align:right; font-variant-numeric:tabular-nums; }
.card { border:1px solid var(--line); background:var(--card); border-radius:6px;
        padding:.9rem 1rem; margin:.7rem 0; }
.sev1 { color:var(--sev1); font-weight:700; } .sev2 { color:var(--sev2); font-weight:700; }
.sev3 { color:var(--sev3); font-weight:700; }
code, .mono { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.85em; }
.factors { margin:.5rem 0 0; padding-left:1.1rem; color:var(--muted); font-size:.87rem; }
.factors li.unmeasured { font-style:italic; }
.evidence { border-left:3px solid var(--line); padding-left:.7rem; margin-top:.5rem;
            color:var(--muted); font-size:.87rem; }
.wrap { overflow-x:auto; }
footer { margin-top:3rem; color:var(--muted); font-size:.84rem; border-top:1px solid var(--line);
         padding-top:1rem; }
"""


def render_html(run: CatalogRun, *, top: int = 25, banner: str = "") -> str:
    """A self-contained report. No network, no fonts, no scripts."""
    e = html.escape
    parts: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Errata R2 - {e(Path(run.catalog).name)}</title>",
        f"<style>{_CSS}</style></head><body><main>",
        "<h1>Errata R2 &mdash; catalog audit</h1>",
        f"<p class='sub'>{len(run.records):,} record(s) from <code>{e(run.catalog)}</code> "
        f"&middot; batch <code>{e(run.batch_id)}</code></p>",
    ]

    if banner:
        parts.append(f"<div class='banner'>{e(banner)}</div>")

    parts.append("<div class='banner'>")
    parts.append(
        "<strong>What this report does not claim.</strong> There is no calibration set (FR-6.1), "
        "so structural findings carry no probability and are ranked on blast radius alone &mdash; "
        "every queue row says so. Errata grades; it never writes to a catalog (ADR-001)."
    )
    parts.append("</div>")

    # -- groundable fraction ------------------------------------------------------------------
    parts.append("<h2>Groundable fraction &mdash; before any audit (FR-8.1)</h2>")
    parts.append("<div class='wrap'><table><tr><th>bucket</th><th class='n'>records</th>"
                 "<th class='n'>share</th><th>meaning</th></tr>")
    counts = run.groundable.counts()
    for status in GroundingStatus:
        count = counts[status]
        share = (count / run.groundable.total * 100) if run.groundable.total else 0.0
        parts.append(
            f"<tr><td class='mono'>{e(status.value)}</td><td class='n'>{count:,}</td>"
            f"<td class='n'>{share:.2f}%</td><td>{e(status.sentence)}</td></tr>"
        )
    parts.append("</table></div>")
    leads = run.groundable.recovery_leads()
    if leads:
        parts.append("<div class='card'><strong>Document-recovery leads.</strong> One document, "
                     "this many records unlocked:<ul>")
        for name, count in leads[:10]:
            parts.append(f"<li><code>{e(name)}</code> &mdash; {count:,} record(s)</li>")
        parts.append("</ul></div>")

    # -- cost ---------------------------------------------------------------------------------
    parts.append("<h2>Tiered execution &mdash; measured, not estimated (FR-8.7)</h2>")
    parts.append("<div class='wrap'><table><tr><th>tier</th><th>what it does</th>"
                 "<th class='n'>records</th><th class='n'>work</th><th>scales with</th></tr>")
    for cost in run.cost.tiers:
        parts.append(
            f"<tr><td class='mono'>{e(cost.tier.value)}</td><td>{e(cost.tier.description)}</td>"
            f"<td class='n'>{cost.records_entered:,}</td>"
            f"<td class='n'>{cost.work_units:,} {e(cost.unit)}</td>"
            f"<td>{e(cost.tier.scales_with)}</td></tr>"
        )
    parts.append("</table></div>")
    parts.append(
        f"<p class='sub'>T2 and T3 volume bounded by the disagreement count rather than the record "
        f"count: <strong>{run.cost.scales_with_error_count()}</strong> "
        f"({run.cost.error_count:,} disagreement(s) over {len(run.records):,} record(s)).</p>"
    )

    # -- headline numbers ---------------------------------------------------------------------
    parts.append("<h2>Findings</h2><div class='wrap'><table>")
    for label, value in (
        ("queue rows", f"{run.findings:,}"),
        ("&nbsp;&nbsp;from T0 &mdash; the feed's own structure", f"{run.structural_findings:,}"),
        ("&nbsp;&nbsp;from T1 &mdash; a source document", f"{run.grounded_findings:,}"),
        ("error signatures", f"{len(run.clusters):,}"),
        ("rows needing two signatures (FR-8.9)", f"{len(run.triage.safety_entries()):,}"),
        ("coverage over groundable records", f"{run.grounded_coverage:.1%}"),
        ("coverage over the whole catalog", f"{run.catalog_coverage:.1%}"),
    ):
        parts.append(f"<tr><td>{label}</td><td class='n'>{value}</td></tr>")
    parts.append("</table></div>")

    parts.append("<h2>Declined &mdash; one machine-readable reason each (FR-6.2)</h2>")
    parts.append("<div class='wrap'><table><tr><th>reason</th><th class='n'>records</th></tr>")
    for reason, count in run.declined_by_reason().items():
        parts.append(f"<tr><td class='mono'>{e(reason)}</td><td class='n'>{count:,}</td></tr>")
    parts.append("</table></div>")

    # -- clusters -----------------------------------------------------------------------------
    parts.append("<h2>Error signatures &mdash; computed, not asserted (FR-8.5)</h2>")
    parts.append(
        "<p class='sub'>Signatures key to document and data artifacts only. There is no field for "
        "a supplier, a brand or a company, and a test asserts the absence (FR-8.6).</p>"
    )
    parts.append("<div class='wrap'><table><tr><th class='n'>records</th><th>pattern</th>"
                 "<th>fingerprint</th></tr>")
    for cluster in run.clusters[:top]:
        parts.append(
            f"<tr><td class='n'>{cluster.size:,}</td><td>{e(cluster.signature.sentence())}</td>"
            f"<td class='mono'>{e(cluster.signature.fingerprint)}</td></tr>"
        )
    parts.append("</table></div>")

    # -- queue --------------------------------------------------------------------------------
    parts.append(f"<h2>Queue &mdash; ranked by expected review value (FR-8.4), top {top}</h2>")
    for entry in run.triage.top(top):
        redline = entry.redline
        severity = int(redline.severity)
        parts.append("<div class='card'>")
        parts.append(
            f"<div><span class='sev{min(severity, 3)}'>SEV-{severity}</span> "
            f"&middot; <code>{e(redline.sku_id)}</code> &middot; "
            f"{e(redline.attribute_label or redline.attribute_uri)} "
            f"&middot; <span class='mono'>EV {entry.expected_review_value:,.2f}</span> "
            f"&middot; <span class='mono'>{e(entry.tier)}</span></div>"
        )
        for line in entry.sentence().splitlines()[1:]:
            parts.append(f"<div>{e(line)}</div>")
        parts.append(f"<div class='evidence'>{e(redline.rationale)}</div>")
        parts.append(
            f"<div class='evidence'><strong>The case for the catalog:</strong> "
            f"{e(redline.counter_evidence.summary)}</div>"
        )
        for evidence in redline.evidence:
            parts.append(
                f"<div class='evidence mono'>{e(evidence.doc_id)} p{evidence.page} "
                f"chars {evidence.char_span[0]}&ndash;{evidence.char_span[1]}"
                + (f" &middot; column {e(evidence.column_header)}" if evidence.column_header else "")
                + (f" &middot; row {e(evidence.row_header)}" if evidence.row_header else "")
                + f"<br>{e(evidence.snippet[:200])}</div>"
            )
        parts.append("<ul class='factors'>")
        for factor in entry.factors:
            css = "" if factor.measured else " class='unmeasured'"
            parts.append(f"<li{css}>{e(factor.sentence())}</li>")
        parts.append("</ul></div>")

    parts.append(
        "<footer>"
        f"batch <code>{e(run.batch_id)}</code><br>"
        f"policy {e(run.policy_version)} &middot; attributes {e(run.attribute_map_version)} &middot; "
        + (f"ETIM {e(run.etim_release)}" if run.etim_release
           else "ETIM not loaded &mdash; T0 only")
        + f"<br>{e(run.scale_version)} &middot; {e(run.audit_version)} &middot; "
        f"{e(run.structural_version)}<br>"
        + (f"{e(run.etim_attribution)}<br>" if run.etim_attribution else "")
        + "".join(f"{e(note)}<br>" for note in run.notes)
        + "</footer>"
    )
    parts.append("</main></body></html>")
    return "\n".join(parts)
