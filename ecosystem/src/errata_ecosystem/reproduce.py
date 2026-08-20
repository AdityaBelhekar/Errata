"""The R3 exit criterion: *a third party reproduces our published scores from the repository*.

This module is the half of that sentence we can build. It runs every axis, checks each headline
against the number this repository publishes, hashes every input the numbers depend on, and prints
a receipt that says REPRODUCED, DIVERGED or INCOMPLETE.

**What it cannot do is be the third party.** A reproduction package that certifies itself has
reproduced nothing, so :data:`THIRD_PARTY_ATTESTATIONS` is an empty list and stays empty until
somebody outside this repository runs the command and sends back a receipt. The exit criterion is
therefore reported as **half met**, in the same shape R2 reported the public-catalog half of its
own: the machinery is done and measured, the external act has not happened, and neither fact is
allowed to stand in for the other.

**Why the expected values are pinned in code rather than read from a report.** A reproduction check
that compared this run against the last run would pass forever -- including through the change that
broke the number. The values below were measured on 2026-08-20 and written down; a change that
moves them fails here and has to be explained, which is the entire point.
"""

from __future__ import annotations

import enum
import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .axes import AxisResult, AxisStatus, run_all
from .goldset import VerificationLevel, load_gold_set, verify
from .leaderboard import leaderboard, render_text
from .reviewer import load_sessions
from .reviewer import report as reviewer_report
from .splits import load_split

__all__ = [
    "PUBLISHED",
    "THIRD_PARTY_ATTESTATIONS",
    "Check",
    "ReproductionReceipt",
    "Verdict",
    "reproduce",
]

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Every headline number this repository publishes for R3, as measured on 2026-08-20 on the
#: reference inputs. Each entry is (path into the axis result, expected value).
#:
#: These are exact-match comparisons on strings, not tolerance comparisons on floats. The metric
#: is deterministic given the same inputs and the same code -- NFR-1 requires exactly that -- so a
#: tolerance would only serve to absorb a real change quietly.
PUBLISHED: dict[str, dict[str, Any]] = {
    "grounding": {
        "word_grounding_f1": "46.34%",
        "page_grounding_f1": "67.15%",
        "value_f1": "67.15%",
        "conservative_word_f1": "43.72%",
        "n": 1426,
    },
    "class_assignment": {"top_1": "47.06%", "top_5": "100.00%", "must_abstain_held": "7/7", "n": 17},
    "compound_values": {"correct": "14/20", "false_positives": 2, "unexpected_abstentions": 4},
    "crosswalk": {
        "codes_with_attribute_layer": 2,
        "unmapped_codes_abstained": "3/3",
        "declined_mappings": 1,
        "no_match_recorded": 2,
    },
    "supersession": {"n": 5},
    "abstention": {"aurc": 0.337, "n": 1426},
}

#: FR-9.5's other half, pinned: the gold set's own shape.
PUBLISHED_GOLD = {
    "records": 1426,
    "grounded": 1426,
    "hard_tail": 275,
    "hard_tail_sha256": "99216acbd108dc72cecce4c9b470fc4356fb0d9980aeb58c2b9f1dd1cf893cd8",
}

#: Receipts from people who are not us. Empty, and the exit criterion is open until it is not.
THIRD_PARTY_ATTESTATIONS: tuple[dict[str, str], ...] = ()


class Verdict(str, enum.Enum):
    REPRODUCED = "REPRODUCED"
    DIVERGED = "DIVERGED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    expected: Any
    actual: Any

    @property
    def ok(self) -> bool:
        return self.expected == self.actual

    def line(self) -> str:
        mark = "ok  " if self.ok else "FAIL"
        detail = "" if self.ok else f"   (expected {self.expected!r}, got {self.actual!r})"
        return f"  [{mark}] {self.name:<48} {self.actual}{detail}"


@dataclass(frozen=True, slots=True)
class ReproductionReceipt:
    verdict: Verdict
    checks: tuple[Check, ...]
    axes: tuple[AxisResult, ...]
    inputs: dict[str, str]
    environment: dict[str, str]
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.ok)

    def text(self) -> str:
        lines = [
            "ERRATA R3 -- REPRODUCTION RECEIPT",
            "=" * 96,
            f"verdict: {self.verdict.value}   ({len(self.checks) - len(self.failures)} of "
            f"{len(self.checks)} checks match the published values)",
            "",
            "CHECKS",
            "-" * 96,
        ]
        lines += [check.line() for check in self.checks]
        lines += ["", "INPUTS THESE NUMBERS DEPEND ON", "-" * 96]
        lines += [f"  {k:<34} {v}" for k, v in sorted(self.inputs.items())]
        lines += ["", "ENVIRONMENT", "-" * 96]
        lines += [f"  {k:<34} {v}" for k, v in sorted(self.environment.items())]
        lines += ["", "THE HALF THIS COMMAND CANNOT DO", "-" * 96]
        if THIRD_PARTY_ATTESTATIONS:  # pragma: no cover - none exist yet
            for attestation in THIRD_PARTY_ATTESTATIONS:
                lines.append(f"  {attestation}")
        else:
            lines.append(
                "  NO THIRD PARTY HAS RUN THIS. The R3 exit criterion is 'a third party "
                "reproduces our published scores from the repo'; this receipt is the first half "
                "of that sentence and cannot be the second. The criterion stays OPEN."
            )
        for note in self.notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "checks": [
                {"name": c.name, "expected": c.expected, "actual": c.actual, "ok": c.ok}
                for c in self.checks
            ],
            "inputs": self.inputs,
            "environment": self.environment,
            "third_party_attestations": list(THIRD_PARTY_ATTESTATIONS),
            "axes": [a.as_dict() for a in self.axes],
            "notes": list(self.notes),
        }


