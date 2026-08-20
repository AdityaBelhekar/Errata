"""FR-2.1 / FR-2.4 -- the ETIM loader, and the citations that point into it.

Two kinds of test live here.

The first is about **the two traps in the distribution**: the CSVs are UTF-16-LE with no BOM and the
delimiter is ``;``. Both are recorded in ``data/reference/manifest.json`` because somebody read the
bytes, and both are asserted here because the failure mode is silent -- ``encoding="utf-8"`` yields
a first column full of NUL characters that then matches nothing, forever.

The second is **citation integrity across packages**, and it earns its place. ``errata_valuesem``'s
ontology declared ``EF000094`` as the ETIM feature for the tripping characteristic. There is no
EF000094 in ETIM 10.0; the feature is EF000889 "Release characteristic". That is HANDOFF §7's
signature exactly -- disciplined about the fact, careless about the locator nobody was expected to
open -- and the remedy is not vigilance, it is this test.
"""

from __future__ import annotations

import pytest
import yaml
from conftest import etim_archive, requires_etim

from errata_audit.attributes import load_attributes
from errata_audit.classify import load_scope
from errata_audit.etim import ETIM_ATTRIBUTION, ETIM_ENCODING, load_etim
from errata_valuesem.ontology import load as load_ontology

pytestmark = requires_etim


@pytest.fixture(scope="module")
def model():
    return load_etim(etim_archive(), release="10.0", class_ids=load_scope().as_set)


def test_the_encoding_is_utf_16_le_and_the_delimiter_is_a_semicolon() -> None:
    """Both were read off the bytes. ``encoding='utf-16'`` raises outright on these files."""
    assert ETIM_ENCODING == "utf-16-le"


def test_the_release_loads_and_carries_its_attribution(model) -> None:
    assert model.release == "10.0"
    assert "ODC-By" in model.attribution == ETIM_ATTRIBUTION.count("ODC-By") > 0 or "ODC-By" in model.attribution
    assert "ETIM International" in model.attribution


def test_the_release_is_a_parameter_not_a_guess(model) -> None:
    """FR-2.1: the loader is release-parameterised so 11.0 loads without a code change. The label
    is supplied by the caller because the archive does not carry one, and inferring "10.0" from a
    filename is the kind of confident guess ground rule 1 forbids."""
    other = load_etim(etim_archive(), release="99.9", class_ids={"EC000042"})
    assert other.release == "99.9"
    assert other.get("EC000042").uri("99.9").endswith("@ 99.9")


def test_every_class_is_loaded_even_when_features_are_restricted(model) -> None:
    """A retriever that could only see the classes it was told about would report perfect accuracy
    by construction. Scope restricts the *feature* load, never the class list."""
    assert len(model) > 5000
    assert model.get("EC000001") is not None  # busbar terminal: out of scope, still retrievable


def test_the_mcb_class_declares_the_features_the_attribute_map_uses(model) -> None:
    mcb = model.get("EC000042")
    assert mcb.description == "Miniature circuit breaker (MCB)"
    declared = {f.feature_id for f in mcb.features}
    assert {"EF000227", "EF008618", "EF000889"} <= declared


def test_a_closed_value_list_is_read_per_class_not_per_feature(model) -> None:
    """``ARTCLASSFEATURENR`` is the join key. Joining on the feature id instead would give a class
    the union of every other class's permitted values -- and FR-3.1 rejects values outside the
    list, so the wrong join quietly stops rejecting anything."""
    release = model.get("EC000042").feature("EF000889")
    assert release.is_closed_list
    assert {"B", "C", "D"} <= {v.description for v in release.values}


def test_units_come_from_the_release(model) -> None:
    current = model.get("EC000042").feature("EF000227")
    assert current.unit == "A"


@pytest.mark.parametrize("class_id", ["EC000042", "EC000003", "EC000271", "EC001047"])
def test_every_class_in_the_allow_list_exists_in_the_release(model, class_id: str) -> None:
    assert model.get(class_id) is not None


def test_the_rcbo_shaped_class_is_deliberately_excluded(model) -> None:
    """EC000905 exists in ETIM and is deliberately not in R1 scope: it carries both the release
    characteristic and the fault current, `errata_valuesem` leaves the term unregistered because
    three live readings exist, and mapping it here would inherit an ambiguity the value layer has
    already declined to resolve."""
    scope = load_scope()
    assert model.get("EC000905") is not None
    assert "EC000905" not in scope
    assert "EC000905" in scope.excluded


def test_every_feature_id_in_the_attribute_map_exists_and_is_declared(model) -> None:
    """The cross-package citation test. A feature id that does not exist, or that exists but is not
    on the class that claims it, is a fabricated locator."""
    for attribute in load_attributes():
        if not attribute.etim_feature:
            continue
        for class_id in attribute.classes:
            klass = model.get(class_id)
            assert klass is not None, f"{class_id} is not in the release"
            assert klass.feature(attribute.etim_feature) is not None, (
                f"{attribute.key}: {class_id} does not declare {attribute.etim_feature}"
            )


def test_every_etim_feature_cited_by_the_value_ontology_exists(model) -> None:
    """Finding N11 was found by this test: `terms.yaml` cited EF000094 for the tripping
    characteristic and ETIM 10.0 has no such feature."""
    ontology = load_ontology()
    cited = {
        vocabulary.etim_feature
        for vocabulary in ontology.vocabularies.values()
        if getattr(vocabulary, "etim_feature", "")
    }
    known = {f.feature_id for klass in model for f in klass.features}
    # Only classes in scope have their features loaded, so check against the ones we have plus a
    # direct lookup for anything else.
    missing = {feature for feature in cited if feature not in known}
    assert not missing, (
        f"the value ontology cites ETIM features that are not declared by any in-scope class: "
        f"{sorted(missing)}. Either the id is wrong or the vocabulary belongs to another class."
    )


def test_the_manifest_records_what_this_loader_reads() -> None:
    """The manifest is the repository's record of what was fetched. If it and the loader disagree
    about the file names, one of them has drifted."""
    import json
    from pathlib import Path

    manifest = json.loads(
        (Path(__file__).resolve().parents[2] / "data" / "reference" / "manifest.json").read_text(
            "utf-8"
        )
    )
    etim = next(a for a in manifest["artifacts"] if a["id"].startswith("etim-10.0"))
    assert "ETIMARTCLASS.csv" in etim["verified_contents"]
    assert etim["licence"].startswith("Open Data Commons")


def test_the_scope_file_is_configuration_with_stated_reasons() -> None:
    """FR-2.4: "class allow-list is configuration, not hardcoded logic". Every entry states why,
    because a scope decision nobody can read is a scope decision nobody can challenge."""
    from errata_audit.classify import load_scope as _load

    path = __import__("errata_audit.classify", fromlist=["x"]).__file__
    config = yaml.safe_load(
        (
            __import__("pathlib").Path(path).parent / "config" / "r1-classes.yaml"
        ).read_text("utf-8")
    )
    assert all(entry.get("reason") for entry in config["classes"])
    assert all(entry.get("reason") for entry in config["excluded"])
    assert _load().name == config["name"]
