"""``errata-scale`` -- the command surface.

    "The exit code is the decision, not a diagnostic."

A CLI that exits 0 whether or not it found a poisoned record is a CLI nobody can put in a pipeline,
so the exit codes are tested as behaviour rather than documented as intent. The rest of this file
checks the things a person actually relies on at the terminal: that the banner naming the corpus as
constructed cannot be lost, that a missing corpus produces an instruction rather than a traceback,
and that the safety-class rule stops a drain before it writes anything.
"""

from __future__ import annotations

import json

from scalefixtures import catalog_of, ledger_path, row  # noqa: F401

from errata_audit import Ledger
from errata_scale.cli import EXIT_CLEAN, EXIT_ERROR, EXIT_FINDINGS, EXIT_NOT_RUN, main


def _defects(prefix: str = "A") -> list[dict[str, str]]:
    return [
        row(f"{prefix}-1", mpn=f"MPN-{prefix}", rated_current="16 A"),
        row(f"{prefix}-2", mpn=f"MPN-{prefix}", rated_current="16 A"),
        row(f"{prefix}-3", mpn=f"MPN-{prefix}", rated_current="61 A"),
    ]


def test_status_says_what_r2_declines_to_claim(capsys):
    assert main(["status"]) == EXIT_CLEAN
    out = capsys.readouterr().out
    assert "what it does NOT claim" in out
    assert "no calibration set" in out
    assert "CONSTRUCTED" in out
    assert "never writes to a customer PIM" in out


def test_policy_prints_the_version_that_would_resolve(capsys):
    assert main(["policy"]) == EXIT_CLEAN
    out = capsys.readouterr().out
    assert "electrical-conservative@v3" in out
    assert "safety_class_override" in out
    assert "records the policy version that resolved it" in out


def test_integrity_passes_over_the_repository(capsys):
    assert main(["integrity"]) == EXIT_CLEAN
    assert "FR-8.2 OK" in capsys.readouterr().out


