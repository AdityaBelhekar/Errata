"""Build the demonstration catalog from the ABB S200 datasheet, deterministically.

**The catalog is constructed. The datasheet is real.** That distinction has to survive every
retelling of this demo, so it is written into the generated provenance file, printed by the CLI,
and repeated on the face of the HTML report:

| | Real | Constructed |
|---|---|---|
| the datasheet | ABB's own, hash-registered | |
| the values Errata re-derives, and their boxes | read from its tables | |
| **the catalog being audited** | | **built here** |

No public ABB catalog feed is available to us, so the thing under audit is generated from the
document with defects injected on purpose. That is a normal way to demonstrate detection -- you
cannot demonstrate recall against errors you cannot enumerate -- and it means the demo's *detection*
half is a measurement of a population we created, while its *grounding* half is empirical.

**Mutation is by content hash, not by a seeded RNG.** ``sha256(sku)`` decides each row's fate, so
the catalog is reproducible from the SKU list alone, in any Python, in any iteration order, forever.
A seeded RNG would tie the output to the order the tables happened to be read in, and the day the
table parser changes, every row's kind would move silently.

The mutation kinds are chosen to exercise all three outcomes the product must be able to reach --
raise, resolve silently, decline -- and in particular to include **equivalence traps**: a weight
stated in grams and a pole count written ``1P``. A detection demo containing no traps reports a
precision that has never been tested, and FR-5.3 calls semantic equivalence the single
highest-consequence requirement in the PRD.

    ./.venv/Scripts/python.exe audit/tools/build_demo_catalog.py
"""

from __future__ import annotations

import csv
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "audit" / "src"))

import yaml  # noqa: E402

from errata_audit.tables import extract_tables  # noqa: E402

DATASHEET = ROOT / "var" / "spike" / "datasheets" / "abb-s200-2CDC002142D0207.pdf"
SECOND_DATASHEET = ROOT / "var" / "spike" / "datasheets" / "abb-s200muc-1SXP403008B0202.pdf"
OUT_DIR = ROOT / "audit" / "src" / "errata_audit" / "demo"

COLUMNS = {
    "rated_current": "Rated current I n A",
    "poles": "Number of poles",
    "packaging_uom": "Packing unit PCS",
    "weight_kg": "Weight 1 PC kg",
    "order_code": "Order code",
}


@dataclass(frozen=True, slots=True)
class Row:
    sku: str
    values: dict[str, str]
    kind: str
    note: str
    datasheet: str


def bucket(sku: str) -> int:
    return int(hashlib.sha256(sku.encode("utf-8")).hexdigest(), 16) % 100


def mutate(sku: str, source: dict[str, str]) -> tuple[dict[str, str], str, str]:
    """Return ``(catalog values, kind, note)`` for one SKU.

    Every branch states what a competent reviewer should say about the row, because that is the
    ground truth the demo is measured against and it must not be inferrable only from the code.
    """
    values = {
        "rated_current": f"{source['rated_current']} A",
        "poles": source["poles"],
        "packaging_uom": f"{source['packaging_uom']} pcs",
        "weight_kg": f"{source['weight_kg']} kg",
        "order_code": source["order_code"],
    }
    slot = bucket(sku)

    if slot < 12:
        digits = source["rated_current"]
        broken = digits[::-1] if len(digits) > 1 and digits[::-1] != digits else str(int(float(digits) * 10))
        values["rated_current"] = f"{broken} A"
        return values, "defect", f"rated current transposed from {digits} A -- a real defect, SEV-1, safety class"

    if slot < 18:
        pack = source["packaging_uom"]
        values["packaging_uom"] = "Each"
        if pack.strip() == "1":
            # "Each" against a packing unit of 1 is not a defect -- it is the same statement in
            # trade vocabulary, and an audit that flagged it would be committing the exact error
            # FR-5.3 exists to prevent. Kept in the catalog as an equivalence trap rather than
            # dropped, because a trap the comparator passes is worth more than a row that is
            # simply correct.
            return values, "equivalent", (
                "'Each' against a document packing unit of 1 -- the same frame in trade "
                "vocabulary, NOT a defect. Must not flag"
            )
        return values, "defect", (
            f"packaging frame error: the document states a pack of {pack} and the catalog says "
            "Each -- the highest-severity class in the taxonomy"
        )

    if slot < 24:
        grams = round(float(source["weight_kg"]) * 1000)
        values["weight_kg"] = f"{grams} g"
        return values, "equivalent", (
            "the same weight in grams -- a unit-frame difference, NOT a defect. Flagging this "
            "would be the false positive that ends a pilot"
        )

    if slot < 30:
        values["poles"] = f"{source['poles']}P"
        return values, "equivalent", (
            "pole count written in trade notation -- semantically identical. FR-5.3: must not flag"
        )

    if slot < 34:
        values["rated_current"] = ""
        return values, "gap", (
            "the catalog field is blank where the document states a value -- a fill-rate finding, "
            "recoverable rather than wrong"
        )

    if slot < 38:
        weight = source["weight_kg"]
        values["weight_kg"] = f"{weight.replace('.', '', 1)} kg"
        return values, "defect", f"decimal point dropped from {weight} kg -- a real defect"

    return values, "correct", "matches the document; the audit should stay silent"


