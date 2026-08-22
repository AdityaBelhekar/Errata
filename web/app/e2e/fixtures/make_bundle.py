#!/usr/bin/env python
"""Write the golden Evidence Bundle the JavaScript verifier is tested against.

Register H-3: ``errata_bundle.verify`` has Python tests including tamper detection.
The **JavaScript** verifier in ``console.js`` had none — and it is the one a
customer would rely on, because it is the one that runs in their browser on a
bundle we sent them. The byte-digest interop was tested in one direction only
(Python writes, ``sha256sum`` agrees); nothing asserted the browser computes the
same value.

One direction is not interop. It is a coincidence waiting to end.

This produces a real bundle from the real writer, committed as a fixture, so the
browser test verifies **digests Python actually wrote** rather than digests a test
helper invented. FE-2.5 describes the bundle format in prose, and prose does not
fail a build; this fixture does.

    python web/app/e2e/fixtures/make_bundle.py

Regenerate only when the bundle format changes — and when you do, expect
``bundle.spec.ts`` to be the thing that tells you the format change reached the
browser.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from errata_bundle.bundle import BundleWriter
from errata_bundle.fixtures import GEOMETRIES, write_fixture

HERE = Path(__file__).resolve().parent
TARGET = HERE / "bundle"


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    scratch = HERE / "_scratch"
    if scratch.exists():
        shutil.rmtree(scratch)

    # `upright` rather than a rotated geometry: this fixture exists to test DIGESTS, and a
    # rotated page would make a projection failure look like a verification failure.
    # Rotation is covered by audit/tests/test_console_geometry.py.
    spec = next(s for s in GEOMETRIES if s.name == "upright")
    pdf = write_fixture(spec, scratch / "src")

    written = BundleWriter(root=scratch / "bundles").write(
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

    shutil.copytree(written, TARGET)
    shutil.rmtree(scratch)

    files = sorted(p.relative_to(TARGET).as_posix() for p in TARGET.rglob("*") if p.is_file())
    print(f"wrote {TARGET.relative_to(HERE.parents[3])}")
    for name in files:
        print(f"  {name}")


if __name__ == "__main__":
    main()
