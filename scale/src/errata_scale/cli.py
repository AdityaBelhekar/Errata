"""``errata-scale`` -- R2 from the command line.

**The exit code is the decision, not a diagnostic**, matching ``errata-r0`` and ``errata-audit``:

    0  the run completed and nothing needs a reviewer
    1  the run completed and there are findings a reviewer should see
    2  the run could not proceed -- no catalog, or a corpus that has not been built
    3  the run failed for a reason that is not about the data

``run`` is the command R2 exists for: a whole catalog, tier by tier, with the groundable fraction
printed before the findings and every ranking factor printed under the row it ranked. Everything
else here is a way of looking at one part of that in isolation, or of doing something to a batch
after the fact -- draining its queue, reversing it, reading a claim's history.

Nothing reaches the network unless ``--allow-network`` says so, for the reason the R1 CLI gives:
"the audit used the PDF at this URL" and "the audit used yesterday's copy" are different claims.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from errata_audit import (
    BlobStore,
    DocumentSource,
    Ledger,
    ingest_document,
    load_attributes,
    load_calibration,
    load_catalog,
    load_etim,
    load_scope,
)
from errata_spec import Decision, DocumentRegister, builtin_policy

from .chains import claim_chains, scan_for_mutation
from .groundable import GroundingStatus, inventory
from .queue import ReviewQueue, SecondAdjudicatorRequired
from .report import render_html, render_json, render_text
from .reversal import accepted_in_batch, reverse_batch
from .run import SCALE_VERSION, run_catalog
from .triage import QueueEntry

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_NOT_RUN = 2
EXIT_ERROR = 3

_RULE = "-" * 78

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ETIM_DIR = REPO_ROOT / "var" / "reference" / "etim"
DEFAULT_BLOBS = REPO_ROOT / "var" / "audit" / "blobs"
DEFAULT_LEDGER = REPO_ROOT / "var" / "scale" / "ledger.jsonl"
DEFAULT_CATALOG = REPO_ROOT / "var" / "scale" / "catalog.csv"
DEFAULT_PROVENANCE = REPO_ROOT / "var" / "scale" / "provenance.yaml"
DEMO_DATASHEETS = REPO_ROOT / "var" / "spike" / "datasheets"
REAL_CATALOG = REPO_ROOT / "audit" / "src" / "errata_audit" / "demo" / "catalog.csv"

BANNER = (
    "THE CATALOG IS CONSTRUCTED. Stratum S1 comes from the R1 demonstration catalog, whose rows "
    "were read from ABB's own hash-registered datasheet; stratum S2 is generated with defects "
    "injected on purpose, because no public 10k+ industrial catalog with retrievable source "
    "documents was reachable. Detection numbers describe a population we created; grounding, "
    "where a document exists, is empirical. See var/scale/provenance.yaml."
)


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(prog="errata-scale", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="audit a whole catalog, T0 -> T3")
    run.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    run.add_argument("--datasheet", action="append", default=[], help="path or URL; repeatable")
    run.add_argument("--limit", type=int, default=0, help="first N records only")
    run.add_argument("--top", type=int, default=15)
    run.add_argument("--html", type=Path, default=None)
    run.add_argument("--json", action="store_true")
    run.add_argument("--ledger", type=Path, default=None, help="record the batch here (FR-8.8)")
    run.add_argument("--label", default="", help="name a second batch over the same inputs")
    run.add_argument("--no-documents", action="store_true", help="T0 only; skip ETIM and T1")
    _common(run)

    ground = sub.add_parser("groundable", help="FR-8.1 -- the inventory alone, before any audit")
    ground.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    ground.add_argument("--datasheet", action="append", default=[])
    ground.add_argument("--json", action="store_true")
    ground.add_argument("--bucket", default="", help="enumerate one bucket to record level")
    _common(ground)

    clusters = sub.add_parser("clusters", help="FR-8.5 -- error signatures, computed")
    clusters.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    clusters.add_argument("--datasheet", action="append", default=[])
    clusters.add_argument("--top", type=int, default=25)
    clusters.add_argument("--json", action="store_true")
    clusters.add_argument("--no-documents", action="store_true")
    _common(clusters)

    queue = sub.add_parser("queue", help="the ranked queue, and how much of it is drained")
    queue.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    queue.add_argument("--datasheet", action="append", default=[])
    queue.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    queue.add_argument("--top", type=int, default=15)
    queue.add_argument("--open-only", action="store_true")
    queue.add_argument("--no-documents", action="store_true")
    _common(queue)

    drain = sub.add_parser(
        "drain",
        help="record decisions over the ranked queue (FR-7.6); the batch reversal demonstration",
    )
    drain.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    drain.add_argument("--datasheet", action="append", default=[])
    drain.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    drain.add_argument("--by", required=True, help="the adjudicator's name")
    drain.add_argument("--second", default="", help="second adjudicator, for safety-class rows")
    # Deliberately not --limit: `_load_run` reads `--limit` as "first N records", and a drain that
    # silently audited only the first 1,000 rows before deciding on them would report a queue that
    # was never the queue. Found by running it.
    drain.add_argument(
        "--count", type=int, default=1000, help="how many queue rows to decide (not records)"
    )
    drain.add_argument(
        "--decision",
        choices=["accept", "keep", "alternate"],
        default="accept",
        help="scripted decision. NOT human review -- see the banner this command prints",
    )
    drain.add_argument("--seconds", type=float, default=None)
    drain.add_argument("--no-documents", action="store_true")
    _common(drain)

    reverse = sub.add_parser("reverse", help="FR-8.8 -- reverse a batch, as a query")
    reverse.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    reverse.add_argument("--batch", required=True)
    reverse.add_argument("--by", required=True)
    reverse.add_argument("--reason", default="")
    reverse.add_argument("--dry-run", action="store_true")

    chain = sub.add_parser("chain", help="FR-8.2 -- the supersedes chain for one SKU")
    chain.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    chain.add_argument("--sku", default="")

    integrity = sub.add_parser(
        "integrity", help="FR-8.2 -- scan every module for ledger UPDATE or DELETE"
    )
    integrity.add_argument("--root", type=Path, action="append", default=[])

    corpus = sub.add_parser("corpus", help="build the R2 demonstration catalog")
    corpus.add_argument("--total", type=int, default=10_000)
    corpus.add_argument("--out", type=Path, default=DEFAULT_CATALOG)

    sub.add_parser("policy", help="FR-8.3 -- the resolution policy this build would apply")
    sub.add_parser("status", help="what R2 can do, and what it declines to claim")

    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_NOT_RUN


def _dispatch(args: argparse.Namespace) -> int:
    return {
        "run": _cmd_run,
        "groundable": _cmd_groundable,
        "clusters": _cmd_clusters,
        "queue": _cmd_queue,
        "drain": _cmd_drain,
        "reverse": _cmd_reverse,
        "chain": _cmd_chain,
        "integrity": _cmd_integrity,
        "corpus": _cmd_corpus,
        "policy": lambda _args: _cmd_policy(),
        "status": lambda _args: _cmd_status(),
    }[args.command](args)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--etim", type=Path, default=None)
    parser.add_argument("--etim-release", default="10.0")
    parser.add_argument("--scope", type=Path, default=None)
    parser.add_argument("--blobs", type=Path, default=DEFAULT_BLOBS)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="permit fetching a datasheet URL; off by default and never implied",
    )


# ------------------------------------------------------------------------------------------------
# loading
# ------------------------------------------------------------------------------------------------


def _catalog_path(args: argparse.Namespace) -> Path:
    path = Path(args.catalog)
    if path.exists():
        return path
    raise FileNotFoundError(
        f"no catalog at {path}. The R2 demonstration corpus is generated rather than committed "
        "(10,000 rows of constructed catalog is not source). Build it with:\n"
        "    errata-scale corpus\n"
        "or point --catalog at your own CSV, TSV, JSON or YAML feed."
    )


def _documents(args: argparse.Namespace, records) -> dict[str, DocumentSource]:
    if getattr(args, "no_documents", False):
        return {}
    register = DocumentRegister()
    store = BlobStore(args.blobs)
    paths = list(args.datasheet)
    if not paths:
        wanted = {record.datasheet for record in records if record.datasheet}
        if DEMO_DATASHEETS.exists():
            paths = (
                [str(DEMO_DATASHEETS / name) for name in sorted(wanted)]
                if wanted
                else [str(p) for p in sorted(DEMO_DATASHEETS.glob("*.pdf"))]
            )
    out: dict[str, DocumentSource] = {}
    for path in paths:
        try:
            document = ingest_document(
                path, register=register, store=store, allow_network=args.allow_network
            )
        except FileNotFoundError:
            continue
        out[Path(str(path)).name] = document
    return out


def _model(args: argparse.Namespace):
    scope = load_scope(args.scope)
    archive = args.etim or _default_etim()
    if archive is None:
        return None, None
    return scope, load_etim(archive, release=args.etim_release, class_ids=scope.as_set)


def _default_etim() -> Path | None:
    if not DEFAULT_ETIM_DIR.exists():
        return None
    extracted = DEFAULT_ETIM_DIR / "extracted"
    if (extracted / "ETIMARTCLASS.csv").exists():
        return extracted
    archives = sorted(p for p in DEFAULT_ETIM_DIR.glob("*.zip") if not p.name.startswith("_"))
    return archives[0] if archives else None


def _load_run(args: argparse.Namespace, *, ledger: Ledger | None = None):
    catalog = _catalog_path(args)
    records = load_catalog(catalog)
    if getattr(args, "limit", 0):
        records = records[: args.limit]
    documents = _documents(args, records)
    scope, etim = (None, None) if getattr(args, "no_documents", False) else _model(args)
    notes = []
    if etim is None and not getattr(args, "no_documents", False):
        notes.append(
            "ETIM was not found, so T1 did not run and this is a T0-only report. Fetch it with "
            "scripts/fetch_reference_data.sh; the model is free (ODC-By) and needs no login."
        )
    return run_catalog(
        catalog,
        documents,
        etim=etim,
        scope=scope,
        attributes=load_attributes(),
        calibration=load_calibration(),
        limit=getattr(args, "limit", 0),
        label=getattr(args, "label", ""),
        ledger=ledger,
        notes=notes,
    )


# ------------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace) -> int:
    ledger = Ledger(args.ledger) if args.ledger else None
    run = _load_run(args, ledger=ledger)

    if args.json:
        print(render_json(run, top=args.top))
    else:
        print(render_text(run, top=args.top, banner=BANNER if _is_demo(args) else ""))

    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(
            render_html(run, top=max(args.top, 25), banner=BANNER if _is_demo(args) else ""),
            encoding="utf-8",
        )
        print(f"\nwrote {args.html}")

    if ledger is not None:
        print(f"batch {run.batch_id} recorded in {args.ledger}")

    return EXIT_FINDINGS if run.findings else EXIT_CLEAN


def _cmd_groundable(args: argparse.Namespace) -> int:
    catalog = _catalog_path(args)
    records = load_catalog(catalog)
    documents = _documents(args, records)
    report = inventory(records, documents, catalog=catalog.name)

    if args.bucket:
        try:
            status = GroundingStatus(args.bucket)
        except ValueError:
            print(
                f"unknown bucket {args.bucket!r}; expected one of "
                f"{', '.join(s.value for s in GroundingStatus)}",
                file=sys.stderr,
            )
            return EXIT_ERROR
        rows = report.records_in(status)
        print(f"{len(rows):,} record(s) in {status.value} -- {status.sentence}")
        for record in rows[:2000]:
            print(f"  row {record.row_number}  {record.sku_id}  {record.named}")
        if len(rows) > 2000:
            print(f"  ... {len(rows) - 2000:,} more")
        return EXIT_CLEAN

    print(json.dumps(report.as_dict(), indent=2) if args.json else report.text())
    return EXIT_CLEAN


def _cmd_clusters(args: argparse.Namespace) -> int:
    run = _load_run(args)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "signature_id": cluster.signature.signature_id,
                        "fingerprint": cluster.signature.fingerprint,
                        "size": cluster.size,
                        "skus": list(cluster.skus[:50]),
                    }
                    for cluster in run.clusters[: args.top]
                ],
                indent=2,
            )
        )
        return EXIT_FINDINGS if run.clusters else EXIT_CLEAN

    print(f"{len(run.clusters):,} error signature(s) over {run.findings:,} finding(s)")
    print("signatures key to document and data artifacts only -- there is no field for a")
    print("supplier, a brand or a company, and a test asserts the absence (FR-8.6).")
    print()
    for cluster in run.clusters[: args.top]:
        print(f"  {cluster.size:8,d}  {cluster.signature.sentence()}")
        print(f"            {cluster.signature.fingerprint}")
        print(f"            e.g. {', '.join(cluster.skus[:4])}")
    return EXIT_FINDINGS if run.clusters else EXIT_CLEAN


def _cmd_queue(args: argparse.Namespace) -> int:
    ledger = Ledger(args.ledger)
    run = _load_run(args)
    review = ReviewQueue(run.triage, ledger=ledger, batch_id=run.batch_id)
    decided, total = review.progress()

    print(f"batch {run.batch_id}")
    print(f"queue {decided:,} decided / {total:,} total  ({(decided / total if total else 0):.1%})")
    print()
    entries = review.open_entries() if args.open_only else run.triage.entries
    for position, entry in enumerate(entries[: args.top], start=1):
        print(f"  [{position}] EV {entry.expected_review_value:,.2f}  ({entry.tier})")
        for line in entry.sentence().splitlines():
            print(f"      {line}")
        print(f"      redline {entry.redline_id}")
        print()
    return EXIT_FINDINGS if entries else EXIT_CLEAN


def _cmd_drain(args: argparse.Namespace) -> int:
    ledger = Ledger(args.ledger)
    run = _load_run(args, ledger=ledger)
    review = ReviewQueue(run.triage, ledger=ledger, batch_id=run.batch_id)

    print(_RULE)
    print("SCRIPTED DECISIONS -- NOT HUMAN REVIEW.")
    print("This command exists to demonstrate FR-8.8 (batch reversal over 1,000 records) and the")
    print("append-only ledger under load. Every decision it writes is attributed to the name you")
    print("passed, is recorded as a scripted drain in its note, and means nothing about whether")
    print("the finding was correct. Reviewer-seconds collected here are not a measurement.")
    print(_RULE)

    safety = [entry for entry in run.triage.entries if entry.requires_two_signatures]
    if safety and not args.second:
        print(
            f"error: {len(safety):,} queue row(s) are safety-class and acceptance needs a second "
            "named adjudicator (FR-8.9). Pass --second, or the drain would stop on the first one.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    state = {"n": 0}

    def decide(entry: QueueEntry):
        state["n"] += 1
        if args.decision == "accept":
            decision = Decision.ACCEPT_REDLINE
        elif args.decision == "keep":
            decision = Decision.KEEP_CATALOG
        else:
            decision = (
                Decision.ACCEPT_REDLINE if state["n"] % 2 else Decision.KEEP_CATALOG
            )
        return (decision, args.by, args.second)

    try:
        report = review.drain(decide, limit=args.count, seconds_to_decision=args.seconds)
    except SecondAdjudicatorRequired as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR

    print()
    print(report.text())
    print(f"batch {run.batch_id}")
    print(f"reverse it with:  errata-scale reverse --batch {run.batch_id} --by <name>")
    return EXIT_CLEAN


def _cmd_reverse(args: argparse.Namespace) -> int:
    ledger = Ledger(args.ledger)
    accepted = accepted_in_batch(ledger, args.batch)
    if args.dry_run:
        print(f"{len(accepted):,} accepted redline(s) would be reversed in batch {args.batch}")
        for item in accepted[:20]:
            print(
                f"  {item.sku_id:24s} {item.attribute_uri:24s} "
                f"{item.decided_value!r} -> {item.catalog_value!r}"
            )
        return EXIT_CLEAN

    report = reverse_batch(ledger, args.batch, reversed_by=args.by, reason=args.reason)
    print(report.text())
    print()
    print(
        "Nothing was deleted. Each reversal is a new claim superseding the accepted one, so the\n"
        "accepted claim stays readable forever -- somebody accepted it on evidence that was\n"
        "accurate at the time, and rewriting that would turn a good decision into a gap."
    )
    return EXIT_CLEAN


def _cmd_chain(args: argparse.Namespace) -> int:
    ledger = Ledger(args.ledger)
    chains = claim_chains(ledger)
    if args.sku:
        chains = {key: chain for key, chain in chains.items() if key[0] == args.sku}
        if not chains:
            print(f"no claims recorded for {args.sku!r} in {args.ledger}")
            return EXIT_NOT_RUN
    for chain in sorted(chains.values(), key=lambda c: (c.sku_id, c.attribute_uri)):
        print(f"  {chain.sentence()}")
    print(f"\n{len(chains):,} chain(s)")
    return EXIT_CLEAN


def _cmd_integrity(args: argparse.Namespace) -> int:
    roots = args.root or [
        REPO_ROOT / name / "src" for name in ("spec", "valuesem", "comparator", "bench", "audit", "scale")
    ]
    findings = scan_for_mutation([root for root in roots if Path(root).exists()])
    if not findings:
        print(
            f"FR-8.2 OK -- no ledger UPDATE or DELETE in any code path across "
            f"{len([r for r in roots if Path(r).exists()])} source root(s)."
        )
        print("A correction is a new claim whose supersedes names the old one; that is what makes")
        print("batch reversal a query rather than a recovery project.")
        return EXIT_CLEAN
    print(f"FR-8.2 VIOLATED -- {len(findings)} ledger-mutating operation(s):", file=sys.stderr)
    for finding in findings:
        print(f"  {finding.sentence()}", file=sys.stderr)
    return EXIT_ERROR


def _cmd_corpus(args: argparse.Namespace) -> int:
    import yaml

    from .corpus import provenance, write_catalog

    if not REAL_CATALOG.exists():
        print(
            f"the R1 demonstration catalog is not at {REAL_CATALOG}; it is the documented stratum "
            "of this corpus and the run is not honest without it.",
            file=sys.stderr,
        )
        return EXIT_NOT_RUN

    real, count, synthetic = write_catalog(
        args.out, real_catalog=REAL_CATALOG, target_total=args.total
    )
    document = provenance(
        real_count=real,
        synthetic=synthetic,
        real_catalog=str(REAL_CATALOG),
        destination=str(args.out),
    )
    args.out.with_name("provenance.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(f"wrote {args.out}")
    print(f"  {real + count:,} rows -- {real:,} documented (S1), {count:,} constructed (S2)")
    print(f"  expected T0 findings {document['expected']['findings']:,}, "
          f"declines {document['expected']['declines']:,}, "
          f"traps {document['expected']['equivalence_traps']:,}")
    print(f"wrote {args.out.with_name('provenance.yaml')}")
    return EXIT_CLEAN


def _cmd_policy() -> int:
    policy = builtin_policy()
    print(f"{policy.version_tag}")
    print(policy.description.strip())
    print("\nsource rank (higher wins; rank beats recency, always)")
    for key, rank in sorted(policy.source_rank.items(), key=lambda kv: -kv[1]):
        print(f"  {rank:4d}  {key}")
    print("\nrules, in the order the engine applies them")
    for rule in policy.rules:
        print(f"  {rule.name:26s} {rule.action}")
        if rule.attributes:
            print(f"      attributes: {', '.join(rule.attributes)}")
        if rule.note:
            print(f"      {' '.join(rule.note.split())}")
    print(
        "\nEvery value this policy resolves records the policy version that resolved it (FR-8.3),"
        "\nand a safety-class attribute is never resolved automatically at any confidence."
    )
    return EXIT_CLEAN


def _cmd_status() -> int:
    print(_RULE)
    print(f"ERRATA R2 -- {SCALE_VERSION}")
    print(_RULE)
    print("what this release does")
    print("  FR-8.1  groundable fraction, computed before any audit, enumerable to record level")
    print("  FR-8.2  append-only ledger with supersedes chains; `integrity` scans every module")
    print("  FR-8.3  the resolution policy is executed, and every resolution records its version")
    print("  FR-8.4  triage router; every ranking factor is carried and printed separately")
    print("  FR-8.5  error signatures clustered from the findings; size is len(members)")
    print("  FR-8.6  no organisation field exists in the signature schema, and a test asserts it")
    print("  FR-8.7  tiers T0 -> T3, with a cost report counting operations that happened")
    print("  FR-8.8  batch reversal as a query over the ledger, demonstrated on 1,000 records")
    print("  FR-8.9  safety-class acceptance is impossible with one signature")
    print()
    print("what it does NOT claim")
    print("  * there is still no calibration set (FR-6.1). Structural findings carry no")
    print("    probability and are ranked on blast radius alone; every queue row says so.")
    print("  * the demonstration catalog is CONSTRUCTED. R2's exit criterion asks for a public")
    print("    10k+ catalog and no such catalog with retrievable source documents was reachable;")
    print("    see docs/R2-report.md. Scale and the drainable queue are demonstrated; the")
    print("    'public' half of the criterion is open.")
    print("  * revenue weight and propagation count are customer configuration and are unset,")
    print("    so the queue shows them as stated defaults rather than as measurements.")
    print("  * Errata grades. It never enriches and it never writes to a customer PIM (ADR-001).")
    return EXIT_CLEAN


def _is_demo(args: argparse.Namespace) -> bool:
    return Path(args.catalog).resolve() == DEFAULT_CATALOG.resolve()


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


if __name__ == "__main__":
    raise SystemExit(main())
