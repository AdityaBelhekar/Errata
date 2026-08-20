"""FR-9.5 -- the gold set as URLs, hashes and annotations, and the verification that it is real.

The requirement is one sentence -- *no source PDF is redistributed* -- and it is easy to satisfy
in a way that means nothing: ship a file of numbers, call it an annotation layer, and never check
that the numbers describe the document they claim to. This module does the checking.

:func:`verify` runs three levels and says which one it reached:

``HASHES``
    The annotation files hash to what the gold manifest records, and every record parses. Runs
    anywhere, with no documents present. This is what a third party gets before they fetch.

``DOCUMENTS``
    The documents are present locally and their bytes hash to what the manifest records. The
    corpus has been reconstructed from the publisher's own server.

``GROUNDED``
    Every annotation is re-derived from the document: the boxes are word boxes that exist on that
    page, and the words inside them spell the value the annotation claims. **This is the level
    that makes the gold set evidence rather than assertion**, and it is the level a reproduction
    run must reach before any grounding number it produces is worth reading.

The re-derivation deliberately uses R1's production layout module rather than the spike that built
the annotations. Verifying an extraction with the extractor that produced it checks nothing --
which is exactly the mistake finding N16 was made of.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from errata_audit.layout import extract_layer

from .vocabulary import canonical_uri

__all__ = [
    "GOLD_MANIFEST",
    "GoldAnnotation",
    "GoldSet",
    "VerificationLevel",
    "VerificationReport",
    "load_gold_set",
    "verify",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD_MANIFEST = REPO_ROOT / "data" / "gold" / "manifest.json"
DEFAULT_DOCUMENTS = REPO_ROOT / "var" / "spike" / "datasheets"

#: Box coordinates are written to two decimal places, so a re-derived box is compared with the
#: same tolerance. Tighter would fail on rounding; looser would let a box drift off its word.
BOX_TOLERANCE = 0.01


class VerificationLevel(str, enum.Enum):
    """How far verification got. Ordered; a report names the highest level it reached."""

    FAILED = "failed"
    HASHES = "hashes"
    DOCUMENTS = "documents"
    GROUNDED = "grounded"


@dataclass(frozen=True, slots=True)
class GoldAnnotation:
    """One annotation: a value, where it is printed, and the words that print it."""

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
    def attribute_uri(self) -> str:
        """The canonical vocabulary, resolved on read rather than stored twice (N15)."""
        return canonical_uri(self.attribute_key)


@dataclass(frozen=True, slots=True)
class GoldSet:
    """The gold set as distributed: annotations, and the documents they point at."""

    version: str
    layout_version: str
    gold_version: str
    labelling_caveat: str
    documents: tuple[dict, ...]
    annotations: tuple[GoldAnnotation, ...]
    manifest_path: Path

    def __len__(self) -> int:
        return len(self.annotations)

    def by_document(self, document: str) -> tuple[GoldAnnotation, ...]:
        return tuple(a for a in self.annotations if a.document == document)

    @property
    def record_ids(self) -> tuple[str, ...]:
        return tuple(a.record_id for a in self.annotations)

    @property
    def documents_with_no_annotations(self) -> tuple[str, ...]:
        """Registered documents that contribute nothing -- a gap, printed rather than inferred."""
        return tuple(d["document"] for d in self.documents if not d.get("records"))


@dataclass(frozen=True, slots=True)
class VerificationReport:
    level: VerificationLevel
    checked_annotations: int = 0
    checked_documents: int = 0
    grounded_records: int = 0
    problems: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.level is not VerificationLevel.FAILED and not self.problems

    def text(self) -> str:
        lines = [
            f"gold set verification: {self.level.value.upper()}",
            f"  annotations checked   {self.checked_annotations}",
            f"  documents verified    {self.checked_documents}",
            f"  records re-derived    {self.grounded_records}",
        ]
        for note in self.notes:
            lines.append(f"  note: {note}")
        for problem in self.problems:
            lines.append(f"  PROBLEM: {problem}")
        return "\n".join(lines)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_gold_set(manifest: Path | str | None = None) -> GoldSet:
    """Read the manifest and every annotation file it lists.

    A file whose hash does not match the manifest raises here rather than being loaded and
    reported on later: an annotation layer that does not match its own manifest is not a gold set
    in a degraded state, it is an unknown file.
    """
    path = Path(manifest) if manifest is not None else GOLD_MANIFEST
    doc = json.loads(path.read_text(encoding="utf-8"))
    root = path.resolve().parents[2]

    annotations: list[GoldAnnotation] = []
    for entry in doc.get("annotations", []):
        file_path = root / entry["file"]
        body = file_path.read_bytes()
        actual = _sha256(body)
        if actual != entry["sha256"]:
            raise ValueError(
                f"{entry['file']}: sha256 {actual} does not match the gold manifest's "
                f"{entry['sha256']}. Do not update the manifest to make this pass -- rebuild the "
                "annotations from the documents and find out what moved."
            )
        for line in body.decode("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            annotations.append(
                GoldAnnotation(
                    record_id=row["record_id"],
                    document=row["document"],
                    document_sha256=row["document_sha256"],
                    sku=row["sku"],
                    attribute_key=row["attribute_key"],
                    value=row["value"],
                    page=int(row["page"]),
                    boxes=tuple(tuple(float(c) for c in box) for box in row["boxes"]),
                    column_header=row.get("column_header", ""),
                    from_merged_cell=bool(row.get("from_merged_cell")),
                )
            )

    return GoldSet(
        version=str(doc.get("gold_set", "")),
        layout_version=str(doc.get("layout_version", "")),
        gold_version=str(doc.get("gold_version", "")),
        labelling_caveat=str(doc.get("labelling_caveat", "")),
        documents=tuple(doc.get("documents", ())),
        annotations=tuple(annotations),
        manifest_path=path,
    )


def verify(
    gold: GoldSet | None = None,
    *,
    documents: Path | str | None = None,
    sample: int | None = None,
) -> VerificationReport:
    """Verify the gold set as far as the local machine allows.

    ``sample`` re-derives only the first N annotations per document. The default is every one of
    them: this is the check that decides whether the benchmark's gold means anything, and it takes
    seconds.
    """
    gold = gold if gold is not None else load_gold_set()
    problems: list[str] = []
    notes: list[str] = []

    if not gold.annotations:
        return VerificationReport(
            level=VerificationLevel.FAILED,
            problems=("the gold set carries no annotations",),
        )

    empty = gold.documents_with_no_annotations
    if empty:
        notes.append(
            f"{len(empty)} registered document(s) contribute no annotations: {', '.join(empty)} "
            "-- see data/gold/splits/hard-tail.json, gold_set_gaps, for why"
        )

    doc_dir = Path(documents) if documents is not None else DEFAULT_DOCUMENTS
    present: dict[str, Path] = {}
    for entry in gold.documents:
        filename = entry["url"].rsplit("/", 1)[-1]
        candidates = [doc_dir / f"{entry['document']}.pdf", doc_dir / filename]
        found = next((c for c in candidates if c.exists()), None)
        if found is None:
            continue
        actual = _sha256(found.read_bytes())
        if actual != entry["sha256"]:
            problems.append(
                f"{found.name}: sha256 {actual[:12]} does not match the registered "
                f"{entry['sha256'][:12]} -- this is not the document the annotations describe"
            )
            continue
        present[entry["document"]] = found

    if problems:
        return VerificationReport(
            level=VerificationLevel.FAILED,
            checked_annotations=len(gold.annotations),
            problems=tuple(problems),
            notes=tuple(notes),
        )

    if not present:
        notes.append(
            "no documents present locally; run scripts/fetch_reference_data.sh to reach the "
            "GROUNDED level, which is the one that verifies the annotations against the pages"
        )
        return VerificationReport(
            level=VerificationLevel.HASHES,
            checked_annotations=len(gold.annotations),
            notes=tuple(notes),
        )

    grounded = 0
    for document, pdf in sorted(present.items()):
        layer = extract_layer(pdf)
        word_boxes: dict[int, set[tuple[int, ...]]] = {}
        for word in layer.words:
            word_boxes.setdefault(word.page, set()).add(_quantise(word.bbox))

        rows = gold.by_document(document)
        if sample is not None:
            rows = rows[:sample]
        for annotation in rows:
            page_boxes = word_boxes.get(annotation.page, set())
            for box in annotation.boxes:
                if _quantise(box) not in page_boxes:
                    problems.append(
                        f"{annotation.record_id}: box {box} is not a word box on page "
                        f"{annotation.page} of {document}"
                    )
                    break
            else:
                spelled = _words_in(layer, annotation)
                if spelled != annotation.value.split():
                    problems.append(
                        f"{annotation.record_id}: the boxed words spell {' '.join(spelled)!r}, "
                        f"the annotation claims {annotation.value!r}"
                    )
                    continue
                grounded += 1

    if problems:
        return VerificationReport(
            level=VerificationLevel.FAILED,
            checked_annotations=len(gold.annotations),
            checked_documents=len(present),
            grounded_records=grounded,
            problems=tuple(problems[:20]),
            notes=tuple(notes),
        )

    return VerificationReport(
        level=VerificationLevel.GROUNDED,
        checked_annotations=len(gold.annotations),
        checked_documents=len(present),
        grounded_records=grounded,
        notes=tuple(notes),
    )


def _quantise(box) -> tuple[int, ...]:
    """Coordinates to hundredths, as integers, so comparison is exact rather than nearly-equal."""
    return tuple(round(float(c) / BOX_TOLERANCE) for c in box)


def _words_in(layer, annotation: GoldAnnotation) -> list[str]:
    wanted = {_quantise(box) for box in annotation.boxes}
    return [
        word.text
        for word in layer.words
        if word.page == annotation.page and _quantise(word.bbox) in wanted
    ]
