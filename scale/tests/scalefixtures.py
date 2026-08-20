"""Literal catalog rows for the R2 tests, in a uniquely named module.

Not in ``conftest.py``, and the reason is mechanical rather than stylistic: this repository runs
its distributions' test directories side by side with no ``__init__.py``, so two modules with the
same basename collide in ``sys.path`` -- ``audit/tests/conftest.py`` and this package's conftest
are both importable as ``conftest``, and whichever pytest reaches first wins. Shared helpers
therefore live under a name nothing else in the repository uses.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASHEETS = REPO_ROOT / "var" / "spike" / "datasheets"
ABB_S200 = DATASHEETS / "abb-s200-2CDC002142D0207.pdf"
ETIM_DIR = REPO_ROOT / "var" / "reference" / "etim"
SCALE_CATALOG = REPO_ROOT / "var" / "scale" / "catalog.csv"
R1_CATALOG = REPO_ROOT / "audit" / "src" / "errata_audit" / "demo" / "catalog.csv"

COLUMNS: tuple[str, ...] = (
    "sku",
    "mpn",
    "manufacturer",
    "description",
    "datasheet",
    "rated_current",
    "poles",
    "packaging_uom",
    "weight_kg",
    "order_code",
)

DEFAULTS: dict[str, str] = {
    "manufacturer": "SYN-MFR-01",
    "description": "Miniature circuit breaker",
    "datasheet": "",
    "rated_current": "16 A",
    "poles": "1",
    "packaging_uom": "10 pcs",
    "weight_kg": "0.125 kg",
    "order_code": "SYN1610",
}


def row(sku: str, mpn: str = "", **overrides: str) -> dict[str, str]:
    """One catalog row, with everything not named taking a correct default."""
    values = dict(DEFAULTS)
    values.update(overrides)
    values["sku"] = sku
    values["mpn"] = mpn or sku
    return {column: values.get(column, "") for column in COLUMNS}


def write_catalog(path: Path, rows: Sequence[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return path


# ------------------------------------------------------------------------------------------------
# Fixtures.
#
# These live here rather than in a ``conftest.py``, and the reason is mechanical. This repository
# runs its distributions' test directories side by side with no ``__init__.py``, so pytest prepends
# each one to ``sys.path`` as it collects it and a second ``conftest.py`` would shadow the R1 one --
# ``audit/tests/test_audit.py`` does ``from conftest import ...`` and would silently get this
# package's module instead. Found by running the whole suite; ``pytest scale/tests audit/tests``
# passes either way, which is exactly why it is worth a comment.
#
# A fixture imported into a test module's namespace is discovered normally, so the scale tests ask
# for what they need with an explicit import and there is no shared name to collide.
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def catalog_of(tmp_path: Path):
    """Write a catalog from literal rows and hand back its path."""

    def _make(rows: Sequence[dict[str, str]], name: str = "catalog.csv") -> Path:
        return write_catalog(tmp_path / name, rows)

    return _make


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger.jsonl"


@pytest.fixture(scope="session")
def demo_catalog() -> Path:
    """The generated 10,000-row corpus, or a skip.

    A clean clone has no ``var/``, and a suite that fails there teaches people to ignore red.
    """
    if not SCALE_CATALOG.exists():
        pytest.skip(
            "the R2 demonstration catalog has not been built; run `errata-scale corpus` "
            "(or scale/tools/build_scale_catalog.py) first"
        )
    return SCALE_CATALOG
