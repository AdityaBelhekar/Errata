"""The CLI's exit codes, and the boundaries R3 is not allowed to cross.

The exit code is the decision in every Errata CLI, so it is tested as behaviour rather than as
decoration. The boundary tests are the ones that would catch a change nobody meant to make: a
network call appearing in the benchmark, a JSON stream with English on top of it (finding N19),
or a redline reverting to two vocabularies (finding N15).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from errata_ecosystem.cli import (
    EXIT_FINDINGS,
    EXIT_NOT_MEASURED,
    EXIT_OK,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ECOSYSTEM_SRC = REPO_ROOT / "ecosystem" / "src" / "errata_ecosystem"


# ------------------------------------------------------------------------------------------------
# exit codes
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["status"], EXIT_OK),
        (["vocab", "rated_current"], EXIT_OK),
        (["bridge", "status"], EXIT_OK),
        (["bridge", "show", "--code", "39121603"], EXIT_OK),
        (["gold", "show"], EXIT_OK),
        (["gold", "verify"], EXIT_OK),
        (["split", "show"], EXIT_OK),
        (["split", "verify"], EXIT_OK),
        (["eclass", "scan"], EXIT_OK),
        (["score", "--axis", "crosswalk"], EXIT_OK),
        (["reviewer"], EXIT_NOT_MEASURED),
        (["reviewer", "--protocol"], EXIT_OK),
        (["reproduce"], EXIT_OK),
    ],
)
def test_exit_codes(argv, expected, capsys) -> None:
    assert main(argv) == expected
    capsys.readouterr()


def test_the_leaderboard_exits_one_because_there_are_losses(capsys) -> None:
    """Not a failure -- the exit code says "there is something here a reader must see", which is
    the same meaning it carries in errata-audit and errata-scale."""
    assert main(["leaderboard"]) == EXIT_FINDINGS
    assert "WHERE WE LOSE" in capsys.readouterr().out


def test_an_axis_with_no_data_exits_two(tmp_path, capsys) -> None:
    assert main(["score", "--axis", "grounding", "--corpus", str(tmp_path / "x.yaml")]) == (
        EXIT_NOT_MEASURED
    )
    capsys.readouterr()


def test_the_html_leaderboard_is_written_where_it_was_asked_for(tmp_path, capsys) -> None:
    target = tmp_path / "board.html"
    main(["leaderboard", "--html", str(target)])
    capsys.readouterr()
    assert target.exists()
    assert "<table>" in target.read_text(encoding="utf-8")


def test_the_eclass_adapter_command_says_what_is_missing_rather_than_failing(
    monkeypatch, capsys
) -> None:
    monkeypatch.delenv("ERRATA_ECLASS_DICTIONARY", raising=False)
    assert main(["eclass", "adapter"]) == EXIT_NOT_MEASURED
    assert "Errata ships none" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------
# finding N19 -- a --json stream must be JSON
# ------------------------------------------------------------------------------------------------


def test_score_json_is_parseable_json(capsys) -> None:
    main(["score", "--axis", "supersession", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["axis"] == "supersession"


def test_the_audit_cli_no_longer_prints_english_on_top_of_its_json() -> None:
    """Finding N19, regression test at the process boundary.

    PyMuPDF advertises its layout add-on with a bare ``print`` on every ``find_tables()`` call.
    ``warnings.simplefilter("ignore")`` never silenced it -- it is not a warning -- so every
    ``--json`` payload in this repository carried a line of English on top of it, and no
    in-process test could see it because the tests call the API rather than the executable.
    """
    executable = REPO_ROOT / ".venv" / "Scripts" / "errata-audit.exe"
    if not executable.exists():  # pragma: no cover - non-Windows or not installed
        pytest.skip("errata-audit console script not installed")
    finished = subprocess.run(
        [str(executable), "catalog", "--json"],
        capture_output=True,
        text=True,
        timeout=900,
        cwd=REPO_ROOT,
    )
    payload = json.loads(finished.stdout)  # raises if anything else reached stdout
    assert payload["records"] > 0


# ------------------------------------------------------------------------------------------------
# boundaries
# ------------------------------------------------------------------------------------------------


def test_the_benchmark_makes_no_network_call() -> None:
    """A harness that fetched silently could not tell you which corpus produced its number.

    Checked statically, over the package's own source: the fetch step is
    ``scripts/fetch_reference_data.sh``, deliberately outside the code that scores.
    """
    banned = re.compile(
        r"\b(?:import\s+(?:requests|httpx|socket)|urllib\.request|urlopen|http\.client)\b"
    )
    offenders = [
        path.name
        for path in ECOSYSTEM_SRC.rglob("*.py")
        if banned.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_no_ecosystem_module_writes_into_the_repository_at_import_time() -> None:
    """Importing a benchmark must not have effects. Anything R3 writes is written by a command
    the user typed, into var/ or a path they named."""
    banned = re.compile(r"^\s*(?:open\([^)]*['\"]w|.*\.write_text\()", re.MULTILINE)
    for path in ECOSYSTEM_SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        module_level = source.split("\ndef ")[0].split("\nclass ")[0]
        assert not banned.search(module_level), path.name


def test_every_r1_and_r2_redline_speaks_one_vocabulary(tmp_path) -> None:
    """Finding N15's regression guard, run over real R1 output rather than over a fixture."""
    from errata_audit import (
        BlobStore,
        audit_sku,
        ingest_document,
        load_catalog,
        load_etim,
        load_scope,
    )
    from errata_audit.cli import DEFAULT_ETIM_DIR, DEMO_CATALOG, DEMO_DATASHEETS
    from errata_ecosystem.vocabulary import vocabulary_violations
    from errata_spec import DocumentRegister

    datasheet = DEMO_DATASHEETS / "abb-s200-2CDC002142D0207.pdf"
    etim_dir = DEFAULT_ETIM_DIR / "extracted"
    if not datasheet.exists() or not etim_dir.exists():  # pragma: no cover - unfetched machine
        pytest.skip("reference data absent on this machine")

    scope = load_scope()
    model = load_etim(etim_dir, release="10.0", class_ids=scope.as_set)
    store = BlobStore(tmp_path / "blobs")
    document = ingest_document(datasheet, register=DocumentRegister(), store=store)

    record = next(r for r in load_catalog(DEMO_CATALOG) if r.sku_id == "S201M-B16UC")
    result = audit_sku(record, document, etim=model, scope=scope)

    redlines = [o.redline for o in result.outcomes if getattr(o, "redline", None) is not None]
    assert redlines, "the demo SKU should still raise at least one finding"
    assert vocabulary_violations(redlines) == ()
    assert all(r.attribute_uri.startswith(("etim:", "customer:")) for r in redlines)


def test_the_python_that_runs_this_is_the_one_the_receipt_reports() -> None:
    from errata_ecosystem.reproduce import reproduce

    assert reproduce().environment["python"] == sys.version.split()[0]
