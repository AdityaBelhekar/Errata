"""Assemble the FR-0.3 corpus and write it where `errata-r0 operating-point` can read it.

Five inputs, and where each comes from:

| Column | Source | Real? |
|---|---|---|
| `gold_value`, `gold_page`, `gold_evidence_boxes` | table cell + its word boxes | ✅ ABB's document |
| `predicted_value`, `predicted_page`, `predicted_box` | the table-blind flat-text extractor | ✅ derived from it |
| `confidence` | pattern specificity × proximity × contention | ✅ observable without the answer |
| `is_disagreement_predicted` | **the real `errata_comparator`** on catalog vs predicted | ✅ the product |
| `is_disagreement_actual` | the injected catalog defect, known by construction | ⚠️ constructed |

The disagreement decision runs through `errata_comparator.compare_attribute` -- the component the
product is won or lost on -- rather than a string comparison written for this file. That means
gate 2 is measuring the thing that ships, and that a semantic-equivalence failure would show up
here as a false disagreement rather than being quietly normalised away.

**The abstention path is preserved end to end.** Where the extractor declines, `predicted_value`
is `None` -- not `""` -- and no disagreement is raised. FR-3.3 insists abstentions and values are
distinct types precisely so that a decline cannot be read downstream as a value, and collapsing
them here would hand the risk-coverage curve a confident wrong answer in place of an honest
silence.

    ./.venv/Scripts/python.exe -m spike.build_corpus
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import yaml

from errata_comparator import AttributeSpec, compare_attribute
from errata_spec import DocumentRegister
from errata_spec.taxonomy import CLASS_PROFILE
from spike.attributes import BY_KEY
from spike.catalog import CATALOG_VERSION, DEFECT_RATE, EQUIVALENT_VARIANT_RATE, build_catalog
from spike.gold import GOLD_VERSION, build_gold
from spike.layout import LAYOUT_VERSION
from spike.predict import PREDICT_VERSION, predict
from spike.tables import TABLES_VERSION

DATASHEET_DIR = Path("var/spike/datasheets")
DEFAULT_OUT = Path("var/spike/corpus.yaml")


def _box(bbox: tuple[float, float, float, float]) -> dict[str, float]:
    x0, y0, x1, y1 = bbox
    return {"x0": round(x0, 2), "y0": round(y0, 2), "x1": round(x1, 2), "y1": round(y1, 2)}


def build(datasheets: list[Path]) -> dict[str, object]:
    register = DocumentRegister()
    records: list[dict[str, object]] = []
    tallies: Counter[str] = Counter()

    for pdf in datasheets:
        revision = register.register_path(pdf, doc_id=pdf.stem, media_type="application/pdf")
        gold, layer = build_gold(pdf)
        catalog = build_catalog(gold)
        tallies["documents"] += 1

        if not layer.is_born_digital:
            # Stated, not silently skipped: a document with no text layer needs OCR, and the
            # spike's fence says OCR is out of scope.
            tallies["skipped_no_text_layer"] += 1
            continue

        for record in gold:
            entry = catalog[record.attribute_id]
            attribute = BY_KEY[record.attribute]
            prediction = predict(layer, record.sku, attribute)

            if prediction is None:
                tallies["abstained"] += 1
                raised = False
            else:
                comparison = compare_attribute(
                    AttributeSpec(key=record.attribute, label=record.column_header),
                    entry.value,
                    prediction.value,
                )
                raised = CLASS_PROFILE[comparison.disagreement_class].raises_finding
                tallies["raised" if raised else "silent"] += 1

            tallies[f"catalog:{entry.kind}"] += 1
            records.append(
                {
                    "attribute_id": f"{revision.doc_id}::{record.attribute_id}",
                    "gold_value": record.value,
                    "gold_page": record.page,
                    "gold_evidence_boxes": [_box(b) for b in record.boxes],
                    "predicted_value": prediction.value if prediction else None,
                    "predicted_page": prediction.page if prediction else None,
                    "predicted_box": _box(prediction.box) if prediction else None,
                    "confidence": prediction.confidence if prediction else 0.0,
                    "is_disagreement_predicted": raised,
                    "is_disagreement_actual": entry.is_genuine_disagreement,
                }
            )

    document = {
        "name": "mcb-abb-s200-spike",
        "provenance": "empirical",
        "source": (
            "ABB S200 / S200M UC published datasheets, fetched from library.e.abb.com and "
            "hash-registered in data/reference/manifest.json. Gold values and evidence boxes are "
            "read from the documents' own ordering tables."
        ),
        "notes": _notes(tallies),
        "records": records,
    }
    return document


def _notes(tallies: Counter[str]) -> list[str]:
    """Everything a reader needs in order not to over-read the number.

    These land in the report's own output, which is the point: a caveat filed in a document
    nobody opens is not a caveat.
    """
    return [
        "GROUNDING HALF IS EMPIRICAL. The documents are ABB's own published datasheets, the gold "
        "values are the text printed in their ordering-table cells, and the gold evidence boxes "
        "are the word boxes of that text. Nothing on this side is generated.",
        "DISAGREEMENT HALF USES A CONSTRUCTED CATALOG. No real ABB catalog was available, so "
        f"catalog values were built from the gold with a {DEFECT_RATE:.0%} injected-defect rate "
        f"and a {EQUIVALENT_VARIANT_RATE:.0%} cosmetic-but-equivalent rate (seeded, reproducible). "
        "Disagreement precision and recall therefore measure the comparator against defects we "
        "chose, not against defects a real catalog contains.",
        "GOLD IS DOCUMENT-DERIVED, NOT EXPERT-LABELLED. FR-0.3 asks for 200 HAND-labelled "
        "records. These are read mechanically from table structure. That is faithful -- the value "
        "is the cell text and the evidence is its words -- but it is not a domain expert's "
        "judgment, and it shares gate 1's weakness: the same author wrote the labeller and the "
        "thing being measured. An independent pass would strengthen it.",
        "PREDICTIONS ARE TABLE-BLIND BY DESIGN. The extractor sees only the flat char-indexed "
        "text layer and matches a value-shaped token near the SKU's type designation. It cannot "
        "see cells or columns. If it shared the gold builder's table structure the two would "
        "agree by construction and the grounding number would be worthless.",
        "FR-3.4 IS ENFORCED STRUCTURALLY. predict() takes (layer, sku, attribute) and has no "
        "parameter through which a catalog or gold value could reach it.",
        "Disagreements are decided by the real errata_comparator, not by string equality, so this "
        "measures the component that ships.",
        f"versions: {LAYOUT_VERSION}, {TABLES_VERSION}, {GOLD_VERSION}, {PREDICT_VERSION}, "
        f"{CATALOG_VERSION}",
        f"tallies: {dict(sorted(tallies.items()))}",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spike.build_corpus")
    parser.add_argument("--datasheets", type=Path, default=DATASHEET_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    pdfs = sorted(Path(args.datasheets).glob("*.pdf"))
    if not pdfs:
        print(f"no PDFs under {args.datasheets}. Run scripts/fetch_reference_data.sh first.")
        return 1

    document = build(pdfs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    records = document["records"]
    assert isinstance(records, list)
    print(f"wrote {args.out}  ({len(records)} records from {len(pdfs)} document(s))")
    print()
    print("Now run:")
    print(f"  ./.venv/Scripts/errata-r0.exe operating-point --corpus {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
