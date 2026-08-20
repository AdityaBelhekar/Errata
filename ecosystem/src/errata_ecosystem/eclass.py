"""FR-9.8 / ADR-003 -- ECLASS by the customer's licence, and the scanner that proves we kept none.

ETIM is free under ODC-By. ECLASS is licensed -- per release, per concordance, per IRDI, or by
membership priced on company size. ADR-003 chose option B: *no ECLASS content in the repository,
the container image, or the benchmark set*, and support ships as an adapter that reads the
**customer's own licensed files at runtime**.

Two halves, and the second is the one that can actually be verified by a stranger:

**The adapter** (:class:`EclassAdapter`) loads a dictionary from a path the customer supplies, or
from ``ERRATA_ECLASS_DICTIONARY``. It holds the content in memory, refuses to write any of it
inside the repository, and refuses to load a file that does not look like an ECLASS export rather
than accepting whatever it was handed. The shape it reads is the ECLASS basic CSV export: one row
per property, keyed by IRDI.

**The scanner** (:func:`scan`) walks a tree and reports any file containing ECLASS *content* --
matched on the IRDI form ``0173-1#xx-XXXNNN#NNN``, which is what an ECLASS identifier looks like
and what would actually be a licence breach. It deliberately does **not** flag the word "ECLASS":
this repository discusses ECLASS at length in ADR-003 and in the phase documents, and a scanner
that fired on the word would either be switched off or would push the discussion out of the
documents. What it flags is a licensed identifier, which is the thing the licence covers.

The scanner runs over the working tree and over built distributions, because "the repository is
clean" and "the wheel is clean" are different claims and FR-9.8 makes the second one.
"""

from __future__ import annotations

import csv
import os
import re
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ECLASS_ENV_VAR",
    "ECLASS_IRDI",
    "EclassAdapter",
    "EclassContentFound",
    "EclassProperty",
    "ScanFinding",
    "ScanReport",
    "assert_clean",
    "scan",
    "scan_distribution",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
ECLASS_ENV_VAR = "ERRATA_ECLASS_DICTIONARY"

#: An ECLASS IRDI: ICD 0173, ``-1`` for the ECLASS registry, a two-digit object type, a
#: six-character code, and a version. Matching the identifier rather than the word is what makes
#: this scanner both strict about content and quiet about discussion.
ECLASS_IRDI = re.compile(r"\b0173-1#\d{2}-[A-Z]{3}\d{3}#\d{3}\b")

#: Directories the scanner never descends into: generated, vendored or the customer's own runtime
#: area. ``var/`` is explicitly excluded and explicitly NOT a loophole -- it is gitignored, it is
#: where a customer's licensed export would legitimately be mounted at runtime, and shipping it is
#: impossible because it is not in any distribution. :func:`scan_distribution` is the check that
#: matters for what leaves the building.
SKIP_DIRECTORIES = frozenset({".git", ".venv", "var", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "dist", "build"})

_TEXT_SUFFIXES = frozenset(
    {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".csv", ".tsv", ".toml", ".cfg", ".ini", ".html", ".sh", ".jsonl"}
)


class EclassContentFound(AssertionError):
    """Licensed content is in a place it must never be. An assertion: the build should stop."""


@dataclass(frozen=True, slots=True)
class EclassProperty:
    """One property of the customer's dictionary. Held in memory; never written down by us."""

    irdi: str
    preferred_name: str
    definition: str = ""
    unit: str = ""
    data_type: str = ""

    @property
    def uri(self) -> str:
        return f"eclass:{self.irdi}"


