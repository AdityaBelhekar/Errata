"""FR-1.3 — the Document Register. Content-addressed storage with a revision history.

``Evidence.doc_revision_sha256`` is a required, 64-character field: a claim cannot be constructed
without naming the exact bytes it was derived from. Until now nothing in this repository *produced*
one. This module closes that loop.

The register answers three questions, and they are different questions:

* **"What bytes were these?"** -- the sha256 of the file, which is the identity. Two documents with
  identical bytes are one document however many times they are fetched, from however many URLs.
* **"Where did they come from, and when?"** -- source URL and retrieval timestamp, recorded per
  *fetch*, because the same bytes can legitimately arrive from several places.
* **"What came before?"** -- the revision chain. A supplier reposting a datasheet at the same URL
  does not invalidate the claims made against the old one; it makes them **historical rather than
  wrong**, which is a distinction the product is built on and which only a chain can express.

Design notes worth keeping:

**Identity is the hash, not the URL.** URLs are not stable, are not unique, and are frequently
reused for revised content -- which is exactly the case the register exists to catch. A register
keyed on URL would silently overwrite the evidence for every historical claim.

**Re-fetching identical bytes is not an event.** FR-1.3 requires that it "does not create a second
record". It does update the *fetch* log, because knowing a document was still live last Tuesday is
worth something, but the document and its id do not change.

**Nothing is deleted.** There is no removal method, and that is deliberate rather than an
omission: a claim pointing at a revision that has been deleted is unreconstructible, and
"what was this reviewer looking at" must have one permanent answer (§4.3, FR-7.8).

**No network calls.** The register stores and indexes bytes handed to it. Fetching is somebody
else's job, which keeps this testable without a network and keeps the deterministic core
deterministic.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "DocumentRegister",
    "DocumentRevision",
    "Fetch",
    "RevisionNotFoundError",
    "sha256_bytes",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RevisionNotFoundError(KeyError):
    """Raised when a revision hash is not in the register.

    A distinct type because the caller almost always wants to handle it differently from a
    missing dictionary key: an unknown revision means a claim references evidence the register
    cannot produce, which is a data-integrity problem, not a lookup miss.
    """


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


class Fetch(BaseModel):
    """One retrieval of one set of bytes.

    Separate from the revision because they have different cardinality: the same bytes can be
    fetched many times, from many URLs, and each of those is a fact worth keeping. Collapsing
    them into the revision would mean either losing fetches or duplicating documents.
    """

    model_config = ConfigDict(frozen=True)

    source_url: str = ""
    """Empty for a local file. Not an identifier -- see the module docstring."""

    retrieved_utc: datetime = Field(default_factory=_now)
    local_path: str = ""
    note: str = ""


class DocumentRevision(BaseModel):
    """One immutable version of one document."""

    model_config = ConfigDict(frozen=True)

    sha256: str = Field(min_length=64, max_length=64)
    """The identity. Matches ``Evidence.doc_revision_sha256`` exactly."""

    doc_id: str
    """Stable across revisions. Every revision of the same logical document shares it, which is
    what makes 'the current version of this datasheet' a question with an answer."""

    byte_length: int = Field(ge=0)
    media_type: str = ""

    revision_label: str = ""
    """Only when the document declares one on its face -- '09/2024', 'Rev C'. Never inferred: a
    guessed revision label is worse than none, because it reads as having been read off the page."""

    supersedes: str = ""
    """sha256 of the revision this one replaced, or empty for the first. The chain, not a flag."""

    fetches: tuple[Fetch, ...] = ()

    @model_validator(mode="after")
    def _hashes_are_well_formed(self) -> DocumentRevision:
        if not _SHA256_RE.match(self.sha256):
            raise ValueError(f"sha256 {self.sha256!r} is not 64 lowercase hex characters")
        if self.supersedes and not _SHA256_RE.match(self.supersedes):
            raise ValueError(f"supersedes {self.supersedes!r} is not a sha256")
        if self.supersedes == self.sha256:
            raise ValueError("a revision cannot supersede itself")
        if not self.doc_id:
            raise ValueError("doc_id must not be empty")
        return self

    @property
    def is_first_revision(self) -> bool:
        return not self.supersedes


class DocumentRegister:
    """An append-only, content-addressed store of document revisions.

    In-memory with an explicit JSON snapshot, rather than a database, because the spike needs it
    now and R1 will decide the storage question on its own evidence. The *interface* is the part
    intended to survive: `register`, `get`, `history`, `current`.
    """

    def __init__(self) -> None:
        self._by_sha: dict[str, DocumentRevision] = {}
        self._by_doc: dict[str, list[str]] = {}

    # -- writing ---------------------------------------------------------------------------

    def register(
        self,
        payload: bytes,
        *,
        doc_id: str,
        source_url: str = "",
        local_path: str = "",
        media_type: str = "",
        revision_label: str = "",
        note: str = "",
        retrieved_utc: datetime | None = None,
    ) -> DocumentRevision:
        """Store bytes, or record another fetch of bytes already stored.

        Returns the revision either way. Idempotent on the bytes: FR-1.3's "re-fetching identical
        bytes does not create a second record" is the whole contract here, and the natural
        implementation -- append a revision per call -- gets it wrong in a way that only shows up
        much later, as a revision history full of a document that never changed.
        """
        if not doc_id:
            raise ValueError("doc_id must not be empty")

        digest = sha256_bytes(payload)
        fetch = Fetch(
            source_url=source_url,
            local_path=local_path,
            note=note,
            retrieved_utc=retrieved_utc or _now(),
        )

        existing = self._by_sha.get(digest)
        if existing is not None:
            if existing.doc_id != doc_id:
                raise ValueError(
                    f"bytes {digest[:12]}... are already registered under doc_id "
                    f"{existing.doc_id!r}; the same bytes cannot be two documents. If two "
                    f"logical documents genuinely share a file, they share a revision."
                )
            updated = existing.model_copy(update={"fetches": (*existing.fetches, fetch)})
            self._by_sha[digest] = updated
            return updated

        chain = self._by_doc.setdefault(doc_id, [])
        revision = DocumentRevision(
            sha256=digest,
            doc_id=doc_id,
            byte_length=len(payload),
            media_type=media_type,
            revision_label=revision_label,
            supersedes=chain[-1] if chain else "",
            fetches=(fetch,),
        )
        self._by_sha[digest] = revision
        chain.append(digest)
        return revision

    def register_path(self, path: Path | str, *, doc_id: str, **kwargs: object) -> DocumentRevision:
        """Convenience wrapper: read a local file and register its bytes."""
        path = Path(path)
        kwargs.setdefault("local_path", str(path))
        return self.register(path.read_bytes(), doc_id=doc_id, **kwargs)  # type: ignore[arg-type]

    # -- reading ---------------------------------------------------------------------------

    def get(self, sha256: str) -> DocumentRevision:
        try:
            return self._by_sha[sha256]
        except KeyError as exc:
            raise RevisionNotFoundError(
                f"no revision {sha256[:12]}... in the register. A claim referencing it cannot be "
                f"reconstructed, which is a data-integrity problem rather than a cache miss."
            ) from exc

    def __contains__(self, sha256: object) -> bool:
        return sha256 in self._by_sha

    def __len__(self) -> int:
        return len(self._by_sha)

    def __iter__(self) -> Iterator[DocumentRevision]:
        return iter(self._by_sha.values())

    def history(self, doc_id: str) -> tuple[DocumentRevision, ...]:
        """Every revision of one document, oldest first."""
        return tuple(self._by_sha[h] for h in self._by_doc.get(doc_id, ()))

    def current(self, doc_id: str) -> DocumentRevision | None:
        """The newest revision, or None if the document is unknown.

        "Newest" means last registered, not newest by any timestamp in the document. A supplier's
        own dating is unreliable and frequently absent; arrival order is a fact we observed.
        """
        chain = self._by_doc.get(doc_id)
        return self._by_sha[chain[-1]] if chain else None

    def doc_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_doc))

    def is_superseded(self, sha256: str) -> bool:
        """True when a newer revision of the same document exists.

        The question a reviewer actually asks, and the reason claims against an old revision are
        *historical* rather than wrong: the evidence was accurate when it was taken.
        """
        revision = self.get(sha256)
        chain = self._by_doc[revision.doc_id]
        return chain[-1] != sha256

    # -- persistence -----------------------------------------------------------------------

    def to_json(self) -> str:
        """Snapshot, ordered deterministically so two identical registers serialise identically."""
        return json.dumps(
            {
                "schema": "errata-document-register/1",
                "revisions": [
                    json.loads(self._by_sha[h].model_dump_json())
                    for doc in sorted(self._by_doc)
                    for h in self._by_doc[doc]
                ],
            },
            indent=2,
            sort_keys=False,
        )

    @classmethod
    def from_json(cls, text: str) -> DocumentRegister:
        payload = json.loads(text)
        schema = payload.get("schema", "")
        if schema != "errata-document-register/1":
            raise ValueError(f"unknown register schema {schema!r}")
        register = cls()
        for raw in payload["revisions"]:
            revision = DocumentRevision.model_validate(raw)
            register._by_sha[revision.sha256] = revision
            register._by_doc.setdefault(revision.doc_id, []).append(revision.sha256)
        register._verify_chains()
        return register

    def _verify_chains(self) -> None:
        """A loaded register must have intact revision chains.

        Reconstructing history from a file that has been hand-edited -- and these files will be
        hand-edited -- must fail loudly rather than produce a plausible wrong history.
        """
        for doc_id, chain in self._by_doc.items():
            expected = ""
            for digest in chain:
                revision = self._by_sha[digest]
                if revision.supersedes != expected:
                    raise ValueError(
                        f"broken revision chain for {doc_id!r}: {digest[:12]}... claims to "
                        f"supersede {revision.supersedes[:12] or '(nothing)'}..., but the "
                        f"preceding revision is {expected[:12] or '(nothing)'}..."
                    )
                expected = digest
