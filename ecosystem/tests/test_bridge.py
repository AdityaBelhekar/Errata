"""FR-9.7 -- the bridge holds against both published dictionaries, or it does not load.

Every test below that asserts a *refusal* has a matching test that asserts the same input loads
when the offending part is corrected. A validator nobody has watched reject something is a
validator nobody knows is running.
"""

from __future__ import annotations

import pytest
import yaml

from errata_ecosystem.bridge import (
    ATTRIBUTE_BEARING_RELATIONS,
    BRIDGE_FILE,
    BridgeValidationError,
    load_bridge,
    load_unspsc,
    validate_bridge,
)


@pytest.fixture(scope="module")
def loaded():
    return load_bridge()


@pytest.fixture(scope="module")
def codes():
    return load_unspsc()


@pytest.fixture(scope="module")
def raw():
    return yaml.safe_load(BRIDGE_FILE.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------
# facts read out of the hash-registered codeset on 2026-08-20 (data/reference/manifest.json)
# ------------------------------------------------------------------------------------------------


def test_the_unspsc_codeset_is_the_one_the_manifest_registered(codes) -> None:
    assert len(codes) == 71502
    assert codes["39121603"].commodity_name == "Miniature circuit breakers"
    assert codes["39121603"].class_name == "Circuit protection devices and accessories"
    assert codes["39121614"].commodity_name == "Earth leakage circuit breakers"


def test_unspsc_carries_no_attribute_layer_which_is_the_hole_this_bridge_fills(codes) -> None:
    """The PRD asserts it; this reads it. A ``UnspscCode`` has four levels and two names per
    level and nothing else, because the published file has nothing else."""
    fields = set(vars(codes["39121603"]).keys()) if hasattr(codes["39121603"], "__dict__") else set(
        codes["39121603"].__slots__
    )
    assert not {f for f in fields if "unit" in f or "feature" in f or "property" in f}


def test_no_commodity_title_names_a_residual_current_device(codes) -> None:
    """The reason EC000003 is a ``no_match`` rather than an approximation."""
    hits = [c for c in codes.values() if "residual current" in c.commodity_name.lower()]
    assert hits == []


# ------------------------------------------------------------------------------------------------
# the bridge itself
# ------------------------------------------------------------------------------------------------


def test_the_bridge_loads_and_validates_against_both_dictionaries(loaded) -> None:
    bridge, _ = loaded
    assert bridge.licence == "Apache-2.0"
    assert bridge.attribution["etim"].startswith("Contains information from the ETIM")
    assert bridge.mappings


def test_every_mapping_carries_a_rationale(loaded) -> None:
    bridge, _ = loaded
    for mapping in bridge.mappings:
        assert len(mapping.rationale) > 40, mapping.sentence()


def test_an_exact_match_delivers_an_attribute_layer_derived_from_etim(loaded) -> None:
    bridge, model = loaded
    bindings = bridge.attributes_for("39121603", model)
    assert len(bindings) >= 27
    ids = {b.feature_id for b in bindings}
    assert "EF000227" in ids  # rated current
    rated = next(b for b in bindings if b.feature_id == "EF000227")
    assert rated.description == "Rated current"
    assert rated.unit == "A"


def test_the_attribute_layer_is_not_written_in_the_bridge_file(raw) -> None:
    """It is derived at load time, so it cannot drift from ETIM. If a feature id ever appears in
    the YAML, that guarantee has quietly been replaced by a copy."""
    body = BRIDGE_FILE.read_text(encoding="utf-8")
    assert "EF000227" not in body
    for mapping in raw["mappings"]:
        assert "features" not in mapping and "attributes" not in mapping


def test_a_close_match_delivers_nothing(loaded) -> None:
    """The one mapping whose own rationale says the two descriptors turn on different properties.
    A loader that carried 14 features across it would be contradicting the file it just read."""
    bridge, model = loaded
    assert bridge.attributes_for("39121616", model) == ()
    assert "skos:closeMatch" not in ATTRIBUTE_BEARING_RELATIONS


def test_the_declined_row_names_no_etim_class(loaded) -> None:
    bridge, _ = loaded
    declined = [m for m in bridge.mappings if m.relation == "declined"]
    assert len(declined) == 1
    assert declined[0].unspsc == "39121614"
    assert declined[0].etim_class is None
    assert "EC000905" in declined[0].rationale


def test_the_no_match_rows_name_no_unspsc_code(loaded) -> None:
    bridge, _ = loaded
    for mapping in bridge.refusals:
        if mapping.relation == "no_match":
            assert mapping.unspsc is None
            assert mapping.etim_class is not None


def test_an_unmapped_in_scope_code_yields_nothing_rather_than_the_nearest_thing(loaded) -> None:
    bridge, model = loaded
    for code in ("39121602", "39121615", "39121633"):
        assert bridge.for_unspsc(code) == ()
        assert bridge.attributes_for(code, model) == ()


# ------------------------------------------------------------------------------------------------
# the refusals, each with the corrected control next to it
# ------------------------------------------------------------------------------------------------


def _one(**overrides) -> dict:
    row = {
        "unspsc": "39121603",
        "unspsc_title": "Miniature circuit breakers",
        "etim_class": "EC000042",
        "etim_description": "Miniature circuit breaker (MCB)",
        "relation": "skos:exactMatch",
        "confidence": "high",
        "rationale": "a rationale long enough to be a rationale rather than a placeholder",
    }
    row.update(overrides)
    return {"mappings": [row]}


def test_a_valid_row_validates(codes, loaded) -> None:
    _, model = loaded
    assert validate_bridge(_one(), codes=codes, model=model)


def test_a_code_that_does_not_exist_is_refused(codes, loaded) -> None:
    _, model = loaded
    with pytest.raises(BridgeValidationError, match="not in the codeset"):
        validate_bridge(_one(unspsc="99999999"), codes=codes, model=model)


def test_a_title_that_has_moved_under_the_mapping_is_refused(codes, loaded) -> None:
    """UNSPSC is revised roughly annually. A mapping judged against a title that no longer exists
    is stale by definition, and resolving anyway is how a bridge rots silently."""
    _, model = loaded
    with pytest.raises(BridgeValidationError, match="re-judge it"):
        validate_bridge(_one(unspsc_title="Miniature circuit breakers (renamed)"), codes=codes, model=model)


def test_an_etim_class_that_does_not_exist_is_refused(codes, loaded) -> None:
    _, model = loaded
    with pytest.raises(BridgeValidationError, match="not in the loaded release"):
        validate_bridge(_one(etim_class="EC999999"), codes=codes, model=model)


def test_a_mapping_without_a_rationale_is_refused(codes, loaded) -> None:
    _, model = loaded
    with pytest.raises(BridgeValidationError, match="no rationale"):
        validate_bridge(_one(rationale="  "), codes=codes, model=model)


def test_an_unknown_relation_is_refused(codes, loaded) -> None:
    _, model = loaded
    with pytest.raises(BridgeValidationError, match="not a known relation"):
        validate_bridge(_one(relation="sort_of_matches"), codes=codes, model=model)


def test_a_one_sided_row_must_be_a_refusal(codes, loaded) -> None:
    _, model = loaded
    with pytest.raises(BridgeValidationError, match="needs both sides"):
        validate_bridge(_one(etim_class=None, etim_description=None), codes=codes, model=model)


def test_a_no_match_that_names_both_sides_is_refused(codes, loaded) -> None:
    """'We found nothing' and 'we found something and dislike it' are different claims."""
    _, model = loaded
    with pytest.raises(BridgeValidationError, match="discouraging label"):
        validate_bridge(_one(relation="no_match"), codes=codes, model=model)


def test_an_empty_bridge_is_not_a_bridge(codes, loaded) -> None:
    _, model = loaded
    with pytest.raises(BridgeValidationError, match="not a bridge"):
        validate_bridge({"mappings": []}, codes=codes, model=model)
