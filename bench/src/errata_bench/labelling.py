"""FR-0.1's independent dual-labelling: the packet, and the agreement arithmetic.

The gate reports 1.30% and cannot quote it outside this repository, for one reason that no amount
of code fixing addresses: **all 624 cases were labelled by the same author who wrote the comparator
being graded.** A suite written alongside the code it grades encodes the same blind spots twice,
and `HANDOFF.md` §10 has the demonstration -- the 175 seed cases score 100% while the 449
adversarial ones decline at roughly six times the rate and produced every bug found so far.

This module does the mechanical half of fixing that, which is the half software can do:

* :func:`build_packet` emits every case **stripped of its label, its rationale and its citation**,
  so a second labeller sees exactly what a reviewer sees -- two values and an attribute -- and
  cannot be anchored by the first labeller's reasoning or by the standard they leaned on.
* :func:`score_packet` reads a completed packet back and computes raw agreement and Cohen's
  kappa, per family and overall.

The judgment half is not automatable and is not attempted here. A packet filled in by anyone who
has read the suite's rationales is not an independent labelling, it is an echo.

**Why kappa and not raw agreement.** The label distribution is lopsided -- `equivalent` and
`contradiction` dominate -- so two labellers guessing the majority class would agree most of the
time while establishing nothing. Kappa prices that in. Read them together: high agreement with low
kappa means the suite is easy, not that the labelling is sound.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .equivalence import Case, Label, load_cases

__all__ = [
    "PACKET_FIELDS",
    "AgreementReport",
    "FamilyAgreement",
    "build_packet",
    "cohen_kappa",
    "score_packet",
    "write_packet",
]

#: Columns in the emitted packet. `label` and `note` are the labeller's to fill; everything else
#: is context they are allowed to see. Deliberately excludes `expect`, `expect_alternatives`,
#: `source` and `rationale` -- those are the first labeller's answers and their reasoning.
PACKET_FIELDS = ("case_id", "family", "attribute", "value_a", "value_b", "label", "note")

#: What a labeller may write in the `label` column, with the one-line gloss they get in the
#: instructions. Wording is taken from the suite's own definitions so the two labellers are
#: answering the same question.
LABEL_GLOSS: dict[Label, str] = {
    Label.EQUIVALENT: "the same value written two ways -- a reviewer should never see this record",
    Label.CONTRADICTION: "the two values cannot both be true of one product",
    Label.GRANULARITY: "one side is a less specific version of the other; under-specified, not wrong",
    Label.PRECISION: "same value, but one side has dropped a stated tolerance or precision",
    Label.AGREEMENT_SPECIFIC: "the evidence supports the catalog and adds detail the catalog omitted",
    Label.UNDETERMINED: "you genuinely cannot tell from these two strings alone",
    Label.NULL_GAP: "one side is blank and the other states a value",
}

INSTRUCTIONS = """\
INDEPENDENT DUAL-LABELLING PACKET -- Errata equivalence suite (FR-0.1)
=====================================================================

WHO SHOULD FILL THIS IN
  Someone who did NOT write the comparator and has NOT read the suite's rationales. If you have
  already read them, you are not an independent labeller for these cases -- please hand this on.

WHAT YOU ARE BEING ASKED
  For each row you get an attribute and two values: `value_a` from a product catalog, `value_b`
  from the manufacturer's datasheet. Say what the relationship between them is, as a competent
  domain reviewer would.

  You are NOT being asked what a piece of software should output. You are being asked what is
  true. Where those differ, the software is wrong -- that is the entire point of the exercise.

HOW TO FILL IT IN
  Put exactly one label in the `label` column. Use the `note` column freely, especially when you
  are unsure or when you think the question is badly posed -- a note saying "this depends on
  something not shown" is a useful result, not a failure to answer.

THE LABELS
{labels}

THE RULE THAT MATTERS MOST
  If you cannot tell from the two strings in front of you, write `undetermined`. Do not reason
  toward the answer you think is expected. An honest "you cannot tell" is the most valuable
  entry in this file, because the comparator's worst failure mode is answering confidently where
  the honest reply is that there is not enough information.

WHEN YOU ARE DONE
  Save the file and hand it back. Agreement is scored with:

      errata-r0 labelling score --packet <your-file.csv>
"""


@dataclass(frozen=True, slots=True)
class FamilyAgreement:
    family: str
    n: int
    agreed: int
    kappa: float

    @property
    def raw_agreement(self) -> float:
        return self.agreed / self.n if self.n else 0.0


@dataclass(frozen=True, slots=True)
class AgreementReport:
    """Inter-labeller agreement between the suite's labels and a returned packet."""

    n: int
    agreed: int
    kappa: float
    by_family: tuple[FamilyAgreement, ...]
    disagreements: tuple[tuple[str, Label, Label], ...]
    unlabelled: tuple[str, ...]

    @property
    def raw_agreement(self) -> float:
        return self.agreed / self.n if self.n else 0.0

    @property
    def caveats(self) -> list[str]:
        notes: list[str] = []
        if self.unlabelled:
            notes.append(
                f"{len(self.unlabelled)} case(s) came back without a label and are excluded from "
                "the arithmetic. A packet returned half-filled measures the labeller's stamina, "
                "not the suite."
            )
        if self.n and self.kappa < 0.6:
            notes.append(
                f"kappa is {self.kappa:.2f}. Below about 0.6 the two labellers are not describing "
                "the same phenomenon, and the disagreements are the finding -- reconcile them "
                "case by case before treating either labelling as ground truth."
            )
        if self.n and self.raw_agreement > 0.9 and self.kappa < 0.5:
            notes.append(
                "high raw agreement with low kappa: the label distribution is lopsided enough "
                "that agreeing this often is close to what chance would give. Do not read the "
                "agreement figure on its own."
            )
        return notes


