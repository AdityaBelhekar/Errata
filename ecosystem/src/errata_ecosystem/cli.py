"""``errata-r3`` -- the benchmark and the ecosystem from the command line.

**The exit code is the decision**, matching ``errata-r0``, ``errata-audit`` and ``errata-scale``:

    0  ran, and everything it checked holds
    1  ran, and something a reader needs to know about does not hold
    2  could not measure -- an input is missing, or the number honestly does not exist yet
    3  failed for a reason that is not about the data

Nothing here reaches the network. The gold set is reconstructed by
``scripts/fetch_reference_data.sh``, which is a separate, auditable step: "the benchmark used the
document at this URL" and "the benchmark used whatever was cached" are different claims, and a
harness that fetched silently could not tell you which one it made.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

import yaml

from .axes import AxisStatus, axis_ids, run_all, run_axis
from .bridge import BridgeValidationError, load_bridge
from .corpusbuild import COMPARATOR_SPECS, build_corpus, write_corpus
from .corpusscore import render_score, score_corpus
from .eclass import ECLASS_ENV_VAR, assert_clean, scan, scan_distribution
from .extractors import EXTRACTORS
from .goldset import VerificationLevel, load_gold_set, verify
from .leaderboard import leaderboard, losses, render_html, render_json, render_text
from .licences import check_licences
from .reproduce import Verdict, full_report, reproduce, write_json
from .reviewer import PROTOCOL, load_sessions, sessions_from_ledger
from .reviewer import report as reviewer_report
from .splits import HardTailTouched, assert_untouched, load_split, load_tuning_runs
from .vocabulary import canonical_uri

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_NOT_MEASURED = 2
EXIT_ERROR = 3

_RULE = "-" * 96

REPO_ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(prog="errata-r3", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    score = sub.add_parser("score", help="FR-9.1/9.2 -- run one axis, or all of them")
    score.add_argument("--axis", choices=axis_ids(), help="omit to run every axis")
    score.add_argument("--corpus", help="corpus for the grounding and abstention axes")
    score.add_argument("--json", action="store_true")

    board = sub.add_parser("leaderboard", help="FR-9.9 -- generated, including our losing scores")
    board.add_argument("--html", help="write the leaderboard here as HTML")
    board.add_argument("--json", action="store_true")
    board.add_argument("--corpus")

    gold = sub.add_parser("gold", help="FR-9.5 -- the gold set: URLs, hashes, annotations")
    gold.add_argument("action", choices=["verify", "show"])
    gold.add_argument("--documents", help="directory holding the fetched source documents")

    split = sub.add_parser("split", help="FR-9.6 -- the frozen hard-tail split and its guard")
    split.add_argument("action", choices=["show", "verify"])
    split.add_argument("--name", default="hard-tail")
    split.add_argument("--tuning-ledger")

    bridge = sub.add_parser("bridge", help="FR-9.7 -- the ETIM <-> UNSPSC attribute bridge")
    bridge.add_argument("action", choices=["show", "status", "export"])
    bridge.add_argument("--code", help="a UNSPSC eight-digit commodity code")
    bridge.add_argument("--json", action="store_true")

    eclass = sub.add_parser("eclass", help="FR-9.8 -- bring-your-own-licence, and the scanner")
    eclass.add_argument("action", choices=["scan", "adapter"])
    eclass.add_argument("--root", help="tree to scan (default: the repository)")
    eclass.add_argument("--dist", action="append", default=[], help="a built wheel or sdist to scan")
    eclass.add_argument("--path", help="the customer's licensed dictionary, for `adapter`")

    reviewer = sub.add_parser("reviewer", help="FR-9.3/9.4 -- the timed protocol and its arithmetic")
    reviewer.add_argument("--sessions", help="a session file produced under the protocol")
    reviewer.add_argument("--ledger", help="read adjudications out of an existing ledger")
    reviewer.add_argument("--protocol", action="store_true", help="print the protocol and stop")

    repro = sub.add_parser("reproduce", help="the R3 exit criterion, as far as we can run it")
    repro.add_argument("--corpus")
    repro.add_argument("--json", help="write the receipt here as JSON")
    repro.add_argument("--full", action="store_true", help="receipt plus leaderboard")

    corpus = sub.add_parser(
        "corpus",
        help="build and score an FR-0.3 corpus for a named extractor (gate 2, without the spike)",
    )
    corpus.add_argument(
        "action", choices=("build", "score", "list"), help="build a corpus, score one, or list extractors"
    )
    corpus.add_argument(
        "--extractor",
        default="r1-textwindow",
        help=(
            "which system to run. Default is r1-textwindow: R1 with table structure withheld, "
            "which is the only R1 configuration whose score is not a tautology against gold."
        ),
    )
    corpus.add_argument(
        "--comparator-spec",
        choices=COMPARATOR_SPECS,
        default="product",
        help=(
            "'product' describes attributes to the comparator as R1 does on a real run; 'frozen' "
            "reproduces the impoverished spec the published gate-2 corpus was built with"
        ),
    )
    corpus.add_argument("--out", help="write the built corpus here as YAML")

    sub.add_parser("licences", help="NFR-7 -- the licence check CI runs on every build")

    vocab = sub.add_parser("vocab", help="resolve an attribute term to its canonical uri (N15)")
    vocab.add_argument("term")

    sub.add_parser("status", help="what R3 can do, and what it declines to claim")

    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except BridgeValidationError as exc:
        print(f"bridge: {exc}", file=sys.stderr)
        return EXIT_FINDINGS
    except FileNotFoundError as exc:
        print(f"missing input: {exc}", file=sys.stderr)
        return EXIT_NOT_MEASURED
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def _dispatch(args: argparse.Namespace) -> int:
    match args.command:
        case "score":
            return _cmd_score(args)
        case "leaderboard":
            return _cmd_leaderboard(args)
        case "gold":
            return _cmd_gold(args)
        case "split":
            return _cmd_split(args)
        case "bridge":
            return _cmd_bridge(args)
        case "eclass":
            return _cmd_eclass(args)
        case "reviewer":
            return _cmd_reviewer(args)
        case "reproduce":
            return _cmd_reproduce(args)
        case "corpus":
            return _cmd_corpus(args)
        case "licences":
            return _cmd_licences()
        case "vocab":
            print(canonical_uri(args.term))
            return EXIT_OK
        case _:
            return _cmd_status()


def _cmd_licences() -> int:
    """NFR-7's acceptance criterion is "CI licence check on every build". This is that check."""
    report = check_licences()
    print(report.text())
    return EXIT_OK if report.ok else EXIT_FINDINGS


