"""The R2 demonstration catalog: 10,000+ records, and an exact account of what is real in them.

**Read this before quoting any number this corpus produces.**

R2's exit criterion asks for a full audit of a 10k+ SKU *public* catalog subset. No public
industrial catalog of that size, carrying technical attributes and pointing at retrievable source
documents, was reachable -- the same negative result D-1 recorded for ETIM class distributions, hit
again from a different direction and written up in ``docs/R2-report.md``. Rather than quietly
relabel a constructed corpus as a public one, this module builds the corpus, states exactly which
half of the criterion it satisfies, and leaves the other half open.

What is real:

| | Real | Constructed |
|---|---|---|
| the ABB S200 datasheet | hash-registered, ABB's own | |
| the values Errata re-derives from it, and their spans | | |
| the S1 rows' identities and reference values | derived from that datasheet by the R1 generator | |
| the value *pool* the S2 rows draw from | the IEC preferred current series and the datasheet's own weights and packing units | |
| **the S2 rows' identities, and the defects in them** | | **built here** |

So: **grounding is empirical, detection at T1 is measured against a population we created, and
detection at T0 is measured against defects we injected on purpose.** That is a normal way to
demonstrate recall -- you cannot measure recall against errors you cannot enumerate -- and it is
stated on every report rather than in a footnote.

**Mutation is by content hash, never by a seeded RNG.** ``sha256(family key) % 100`` decides each
family's kind, so the corpus is reproducible from the SKU list alone, in any Python, in any
iteration order, forever. A seeded RNG would tie the corpus to a call order, and the day this file
is refactored every row's expected outcome would move silently.

**Every synthetic manufacturer is named ``SYN-MFR-nn``.** Not a plausible-sounding company: a
plausible name in a defect corpus is one copy-paste away from being a defamatory claim about a real
one, which is the failure FR-8.6 exists to prevent.
"""

from __future__ import annotations

import csv
import enum
import hashlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CORPUS_VERSION",
    "FamilyKind",
    "SyntheticRow",
    "build_rows",
    "expected_counts",
    "family_kind",
    "provenance",
    "write_catalog",
]

CORPUS_VERSION = "errata-scale-corpus/1.0.0"

#: The IEC preferred series, as printed in the ABB S200 ordering tables the R1 corpus was read
#: from. Real values; the products carrying them here are not.
CURRENTS: tuple[str, ...] = ("6", "10", "13", "16", "20", "25", "32", "40", "50", "63")

#: Weights and packing units as the same tables state them, by pole count.
WEIGHTS: dict[int, str] = {1: "0.125", 2: "0.250", 3: "0.375", 4: "0.500"}
PACKING: dict[int, str] = {1: "10", 2: "10", 3: "12", 4: "12"}

#: Deliberately not company names. See the module docstring.
MANUFACTURERS: tuple[str, ...] = tuple(f"SYN-MFR-{n:02d}" for n in range(1, 9))

DESCRIPTION = "Miniature circuit breaker"

COLUMNS: tuple[str, ...] = (
    "sku",
    "mpn",
    "manufacturer",
    "description",
    "datasheet",
    "rated_current",
    "poles",
    "packaging_uom",
    "weight_kg",
    "order_code",
)