def _sha256(path: Path) -> str:
    if not path.exists():
        return "ABSENT"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    out: dict[str, str] = {}
    for name in (
        "errata-valuesem",
        "errata-spec",
        "errata-comparator",
        "errata-bench",
        "errata-audit",
        "errata-scale",
        "errata-ecosystem",
        "pymupdf",
        "pint",
        "lark",
    ):
        try:
            out[name] = version(name)
        except PackageNotFoundError:  # pragma: no cover - depends on the install
            out[name] = "not installed"
    return out


def reproduce(*, corpus: Path | str | None = None) -> ReproductionReceipt:
    """Run everything, compare to the published values, and return the receipt."""
    axes = run_all(corpus=corpus)
    by_id = {a.axis: a for a in axes}
    checks: list[Check] = []
    notes: list[str] = []

    incomplete = [a.axis for a in axes if a.status is AxisStatus.NOT_MEASURED]

    for axis_id, expectations in PUBLISHED.items():
        result = by_id.get(axis_id)
        if result is None or result.status is AxisStatus.NOT_MEASURED:
            checks.append(Check(f"{axis_id}: axis measured", True, False))
            continue
        for key, expected in expectations.items():
            actual = result.n if key == "n" else result.metrics.get(key)
            checks.append(Check(f"{axis_id}.{key}", expected, actual))

    # FR-9.5 / FR-9.6 -- the gold set and the frozen split are inputs to every number above.
    try:
        gold = load_gold_set()
        verification = verify(gold)
        checks.append(Check("gold.records", PUBLISHED_GOLD["records"], len(gold)))
        checks.append(
            Check(
                "gold.verification_level",
                VerificationLevel.GROUNDED.value,
                verification.level.value,
            )
        )
        checks.append(
            Check("gold.grounded_records", PUBLISHED_GOLD["grounded"], verification.grounded_records)
        )
        if verification.level is not VerificationLevel.GROUNDED:
            notes.append(
                "the gold set was not verified against the documents -- run "
                "scripts/fetch_reference_data.sh, then re-run"
            )
    except (OSError, ValueError) as exc:
        checks.append(Check("gold.loads", True, f"failed: {exc}"))

    try:
        split = load_split()
        checks.append(Check("split.hard_tail.records", PUBLISHED_GOLD["hard_tail"], len(split)))
        checks.append(
            Check("split.hard_tail.sha256", PUBLISHED_GOLD["hard_tail_sha256"], split.sha256)
        )
    except (OSError, ValueError) as exc:
        checks.append(Check("split.loads", True, f"failed: {exc}"))

    failures = [c for c in checks if not c.ok]
    if incomplete:
        verdict = Verdict.INCOMPLETE
        notes.append(
            "axes without data on this machine: "
            + ", ".join(incomplete)
            + " -- fetch the reference data before reading the verdict"
        )
    elif failures:
        verdict = Verdict.DIVERGED
    else:
        verdict = Verdict.REPRODUCED

    inputs = {
        "corpus": _sha256(Path(corpus) if corpus else REPO_ROOT / "var" / "spike" / "corpus.yaml"),
        "gold_annotations": _sha256(
            REPO_ROOT / "data" / "gold" / "annotations" / "abb-s200-2CDC002142D0207.jsonl"
        ),
        "gold_manifest": _sha256(REPO_ROOT / "data" / "gold" / "manifest.json"),
        "hard_tail_split": _sha256(REPO_ROOT / "data" / "gold" / "splits" / "hard-tail.json"),
        "bridge": _sha256(
            REPO_ROOT / "ecosystem" / "src" / "errata_ecosystem" / "data" / "etim-unspsc-bridge.yaml"
        ),
        "unspsc_codeset": _sha256(REPO_ROOT / "var" / "reference" / "unspsc" / "ok-unspsc-codes.csv"),
        "reference_manifest": _sha256(REPO_ROOT / "data" / "reference" / "manifest.json"),
    }

    environment = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        **_versions(),
    }

    return ReproductionReceipt(
        verdict=verdict,
        checks=tuple(checks),
        axes=axes,
        inputs=inputs,
        environment=environment,
        notes=tuple(notes),
    )


def full_report(*, corpus: Path | str | None = None) -> str:
    """The receipt and the leaderboard, in the order a reader needs them."""
    receipt = reproduce(corpus=corpus)
    board = leaderboard(receipt.axes, reviewer_report(load_sessions()))
    return receipt.text() + "\n\n" + render_text(board)


def write_json(receipt: ReproductionReceipt, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(receipt.as_dict(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return target
