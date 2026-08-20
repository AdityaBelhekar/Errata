"""FR-1.2 / FR-1.3 -- the blob store, and the acquisition step that must not surprise anyone.

The register's own contract is tested in ``spec/tests/test_registry.py``. What is tested here is
the half R1 added: bytes on disk addressed by content, and a fetch that refuses to reach the
network unless it was told to.

The network test is the important one. An audit is a claim about what a document said, and a
pipeline that silently fetches mid-run produces a result nobody can reproduce next week. The
refusal has to be a raise, not a warning, because a warning in a log file is a refusal nobody sees.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from errata_audit.documents import BlobStore, NetworkNotPermittedError, ingest_document
from errata_spec import DocumentRegister

PAYLOAD = b"%PDF-1.7 rated current 16 A"


def test_bytes_are_addressed_by_their_own_hash(store: BlobStore) -> None:
    digest, path = store.put(PAYLOAD)
    assert digest == hashlib.sha256(PAYLOAD).hexdigest()
    assert path.name.startswith(digest)
    assert path.read_bytes() == PAYLOAD


def test_storing_the_same_bytes_twice_writes_one_file(store: BlobStore) -> None:
    first_digest, first = store.put(PAYLOAD)
    second_digest, second = store.put(PAYLOAD)
    assert (first_digest, first) == (second_digest, second)
    assert len(list(store.root.rglob("*.pdf"))) == 1


def test_no_partial_file_is_left_behind(store: BlobStore) -> None:
    store.put(PAYLOAD)
    assert not list(store.root.rglob("*.partial"))


def test_ingesting_a_local_file_registers_it_and_stores_the_bytes(
    ordering_table_pdf: Path, register: DocumentRegister, store: BlobStore
) -> None:
    source = ingest_document(ordering_table_pdf, register=register, store=store)
    assert source.sha256 in register
    assert source.path.read_bytes() == ordering_table_pdf.read_bytes()
    assert source.doc_id == ordering_table_pdf.name


def test_ingesting_the_same_file_twice_does_not_create_a_second_revision(
    ordering_table_pdf: Path, register: DocumentRegister, store: BlobStore
) -> None:
    first = ingest_document(ordering_table_pdf, register=register, store=store)
    second = ingest_document(ordering_table_pdf, register=register, store=store)
    assert first.sha256 == second.sha256
    assert len(register.history(first.doc_id)) == 1
    # ...but the second fetch is still recorded: knowing the document was still there is worth
    # something, and it is a different fact from the document having changed.
    assert len(register.get(second.sha256).fetches) == 2


def test_changed_bytes_create_a_linked_revision(
    tmp_path: Path, register: DocumentRegister, store: BlobStore
) -> None:
    path = tmp_path / "d.pdf"
    path.write_bytes(PAYLOAD)
    first = ingest_document(path, register=register, store=store, doc_id="acme-ds")
    path.write_bytes(PAYLOAD + b" (revised)")
    second = ingest_document(path, register=register, store=store, doc_id="acme-ds")

    assert second.revision.supersedes == first.sha256
    assert register.is_superseded(first.sha256)
    # The old bytes are still readable, which is what makes a historical claim reconstructible.
    assert store.get(first.sha256) == PAYLOAD


def test_a_network_url_is_refused_unless_permitted(
    register: DocumentRegister, store: BlobStore
) -> None:
    with pytest.raises(NetworkNotPermittedError, match="not permitted to fetch"):
        ingest_document(
            "https://example.invalid/datasheet.pdf", register=register, store=store
        )


def test_a_file_url_is_local_and_needs_no_permission(
    ordering_table_pdf: Path, register: DocumentRegister, store: BlobStore
) -> None:
    source = ingest_document(
        ordering_table_pdf.as_uri(), register=register, store=store
    )
    assert source.source_url.startswith("file:")
    assert source.sha256 in register


def test_the_module_makes_no_network_call_at_import_time() -> None:
    """``urlopen`` is imported inside the fetch function, not at module scope.

    Import-time purity is not fussiness: it is what lets the determinism tests, the CLI's ``status``
    command and every unit test here run with no network stack at all.
    """
    import ast
    import inspect

    from errata_audit import documents

    tree = ast.parse(inspect.getsource(documents))
    module_level = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom | ast.Import)
    ]
    names = {
        alias.name
        for node in module_level
        for alias in node.names
    } | {getattr(node, "module", "") or "" for node in module_level}
    assert not any("urlopen" in name for name in names)