class FamilyKind(str, enum.Enum):
    """What a family of rows sharing one part number is for.

    Each kind names the outcome a competent reviewer should reach, because that is the ground truth
    the corpus is measured against and it must not be inferrable only from the code.
    """

    CONSISTENT_PAIR = "consistent_pair"
    """Two rows, identical. The audit should stay silent."""

    CONTRADICTION_TRIPLE = "contradiction_triple"
    """Three rows; one states a transposed current. A real defect, SEV-1, safety class."""

    EQUAL_RANK_PAIR = "equal_rank_pair"
    """Two rows disagreeing with no majority. The policy must abstain, not pick one."""

    FILL_GAP_TRIPLE = "fill_gap_triple"
    """Three rows; one leaves the packing unit blank. A fill-rate defect, SEV-2."""

    UNIT_FRAME_PAIR = "unit_frame_pair"
    """Two rows stating the same weight in kg and in g. **Must not be flagged** -- FR-5.3."""

    VOCABULARY_PAIR = "vocabulary_pair"
    """Two rows stating the pole count as ``1`` and ``1P``. **Must not be flagged** -- FR-5.3."""

    DIMENSION_SINGLE = "dimension_single"
    """One row whose rated current is stated as a mass. A defect no document is needed to see."""

    CLEAN_SINGLE = "clean_single"
    """One row, nothing wrong with it, nothing to compare it to."""

    @property
    def rows(self) -> int:
        return {
            FamilyKind.CONSISTENT_PAIR: 2,
            FamilyKind.CONTRADICTION_TRIPLE: 3,
            FamilyKind.EQUAL_RANK_PAIR: 2,
            FamilyKind.FILL_GAP_TRIPLE: 3,
            FamilyKind.UNIT_FRAME_PAIR: 2,
            FamilyKind.VOCABULARY_PAIR: 2,
            FamilyKind.DIMENSION_SINGLE: 1,
            FamilyKind.CLEAN_SINGLE: 1,
        }[self]

    @property
    def expected_findings(self) -> int:
        return {
            FamilyKind.CONTRADICTION_TRIPLE: 1,
            FamilyKind.FILL_GAP_TRIPLE: 1,
            FamilyKind.DIMENSION_SINGLE: 1,
        }.get(self, 0)

    @property
    def expected_declines(self) -> int:
        return 2 if self is FamilyKind.EQUAL_RANK_PAIR else 0

    @property
    def is_trap(self) -> bool:
        """A family whose rows differ on the page and agree in fact.

        A detection corpus with no traps reports a precision that has never been tested.
        """
        return self in {FamilyKind.UNIT_FRAME_PAIR, FamilyKind.VOCABULARY_PAIR}

    @property
    def expectation(self) -> str:
        return {
            FamilyKind.CONSISTENT_PAIR: "identical rows; the audit should stay silent",
            FamilyKind.CONTRADICTION_TRIPLE: (
                "one row states a transposed rated current; SEV-1, safety class, two signatures"
            ),
            FamilyKind.EQUAL_RANK_PAIR: (
                "two rows disagree with no majority; both must be surfaced as "
                "equal_rank_source_conflict and neither may be chosen"
            ),
            FamilyKind.FILL_GAP_TRIPLE: (
                "one row is blank where its siblings state a packing unit; SEV-2 fill-rate defect"
            ),
            FamilyKind.UNIT_FRAME_PAIR: (
                "the same weight in kg and in g -- a unit-frame difference, NOT a defect. "
                "Flagging this is the false positive that ends a pilot"
            ),
            FamilyKind.VOCABULARY_PAIR: (
                "the same pole count written 1 and 1P -- a vocabulary difference, NOT a defect"
            ),
            FamilyKind.DIMENSION_SINGLE: (
                "the rated current is stated as a mass; wrong without opening any document"
            ),
            FamilyKind.CLEAN_SINGLE: "a single correct row with no sibling to compare against",
        }[self]


#: Content-hash buckets, in order. The boundaries are the corpus design and they are written here
#: rather than computed, so a change to the mix is a visible diff.
_BUCKETS: tuple[tuple[int, FamilyKind], ...] = (
    (40, FamilyKind.CONSISTENT_PAIR),
    (55, FamilyKind.CONTRADICTION_TRIPLE),
    (65, FamilyKind.EQUAL_RANK_PAIR),
    (75, FamilyKind.FILL_GAP_TRIPLE),
    (85, FamilyKind.UNIT_FRAME_PAIR),
    (90, FamilyKind.VOCABULARY_PAIR),
    (95, FamilyKind.DIMENSION_SINGLE),
    (100, FamilyKind.CLEAN_SINGLE),
)


def _bucket(key: str) -> int:
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % 100


def family_kind(family: str) -> FamilyKind:
    """Which kind a family is, decided by the hash of its own name.

    Reproducible from the family name alone -- no state, no counter, no RNG.
    """
    bucket = _bucket(family)
    for edge, kind in _BUCKETS:
        if bucket < edge:
            return kind
    return FamilyKind.CLEAN_SINGLE  # pragma: no cover - _BUCKETS ends at 100