def test_a_run_with_findings_exits_one(capsys, catalog_of):
    catalog = catalog_of(_defects())
    assert main(["run", "--catalog", str(catalog), "--no-documents"]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "GROUNDABLE FRACTION" in out
    assert "TIERED EXECUTION" in out
    assert "QUEUE" in out


def test_a_clean_run_exits_zero(capsys, catalog_of):
    catalog = catalog_of([row("CLEAN-1"), row("CLEAN-2")])
    assert main(["run", "--catalog", str(catalog), "--no-documents"]) == EXIT_CLEAN


def test_a_missing_catalog_gives_an_instruction_rather_than_a_traceback(capsys, tmp_path):
    assert main(["run", "--catalog", str(tmp_path / "nope.csv")]) == EXIT_NOT_RUN
    assert "errata-scale corpus" in capsys.readouterr().err


def test_the_json_report_carries_the_whole_shape(capsys, catalog_of):
    catalog = catalog_of(_defects())
    main(["run", "--catalog", str(catalog), "--no-documents", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["groundable_fraction_report"]["percentages_sum"] is True
    assert payload["cost_report"]["scales_with_error_count"] is True
    assert payload["findings"]["total"] == len(payload["queue"])
    assert payload["clusters"][0]["size"] >= 1
    assert payload["queue"][0]["factors"]


def test_the_html_report_is_self_contained(capsys, catalog_of, tmp_path):
    catalog = catalog_of(_defects())
    out = tmp_path / "report.html"
    main(["run", "--catalog", str(catalog), "--no-documents", "--html", str(out)])
    html = out.read_text("utf-8")
    assert html.startswith("<!doctype html>")
    assert "Groundable fraction" in html
    assert "never writes to a catalog" in html
    # no network: a report a customer opens must not phone anywhere
    for scheme in ("http://", "https://", "src=", "<script"):
        assert scheme not in html


def test_groundable_enumerates_a_bucket_to_record_level(capsys, catalog_of):
    catalog = catalog_of([row("A-1", datasheet="missing.pdf"), row("A-2")])
    assert (
        main(
            [
                "groundable",
                "--catalog",
                str(catalog),
                "--bucket",
                "document_named_not_supplied",
            ]
        )
        == EXIT_CLEAN
    )
    out = capsys.readouterr().out
    assert "A-1" in out
    assert "missing.pdf" in out


def test_an_unknown_bucket_is_refused_by_name(capsys, catalog_of):
    catalog = catalog_of([row("A-1")])
    assert main(["groundable", "--catalog", str(catalog), "--bucket", "nonsense"]) == EXIT_ERROR
    assert "expected one of" in capsys.readouterr().err


def test_clusters_report_the_fingerprint_next_to_the_count(capsys, catalog_of):
    catalog = catalog_of(_defects("A") + _defects("B"))
    assert main(["clusters", "--catalog", str(catalog), "--no-documents"]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "error signature(s)" in out
    assert "there is no field for a" in out


def test_a_drain_refuses_to_start_without_a_second_adjudicator(capsys, catalog_of, ledger_path):
    """FR-8.9, at the command surface: the run stops before it writes rather than on row one."""
    catalog = catalog_of(_defects())
    code = main(
        [
            "drain",
            "--catalog",
            str(catalog),
            "--no-documents",
            "--ledger",
            str(ledger_path),
            "--by",
            "A. Reviewer",
        ]
    )
    assert code == EXIT_ERROR
    assert "second named adjudicator" in capsys.readouterr().err
    assert Ledger(ledger_path).of_kind("scale_decision") == ()


def test_drain_then_reverse_round_trips(capsys, catalog_of, ledger_path):
    catalog = catalog_of(_defects())
    assert (
        main(
            [
                "drain",
                "--catalog",
                str(catalog),
                "--no-documents",
                "--ledger",
                str(ledger_path),
                "--by",
                "A. Reviewer",
                "--second",
                "B. Reviewer",
            ]
        )
        == EXIT_CLEAN
    )
    out = capsys.readouterr().out
    assert "SCRIPTED DECISIONS -- NOT HUMAN REVIEW." in out
    batch = out.split("reverse it with:  errata-scale reverse --batch ")[1].split(" ")[0]

    assert main(["reverse", "--ledger", str(ledger_path), "--batch", batch, "--by", "C"]) == EXIT_CLEAN
    reversed_out = capsys.readouterr().out
    assert "Nothing was deleted." in reversed_out

    assert main(["chain", "--ledger", str(ledger_path), "--sku", "A-3"]) == EXIT_CLEAN
    assert "->" in capsys.readouterr().out


def test_a_dry_run_reversal_changes_nothing(capsys, catalog_of, ledger_path):
    catalog = catalog_of(_defects())
    main(
        [
            "drain",
            "--catalog",
            str(catalog),
            "--no-documents",
            "--ledger",
            str(ledger_path),
            "--by",
            "A. Reviewer",
            "--second",
            "B. Reviewer",
        ]
    )
    capsys.readouterr()
    before = ledger_path.read_text("utf-8")
    batch = str(Ledger(ledger_path).of_kind("scale_batch")[0].payload["batch_id"])
    assert (
        main(["reverse", "--ledger", str(ledger_path), "--batch", batch, "--by", "C", "--dry-run"])
        == EXIT_CLEAN
    )
    assert "would be reversed" in capsys.readouterr().out
    assert ledger_path.read_text("utf-8") == before


def test_the_queue_reports_progress_from_the_ledger(capsys, catalog_of, ledger_path):
    catalog = catalog_of(_defects())
    main(
        [
            "drain",
            "--catalog",
            str(catalog),
            "--no-documents",
            "--ledger",
            str(ledger_path),
            "--by",
            "A. Reviewer",
            "--second",
            "B. Reviewer",
            "--count",
            "1",
        ]
    )
    capsys.readouterr()
    main(["queue", "--catalog", str(catalog), "--no-documents", "--ledger", str(ledger_path)])
    assert "1 decided / 1 total" in capsys.readouterr().out


def test_chain_on_an_unknown_sku_says_so(capsys, ledger_path):
    ledger_path.write_text("", encoding="utf-8")
    assert main(["chain", "--ledger", str(ledger_path), "--sku", "NOPE"]) == EXIT_NOT_RUN
    assert "no claims recorded" in capsys.readouterr().out


def test_the_constructed_corpus_banner_cannot_be_lost(catalog_of, tmp_path):
    """Decision D-4's binding rule: a constructed corpus is acceptable exactly as long as nobody
    can read a number out of it without also reading that it is constructed.

    Pinned here rather than trusted, because the banner is the kind of string that gets shortened
    for tidiness. It has to survive into both renderings.
    """
    from errata_scale.cli import BANNER
    from errata_scale.report import render_html, render_text
    from errata_scale.run import run_catalog

    for phrase in ("THE CATALOG IS CONSTRUCTED", "defects injected on purpose", "provenance.yaml"):
        assert phrase in BANNER

    run = run_catalog(catalog_of(_defects()))
    assert BANNER in render_text(run, banner=BANNER)
    assert "THE CATALOG IS CONSTRUCTED" in render_html(run, banner=BANNER)
