"""The Evidence Bundle: verification, and the cross-language property it depends on."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from errata_bundle.bundle import BundleWriter, digest_bytes, verify
from errata_bundle.fixtures import GEOMETRIES, write_fixture


@pytest.fixture
def written(tmp_path) -> Path:
    spec = next(s for s in GEOMETRIES if s.name == "upright")
    pdf = write_fixture(spec, tmp_path / "src")
    writer = BundleWriter(root=tmp_path / "bundles")
    return writer.write(
        sku="TEST-1",
        document_path=pdf,
        document_sha256="0" * 64,
        document_name=pdf.name,
        findings=[
            {
                "attribute": "rated_current",
                "catalog_value": "61 A",
                "derived_value": "16 A",
                "evidence": [
                    {"page": 1, "bbox": (72.0, 150.0, 120.0, 165.0), "table_cell": "16"}
                ],
                "counter_evidence": [],
                "counter_summary": "No supporting evidence found.",
            }
        ],
        resolved=[],
        declined=[],
        versions={"layout": "test/1", "derive": "test/1"},
    )


def test_a_fresh_bundle_verifies(written):
    ok, problems = verify(written)
    assert ok, problems


def test_every_file_is_listed_and_hashed(written):
    manifest = json.loads((written / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        assert (written / name).exists()
        assert digest_bytes((written / name).read_bytes()) == expected
    # The manifest must not carry its own digest: that is the canonicalisation trap this format
    # exists to avoid. See bundle.py's module docstring.
    assert "bundle_digest" not in manifest
    assert (written / "bundle.sha256").exists()


def test_tampering_with_a_page_is_detected(written):
    page = next((written / "pages").glob("*.png"))
    page.write_bytes(page.read_bytes() + b"tampered")
    ok, problems = verify(written)
    assert not ok
    assert any("pages/" in p for p in problems)


def test_tampering_with_the_manifest_is_detected(written):
    manifest = json.loads((written / "manifest.json").read_text(encoding="utf-8"))
    manifest["sku"] = "SOMETHING-ELSE"
    (written / "manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    ok, problems = verify(written)
    assert not ok
    assert any("manifest digest mismatch" in p for p in problems)


def test_the_digest_is_plain_sha256_of_the_manifest_bytes(written):
    """The property that makes a bundle checkable with `sha256sum` and nothing else.

    This is the whole reason the digest moved out of the manifest. If it ever again depends on
    re-serialising JSON, this test fails -- and so, silently, would every non-Python reader.
    """
    recorded = (written / "bundle.sha256").read_text(encoding="ascii").strip()
    assert recorded == digest_bytes((written / "manifest.json").read_bytes())
    assert len(recorded) == 64
    int(recorded, 16)  # hex, so a shell tool can compare it as a string


def test_the_source_pdf_is_never_copied_into_the_bundle(written):
    """FR-9.5. The bundle carries the document's hash, never its bytes."""
    assert not list(written.rglob("*.pdf"))
    manifest = json.loads((written / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["document"]["sha256"]
    assert not any(name.endswith(".pdf") for name in manifest["files"])


def test_evidence_boxes_are_stored_as_fractions(written):
    redlines = json.loads((written / "redlines.json").read_text(encoding="utf-8"))
    box = redlines["findings"][0]["evidence"][0]["box"]
    assert len(box) == 4
    assert all(0.0 <= v <= 1.0 for v in box), (
        "boxes must be page fractions, not pixels: the console scales the page freely and a pixel "
        "box would drift off its words at every size but one"
    )
    # The PDF-space bbox must not survive into the wire format -- one coordinate system per file.
    assert "bbox" not in redlines["findings"][0]["evidence"][0]
