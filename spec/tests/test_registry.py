"""FR-1.3 — the Document Register.

The requirement's acceptance criteria are two sentences, and both are tested here as written:

    "Re-fetching identical bytes does not create a second record; changed bytes create a new
     revision linked to the prior."

Both halves have an obvious wrong implementation that passes casual inspection. Appending a
revision per call satisfies "changed bytes create a new revision" perfectly and quietly fails the
first half, producing a history full of a document that never changed. Keying on URL satisfies
neither, and fails worst in exactly the case the register exists for -- a supplier reposting a
revised datasheet at the same address.

The register is production code rather than spike scaffolding (see the P3 scope fence in
`PHASES.md`): `Evidence.doc_revision_sha256` is a required field that nothing previously produced,
so this is the missing half of a contract the claim schema has been enforcing since it was written.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from errata_spec import (
    DocumentRegister,
    DocumentRevision,
    Evidence,
    RevisionNotFoundError,
    sha256_bytes,
)

DOC = "schneider-acti9-ic60n-a9f74210"
V1 = b"%PDF-1.7 rated current 10 A, curve C, 6 kA"
V2 = b"%PDF-1.7 rated current 10 A, curve C, 10 kA  (revised 09/2024)"


@pytest.fixture
def register() -> DocumentRegister:
    return DocumentRegister()


# -- FR-1.3, first half: identical bytes ------------------------------------------------------


def test_refetching_identical_bytes_does_not_create_a_second_record(
    register: DocumentRegister,
) -> None:
    """The acceptance criterion, verbatim."""
    first = register.register(V1, doc_id=DOC, source_url="https://example.invalid/a.pdf")
    second = register.register(V1, doc_id=DOC, source_url="https://example.invalid/a.pdf")

    assert len(register) == 1
    assert first.sha256 == second.sha256
    assert len(register.history(DOC)) == 1


def test_the_same_bytes_from_a_different_url_are_still_one_document(
    register: DocumentRegister,
) -> None:
    """Identity is the bytes, not the address.

    Manufacturers mirror datasheets across regional sites constantly. A register keyed on URL
    would hold four copies of one document and four different answers to "what did the reviewer
    see".
    """
    register.register(V1, doc_id=DOC, source_url="https://example.invalid/eu/a.pdf")
    register.register(V1, doc_id=DOC, source_url="https://example.invalid/us/a.pdf")
    register.register(V1, doc_id=DOC, source_url="https://example.invalid/apac/a.pdf")

    assert len(register) == 1
    revision = register.current(DOC)
    assert revision is not None
    assert len(revision.fetches) == 3, "every retrieval is a fact worth keeping"
    assert {f.source_url for f in revision.fetches} == {
        "https://example.invalid/eu/a.pdf",
        "https://example.invalid/us/a.pdf",
        "https://example.invalid/apac/a.pdf",
    }


def test_each_refetch_records_its_own_timestamp(register: DocumentRegister) -> None:
    """Knowing a document was still live last Tuesday is worth something on its own."""
    monday = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
    register.register(V1, doc_id=DOC, retrieved_utc=monday)
    register.register(V1, doc_id=DOC, retrieved_utc=monday + timedelta(days=1))

    revision = register.current(DOC)
    assert revision is not None
    assert [f.retrieved_utc for f in revision.fetches] == [monday, monday + timedelta(days=1)]


def test_the_same_bytes_cannot_belong_to_two_documents(register: DocumentRegister) -> None:
    """Refused rather than silently reassigned. If two logical documents genuinely share a file,
    they share a revision, and pretending otherwise gives one set of bytes two histories."""
    register.register(V1, doc_id=DOC)
    with pytest.raises(ValueError, match="already registered under doc_id"):
        register.register(V1, doc_id="some-other-document")


# -- FR-1.3, second half: changed bytes -------------------------------------------------------


def test_changed_bytes_create_a_new_revision_linked_to_the_prior(
    register: DocumentRegister,
) -> None:
    """The acceptance criterion, verbatim. Note *linked* -- a flag would not do."""
    first = register.register(V1, doc_id=DOC)
    second = register.register(V2, doc_id=DOC, revision_label="09/2024")

    assert len(register) == 2
    assert second.supersedes == first.sha256
    assert first.is_first_revision
    assert not second.is_first_revision
    assert [r.sha256 for r in register.history(DOC)] == [first.sha256, second.sha256]


def test_the_prior_revision_remains_retrievable(register: DocumentRegister) -> None:
    """The point of the whole design. A claim made against the old datasheet is HISTORICAL, not
    wrong -- the evidence was accurate when it was taken -- and that is only expressible if the
    old bytes are still addressable."""
    first = register.register(V1, doc_id=DOC)
    register.register(V2, doc_id=DOC)

    assert register.get(first.sha256).sha256 == first.sha256
    assert register.is_superseded(first.sha256)
    assert not register.is_superseded(register.current(DOC).sha256)


def test_current_returns_the_newest_revision(register: DocumentRegister) -> None:
    register.register(V1, doc_id=DOC)
    latest = register.register(V2, doc_id=DOC)
    assert register.current(DOC) == latest


def test_current_is_none_for_an_unknown_document(register: DocumentRegister) -> None:
    assert register.current("never-seen") is None
    assert register.history("never-seen") == ()


def test_a_revision_label_is_recorded_but_never_invented(register: DocumentRegister) -> None:
    """A guessed revision label is worse than none: it reads as having been read off the page."""
    unlabelled = register.register(V1, doc_id=DOC)
    labelled = register.register(V2, doc_id=DOC, revision_label="09/2024")
    assert unlabelled.revision_label == ""
    assert labelled.revision_label == "09/2024"


# -- integrity ---------------------------------------------------------------------------------


def test_an_unknown_revision_raises_a_distinct_error(register: DocumentRegister) -> None:
    """Not a bare KeyError: an unknown revision means a claim references evidence that cannot be
    produced, which is a data-integrity problem and wants handling as one."""
    with pytest.raises(RevisionNotFoundError, match="data-integrity"):
        register.get("0" * 64)


def test_a_revision_cannot_supersede_itself() -> None:
    with pytest.raises(ValidationError, match="cannot supersede itself"):
        DocumentRevision(sha256="a" * 64, doc_id=DOC, byte_length=1, supersedes="a" * 64)


@pytest.mark.parametrize("bad", ["", "abc", "A" * 64, "g" * 64, "a" * 63])
def test_a_malformed_hash_is_refused(bad: str) -> None:
    with pytest.raises(ValidationError):
        DocumentRevision(sha256=bad, doc_id=DOC, byte_length=1)


def test_an_empty_doc_id_is_refused(register: DocumentRegister) -> None:
    with pytest.raises(ValueError, match="doc_id must not be empty"):
        register.register(V1, doc_id="")


def test_the_register_has_no_way_to_delete_anything() -> None:
    """§4.3 / FR-7.8: "what was this reviewer looking at" must have one permanent answer.

    Asserted on the interface rather than trusted to convention, because the natural thing to add
    when a test fixture needs cleaning up is a `remove()`, and the cost of having one is invisible
    until a claim goes unreconstructible.
    """
    forbidden = {"delete", "remove", "pop", "clear", "discard", "purge", "prune"}
    present = forbidden & {name for name in dir(DocumentRegister) if not name.startswith("_")}
    assert not present, f"the register grew a removal method: {sorted(present)}"


def test_the_register_makes_no_network_call() -> None:
    """It stores bytes handed to it. Fetching is somebody else's job, which is what keeps this
    testable without a network."""
    import ast
    import inspect

    from errata_spec import registry

    source = inspect.getsource(registry)
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    banned = {"socket", "urllib", "requests", "httpx", "http", "aiohttp", "ssl"}
    assert not (imported & banned), f"registry imports {sorted(imported & banned)}"


# -- interoperation with the claim schema -----------------------------------------------------


def test_a_register_hash_satisfies_the_evidence_schema(register: DocumentRegister) -> None:
    """The loop this module exists to close: Evidence has always required a 64-character
    revision hash and nothing produced one."""
    revision = register.register(V1, doc_id=DOC)
    evidence = Evidence(
        doc_id=revision.doc_id,
        doc_revision_sha256=revision.sha256,
        page=1,
        char_span=(0, 16),
        snippet="rated current 10",
    )
    assert evidence.doc_revision_sha256 == revision.sha256
    assert register.get(evidence.doc_revision_sha256).doc_id == evidence.doc_id


def test_sha256_helper_matches_the_registered_hash(register: DocumentRegister) -> None:
    assert register.register(V1, doc_id=DOC).sha256 == sha256_bytes(V1)


# -- persistence -------------------------------------------------------------------------------


def test_a_register_round_trips_through_json(register: DocumentRegister) -> None:
    register.register(V1, doc_id=DOC, source_url="https://example.invalid/a.pdf")
    register.register(V2, doc_id=DOC, revision_label="09/2024")
    register.register(b"another document entirely", doc_id="abb-s201-c10")

    restored = DocumentRegister.from_json(register.to_json())

    assert len(restored) == len(register)
    assert restored.doc_ids() == register.doc_ids()
    for original in register:
        assert restored.get(original.sha256) == original


def test_serialisation_is_deterministic(register: DocumentRegister) -> None:
    """Two identical registers must serialise identically, or the snapshot cannot be diffed and
    a review of "what changed in the register" becomes unreadable."""
    other = DocumentRegister()
    stamp = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    for reg in (register, other):
        reg.register(V1, doc_id=DOC, retrieved_utc=stamp)
        reg.register(V2, doc_id=DOC, retrieved_utc=stamp)
    assert register.to_json() == other.to_json()


def test_a_hand_edited_register_with_a_broken_chain_is_refused(
    register: DocumentRegister,
) -> None:
    """These files will be hand-edited. Reconstructing a plausible wrong history is worse than
    refusing to load."""
    register.register(V1, doc_id=DOC)
    register.register(V2, doc_id=DOC)

    payload = json.loads(register.to_json())
    payload["revisions"][1]["supersedes"] = "b" * 64  # points at nothing

    with pytest.raises(ValueError, match="broken revision chain"):
        DocumentRegister.from_json(json.dumps(payload))


def test_an_unknown_schema_version_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown register schema"):
        DocumentRegister.from_json(json.dumps({"schema": "something-else/9", "revisions": []}))


def test_register_path_reads_a_local_file(tmp_path, register: DocumentRegister) -> None:
    path = tmp_path / "datasheet.pdf"
    path.write_bytes(V1)
    revision = register.register_path(path, doc_id=DOC)
    assert revision.sha256 == sha256_bytes(V1)
    assert revision.fetches[0].local_path == str(path)