def build_packet(cases: Sequence[Case] | None = None) -> list[dict[str, str]]:
    """Every case, stripped to what a reviewer would actually see.

    The stripping is the point. `expect`, `expect_alternatives`, `source` and `rationale` all
    encode the first labeller's answer or the reasoning that produced it, and a second labeller
    who sees any of them is confirming rather than labelling.
    """
    rows: list[dict[str, str]] = []
    for case in cases if cases is not None else load_cases():
        rows.append(
            {
                "case_id": case.id,
                "family": case.family,
                "attribute": getattr(case, "attribute_key", "") or "",
                "value_a": case.a,
                "value_b": case.b,
                "label": "",
                "note": "",
            }
        )
    return rows


def write_packet(destination: Path, cases: Sequence[Case] | None = None) -> Path:
    """Write the packet plus its instructions. Returns the CSV path."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    rows = build_packet(cases)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PACKET_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    gloss = "\n".join(f"  {label.value:20} {text}" for label, text in LABEL_GLOSS.items())
    destination.with_suffix(".README.txt").write_text(
        INSTRUCTIONS.format(labels=gloss), encoding="utf-8"
    )
    return destination


def cohen_kappa(pairs: Iterable[tuple[Label, Label]]) -> float:
    """Cohen's kappa for two labellers over the same items.

    Returns 0.0 when expected agreement is 1.0 -- every item in one category, where kappa is
    undefined. Reporting 0 there is the conservative reading: it says "this measured nothing",
    which is true.
    """
    pairs = list(pairs)
    if not pairs:
        return 0.0
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    first = Counter(a for a, _ in pairs)
    second = Counter(b for _, b in pairs)
    expected = sum((first[k] / n) * (second[k] / n) for k in set(first) | set(second))
    if expected >= 1.0:
        return 0.0
    return (observed - expected) / (1 - expected)


def score_packet(packet: Path, cases: Sequence[Case] | None = None) -> AgreementReport:
    """Compare a returned packet against the suite's own labels.

    Neither labelling is privileged. The suite's label is not "the answer" being marked -- if the
    independent labeller is right and the suite is wrong, that is a suite finding, and it is the
    more valuable of the two outcomes.
    """
    known = {c.id: c for c in (cases if cases is not None else load_cases())}

    pairs: list[tuple[Label, Label]] = []
    families: dict[str, list[tuple[Label, Label]]] = {}
    disagreements: list[tuple[str, Label, Label]] = []
    unlabelled: list[str] = []

    with Path(packet).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            case_id = (row.get("case_id") or "").strip()
            case = known.get(case_id)
            if case is None:
                raise KeyError(
                    f"packet row {case_id!r} does not match any case in the suite. The packet and "
                    "the suite have drifted apart; regenerate it rather than guessing."
                )
            raw = (row.get("label") or "").strip().lower()
            if not raw:
                unlabelled.append(case_id)
                continue
            try:
                theirs = Label(raw)
            except ValueError as exc:
                raise ValueError(
                    f"{case_id}: {raw!r} is not one of "
                    f"{', '.join(sorted(x.value for x in Label))}"
                ) from exc
            ours = case.expect
            pairs.append((ours, theirs))
            families.setdefault(case.family, []).append((ours, theirs))
            if ours != theirs:
                disagreements.append((case_id, ours, theirs))

    return AgreementReport(
        n=len(pairs),
        agreed=sum(1 for a, b in pairs if a == b),
        kappa=cohen_kappa(pairs),
        by_family=tuple(
            FamilyAgreement(
                family=family,
                n=len(items),
                agreed=sum(1 for a, b in items if a == b),
                kappa=cohen_kappa(items),
            )
            for family, items in sorted(families.items())
        ),
        disagreements=tuple(disagreements),
        unlabelled=tuple(unlabelled),
    )


def render_agreement(report: AgreementReport) -> str:
    """Human-readable agreement report."""
    lines = [
        "",
        "FR-0.1 INDEPENDENT DUAL-LABELLING -- AGREEMENT",
        "-" * 78,
        f"  cases scored        {report.n}",
        f"  raw agreement       {100 * report.raw_agreement:.2f}%  ({report.agreed}/{report.n})",
        f"  Cohen's kappa       {report.kappa:.3f}",
        "",
        "  by family",
    ]
    for family in report.by_family:
        lines.append(
            f"    {family.family:12} {100 * family.raw_agreement:6.2f}%  "
            f"({family.agreed}/{family.n})   kappa {family.kappa:.3f}"
        )
    if report.disagreements:
        lines += ["", f"  disagreements ({len(report.disagreements)}) -- each one is a finding"]
        for case_id, ours, theirs in report.disagreements:
            lines.append(f"    {case_id:12} suite={ours.value:20} independent={theirs.value}")
    if report.caveats:
        lines += ["", "  read this next to the numbers"]
        lines += [f"    - {c}" for c in report.caveats]
    lines.append("")
    return "\n".join(lines)


def report_as_dict(report: AgreementReport) -> dict[str, object]:
    return {
        "cases_scored": report.n,
        "raw_agreement": report.raw_agreement,
        "cohen_kappa": report.kappa,
        "by_family": [
            {
                "family": f.family,
                "n": f.n,
                "agreed": f.agreed,
                "raw_agreement": f.raw_agreement,
                "cohen_kappa": f.kappa,
            }
            for f in report.by_family
        ],
        "disagreements": [
            {"case_id": cid, "suite": ours.value, "independent": theirs.value}
            for cid, ours, theirs in report.disagreements
        ],
        "unlabelled": list(report.unlabelled),
        "caveats": report.caveats,
    }


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(build_packet()[:3], indent=2))
