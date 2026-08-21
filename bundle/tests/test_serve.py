"""The console service: the join between bundles on disk and decisions in the ledger.

Defect D-1 lives here. The queue joined on the bundle's short attribute name (``rated_current``)
while the ledger records ``attribute_uri`` (``etim:EF000227``), so they never matched. The failure
mode is the worst kind available to this feature: the decision **is** written, the queue simply
never shows it, and a reviewer re-decides work they already did — each time superseding a perfectly
good claim for no reason.

It also looked like it worked. One older ledger row happened to carry the bare name, so exactly one
record showed as decided and the join appeared fine. These tests pin both spellings so that a
future change cannot quietly go back to matching one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from errata_bundle.serve import ConsoleService


@pytest.fixture
def service(tmp_path: Path) -> ConsoleService:
    bundles = tmp_path / "bundles"
    (bundles / "SKU-1").mkdir(parents=True)
    (bundles / "index.json").write_text(
        json.dumps({"bundles": [{"sku": "SKU-1"}]}), encoding="utf-8"
    )
    (bundles / "SKU-1" / "redlines.json").write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "attribute": "rated_current",
                        "redline": {"attribute_uri": "etim:EF000227"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return ConsoleService(
        root=tmp_path, bundles=bundles, ledger_path=tmp_path / "ledger.jsonl"
    )


def _write_adjudication(service: ConsoleService, attribute_uri: str) -> None:
    """Append one adjudication event in the ledger's own on-disk shape."""
    event = {
        "schema": "errata-claim-ledger/1",
        "kind": "adjudication",
        "event_id": "e1",
        "recorded_utc": "2026-08-21T00:00:00+00:00",
        "payload": {
            "sku_id": "SKU-1",
            "attribute_uri": attribute_uri,
            "decision": "accept_redline",
            "decided_by": "R. Vogel",
            "decided_by_role": "domain_reviewer",
            "seconds_to_decision": 41.2,
            "evidence_accepted": True,
        },
    }
    with service.ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


@pytest.mark.parametrize(
    "recorded_as",
    ["etim:EF000227", "rated_current"],
    ids=["ledger-uses-uri", "ledger-uses-bare-name"],
)
def test_a_decision_is_found_under_either_spelling(service, recorded_as):
    """D-1 regression. Both spellings must join, or decisions become invisible."""
    _write_adjudication(service, recorded_as)
    queue = service.queue()
    entry = queue["bundles"][0]

    assert entry["undecided"] == 0, (
        f"a decision recorded as {recorded_as!r} did not join to the bundle's "
        "'rated_current'. The reviewer would be shown this finding again as if undecided."
    )
    assert entry["decisions"]["rated_current"]["decision"] == "accept_redline"
    assert queue["decided_total"] == 1


def test_an_undecided_finding_stays_undecided(service):
    queue = service.queue()
    assert queue["bundles"][0]["undecided"] == 1
    assert queue["decided_total"] == 0


def test_attribute_keys_normalises_uris_and_bare_names():
    keys = ConsoleService._attribute_keys("etim:EF000227", "rated_current")
    assert "etim:EF000227" in keys
    assert "EF000227" in keys
    assert "rated_current" in keys
    # Empty names contribute nothing rather than an empty key that would match everything.
    assert "" not in ConsoleService._attribute_keys("", "x")


def test_the_latest_decision_wins(service):
    """An append-only log answers 'what is true now' with the last event, not the first."""
    _write_adjudication(service, "etim:EF000227")
    event = {
        "schema": "errata-claim-ledger/1",
        "kind": "adjudication",
        "event_id": "e2",
        "recorded_utc": "2026-08-21T01:00:00+00:00",
        "payload": {
            "sku_id": "SKU-1",
            "attribute_uri": "etim:EF000227",
            "decision": "keep_catalog",
            "decided_by": "M. Sato",
            "decided_by_role": "domain_reviewer",
        },
    }
    with service.ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")

    entry = service.queue()["bundles"][0]
    assert entry["decisions"]["rated_current"]["decision"] == "keep_catalog"
    assert entry["decisions"]["rated_current"]["decided_by"] == "M. Sato"


def test_session_never_pools_roles(service):
    """FR-9.3. An implementer's decisions must not be averaged in with a reviewer's.

    ``errata_ecosystem.reviewer`` refuses to produce a rate from anyone who built the tool. A
    console that pooled the two would hand that harness a number it must throw away -- or worse,
    one it would not notice it should.
    """
    _write_adjudication(service, "etim:EF000227")
    event = {
        "schema": "errata-claim-ledger/1",
        "kind": "adjudication",
        "event_id": "e3",
        "recorded_utc": "2026-08-21T02:00:00+00:00",
        "payload": {
            "sku_id": "SKU-2",
            "attribute_uri": "etim:EF000999",
            "decision": "escalate",
            "decided_by": "the author",
            "decided_by_role": "implementer",
            "seconds_to_decision": 3.0,
        },
    }
    with service.ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")

    session = service.session()
    assert set(session["by_role"]) == {"domain_reviewer", "implementer"}
    assert session["by_role"]["domain_reviewer"]["n"] == 1
    assert session["by_role"]["implementer"]["n"] == 1
    assert session["by_role"]["domain_reviewer"]["median_seconds"] == 41.2


def test_missing_bundles_directory_explains_itself(tmp_path):
    service = ConsoleService(
        root=tmp_path, bundles=tmp_path / "nope", ledger_path=tmp_path / "ledger.jsonl"
    )
    queue = service.queue()
    assert queue["bundles"] == []
    # An empty queue and a missing directory are different states, and a reviewer seeing
    # "nothing disagrees" when in fact nothing was built would be badly misled.
    assert "errata_bundle build" in queue["error"]


def test_adjudicate_requires_an_actor(service):
    with pytest.raises(ValueError, match="decided_by"):
        service.adjudicate(
            {"sku": "SKU-1", "attribute": "rated_current", "decision": "escalate"}
        )