@dataclass(frozen=True, slots=True)
class SyntheticRow:
    """One constructed catalog row, with the reason it exists attached."""

    sku: str
    mpn: str
    manufacturer: str
    rated_current: str
    poles: str
    packaging_uom: str
    weight_kg: str
    order_code: str
    family: str
    kind: FamilyKind
    role: str
    """``modal``, ``minority``, ``blank``, ``trap`` or ``only`` -- what this row is *for*."""

    def as_row(self) -> dict[str, str]:
        return {
            "sku": self.sku,
            "mpn": self.mpn,
            "manufacturer": self.manufacturer,
            "description": DESCRIPTION,
            "datasheet": "",
            "rated_current": self.rated_current,
            "poles": self.poles,
            "packaging_uom": self.packaging_uom,
            "weight_kg": self.weight_kg,
            "order_code": self.order_code,
        }


def _family_values(family: str) -> tuple[str, int, str, str, str]:
    """The correct values for a family, drawn deterministically from the real value pool."""
    bucket = _bucket(family + "|values")
    current = CURRENTS[bucket % len(CURRENTS)]
    poles = (bucket // len(CURRENTS)) % 4 + 1
    return (
        f"{current} A",
        poles,
        f"{PACKING[poles]} pcs",
        f"{WEIGHTS[poles]} kg",
        f"SYN{bucket:02d}{current.zfill(2)}{poles}",
    )


def _transpose(current: str) -> str:
    """Swap the digits of a two-digit current; pad a one-digit one first.

    The same defect shape the R1 corpus injects, so the two releases' clusters are comparable:
    ``16 A`` becomes ``61 A``, and ``6 A`` becomes ``60 A``.
    """
    digits = current.split()[0]
    if len(digits) == 1:
        return f"{digits}0 A"
    return f"{digits[::-1].lstrip('0') or '0'} A"


def _rows_for(index: int) -> list[SyntheticRow]:
    family = f"SYN-{index:06d}"
    kind = family_kind(family)
    current, poles, packing, weight, order = _family_values(family)
    manufacturer = MANUFACTURERS[_bucket(family + "|mfr") % len(MANUFACTURERS)]
    mpn = f"{family}-{poles}P"

    def row(suffix: str, role: str, **overrides: str) -> SyntheticRow:
        values = {
            "rated_current": current,
            "poles": str(poles),
            "packaging_uom": packing,
            "weight_kg": weight,
            "order_code": order,
        }
        values.update(overrides)
        return SyntheticRow(
            sku=f"{family}-{suffix}",
            mpn=mpn,
            manufacturer=manufacturer,
            family=family,
            kind=kind,
            role=role,
            **values,
        )

    if kind is FamilyKind.CONSISTENT_PAIR:
        return [row("A", "modal"), row("B", "modal")]
    if kind is FamilyKind.CONTRADICTION_TRIPLE:
        return [
            row("A", "modal"),
            row("B", "modal"),
            row("C", "minority", rated_current=_transpose(current)),
        ]
    if kind is FamilyKind.EQUAL_RANK_PAIR:
        other = WEIGHTS[(poles % 4) + 1]
        return [row("A", "modal"), row("B", "minority", weight_kg=f"{other} kg")]
    if kind is FamilyKind.FILL_GAP_TRIPLE:
        return [row("A", "modal"), row("B", "modal"), row("C", "blank", packaging_uom="")]
    if kind is FamilyKind.UNIT_FRAME_PAIR:
        grams = str(int(float(weight.split()[0]) * 1000))
        return [row("A", "modal"), row("B", "trap", weight_kg=f"{grams} g")]
    if kind is FamilyKind.VOCABULARY_PAIR:
        return [row("A", "modal"), row("B", "trap", poles=f"{poles}P")]
    if kind is FamilyKind.DIMENSION_SINGLE:
        return [row("A", "only", rated_current=weight)]
    return [row("A", "only")]


def build_rows(*, target: int) -> tuple[SyntheticRow, ...]:
    """Generate families until ``target`` synthetic rows exist.

    The stop condition is on rows rather than families so the corpus size is the number a reader
    can check, and it is deterministic: the same target always produces the same rows.
    """
    rows: list[SyntheticRow] = []
    index = 0
    while len(rows) < target:
        rows.extend(_rows_for(index))
        index += 1
    return tuple(rows)


def expected_counts(rows: Sequence[SyntheticRow]) -> dict[str, int]:
    """What T0 should find in this corpus, computed from the families rather than from a run."""
    families: dict[str, FamilyKind] = {row.family: row.kind for row in rows}
    counts: dict[str, int] = {kind.value: 0 for kind in FamilyKind}
    findings = declines = traps = 0
    for kind in families.values():
        counts[kind.value] += 1
        findings += kind.expected_findings
        declines += kind.expected_declines
        traps += 1 if kind.is_trap else 0
    counts["families"] = len(families)
    counts["rows"] = len(rows)
    counts["expected_findings"] = findings
    counts["expected_declines"] = declines
    counts["equivalence_traps"] = traps
    return counts


def real_rows(path: Path | str) -> Iterator[dict[str, str]]:
    """The S1 stratum: the R1 demonstration catalog, unchanged.

    Copied rather than regenerated. Its own provenance file records how it was built from ABB's
    datasheet, and re-deriving it here would create a second account of the same rows that could
    drift from the first.
    """
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            yield {column: row.get(column, "") for column in COLUMNS}


def write_catalog(
    destination: Path | str,
    *,
    real_catalog: Path | str,
    target_total: int = 10_000,
) -> tuple[int, int, tuple[SyntheticRow, ...]]:
    """Write the R2 corpus. Returns ``(real rows, synthetic rows, the synthetic rows)``."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    grounded = list(real_rows(real_catalog))
    synthetic = build_rows(target=max(0, target_total - len(grounded)))

    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in grounded:
            writer.writerow(row)
        for row in synthetic:
            writer.writerow(row.as_row())

    return len(grounded), len(synthetic), synthetic


def provenance(
    *,
    real_count: int,
    synthetic: Sequence[SyntheticRow],
    real_catalog: str,
    destination: str,
) -> dict[str, object]:
    """The provenance document written next to the corpus. Read by tests and by the report."""
    counts = expected_counts(synthetic)
    return {
        "catalog": "errata-scale R2 demonstration catalog",
        "corpus_version": CORPUS_VERSION,
        "generated_by": "errata_scale.corpus.write_catalog",
        "destination": destination,
        "warning": (
            "THE CATALOG IS CONSTRUCTED. Stratum S1 is the R1 demonstration catalog, whose rows "
            "were read from ABB's own hash-registered datasheet; stratum S2 is generated here, "
            "with defects injected on purpose, because no public 10k+ industrial catalog with "
            "retrievable source documents was reachable. Detection numbers describe a population "
            "we created. Grounding, where a document exists, is empirical."
        ),
        "mutation": "by sha256(family key) % 100 -- reproducible from the SKU list alone, no RNG",
        "strata": {
            "S1_documented": {
                "rows": real_count,
                "source": real_catalog,
                "documents": "the ABB S200 datasheets registered in data/reference/manifest.json",
                "tiers": "T0 and T1 -- these are the only rows a document can ground",
            },
            "S2_undocumented": {
                "rows": counts["rows"],
                "families": counts["families"],
                "source": "constructed; values drawn from the IEC preferred series and the S1 tables",
                "documents": "none, deliberately -- these rows are the groundable-fraction story",
                "tiers": "T0 only",
            },
        },
        "expected": {
            "findings": counts["expected_findings"],
            "declines": counts["expected_declines"],
            "equivalence_traps": counts["equivalence_traps"],
        },
        "families_by_kind": {
            kind.value: {
                "families": counts[kind.value],
                "rows_each": kind.rows,
                "expectation": kind.expectation,
            }
            for kind in FamilyKind
        },
    }