def _cmd_corpus(args: argparse.Namespace) -> int:
    """Gate 2's corpus, rebuilt by production code, for whichever system is named.

    ``build`` writes the corpus ``errata-r0 operating-point`` reads. ``score`` prints the
    stratified report, which refuses to hand back a single number when every stratum shares a
    mechanism with the answer key.
    """
    if args.action == "list":
        for name, description in sorted(EXTRACTORS.items()):
            print(f"  {name:16s} {description}")
        return EXIT_OK

    document = build_corpus(args.extractor, comparator_spec=args.comparator_spec)

    if args.out:
        path = write_corpus(document, args.out)
        print(f"wrote {path}  ({len(document['records'])} records)")
        return EXIT_OK

    if args.action == "build":
        print(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
        return EXIT_OK

    score = score_corpus(document)
    print(render_score(score))
    # Exit non-zero when nothing in the run may be quoted. A report whose every stratum shares a
    # mechanism with gold has produced no measurement, and a zero exit would let a CI job record
    # it as one.
    return EXIT_OK if any(s.comparable for s in score.strata) else EXIT_NOT_MEASURED


def _cmd_score(args: argparse.Namespace) -> int:
    results = (
        (run_axis(args.axis, corpus=args.corpus),) if args.axis else run_all(corpus=args.corpus)
    )
    if args.json:
        print(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        for result in results:
            print(result.text())
            print()
    return (
        EXIT_NOT_MEASURED
        if any(r.status is AxisStatus.NOT_MEASURED for r in results)
        else EXIT_OK
    )


def _cmd_leaderboard(args: argparse.Namespace) -> int:
    axes = run_all(corpus=args.corpus)
    board = leaderboard(axes, reviewer_report(load_sessions()))
    if args.html:
        target = Path(args.html)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_html(board), encoding="utf-8", newline="\n")
        print(f"wrote {target}")
    if args.json:
        print(render_json(board))
    elif not args.html:
        print(render_text(board))
    return EXIT_FINDINGS if losses(board) else EXIT_OK


def _cmd_gold(args: argparse.Namespace) -> int:
    gold = load_gold_set()
    if args.action == "show":
        print(f"gold set {gold.version}   {len(gold)} annotations")
        print(f"  layout {gold.layout_version}   gold builder {gold.gold_version}")
        for document in gold.documents:
            print(
                f"  {document['document']:<34} {document['records']:>5} records   "
                f"{document['pages']:>3} pages   {document['sha256'][:12]}"
            )
            print(f"      {document['url']}")
        print()
        print("  NO SOURCE DOCUMENT IS REDISTRIBUTED (FR-9.5). The files above are fetched from")
        print("  the publisher by scripts/fetch_reference_data.sh and verified against those")
        print("  hashes before use.")
        print()
        print(f"  {gold.labelling_caveat}")
        return EXIT_OK

    report = verify(gold, documents=args.documents)
    print(report.text())
    if not report.ok:
        return EXIT_FINDINGS
    return EXIT_OK if report.level is VerificationLevel.GROUNDED else EXIT_NOT_MEASURED


def _cmd_split(args: argparse.Namespace) -> int:
    split = load_split(args.name)
    print(split.text())
    if args.action == "show":
        for category in split.unrepresented:
            print(f"\n  {category['category']}: {'present' if category['present'] else 'ABSENT'}")
            print(f"      {category['why']}")
        return EXIT_OK

    runs = load_tuning_runs(args.tuning_ledger)
    try:
        assert_untouched(split, runs)
    except HardTailTouched as exc:
        print(f"\n{exc}", file=sys.stderr)
        return EXIT_FINDINGS
    print(f"\n  {len(runs)} declared tuning run(s); none touched the frozen split.")
    return EXIT_OK


def _cmd_bridge(args: argparse.Namespace) -> int:
    bridge, model = load_bridge()

    if args.action == "export":
        print(json.dumps(bridge.as_dict(model), indent=2))
        return EXIT_OK

    if args.action == "status":
        carried = [m for m in bridge.mappings if m.carries_attributes]
        print(f"bridge {bridge.version}, released {bridge.released}, licence {bridge.licence}")
        print(f"  ETIM release {bridge.etim_release}   UNSPSC {bridge.unspsc_sha256[:12]}")
        print(f"  {len(bridge.mappings)} mappings: {len(carried)} carry an attribute layer, "
              f"{len(bridge.refusals)} are refusals")
        print(_RULE)
        for key, text in bridge.attribution.items():
            print(f"  {key}: {text}")
        print(_RULE)
        print(f"  DECIDED BY: {bridge.decided_by}")
        return EXIT_OK

    codes = [args.code] if args.code else sorted({m.unspsc for m in bridge.mappings if m.unspsc})
    for code in codes:
        mappings = bridge.for_unspsc(code)
        if not mappings:
            print(f"{code}: no mapping in this bridge. That is an abstention, not a gap in the "
                  "codeset -- nothing is guessed.")
            continue
        for mapping in mappings:
            print(mapping.sentence())
            print(f"    confidence: {mapping.confidence}")
            print(f"    {mapping.rationale}")
        attributes = bridge.attributes_for(code, model)
        print(f"    attribute layer: {len(attributes)} ETIM features")
        for binding in attributes:
            print(f"      {binding.sentence()}")
        print()
    return EXIT_OK


def _cmd_eclass(args: argparse.Namespace) -> int:
    if args.action == "adapter":
        from .eclass import EclassAdapter

        path = args.path
        if not path:
            adapter = EclassAdapter.from_environment()
            if adapter is None:
                print(
                    "no ECLASS dictionary configured. Errata ships none and never will "
                    f"(ADR-003): set {ECLASS_ENV_VAR} to your own licensed export, or pass "
                    "--path."
                )
                return EXIT_NOT_MEASURED
        else:
            adapter = EclassAdapter.from_path(path)
        print(adapter.describe())
        return EXIT_OK

    reports = [scan(args.root)]
    for archive in args.dist:
        reports.append(scan_distribution(archive))
    for report in reports:
        print(report.text())
    try:
        assert_clean(reports)
    except AssertionError:
        return EXIT_FINDINGS
    return EXIT_OK


def _cmd_reviewer(args: argparse.Namespace) -> int:
    if args.protocol:
        print(PROTOCOL)
        return EXIT_OK
    sessions = (
        sessions_from_ledger(args.ledger) if args.ledger else load_sessions(args.sessions)
    )
    report = reviewer_report(sessions)
    print(report.text())
    return EXIT_OK if report.measured else EXIT_NOT_MEASURED


def _cmd_reproduce(args: argparse.Namespace) -> int:
    if args.full:
        print(full_report(corpus=args.corpus))
        receipt = reproduce(corpus=args.corpus)
    else:
        receipt = reproduce(corpus=args.corpus)
        print(receipt.text())
    if args.json:
        target = write_json(receipt, args.json)
        print(f"\nwrote {target}")
    match receipt.verdict:
        case Verdict.REPRODUCED:
            return EXIT_OK
        case Verdict.DIVERGED:
            return EXIT_FINDINGS
        case _:
            return EXIT_NOT_MEASURED


def _cmd_status() -> int:
    print("errata-r3 -- R3: the benchmark and the ecosystem")
    print(_RULE)
    print("WHAT IT DOES")
    print("  FR-9.1  ExtractBench's word-level grounding F1 at IoU 0.5, called rather than")
    print("          re-implemented -- errata_bench.operating_point is the one implementation.")
    print("  FR-9.2  five axes nobody else scores, each runnable alone: class assignment,")
    print("          compound values, cross-standard mapping, supersession, calibrated abstention.")
    print("  FR-9.5  the gold set as URLs, content hashes and annotation layers. No source PDF is")
    print("          redistributed, and every annotation is re-derived from the document it")
    print("          describes before any number computed from it is printed.")
    print("  FR-9.6  a frozen hard-tail split, hashed, with a guard that fails on a tuning run")
    print("          that touches it.")
    print("  FR-9.7  the ETIM <-> UNSPSC attribute bridge, Apache-2.0, ODC-By attributed, with a")
    print("          rationale on every row including the rows that refuse to map.")
    print("  FR-9.8  ECLASS by the customer's own licence at runtime, and a scanner over both the")
    print("          working tree and the built distributions.")
    print("  FR-9.9  a leaderboard generated from the harness, printing the scores we lose on.")
    print()
    print("WHAT IT DECLINES TO CLAIM")
    print(_RULE)
    print("  FR-9.3 reviewer-seconds per verified attribute -- NOT MEASURED. Nobody has been")
    print("         timed. The protocol ships; the number is a measurement of people.")
    print("  FR-9.4 evidence-acceptance rate -- NOT MEASURED, for the same reason. The only")
    print("         adjudications this repository holds were made by the people who built it.")
    print("  The exit criterion -- 'a third party reproduces our published scores from the repo'")
    print("         -- is OPEN. `errata-r3 reproduce` is the package; nobody outside has run it.")
    print("  The gold set is document-derived, not expert-labelled, and it is two documents from")
    print("         one manufacturer. The hard tail contains merged-source cells and none of the")
    print("         four categories the PRD names, because the corpus contains none of them.")
    print("  Every bridge mapping is a single judgement by its author. Validation proves the")
    print("         codes exist, not that the judgement is right.")
    return EXIT_OK


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            # A non-reconfigurable stream (a pipe under some launchers) is not a failure -- the
            # output is simply whatever encoding it already had.
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
