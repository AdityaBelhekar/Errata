"""FR-9.5 and FR-9.6 -- the gold set is what it says it is, and the hard tail is held out.

The interesting tests here are the tampering ones. "The annotations load" proves nothing; "an
annotation moved by a hundredth of a point is caught" proves the verification is doing work.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from errata_ecosystem.goldset import (
    GOLD_MANIFEST,
    VerificationLevel,
    load_gold_set,
    verify,
)
from errata_ecosystem.splits import (
    FrozenSplit,
    HardTailTouched,
    TuningRun,
    assert_untouched,
    load_split,
    record_tuning_run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def gold():
    return load_gold_set()


# ------------------------------------------------------------------------------------------------
# FR-9.5 -- URLs, hashes, annotations. No documents.
# ------------------------------------------------------------------------------------------------


def test_no_source_document_is_committed_anywhere_in_the_repository() -> None:
    """The requirement, checked as a property of the tree rather than as an intention.

    ``var/`` is excluded because it is gitignored and is where the fetch script puts the
    publisher's files -- that is the mechanism, not a loophole.
    """
    skip = {".git", ".venv", "var", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build"}
    offenders = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.parts):
            continue
        if path.suffix.lower() in {".pdf", ".epub", ".docx"}:
            offenders.append(str(path.relative_to(REPO_ROOT)))
            continue
        with path.open("rb") as handle:
            if handle.read(5) == b"%PDF-":
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"copyrighted documents in the repository: {offenders}"


def test_the_manifest_carries_a_url_and_a_hash_for_every_document(gold) -> None:
    assert gold.documents
    for document in gold.documents:
        assert document["url"].startswith("https://")
        assert len(document["sha256"]) == 64
        assert "NOT REDISTRIBUTED" in document["licence"]


def test_the_annotation_layer_hashes_to_what_the_manifest_records() -> None:
    doc = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))
    for entry in doc["annotations"]:
        body = (REPO_ROOT / entry["file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == entry["sha256"]


def test_the_gold_set_verifies_against_the_documents_themselves(gold) -> None:
    """The level that matters: every box is a real word box, and the boxed words spell the value.

    Re-derived with R1's layout module, not the spike that wrote the annotations -- verifying an
    extraction with its own extractor is finding N16's mistake.
    """
    report = verify(gold)
    if report.level is VerificationLevel.HASHES:
        pytest.skip("documents not fetched on this machine; run scripts/fetch_reference_data.sh")
    assert report.level is VerificationLevel.GROUNDED
    assert report.grounded_records == len(gold)
    assert report.problems == ()


def test_a_moved_box_is_caught(gold, tmp_path) -> None:
    """The negative control for the test above."""
    from dataclasses import replace

    if verify(gold).level is not VerificationLevel.GROUNDED:  # pragma: no cover - no documents
        pytest.skip("documents not fetched on this machine")

    first = gold.annotations[0]
    moved = replace(first, boxes=tuple((x + 3.0, y, x2, y2) for x, y, x2, y2 in first.boxes))
    tampered = replace(gold, annotations=(moved,))
    report = verify(tampered)
    assert report.level is VerificationLevel.FAILED
    assert any("is not a word box" in problem for problem in report.problems)


def test_a_changed_value_is_caught(gold) -> None:
    from dataclasses import replace

    if verify(gold).level is not VerificationLevel.GROUNDED:  # pragma: no cover - no documents
        pytest.skip("documents not fetched on this machine")

    first = gold.annotations[0]
    tampered = replace(gold, annotations=(replace(first, value="999"),))
    report = verify(tampered)
    assert report.level is VerificationLevel.FAILED
    assert any("the annotation claims" in problem for problem in report.problems)


def test_a_document_that_contributes_nothing_is_reported_rather_than_hidden(gold) -> None:
    assert "abb-s200muc-1SXP403008B0202" in gold.documents_with_no_annotations
    note = " ".join(verify(gold).notes)
    assert "contribute no annotations" in note


def test_annotations_resolve_into_the_canonical_attribute_vocabulary(gold) -> None:
    uris = {a.attribute_uri for a in gold.annotations}
    assert "etim:EF000227" in uris
    assert all(":" in uri for uri in uris)


# ------------------------------------------------------------------------------------------------
# FR-9.6 -- the frozen split
# ------------------------------------------------------------------------------------------------


def test_the_split_hash_is_pinned_and_matches_the_gold_manifest() -> None:
    split = load_split()
    assert split.sha256 == "99216acbd108dc72cecce4c9b470fc4356fb0d9980aeb58c2b9f1dd1cf893cd8"
    assert len(split) == 275
    assert split.of_total == 1426


def test_every_split_record_is_a_real_gold_record(gold) -> None:
    split = load_split()
    known = set(gold.record_ids)
    assert split.record_ids <= known


def test_the_split_is_exactly_the_merged_cell_records(gold) -> None:
    split = load_split()
    merged = {a.record_id for a in gold.annotations if a.from_merged_cell}
    assert split.record_ids == merged


def test_the_categories_the_prd_names_are_recorded_as_absent_rather_than_implied() -> None:
    split = load_split()
    named = {c["category"] for c in split.unrepresented}
    assert named == {
        "degraded scans",
        "fold-outs",
        "cross-page tables",
        "superseded revisions",
    }
    for category in split.unrepresented:
        assert category["present"] is False
        assert len(category["why"]) > 60


def test_a_tuning_run_that_touches_the_split_fails_the_build() -> None:
    split = load_split()
    offender = TuningRun(
        run_id="t-bad", purpose="threshold sweep", record_ids=tuple(sorted(split.record_ids)[:2])
    )
    with pytest.raises(HardTailTouched, match=r"FR-9\.6 violated"):
        assert_untouched(split, [offender])


def test_a_tuning_run_that_stays_out_of_the_split_passes(gold) -> None:
    split = load_split()
    allowed = split.held_out(gold.record_ids)
    assert len(allowed) == len(gold) - len(split)
    assert_untouched(split, [TuningRun(run_id="t-ok", purpose="sweep", record_ids=allowed[:50])])


def test_recording_a_violating_run_raises_before_it_is_written(tmp_path) -> None:
    """A violating run must not be able to leave a record saying it happened and carry on."""
    split = load_split()
    ledger = tmp_path / "tuning.jsonl"
    with pytest.raises(HardTailTouched):
        record_tuning_run(
            TuningRun(run_id="t", purpose="p", record_ids=tuple(sorted(split.record_ids)[:1])),
            ledger=ledger,
            split=split,
        )
    assert not ledger.exists()


def test_a_split_whose_contents_moved_does_not_load(tmp_path) -> None:
    """The freeze is the hash. Editing the record list and re-running must fail, not re-freeze."""
    original = (REPO_ROOT / "data" / "gold" / "splits" / "hard-tail.json").read_text("utf-8")
    doc = json.loads(original)
    doc["record_ids"] = doc["record_ids"][:-1]
    (tmp_path / "hard-tail.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="is not frozen"):
        load_split(splits_dir=tmp_path)


def test_coverage_is_reported_as_a_fraction_of_the_whole_set() -> None:
    split = load_split()
    assert isinstance(split, FrozenSplit)
    assert 0.19 < split.coverage < 0.20
