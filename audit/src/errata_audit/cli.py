"""``errata-audit`` -- FR-7.9. The audit, from a clean clone, with no signup.

    "audit sku --catalog-url <url> --datasheet <url> prints a redline with evidence, or an honest
     abstention. Runs from a clean clone with no signup. This is the README hook."

**The exit code is the decision, not a diagnostic**, matching ``errata-r0``:

    0  audited, and the catalog is supported by the document
    1  audited, and there are findings a reviewer should see
    2  could not audit -- no class, no document, or nothing that could be grounded
    3  the run failed for a reason that is not about the data

A CLI that exits 0 whether or not it found a poisoned record is a CLI nobody can put in a pipeline,
and 1-means-findings is the convention every linter in the world already taught the reader.

**Nothing here reaches the network unless told to.** ``--datasheet https://...`` requires
``--allow-network``; without it the command refuses rather than silently using a cached copy,
because "the audit used the PDF at this URL" and "the audit used yesterday's PDF" are different
claims and only one of them is what the operator asked for.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from errata_spec import Decision, DocumentRegister

from .attributes import load_attributes
from .audit import AuditRun, Outcome, SkuAudit, audit_sku
from .classify import ClassScope, load_scope, resolve_class, top_k_accuracy
from .confidence import load_calibration
from .console import render_html, render_text
from .documents import BlobStore, DocumentSource, NetworkNotPermittedError, ingest_document
from .etim import EtimModel, load_etim
from .ingest import CatalogRecord, load_catalog
from .layout import extract_layer
from .ledger import Ledger, calibration_examples

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_NOT_AUDITED = 2
EXIT_ERROR = 3

_RULE = "-" * 78

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ETIM_DIR = REPO_ROOT / "var" / "reference" / "etim"
DEFAULT_BLOBS = REPO_ROOT / "var" / "audit" / "blobs"
DEFAULT_LEDGER = REPO_ROOT / "var" / "audit" / "ledger.jsonl"
DEMO_DIR = Path(__file__).parent / "demo"
DEMO_CATALOG = DEMO_DIR / "catalog.csv"
DEMO_DATASHEETS = REPO_ROOT / "var" / "spike" / "datasheets"


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(
        prog="errata-audit",
        description="R1 -- audit one SKU against one document. Exit code is the decision.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sku = sub.add_parser("sku", help="audit one SKU (FR-7.9)")
    sku.add_argument("--catalog", "--catalog-url", dest="catalog", default=str(DEMO_CATALOG))
    sku.add_argument("--datasheet", action="append", default=[], help="path or URL; repeatable")
    sku.add_argument("--sku", default="", help="which record; omit with --random to pick one")
    sku.add_argument("--random", action="store_true", help="choose a SKU at runtime (PRD §12)")
    sku.add_argument("--html", type=Path, default=None, help="write the three-pane console here")
    sku.add_argument("--ledger", type=Path, default=None, help="append claims and redlines here")
    sku.add_argument("--json", action="store_true")
    _common(sku)

    catalog = sub.add_parser(
        "catalog", help="audit many records -- a convenience for demonstration, not R2 scale"
    )
    catalog.add_argument("--catalog", default=str(DEMO_CATALOG))
    catalog.add_argument("--datasheet", action="append", default=[])
    catalog.add_argument("--limit", type=int, default=0)
    catalog.add_argument("--json", action="store_true")
    _common(catalog)

    classes = sub.add_parser("classes", help="FR-2.2 -- top-1 / top-5 accuracy on a labelled set")
    classes.add_argument("--labels", type=Path, default=DEMO_DIR / "class-labels.yaml")
    classes.add_argument("--json", action="store_true")
    _common(classes)

    adjudicate = sub.add_parser("adjudicate", help="FR-7.6 -- record a human decision")
    adjudicate.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    adjudicate.add_argument("--redline-id", required=True)
    adjudicate.add_argument(
        "--decision", required=True, choices=["accept", "keep", "escalate"]
    )
    adjudicate.add_argument("--by", required=True, help="the adjudicator's name")
    adjudicate.add_argument("--second", default="", help="second adjudicator (safety class)")
    adjudicate.add_argument("--note", default="")
    adjudicate.add_argument("--seconds", type=float, default=None)
    adjudicate.add_argument(
        "--evidence-accepted", choices=["yes", "no"], default=None,
        help="did the box support the claim? feeds evidence-acceptance rate (FR-9.4)",
    )

    calibrate = sub.add_parser("calibrate", help="FR-6.1 -- fit a calibration set from decisions")
    calibrate.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    calibrate.add_argument("--out", type=Path, default=None)

    drift = sub.add_parser(
        "drift", help="NFR-4 -- the calibration drift alarm, and the fixtures that prove it fires"
    )
    drift.add_argument(
        "--fixture",
        choices=("stable", "drifted", "degraded"),
        default="drifted",
        help=(
            "which synthetic fixture to run the alarm against. `drifted` is NFR-4's acceptance "
            "criterion; `degraded` is the one that must NOT fire -- accuracy collapses while every "
            "promise stays true, which is how a calibration alarm is told from an accuracy alarm"
        ),
    )
    drift.add_argument("--n", type=int, default=400, help="observations in the window")
    drift.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help=(
            "watch REAL decisions instead of a fixture. Produces INSUFFICIENT_DATA today: "
            "calibration needs reviewer decisions and nobody has made any (FR-7.6)"
        ),
    )

    web = sub.add_parser(
        "serve", help="FR-7.1/7.6 -- the reviewer console as a local web app, with adjudication"
    )
    web.add_argument("--catalog", default=str(DEMO_CATALOG))
    web.add_argument("--datasheet", action="append", default=[])
    web.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    web.add_argument("--port", type=int, default=8765)
    web.add_argument(
        "--host",
        default="127.0.0.1",
        help="loopback by default; binding elsewhere needs --allow-remote and means it",
    )
    web.add_argument(
        "--allow-remote",
        action="store_true",
        help="permit a non-loopback bind. The console has NO authentication and shows a customer's "
        "catalog beside a manufacturer's document",
    )
    web.add_argument("--open", action="store_true", help="open a browser at the console")
    _common(web)

    sub.add_parser("status", help="what R1 can do, and what it declines to claim")

    args = parser.parse_args(argv)

    try:
        if args.command == "sku":
            return _cmd_sku(args)
        if args.command == "catalog":
            return _cmd_catalog(args)
        if args.command == "classes":
            return _cmd_classes(args)
        if args.command == "adjudicate":
            return _cmd_adjudicate(args)
        if args.command == "drift":
            return _cmd_drift(args)
        if args.command == "calibrate":
            return _cmd_calibrate(args)
        if args.command == "serve":
            return _cmd_serve(args)
        if args.command == "status":
            return _cmd_status()
    except NetworkNotPermittedError as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_ERROR
    except FileNotFoundError as error:
        print(f"missing input: {error}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_ERROR


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--etim", type=Path, default=None, help="ETIM release archive or directory")
    parser.add_argument("--etim-release", default="10.0")
    parser.add_argument("--scope", type=Path, default=None, help="class allow-list YAML (FR-2.4)")
    parser.add_argument("--blobs", type=Path, default=DEFAULT_BLOBS)
    parser.add_argument(
        "--allow-network", action="store_true", help="permit fetching http(s) documents"
    )


# ------------------------------------------------------------------------------------------------
# sku
# ------------------------------------------------------------------------------------------------


def _cmd_sku(args: argparse.Namespace) -> int:
    records = load_catalog(args.catalog)
    record = _pick(records, args)
    if record is None:
        print(
            f"no record {args.sku!r} in {args.catalog}. Pass --random to have one chosen at "
            "runtime, which is what the demo script does.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    scope, etim = _load_model(args)
    register = DocumentRegister()
    store = BlobStore(args.blobs)
    documents = _documents(args, record, register=register, store=store)
    document = _document_for(record, documents)

    if document is None:
        print(_no_document_text(record))
        return EXIT_NOT_AUDITED

    result = audit_sku(
        record,
        document,
        etim=etim,
        scope=scope,
        attributes=load_attributes(),
        calibration=load_calibration(),
    )

    ledger = Ledger(args.ledger) if args.ledger else None
    if ledger is not None:
        _record(ledger, result)

    if args.json:
        print(json.dumps(_as_json(result), indent=2, default=str))
    else:
        print(render_text(result))
        if ledger is not None:
            print(f"\nledger: {ledger.path}")
            for outcome in result.findings:
                assert outcome.redline is not None
                print(
                    f"  errata-audit adjudicate --redline-id {outcome.redline.redline_id} "
                    f"--decision accept --by <name>"
                    + (" --second <name>" if outcome.redline.requires_two_signatures else "")
                )

    if args.html:
        layer = extract_layer(document.path, document_sha256=document.sha256)
        history = tuple(dict(e) for e in ledger.history(record.sku_id)) if ledger else ()
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(
            render_html(
                result, layer=layer, history=history, etim_attribution=etim.attribution
            ),
            "utf-8",
        )
        print(f"\nconsole: {args.html}")

    if result.findings:
        return EXIT_FINDINGS
    if not result.audited:
        return EXIT_NOT_AUDITED
    return EXIT_CLEAN


def _pick(records: tuple[CatalogRecord, ...], args: argparse.Namespace) -> CatalogRecord | None:
    if args.sku:
        return next((r for r in records if r.sku_id == args.sku or r.mpn == args.sku), None)
    if args.random:
        # PRD §12's demo criterion is "on a SKU chosen at runtime". Unseeded on purpose: a seeded
        # choice is a rehearsal, and the point of the criterion is that nothing was rehearsed.
        chosen = random.choice(records)
        print(f"# SKU chosen at runtime: {chosen.sku_id}\n")
        return chosen
    return records[0] if records else None


# ------------------------------------------------------------------------------------------------
# catalog
# ------------------------------------------------------------------------------------------------


def _cmd_catalog(args: argparse.Namespace) -> int:
    records = load_catalog(args.catalog)
    if args.limit:
        records = records[: args.limit]
    scope, etim = _load_model(args)
    register = DocumentRegister()
    store = BlobStore(args.blobs)
    calibration = load_calibration()
    attributes = load_attributes()

    documents: dict[str, DocumentSource] = {}
    for path in _datasheet_paths(args, records):
        try:
            source = ingest_document(
                path, register=register, store=store, allow_network=args.allow_network
            )
        except FileNotFoundError:
            continue
        documents[Path(str(path)).name] = source

    audits: list[SkuAudit] = []
    missing = 0
    for record in records:
        document = documents.get(Path(record.datasheet).name) if record.datasheet else None
        if document is None and len(documents) == 1 and not record.datasheet:
            document = next(iter(documents.values()))
        if document is None:
            missing += 1
            continue
        audits.append(
            audit_sku(
                record,
                document,
                etim=etim,
                scope=scope,
                attributes=attributes,
                calibration=calibration,
            )
        )

    run = AuditRun(
        skus=tuple(audits),
        policy_version="electrical-conservative@v3",
        attribute_map_version=attributes.version,
        etim_release=etim.release,
        etim_attribution=etim.attribution,
        notes=(
            f"{missing} record(s) named a datasheet that was not supplied and were not audited; "
            "they are reported here rather than dropped.",
        )
        if missing
        else (),
    )

    if args.json:
        print(
            json.dumps(
                {
                    "records": len(records),
                    "audited": len(run.skus),
                    "records_without_document": missing,
                    "findings": len(run.findings),
                    "declined": len(run.declined),
                    "resolved": len(run.resolved),
                    "coverage": round(run.coverage, 4),
                    "declined_by_reason": run.declined_by_reason(),
                },
                indent=2,
            )
        )
    else:
        print(_RULE)
        print(f"ERRATA -- {len(run.skus)} record(s) audited from {args.catalog}")
        print(_RULE)
        print(f"findings            {len(run.findings)}")
        print(f"checked, supported  {len(run.resolved)}")
        print(f"declined            {len(run.declined)}")
        print(f"coverage            {run.coverage:.1%}")
        if missing:
            print(f"no document         {missing}")
        print("\ndeclined by reason")
        for reason, count in run.declined_by_reason().items():
            print(f"  {reason:38s} {count:5d}")
        print("\ntop findings by expected review value")
        for outcome in run.findings[:10]:
            assert outcome.redline is not None
            print("  " + outcome.redline.queue_sentence().splitlines()[0])
            print(
                f"      catalog {outcome.catalog_value!r} / document {outcome.derived_value!r}"
            )
        for note in run.notes:
            print(f"\nnote: {note}")

    return EXIT_FINDINGS if run.findings else EXIT_CLEAN


# ------------------------------------------------------------------------------------------------
# classes
# ------------------------------------------------------------------------------------------------


def _cmd_classes(args: argparse.Namespace) -> int:
    import yaml

    if not args.labels.exists():
        print(f"no labelled set at {args.labels}", file=sys.stderr)
        return EXIT_ERROR
    document = yaml.safe_load(args.labels.read_text("utf-8"))
    scope, etim = _load_model(args)

    pairs = []
    rows = []
    abstain_rows = []
    for case in document.get("cases", ()):
        # No `attribute_features` here, deliberately. The schema-fit tie-break is evidence about a
        # *record* -- which attributes the feed actually carries -- and these cases are bare
        # descriptions with no record behind them. Passing the whole attribute map would hand every
        # ambiguous query the same tie-break and turn a guess into an apparent 100%: the first run
        # of this evaluation did exactly that, and resolved "circuit breaker" to EC000042 five
        # cases in a row (finding N13).
        resolution = resolve_class(case["query"], etim, scope=scope)
        if case.get("class_id"):
            pairs.append((resolution, case["class_id"]))
            rows.append((case["query"], case["class_id"], resolution))
        else:
            # A must-abstain case is scored separately and never folded into the accuracy rate.
            # Averaging the two would let a resolver trade a wrong class for a correct decline and
            # report the same number, which is exactly the substitution FR-2.3 is about.
            abstain_rows.append((case["query"], resolution, case.get("why", "")))

    top1 = top_k_accuracy(pairs, k=1)
    top5 = top_k_accuracy(pairs, k=5)
    abstained = sum(1 for r, _ in pairs if r.abstained)
    wrong = [(q, gold, r) for q, gold, r in rows if r.class_id and r.class_id != gold]
    held = sum(1 for _q, r, _w in abstain_rows if r.abstained)

    if args.json:
        print(
            json.dumps(
                {
                    "labelled_by": document.get("labelled_by", ""),
                    "cases": top1[1],
                    "top1": {"hits": top1[0], "rate": round(top1[2], 4)},
                    "top5": {"hits": top5[0], "rate": round(top5[2], 4)},
                    "abstained_on_labelled": abstained,
                    "must_abstain": {"held": held, "cases": len(abstain_rows)},
                    "wrong": [
                        {"query": q, "gold": gold, "chosen": r.class_id} for q, gold, r in wrong
                    ],
                    "resolved_when_it_should_have_held": [
                        {"query": q, "chosen": r.class_id}
                        for q, r, _why in abstain_rows
                        if not r.abstained
                    ],
                },
                indent=2,
            )
        )
        return EXIT_CLEAN

    print(_RULE)
    print(f"FR-2.2 class resolution -- {top1[1]} labelled cases")
    print(_RULE)
    print(f"top-1     {top1[0]}/{top1[1]}  {top1[2]:.1%}")
    print(f"top-5     {top5[0]}/{top5[1]}  {top5[2]:.1%}")
    print(f"abstained {abstained}/{top1[1]}  {abstained / top1[1]:.1%}  (never counted as a hit)")
    print(
        "\nRead the rate next to the abstention count: a resolver can buy accuracy by declining\n"
        "the hard cases, exactly as a comparator can flatter its false-positive rate by refusing\n"
        "to commit."
    )
    if abstain_rows:
        print(
            f"\nmust abstain  {held}/{len(abstain_rows)} held  -- scored separately, never folded "
            "into the rate above"
        )
        for query, resolution, why in abstain_rows:
            if not resolution.abstained:
                print(f"  RESOLVED WHEN IT SHOULD HAVE HELD: {query!r} -> {resolution.class_id}")
                if why:
                    print(f"    {why}")

    if wrong:
        print("\nwrong (chose a class that is not the label):")
        for query, gold, resolution in wrong:
            print(f"  {query!r}\n    gold {gold}  chosen {resolution.class_id}")
    caveat = document.get("caveat", "")
    if caveat:
        print(f"\ncaveat: {caveat}")
    return EXIT_CLEAN


# ------------------------------------------------------------------------------------------------
# adjudicate / calibrate / status
# ------------------------------------------------------------------------------------------------


def _cmd_adjudicate(args: argparse.Namespace) -> int:
    from errata_spec import Redline

    ledger = Ledger(args.ledger)
    match = next(
        (
            event
            for event in ledger.of_kind("redline")
            if str(event.payload.get("redline_id")) == args.redline_id
        ),
        None,
    )
    if match is None:
        print(f"no redline {args.redline_id} in {args.ledger}", file=sys.stderr)
        return EXIT_ERROR

    redline = Redline.model_validate(match.payload)
    decision = {
        "accept": Decision.ACCEPT_REDLINE,
        "keep": Decision.KEEP_CATALOG,
        "escalate": Decision.ESCALATE,
    }[args.decision]

    if redline.requires_two_signatures and not args.second:
        print(
            f"{redline.attribute_uri} is a safety-class attribute: acceptance needs a second "
            "named adjudicator (FR-8.9). Pass --second.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    evidence_accepted = (
        None if args.evidence_accepted is None else args.evidence_accepted == "yes"
    )
    score_event = next(
        (
            event
            for event in ledger.of_kind("score")
            if str(event.payload.get("redline_id")) == args.redline_id
        ),
        None,
    )
    adjudication, claim = ledger.adjudicate(
        redline,
        decision=decision,
        decided_by=args.by,
        note=args.note,
        seconds_to_decision=args.seconds,
        evidence_accepted=evidence_accepted,
        second_adjudicator=args.second,
        raw_score=score_event.payload.get("raw_score") if score_event else None,
    )
    print(
        f"recorded: {decision.value} on {redline.sku_id}/{redline.attribute_label or redline.attribute_uri} "
        f"by {adjudication.decided_by} at {adjudication.decided_at.isoformat()}"
    )
    print(f"claim {claim.claim_id} appended -- nothing was overwritten")
    if decision is Decision.KEEP_CATALOG and not redline.counter_evidence.supporting:
        print(
            "\nNoted: this was 'keep catalog' against an empty counter-evidence panel. §5.4 calls "
            "that the highest-signal event in the system -- the reviewer knows something the "
            "corpus does not, and it is both a document-recovery lead and a false-positive signal."
        )
    return EXIT_CLEAN


def _cmd_drift(args) -> int:
    """NFR-4. Run the alarm against a fixture, or against a real ledger.

    The exit code carries the verdict, matching every other command here: 0 stable, 1 drifted (a
    finding somebody must act on), 2 insufficient data -- which is deliberately not 0, because
    "nothing has been checked" and "everything is fine" are different statements.
    """
    from .drift import (
        DriftVerdict,
        degraded_but_calibrated,
        drifted_overconfident,
        monitor,
        stable,
    )

    if args.ledger:
        observations = [
            (float(p), bool(y)) for p, y in calibration_examples(Ledger(args.ledger))
        ]
        print(
            f"  watching {len(observations)} real adjudication(s) from {args.ledger}\n"
            "  This is the mode that matters and it has nothing to watch yet: calibration needs\n"
            "  reviewer decisions and none exist (FR-7.6, errata_audit.confidence).\n"
        )
    else:
        observations = {
            "stable": stable,
            "drifted": drifted_overconfident,
            "degraded": degraded_but_calibrated,
        }[args.fixture](args.n)
        print(
            f"  SYNTHETIC FIXTURE {args.fixture!r}. Nothing here measures calibration quality --\n"
            "  the thing under test is the ALARM, and the only way to test an alarm is to cause\n"
            "  the condition it watches for. NFR-4's own acceptance criterion asks for exactly\n"
            "  this. Ground rule 5 governs gates; this is not one.\n"
        )

    report = monitor(observations)
    print(report.text())
    return {
        DriftVerdict.STABLE: EXIT_CLEAN,
        DriftVerdict.DRIFTED: EXIT_FINDINGS,
        DriftVerdict.INSUFFICIENT_DATA: EXIT_NOT_AUDITED,
    }[report.verdict]


def _cmd_calibrate(args: argparse.Namespace) -> int:
    from .confidence import fit_platt

    ledger = Ledger(args.ledger)
    examples = calibration_examples(ledger)
    if len(examples) < 2:
        print(
            f"{len(examples)} usable decision(s) in {args.ledger}. Calibration needs reviewer "
            "decisions of both kinds -- accepted redlines and kept catalog values. Until then "
            "confidences are reported as raw scores and never as probabilities, which is the "
            "honest position rather than a missing feature."
        )
        return EXIT_NOT_AUDITED

    try:
        model = fit_platt(
            examples,
            calibration_set_id=f"ledger-{args.ledger.stem}",
            provenance=f"fitted from {len(examples)} adjudications in {args.ledger}",
        )
    except ValueError as error:
        print(f"cannot calibrate: {error}")
        return EXIT_NOT_AUDITED

    print(f"fitted on {model.n} decisions ({model.positives} accepted, base rate {model.base_rate:.1%})")
    print(f"expected calibration error {model.expected_calibration_error:.3f}")
    print("\nreliability diagram")
    for row in model.bins:
        print(
            f"  [{row.lower:.1f},{row.upper:.1f})  n={row.count:4d}  said {row.mean_predicted:.2f}  "
            f"observed {row.observed_rate:.2f}  gap {row.gap:+.2f}"
        )

    if args.out:
        import yaml

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            yaml.safe_dump(
                {
                    "calibration_set_id": model.calibration_set_id,
                    "provenance": model.provenance,
                    "examples": [
                        {"raw_score": score, "catalog_wrong": bool(label)}
                        for score, label in examples
                    ],
                },
                sort_keys=False,
            ),
            "utf-8",
        )
        print(f"\nwrote {args.out}")
    return EXIT_CLEAN


def _cmd_serve(args: argparse.Namespace) -> int:
    """Run the reviewer console until interrupted.

    The bind address is checked here rather than in the server: refusing a non-loopback bind is a
    product decision, and it belongs where the operator typed the flag. A console with no
    authentication on a network interface is not a smaller version of the same thing.
    """
    from .web import build_service, serve

    loopback = args.host in {"127.0.0.1", "::1", "localhost"}
    if not loopback and not args.allow_remote:
        print(
            f"refusing to bind {args.host}: this console has no authentication and renders a "
            "customer's catalog next to a manufacturer's document. Pass --allow-remote if you "
            "mean it, and put something in front of it that does authenticate.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    scope, etim = _load_model(args)
    records = load_catalog(args.catalog)
    datasheets = _datasheet_paths(args, records)
    if not datasheets:
        print(
            "no datasheets to audit against. Pass --datasheet, or put the documents where the "
            f"demo expects them ({DEMO_DATASHEETS}).",
            file=sys.stderr,
        )
        return EXIT_ERROR

    service = build_service(
        catalog=args.catalog,
        datasheets=datasheets,
        etim=etim,
        scope=scope,
        ledger=args.ledger,
        blobs=args.blobs,
        attributes=load_attributes(),
    )
    httpd = serve(service, host=args.host, port=args.port)
    url = f"http://{args.host}:{httpd.server_address[1]}/"

    print(_RULE)
    print(f"ERRATA reviewer console  {url}")
    print(_RULE)
    print(f"catalog   {args.catalog}  ({len(service.catalog)} records)")
    print(f"documents {', '.join(sorted(service.documents))}")
    print(f"ledger    {args.ledger}   (append-only; decisions are written here)")
    print(f"etim      {etim.release} -- {etim.attribution}")
    print()
    print("The first queue page audits 40 records and says how far it has scanned; the rest are")
    print("audited on demand. Confidences are RAW SCORES until reviewer decisions exist.")
    print("Ctrl-C to stop.")

    if args.open:  # pragma: no cover - convenience only
        import webbrowser

        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - operator action
        print("\nstopped.")
    finally:
        httpd.server_close()
    return EXIT_CLEAN


def _cmd_status() -> int:
    print(_RULE)
    print("ERRATA R1 -- what this can do, and what it declines to claim")
    print(_RULE)
    for line in (
        "built    ingest, document register + content-addressed store, layout with word boxes,",
        "         table structure with header roles, ETIM class resolution in three stages,",
        "         blind re-derivation, the comparator, the declined bucket, the ledger, and the",
        "         three-pane console -- as a static report AND as a local web app where a",
        "         reviewer actually decides:  errata-audit serve --open",
        "",
        "NOT      the embedding retriever and the cross-encoder (FR-2.2 halves): interfaces only.",
        "         An LLM selector: an interface only, capped at 5 candidates by construction.",
        "         A calibration set (FR-6.1): none exists, because calibration needs reviewer",
        "         decisions and nobody has made any. Confidences are raw scores and say so.",
        "         OCR (FR-1.4): born-digital documents only; a scan is declined, not guessed.",
        "",
        "gates    R0 gate 1 PASS 1.30%; gate 2 MEASURED, asymmetry NOT confirmed; gate 3 deferred",
        "         by decision D-1. R1 was entered on an explicit, recorded waiver -- see PHASES.md.",
    ):
        print(line)
    return EXIT_CLEAN


# ------------------------------------------------------------------------------------------------
# shared
# ------------------------------------------------------------------------------------------------


def _load_model(args: argparse.Namespace) -> tuple[ClassScope, EtimModel]:
    scope = load_scope(args.scope)
    archive = args.etim or _default_etim()
    if archive is None:
        raise FileNotFoundError(
            f"no ETIM release found in {DEFAULT_ETIM_DIR}. Run scripts/fetch_reference_data.sh, "
            "or pass --etim. The model is free (ODC-By) and needs no login."
        )
    return scope, load_etim(archive, release=args.etim_release, class_ids=scope.as_set)


def _default_etim() -> Path | None:
    if not DEFAULT_ETIM_DIR.exists():
        return None
    extracted = DEFAULT_ETIM_DIR / "extracted"
    if (extracted / "ETIMARTCLASS.csv").exists():
        return extracted
    archives = sorted(p for p in DEFAULT_ETIM_DIR.glob("*.zip") if not p.name.startswith("_"))
    return archives[0] if archives else None


def _documents(
    args: argparse.Namespace,
    record: CatalogRecord,
    *,
    register: DocumentRegister,
    store: BlobStore,
) -> list[DocumentSource]:
    out: list[DocumentSource] = []
    for path in _datasheet_paths(args, (record,)):
        try:
            out.append(
                ingest_document(
                    path, register=register, store=store, allow_network=args.allow_network
                )
            )
        except FileNotFoundError:
            continue
    return out


def _datasheet_paths(args: argparse.Namespace, records) -> list[str]:
    if args.datasheet:
        return list(args.datasheet)
    wanted = {r.datasheet for r in records if r.datasheet}
    if wanted and DEMO_DATASHEETS.exists():
        return [str(DEMO_DATASHEETS / name) for name in sorted(wanted)]
    if DEMO_DATASHEETS.exists():
        return [str(p) for p in sorted(DEMO_DATASHEETS.glob("*.pdf"))]
    return []


def _document_for(record: CatalogRecord, documents: list[DocumentSource]) -> DocumentSource | None:
    """Choose the document to audit against, or ``None``.

    A record that names a datasheet gets that datasheet or nothing -- auditing it against a
    different manufacturer's PDF would be the worst failure this system could have.

    When a record names none and several were supplied, the choice is made on evidence rather than
    on order: the document whose text actually contains the type designation. If several do, the
    caller is asked rather than guessed at; if none does, there is no source document. Taking
    ``documents[0]`` would be a coin flip wearing a sort order.
    """
    if record.datasheet:
        wanted = Path(record.datasheet).name
        return next(
            (d for d in documents if d.path.name.endswith(wanted) or d.doc_id == wanted), None
        )
    if len(documents) <= 1:
        return documents[0] if documents else None

    mpn = record.mpn or record.sku_id
    matches = [
        document
        for document in documents
        if any(
            word.text == mpn
            for word in extract_layer(document.path, document_sha256=document.sha256).words
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _no_document_text(record: CatalogRecord) -> str:
    return (
        f"{record.sku_id}: no source document.\n"
        f"  The record names {record.datasheet!r} and it was not supplied.\n"
        "  Declined with reason no_source_document (FR-6.2). This record joins the document\n"
        "  recovery queue; it is not audited against a different manufacturer's PDF, and it is\n"
        "  not silently skipped."
    )


def _record(ledger: Ledger, audit: SkuAudit) -> None:
    for outcome in audit.outcomes:
        if outcome.claim is not None:
            ledger.append_claim(outcome.claim)
        if outcome.abstention is not None:
            ledger.append_abstention(outcome.abstention)
        if outcome.redline is not None:
            ledger.append_redline(outcome.redline)
            # The score the extractor actually had at the time, recorded as its own event rather
            # than folded into the redline. Two reasons: the redline event stays a faithful dump of
            # the schema in `errata_spec`, and calibration must be fitted against the signal that
            # existed when the reviewer decided -- not against a probability produced later by the
            # model the decision is being used to fit.
            ledger.append(
                "score",
                {
                    "redline_id": str(outcome.redline.redline_id),
                    "sku_id": outcome.redline.sku_id,
                    "attribute_uri": outcome.redline.attribute_uri,
                    "raw_score": outcome.confidence.raw_score,
                    "calibrated_p": outcome.confidence.calibrated_p,
                    "method": outcome.derivation.method if outcome.derivation else "",
                },
            )


def _as_json(audit: SkuAudit) -> dict:
    return {
        "sku": audit.record.sku_id,
        "document": {
            "doc_id": audit.document.doc_id,
            "sha256": audit.document.sha256,
            "source_url": audit.document.source_url,
        },
        "class": {
            "uri": audit.class_uri,
            "resolved": audit.resolution.class_id,
            "selector": audit.resolution.selector,
            "margin": audit.resolution.margin,
            "retrieval_method": audit.resolution.retrieval_method,
            "declined_reason": audit.resolution.declined_reason.value
            if audit.resolution.declined_reason
            else None,
        },
        "coverage": round(audit.coverage, 4),
        "outcomes": [
            {
                "attribute": outcome.attribute.key,
                "attribute_uri": outcome.attribute.uri,
                "outcome": outcome.outcome,
                "catalog_value": outcome.catalog_value,
                "derived_value": outcome.derived_value,
                "disagreement_class": outcome.comparison.disagreement_class.value
                if outcome.comparison
                else None,
                "severity": int(outcome.severity),
                "declined_reason": outcome.declined_reason.value
                if outcome.declined_reason
                else None,
                "detail": outcome.detail,
                "raw_score": outcome.confidence.raw_score,
                "calibrated_p": outcome.confidence.calibrated_p,
                "redline_id": str(outcome.redline.redline_id) if outcome.redline else None,
                "evidence": [
                    {
                        "page": e.page,
                        "char_span": list(e.char_span),
                        "bbox": [e.bbox.x0, e.bbox.y0, e.bbox.x1, e.bbox.y1] if e.bbox else None,
                        "row_header": e.row_header,
                        "column_header": e.column_header,
                        "snippet": e.snippet,
                    }
                    for e in (outcome.redline.evidence if outcome.redline else outcome.derivation.evidence if outcome.derivation else ())
                ],
                "counter_evidence": outcome.redline.counter_evidence.summary
                if outcome.redline
                else None,
            }
            for outcome in audit.outcomes
        ],
        "not_audited": [o.attribute.key for o in audit.outcomes if o.outcome == Outcome.NOT_IN_FEED],
    }


def _force_utf8() -> None:
    """Same reason as ``errata-r0``: this prints section marks and en-dashes, and on Windows the
    process must decide its own output encoding rather than inheriting cp1252 and corrupting the
    very output a reader is being asked to trust."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding in {"utf8", "utf8sig"}:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # pragma: no cover
            continue


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
