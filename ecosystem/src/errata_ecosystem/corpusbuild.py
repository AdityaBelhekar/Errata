"""Build an FR-0.3 corpus from the published gold set, for any extractor, without the spike.

Two open findings meet in this module and one piece of work closes both.

**Finding 1 -- the headline number does not measure the shipped product.** R0 gate 2 reports
46.34% word-level grounding F1. That came from ``spike/predict.py``. ``errata_audit.derive`` --
the extractor this repository ships -- had never been scored on the grounding metric at all.

**Finding 2 -- the spike can never be deleted.** ``spike/README.md`` says it is frozen rather than
deleted "for one reason: ``build_corpus.py`` is the only thing that can regenerate
``var/spike/corpus.yaml``, and a measured gate whose corpus cannot be rebuilt is a measurement
nobody can check." So R0's second gate permanently depended on scaffolding nobody was allowed to
touch.

Both have the same root cause: the corpus builder lived inside the scaffolding. This module is the
production one. It rebuilds the gate-2 corpus from artifacts that are *already committed and
already hashed*, with a pluggable extractor, and it reproduces the frozen corpus byte-for-byte
when handed the frozen baseline -- which is the proof that it is faithful, and the reason the
spike can now go.

**Where every column comes from, and whether it is real.**

=========================================  ==========================================  ======
column                                     source                                      real?
=========================================  ==========================================  ======
``gold_value``, ``gold_page``,             ``data/gold/annotations/*.jsonl`` -- the     yes
``gold_evidence_boxes``                    published annotation layer, hashed in
                                           ``data/gold/manifest.json`` and
                                           re-derivable from the documents by
                                           ``errata-r3 gold verify``
``predicted_*``, ``confidence``            the chosen extractor                        yes
``is_disagreement_predicted``              the real ``errata_comparator``              yes
``is_disagreement_actual``                 the injected catalog defect                 **no**
=========================================  ==========================================  ======

So the *grounding* half is fully empirical and the *disagreement-detection* half rests on a
catalog whose errors we injected. That is a normal way to measure detection -- you cannot measure
recall against errors you cannot enumerate -- but it travels with the number, in the corpus
``notes``, which land in the report's own output.

**Reading gold from the committed annotations rather than rebuilding it is the load-bearing
choice.** The annotation layer is a published artifact under a content hash: it cannot drift, and
``errata-r3 gold verify`` re-derives all 1,426 records from the documents with R1's own layout
module rather than the code that wrote them. Rebuilding gold here instead would put the gold and
the prediction back in one process, which is the arrangement the spike existed to avoid.

**The constructed catalog is reproduced, not re-invented.** ``_build_catalog`` is a faithful port
of the generator frozen with the gate-2 measurement -- same seed, same rates, same mutators, same
order of ``random`` calls. That is not tidiness: the corpus is only comparable to the published
46.34% if the catalog it audits is the same catalog, and "same" here means every ``rng.random()``
lands in the same place. The regression test asserts the whole rebuilt corpus matches the frozen
one byte-for-byte, so a change to any of it fails the build rather than quietly moving a
published number.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from errata_audit import (
    AttributeMap,
    AuditAttribute,
    EtimClass,
    Table,
    TextLayer,
    extract_layer,
    extract_tables,
    load_attributes,
)
from errata_audit.etim import load_etim_cached
from errata_audit.layout import LAYOUT_VERSION
from errata_audit.tables import TABLES_VERSION
from errata_comparator import AttributeSpec, compare_attribute
from errata_spec import DocumentRegister
from errata_spec.taxonomy import CLASS_PROFILE, DisagreementClass

from .extractors import Extractor, assert_blind, get_extractor
from .vocabulary import canonical_uri

__all__ = [
    "CATALOG_VERSION",
    "CORPUS_BUILDER_VERSION",
    "DEFECT_RATE",
    "EQUIVALENT_VARIANT_RATE",
    "MCB_CLASS_ID",
    "SEED",
    "GoldAnnotation",
    "build_corpus",
    "load_gold",
    "stratify",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD_DIR = REPO_ROOT / "data" / "gold"
DEFAULT_DOCUMENTS = REPO_ROOT / "var" / "spike" / "datasheets"
DEFAULT_ETIM = (
    REPO_ROOT
    / "var"
    / "reference"
    / "etim"
    / "ETIM-10.0-ALL-SECTORS-CSV-METRIC-EI-2024-12-05.zip"
)

CORPUS_BUILDER_VERSION = "errata-corpusbuild/1.0.0"

#: The generator frozen with the gate-2 measurement. Changing any of the three moves a published
#: number, which is why they are constants with names rather than parameters with defaults.
CATALOG_VERSION = "spike-catalog/1.0.0"
SEED = 20260819
DEFECT_RATE = 0.18
EQUIVALENT_VARIANT_RATE = 0.12

#: ETIM's miniature circuit breaker class. Every SKU in this corpus is an ABB S200 MCB, so the
#: class is stated once here rather than resolved per record from a catalog the corpus does not
#: have. Stating it is what makes FR-3.1's closed-list check live during the measurement -- an
#: extractor scored with ``klass=None`` would never have its schema constraint exercised, and the
#: score would describe a pipeline with one of its four requirements switched off.
MCB_CLASS_ID = "EC000042"

#: How the attribute is described to the comparator. This is a real fork in what gets measured and
#: it is a parameter rather than a constant because both answers are needed.
#:
#: ``frozen`` reproduces the gate-2 corpus exactly: the spike described each attribute to the
#: comparator as ``AttributeSpec(key=..., label=<column header>)`` and nothing else -- no ``kinds``,
#: no ``vocabulary``, no uri. ``product`` passes ``AuditAttribute.to_spec()``, which is what R1
#: actually hands the comparator on every run.
#:
#: **The difference is not cosmetic and it was found by rebuilding.** Under ``frozen`` the
#: comparator cannot tell that a packing unit is a PACKAGING value, so it judges "5" against "5.0"
#: as a generic pair and raises; under ``product`` it reads them through the packaging semantics
#: and stays silent. 303 of 1,426 records move -- every ``packing_unit`` record in the corpus.
#:
#: So the published gate-2 disagreement half was measured against a comparator told *less about
#: the attribute than the product tells it*. The grounding half is untouched: no comparator runs
#: on that path. Both modes are kept because deleting ``frozen`` would make the published 46.34%
#: uncheckable, and defaulting to it would keep measuring a pipeline nobody ships.
COMPARATOR_SPECS = ("frozen", "product")

#: What "the extractor got the value right" means when the two sides do not share a surface
#: convention.
#:
#: ExtractBench's Value F1 asks "does it get the answer right", and the default answer to that in
#: ``errata_bench`` is exact string match -- correct for a corpus whose gold and predictions are
#: written the same way, and a broken instrument for one whose are not. The published gold set
#: records the cell text exactly as printed (``6``, never ``6 A``: the unit lives in the column
#: header and gold carries the header separately). R1 composes the two, because FR-4.3 says ``16``
#: in a cell is not a fact and ``16`` under a column headed *Rated current I n A* is.
#:
#: Both conventions are right. Comparing them with ``==`` is not. So acceptance is decided by
#: ``errata_comparator`` -- the component that owns equivalence and that FR-0.1/FR-0.2 already
#: measure -- against gold composed by the attribute's own documented rule from gold's own column
#: header. These are the verdicts that mean the two sides state the same fact.
#:
#: ``UNDETERMINED`` is deliberately absent. "We could not check" is not "we checked and it is
#: fine", and the taxonomy keeps them apart precisely so that a scorer cannot quietly merge them.
#: ``PRECISION_MISMATCH`` is absent too: a dropped tolerance is a real difference in what was
#: stated, and accepting it here would let the extractor lose information for free.
ACCEPTING_CLASSES = frozenset(
    {
        DisagreementClass.AGREEMENT,
        DisagreementClass.SEMANTIC_EQUIVALENCE,
        DisagreementClass.UNIT_FRAME_MISMATCH,
    }
)


# ------------------------------------------------------------------------------------------------
# The published gold set
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GoldAnnotation:
    """One line of the published annotation layer: what the datasheet says, and where."""

    record_id: str
    document: str
    document_sha256: str
    sku: str
    attribute_key: str
    value: str
    page: int
    boxes: tuple[tuple[float, float, float, float], ...]
    column_header: str
    from_merged_cell: bool

    @property
    def attribute_id(self) -> str:
        return f"{self.sku}-{self.attribute_key}"


def load_gold(gold_dir: Path | str = GOLD_DIR) -> dict[str, tuple[GoldAnnotation, ...]]:
    """Every annotation, grouped by document, **in file order**.

    File order matters and is not an implementation detail. The constructed catalog draws from a
    seeded ``random.Random`` once per gold record, so two readers who disagree about the order
    produce two different catalogs and two different disagreement numbers from the same inputs.
    The annotation files are written in the gold builder's own emission order and read back in it.
    """
    manifest = json.loads((Path(gold_dir) / "manifest.json").read_text("utf-8"))
    grouped: dict[str, list[GoldAnnotation]] = {}

    for entry in manifest["documents"]:
        path = REPO_ROOT / entry["annotation_file"]
        rows: list[GoldAnnotation] = []
        for line in path.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append(
                GoldAnnotation(
                    record_id=row["record_id"],
                    document=row["document"],
                    document_sha256=row["document_sha256"],
                    sku=row["sku"],
                    attribute_key=row["attribute_key"],
                    value=row["value"],
                    page=int(row["page"]),
                    boxes=tuple(tuple(float(c) for c in box) for box in row["boxes"]),
                    column_header=row["column_header"],
                    from_merged_cell=bool(row["from_merged_cell"]),
                )
            )
        grouped[entry["document"]] = rows

    return {doc: tuple(rows) for doc, rows in grouped.items()}


# ------------------------------------------------------------------------------------------------
# The constructed catalog -- the one part of the corpus not read from a document
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    sku: str
    attribute: str
    value: str
    kind: str
    """``correct`` | ``defect`` | ``equivalent_variant``."""

    note: str = ""

    @property
    def is_genuine_disagreement(self) -> bool:
        """What a competent domain reviewer would say.

        ``equivalent_variant`` is deliberately ``False``: the catalog says the same thing in a
        different shape, and a reviewer shown that row would ask why they were shown it. FR-5.3
        calls semantic equivalence "the single highest-consequence requirement in the document",
        and a detection measurement containing no equivalence traps would report a precision that
        had never been tested.
        """
        return self.kind == "defect"


def _transpose(value: str) -> str | None:
    digits = [i for i, c in enumerate(value) if c.isdigit()]
    if len(digits) < 2:
        return None
    i, j = digits[0], digits[1]
    chars = list(value)
    chars[i], chars[j] = chars[j], chars[i]
    swapped = "".join(chars)
    return swapped if swapped != value else None


def _drop_decimal(value: str) -> str | None:
    if "." not in value:
        return None
    stripped = value.replace(".", "", 1)
    return stripped if stripped != value else None


def _scale(value: str) -> str | None:
    try:
        number = float(value)
    except ValueError:
        return None
    scaled = number * 10
    text = f"{scaled:g}"
    return text if text != value else None


DEFECTS = (_transpose, _drop_decimal, _scale)


def _equivalent_variant(value: str) -> str | None:
    """Same value, different surface form. Must not be flagged."""
    try:
        number = float(value)
    except ValueError:
        return None
    if number != int(number):
        return f"{number:.3f}".rstrip("0").rstrip(".") + "0"
    return f"{int(number)}.0"


def _build_catalog(
    gold: tuple[GoldAnnotation, ...], *, seed: int = SEED
) -> dict[str, CatalogEntry]:
    """A catalog entry per gold record, keyed by ``attribute_id``.

    Deterministic, and the determinism is load-bearing rather than convenient: a fixed seed means
    a change in the numbers is a change in the code rather than a reroll. The order of the
    ``rng`` calls is part of the contract -- see :func:`load_gold`.
    """
    rng = random.Random(seed)
    catalog: dict[str, CatalogEntry] = {}

    for record in gold:
        roll = rng.random()
        entry: CatalogEntry | None = None

        if roll < DEFECT_RATE:
            rng.shuffle(mutators := list(DEFECTS))
            for mutate in mutators:
                broken = mutate(record.value)
                if broken is not None:
                    entry = CatalogEntry(
                        sku=record.sku,
                        attribute=record.attribute_key,
                        value=broken,
                        kind="defect",
                        note=f"injected {mutate.__name__.lstrip('_')} of {record.value!r}",
                    )
                    break
        elif roll < DEFECT_RATE + EQUIVALENT_VARIANT_RATE:
            variant = _equivalent_variant(record.value)
            if variant is not None:
                entry = CatalogEntry(
                    sku=record.sku,
                    attribute=record.attribute_key,
                    value=variant,
                    kind="equivalent_variant",
                    note=f"cosmetic variant of {record.value!r} -- must NOT be flagged (FR-5.3)",
                )

        catalog[record.attribute_id] = entry or CatalogEntry(
            sku=record.sku,
            attribute=record.attribute_key,
            value=record.value,
            kind="correct",
        )

    return catalog


# ------------------------------------------------------------------------------------------------
# The build
# ------------------------------------------------------------------------------------------------


def _attribute_for(gold_key: str, attributes: AttributeMap) -> AuditAttribute | None:
    """Resolve a gold-set attribute key to the R1 attribute it names.

    Goes through :func:`errata_ecosystem.vocabulary.canonical_uri` rather than matching keys
    directly, because the gold set's keys were frozen under a content hash before the R1 map
    existed and one of them (``packing_unit``) differs. Matching on the canonical uri is what
    stops that becoming a second attribute (finding N15).
    """
    uri = canonical_uri(gold_key)
    return next((a for a in attributes if a.uri == uri), None)


def _spec_for(attribute: AuditAttribute, record: GoldAnnotation, mode: str) -> AttributeSpec:
    """How this attribute is described to the comparator. See :data:`COMPARATOR_SPECS`."""
    if mode == "frozen":
        # Exactly what the spike passed: a key and the gold's own column header, and nothing that
        # would let the comparator reason about the value's kind. Reproduced rather than improved,
        # because this is the arrangement the published gate-2 numbers were measured under.
        return AttributeSpec(key=record.attribute_key, label=record.column_header)
    return attribute.to_spec()


def _box(bbox: tuple[float, float, float, float]) -> dict[str, float]:
    x0, y0, x1, y1 = bbox
    return {"x0": round(x0, 2), "y0": round(y0, 2), "x1": round(x1, 2), "y1": round(y1, 2)}


def _etim_class(etim_path: Path, class_id: str = MCB_CLASS_ID) -> EtimClass | None:
    """The resolved ETIM class, or ``None`` when the release is not on this machine.

    Returning ``None`` rather than raising is deliberate but it is **not free**, and the corpus
    says so in its notes: with no class there is no closed value list, and FR-3.1's schema
    constraint never fires. A corpus built without ETIM is a corpus of a pipeline missing a
    requirement, and that fact belongs on the face of the report rather than in a changelog.
    """
    if not Path(etim_path).exists():
        return None
    model = load_etim_cached(etim_path, release="10.0", class_ids=frozenset({class_id}))
    return model.get(class_id)


def build_corpus(
    extractor_name: str,
    *,
    documents: Path | str = DEFAULT_DOCUMENTS,
    gold_dir: Path | str = GOLD_DIR,
    etim_path: Path | str = DEFAULT_ETIM,
    comparator_spec: str = "product",
) -> dict[str, Any]:
    """Build the FR-0.3 corpus document for one named extractor.

    Returns the mapping ``errata_bench.load_corpus`` reads, with one extra key per record --
    ``method`` -- which the scorer ignores and :func:`stratify` uses. Adding a field the corpus
    loader does not know about is safe by construction (it reads by name), and it is the only way
    to report which half of a score is comparable to ExtractBench and which half is partly
    circular.
    """
    if comparator_spec not in COMPARATOR_SPECS:
        raise ValueError(
            f"comparator_spec must be one of {COMPARATOR_SPECS}, got {comparator_spec!r}"
        )
    documents = Path(documents)
    attributes = load_attributes()
    gold_by_document = load_gold(gold_dir)
    klass = _etim_class(Path(etim_path))
    register = DocumentRegister()

    records: list[dict[str, Any]] = []
    tallies: Counter[str] = Counter()
    unresolved: set[str] = set()
    extractor_versions: set[str] = set()

    for doc_id, gold in sorted(gold_by_document.items()):
        if not gold:
            # A registered document that contributes no annotations is a gap in the gold set, not
            # an error here. build_gold records why (transposed ordering tables); repeating the
            # reason would put it in two places and let them drift.
            tallies["documents_without_annotations"] += 1
            continue

        pdf = documents / f"{doc_id}.pdf"
        if not pdf.exists():
            raise FileNotFoundError(
                f"{pdf} absent. The datasheets are not committed (FR-9.5); run "
                "scripts/fetch_reference_data.sh to reconstruct them from ABB's own server."
            )

        revision = register.register_path(pdf, doc_id=doc_id, media_type="application/pdf")
        layer: TextLayer = extract_layer(pdf)
        tables: tuple[Table, ...] = extract_tables(pdf)
        tallies["documents"] += 1

        extractor: Extractor = get_extractor(
            extractor_name,
            klass=klass,
            doc_id=doc_id,
            revision_sha256=revision.sha256,
        )
        # Before a single record is produced. A leaky extractor must not get as far as writing a
        # score somebody might quote.
        assert_blind(extractor)
        extractor_versions.add(f"{extractor.name}={extractor.version}")

        catalog = _build_catalog(gold)

        for record in gold:
            attribute = _attribute_for(record.attribute_key, attributes)
            if attribute is None:
                unresolved.add(record.attribute_key)
                continue

            entry = catalog[record.attribute_id]
            prediction = extractor.predict(layer, tables, mpn=record.sku, attribute=attribute)

            if prediction is None:
                tallies["abstained"] += 1
                raised = False
                method = "abstained"
                equivalent = None
            else:
                # The DISAGREEMENT half: the customer's catalog value against what the system
                # asserts. Composition matters here and nowhere else -- this is the comparison the
                # product actually performs on every run.
                comparison = compare_attribute(
                    _spec_for(attribute, record, comparator_spec),
                    entry.value,
                    prediction.claim,
                )
                raised = CLASS_PROFILE[comparison.disagreement_class].raises_finding
                tallies["raised" if raised else "silent"] += 1
                method = prediction.method or "unknown"

                # The VALUE half: what ExtractBench's Value F1 asks, decided by the component
                # that owns equivalence rather than by `==`. Both sides are the value AS PRINTED,
                # so no system is advantaged by the convention it emits in. See ACCEPTING_CLASSES.
                # Exact match first, and it is not an optimisation. The comparator DECLINES a
                # bare unitless value rather than guessing at it -- correct behaviour, and it
                # would import those declines here as failures. Two byte-identical strings are the
                # same value and need no adjudication to say so, which makes this test monotone:
                # the comparator can only ever ADD an acceptance, never take one away. Without
                # that property the value axis would move whenever the comparator got stricter,
                # which is a change in an instrument dressed up as a change in a result.
                if prediction.value.strip() == record.value.strip():
                    equivalent = True
                    tallies["value:identical"] += 1
                else:
                    against_gold = compare_attribute(
                        _spec_for(attribute, record, comparator_spec),
                        record.value,
                        prediction.value,
                    )
                    equivalent = against_gold.disagreement_class in ACCEPTING_CLASSES
                    tallies[f"value:{against_gold.disagreement_class.value}"] += 1

            tallies[f"catalog:{entry.kind}"] += 1
            tallies[f"method:{method}"] += 1
            records.append(
                {
                    "attribute_id": f"{doc_id}::{record.attribute_id}",
                    "gold_value": record.value,
                    "gold_page": record.page,
                    "gold_evidence_boxes": [_box(b) for b in record.boxes],
                    "predicted_value": prediction.value if prediction else None,
                    "predicted_page": prediction.page if prediction else None,
                    "predicted_box": _box(prediction.box) if prediction else None,
                    "confidence": prediction.confidence if prediction else 0.0,
                    "is_disagreement_predicted": raised,
                    "is_disagreement_actual": entry.is_genuine_disagreement,
                    "value_equivalent": equivalent,
                    "method": method,
                }
            )

    if unresolved:
        raise ValueError(
            f"gold attribute keys with no entry in the R1 attribute map: {sorted(unresolved)}. "
            "Add an alias to audit/config/attributes.yaml rather than dropping the records -- "
            "silently skipping the attributes that do not resolve is the cheapest possible way to "
            "improve every rate in this report."
        )

    return {
        "name": f"mcb-abb-s200-{extractor_name}",
        "comparator_spec": comparator_spec,
        "provenance": "empirical",
        "source": (
            "ABB S200 / S200M UC published datasheets, fetched from library.e.abb.com and "
            "hash-registered in data/reference/manifest.json. Gold values and evidence boxes are "
            "read from data/gold/annotations, the published annotation layer, whose hashes are in "
            "data/gold/manifest.json and which errata-r3 gold verify re-derives from the documents."
        ),
        "notes": _notes(
            extractor_name, tallies, klass, sorted(extractor_versions), comparator_spec
        ),
        "records": records,
    }


def _notes(
    extractor_name: str,
    tallies: Counter[str],
    klass: EtimClass | None,
    extractor_versions: list[str],
    comparator_spec: str,
) -> list[str]:
    """Everything a reader needs in order not to over-read the number.

    These land in the report's own output, which is the point: a caveat filed in a document nobody
    opens is not a caveat.
    """
    notes = [
        "GROUNDING HALF IS EMPIRICAL. The documents are ABB's own published datasheets and the "
        "gold values and evidence boxes are the published annotation layer, re-derivable from "
        "those documents by `errata-r3 gold verify`. Nothing on this side is generated.",
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
        "Disagreements are decided by the real errata_comparator, not by string equality, so this "
        "measures the component that ships.",
        "TWO COMPARISONS, TWO VALUES, AND THE DIFFERENCE IS THE POINT. The value axis scores the "
        "value AS PRINTED against gold, which is also as printed -- so a system that composes the "
        "header's unit (R1: '16' under 'Rated current I n A' becomes '16 A', FR-4.3) is neither "
        "rewarded nor punished for a convention. The disagreement axis uses what each system "
        "ASSERTS, because that is the comparison the product performs against a customer catalog.",
        "VALUE ACCEPTANCE IS EXACT MATCH, WIDENED BY THE COMPARATOR. Identical strings are the "
        "same value; where they differ, errata_comparator decides, so '6' and '6.0' are one value "
        "here exactly as they are everywhere else in this repository. The widening is one-way -- "
        "it can only add an acceptance -- so this axis can never fall below the exact-match score. "
        "Only agreement, semantic equivalence and unit-frame mismatch count as accepted -- an "
        "undetermined comparison does not, because 'we could not check' is not 'we checked and it "
        "is fine'.",
        "FR-3.4 IS ENFORCED STRUCTURALLY. Every extractor's predict() is signature-checked by "
        "errata_ecosystem.extractors.assert_blind before a single record is produced; there is no "
        "parameter through which a catalog or gold value could reach it.",
    ]

    if comparator_spec == "frozen":
        notes.append(
            "COMPARATOR SPEC IS `frozen`. Each attribute was described to the comparator as a key "
            "and a column header only -- no kinds, no vocabulary -- which is what the gate-2 "
            "corpus was built with and is LESS than the product tells the comparator on a real "
            "run. Under this spec the comparator cannot tell a packing unit from a bare number "
            "and raises on '5' vs '5.0'. Kept so the published 46.34% stays checkable; do not "
            "quote the disagreement half of it as a property of the shipped pipeline."
        )
    else:
        notes.append(
            "COMPARATOR SPEC IS `product`. Attributes are described to the comparator exactly as "
            "R1 describes them on a real run (kinds, vocabulary and uri included). This differs "
            "from the frozen gate-2 corpus on every packing_unit record."
        )

    if extractor_name == "tableblind":
        notes.append(
            "PREDICTIONS ARE TABLE-BLIND BY DESIGN. The baseline sees only the flat char-indexed "
            "text layer and matches a value-shaped token near the SKU's type designation. It "
            "cannot see cells or columns. Its mechanism is INDEPENDENT of the gold builder's, "
            "which is what makes the grounding number comparable to ExtractBench's."
        )
    else:
        notes.append(
            "READ THE STRATIFIED SCORE, NOT THE HEADLINE. Gold is read from table structure and "
            "this extractor prefers the same path, so `table_cell` predictions share a mechanism "
            "with the answer key and agree partly by construction. Only the `text_window` "
            "stratum is mechanism-independent of gold and therefore comparable to ExtractBench's "
            "46.4%. `errata-r3 corpus score` prints both and refuses to combine them."
        )

    if klass is None:
        notes.append(
            "NO ETIM RELEASE WAS AVAILABLE ON THIS MACHINE, so no class was resolved and FR-3.1's "
            "closed-value-list check never fired. This corpus therefore scores a pipeline with "
            "one of its four re-derivation requirements switched off. Run "
            "scripts/fetch_reference_data.sh and rebuild before quoting anything from it."
        )
    else:
        notes.append(
            f"ETIM class {klass.class_id} was resolved, so FR-3.1's closed-value-list check was "
            "live for every derivation."
        )

    notes.append(
        f"versions: {CORPUS_BUILDER_VERSION}, {LAYOUT_VERSION}, {TABLES_VERSION}, "
        f"{CATALOG_VERSION}, {', '.join(extractor_versions)}"
    )
    notes.append(f"tallies: {dict(sorted(tallies.items()))}")
    return notes


def stratify(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Split a built corpus by how each prediction was found.

    The strata are not a convenience view. ``table_cell`` and ``text_window`` differ in whether
    the prediction shares a mechanism with the gold, and a single number over both would be part
    measurement and part tautology with no way to tell which part is which.
    """
    strata: dict[str, list[dict[str, Any]]] = {}
    for record in document["records"]:
        strata.setdefault(str(record.get("method", "unknown")), []).append(record)
    return strata


def write_corpus(document: dict[str, Any], out: Path | str) -> Path:
    """Write the corpus where ``errata-r0 operating-point`` can read it."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return out
