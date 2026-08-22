"""FR-7.1 / FR-7.6 — the reviewer console as a running web application.

A console is only a console if a human can decide something in it, so the tests here are about the
loop rather than the layout: a request comes in, an audit is served, a decision is posted, and the
ledger has a row that was not there before.

Three of them guard rules that a UI is the natural place to lose:

* **the safety-class second signature is enforced on the server**, not by an HTML `required`
  attribute a curl request ignores;
* **the console never writes to a catalog** — accepting writes a claim to Errata's own ledger, and
  the test asserts the record under audit is untouched;
* **a hostile SKU is escaped**, because the queue renders catalog strings from a customer's feed and
  a feed is not a trusted source.

The server is started on port 0 in a thread and torn down per test, so nothing here depends on a
port being free or on a server somebody left running.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import etim_archive, requires_etim

from errata_audit.classify import load_scope
from errata_audit.etim import load_etim
from errata_audit.ledger import Ledger
from errata_audit.web import AuditService, build_service, serve
from errata_spec import Decision

pytestmark = requires_etim

CATALOG = (
    "sku,mpn,manufacturer,description,rated_current,poles,packaging_uom,weight_kg\n"
    "AX-16,AX-16,ACME,miniature circuit breaker,61 A,1,5 pcs,0.125 kg\n"
    "AX-10,AX-10,ACME,miniature circuit breaker,10 A,1,5 pcs,0.125 kg\n"
)


@pytest.fixture(scope="module")
def etim():
    return load_etim(etim_archive(), release="10.0", class_ids=load_scope().as_set)


@pytest.fixture
def service(tmp_path: Path, ordering_table_pdf: Path, etim) -> AuditService:
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(CATALOG, "utf-8")
    return build_service(
        catalog=catalog,
        datasheets=[ordering_table_pdf],
        etim=etim,
        scope=load_scope(),
        ledger=tmp_path / "ledger.jsonl",
        blobs=tmp_path / "blobs",
    )


@pytest.fixture
def client(service: AuditService) -> Iterator[str]:
    httpd = serve(service, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def get(client: str, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(client + path) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        # Closed explicitly: an HTTPError owns an open temporary file, and letting the garbage
        # collector close it raises an unraisable exception later, in an unrelated test, which is a
        # miserable thing to debug. `filterwarnings = ["error"]` turns that into a failure -- which
        # is the setting working as intended.
        with error:
            return error.code, error.read().decode("utf-8")


def post(client: str, path: str, fields: dict[str, str]) -> tuple[int, str]:
    payload = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(client + path, data=payload, method="POST")
    with urllib.request.urlopen(request) as response:
        return response.status, response.geturl()


# ------------------------------------------------------------------------------------------------
# The service
# ------------------------------------------------------------------------------------------------


def test_an_audit_is_cached_per_document_revision(service: AuditService) -> None:
    """Keyed on ``(sku, document sha256)`` — the same rule the layout cache and the register use, so
    a revised datasheet can never be served from a stale entry."""
    first = service.audit("AX-16")
    second = service.audit("AX-16")
    assert first is second


def test_the_queue_is_ranked_and_knows_what_has_been_decided(service: AuditService) -> None:
    rows = service.queue(10)
    assert rows, "the constructed catalog contains a contradiction and it should surface"
    values = [outcome.redline.expected_review_value for _result, outcome in rows]
    assert values == sorted(values, reverse=True)
    assert service.decided_ids() == set()
    assert len(service.undecided(10)) == len(rows)


def test_a_decision_writes_the_finding_the_score_and_the_claim(service: AuditService) -> None:
    _result, outcome = service.queue(10)[0]
    service.adjudicate(
        str(outcome.redline.redline_id),
        decision=Decision.ACCEPT_REDLINE,
        decided_by="A. Reviewer",
        second_adjudicator="B. Engineer",
        seconds=31.5,
        evidence_accepted=True,
    )
    kinds = [event.kind for event in service.ledger.events()]
    assert kinds == ["redline", "score", "adjudication", "claim"]

    decision = service.ledger.of_kind("adjudication")[0].payload
    assert decision["decided_by"] == "A. Reviewer"
    assert decision["seconds_to_decision"] == 31.5  # FR-9.3, timed by the page itself
    assert decision["evidence_accepted"] is True  # FR-9.4
    assert decision["raw_score"] is not None  # so a later calibration has something to fit


def test_the_safety_class_second_signature_is_enforced_on_the_server(
    service: AuditService,
) -> None:
    """The form marks the field required; a request that ignores the form must still be refused.
    FR-8.9 is enforced by ``Redline`` itself, which is why there is no path around it."""
    _result, outcome = service.queue(10)[0]
    assert outcome.redline.requires_two_signatures
    with pytest.raises(ValueError, match="single-signature acceptance is impossible"):
        service.adjudicate(
            str(outcome.redline.redline_id),
            decision=Decision.ACCEPT_REDLINE,
            decided_by="A. Reviewer",
        )
    assert service.ledger.of_kind("adjudication") == ()


def test_a_decision_survives_a_restart_because_ids_are_content_derived(
    service: AuditService, tmp_path: Path
) -> None:
    """The reason redline ids are a uuid5 of the finding's content: a decision recorded in one
    session has to attach to the same finding in the next one, and a random id makes that
    impossible the moment the process restarts."""
    _result, outcome = service.queue(10)[0]
    redline_id = str(outcome.redline.redline_id)
    service.adjudicate(
        redline_id,
        decision=Decision.KEEP_CATALOG,
        decided_by="A. Reviewer",
        second_adjudicator="B. Engineer",
    )

    service._cache.clear()  # a restart, in one line
    assert redline_id in service.decided_ids()
    assert service.find_redline(redline_id) is not None


def test_calibration_state_says_what_is_still_missing(service: AuditService) -> None:
    decisions, accepted, kept, sentence = service.calibration_state()
    assert (decisions, accepted, kept) == (0, 0, 0)
    assert "Not calibrated" in sentence

    _result, outcome = service.queue(10)[0]
    service.adjudicate(
        str(outcome.redline.redline_id),
        decision=Decision.ACCEPT_REDLINE,
        decided_by="A",
        second_adjudicator="B",
    )
    decisions, accepted, kept, sentence = service.calibration_state()
    assert (decisions, accepted, kept) == (1, 1, 0)
    assert "both" in sentence, "a one-sided set cannot be fitted and the console must say so"


def test_a_missing_named_datasheet_does_not_stop_the_console(
    tmp_path: Path, ordering_table_pdf: Path, etim
) -> None:
    """A catalog naming a document nobody supplied is ordinary — it is what
    ``no_source_document`` exists for. A console that refused to start over one row would be
    unusable on any real feed."""
    catalog = tmp_path / "c.csv"
    catalog.write_text(
        "sku,mpn,datasheet,rated_current\nAX-16,AX-16,nowhere.pdf,16 A\n", "utf-8"
    )
    service = build_service(
        catalog=catalog,
        datasheets=[ordering_table_pdf, tmp_path / "nowhere.pdf"],
        etim=etim,
        scope=load_scope(),
        ledger=tmp_path / "l.jsonl",
        blobs=tmp_path / "b",
    )
    assert service.missing_documents == ("nowhere.pdf",)
    assert service.audit("AX-16") is None


# ------------------------------------------------------------------------------------------------
# The HTTP surface
# ------------------------------------------------------------------------------------------------


def test_the_queue_page_renders_with_its_caveats(client: str) -> None:
    status, body = get(client, "/")
    assert status == 200
    assert "Review queue" in body
    assert "catalog under audit is constructed" in body
    assert "Not calibrated" in body


def test_the_sku_page_shows_three_panes_and_an_adjudication_form(client: str) -> None:
    status, body = get(client, "/sku/AX-16")
    assert status == 200
    assert ">Queue<" in body and ">Evidence<" in body and ">Claim history<" in body
    assert "Accept redline" in body and "Keep catalog" in body and "Escalate" in body
    assert "data:image/png;base64," in body  # the page image, with the boxes over it
    assert "class='box header'" in body  # FR-7.3


def test_an_unknown_sku_is_a_stated_reason_not_a_stack_trace(client: str) -> None:
    status, body = get(client, "/sku/NOPE-1")
    assert status == 404
    assert "No record" in body


def test_posting_a_decision_records_it_and_redirects(client: str, service: AuditService) -> None:
    _result, outcome = service.queue(10)[0]
    status, url = post(
        client,
        "/adjudicate",
        {
            "redline_id": str(outcome.redline.redline_id),
            "sku": "AX-16",
            "decision": "keep",
            "by": "A. Reviewer",
            "second": "B. Engineer",
            "note": "supplier confirmed the catalog",
            "seconds": "12.5",
            "evidence_accepted": "no",
        },
    )
    assert status == 200
    assert "/sku/AX-16" in url
    decisions = service.ledger.of_kind("adjudication")
    assert len(decisions) == 1
    assert decisions[0].payload["decision"] == "keep_catalog"
    assert decisions[0].payload["note"] == "supplier confirmed the catalog"


def test_posting_without_the_second_signature_reports_the_refusal(
    client: str, service: AuditService
) -> None:
    _result, outcome = service.queue(10)[0]
    status, url = post(
        client,
        "/adjudicate",
        {
            "redline_id": str(outcome.redline.redline_id),
            "sku": "AX-16",
            "decision": "accept",
            "by": "A. Reviewer",
        },
    )
    assert status == 200
    assert "flash=" in url
    assert service.ledger.of_kind("adjudication") == ()


def test_the_console_never_writes_to_the_catalog(client: str, service: AuditService, tmp_path: Path) -> None:
    """ADR-001. Accepting a redline writes a claim to Errata's ledger saying a human accepted it.
    The catalog file and the record in memory are untouched, and there is no code path that could
    change that."""
    before = (tmp_path / "catalog.csv").read_text("utf-8")
    _result, outcome = service.queue(10)[0]
    post(
        client,
        "/adjudicate",
        {
            "redline_id": str(outcome.redline.redline_id),
            "sku": "AX-16",
            "decision": "accept",
            "by": "A",
            "second": "B",
        },
    )
    assert (tmp_path / "catalog.csv").read_text("utf-8") == before
    assert service.record("AX-16").value("rated_current") == "61 A"


def test_a_hostile_catalog_string_is_escaped(tmp_path: Path, ordering_table_pdf: Path, etim) -> None:
    """The queue renders strings from a customer's feed, and a feed is not a trusted source."""
    catalog = tmp_path / "c.csv"
    catalog.write_text(
        'sku,mpn,description,rated_current,poles\n'
        '"<script>alert(1)</script>",AX-16,miniature circuit breaker,61 A,1\n',
        "utf-8",
    )
    service = build_service(
        catalog=catalog,
        datasheets=[ordering_table_pdf],
        etim=etim,
        scope=load_scope(),
        ledger=tmp_path / "l.jsonl",
        blobs=tmp_path / "b",
    )
    httpd = serve(service, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        _status, body = get(f"http://127.0.0.1:{httpd.server_address[1]}", "/")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_the_pages_carry_a_restrictive_content_security_policy(client: str) -> None:
    with urllib.request.urlopen(client + "/") as response:
        policy = response.headers["Content-Security-Policy"]
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        # Without nosniff a browser may override the Content-Type it was given, which turns any
        # endpoint that echoes bytes into a script host. It was the one of the four that was
        # missing, and the test register recorded all four as missing (corrected in
        # docs/EXECUTION-BLUEPRINT.md C-A).
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in policy
    assert "img-src 'self' data:" in policy


def test_inline_script_and_style_run_from_a_nonce_not_unsafe_inline(client: str) -> None:
    """`'unsafe-inline'` gives away most of what a CSP is for: with it, any string that reaches the
    page as markup executes. Escaping already stops that here -- the nonce means a single escaping
    mistake is not also a script execution."""
    with urllib.request.urlopen(client + "/") as response:
        policy = response.headers["Content-Security-Policy"]
        body = response.read().decode("utf-8")

    assert "unsafe-inline" not in policy

    nonces = set(re.findall(r"'nonce-([A-Za-z0-9_-]+)'", policy))
    assert len(nonces) == 1, f"script-src and style-src must share one nonce, found {nonces}"
    (nonce,) = nonces

    # The header and the markup are written in the same place so they cannot disagree. This asserts
    # they actually do agree -- a nonce in the header that no tag carries blocks the page's own
    # stylesheet, and a browser reports that as a blank screen rather than as an error.
    assert f"<style nonce='{nonce}'>" in body


def test_every_response_gets_a_different_nonce(client: str) -> None:
    """A nonce reused across responses is a constant, and a constant is `'unsafe-inline'` spelled
    less honestly."""
    seen = set()
    for _ in range(3):
        with urllib.request.urlopen(client + "/") as response:
            seen.update(re.findall(r"'nonce-([A-Za-z0-9_-]+)'", response.headers["Content-Security-Policy"]))
    assert len(seen) == 3


def test_the_nonce_placeholder_never_reaches_the_client(client: str) -> None:
    """If substitution is ever skipped the page still renders -- and silently loses its styling and
    its timing script. A test is the only thing that notices."""
    # /sku/ is included deliberately: it is the only page carrying the inline <script>, so a
    # substitution that worked for <style> and not for <script> would pass on the other three.
    for path in ("/", "/status", "/ledger", "/sku/AX-16"):
        _status, body = get(client, path)
        assert "__csp_nonce_" not in body, f"{path} leaked the placeholder"
        if "<script" in body:
            assert "<script nonce=" in body, f"{path} has an inline script with no nonce"


def test_the_status_page_lists_what_is_not_built(client: str) -> None:
    _status, body = get(client, "/status")
    assert "What this does not claim" in body
    assert "LLM selector" in body
    assert "waiver" in body


def test_the_ledger_page_renders_the_decisions(client: str, service: AuditService) -> None:
    _result, outcome = service.queue(10)[0]
    service.adjudicate(
        str(outcome.redline.redline_id),
        decision=Decision.ESCALATE,
        decided_by="A. Reviewer",
        second_adjudicator="B. Engineer",
    )
    _status, body = get(client, "/ledger")
    assert "append-only" in body
    assert "escalate" in body


def test_the_ledger_file_is_line_delimited_json_a_customer_can_read(
    service: AuditService,
) -> None:
    _result, outcome = service.queue(10)[0]
    service.adjudicate(
        str(outcome.redline.redline_id),
        decision=Decision.ACCEPT_REDLINE,
        decided_by="A",
        second_adjudicator="B",
    )
    lines = Ledger(service.ledger.path).path.read_text("utf-8").strip().splitlines()
    assert all(json.loads(line)["schema"] == "errata-claim-ledger/1" for line in lines)
