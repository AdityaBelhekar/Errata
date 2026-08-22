"""ADR-004 -- a scan carrying an OCR layer is declined, and a real datasheet is not.

FE-2.5 defect G-2. `is_born_digital` is true for any extracted word, so a scanned document with an
OCR layer -- `H28-1957-Part-I.pdf`, 100% image area, 161,731 words -- passed straight through into
grounding. Those words are a model's reading of pixels, so a citation into them quotes something
the document does not say, and the evidence box has nothing true to project onto.

These tests pin **both ends and the margin between them**. A threshold test that only checks the
scan is declined would still pass if someone raised the constant until it declined half the corpus;
one that only checks real datasheets survive would still pass if someone lowered it to zero. The
third test is the one that matters in a year.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from errata_audit.attributes import load_attributes
from errata_audit.derive import derive
from errata_audit.layout import IMAGE_DOMINATED_RATIO, extract_layer
from errata_audit.tables import extract_tables
from errata_bundle.fixtures import write_ocr_over_scan
from errata_spec import DeclinedReason

#: The real datasheets in `var/` are fetched, not committed (FR-9.5), so these tests skip rather
#: than fail on a machine that has not run `scripts/fetch_reference_data.sh`. The manufactured
#: fixture always runs -- the decline itself is never untested.
DATASHEETS = Path("var/spike/datasheets")

#: Highest image-area ratio observed across the two real datasheets, 25 pages, in ADR-004. Pinned
#: so that if a future document exceeds it, the margin test fails and someone re-reads the ADR
#: instead of discovering the overlap through a wrong decline.
OBSERVED_BORN_DIGITAL_MAX = 0.191


@pytest.fixture(scope="module")
def ocr_pdf(tmp_path_factory) -> Path:
    return write_ocr_over_scan(tmp_path_factory.mktemp("ocr"))


def _real_datasheets() -> list[Path]:
    return sorted(DATASHEETS.glob("*.pdf")) if DATASHEETS.is_dir() else []


# ------------------------------------------------------------------------------------------------
# The scan is declined
# ------------------------------------------------------------------------------------------------


def test_an_ocr_layer_over_a_scan_is_recognised(ocr_pdf: Path) -> None:
    """The whole defect in one assertion: plenty of words, and every one of them a guess."""
    layer = extract_layer(ocr_pdf, use_cache=False)

    # This is what made the defect invisible: by every signal the pipeline had, the document is fine.
    assert layer.is_born_digital, "the fixture must have a text layer, or it tests the wrong thing"
    assert layer.words, "...and real words in it, or the decline below proves nothing"

    assert layer.is_ocr_over_scan
    assert layer.ocr_over_scan_pages == (1,)


def test_the_page_is_measured_as_a_picture(ocr_pdf: Path) -> None:
    layer = extract_layer(ocr_pdf, use_cache=False)
    (page,) = layer.pages
    assert page.image_area_ratio == pytest.approx(1.0, abs=1e-6)
    assert page.is_image_dominated


def test_the_pipeline_actually_declines_it(ocr_pdf: Path) -> None:
    """End to end. The properties above are only worth having if `derive` acts on them.

    Before ADR-004 this call returned a grounded value with an evidence box, drawn from words
    that are a reading of pixels. That is the fabricated finding the ground rules put above
    every other failure, and it is what this test now prevents.
    """
    layer = extract_layer(ocr_pdf, use_cache=False)
    result = derive(
        layer,
        extract_tables(ocr_pdf),
        mpn="4C-M",
        attribute=load_attributes().get("rated_current"),
        klass=None,
        sku_id="4C-M",
        doc_id="ocr-fixture",
        revision_sha256="a" * 64,
    )

    assert result.abstained, "a scan must not yield a grounded value"
    assert result.value is None
    assert result.evidence == (), "and no evidence box, because there is nothing true to box"
    assert result.abstention is not None
    assert result.abstention.reason is DeclinedReason.OCR_TEXT_NOT_EVIDENCE


def test_the_decline_names_what_actually_happened(ocr_pdf: Path) -> None:
    """`LAYOUT_UNREADABLE` would be a lie here -- the layout is legible. ADR-004 §Decision 4."""
    assert DeclinedReason.OCR_TEXT_NOT_EVIDENCE.value == "ocr_text_not_evidence"
    assert DeclinedReason.OCR_TEXT_NOT_EVIDENCE is not DeclinedReason.LAYOUT_UNREADABLE


# ------------------------------------------------------------------------------------------------
# The real documents are not
# ------------------------------------------------------------------------------------------------


@pytest.mark.skipif(not _real_datasheets(), reason="var/ not fetched; see scripts/fetch_reference_data.sh")
@pytest.mark.parametrize("pdf", _real_datasheets(), ids=lambda p: p.stem)
def test_a_real_datasheet_is_not_declined(pdf: Path) -> None:
    """The non-degradation half. These documents carry photographs, wiring diagrams and dimension
    drawings, and none of that may make them look like a scan."""
    layer = extract_layer(pdf, use_cache=False)
    assert layer.is_born_digital
    assert not layer.is_ocr_over_scan
    assert layer.ocr_over_scan_pages == ()


# ------------------------------------------------------------------------------------------------
# The margin -- the test that matters in a year
# ------------------------------------------------------------------------------------------------


def test_the_threshold_sits_clear_of_both_ends() -> None:
    """The constant is not a tuning knob, and this is what stops it becoming one.

    ADR-004 sets `IMAGE_DOMINATED_RATIO` from a measured gap: real born-digital pages peak at 0.191,
    a scan is 1.0, nothing lives in between. If someone later moves it in the direction that
    recovers coverage -- the `MIN_CONTRAST` failure mode this repository already has one instance of
    -- this fails and points at the ADR.
    """
    assert IMAGE_DOMINATED_RATIO > OBSERVED_BORN_DIGITAL_MAX * 2, (
        f"threshold {IMAGE_DOMINATED_RATIO} leaves less than a 2x margin above the highest "
        f"born-digital page observed ({OBSERVED_BORN_DIGITAL_MAX}). Real datasheets would start "
        f"being declined as scans. See ADR-004."
    )
    assert IMAGE_DOMINATED_RATIO < 1.0, (
        f"threshold {IMAGE_DOMINATED_RATIO} only catches a page that is 100% image. A scan with a "
        f"1mm white margin would pass. See ADR-004."
    )


@pytest.mark.skipif(not _real_datasheets(), reason="var/ not fetched; see scripts/fetch_reference_data.sh")
def test_the_observed_maximum_is_still_the_maximum() -> None:
    """ADR-004's measured table, re-derived rather than trusted.

    The ADR's born-digital end is 2 documents and 25 pages -- it says so. When the full corpus lands
    this test is what tells you whether that sample held, instead of the ADR quietly aging into
    fiction.
    """
    worst = 0.0
    where = ""
    for pdf in _real_datasheets():
        for page in extract_layer(pdf, use_cache=False).pages:
            if page.image_area_ratio > worst:
                worst, where = page.image_area_ratio, f"{pdf.stem} p{page.number}"

    assert worst <= OBSERVED_BORN_DIGITAL_MAX + 0.01, (
        f"a born-digital page now reaches {worst:.3f} image area ({where}), above ADR-004's "
        f"recorded maximum of {OBSERVED_BORN_DIGITAL_MAX}. The measured separation the threshold "
        f"rests on has changed; re-run the measurement and amend the ADR."
    )
