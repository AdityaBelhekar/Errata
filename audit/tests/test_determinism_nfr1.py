"""NFR-1 -- run the pipeline twice over the same bytes and diff the payloads.

Determinism was asserted in prose in half a dozen places and tested in none of them end to end.
``layout.py`` stamps a version "whenever anything changes that could move a char offset";
``derive.py`` describes itself as "deterministic and parameterless"; ``valuesem`` forbids network
and model calls. Each of those is a claim about one component. NFR-1 is a claim about the whole
pipeline, and its acceptance criterion is an experiment, not an assertion: *"Re-run produces
byte-identical claim payloads excluding timestamps and ids."*

Nobody had run it. These tests run it.

**Why this matters more here than in most codebases.** ``Evidence.char_span`` is an offset into a
canonical text layer. A claim made last month is only reconstructible if the same bytes still
produce the same offsets, and a pipeline that reorders words between runs silently invalidates
every stored claim while every unit test still passes -- because each component is individually
correct and the composition is not. That is precisely the class of bug an end-to-end diff catches
and a per-module test cannot.

Two runs are compared **in the same process**, and that is a deliberate limitation worth stating:
it catches iteration-order instability, unsorted collections and floating-point formatting drift.
It does **not** catch hash-randomisation across processes, because ``PYTHONHASHSEED`` is fixed
within one interpreter. ``test_the_pipeline_is_deterministic_across_processes`` covers that by
actually starting a second interpreter, which is slower and is the only way to test the thing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from conftest import etim_archive, requires_etim

from errata_audit.audit import audit_sku
from errata_audit.classify import load_scope
from errata_audit.etim import load_etim
from errata_audit.ingest import record_from_mapping
from errata_spec.determinism import (
    MINIMUM_RETAINED,
    NotReproducible,
    assert_reproducible,
    canonical_payload,
)

pytestmark = requires_etim

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def etim():
    return load_etim(etim_archive(), release="10.0", class_ids=load_scope().as_set)


def _record(datasheet: Path):
    return record_from_mapping(
        {
            "sku": "AX-16",
            "mpn": "AX-16",
            "manufacturer": "ACME",
            "description": "miniature circuit breaker",
            "datasheet": str(datasheet),
            "rated_current": "16 A",
            "poles": "1",
            "packaging_uom": "5 pcs",
            "weight_kg": "0.125 kg",
        }
    )


# ------------------------------------------------------------------------------------------------
# The experiment NFR-1 asks for
# ------------------------------------------------------------------------------------------------


def test_two_runs_of_one_audit_produce_identical_payloads(
    etim, ordering_table_pdf: Path, source_of
) -> None:
    """The whole R1 audit, twice, diffed field by field."""
    document = source_of(ordering_table_pdf, doc_id="acme-ordering")
    scope = load_scope()
    record = _record(ordering_table_pdf)

    first = audit_sku(record, document, etim=etim, scope=scope)
    second = audit_sku(record, document, etim=etim, scope=scope)

    payload = assert_reproducible(first, second, what="R1 audit of AX-16")
    assert payload.retained >= MINIMUM_RETAINED
    assert payload.elided > 0, (
        "nothing was elided, so either the audit emitted no ids or timestamps at all -- which "
        "would be surprising -- or VOLATILE_FIELDS has stopped matching the field names. Either "
        "way this comparison is not testing what it claims to."
    )


def test_the_declined_bucket_is_deterministic_too(etim, scanned_pdf: Path, source_of) -> None:
    """An abstention is a payload like any other, and its *reason* has to be stable.

    A pipeline that declined for one reason on Monday and another on Tuesday over identical bytes
    would be worse than a wrong answer: the reason is what a reviewer acts on.
    """
    document = source_of(scanned_pdf, doc_id="acme-scan")
    scope = load_scope()
    record = _record(scanned_pdf)

    first = audit_sku(record, document, etim=etim, scope=scope)
    second = audit_sku(record, document, etim=etim, scope=scope)

    assert first.outcomes, "the scanned document produced no outcomes at all"
    assert canonical_payload(first).text == canonical_payload(second).text


def test_the_text_layer_and_its_spans_are_stable(ordering_table_pdf: Path) -> None:
    """The foundation the rest of it rests on: same bytes, same offsets, same boxes.

    Checked separately from the audit because when the audit diff fails, this is the first thing
    to look at, and a test that has already isolated it saves the bisect.
    """
    from errata_audit.layout import extract_layer

    first = extract_layer(ordering_table_pdf)
    second = extract_layer(ordering_table_pdf)

    assert first.sha256 == second.sha256
    assert [(w.text, w.start, w.end, w.bbox) for w in first.words] == [
        (w.text, w.start, w.end, w.bbox) for w in second.words
    ]


# ------------------------------------------------------------------------------------------------
# The part one process cannot test
# ------------------------------------------------------------------------------------------------


@pytest.mark.slow
def test_the_pipeline_is_deterministic_across_processes(ordering_table_pdf: Path) -> None:
    """Two interpreters, two different hash seeds, one answer.

    Within a single process ``PYTHONHASHSEED`` is fixed, so an unordered set or a dict keyed on
    something hashed by identity can iterate consistently all day and still differ on the next
    run. This is the only way to find that, and it is why the test pays for a subprocess.
    """
    script = textwrap.dedent(
        """
        import json, sys
        from pathlib import Path
        from errata_audit.layout import extract_layer
        from errata_audit.tables import extract_tables
        from errata_spec.determinism import canonical_payload

        path = Path(sys.argv[1])
        layer = extract_layer(path)
        tables = extract_tables(path)
        payload = canonical_payload(
            {
                "text_sha256": layer.sha256,
                "words": [(w.text, w.start, w.end, w.bbox) for w in layer.words],
                "cells": [
                    (c.text, c.page, c.row, c.column, c.bbox, c.column_header)
                    for t in tables
                    for c in t.cells
                ],
            }
        )
        print(json.dumps({"digest": payload.digest, "retained": payload.retained}))
        """
    )

    def run(seed: str) -> dict:
        completed = subprocess.run(
            [sys.executable, "-c", script, str(ordering_table_pdf)],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": "", "SYSTEMROOT": ""} | _inherited_env(),
        )
        return json.loads(completed.stdout.strip().splitlines()[-1])

    first = run("0")
    second = run("12345")

    assert first["retained"] >= MINIMUM_RETAINED, "the subprocess produced almost nothing"
    assert first["digest"] == second["digest"], (
        "the layout and table pass produced different output under two hash seeds. Something in "
        "the path iterates a set or a dict keyed on object identity, and every stored char_span "
        "made by this pipeline is therefore only reproducible by luck (NFR-1)."
    )


def _inherited_env() -> dict[str, str]:
    """The minimum a subprocess needs to import the packages, and nothing else.

    Passed explicitly rather than inheriting ``os.environ`` wholesale so the child cannot pick up
    a stray setting that makes it agree with the parent for a reason unrelated to determinism.
    """
    import os

    keep = ("PATH", "SYSTEMROOT", "PYTHONPATH", "VIRTUAL_ENV", "TEMP", "TMP", "HOME")
    return {name: os.environ[name] for name in keep if name in os.environ}


# ------------------------------------------------------------------------------------------------
# The guard on the guard
# ------------------------------------------------------------------------------------------------


def test_a_set_in_the_payload_is_a_failure_not_something_to_sort() -> None:
    """Sorting a set to make a determinism test pass is fixing the thermometer."""
    with pytest.raises(NotReproducible, match="no defined iteration order"):
        canonical_payload({"tags": {"a", "b", "c"}})


def test_a_payload_that_is_mostly_holes_cannot_pass() -> None:
    """Two runs that agree about almost nothing agree trivially."""
    thin = {"claim_id": "x", "asserted_at": "y"}
    with pytest.raises(NotReproducible, match="below the"):
        assert_reproducible(thin, thin, what="a payload with no content")


def test_ids_and_timestamps_are_elided_but_evidence_is_not() -> None:
    """The exclusion list must not grow to cover the fields a re-run is meant to reproduce."""
    payload = canonical_payload(
        {
            "claim_id": "should-be-gone",
            "asserted_at": "should-be-gone",
            "doc_revision_sha256": "must-stay",
            "char_span": [10, 14],
            "value_raw": "16 A",
        }
    )
    assert "should-be-gone" not in payload.text
    assert "must-stay" in payload.text
    assert "16 A" in payload.text
    assert payload.elided == 2
