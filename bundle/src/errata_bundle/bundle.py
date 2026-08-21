"""The Evidence Bundle -- a portable, content-addressed, offline-verifiable evidence object.

FR-7.8 requires that *"evidence shown is reconstructible from stored state, not regenerated at view
time"*, so that *"what was this reviewer looking at"* has one permanent answer (PRD §4.3). Today
that is a property the console is trusted to have. A bundle makes it structural: the console
renders **only** from a bundle and has no extractor, so there is no code path that could regenerate
evidence even if someone wanted one.

What is in it
-------------

::

    <bundle>/
      manifest.json    digests of every file below, the page projections, and the versions
      redlines.json    the findings: evidence, counter-evidence, blast radius factors
      words.json       word geometry as page fractions -- the selectable text layer
      pages/p2.png     deterministic raster of each page the evidence lands on

What is deliberately NOT in it
------------------------------

**The source PDF.** FR-9.5 forbids redistributing it and this format never contains it -- only its
SHA-256, so a holder can verify they have the same document without being given a copy.

Whether the *rendered page raster* of a copyrighted datasheet may be redistributed is a legal
question, not an engineering one, and it is **unanswered**. Until it is answered, bundles built
from third-party documents stay local: they are written under ``var/`` which is gitignored, and
nothing in this module uploads, publishes or packages them. A bundle that leaves the machine is a
decision a person makes, not a default this code takes.

Verification -- and why it hashes bytes, not structures
-------------------------------------------------------

``manifest.json`` carries the SHA-256 of every other file. ``bundle.sha256`` carries the SHA-256 of
``manifest.json``'s own bytes, and that hex string is the bundle's identity. Verifying a bundle is
therefore: hash each file's bytes, then hash the manifest's bytes. Nothing else.

The first version of this format instead stored a ``bundle_digest`` computed over a *canonical
JSON* re-serialisation of the manifest, and the console recomputed it in JavaScript. It failed on
the first real bundle, for a reason worth recording because it will be proposed again::

    Python  json.dumps(2.0)    ->  "2.0"
    JS      JSON.stringify(2)  ->  "2"

Every projection carries floats -- ``zoom``, the affine matrix, the page rect -- so the two
languages produced different bytes for the same object and every digest mismatched. RFC 8785 (JSON
Canonicalization Scheme) exists precisely for this, by mandating ECMAScript number formatting, and
implementing it would have worked.

It would also have made the correctness of stored evidence depend on two independent
implementations of a number-formatting specification agreeing forever, in every language that ever
reads a bundle. Hashing the bytes we actually wrote has no such dependency: a bundle is verifiable
by ``sha256sum``, by thirty lines of JavaScript, and by anything else that can read a file.
Canonical JSON is still used to *write* the files, so output stays deterministic -- but nothing
load-bearing depends on reproducing it.

A ledger a customer can read is good. One they can *check*, with tools they already have, is the
version of that claim worth making.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf

from .geometry import GEOMETRY_VERSION, PageProjection, project_page

__all__ = ["BUNDLE_VERSION", "BundleWriter", "canonical_json", "digest_bytes"]

#: Bump when the on-disk shape changes in a way a reader must know about.
BUNDLE_VERSION = "errata-bundle/0.1.0"

#: Render scale. Matches ``errata_audit.console.PAGE_ZOOM`` deliberately -- two renderers producing
#: two different rasters of the same page is two answers to "what did the reviewer see".
PAGE_ZOOM = 2.0


def canonical_json(payload: Any) -> bytes:
    """Deterministic JSON: sorted keys, no incidental whitespace, UTF-8.

    Mirrors ``errata_spec.determinism.canonical_payload``'s intent. It is repeated rather than
    imported so that a bundle reader -- including thirty lines of JavaScript -- can reproduce the
    digest without depending on this package.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bbox_tuple(bbox: Any) -> tuple[float, float, float, float] | None:
    """Accept a BBox model, a mapping or a 4-tuple. Returns PDF user-space coordinates."""
    if bbox is None:
        return None
    if isinstance(bbox, (tuple, list)) and len(bbox) == 4:
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    for names in (("x0", "y0", "x1", "y1"), ("left", "top", "right", "bottom")):
        if all(hasattr(bbox, n) for n in names):
            return tuple(float(getattr(bbox, n)) for n in names)  # type: ignore[return-value]
    if isinstance(bbox, dict):
        for names in (("x0", "y0", "x1", "y1"), ("left", "top", "right", "bottom")):
            if all(n in bbox for n in names):
                return tuple(float(bbox[n]) for n in names)  # type: ignore[return-value]
    return None


