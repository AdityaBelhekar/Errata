"""R0 kill test 1 -- the equivalence suite (FR-0.1, FR-0.2).

This is the first thing built and the first thing that can end the project. §13, test 1:

    Above ~5% false positives: stop.
    Above 2%: do not ship until it is under 2%.

The arithmetic behind the threshold, from §6.1: a sweep surfacing 40,000 redlines at a 15%
false-positive rate wastes 6,000 reviews, and at $20-$35/hour for specialised review even 40
seconds a decision spends thousands of the customer's dollars proving the tool is wrong -- inside
the pilot, in front of the person who approved it.

What counts as a false positive here is narrow and deliberate: a pair a competent domain reviewer
would call "no defect", on which the comparator raised a finding. Everything else the harness can
get wrong is reported too, under its own name, because collapsing four different failures into one
percentage is how a gate stops meaning anything:

    FALSE_POSITIVE          accused where there is nothing to accuse   -- the gate
    FALSE_NEGATIVE          missed a genuine defect                    -- costs one bad record
    MISCLASSIFIED           found it, called it the wrong thing        -- tone and severity
    UNEXPECTED_ABSTENTION   declined where an answer was available     -- coverage loss
    OVER_RESOLVED           answered where the honest reply is 'unknown'
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from errata_comparator import AttributeSpec, Comparison, compare_attribute
from errata_spec import DisagreementClass
from errata_spec.taxonomy import CLASS_PROFILE
from errata_valuesem import Kind

from .stats import Proportion, wilson

__all__ = [
    "LABEL_CLASSES",
    "Case",
    "CaseResult",
    "Gate",
    "Label",
    "Outcome",
    "SuiteReport",
    "load_cases",
    "run_suite",
]

SUITE_VERSION = "equivalence/0.1.0"

#: FR-0.1 asks for 500 equivalence pairs and 500 genuine contradictions. The seed suite is smaller
#: and the harness says so out loud in every report, because a 2% gate measured on 60 cases has a
#: confidence interval wide enough to drive a truck through.
TARGET_EQUIVALENT_PAIRS = 500
TARGET_CONTRADICTION_PAIRS = 500


class Label(str, enum.Enum):
    """What a competent domain reviewer would call the pair.

    The label is the ground truth. When the label and the code disagree, the code is wrong -- and
    when the label itself is arguable, the case carries ``expect_alternatives`` rather than being
    quietly resolved in the direction that makes the numbers look better.
    """

    EQUIVALENT = "equivalent"
    CONTRADICTION = "contradiction"
    GRANULARITY = "granularity"
    PRECISION = "precision"
    AGREEMENT_SPECIFIC = "agreement_specific"
    UNDETERMINED = "undetermined"

    NULL_GAP = "null_gap"
    """One side is blank and the other states a value -- a real finding, not a disagreement.

    Added after the adversarial pass surfaced a genuine hole in this vocabulary rather than in the
    comparator. §3.3 defines `catalog_null_evidence_present` ("the fill-rate finding") and
    `unsupported_value` ("undefendable") as findings the product exists to raise, but no suite
    label mapped to either, so `N/A` against `Yes` had to be filed under `undetermined` -- and the
    comparator was then marked over-resolved for doing exactly the right thing.

    The case author saw this and wrote it down: they predicted CATALOG_NULL_EVIDENCE_PRESENT and
    called it "a real, SEV2 finding", then labelled `undetermined` because nothing better existed.
    That is a missing category, and the fix is to add it rather than to relabel the case into
    something false or to soften the comparator.

    Note that null-ness is a property of the VALUES, not of the attribute: `-`, `n/a`, `TBD` and a
    blank are all nullish (see errata_valuesem.canonical.NULLISH), so which side is null decides
    which of the two classes applies. Both are accepted here because both are the same finding seen
    from opposite sides.
    """


LABEL_CLASSES: dict[Label, frozenset[DisagreementClass]] = {
    Label.EQUIVALENT: frozenset(
        {
            DisagreementClass.AGREEMENT,
            DisagreementClass.SEMANTIC_EQUIVALENCE,
            DisagreementClass.UNIT_FRAME_MISMATCH,
        }
    ),
    Label.CONTRADICTION: frozenset(
        {DisagreementClass.CONTRADICTION, DisagreementClass.PACKAGING_FRAME_ERROR}
    ),
    Label.GRANULARITY: frozenset({DisagreementClass.GRANULARITY_MISMATCH}),
    Label.PRECISION: frozenset({DisagreementClass.PRECISION_MISMATCH}),
    Label.AGREEMENT_SPECIFIC: frozenset(
        {
            DisagreementClass.AGREEMENT,
            DisagreementClass.SEMANTIC_EQUIVALENCE,
            DisagreementClass.UNIT_FRAME_MISMATCH,
        }
    ),
    Label.UNDETERMINED: frozenset({DisagreementClass.UNDETERMINED}),
    Label.NULL_GAP: frozenset(
        {
            DisagreementClass.CATALOG_NULL_EVIDENCE_PRESENT,
            DisagreementClass.UNSUPPORTED_VALUE,
        }
    ),
}

_ACCUSATORY = frozenset(
    {DisagreementClass.CONTRADICTION, DisagreementClass.PACKAGING_FRAME_ERROR}
)


class Outcome(str, enum.Enum):
    PASS = "pass"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    MISCLASSIFIED = "misclassified"
    UNEXPECTED_ABSTENTION = "unexpected_abstention"
    OVER_RESOLVED = "over_resolved"


class Gate(str, enum.Enum):
    """The R0 decision. These are not severity levels, they are instructions."""

    PASS = "PASS"
    """Under 2%. Proceed to R1."""

    HOLD = "HOLD"
    """Between 2% and 5%. Do not ship. Keep working on the comparator."""

    STOP = "STOP"
    """Above 5%. §13: the correct decision is to stop the project."""

    INCONCLUSIVE = "INCONCLUSIVE"
    """The suite is too small, or nothing was flagged, for the number to mean anything."""


PASS_THRESHOLD = 0.02
STOP_THRESHOLD = 0.05

#: Below this many flagged records the point estimate is noise. Reporting a gate verdict off three
#: flagged cases would be exactly the kind of confident-but-meaningless number this product exists
#: to find in other people's data.
MIN_FLAGGED_FOR_VERDICT = 30


@dataclass(frozen=True, slots=True)
class Case:
    """One hand-labelled pair."""

    id: str
    family: str
    attribute: AttributeSpec
    a: str
    b: str
    expect: Label
    expect_alternatives: tuple[Label, ...] = ()
    source: str = ""
    rationale: str = ""
    origin: str = ""

    @property
    def labels(self) -> tuple[Label, ...]:
        return (self.expect, *self.expect_alternatives)

    @property
    def accepted(self) -> frozenset[DisagreementClass]:
        accepted: set[DisagreementClass] = set()
        for label in self.labels:
            accepted |= LABEL_CLASSES[label]
        return frozenset(accepted)

    @property
    def is_dual_labelled(self) -> bool:
        return bool(self.expect_alternatives)

    @property
    def reviewer_says_no_defect(self) -> bool:
        """True when every accepted reading raises no finding.

        These are the cases the false-positive gate is measured against.
        """
        return not any(CLASS_PROFILE[c].raises_finding for c in self.accepted)

    @property
    def reviewer_says_defect(self) -> bool:
        return all(CLASS_PROFILE[c].raises_finding for c in self.accepted)


@dataclass(frozen=True, slots=True)
class CaseResult:
    case: Case
    comparison: Comparison
    outcome: Outcome
    accusatory: bool = False
    """Set when the comparator called a soft finding a contradiction. Not counted in the gate, but
    a reviewer experiences it as a false accusation, so it is reported next to one."""

    @property
    def actual(self) -> DisagreementClass:
        return self.comparison.disagreement_class

    def describe(self) -> str:
        expected = "/".join(label.value for label in self.case.labels)
        return (
            f"{self.case.id:10} {self.case.a!r} vs {self.case.b!r}\n"
            f"           expected {expected} -> got {self.actual.value}\n"
            f"           {self.comparison.rationale}"
        )


@dataclass(slots=True)
class SuiteReport:
    """Everything the R0 gate needs, and the caveats that keep it honest."""

    results: list[CaseResult] = field(default_factory=list)
    suite_version: str = SUITE_VERSION

    # -- populations -------------------------------------------------------------------------
    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def flagged(self) -> list[CaseResult]:
        return [r for r in self.results if CLASS_PROFILE[r.actual].raises_finding]

    @property
    def clean_cases(self) -> list[CaseResult]:
        return [r for r in self.results if r.case.reviewer_says_no_defect]

    @property
    def defect_cases(self) -> list[CaseResult]:
        return [r for r in self.results if r.case.reviewer_says_defect]

    def by_outcome(self, outcome: Outcome) -> list[CaseResult]:
        return [r for r in self.results if r.outcome is outcome]

    # -- headline metrics ---------------------------------------------------------------------
    @property
    def fp_on_flagged(self) -> Proportion:
        """The §6.1 gate: false positives *measured on flagged records*.

        This is the number a reviewer experiences -- of everything the tool put in front of me,
        what fraction was not a defect.
        """
        return wilson(len(self.by_outcome(Outcome.FALSE_POSITIVE)), len(self.flagged))

    @property
    def fp_on_clean(self) -> Proportion:
        """How often a genuinely-equivalent pair gets accused. The suite-side view."""
        return wilson(len(self.by_outcome(Outcome.FALSE_POSITIVE)), len(self.clean_cases))

    @property
    def fn_on_defects(self) -> Proportion:
        return wilson(len(self.by_outcome(Outcome.FALSE_NEGATIVE)), len(self.defect_cases))

    @property
    def accusatory_rate(self) -> Proportion:
        return wilson(sum(1 for r in self.results if r.accusatory), len(self.flagged))

    # -- honest-accounting metrics ----------------------------------------------------------------
    #
    # Each of the three below exists because a headline number was routing around the very buckets
    # the harness built to stay honest. They are reported alongside the gate metric, never instead
    # of it, so the narrow §6.1 definition stays intact and comparable across runs.

    @property
    def over_resolved_findings(self) -> list[CaseResult]:
        """Over-resolutions that RAISED a finding -- the reviewer saw these.

        An `undetermined` label means a competent reviewer would say the two values cannot be
        compared. When the comparator answers anyway *and raises a finding*, a human opens a
        redline for a question that has no answer. That costs the same reviewer-seconds as a false
        positive and buys the same nothing.
        """
        return [
            r
            for r in self.by_outcome(Outcome.OVER_RESOLVED)
            if CLASS_PROFILE[r.actual].raises_finding
        ]

    @property
    def fp_reviewer_experienced(self) -> Proportion:
        """False positives as the REVIEWER experiences them, over everything flagged.

        `fp_on_flagged` claims in its own docstring to be "the number a reviewer experiences", and
        it is not: `_score` reaches the OVER_RESOLVED branch before the false-positive check, so a
        finding raised on an `undetermined` pair is excluded from the numerator **while remaining
        in the denominator** -- the rate is improved at both ends by the same case.

        The reviewer cannot see the label. They see a redline. This metric counts every redline
        that should not have been raised, which is what §6.1's cost model actually prices.
        """
        numerator = len(self.by_outcome(Outcome.FALSE_POSITIVE)) + len(self.over_resolved_findings)
        return wilson(numerator, len(self.flagged))

    @property
    def cases_in_neither_denominator(self) -> list[CaseResult]:
        """Finding 18. Cases whose labels straddle defect and no-defect.

        ``reviewer_says_no_defect`` requires EVERY accepted reading to raise nothing;
        ``reviewer_says_defect`` requires every one to raise something. A case labelled
        ``equivalent`` *and* ``contradiction`` satisfies neither, so it is silently absent from
        both `fp_on_clean` and `fn_on_defects`.

        The gate metric is unaffected -- its denominator is `flagged`, which includes these. But
        the two supporting rates are quoted next to the case count, and a reader who adds their
        denominators together and gets less than the suite size deserves to be told why rather
        than left to wonder whether something was dropped to flatter a number.
        """
        return [
            r
            for r in self.results
            if not r.case.reviewer_says_no_defect and not r.case.reviewer_says_defect
        ]

    @property
    def contested_findings(self) -> list[CaseResult]:
        """Findings raised on a dual-labelled case whose OTHER reading says raise nothing.

        Finding 17. ``accepted`` unions the classes of every label, so a case carrying both
        ``equivalent`` and ``contradiction`` scores PASS whichever way the comparator answers.
        That is defensible when the alternatives are adjacent readings -- ``granularity`` against
        ``undetermined``, say, where a reviewer might reasonably go either way and the reviewer's
        *experience* is similar either way.

        It is not defensible when the two readings straddle "raise nothing" and "raise a finding",
        because those have opposite consequences for the person reading the queue. A SEV-1
        packaging-frame error means somebody re-prices a line; ``equivalent`` means nobody should
        ever have seen the record. A label that accepts both makes the case unfalsifiable at
        exactly the severity the gate exists to police.

        This does not decide which reading is right -- that is a domain judgment and FR-0.1 wants
        an independent labeller to make it. It measures how much of the headline number is
        resting on the ambiguity.
        """
        return [
            r
            for r in self.results
            if r.case.is_dual_labelled
            and CLASS_PROFILE[r.actual].raises_finding
            and any(not CLASS_PROFILE[c].raises_finding for c in r.case.accepted)
        ]

    @property
    def fp_adversarial(self) -> Proportion:
        """The gate metric with every contested finding resolved AGAINST the comparator.

        The sensitivity band on `fp_reviewer_experienced`. If the gate passes here too, the
        dual-labelling is not load-bearing and finding 17 is cosmetic. If it does not, then the
        headline number depends on a judgment call that the same author who wrote the comparator
        also made -- which is precisely the thing FR-0.1's independent dual-labelling exists to
        settle, and the gate should say so out loud rather than bank the favourable reading.

        Reported alongside the gate metric, never instead of it. The gate still judges on
        `fp_reviewer_experienced` (ground rule 8); this is the honesty check on that verdict.
        """
        numerator = (
            len(self.by_outcome(Outcome.FALSE_POSITIVE))
            + len(self.over_resolved_findings)
            + len(self.contested_findings)
        )
        return wilson(numerator, len(self.flagged))

    @property
    def declined_defects(self) -> list[CaseResult]:
        """Genuine defects the comparator declined to answer.

        A declined contradiction satisfies this harness's own false-negative definition -- it did
        not raise a finding on a pair a reviewer calls a defect. The abstention branch in `_score`
        simply reaches it first, so the miss is booked as coverage loss instead of as a miss.
        """
        return [
            r
            for r in self.results
            if r.case.reviewer_says_defect and r.actual is DisagreementClass.UNDETERMINED
        ]

    @property
    def miss_rate_including_declines(self) -> Proportion:
        """Every defect not surfaced, however it failed to surface.

        `fn_on_defects` counts only defects answered *wrongly*. Adding the ones declined outright
        is the honest miss rate: a defect the customer never saw is missed whether the tool said
        the wrong thing or said nothing.
        """
        numerator = len(self.by_outcome(Outcome.FALSE_NEGATIVE)) + len(self.declined_defects)
        return wilson(numerator, len(self.defect_cases))

    @property
    def coverage(self) -> Proportion:
        answered = sum(1 for r in self.results if r.actual is not DisagreementClass.UNDETERMINED)
        return wilson(answered, self.total)

    @property
    def pass_rate(self) -> Proportion:
        return wilson(len(self.by_outcome(Outcome.PASS)), self.total)

    # -- the verdict ---------------------------------------------------------------------------
    @property
    def gate(self) -> Gate:
        """The R0 decision, judged on the REVIEWER-EXPERIENCED false-positive rate.

        This used to read ``fp_on_flagged``, and the change is a correctness fix rather than a
        redefinition: that metric's own docstring claims to be "the number a reviewer experiences
        -- of everything the tool put in front of me, what fraction was not a defect", and it
        demonstrably was not. Findings raised on `undetermined` pairs were excluded from its
        numerator by branch order while staying in its denominator, so a single bad redline
        improved the rate at both ends. On the current suite the two differ by 4.7x (1.33% against
        6.22%) and they straddle the stop threshold, so the choice decides the verdict.

        §6.1 prices this gate against reviewer-seconds spent on redlines that should not exist. A
        reviewer cannot see the suite's label; they see a redline and lose trust when it is wrong.
        Whether the ground truth was "these agree" or "you cannot tell from this" changes nothing
        about that experience, so both belong in the numerator.

        ``fp_on_flagged`` is still computed and still reported, so runs stay comparable and the
        narrow §6.1 reading remains visible next to this one.
        """
        flagged = len(self.flagged)
        if flagged < MIN_FLAGGED_FOR_VERDICT:
            return Gate.INCONCLUSIVE
        rate = self.fp_reviewer_experienced.point
        if rate > STOP_THRESHOLD:
            return Gate.STOP
        if rate >= PASS_THRESHOLD:
            return Gate.HOLD
        return Gate.PASS

    @property
    def caveats(self) -> list[str]:
        """What this number does not yet establish. Printed with every report."""
        notes: list[str] = []
        equivalent_pairs = sum(1 for r in self.results if r.case.reviewer_says_no_defect)
        contradiction_pairs = sum(
            1 for r in self.results if Label.CONTRADICTION in r.case.labels
        )
        if equivalent_pairs < TARGET_EQUIVALENT_PAIRS:
            notes.append(
                f"FR-0.1 asks for {TARGET_EQUIVALENT_PAIRS} equivalence pairs; the suite has "
                f"{equivalent_pairs}. The interval below is the honest width of that shortfall."
            )
        if contradiction_pairs < TARGET_CONTRADICTION_PAIRS:
            notes.append(
                f"FR-0.1 asks for {TARGET_CONTRADICTION_PAIRS} genuine contradictions; the suite "
                f"has {contradiction_pairs}."
            )
        if len(self.flagged) < MIN_FLAGGED_FOR_VERDICT:
            notes.append(
                f"only {len(self.flagged)} records were flagged; below {MIN_FLAGGED_FOR_VERDICT} "
                "the point estimate is noise and no gate verdict is issued."
            )
        elif self.fp_on_flagged.hi > STOP_THRESHOLD >= self.fp_on_flagged.point:
            notes.append(
                f"the upper bound of the false-positive interval ({100 * self.fp_on_flagged.hi:.1f}%) "
                f"crosses the {100 * STOP_THRESHOLD:.0f}% stop threshold. The point estimate passes "
                "and the sample does not yet exclude a failing rate."
            )
        dual = sum(1 for r in self.results if r.case.is_dual_labelled)
        if dual:
            contested = len(self.contested_findings)
            note = (
                f"{dual} cases are dual-labelled: a second reading was accepted as defensible. "
                f"{contested} of them carry a finding the second reading says should not have "
                "been raised, so those score PASS whichever way the comparator answers."
            )
            if contested:
                note += (
                    f" Resolved against the comparator the rate is "
                    f"{100 * self.fp_adversarial.point:.2f}%, against the gate's "
                    f"{100 * self.fp_reviewer_experienced.point:.2f}%"
                )
                if self.fp_adversarial.point > PASS_THRESHOLD:
                    note += (
                        f" -- which is above the {100 * PASS_THRESHOLD:.0f}% pass threshold. "
                        "The PASS is real but conditional on those judgment calls, and they were "
                        "made by the same author who wrote the comparator. This is what FR-0.1's "
                        "independent dual-labelling is for."
                    )
                else:
                    note += ", which still passes."
            notes.append(note)
        unclassifiable = len(self.cases_in_neither_denominator)
        if unclassifiable:
            notes.append(
                f"{unclassifiable} cases sit in NEITHER supporting denominator: their labels "
                "straddle defect and no-defect, so `reviewer_says_no_defect` and "
                "`reviewer_says_defect` are both false and the case drops out of the "
                f"false-positive and missed-defect rates alike. The arithmetic reconciles -- "
                f"{self.fp_on_clean.total} no-defect + {self.fn_on_defects.total} defect + "
                f"{unclassifiable} straddling = {self.total} -- but a reader comparing those two "
                "denominators to the case count should know why they do not sum to it."
            )
        if self.total and len(self.by_outcome(Outcome.PASS)) == self.total:
            notes.append(
                "the comparator passes every case. That is weak evidence, not strong: a suite "
                "written alongside the code it grades will encode the same blind spots twice. The "
                "suite is only doing its job once it contains cases the comparator fails."
            )
        notes.append(
            "every case in this suite was labelled by the same author who wrote the comparator. "
            "FR-0.1 requires independent dual-labelling before the number is quotable outside "
            "this repository."
        )
        return notes


# ------------------------------------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------------------------------------


def _attribute_from(spec: dict[str, Any] | None) -> AttributeSpec:
    spec = spec or {}
    kinds = tuple(Kind(k) for k in spec.get("kinds", ()))
    return AttributeSpec(
        key=spec.get("key", "unspecified_attribute"),
        label=spec.get("label", ""),
        kinds=kinds,
        vocabulary=spec.get("vocabulary", ""),
        decimal_separator=spec.get("decimal_separator"),
    )


def _merge_attribute(default: dict[str, Any], override: dict[str, Any] | None) -> AttributeSpec:
    merged = dict(default)
    merged.update(override or {})
    return _attribute_from(merged)


def load_cases(directory: Path | None = None) -> list[Case]:
    """Load every case in the equivalence suite.

    Reads the packaged suite by default so ``errata-r0 equivalence`` works from a clean install;
    pass a directory to run a customer's own labelled set.
    """
    documents: list[tuple[str, dict[str, Any]]] = []
    if directory is None:
        root = resources.files("errata_bench").joinpath("suites/equivalence")
        for entry in sorted(root.iterdir(), key=lambda p: p.name):
            if entry.name.endswith(".yaml"):
                documents.append((entry.name, yaml.safe_load(entry.read_text("utf-8")) or {}))
    else:
        for path in sorted(Path(directory).glob("*.yaml")):
            documents.append((path.name, yaml.safe_load(path.read_text("utf-8")) or {}))

    cases: list[Case] = []
    seen: set[str] = set()
    for filename, document in documents:
        family = document.get("family", Path(filename).stem)
        defaults = (document.get("defaults") or {}).get("attribute", {})
        for raw in document.get("cases", []):
            case_id = raw["id"]
            if case_id in seen:
                raise ValueError(f"duplicate case id {case_id!r} in {filename}")
            seen.add(case_id)
            cases.append(
                Case(
                    id=case_id,
                    family=raw.get("family", family),
                    attribute=_merge_attribute(defaults, raw.get("attribute")),
                    a=str(raw["a"]),
                    b=str(raw["b"]),
                    expect=Label(raw["expect"]),
                    expect_alternatives=tuple(
                        Label(x) for x in raw.get("expect_alternatives", ())
                    ),
                    source=str(raw.get("source", "")).strip(),
                    rationale=" ".join(str(raw.get("rationale", "")).split()),
                    origin=filename,
                )
            )

    missing_source = [c.id for c in cases if not c.source]
    if missing_source:
        raise ValueError(
            "every case must carry a source -- an equivalence without a citation is an opinion. "
            f"Missing: {', '.join(missing_source)}"
        )
    return cases


# ------------------------------------------------------------------------------------------------
# Running
# ------------------------------------------------------------------------------------------------


def _score(case: Case, comparison: Comparison) -> tuple[Outcome, bool]:
    actual = comparison.disagreement_class
    accepted = case.accepted
    actual_raises = CLASS_PROFILE[actual].raises_finding

    # `accusatory` answers one question and it is deliberately independent of which outcome bucket
    # the case lands in: **would a reviewer open this and experience a false accusation?**
    #
    # It used to be computed only on the MISCLASSIFIED branch, which meant it fired 0 times across
    # the whole suite -- the one instrument built to capture reviewer experience was dead code,
    # while 8 SEV-1 accusations sat in the OVER_RESOLVED bucket unmeasured. An accusation raised on
    # a pair whose ground truth is "you cannot tell" is still an accusation; the reviewer does not
    # know the label, they only see the redline.
    accusatory = actual in _ACCUSATORY and actual not in accepted

    if actual in accepted:
        return Outcome.PASS, False
    if actual is DisagreementClass.UNDETERMINED:
        return Outcome.UNEXPECTED_ABSTENTION, accusatory
    if DisagreementClass.UNDETERMINED in accepted:
        return Outcome.OVER_RESOLVED, accusatory
    if actual_raises and case.reviewer_says_no_defect:
        return Outcome.FALSE_POSITIVE, accusatory
    if not actual_raises and case.reviewer_says_defect:
        return Outcome.FALSE_NEGATIVE, accusatory
    return Outcome.MISCLASSIFIED, accusatory


def run_suite(cases: Iterable[Case] | None = None) -> SuiteReport:
    """Run the suite and score it."""
    report = SuiteReport()
    for case in cases if cases is not None else load_cases():
        comparison = compare_attribute(case.attribute, case.a, case.b)
        outcome, accusatory = _score(case, comparison)
        report.results.append(
            CaseResult(
                case=case, comparison=comparison, outcome=outcome, accusatory=accusatory
            )
        )
    return report


def failures(report: SuiteReport) -> Iterator[CaseResult]:
    for result in report.results:
        if result.outcome is not Outcome.PASS:
            yield result
