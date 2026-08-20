"""FR-9.6 -- the frozen hard-tail split, and the guard that fails the build if tuning touches it.

A held-out split is a promise, and a promise with no mechanism behind it is how every benchmark
ends up quietly overfitted. So the split is three things at once:

1. **A list of record ids**, frozen in ``data/gold/splits/hard-tail.json`` and hashed into the
   gold manifest. Changing which records are in it changes the hash and fails the load.
2. **A declaration obligation.** Anything that tunes -- a threshold sweep, a fitted calibrator, a
   prompt chosen by looking at outcomes -- writes a :class:`TuningRun` naming the records it read.
3. **A guard**, :func:`assert_untouched`, that fails when a declared tuning run intersects the
   split. CI runs it over the whole tuning ledger.

**The obvious objection is right, and worth writing down.** A declaration is only as honest as the
code that writes it: nothing here can stop someone reading the hard tail in a notebook and never
declaring it. What the mechanism does buy is that the *repository's own* tuning paths cannot touch
the split without either declaring it -- and failing -- or removing the declaration, which is a
visible edit to a file whose whole subject is honesty. That is the same bargain as an append-only
ledger, and it is worth the same amount: it converts a silent drift into a deliberate act.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "DEFAULT_TUNING_LEDGER",
    "SPLITS_DIR",
    "FrozenSplit",
    "HardTailTouched",
    "TuningRun",
    "assert_untouched",
    "load_split",
    "load_tuning_runs",
    "record_tuning_run",
    "split_integrity",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
SPLITS_DIR = REPO_ROOT / "data" / "gold" / "splits"
GOLD_MANIFEST = REPO_ROOT / "data" / "gold" / "manifest.json"
DEFAULT_TUNING_LEDGER = REPO_ROOT / "var" / "r3" / "tuning.jsonl"


class HardTailTouched(AssertionError):
    """A tuning run read records from a frozen split. Deliberately an ``AssertionError``.

    The distinction matters: this is not a bad input the caller should handle, it is a violated
    invariant of the benchmark, and the correct response is for the build to stop.
    """


@dataclass(frozen=True, slots=True)
class FrozenSplit:
    name: str
    criterion: str
    frozen_utc: str
    record_ids: frozenset[str]
    of_total: int
    sha256: str
    unrepresented: tuple[dict, ...] = field(default_factory=tuple)
    gaps: tuple[dict, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        return len(self.record_ids)

    def contains_any(self, record_ids: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted(set(record_ids) & self.record_ids))

    def held_out(self, record_ids: Iterable[str]) -> tuple[str, ...]:
        """``record_ids`` with the split removed -- what a tuning run is allowed to read."""
        return tuple(r for r in record_ids if r not in self.record_ids)

    @property
    def coverage(self) -> float:
        return len(self.record_ids) / self.of_total if self.of_total else 0.0

    def text(self) -> str:
        lines = [
            f"frozen split '{self.name}' -- {len(self)} of {self.of_total} records "
            f"({self.coverage:.2%}), frozen {self.frozen_utc}",
            f"  criterion: {self.criterion}",
            f"  sha256:    {self.sha256}",
        ]
        absent = [c for c in self.unrepresented if not c.get("present")]
        if absent:
            lines.append(
                "  NOT REPRESENTED in this corpus, and named rather than implied: "
                + ", ".join(c["category"] for c in absent)
            )
        for gap in self.gaps:
            lines.append(f"  gap: {gap['document']} contributes {gap['records']} records")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class TuningRun:
    """A declaration: this run tuned something, and these are the records it was allowed to see."""

    run_id: str
    purpose: str
    record_ids: tuple[str, ...]
    recorded_utc: str = ""

    def as_json(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "purpose": self.purpose,
                "record_ids": list(self.record_ids),
                "recorded_utc": self.recorded_utc
                or datetime.now(UTC).isoformat(timespec="seconds"),
            },
            sort_keys=True,
        )


def load_split(name: str = "hard-tail", *, splits_dir: Path | str | None = None) -> FrozenSplit:
    """Load a frozen split and check it against the hash the gold manifest recorded."""
    directory = Path(splits_dir) if splits_dir is not None else SPLITS_DIR
    path = directory / f"{name}.json"
    body = path.read_bytes()
    actual = hashlib.sha256(body).hexdigest()

    recorded = _recorded_hash(name)
    if recorded is not None and recorded != actual:
        raise ValueError(
            f"split {name!r} hashes to {actual} but the gold manifest records {recorded}. "
            "A frozen split whose contents moved is not frozen: find out what changed it, and do "
            "not reconcile by editing the manifest (FR-9.6)."
        )

    doc = json.loads(body.decode("utf-8"))
    return FrozenSplit(
        name=str(doc.get("split", name)),
        criterion=str(doc.get("criterion", "")),
        frozen_utc=str(doc.get("frozen_utc", "")),
        record_ids=frozenset(doc.get("record_ids", ())),
        of_total=int(doc.get("of_total", 0)),
        sha256=actual,
        unrepresented=tuple(doc.get("unrepresented_categories", ())),
        gaps=tuple(doc.get("gold_set_gaps", ())),
    )


def _recorded_hash(name: str) -> str | None:
    if not GOLD_MANIFEST.exists():  # pragma: no cover - the manifest is committed
        return None
    doc = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))
    for entry in doc.get("splits", []):
        if entry.get("split") == name:
            return entry.get("sha256")
    return None


def split_integrity(name: str = "hard-tail") -> tuple[bool, str]:
    """``(ok, sentence)`` -- for a CLI that wants to report rather than raise."""
    try:
        split = load_split(name)
    except (OSError, ValueError) as exc:
        return False, str(exc)
    return True, f"split {name!r} intact at {split.sha256[:12]}, {len(split)} records"


def record_tuning_run(
    run: TuningRun,
    *,
    ledger: Path | str | None = None,
    split: FrozenSplit | None = None,
) -> Path:
    """Append a tuning declaration, **after** checking it against the frozen split.

    Checking before writing is deliberate: a violating run must not be able to leave a record
    saying it happened and continue anyway. The exception is the mechanism.
    """
    split = split if split is not None else load_split()
    assert_untouched(split, [run])

    path = Path(ledger) if ledger is not None else DEFAULT_TUNING_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(run.as_json() + "\n")
    return path


def load_tuning_runs(ledger: Path | str | None = None) -> tuple[TuningRun, ...]:
    path = Path(ledger) if ledger is not None else DEFAULT_TUNING_LEDGER
    if not path.exists():
        return ()
    runs: list[TuningRun] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        runs.append(
            TuningRun(
                run_id=str(row.get("run_id", "")),
                purpose=str(row.get("purpose", "")),
                record_ids=tuple(row.get("record_ids", ())),
                recorded_utc=str(row.get("recorded_utc", "")),
            )
        )
    return tuple(runs)


def assert_untouched(split: FrozenSplit, runs: Sequence[TuningRun]) -> None:
    """Raise if any declared tuning run read a record from the frozen split."""
    violations: list[str] = []
    for run in runs:
        overlap = split.contains_any(run.record_ids)
        if overlap:
            shown = ", ".join(overlap[:3])
            more = f" (+{len(overlap) - 3} more)" if len(overlap) > 3 else ""
            violations.append(
                f"tuning run {run.run_id!r} ({run.purpose}) read {len(overlap)} record(s) from "
                f"the frozen '{split.name}' split: {shown}{more}"
            )
    if violations:
        raise HardTailTouched(
            "FR-9.6 violated -- the hard tail is held out, not held back:\n  "
            + "\n  ".join(violations)
        )