@dataclass
class BundleWriter:
    """Writes one Evidence Bundle for one SKU audit."""

    root: Path
    zoom: float = PAGE_ZOOM

    def write(
        self,
        *,
        sku: str,
        document_path: Path,
        document_sha256: str,
        document_name: str,
        findings: list[dict[str, Any]],
        resolved: list[dict[str, Any]],
        declined: list[dict[str, Any]],
        versions: dict[str, str],
        note: str = "",
    ) -> Path:
        """Write the bundle and return its directory.

        ``findings`` / ``resolved`` / ``declined`` are plain dictionaries rather than domain objects
        on purpose: the bundle is a *wire format*, and coupling it to the in-process class layout
        would make every future refactor of ``errata_spec`` a breaking change for stored evidence
        that must stay readable for years.
        """
        out = self.root / sku
        (out / "pages").mkdir(parents=True, exist_ok=True)

        pages_needed = sorted(
            {
                int(ev["page"])
                for record in (*findings, *resolved)
                for ev in (*record.get("evidence", []), *record.get("counter_evidence", []))
                if ev.get("page")
            }
        )

        document = pymupdf.open(str(document_path))
        projections: dict[int, PageProjection] = {}
        words_by_page: dict[str, list[dict[str, Any]]] = {}
        files: dict[str, str] = {}

        try:
            for number in pages_needed:
                page = document[number - 1]
                projection, pixmap = project_page(page, zoom=self.zoom)
                projections[number] = projection

                image = out / "pages" / f"p{number}.png"
                data = pixmap.tobytes("png")
                image.write_bytes(data)
                files[f"pages/p{number}.png"] = digest_bytes(data)

                # The selectable text layer. Fractions, not pixels, so the overlay survives the
                # page being scaled to any width -- see geometry.py.
                words = []
                for entry in page.get_text("words"):
                    box = (entry[0], entry[1], entry[2], entry[3])
                    fx0, fy0, fx1, fy1 = projection.to_fraction(box)
                    words.append(
                        {
                            "t": entry[4],
                            "b": [round(fx0, 5), round(fy0, 5), round(fx1, 5), round(fy1, 5)],
                        }
                    )
                words_by_page[str(number)] = words
        finally:
            document.close()

        # Project every evidence box into page fractions once, here, so the console never has to
        # know what a PDF is.
        def _project_record(record: dict[str, Any]) -> dict[str, Any]:
            out_record = dict(record)
            for key in ("evidence", "counter_evidence"):
                projected = []
                for ev in record.get(key, []):
                    item = dict(ev)
                    page = int(ev.get("page") or 0)
                    box = _bbox_tuple(ev.get("bbox"))
                    if page in projections and box:
                        fx0, fy0, fx1, fy1 = projections[page].to_fraction(box)
                        item["box"] = [round(fx0, 5), round(fy0, 5), round(fx1, 5), round(fy1, 5)]
                    item.pop("bbox", None)
                    projected.append(item)
                out_record[key] = projected
            return out_record

        redlines = {
            "sku": sku,
            "findings": [_project_record(f) for f in findings],
            "resolved": [_project_record(r) for r in resolved],
            "declined": declined,
        }

        payloads = {
            "redlines.json": canonical_json(redlines),
            "words.json": canonical_json(words_by_page),
        }
        for name, data in payloads.items():
            (out / name).write_bytes(data)
            files[name] = digest_bytes(data)

        manifest = {
            "bundle_version": BUNDLE_VERSION,
            "geometry_version": GEOMETRY_VERSION,
            "sku": sku,
            "document": {
                "name": document_name,
                "sha256": document_sha256,
                "pages": pages_needed,
            },
            "projections": {str(n): p.as_dict() for n, p in projections.items()},
            "versions": dict(sorted(versions.items())),
            "files": dict(sorted(files.items())),
            "note": note,
        }
        manifest_bytes = canonical_json(manifest)
        (out / "manifest.json").write_bytes(manifest_bytes)
        # The bundle's identity, in a sibling file rather than inside the manifest. A digest cannot
        # live inside the thing it digests without a canonicalisation dance, and that dance is what
        # broke cross-language verification -- see the module docstring.
        (out / "bundle.sha256").write_text(
            digest_bytes(manifest_bytes) + "\n", encoding="ascii"
        )
        return out


def verify(bundle: Path) -> tuple[bool, list[str]]:
    """Recompute every digest in a bundle. Returns ``(ok, problems)``.

    The same checks the console performs in the browser, on the same bytes: every file matches its
    recorded hash, the manifest matches the digest in ``bundle.sha256``, and no file is listed that
    is not present.
    """
    problems: list[str] = []
    manifest_path = bundle / "manifest.json"
    digest_path = bundle / "bundle.sha256"
    if not manifest_path.exists():
        return False, ["manifest.json missing"]
    if not digest_path.exists():
        return False, ["bundle.sha256 missing"]

    manifest_bytes = manifest_path.read_bytes()
    recorded = digest_path.read_text(encoding="ascii").strip()
    recomputed = digest_bytes(manifest_bytes)
    if recorded != recomputed:
        problems.append(f"manifest digest mismatch: recorded {recorded}, recomputed {recomputed}")

    manifest = json.loads(manifest_bytes.decode("utf-8"))
    for name, expected in manifest.get("files", {}).items():
        path = bundle / name
        if not path.exists():
            problems.append(f"{name}: listed in manifest, missing on disk")
            continue
        actual = digest_bytes(path.read_bytes())
        if actual != expected:
            problems.append(f"{name}: digest mismatch")

    return not problems, problems