def read_source_rows() -> list[tuple[str, dict[str, str]]]:
    rows: list[tuple[str, dict[str, str]]] = []
    seen: set[str] = set()
    for table in extract_tables(DATASHEET):
        if "Type" not in table.column_headers:
            continue
        for row in table.rows:
            type_cell = table.cell(row, "Type")
            if type_cell is None or not type_cell.text.startswith("S2"):
                continue
            sku = type_cell.text
            if sku in seen:
                continue
            values: dict[str, str] = {}
            for key, header in COLUMNS.items():
                cell = table.cell(row, header)
                if cell is None:
                    break
                values[key] = cell.text
            if len(values) != len(COLUMNS):
                continue
            seen.add(sku)
            rows.append((sku, values))
    return rows


def build() -> list[Row]:
    out: list[Row] = []
    for sku, source in read_source_rows():
        values, kind, note = mutate(sku, source)
        out.append(Row(sku=sku, values=values, kind=kind, note=note, datasheet=DATASHEET.name))

    # Three rows that exist to exercise the Declined bucket rather than the queue. Each one is a
    # real operational situation, and each must produce a stated reason rather than a shrug.
    out.append(
        Row(
            sku="S201M-B100UC",
            values={
                "rated_current": "100 A",
                "poles": "1",
                "packaging_uom": "10 pcs",
                "weight_kg": "0.125 kg",
                "order_code": "2CDS271061R1005",
            },
            kind="declined_expected",
            note=(
                "this type designation does not appear in the datasheet -- the audit must decline "
                "with no_source_document, not audit it against the nearest row"
            ),
            datasheet=DATASHEET.name,
        )
    )
    out.append(
        Row(
            sku="S201MUC-K0.2",
            values={
                "rated_current": "0.2 A",
                "poles": "1",
                "packaging_uom": "10 pcs",
                "weight_kg": "0.125 kg",
                "order_code": "2CDS271061R0009",
            },
            kind="declined_expected",
            note=(
                "points at the S200 M UC datasheet, whose ordering tables do not resolve into "
                "columns -- the layout defeats the table pass, and the audit must say so"
            ),
            datasheet=SECOND_DATASHEET.name,
        )
    )
    out.append(
        Row(
            sku="S201M-B16UC-NODOC",
            values={
                "rated_current": "16 A",
                "poles": "1",
                "packaging_uom": "10 pcs",
                "weight_kg": "0.125 kg",
                "order_code": "2CDS271061R0165",
            },
            kind="declined_expected",
            note="names a datasheet nobody supplied -- no_source_document",
            datasheet="abb-s200-does-not-exist.pdf",
        )
    )
    return out


def main() -> int:
    rows = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    catalog_path = OUT_DIR / "catalog.csv"
    with catalog_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
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
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.sku,
                    row.sku,
                    "ABB",
                    "Miniature circuit breaker",
                    row.datasheet,
                    row.values["rated_current"],
                    row.values["poles"],
                    row.values["packaging_uom"],
                    row.values["weight_kg"],
                    row.values["order_code"],
                ]
            )

    provenance = {
        "catalog": "errata-audit demonstration catalog",
        "generated_by": "audit/tools/build_demo_catalog.py",
        "source_document": DATASHEET.name,
        "warning": (
            "THE CATALOG IS CONSTRUCTED. The datasheet is ABB's own and hash-registered; the "
            "values Errata re-derives and the boxes it draws are read from it. The catalog under "
            "audit was generated by this tool with defects injected on purpose, because no public "
            "ABB catalog feed is available. Detection numbers from this demo describe a population "
            "we created; grounding is empirical."
        ),
        "mutation": "by sha256(sku) % 100 -- reproducible from the SKU list alone, no RNG seed",
        "rows": [
            {"sku": row.sku, "kind": row.kind, "expected": row.note} for row in rows
        ],
    }
    (OUT_DIR / "provenance.yaml").write_text(
        yaml.safe_dump(provenance, sort_keys=False, allow_unicode=True, width=100), "utf-8"
    )

    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row.kind] = kinds.get(row.kind, 0) + 1
    print(f"wrote {catalog_path} -- {len(rows)} rows")
    for kind, count in sorted(kinds.items()):
        print(f"  {kind:20s} {count:4d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