@dataclass(frozen=True, slots=True)
class EclassAdapter:
    """The customer's dictionary, loaded at runtime from the customer's licensed file.

    ``source`` is kept so a report can say *which* file a mapping came from without reproducing
    anything out of it. Nothing in this object is ever serialised by Errata: the one method that
    could -- :meth:`describe` -- emits counts and the source path, never a name or a definition.
    """

    source: Path
    release: str
    properties: tuple[EclassProperty, ...]

    def __len__(self) -> int:
        return len(self.properties)

    def get(self, irdi: str) -> EclassProperty | None:
        return next((p for p in self.properties if p.irdi == irdi), None)

    def describe(self) -> str:
        return (
            f"ECLASS dictionary loaded from {self.source} at runtime: {len(self.properties)} "
            f"properties, release {self.release or 'unstated'}. Content is the customer's under "
            "their licence; Errata holds it in memory for this process and writes none of it."
        )

    @classmethod
    def from_path(cls, path: Path | str, *, release: str = "") -> EclassAdapter:
        """Load an ECLASS basic CSV export.

        Refuses a file with no IRDI column rather than loading zero properties and reporting an
        empty dictionary: "your licence file is the wrong export" and "your dictionary is empty"
        are different problems and only one of them is the customer's.
        """
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(
                f"no ECLASS dictionary at {source}. Errata ships none: set {ECLASS_ENV_VAR} or "
                "pass the path to your own licensed export (ADR-003)."
            )
        if _inside_repository(source):
            raise EclassContentFound(
                f"{source} is inside the Errata repository. A licensed dictionary must live "
                "outside it -- ADR-003 forbids ECLASS content in the repository, and loading it "
                "from there is how it gets committed by accident."
            )

        rows: list[EclassProperty] = []
        with source.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=_sniff_delimiter(source))
            columns = {(c or "").strip().lower(): c for c in (reader.fieldnames or [])}
            irdi_column = next(
                (columns[c] for c in columns if "irdi" in c or c in {"id", "identifier"}), None
            )
            if irdi_column is None:
                raise ValueError(
                    f"{source} has no IRDI column (columns: {list(columns)}). This is not an "
                    "ECLASS property export; Errata will not guess which column identifies a "
                    "property."
                )
            name_column = next(
                (columns[c] for c in columns if "preferred" in c or "name" in c), None
            )
            definition_column = next((columns[c] for c in columns if "definition" in c), None)
            unit_column = next((columns[c] for c in columns if "unit" in c), None)
            type_column = next((columns[c] for c in columns if "type" in c), None)

            for row in reader:
                irdi = (row.get(irdi_column) or "").strip()
                if not irdi:
                    continue
                rows.append(
                    EclassProperty(
                        irdi=irdi,
                        preferred_name=(row.get(name_column) or "").strip() if name_column else "",
                        definition=(
                            (row.get(definition_column) or "").strip() if definition_column else ""
                        ),
                        unit=(row.get(unit_column) or "").strip() if unit_column else "",
                        data_type=(row.get(type_column) or "").strip() if type_column else "",
                    )
                )
        return cls(source=source, release=release, properties=tuple(rows))

    @classmethod
    def from_environment(cls, *, release: str = "") -> EclassAdapter | None:
        """The deployment path: a mounted licence file named by an environment variable.

        Returns ``None`` when unset -- an absent ECLASS dictionary is the normal state of every
        installation that has not bought one, not an error.
        """
        configured = os.environ.get(ECLASS_ENV_VAR, "").strip()
        if not configured:
            return None
        return cls.from_path(configured, release=release)


def _sniff_delimiter(path: Path) -> str:
    head = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    return ";" if head.count(";") > head.count(",") else ","


def _inside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class ScanFinding:
    path: str
    line: int
    sample: str


@dataclass(frozen=True, slots=True)
class ScanReport:
    root: str
    files_scanned: int
    findings: tuple[ScanFinding, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        return not self.findings

    def text(self) -> str:
        head = (
            f"FR-9.8 / ADR-003 -- ECLASS content scan of {self.root}: "
            f"{self.files_scanned} files, {len(self.findings)} finding(s)"
        )
        if self.clean:
            return head + "\n  CLEAN -- no ECLASS identifier appears in any scanned file."
        lines = [head]
        for finding in self.findings:
            lines.append(f"  {finding.path}:{finding.line}  {finding.sample}")
        return "\n".join(lines)


def _walk(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        yield path


def scan(root: Path | str | None = None) -> ScanReport:
    """Walk a tree and report every ECLASS identifier in it."""
    base = Path(root) if root is not None else REPO_ROOT
    findings: list[ScanFinding] = []
    scanned = 0
    for path in _walk(base):
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            match = ECLASS_IRDI.search(line)
            if match:
                findings.append(
                    ScanFinding(
                        path=str(path.relative_to(base)).replace("\\", "/"),
                        line=number,
                        sample=match.group(0),
                    )
                )
    return ScanReport(root=str(base), files_scanned=scanned, findings=tuple(findings))


def scan_distribution(archive: Path | str) -> ScanReport:
    """The check FR-9.8 actually makes: *inspect the build artifact*.

    A clean working tree says nothing about what ``python -m build`` put in the wheel -- package
    data globs are exactly the mechanism by which a file nobody meant to ship gets shipped.
    """
    path = Path(archive)
    findings: list[ScanFinding] = []
    scanned = 0
    with zipfile.ZipFile(path) as bundle:
        for member in bundle.namelist():
            if member.endswith("/"):
                continue
            scanned += 1
            with bundle.open(member) as handle:
                try:
                    text = handle.read().decode("utf-8")
                except UnicodeDecodeError:
                    continue
            for number, line in enumerate(text.splitlines(), start=1):
                match = ECLASS_IRDI.search(line)
                if match:
                    findings.append(
                        ScanFinding(path=f"{path.name}!{member}", line=number, sample=match.group(0))
                    )
    return ScanReport(root=str(path), files_scanned=scanned, findings=tuple(findings))


def assert_clean(reports: Sequence[ScanReport]) -> None:
    """Raise unless every report is clean. What CI calls."""
    dirty = [r for r in reports if not r.clean]
    if dirty:
        detail = "\n".join(r.text() for r in dirty)
        raise EclassContentFound(
            "FR-9.8 / ADR-003 violated -- licensed ECLASS content is present:\n" + detail
        )
