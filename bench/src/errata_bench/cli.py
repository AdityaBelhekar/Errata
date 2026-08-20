"""``errata-r0`` -- the three kill tests, in build order.

§13 is explicit that these come before the console, the connectors, the benchmark and every
component in the spec, and that any one of them can end the project inside a fortnight. So the
command that runs them exists before the product does, and it exits non-zero when the answer is
"stop".

    errata-r0 equivalence      FR-0.1 / FR-0.2   implemented
    errata-r0 operating-point  FR-0.3            implemented -- NOT_MEASURED without --corpus
    errata-r0 coverage         FR-0.4            implemented -- NOT_MEASURED without --distribution
    errata-r0 status           what has a number and what does not

Kill tests 2 and 3 run against a synthetic stand-in when no real data is supplied, and their gate
is pinned to NOT_MEASURED / NOT_RUN unconditionally in that mode -- never a placeholder figure.
§0.3's whole argument is that a spec whose governing rule is "never invent numbers" does not get
credit for declining to invent one while proceeding as though it existed. The day a real MCB corpus
(FR-0.3) or a real ETIM class distribution (FR-0.4) exists, `--corpus` / `--distribution` makes the
number live with no other code change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import coverage as _coverage_module
from . import operating_point as _operating_point_module
from .console import force_utf8_output
from .equivalence import PASS_THRESHOLD, Gate, Outcome, SuiteReport, load_cases, run_suite

EXIT_PASS = 0
EXIT_HOLD = 1
EXIT_STOP = 2
EXIT_INCONCLUSIVE = 3
EXIT_NOT_IMPLEMENTED = 4

_RULE = "-" * 78


def main(argv: list[str] | None = None) -> int:
    force_utf8_output()
    parser = argparse.ArgumentParser(
        prog="errata-r0",
        description="R0 kill tests. Exit code is the decision, not a diagnostic.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    equivalence = sub.add_parser(
        "equivalence", help="FR-0.1/0.2 -- false-positive rate on the equivalence suite"
    )
    equivalence.add_argument("--suite", type=Path, default=None, help="directory of suite YAML")
    equivalence.add_argument("--json", action="store_true", help="machine-readable report")
    equivalence.add_argument(
        "--show", choices=["failures", "all", "none"], default="failures",
        help="which cases to print individually",
    )
    equivalence.add_argument(
        "--family", default="", help="restrict to one family (materials, threads, units, ...)"
    )

    operating_point = sub.add_parser(
        "operating-point", help="FR-0.3 -- audit-vs-extraction asymmetry"
    )
    operating_point.add_argument(
        "--corpus", type=Path, default=None,
        help="CSV/TSV/YAML/JSON of hand-labelled MCB records (see operating_point.load_corpus); "
             "omit to run against the synthetic stand-in, which is always NOT_MEASURED",
    )
    operating_point.add_argument("--json", action="store_true", help="machine-readable report")

    coverage = sub.add_parser("coverage", help="FR-0.4 -- calibration-coverage arithmetic")
    coverage.add_argument(
        "--distribution", type=Path, default=None,
        help="CSV/YAML of a real ETIM class distribution (see coverage.load_distribution); omit "
             "to run against the synthetic stand-in, which is always NOT_MEASURED",
    )
    coverage.add_argument("--json", action="store_true", help="machine-readable report")
    coverage.add_argument(
        "--sensitivity",
        action="store_true",
        help=(
            "sweep the one assumption a synthetic distribution makes -- how concentrated the "
            "catalog is -- and report whether gate 3's finding depends on it. Answers 'how much "
            "does the missing histogram matter', which IS answerable, instead of answering "
            "'what is the histogram', which is not"
        ),
    )

    labelling = sub.add_parser(
        "labelling",
        help="FR-0.1 -- emit an independent dual-labelling packet, or score a returned one",
    )
    labelling_sub = labelling.add_subparsers(dest="labelling_command", required=True)
    emit = labelling_sub.add_parser("packet", help="write a blind labelling packet")
    emit.add_argument("--out", type=Path, required=True, help="destination CSV path")
    emit.add_argument("--family", default="", help="restrict to one family")
    score = labelling_sub.add_parser("score", help="score a returned packet against the suite")
    score.add_argument("--packet", type=Path, required=True, help="the completed CSV")
    score.add_argument("--json", action="store_true", help="machine-readable report")

    corroborate = sub.add_parser(
        "corroborate",
        help="FR-0.1 -- check suite labels against an external, human-curated standard",
    )
    corroborate.add_argument("--json", action="store_true", help="machine-readable report")

    sub.add_parser("status", help="which R0 gates have numbers")

    args = parser.parse_args(argv)

    if args.command == "equivalence":
        return _equivalence(args)
    if args.command == "operating-point":
        return _run_operating_point(args)
    if args.command == "coverage":
        if getattr(args, "sensitivity", False):
            print(_coverage_module.sensitivity().text())
            # Always 3 (inconclusive). A sensitivity sweep is not a verdict, and returning 0
            # would let a CI job record gate 3 as passed by a command that measured nothing.
            return EXIT_INCONCLUSIVE
        return _run_coverage(args)
    if args.command == "labelling":
        return _run_labelling(args)
    if args.command == "corroborate":
        return _run_corroborate(args)
    return _status()


# ------------------------------------------------------------------------------------------------


def _equivalence(args: argparse.Namespace) -> int:
    cases = load_cases(args.suite)
    if args.family:
        cases = [c for c in cases if c.family == args.family]
        if not cases:
            print(f"no cases in family {args.family!r}", file=sys.stderr)
            return EXIT_INCONCLUSIVE

    report = run_suite(cases)

    if args.json:
        print(json.dumps(_as_dict(report), indent=2))
    else:
        _print_report(report, show=args.show)

    return {
        Gate.PASS: EXIT_PASS,
        Gate.HOLD: EXIT_HOLD,
        Gate.STOP: EXIT_STOP,
        Gate.INCONCLUSIVE: EXIT_INCONCLUSIVE,
    }[report.gate]


def _run_corroborate(args: argparse.Namespace) -> int:
    """Independent corroboration against an external standard.

    Exit 0 when every externally judgeable label is corroborated, 1 when any is contradicted. A
    disagreement is a finding that wants a human, not a gate failure -- hence HOLD rather than
    STOP.
    """
    from . import corroborate as _corroborate
    from .ucum import UcumNotAvailable

    try:
        report = _corroborate.corroborate()
    except UcumNotAvailable as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INCONCLUSIVE

    if args.json:
        print(
            json.dumps(
                {
                    "source": report.source,
                    "cases_examined": len(report.results),
                    "externally_judged": len(report.scoreable),
                    "coverage": report.coverage,
                    "agreement_rate": report.agreement_rate,
                    "disagreements": [
                        {
                            "case_id": r.case_id,
                            "a": r.a,
                            "b": r.b,
                            "suite_label": r.suite_label.value,
                            "external_verdict": r.verdict.value,
                            "detail": r.detail,
                        }
                        for r in report.disagreements
                    ],
                },
                indent=2,
            )
        )
    else:
        print(_corroborate.render_corroboration(report))
    return EXIT_HOLD if report.disagreements else EXIT_PASS


def _run_labelling(args: argparse.Namespace) -> int:
    """FR-0.1's independent dual-labelling. Exit 0 for both subcommands -- this is a tool for
    producing evidence, not a gate, and it has no verdict to issue."""
    from . import labelling as _labelling

    if args.labelling_command == "packet":
        cases = load_cases()
        if args.family:
            cases = [c for c in cases if c.family == args.family]
            if not cases:
                print(f"no cases in family {args.family!r}", file=sys.stderr)
                return EXIT_INCONCLUSIVE
        path = _labelling.write_packet(args.out, cases)
        print(f"wrote {path}  ({len(cases)} cases, labels stripped)")
        print(f"wrote {path.with_suffix('.README.txt')}  (instructions for the labeller)")
        print()
        print("Hand BOTH files to someone who did not write the comparator and has not read the")
        print("suite rationales. A packet filled in by anyone who has is not an independent")
        print("labelling, it is an echo -- and FR-0.1 is not satisfied by an echo.")
        return EXIT_PASS

    report = _labelling.score_packet(args.packet)
    if args.json:
        print(json.dumps(_labelling.report_as_dict(report), indent=2))
    else:
        print(_labelling.render_agreement(report))
    return EXIT_PASS


def _print_report(report: SuiteReport, *, show: str) -> None:
    print()
    print("R0 KILL TEST 1 -- EQUIVALENCE SUITE")
    print(f"{report.suite_version}   {report.total} cases")
    print(_RULE)

    print("\nOutcomes")
    for outcome in Outcome:
        count = len(report.by_outcome(outcome))
        if count or outcome is Outcome.PASS:
            print(f"  {outcome.value:24} {count:4}")

    print("\nGate metric (FR-0.2, measured on flagged records)")
    print(f"  false-positive rate    {report.fp_reviewer_experienced.render()}")
    print("    threshold            < 2.00% pass   > 5.00% stop")
    print(
        "    every redline that should not have been raised: false positives PLUS findings on\n"
        "    pairs whose ground truth is 'you cannot tell'. A reviewer cannot see the label."
    )

    print("\nThe same rate under the narrow reading, for comparability")
    print(f"  FP excluding over-resolutions  {report.fp_on_flagged.render()}")
    print(
        f"    the gap is {len(report.over_resolved_findings)} finding(s) raised on undetermined "
        "pairs, which the narrow\n    reading drops from the numerator while keeping in the "
        "denominator"
    )

    contested = report.contested_findings
    if contested:
        print("\nSensitivity to the dual-labelled cases -- READ THIS NEXT TO THE GATE METRIC")
        print(f"  FP under the adversarial reading  {report.fp_adversarial.render()}")
        print(
            f"    {len(contested)} finding(s) sit on cases carrying a second label that says raise\n"
            "    nothing. `accepted` unions both labels, so these score PASS whichever way the\n"
            "    comparator answers. This line resolves every one of them AGAINST the comparator."
        )
        for r in sorted(contested, key=lambda r: r.case.id):
            alts = "+".join(label.value for label in r.case.labels)
            print(f"      {r.case.id:10} {r.case.a!r} vs {r.case.b!r}  [{alts}] -> {r.actual.value}")
        if report.fp_adversarial.point > PASS_THRESHOLD:
            print(
                f"    ** The gate PASSES at {100 * report.fp_reviewer_experienced.point:.2f}% and "
                f"would NOT at {100 * report.fp_adversarial.point:.2f}%.\n"
                "       The headline number rests on judgment calls made by the same author who\n"
                "       wrote the comparator. FR-0.1's independent dual-labelling is what settles\n"
                "       this; until then the PASS is real but conditional, and should be quoted\n"
                "       with this band attached."
            )

    print("\nSupporting metrics")
    print(f"  FP over no-defect pairs {report.fp_on_clean.render()}")
    print(f"  missed defects (answered wrong)  {report.fn_on_defects.render()}")
    print(f"  missed defects (incl. declined)  {report.miss_rate_including_declines.render()}")
    print(
        f"    {len(report.declined_defects)} defect(s) were declined outright -- a defect the "
        "customer never saw is\n    missed whether the tool said the wrong thing or said nothing"
    )
    straddling = len(report.cases_in_neither_denominator)
    if straddling:
        print(
            f"    denominators reconcile: {report.fp_on_clean.total} no-defect + "
            f"{report.fn_on_defects.total} defect + {straddling} straddling = {report.total}"
        )
    print(f"  accusations on non-defects  {report.accusatory_rate.render_short()}")
    print(f"  coverage (not declined) {report.coverage.render()}")
    print(f"  exact-label agreement   {report.pass_rate.render()}")

    if show != "none":
        wanted = (
            report.results
            if show == "all"
            else [r for r in report.results if r.outcome is not Outcome.PASS]
        )
        if wanted:
            heading = "All cases" if show == "all" else "Cases the suite and the code disagree on"
            print(f"\n{heading}")
            print(_RULE)
            for result in wanted:
                marker = "ok " if result.outcome is Outcome.PASS else "FAIL"
                print(f"{marker} [{result.outcome.value}] {result.describe()}")
                if result.case.rationale:
                    print(f"           label rationale: {result.case.rationale}")
                print()

    print(_RULE)
    print(f"GATE: {report.gate.value}")
    print(_gate_sentence(report))

    print("\nWhat this number does not establish")
    for caveat in report.caveats:
        print(f"  - {caveat}")
    print()


def _gate_sentence(report: SuiteReport) -> str:
    if report.gate is Gate.PASS:
        return (
            "Under 2% on flagged records. R1 work may begin -- subject to kill tests 2 and 3, "
            "which have no numbers yet."
        )
    if report.gate is Gate.HOLD:
        return (
            "Between 2% and 5%. Per §6.1 this build does not ship. Work the comparator until it "
            "is under 2%; the project is not dead."
        )
    if report.gate is Gate.STOP:
        return (
            "Above 5%. Per §13 the correct decision is to stop the project, or narrow it to the "
            "value-semantics library plus the benchmark -- a real, useful, honest contribution "
            "and a much smaller claim."
        )
    return (
        "Not enough flagged records for the rate to mean anything. Grow the suite before reading "
        "the number; a confident figure off a handful of cases is the failure mode this product "
        "exists to detect in other people's data."
    )


def _as_dict(report: SuiteReport) -> dict[str, object]:
    return {
        "suite_version": report.suite_version,
        "cases": report.total,
        "gate": report.gate.value,
        "outcomes": {o.value: len(report.by_outcome(o)) for o in Outcome},
        "metrics": {
            "false_positive_rate_on_flagged": {
                "point": report.fp_on_flagged.point,
                "lo": report.fp_on_flagged.lo,
                "hi": report.fp_on_flagged.hi,
                "numerator": report.fp_on_flagged.successes,
                "denominator": report.fp_on_flagged.total,
            },
            "false_positive_rate_on_no_defect_pairs": {
                "point": report.fp_on_clean.point,
                "lo": report.fp_on_clean.lo,
                "hi": report.fp_on_clean.hi,
            },
            "missed_defect_rate": {
                "point": report.fn_on_defects.point,
                "lo": report.fn_on_defects.lo,
                "hi": report.fn_on_defects.hi,
            },
            "coverage": {
                "point": report.coverage.point,
                "lo": report.coverage.lo,
                "hi": report.coverage.hi,
            },
            # Finding 17. The gate verdict is taken from fp_reviewer_experienced; this is the
            # sensitivity band around it, with every dual-labelled case whose second label says
            # "raise nothing" resolved against the comparator. A consumer quoting the headline
            # without this band is quoting a conditional number as an unconditional one.
            "false_positive_rate_adversarial_dual_labels": {
                "point": report.fp_adversarial.point,
                "lo": report.fp_adversarial.lo,
                "hi": report.fp_adversarial.hi,
                "numerator": report.fp_adversarial.successes,
                "denominator": report.fp_adversarial.total,
                "contested_cases": [
                    {
                        "id": r.case.id,
                        "a": r.case.a,
                        "b": r.case.b,
                        "labels": [label.value for label in r.case.labels],
                        "comparator_said": r.actual.value,
                    }
                    for r in sorted(report.contested_findings, key=lambda r: r.case.id)
                ],
            },
        },
        "thresholds": {"pass_below": 0.02, "stop_above": 0.05},
        "caveats": report.caveats,
        "failures": [
            {
                "id": r.case.id,
                "family": r.case.family,
                "a": r.case.a,
                "b": r.case.b,
                "expected": [label.value for label in r.case.labels],
                "actual": r.actual.value,
                "outcome": r.outcome.value,
                "rationale": r.comparison.rationale,
                "source": r.case.source,
            }
            for r in report.results
            if r.outcome is not Outcome.PASS
        ],
    }


# ------------------------------------------------------------------------------------------------


def _run_operating_point(args: argparse.Namespace) -> int:
    corpus = None
    if args.corpus is not None:
        corpus = _operating_point_module.load_corpus(args.corpus)
    report = _operating_point_module.operating_point_report(corpus)

    if args.json:
        print(json.dumps(_operating_point_module.report_as_dict(report), indent=2))
    else:
        print(_operating_point_module.render_report(report))

    return _operating_point_module.GATE_EXIT_CODES[report.verdict]


def _run_coverage(args: argparse.Namespace) -> int:
    distribution = None
    if args.distribution is not None:
        distribution = _coverage_module.load_distribution(args.distribution)
    report = _coverage_module.coverage_report(distribution)

    if args.json:
        print(json.dumps(_coverage_module.report_as_dict(report), indent=2))
    else:
        print(_coverage_module.render_report(report))

    return _coverage_module.GATE_EXIT_CODES[report.gate]


def _status() -> int:
    report = run_suite()
    op_report = _operating_point_module.operating_point_report()
    cov_report = _coverage_module.coverage_report()

    op_line = "NOT MEASURED   no --corpus given; synthetic stand-in only"
    if not op_report.is_synthetic:
        op_line = f"{op_report.verdict.value:14} n={op_report.corpus.size} records"

    cov_line = "NOT MEASURED   no --distribution given; synthetic stand-in only"
    if not cov_report.is_synthetic:
        cov_line = (
            f"{cov_report.gate.value:14} {cov_report.distribution.class_count} classes, "
            f"{cov_report.distribution.sku_total} SKUs"
        )

    print(
        f"""
R0 STATUS -- {"all three gates must have numbers before R1 begins (PRD §4)"}
{_RULE}
  1  equivalence suite      FR-0.1/0.2   MEASURED       gate {report.gate.value}
                                                        FP (reviewer-experienced): {report.fp_reviewer_experienced.render_short()}
                                                        FP (narrow §6.1 reading):  {report.fp_on_flagged.render_short()}
  2  operating point        FR-0.3       {op_line}
  3  calibration coverage   FR-0.4       {cov_line}
{_RULE}
R1 is gated on all three. {"" }Run `errata-r0 operating-point --corpus <file>` and
`errata-r0 coverage --distribution <file>` with real data to make 2 and 3 live -- both gates
already implement the honesty rule (§0.3): NOT_MEASURED/NOT MEASURED unconditionally without one.
""".strip()
    )
    codes = [
        EXIT_PASS if report.gate is Gate.PASS else EXIT_HOLD,
        _operating_point_module.GATE_EXIT_CODES[op_report.verdict],
        _coverage_module.GATE_EXIT_CODES[cov_report.gate],
    ]
    return max(codes)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
