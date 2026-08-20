"""Load the demo catalog, run the real comparator over it, and render the result."""

from __future__ import annotations

import argparse
import html
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from errata_comparator import Comparison, compare_attribute
from errata_spec.taxonomy import DisagreementClass, Severity

from ..console import force_utf8_output
from ..equivalence import Case, load_cases

__all__ = [
    "DemoAttribute",
    "DemoResult",
    "DemoSku",
    "load_demo",
    "main",
    "render_html",
    "render_text",
    "run_demo",
]


@dataclass(frozen=True, slots=True)
class DemoAttribute:
    label: str
    case: Case
    comparison: Comparison

    @property
    def catalog(self) -> str:
        return self.case.a

    @property
    def datasheet(self) -> str:
        return self.case.b


@dataclass(frozen=True, slots=True)
class DemoSku:
    sku: str
    name: str
    attributes: tuple[DemoAttribute, ...]


@dataclass(frozen=True, slots=True)
class DemoResult:
    title: str
    skus: tuple[DemoSku, ...]

    @property
    def every_attribute(self) -> tuple[DemoAttribute, ...]:
        return tuple(a for s in self.skus for a in s.attributes)

    @property
    def findings(self) -> tuple[DemoAttribute, ...]:
        """The reviewer's queue, worst first. Ties broken by sku so the order is deterministic."""
        raised = [a for a in self.every_attribute if a.comparison.raises_finding]
        return tuple(sorted(raised, key=lambda a: (a.comparison.severity, a.case.id)))

    @property
    def resolved_silently(self) -> tuple[DemoAttribute, ...]:
        """Checked, found consistent, and deliberately NOT shown to a reviewer."""
        return tuple(
            a
            for a in self.every_attribute
            if not a.comparison.raises_finding and not a.comparison.is_declined
        )

    @property
    def declined(self) -> tuple[DemoAttribute, ...]:
        return tuple(a for a in self.every_attribute if a.comparison.is_declined)


