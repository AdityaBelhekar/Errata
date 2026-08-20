"""FR-8.2 -- the claim ledger at catalog scale: supersedes chains, and a check that nothing updates.

    "Claim ledger -- append-only, immutable, with ``supersedes`` chains. No UPDATE or DELETE on
    claims in any code path. Full history reconstructible."

R1 built the append-only ledger and demonstrated it on a handful of events. Two things are missing
before that claim can be made about a catalog:

**Chains have to be reconstructible, not merely present.** One SKU's attribute may accumulate a
source-feed claim, a machine claim, a human adjudication and a batch reversal. "Full history
reconstructible" means those must assemble into an ordered chain with one head, and it means the
assembly must *fail loudly* on a cycle or a fork rather than returning whichever branch it walked
into. :func:`claim_chains` builds them; :class:`ChainIntegrityError` is what a broken ledger gets.

**"No UPDATE or DELETE in any code path" is a claim about source code, and is checked as one.**
A test that appends events and observes that nothing was overwritten proves only that the paths it
exercised behaved. :func:`scan_for_mutation` parses every module of every Errata distribution and
looks for the operations that *could* overwrite a ledger -- opening one in a truncating mode,
unlinking one, renaming over one -- and the test asserts the finding list is empty. That is a
static property of the repository rather than a property of one run.

The scan deliberately covers only non-test sources. Tests create and discard temporary ledgers,
which is exactly the operation being prohibited in production code, and a check that could not tell
the two apart would be turned off within a week -- which is worse than a narrower check that stays
on.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from errata_audit import Ledger

__all__ = [
    "ChainIntegrityError",
    "ClaimChain",
    "ClaimNode",
    "MutationFinding",
    "claim_chains",
    "scan_for_mutation",
]


class ChainIntegrityError(ValueError):
    """The ledger does not assemble into a history. Never caught and downgraded."""


@dataclass(frozen=True, slots=True)
class ClaimNode:
    """One claim in a chain."""

    claim_id: str
    supersedes: str | None
    sku_id: str
    attribute_uri: str
    value_raw: str
    asserter_kind: str
    asserted_at: str
    status: str = "active"
    event_id: str = ""

    @property
    def is_human(self) -> bool:
        return self.asserter_kind == "human"


@dataclass(frozen=True, slots=True)
class ClaimChain:
    """Every claim ever recorded about one attribute of one SKU, oldest first."""

    sku_id: str
    attribute_uri: str
    nodes: tuple[ClaimNode, ...]

    @property
    def head(self) -> ClaimNode | None:
        """The claim nothing supersedes -- what the catalog should say now."""
        return self.nodes[-1] if self.nodes else None

    @property
    def depth(self) -> int:
        return len(self.nodes)

    def values(self) -> tuple[str, ...]:
        return tuple(node.value_raw for node in self.nodes)

    def sentence(self) -> str:
        if not self.nodes:
            return f"{self.sku_id} / {self.attribute_uri}: no claims recorded"
        steps = " -> ".join(f"{node.value_raw!r} ({node.asserter_kind})" for node in self.nodes)
        return f"{self.sku_id} / {self.attribute_uri}: {steps}"


def claim_chains(ledger: Ledger) -> dict[tuple[str, str], ClaimChain]:
    """Reconstruct every supersedes chain in a ledger.

    Ordering is by the ``supersedes`` links, not by file order: a ledger merged from two runs is
    still one history, and reading it in write order would silently invent a sequence. Where a
    claim supersedes nothing it starts a chain; where several claims supersede the same parent the
    ledger has forked, and that raises rather than resolving to whichever was read last.
    """
    nodes: dict[tuple[str, str], list[ClaimNode]] = {}
    for event in ledger.of_kind("claim"):
        payload = event.payload
        key = (str(payload.get("sku_id", "")), str(payload.get("attribute_uri", "")))
        supersedes = payload.get("supersedes")
        nodes.setdefault(key, []).append(
            ClaimNode(
                claim_id=str(payload.get("claim_id", "")),
                supersedes=str(supersedes) if supersedes else None,
                sku_id=key[0],
                attribute_uri=key[1],
                value_raw=str(payload.get("value_raw", "")),
                asserter_kind=str(payload.get("asserter_kind", "")),
                asserted_at=str(payload.get("asserted_at", "")),
                status=str(payload.get("status", "active")),
                event_id=str(event.get("event_id", "")),
            )
        )

    return {key: _order(key, group) for key, group in nodes.items()}


def _order(key: tuple[str, str], group: Sequence[ClaimNode]) -> ClaimChain:
    by_id = {node.claim_id: node for node in group}
    children: dict[str | None, list[ClaimNode]] = {}
    for node in group:
        parent = node.supersedes if node.supersedes in by_id else None
        children.setdefault(parent, []).append(node)

    for parent, kids in children.items():
        if parent is not None and len(kids) > 1:
            raise ChainIntegrityError(
                f"{key[0]} / {key[1]}: {len(kids)} claims supersede {parent}. A forked chain has "
                "no single current value, so the ledger cannot answer 'what should the catalog "
                "say' -- which is the one question it exists to answer."
            )

    roots = sorted(children.get(None, []), key=lambda node: (node.asserted_at, node.claim_id))
    ordered: list[ClaimNode] = []
    for root in roots:
        cursor: ClaimNode | None = root
        seen: set[str] = set()
        while cursor is not None:
            if cursor.claim_id in seen:
                raise ChainIntegrityError(
                    f"{key[0]} / {key[1]}: supersedes chain cycles at {cursor.claim_id}"
                )
            seen.add(cursor.claim_id)
            ordered.append(cursor)
            following = children.get(cursor.claim_id, [])
            cursor = following[0] if following else None

    if len(ordered) != len(group):
        raise ChainIntegrityError(
            f"{key[0]} / {key[1]}: {len(group)} claims recorded but only {len(ordered)} are "
            "reachable from a chain root. An unreachable claim is history that cannot be "
            "reconstructed, which FR-8.2 forbids."
        )
    return ClaimChain(sku_id=key[0], attribute_uri=key[1], nodes=tuple(ordered))


# ------------------------------------------------------------------------------------------------
# the static half: no UPDATE and no DELETE, in any code path
# ------------------------------------------------------------------------------------------------

#: File modes that keep an append-only file append-only.
APPEND_SAFE_MODES: frozenset[str] = frozenset({"r", "rb", "rt", "a", "ab", "at", "a+"})

#: Calls that destroy or replace a file.
DESTRUCTIVE_CALLS: frozenset[str] = frozenset(
    {"unlink", "truncate", "remove", "rmtree", "rename", "replace", "write_text", "write_bytes"}
)

#: Names that mean "this expression refers to a ledger".
LEDGER_HINTS: tuple[str, ...] = ("ledger", "claims.jsonl", "claim_log")


@dataclass(frozen=True, slots=True)
class MutationFinding:
    """One place in the source that could overwrite ledger state."""

    path: str
    line: int
    call: str
    detail: str

    def sentence(self) -> str:
        return f"{self.path}:{self.line}  {self.call} -- {self.detail}"


def scan_for_mutation(roots: Iterable[Path | str]) -> tuple[MutationFinding, ...]:
    """Parse every non-test module under ``roots`` and report ledger-mutating operations.

    Deliberately conservative in one direction only: it reports anything that *looks* like it could
    rewrite a ledger, and the fix for a false positive is to name the variable something that is
    not a ledger. A check that under-reports would be worthless; a check that over-reports is an
    annoyance with a one-line remedy.
    """
    findings: list[MutationFinding] = []
    for root in roots:
        for path in sorted(Path(root).rglob("*.py")):
            parts = {part.lower() for part in path.parts}
            if "tests" in parts or path.name.startswith("test_"):
                continue
            try:
                tree = ast.parse(path.read_text("utf-8"), filename=str(path))
            except SyntaxError as error:  # pragma: no cover - a repo that does not parse
                raise ChainIntegrityError(f"{path} does not parse: {error}") from error
            findings.extend(_scan_tree(tree, path))
    return tuple(findings)


def _scan_tree(tree: ast.AST, path: Path) -> list[MutationFinding]:
    findings: list[MutationFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        rendered = _render(node)
        if not _mentions_ledger(rendered):
            continue

        name = _call_name(node)
        if name == "open":
            mode = _mode_of(node)
            if mode is not None and mode not in APPEND_SAFE_MODES:
                findings.append(
                    MutationFinding(
                        path=str(path),
                        line=node.lineno,
                        call=rendered,
                        detail=(
                            f"opens a ledger in mode {mode!r}. FR-8.2: no UPDATE or DELETE on "
                            "claims in any code path -- a correction is a new claim whose "
                            "supersedes names the old one."
                        ),
                    )
                )
        elif name in DESTRUCTIVE_CALLS:
            findings.append(
                MutationFinding(
                    path=str(path),
                    line=node.lineno,
                    call=rendered,
                    detail=(
                        f"{name}() on a ledger destroys or replaces recorded history, which "
                        "FR-8.2 forbids outright."
                    ),
                )
            )
    return findings


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _mode_of(node: ast.Call) -> str | None:
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    args = node.args
    # Path.open(mode) takes it first; builtin open(file, mode) takes it second.
    index = 0 if isinstance(node.func, ast.Attribute) else 1
    if len(args) > index and isinstance(args[index], ast.Constant):
        value = args[index].value
        if isinstance(value, str):
            return value
    return None


def _render(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<unrenderable>"


def _mentions_ledger(rendered: str) -> bool:
    lowered = rendered.lower()
    return any(hint in lowered for hint in LEDGER_HINTS)
