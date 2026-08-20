"""FR-1.2 / FR-1.3 -- the content-addressed blob store, and the register that indexes it.

``errata_spec.registry.DocumentRegister`` already answers *what bytes were these, where did they
come from, and what came before*. What it deliberately does not do is hold the bytes: it is pure
bookkeeping with no filesystem and no network, which is what makes it testable and what keeps the
deterministic core deterministic.

This module supplies the two halves it left out, and keeps them apart on purpose:

* :class:`BlobStore` -- bytes on disk, addressed by their own sha256. No path is ever an identity.
* :func:`ingest_document` -- acquisition. Local paths always; ``http(s)`` **only** when the caller
  passes ``allow_network=True``.

**Why the network is opt-in rather than automatic.** An audit is a claim about what a document
said, and a pipeline that silently reaches the internet mid-run produces a result that cannot be
reproduced next week when the supplier reposts the PDF. Fetching is therefore an explicit,
logged act with a recorded timestamp, and every subsequent step operates on stored bytes. NFR-8's
determinism boundary lives in ``errata_valuesem``; this is the same principle one layer out.

**Re-fetching identical bytes is not a new document** (FR-1.3), and changed bytes at the same URL
create a new revision linked to the prior one. Both behaviours belong to the register; this module
adds only the storage, and stores nothing twice.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from errata_spec import DocumentRegister, DocumentRevision

__all__ = [
    "BlobStore",
    "DocumentSource",
    "NetworkNotPermittedError",
    "ingest_document",
]


class NetworkNotPermittedError(RuntimeError):
    """Raised when a run would have to fetch over the network and was not permitted to.

    A distinct type because the correct handling is never "retry quietly": either the operator
    intends the run to reach the network and says so, or the document is supplied locally. Turning
    this into a warning would make reproducibility depend on whoever happened to be online.
    """


@dataclass(frozen=True, slots=True)
class DocumentSource:
    """One acquired document: where it came from, what it hashes to, where the bytes now live."""

    doc_id: str
    revision: DocumentRevision
    path: Path
    source_url: str = ""

    @property
    def sha256(self) -> str:
        return self.revision.sha256


class BlobStore:
    """Bytes on disk, addressed by content.

    The layout is ``<root>/<first two hex>/<full sha256><suffix>`` -- the usual fan-out, for the
    usual reason: a hundred thousand files in one directory is slow on every filesystem anyone
    runs this on.

    Writes are atomic (temp file, then rename) and idempotent. Storing bytes that are already
    present is a no-op that returns the existing path, which is what makes ``ingest_document``
    safe to call in a loop over a catalog where forty SKUs share one datasheet.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def path_for(self, digest: str, *, suffix: str = ".pdf") -> Path:
        return self.root / digest[:2] / f"{digest}{suffix}"

    def has(self, digest: str, *, suffix: str = ".pdf") -> bool:
        return self.path_for(digest, suffix=suffix).exists()

    def put(self, payload: bytes, *, suffix: str = ".pdf") -> tuple[str, Path]:
        digest = hashlib.sha256(payload).hexdigest()
        destination = self.path_for(digest, suffix=suffix)
        if destination.exists():
            return digest, destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".partial")
        temporary.write_bytes(payload)
        temporary.replace(destination)
        return digest, destination

    def put_path(self, path: Path | str, *, suffix: str | None = None) -> tuple[str, Path]:
        path = Path(path)
        return self.put(path.read_bytes(), suffix=suffix or path.suffix or ".bin")

    def get(self, digest: str, *, suffix: str = ".pdf") -> bytes:
        return self.path_for(digest, suffix=suffix).read_bytes()

    def export(self, digest: str, destination: Path | str, *, suffix: str = ".pdf") -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path_for(digest, suffix=suffix), destination)
        return destination


def ingest_document(
    source: str | Path,
    *,
    register: DocumentRegister,
    store: BlobStore,
    doc_id: str = "",
    revision_label: str = "",
    allow_network: bool = False,
    timeout: float = 30.0,
) -> DocumentSource:
    """Acquire one document, store its bytes, and record the fetch (FR-1.2, FR-1.3).

    ``source`` may be a local path, a ``file://`` URL, or an ``http(s)`` URL. The last of those
    requires ``allow_network=True``; without it the call raises rather than degrading to a cached
    copy, because "the audit used yesterday's PDF" is a materially different statement from "the
    audit used the PDF at this URL" and the two must never be confused.

    ``doc_id`` defaults to the URL's final path segment, which is stable for the same document
    across revisions -- and it is only a *label*: identity is the hash, always.
    """
    text = str(source)
    parsed = urlparse(text)
    source_url = ""

    if parsed.scheme in {"http", "https"}:
        if not allow_network:
            raise NetworkNotPermittedError(
                f"{text} is a network URL and this run was not permitted to fetch. Pass "
                "allow_network=True (CLI: --allow-network), or supply the file locally. An audit "
                "that reaches the network without being told to cannot be reproduced."
            )
        payload = _fetch(text, timeout=timeout)
        source_url = text
        name = Path(unquote(parsed.path)).name or "document.pdf"
    elif parsed.scheme == "file":
        local = Path(url2pathname(parsed.path))
        payload = local.read_bytes()
        source_url = text
        name = local.name
    else:
        local = Path(text)
        payload = local.read_bytes()
        name = local.name

    suffix = Path(name).suffix or ".pdf"
    _digest, path = store.put(payload, suffix=suffix)
    revision = register.register(
        payload,
        doc_id=doc_id or name,
        source_url=source_url,
        local_path=str(path),
        media_type="application/pdf" if suffix.lower() == ".pdf" else "",
        revision_label=revision_label,
        retrieved_utc=datetime.now(UTC),
    )
    return DocumentSource(
        doc_id=revision.doc_id, revision=revision, path=path, source_url=source_url
    )


def _fetch(url: str, *, timeout: float) -> bytes:
    """The one network call in the package, isolated so a test can assert it is not on the path."""
    from urllib.request import Request, urlopen  # local import: keeps the module import-time pure

    request = Request(url, headers={"User-Agent": "errata-audit/0.1 (+https://example.invalid)"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()
