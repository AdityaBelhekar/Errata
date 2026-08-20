"""FR-7.1 - FR-7.9 -- the console, and the command that is the README hook.

The console requirements are unusually specific about *how* a thing is shown, and two of them are
easy to satisfy visually and fail structurally:

* **FR-7.5** -- a queue row is a sentence, never a bare confidence percentage. Tested by asserting
  that no rendered queue row contains a percent-formatted score.
* **FR-7.4** -- the counter-evidence panel is never empty and never absent. Tested by rendering a
  finding that has no counter-evidence and asserting the panel is still there, saying so.

The box-placement test is the one that would otherwise be caught only by eye: a percentage rectangle
computed with the wrong scale still renders, still looks plausible, and lands on the wrong words.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import etim_archive, requires_etim

from errata_audit.attributes import load_attributes
from errata_audit.audit import audit_sku
from errata_audit.classify import load_scope
from errata_audit.cli import main
from errata_audit.console import PageImage, render_html, render_text
from errata_audit.etim import load_etim
from errata_audit.ingest import record_from_mapping
from errata_audit.layout import extract_layer

pytestmark = requires_etim

ATTRIBUTES = load_attributes()


@pytest.fixture(scope="module")
def etim():
    return load_etim(etim_archive(), release="10.0", class_ids=load_scope().as_set)


@pytest.fixture
def result(etim, ordering_table_pdf: Path, source_of):
    record = record_from_mapping(
        {
            "sku": "AX-16",
            "mpn": "AX-16",
            "manufacturer": "ACME",
            "description": "miniature circuit breaker",
            "rated_current": "61 A",
            "poles": "1",
            "packaging_uom": "5 pcs",
            "weight_kg": "0.125 kg",
            # Carried so the rendered report has a populated Declined bucket: this document states
            # no order code, and "we looked and could not ground it" is a row a reviewer must see.
            "order_code": "2CDS271061R0165",
        }
    )
    return audit_sku(
        record,
        source_of(ordering_table_pdf, doc_id="acme-ordering"),
        etim=etim,
        scope=load_scope(),
        attributes=ATTRIBUTES,
    )


# ------------------------------------------------------------------------------------------------
# Text
# ------------------------------------------------------------------------------------------------


def test_the_text_report_reads_as_sentences_not_as_a_score(result) -> None:
    text = render_text(result)
    assert "Catalog says '61 A'. The evidence says '16 A'" in text
    # FR-7.5: no percentage anywhere near the queue row.
    queue_block = text.split("FINDINGS")[1].split("DECLINED")[0]
    assert not re.search(r"\d+(\.\d+)?\s?%", queue_block)


def test_the_report_states_that_the_confidence_is_not_calibrated(result) -> None:
    assert "NOT CALIBRATED" in render_text(result)


def test_the_report_names_the_document_revision(result) -> None:
    assert result.document.sha256 in render_text(result)


def test_the_report_shows_the_declined_bucket_with_reasons(result) -> None:
    text = render_text(result)
    assert "DECLINED" in text
    for outcome in result.declined:
        assert outcome.declined_reason.value in text


def test_the_report_shows_what_was_checked_and_found_supported(result) -> None:
    """"We looked and it was fine" is a recorded outcome, not silence."""
    assert "CHECKED AND SUPPORTED" in render_text(result)


def test_counter_evidence_appears_even_when_there_is_none(result) -> None:
    assert "No independent evidence supports the catalog value" in render_text(result)


# ------------------------------------------------------------------------------------------------
# HTML
# ------------------------------------------------------------------------------------------------


def test_the_html_is_one_self_contained_file(result, ordering_table_pdf: Path) -> None:
    html = render_html(result, layer=extract_layer(ordering_table_pdf))
    assert html.startswith("<!doctype html>")
    assert "data:image/png;base64," in html
    assert "<script src=" not in html and "https://" not in html.split("</head>")[0]


def test_the_three_panes_are_present(result) -> None:
    html = render_html(result)
    assert ">Queue<" in html
    assert ">Evidence<" in html
    assert ">Claim history<" in html


def test_the_value_and_its_headers_are_boxed_in_different_colours(result) -> None:
    html = render_html(result)
    assert "class='box '" in html or "class='box'" in html
    assert "class='box header'" in html


def test_a_box_is_placed_as_a_percentage_of_the_rendered_page() -> None:
    """A rectangle computed with the wrong scale still renders and still looks plausible. The
    arithmetic is pinned here because the failure is invisible in a screenshot."""
    image = PageImage(page=1, width=800, height=600, data_uri="", zoom=2.0)
    left, top, width, height = image.place((100.0, 150.0, 120.0, 160.0))
    assert (left, top) == pytest.approx((25.0, 50.0))
    assert (width, height) == pytest.approx((5.0, 3.3333), rel=1e-3)


def test_the_html_states_that_the_catalog_is_constructed(result) -> None:
    """The demo's honesty caveat travels on the face of the report, not in a README nobody opens."""
    html = render_html(result)
    assert "catalog under audit is constructed" in html
    assert "raw scores, not calibrated" in html


