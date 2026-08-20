"""The architectural boundaries R2 is not allowed to cross, asserted as tests.

R1 has four of these and they are the reason its design survived being built in a hurry. R2 adds
scale, which is exactly the condition under which shortcuts get taken, so it adds four more:

1. **The product still does not import its own scorer.** ``errata_scale`` must not reach
   ``errata_bench``: a system that could see the harness measuring it is a system that can be tuned
   against it.
2. **Only one module in the whole product touches the network**, and it is R1's document ingester.
   ``errata_scale`` has no network code of its own, so a catalog run cannot start fetching URLs
   because a feed asked it to.
3. **Nothing writes to a customer catalog** (ADR-001). Errata grades; it never enriches. The only
   file this package writes to a caller's disk is its own generated corpus and its own reports.
4. **The value layer stays deterministic** (NFR-8). R2 must not have introduced a model or network
   call into ``errata_valuesem`` through a new dependency.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "errata_scale"
REPO = Path(__file__).resolve().parents[2]

NETWORK_MODULES = {"urllib", "urllib.request", "http", "http.client", "socket", "requests", "httpx"}
MODEL_MODULES = {"torch", "transformers", "openai", "anthropic", "sentence_transformers", "onnxruntime"}


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


def _modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def test_the_product_does_not_import_its_own_evaluation_harness():
    for module in _modules():
        assert not any(
            name.startswith("errata_bench") for name in _imports(module)
        ), f"{module.name} imports the evaluation harness"


def test_no_module_in_the_scale_package_reaches_the_network():
    """Document acquisition is R1's job and stays there, behind ``--allow-network``.

    A catalog run walks 10,000 rows of somebody else's data. If any module here could open a socket,
    a feed full of URLs would be a feed that decides what this process connects to.
    """
    for module in _modules():
        offending = _imports(module) & NETWORK_MODULES
        assert not offending, f"{module.name} imports {offending}"


def test_no_module_in_the_scale_package_calls_a_model():
    for module in _modules():
        offending = _imports(module) & MODEL_MODULES
        assert not offending, f"{module.name} imports {offending}"


def test_nothing_opens_a_catalog_for_writing():
    """ADR-001: Errata grades, and never writes to a customer's catalog.

    The check is on the *expression*, not on a comment: an ``open`` in write mode whose target
    mentions the catalog is the shape a write-back feature would arrive in.
    """
    offenders: list[str] = []
    for module in _modules():
        tree = ast.parse(module.read_text("utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name != "open":
                continue
            rendered = ast.unparse(node).lower()
            if "catalog" not in rendered:
                continue
            if any(
                isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "w" in arg.value
                for arg in node.args
            ):
                offenders.append(f"{module.name}:{node.lineno} {rendered}")
    assert not offenders, "\n".join(offenders)


def test_the_value_layer_is_still_deterministic():
    """NFR-8, re-asserted from R2 because a shared dependency is a shared risk."""
    valuesem = REPO / "valuesem" / "src" / "errata_valuesem"
    for module in sorted(valuesem.rglob("*.py")):
        names = _imports(module)
        assert not (names & NETWORK_MODULES), f"{module.name} can reach the network"
        assert not (names & MODEL_MODULES), f"{module.name} can call a model"


def test_the_scale_package_depends_only_on_the_releases_below_it():
    """R2 sits on R1, which sits on the R0 libraries. Nothing points the other way."""
    allowed = {"errata_spec", "errata_valuesem", "errata_comparator", "errata_audit", "errata_scale"}
    for module in _modules():
        for name in _imports(module):
            if not name.startswith("errata_"):
                continue
            assert name.split(".")[0] in allowed, f"{module.name} imports {name}"
