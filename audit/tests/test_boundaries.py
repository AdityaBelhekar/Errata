"""The architectural boundaries R1 is not allowed to cross, asserted as tests.

Every rule here is one a comment already states somewhere. A comment is a request; an import graph
is a fact, and these are the four facts that keep the design honest when somebody is in a hurry:

1. **No distribution depends on `spike/`.** It is throwaway scaffolding, frozen now that gate 2 has
   a number, and the P3 fence says R1 inherits its *findings* and not its code.
2. **`derive` cannot reach the catalog.** FR-3.4 is enforced by `derive()`'s signature, but a module
   that imported `CatalogRecord` could grow a second path to it. It does not import it, and this
   test is why it stays that way.
3. **`errata_audit` does not import `errata_bench`.** The evaluation harness measures the product;
   a product that imported its own scorer would be a product that could be tuned against it.
4. **The value layer stays deterministic.** `errata_valuesem` forbids model and network calls in any
   code path, and R1 must not have quietly introduced one through a new dependency.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "errata_audit"
REPO = Path(__file__).resolve().parents[2]
DISTRIBUTIONS = ("spec", "valuesem", "comparator", "bench", "audit", "scale")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _sources(distribution: str) -> list[Path]:
    root = REPO / distribution / "src"
    return sorted(root.rglob("*.py")) if root.exists() else []


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
def test_no_distribution_imports_the_spike(distribution: str) -> None:
    """`spike/README.md` rule 1: it is not `pip install`-able and nothing depends on it.

    The spike is frozen rather than deleted, so it can still reproduce the gate-2 corpus. A frozen
    directory that something imports is not frozen, it is load-bearing.
    """
    for path in _sources(distribution):
        offenders = {name for name in _imports(path) if name == "spike" or name.startswith("spike.")}
        assert not offenders, f"{path} imports {sorted(offenders)}"


def test_the_extractor_cannot_reach_the_catalog_record_type() -> None:
    """FR-3.4, structurally. ``derive()`` takes no catalog parameter; this stops a second path to
    one appearing through the type it would have to use."""
    imports = _imports(PACKAGE / "derive.py")
    assert not any("ingest" in name for name in imports), (
        "errata_audit.derive imported the ingest module, where CatalogRecord lives. The extractor "
        "must not be able to see the catalog's values (FR-3.4)."
    )


def test_the_product_does_not_import_its_own_evaluation_harness() -> None:
    for path in _sources("audit"):
        offenders = {name for name in _imports(path) if name.startswith("errata_bench")}
        assert not offenders, f"{path} imports {sorted(offenders)}"


def test_r1_did_not_add_a_network_or_model_dependency_to_the_value_layer() -> None:
    """NFR-8. `errata_valuesem` has its own determinism test; this one checks that R1's arrival did
    not add an import to it from the outside."""
    forbidden = {"requests", "httpx", "urllib.request", "socket", "openai", "anthropic", "torch"}
    for path in _sources("valuesem"):
        offenders = _imports(path) & forbidden
        assert not offenders, f"{path} imports {sorted(offenders)}"


def test_only_one_module_in_the_audit_package_can_reach_the_network() -> None:
    """FR-1.2's opt-in fetch lives in ``documents.py`` and nowhere else, so "did this run touch the
    network?" has one place to look."""
    reachable = {
        path.name
        for path in _sources("audit")
        if any(name.startswith("urllib.request") for name in _imports(path))
    }
    assert reachable <= {"documents.py", "web.py"}, (
        f"{sorted(reachable)} can reach the network. Fetching belongs in documents.py; web.py only "
        "parses URLs and serves them."
    )