def load_demo(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        text = resources.files("errata_bench").joinpath("demo/catalog.yaml").read_text("utf-8")
    else:
        text = Path(path).read_text("utf-8")
    return yaml.safe_load(text) or {}


def run_demo(path: Path | None = None) -> DemoResult:
    document = load_demo(path)
    cases = {case.id: case for case in load_cases()}

    skus: list[DemoSku] = []
    for raw_sku in document.get("skus", []):
        attributes: list[DemoAttribute] = []
        for raw_attr in raw_sku.get("attributes", []):
            case_id = str(raw_attr["case"])
            case = cases.get(case_id)
            if case is None:
                # Hard failure on purpose. A demo quietly skipping a case it cannot find is a demo
                # that has drifted from the suite it claims to be grounded in.
                raise KeyError(
                    f"demo catalog references case {case_id!r}, which is not in the equivalence "
                    f"suite. The demo is only honest while every value in it is a cited case."
                )
            attributes.append(
                DemoAttribute(
                    label=str(raw_attr.get("label", case.attribute.label or case.attribute.key)),
                    case=case,
                    comparison=compare_attribute(case.attribute, case.a, case.b),
                )
            )
        skus.append(
            DemoSku(
                sku=str(raw_sku["sku"]),
                name=str(raw_sku.get("name", "")),
                attributes=tuple(attributes),
            )
        )
    return DemoResult(title=str(document.get("title", "Catalog audit")), skus=tuple(skus))


_SEV_LABEL = {
    Severity.SEV1: "SEV-1",
    Severity.SEV2: "SEV-2",
    Severity.SEV3: "SEV-3",
    Severity.NONE: "--",
}


def _class_label(value: DisagreementClass) -> str:
    return value.value.replace("_", " ")


# ---------------------------------------------------------------------------------- text ------


def render_text(result: DemoResult) -> str:
    out: list[str] = []
    add = out.append
    add(f"ERRATA -- {result.title}")
    add("=" * 94)
    add(
        f"{len(result.every_attribute)} attributes checked across {len(result.skus)} SKUs: "
        f"{len(result.findings)} raised, {len(result.resolved_silently)} resolved silently, "
        f"{len(result.declined)} declined."
    )
    add("")
    add("REVIEWER QUEUE -- worst first")
    add("-" * 94)
    if not result.findings:
        add("  (nothing raised)")
    for attribute in result.findings:
        comparison = attribute.comparison
        add(
            f"  [{_SEV_LABEL[comparison.severity]}] {_class_label(comparison.disagreement_class)}"
            f"  --  {attribute.label}"
        )
        add(f"        catalog   : {attribute.catalog!r}")
        add(f"        datasheet : {attribute.datasheet!r}")
        add(f"        why       : {comparison.rationale}")
        add(f"        source    : {' '.join(attribute.case.source.split())[:160]}")
        add(f"        case      : {attribute.case.id}")
        add("")

    add("RESOLVED SILENTLY -- checked, consistent, deliberately not shown to a reviewer")
    add("-" * 94)
    add("  This section is the product. Flagging any of these would burn the reviewer's trust.")
    for attribute in result.resolved_silently:
        add(
            f"  {attribute.catalog!r} vs {attribute.datasheet!r}"
            f"  ->  {_class_label(attribute.comparison.disagreement_class)}   ({attribute.label})"
        )
    add("")

    add("DECLINED -- could not be checked, and says so rather than guessing")
    add("-" * 94)
    if not result.declined:
        add("  (nothing declined)")
    for attribute in result.declined:
        reason = attribute.comparison.declined_reason
        add(
            f"  {attribute.catalog!r} vs {attribute.datasheet!r}"
            f"  ->  {reason.value if reason else 'undetermined'}   ({attribute.label})"
        )
    add("")
    add("-" * 94)
    add("SCOPE: this demonstrates the comparator only. Evidence grounding -- pointing at the box")
    add("on the page a datasheet value came from -- is FR-1.2-1.5 and is NOT built. The datasheet")
    add("values above are supplied, not located. R0 gate 2 remains NOT MEASURED.")
    return "\n".join(out)


# ---------------------------------------------------------------------------------- html ------

_CSS = """:root{
  --ground:#f7f8f9; --surface:#ffffff; --surface-2:#f1f3f5;
  --ink:#16191d; --ink-2:#454d56; --ink-3:#6b747e;
  --rule:#dde1e5; --rule-2:#c8ced4;
  --accent:#0f5c7a; --accent-soft:#e3eef3;
  --sev1:#b3261e; --sev1-soft:#fbe9e7;
  --sev2:#a9601a; --sev2-soft:#fbf0e2;
  --sev3:#5c6672; --sev3-soft:#eef0f2;
  --ok:#2e6f4e; --ok-soft:#e6f1ea;
}
:root:not([data-theme="light"]){ }
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#101317; --surface:#171b20; --surface-2:#1d2228;
    --ink:#e4e8ec; --ink-2:#aab3bc; --ink-3:#7f8891;
    --rule:#272d34; --rule-2:#353c44;
    --accent:#5aa8c8; --accent-soft:#16303c;
    --sev1:#f08a80; --sev1-soft:#3a1c19;
    --sev2:#e0aa66; --sev2-soft:#332617;
    --sev3:#98a2ad; --sev3-soft:#21262c;
    --ok:#79c39a; --ok-soft:#16291f;
  }
}
:root[data-theme="dark"]{
  --ground:#101317; --surface:#171b20; --surface-2:#1d2228;
  --ink:#e4e8ec; --ink-2:#aab3bc; --ink-3:#7f8891;
  --rule:#272d34; --rule-2:#353c44;
  --accent:#5aa8c8; --accent-soft:#16303c;
  --sev1:#f08a80; --sev1-soft:#3a1c19;
  --sev2:#e0aa66; --sev2-soft:#332617;
  --sev3:#98a2ad; --sev3-soft:#21262c;
  --ok:#79c39a; --ok-soft:#16291f;
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;
  font-size:15px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:920px;margin:0 auto;padding:56px 24px 96px;}
h1,h2,h3{font-family:"IBM Plex Serif",Georgia,serif;text-wrap:balance;margin:0;font-weight:600;}
h1{font-size:31px;line-height:1.25;letter-spacing:-0.01em;}
h2{font-size:20px;letter-spacing:-0.005em;}
.mono{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace;font-variant-numeric:tabular-nums;}
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
}
header.masthead{display:flex;flex-direction:column;gap:10px;
  padding-bottom:22px;border-bottom:2px solid var(--ink);}
header.masthead .sub{color:var(--ink-2);font-size:15px;max-width:64ch;}

.counts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
  background:var(--rule);border:1px solid var(--rule);margin:28px 0 44px;}
.count{background:var(--surface);padding:16px 18px;display:flex;flex-direction:column;gap:3px;}
.count .n{font-family:"IBM Plex Mono",monospace;font-size:27px;line-height:1;font-variant-numeric:tabular-nums;}
.count .l{font-size:12.5px;color:var(--ink-3);}
.count.is-raised .n{color:var(--sev1);}
.count.is-silent .n{color:var(--ok);}
.count.is-declined .n{color:var(--ink-2);}

section{margin-bottom:52px;}
.sec-head{display:flex;flex-direction:column;gap:6px;margin-bottom:8px;}
.sec-note{color:var(--ink-2);font-size:14px;max-width:68ch;}

.finding{background:var(--surface);border:1px solid var(--rule);border-left:4px solid var(--sev3);
  padding:16px 18px;display:flex;flex-direction:column;gap:12px;}
.findings{display:flex;flex-direction:column;gap:10px;margin-top:18px;}
.finding.s1{border-left-color:var(--sev1);}
.finding.s2{border-left-color:var(--sev2);}
.finding.s3{border-left-color:var(--sev3);}
.f-top{display:flex;flex-wrap:wrap;align-items:center;gap:10px;}
.chip{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.08em;
  padding:3px 8px;border-radius:2px;text-transform:uppercase;white-space:nowrap;}
.chip.s1{background:var(--sev1-soft);color:var(--sev1);}
.chip.s2{background:var(--sev2-soft);color:var(--sev2);}
.chip.s3{background:var(--sev3-soft);color:var(--sev3);}
.f-class{font-size:14px;font-weight:600;}
.f-attr{color:var(--ink-3);font-size:13px;margin-left:auto;}

.vs{display:grid;grid-template-columns:1fr auto 1fr;gap:14px;align-items:stretch;
  background:var(--surface-2);border:1px solid var(--rule);}
.vs .side{padding:11px 14px;display:flex;flex-direction:column;gap:4px;min-width:0;}
.vs .val{font-family:"IBM Plex Mono",monospace;font-size:15px;word-break:break-word;}
.vs .divider{width:1px;background:var(--rule-2);}
.vs .cap{font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-3);}

.why{font-size:14px;color:var(--ink-2);}
.why strong{color:var(--ink);font-weight:600;}
.src{border-top:1px dotted var(--rule-2);padding-top:10px;display:flex;flex-direction:column;gap:5px;}
.src .lab{font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-3);}
.src .txt{font-size:13px;color:var(--ink-2);}
.case-id{font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--accent);}

table{width:100%;border-collapse:collapse;font-size:14px;margin-top:16px;}
.tscroll{overflow-x:auto;border:1px solid var(--rule);background:var(--surface);}
th{text-align:left;font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-3);font-weight:400;
  padding:10px 14px;border-bottom:1px solid var(--rule);white-space:nowrap;}
td{padding:10px 14px;border-bottom:1px solid var(--rule);vertical-align:top;}
tr:last-child td{border-bottom:none;}
td.v{font-family:"IBM Plex Mono",monospace;white-space:nowrap;}
.verdict{font-family:"IBM Plex Mono",monospace;font-size:12px;}
.verdict.ok{color:var(--ok);}
.verdict.dec{color:var(--ink-3);}

footer.scope{border:1px solid var(--rule-2);border-top:3px solid var(--accent);
  background:var(--surface);padding:20px 22px;display:flex;flex-direction:column;gap:10px;}
footer.scope p{margin:0;font-size:13.5px;color:var(--ink-2);max-width:74ch;}
footer.scope strong{color:var(--ink);}
a{color:var(--accent);}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
@media (max-width:620px){
  .vs{grid-template-columns:1fr;}
  .vs .divider{width:auto;height:1px;}
  .f-attr{margin-left:0;flex-basis:100%;}
  h1{font-size:26px;}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important;}}
"""

_SEV_CLASS = {Severity.SEV1: "s1", Severity.SEV2: "s2", Severity.SEV3: "s3", Severity.NONE: "s3"}


def _e(text: object) -> str:
    return html.escape(str(text), quote=True)


def _finding_html(attribute: DemoAttribute) -> str:
    comparison = attribute.comparison
    sev = _SEV_CLASS[comparison.severity]
    source = " ".join(attribute.case.source.split())
    return f"""      <article class="finding {sev}">
        <div class="f-top">
          <span class="chip {sev}">{_e(_SEV_LABEL[comparison.severity])}</span>
          <span class="f-class">{_e(_class_label(comparison.disagreement_class))}</span>
          <span class="f-attr">{_e(attribute.label)} &middot; {_e(attribute.case.attribute.key)}</span>
        </div>
        <div class="vs">
          <div class="side">
            <span class="cap">Catalog says</span>
            <span class="val">{_e(attribute.catalog)}</span>
          </div>
          <div class="divider"></div>
          <div class="side">
            <span class="cap">Datasheet says</span>
            <span class="val">{_e(attribute.datasheet)}</span>
          </div>
        </div>
        <p class="why">{_e(comparison.rationale)}</p>
        <div class="src">
          <span class="lab">Grounds</span>
          <span class="txt">{_e(source)}</span>
          <span class="case-id">equivalence suite &middot; {_e(attribute.case.id)}</span>
        </div>
      </article>"""


def render_html(result: DemoResult) -> str:
    """A self-contained report page. Deliberately states what it does NOT show."""
    findings = result.findings
    silent = result.resolved_silently
    declined = result.declined

    findings_html = (
        "\n".join(_finding_html(a) for a in findings)
        if findings
        else '      <p class="sec-note">Nothing raised.</p>'
    )

    silent_rows = "\n".join(
        f"""          <tr>
            <td class="v">{_e(a.catalog)}</td>
            <td class="v">{_e(a.datasheet)}</td>
            <td><span class="verdict ok">{_e(_class_label(a.comparison.disagreement_class))}</span></td>
            <td>{_e(a.label)}</td>
          </tr>"""
        for a in silent
    )

    declined_rows = "\n".join(
        f"""          <tr>
            <td class="v">{_e(a.catalog)}</td>
            <td class="v">{_e(a.datasheet)}</td>
            <td><span class="verdict dec">{_e(a.comparison.declined_reason.value if a.comparison.declined_reason else "undetermined")}</span></td>
            <td>{_e(a.label)}</td>
          </tr>"""
        for a in declined
    )

    declined_block = (
        f"""    <div class="tscroll">
      <table>
        <thead><tr><th>Catalog</th><th>Datasheet</th><th>Reason</th><th>Attribute</th></tr></thead>
        <tbody>
{declined_rows}
        </tbody>
      </table>
    </div>"""
        if declined
        else '    <p class="sec-note">Nothing declined in this run.</p>'
    )

    return f"""<title>Errata Catalog Audit</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@600&display=swap">
<style>{_CSS}</style>
<div class="wrap">
  <header class="masthead">
    <span class="eyebrow">Errata &middot; catalog audit</span>
    <h1>{_e(result.title)}</h1>
    <p class="sub">Every attribute below was re-derived independently from the catalog value and
    compared against the manufacturer&rsquo;s figure. Errata grades data; it never writes it.</p>
  </header>

  <div class="counts">
    <div class="count is-raised"><span class="n">{len(findings)}</span><span class="l">raised for review</span></div>
    <div class="count is-silent"><span class="n">{len(silent)}</span><span class="l">resolved silently</span></div>
    <div class="count is-declined"><span class="n">{len(declined)}</span><span class="l">declined &mdash; could not check</span></div>
    <div class="count"><span class="n">{len(result.every_attribute)}</span><span class="l">attributes checked</span></div>
  </div>

  <section>
    <div class="sec-head">
      <span class="eyebrow">Worst first</span>
      <h2>Reviewer queue</h2>
      <p class="sec-note">Ranked by severity. Each finding carries both values, the reason, and the
      standard it is grounded in &mdash; a reviewer should never have to take the verdict on trust.</p>
    </div>
    <div class="findings">
{findings_html}
    </div>
  </section>

  <section>
    <div class="sec-head">
      <span class="eyebrow">Deliberately not shown</span>
      <h2>Resolved silently</h2>
      <p class="sec-note">These were checked and found consistent. Flagging any of them would be
      worse than missing a real error: <strong>316&nbsp;SS</strong> against <strong>A4</strong> is
      one fact in two notations, and a tool that calls it a defect loses the reviewer in the first
      session. This section is the product working, not the product idling.</p>
    </div>
    <div class="tscroll">
      <table>
        <thead><tr><th>Catalog</th><th>Datasheet</th><th>Verdict</th><th>Attribute</th></tr></thead>
        <tbody>
{silent_rows}
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <div class="sec-head">
      <span class="eyebrow">Refused, not guessed</span>
      <h2>Declined</h2>
      <p class="sec-note">Where the comparison could not be made, Errata routes the pair with a
      reason instead of guessing. &ldquo;We checked and it is fine&rdquo; and &ldquo;we could not
      check&rdquo; are different statements, and the product refuses to blur them.</p>
    </div>
{declined_block}
  </section>

  <footer class="scope">
    <span class="eyebrow">Scope of this demonstration</span>
    <p>This shows the <strong>comparator</strong> &mdash; the part of Errata that decides whether two
    values disagree. That part is measured: R0 gate&nbsp;1 passes at a
    <strong>1.30% false-positive rate</strong> over 624 hand-labelled pairs.</p>
    <p><strong>It does not show evidence grounding.</strong> The full product must point at the box
    on the page a datasheet value came from (FR-1.2&ndash;1.5). That pipeline is not built. The
    datasheet values here were supplied, not located, and R0 gate&nbsp;2 remains
    <strong>NOT MEASURED</strong>.</p>
    <p>SKU identifiers are illustrative. Every <em>value pair</em> is loaded by case id from the
    hand-labelled equivalence suite, together with its citation, so this page cannot drift from the
    data the gate is measured against.</p>
  </footer>
</div>"""


def main(argv: list[str] | None = None) -> int:
    force_utf8_output()
    parser = argparse.ArgumentParser(
        prog="errata-demo",
        description="Run the Errata comparator over a demonstration catalog.",
    )
    parser.add_argument("--catalog", type=Path, default=None, help="path to a demo catalog YAML")
    parser.add_argument("--html", type=Path, default=None, help="write an HTML report to this path")
    args = parser.parse_args(argv)

    result = run_demo(args.catalog)
    if args.html is not None:
        args.html.write_text(render_html(result), encoding="utf-8")
        print(f"wrote {args.html}")
    else:
        print(render_text(result))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
