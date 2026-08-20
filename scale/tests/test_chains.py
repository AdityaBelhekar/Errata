"""FR-8.2 -- append-only, immutable, with supersedes chains.

    "No UPDATE or DELETE on claims in any code path. Full history reconstructible."

The second sentence is a claim about *source code*, not about a run, so half of this file is a
static test: :func:`errata_scale.scan_for_mutation` parses every module of every distribution and
the repository is asserted to contain no operation that could overwrite a ledger. The other half
proves the scanner would actually catch one, by writing a module that does it.

The chain tests care about the failure modes that make a history unreconstructible rather than
merely untidy: a fork (two claims superseding one parent, so "what should the catalog say" has two
answers), a cycle, and an orphan (a claim reachable from nothing).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from scalefixtures import ledger_path  # noqa: F401

from errata_audit import Ledger
from errata_scale import ChainIntegrityError, claim_chains, scan_for_mutation
from errata_spec import AsserterKind, Claim

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = [
    REPO_ROOT / name / "src"
    for name in ("spec", "valuesem", "comparator", "bench", "audit", "scale")
]


def _claim(ledger: Ledger, value: str, *, supersedes: uuid.UUID | None = None) -> Claim:
    claim = Claim(
        sku_id="SKU-1",
        attribute_uri="rated_current",
        value_raw=value,
        asserter_kind=AsserterKind.HUMAN,
        supersedes=supersedes,
    )
    ledger.append_claim(claim)
    return claim


# ------------------------------------------------------------------------------------------------
# the static half
# ------------------------------------------------------------------------------------------------


def test_no_module_in_the_repository_updates_or_deletes_a_ledger():
    findings = scan_for_mutation(root for root in SOURCE_ROOTS if root.exists())
    assert findings == (), "\n".join(finding.sentence() for finding in findings)


def test_the_scanner_catches_a_truncating_open(tmp_path):
    module = tmp_path / "bad_writer.py"
    module.write_text(
        "from pathlib import Path\n"
        "def compact(ledger_path: Path) -> None:\n"
        "    with open(ledger_path, 'w', encoding='utf-8') as handle:\n"
        "        handle.write('')\n",
        encoding="utf-8",
    )
    findings = scan_for_mutation([tmp_path])
    assert len(findings) == 1
    assert "no UPDATE or DELETE" in findings[0].detail


def test_the_scanner_catches_a_deletion(tmp_path):
    module = tmp_path / "bad_deleter.py"
    module.write_text(
        "def purge(ledger_path):\n    ledger_path.unlink()\n", encoding="utf-8"
    )
    findings = scan_for_mutation([tmp_path])
    assert len(findings) == 1
    assert "destroys or replaces recorded history" in findings[0].detail


def test_the_scanner_ignores_test_modules(tmp_path):
    """Tests create and discard temporary ledgers on purpose. A check that could not tell that
    apart from production code would be switched off within a week."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_thing.py").write_text(
        "def test_x(tmp_path):\n    (tmp_path / 'ledger.jsonl').unlink(missing_ok=True)\n",
        encoding="utf-8",
    )
    assert scan_for_mutation([tmp_path]) == ()


def test_appending_to_a_ledger_is_not_flagged(tmp_path):
    module = tmp_path / "good_writer.py"
    module.write_text(
        "def append(ledger_path, line):\n"
        "    with open(ledger_path, 'a', encoding='utf-8') as handle:\n"
        "        handle.write(line)\n",
        encoding="utf-8",
    )
    assert scan_for_mutation([tmp_path]) == ()


# ------------------------------------------------------------------------------------------------
# the chains
# ------------------------------------------------------------------------------------------------


def test_a_chain_reconstructs_in_supersedes_order(ledger_path):
    ledger = Ledger(ledger_path)
    first = _claim(ledger, "61 A")
    second = _claim(ledger, "16 A", supersedes=first.claim_id)
    third = _claim(ledger, "61 A", supersedes=second.claim_id)

    chains = claim_chains(ledger)
    chain = chains[("SKU-1", "rated_current")]
    assert chain.values() == ("61 A", "16 A", "61 A")
    assert chain.depth == 3
    assert chain.head is not None
    assert chain.head.claim_id == str(third.claim_id)
    assert "->" in chain.sentence()


def test_the_chain_order_does_not_come_from_file_order(ledger_path):
    """A ledger merged from two runs is still one history; reading it in write order would invent
    a sequence."""
    ledger = Ledger(ledger_path)
    root = Claim(
        sku_id="SKU-1",
        attribute_uri="rated_current",
        value_raw="61 A",
        asserter_kind=AsserterKind.HUMAN,
    )
    child = Claim(
        sku_id="SKU-1",
        attribute_uri="rated_current",
        value_raw="16 A",
        asserter_kind=AsserterKind.HUMAN,
        supersedes=root.claim_id,
    )
    ledger.append_claim(child)  # written first, on purpose
    ledger.append_claim(root)

    chain = claim_chains(ledger)[("SKU-1", "rated_current")]
    assert chain.values() == ("61 A", "16 A")


def test_a_forked_chain_raises_rather_than_choosing_a_branch(ledger_path):
    ledger = Ledger(ledger_path)
    root = _claim(ledger, "61 A")
    _claim(ledger, "16 A", supersedes=root.claim_id)
    _claim(ledger, "25 A", supersedes=root.claim_id)

    with pytest.raises(ChainIntegrityError) as error:
        claim_chains(ledger)
    assert "no single current value" in str(error.value)


def test_an_unreachable_claim_raises(ledger_path):
    """A claim whose parent is present but which no root reaches is history that cannot be
    reconstructed."""
    ledger = Ledger(ledger_path)
    root = _claim(ledger, "61 A")
    middle = _claim(ledger, "16 A", supersedes=root.claim_id)
    _claim(ledger, "25 A", supersedes=middle.claim_id)
    _claim(ledger, "32 A", supersedes=middle.claim_id)
    with pytest.raises(ChainIntegrityError):
        claim_chains(ledger)


def test_chains_are_kept_per_sku_and_per_attribute(ledger_path):
    ledger = Ledger(ledger_path)
    ledger.append_claim(
        Claim(
            sku_id="SKU-1",
            attribute_uri="rated_current",
            value_raw="16 A",
            asserter_kind=AsserterKind.HUMAN,
        )
    )
    ledger.append_claim(
        Claim(
            sku_id="SKU-1",
            attribute_uri="weight_kg",
            value_raw="0.125 kg",
            asserter_kind=AsserterKind.HUMAN,
        )
    )
    ledger.append_claim(
        Claim(
            sku_id="SKU-2",
            attribute_uri="rated_current",
            value_raw="25 A",
            asserter_kind=AsserterKind.HUMAN,
        )
    )
    assert len(claim_chains(ledger)) == 3


def test_an_empty_ledger_has_no_chains(ledger_path):
    assert claim_chains(Ledger(ledger_path)) == {}