def test_the_ocr_layer_toggle_shows_what_the_machine_read(result, ordering_table_pdf: Path) -> None:
    """FR-7.7. A reviewer who cannot see what was actually read has to take the box on trust, and
    the product is an argument against doing that."""
    html = render_html(result, layer=extract_layer(ordering_table_pdf))
    assert "What the machine read" in html
    assert "AX-16" in html


def test_the_class_resolution_stages_are_shown(result) -> None:
    html = render_html(result)
    assert "three stages" in html
    assert "EC000042" in html


def test_html_escapes_its_inputs(etim, ordering_table_pdf: Path, source_of) -> None:
    record = record_from_mapping(
        {
            "sku": "<script>alert(1)</script>",
            "mpn": "AX-16",
            "description": "miniature circuit breaker",
            "rated_current": "61 A",
            "poles": "1",
        }
    )
    audit = audit_sku(
        record,
        source_of(ordering_table_pdf, doc_id="acme"),
        etim=etim,
        scope=load_scope(),
        attributes=ATTRIBUTES,
    )
    html = render_html(audit)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ------------------------------------------------------------------------------------------------
# CLI -- FR-7.9
# ------------------------------------------------------------------------------------------------


def test_status_runs_and_says_what_is_not_built(capsys) -> None:
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "NOT" in out
    assert "calibration" in out


def test_the_exit_code_is_one_when_there_are_findings(tmp_path: Path, capsys) -> None:
    """The exit code is the decision, not a diagnostic. A command that exits 0 whether or not it
    found a poisoned record cannot be put in a pipeline."""
    catalog = tmp_path / "c.csv"
    catalog.write_text(
        "sku,mpn,manufacturer,description,rated_current,poles\n"
        "S201M-B16UC,S201M-B16UC,ABB,miniature circuit breaker,61 A,1\n",
        "utf-8",
    )
    code = main(
        ["sku", "--catalog", str(catalog), "--sku", "S201M-B16UC", "--blobs", str(tmp_path / "b")]
    )
    out = capsys.readouterr().out
    if "no source document" in out.lower():
        pytest.skip("the ABB datasheets are not present in this clone")
    assert code == 1
    assert "SEV-1" in out
    # Two datasheets are on disk and the record names neither: the one containing this type
    # designation was chosen on evidence, not by sort order.
    assert "abb-s200-" in out


def test_a_record_naming_a_missing_document_declines_rather_than_using_another(
    tmp_path: Path, capsys
) -> None:
    catalog = tmp_path / "c.csv"
    catalog.write_text(
        "sku,mpn,datasheet,rated_current\nAX-16,AX-16,nowhere.pdf,16 A\n", "utf-8"
    )
    code = main(["sku", "--catalog", str(catalog), "--sku", "AX-16", "--blobs", str(tmp_path / "b")])
    assert code == 2
    assert "no_source_document" in capsys.readouterr().out


def test_a_network_datasheet_is_refused_without_permission(tmp_path: Path, capsys) -> None:
    catalog = tmp_path / "c.csv"
    catalog.write_text("sku,mpn,rated_current\nAX-16,AX-16,16 A\n", "utf-8")
    code = main(
        [
            "sku",
            "--catalog",
            str(catalog),
            "--sku",
            "AX-16",
            "--datasheet",
            "https://example.invalid/x.pdf",
            "--blobs",
            str(tmp_path / "b"),
        ]
    )
    assert code == 3
    assert "not permitted to fetch" in capsys.readouterr().err


def test_a_non_loopback_bind_is_refused_unless_the_operator_means_it(tmp_path: Path, capsys) -> None:
    """The console has no authentication and renders a customer's catalog beside a manufacturer's
    document. Putting that on a network interface should cost a flag and a sentence, not a default.
    """
    catalog = tmp_path / "c.csv"
    catalog.write_text("sku,mpn,rated_current\nAX-16,AX-16,16 A\n", "utf-8")
    code = main(
        ["serve", "--catalog", str(catalog), "--host", "0.0.0.0", "--blobs", str(tmp_path / "b")]
    )
    assert code == 3
    assert "no authentication" in capsys.readouterr().err


def test_a_redline_id_is_stable_across_runs(tmp_path: Path, capsys) -> None:
    """It began as a usability bug -- the adjudication command the CLI prints stopped working after
    a re-run -- and it is a correctness one: a decision has to attach to a finding that can be
    reproduced, and a ledger with one row per run per finding cannot answer "was this decided?".
    """
    catalog = tmp_path / "c.csv"
    catalog.write_text(
        "sku,mpn,manufacturer,description,rated_current,poles\n"
        "S201M-B16UC,S201M-B16UC,ABB,miniature circuit breaker,61 A,1\n",
        "utf-8",
    )
    ids = []
    for _ in range(2):
        main(
            [
                "sku", "--catalog", str(catalog), "--sku", "S201M-B16UC",
                "--blobs", str(tmp_path / "b"), "--json",
            ]
        )
        out = capsys.readouterr().out
        if "no source document" in out.lower():
            pytest.skip("the ABB datasheets are not present in this clone")
        ids.append(json.loads(out)["outcomes"])
    first = [o["redline_id"] for o in ids[0] if o["redline_id"]]
    second = [o["redline_id"] for o in ids[1] if o["redline_id"]]
    assert first and first == second
