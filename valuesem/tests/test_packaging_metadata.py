"""FR-4.6: this package ships standalone. Its metadata has to be buildable, not just declared.

This existed as a latent failure: ``pyproject.toml`` declared ``readme = "README.md"`` and
``license-files = ["LICENSE", "NOTICE"]``, and none of the three files were present. An editable
install tolerates that -- ``pip install -e`` never reads them -- so the whole test suite passed
while ``python -m build`` would have failed on the first attempt to cut a release.

The lesson generalises: a declaration that only the *release* path reads is invisible to a test
suite that only exercises the *development* path. These tests read the declarations and check
the files exist, which is cheap enough to run every time.

The full acceptance check -- build a wheel, install it into an empty interpreter, parse and
compare with nothing else from this repository present -- is not run here because it costs a
network-free venv creation per run. It is recorded in PHASES.md under P1 task 1.8 with its
verified output.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

DIST_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = DIST_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def test_declared_readme_exists(project: dict) -> None:
    readme = project.get("readme")
    assert readme, "FR-4.6 wants this package presentable on its own; declare a readme"
    assert (DIST_ROOT / readme).is_file(), f"{readme} is declared but missing from {DIST_ROOT}"


def test_declared_licence_files_exist(project: dict) -> None:
    declared = project.get("license-files", [])
    assert declared, "a distribution that ships standalone must carry its own licence"
    for name in declared:
        assert (DIST_ROOT / name).is_file(), f"{name} is declared but missing from {DIST_ROOT}"


def test_licence_is_apache_2(project: dict) -> None:
    assert project["license"] == "Apache-2.0"
    assert "Apache License" in (DIST_ROOT / "LICENSE").read_text(encoding="utf-8")


def test_notice_attributes_the_third_party_data_actually_shipped() -> None:
    """ODC-By requires attribution wherever ETIM-derived content is surfaced, and this package
    surfaces unit and value-list references. The NOTICE has to name it."""
    notice = (DIST_ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "ETIM" in notice
    assert "ODC-By" in notice or "Open Data Commons" in notice
    assert "Recommendation 21" in notice, (
        "the package-type codes in ontology/packaging.yaml are Rec 21, not Rec 20 -- "
        "see finding N1"
    )


def test_notice_does_not_claim_to_ship_eclass() -> None:
    """ADR-003: no ECLASS content in the repo, in any image built from it, or in any
    published benchmark. The NOTICE states the exclusion; this pins the statement."""
    notice = (DIST_ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "ECLASS" in notice
    assert "NOT INCLUDED" in notice


def test_readme_states_the_determinism_guarantee() -> None:
    """The no-model rule is the package's whole proposition. A reader who installs it from
    PyPI and never sees this repository still has to be told."""
    readme = (DIST_ROOT / "README.md").read_text(encoding="utf-8")
    assert "No model in the hot path" in readme
    assert "test_determinism_boundary" in readme


def test_readme_carries_the_labelling_caveat() -> None:
    """Ground rule 1 applied to our own marketing: the measured numbers in the README are
    self-labelled, and the README must say so wherever it quotes them."""
    # Collapsed, because the phrases below wrap across lines in the prose. Reflowing a
    # paragraph to satisfy a substring match would be the test dictating the writing.
    readme = " ".join((DIST_ROOT / "README.md").read_text(encoding="utf-8").split())
    assert "1.30%" in readme, "if the headline number changes, revisit this file"
    assert "dual-labelling" in readme
    assert "same author who wrote the comparator" in readme
