"""FE-7 · the local console server -- the half of FR-7.6 that actually records a decision.

Until this module existed, the console rendered evidence beautifully and could not adjudicate. That
is not a small gap: FR-7.1's acceptance criterion is that a reviewer *"adjudicates without leaving
the screen"*, and a screen that cannot accept a decision is a report with buttons drawn on it.

Design, and the three constraints that fix it
---------------------------------------------

**Standard library only.** No framework, no build step, no dependency. It follows the precedent set
by ``errata_audit.web``, and for the same reason: FR-7.9's constraint is that the whole thing runs
from a clean clone with no signup, and that constraint is worth more than any convenience a
framework buys back.

**127.0.0.1 by default, and binding elsewhere is loud.** A reviewer console shows a customer's
catalog beside a manufacturer's copyrighted document. Putting that on a network interface is a
decision somebody should have to make deliberately, so ``--host`` prints a warning and there is no
config file that can do it quietly.

**The ledger is the real one.** Decisions go through ``errata_audit.ledger.Ledger.adjudicate``, not
a parallel store: same append-only file, same ``supersedes`` chains, same FR-8.9 two-signature rule
enforced by ``Redline`` itself. A console with its own decision store would be a second source of
truth about what a human said, which is the exact failure ADR-001 and the ledger design exist to
prevent.

What it will not do
-------------------

It never writes to a catalog (ADR-001). Accepting a redline writes a *claim* to Errata's own ledger
saying a human accepted it. There is no code path here that could reach a customer's PIM.

It has no authentication, and that is stated rather than forgotten: identity is a name the reviewer
types, stored in their own browser. That is honest for a local operator tool and **not sufficient
for FR-8.9's dual control in a real deployment** -- two names typed by one person at one keyboard
are one signature wearing two hats. The cryptographic version is proposed in
``docs/frontend/FE-SYSTEM-REVIEW.md`` §5.5 and is not built.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

__all__ = ["ConsoleService", "main", "serve"]

#: Where the console's static files live, relative to the repository root.
WEB_ROOT = "web"

#: Ledger location. The same file `errata-audit adjudicate` writes, on purpose.
DEFAULT_LEDGER = Path("var/audit/ledger.jsonl")

DEFAULT_BUNDLES = Path("var/fe25/bundles")


class ConsoleService:
    """Bundles on disk, decisions in the ledger, and the join between them."""

    def __init__(self, *, root: Path, bundles: Path, ledger_path: Path) -> None:
        self.root = root.resolve()
        self.bundles = bundles.resolve()
        self.ledger_path = ledger_path
        self._lock = threading.Lock()

    # -- reading -------------------------------------------------------------------------

    def _ledger(self):
        from errata_audit.ledger import Ledger

        return Ledger(self.ledger_path)

    @staticmethod
    def _attribute_keys(*names: str) -> set[str]:
        """Every spelling of one attribute that might appear as a key.

        The ledger records ``attribute_uri`` -- ``etim:EF000227`` -- while a bundle's ``attribute``
        is the bare ``rated_current``, and older ledger rows carry the bare name too. Matching on
        one spelling silently loses the other, and the failure is invisible in the worst possible
        way: the decision IS recorded, the queue simply never shows it, so a reviewer re-decides
        work they already did and the second decision supersedes the first for no reason.

        Found by making a decision in the console and watching the progress bar not move. Both
        spellings are indexed, and the trailing segment is taken so a URI matches a bare key --
        the same normalisation ``errata_spec.taxonomy.is_safety_class`` already does.
        """
        keys: set[str] = set()
        for name in names:
            if not name:
                continue
            value = name.strip()
            keys.add(value)
            if ":" in value:
                keys.add(value.rsplit(":", 1)[-1])
            if "/" in value:
                keys.add(value.rsplit("/", 1)[-1])
        return keys

    def decisions(self) -> dict[str, dict[str, Any]]:
        """Latest decision per (sku, attribute-spelling), from the ledger.

        'Latest' rather than 'only', because the ledger is append-only and a correction is a new
        event that supersedes an old one. Reading the last event per key is how an append-only log
        answers "what is true now" -- there is no update to read instead.
        """
        latest: dict[str, dict[str, Any]] = {}
        for event in self._ledger().events():
            if event.kind != "adjudication":
                continue
            payload = event.payload
            sku = payload.get("sku_id", "")
            entry = {
                "decision": payload.get("decision"),
                "decided_by": payload.get("decided_by"),
                "decided_by_role": payload.get("decided_by_role"),
                "decided_at": payload.get("decided_at"),
                "seconds": payload.get("seconds_to_decision"),
                "evidence_accepted": payload.get("evidence_accepted"),
                "second_adjudicator": payload.get("second_adjudicator"),
                "note": payload.get("note"),
                "event_id": event.get("event_id"),
            }
            for key in self._attribute_keys(str(payload.get("attribute_uri", ""))):
                latest[f"{sku}::{key}"] = entry
        return latest

    def unique_decisions(self) -> list[dict[str, Any]]:
        """Each current decision exactly once.

        :meth:`decisions` deliberately indexes one decision under several spellings so a lookup
        cannot miss it. That makes it a lookup table and **not** a population: iterating its values
        yields the same adjudication two or three times.

        Anything that COUNTS must come through here instead. The first version of ``session()``
        iterated ``decisions().values()`` and silently double-counted reviewer-seconds -- inflating
        the one metric the PRD calls the number a buyer actually pays for. Caught by a test that
        asserted the per-role totals rather than merely that the endpoint returned something.
        """
        seen: dict[str, dict[str, Any]] = {}
        for entry in self.decisions().values():
            key = str(entry.get("event_id") or id(entry))
            seen[key] = entry
        return list(seen.values())

    def queue(self) -> dict[str, Any]:
        """The queue index, joined to whatever has already been decided."""
        index_path = self.bundles / "index.json"
        if not index_path.exists():
            return {
                "bundles": [],
                "error": (
                    f"no bundles at {self.bundles}. Build some with: "
                    "python -m errata_bundle build --catalog var/scale/catalog.csv "
                    "--datasheet var/spike/datasheets/abb-s200-2CDC002142D0207.pdf"
                ),
            }

        index = json.loads(index_path.read_text(encoding="utf-8"))
        decided = self.decisions()

        for entry in index.get("bundles", []):
            sku = entry.get("sku", "")
            redlines_path = self.bundles / sku / "redlines.json"
            if not redlines_path.exists():
                continue
            redlines = json.loads(redlines_path.read_text(encoding="utf-8"))
            findings = redlines.get("findings", [])
            entry["attributes"] = [f.get("attribute", "") for f in findings]

            found: dict[str, Any] = {}
            for finding in findings:
                uri = (finding.get("redline") or {}).get("attribute_uri", "")
                for key in self._attribute_keys(finding.get("attribute", ""), uri):
                    hit = decided.get(f"{sku}::{key}")
                    if hit:
                        found[finding.get("attribute", "")] = hit
                        break
            entry["decisions"] = found
            entry["undecided"] = len(findings) - len(found)

        index["decided_total"] = sum(
            len(e.get("decisions", {})) for e in index.get("bundles", [])
        )
        index["finding_total"] = sum(
            len(e.get("attributes", [])) for e in index.get("bundles", [])
        )
        return index

    def session(self) -> dict[str, Any]:
        """FR-9.3 in aggregate: how long decisions are taking, and whose they are.

        The rate is reported per role and never pooled. `errata_ecosystem.reviewer` refuses to
        produce a reviewer-seconds figure from anyone who built the tool, and a console that
        averaged an implementer's decisions in with a domain reviewer's would hand that harness a
        number it would have to throw away -- or worse, one it would not notice it should.
        """
        by_role: dict[str, list[float]] = {}
        accepted_boxes = 0
        box_answers = 0
        for entry in self.unique_decisions():
            seconds = entry.get("seconds")
            role = entry.get("decided_by_role") or "unstated"
            if isinstance(seconds, (int, float)):
                by_role.setdefault(role, []).append(float(seconds))
            if entry.get("evidence_accepted") is not None:
                box_answers += 1
                accepted_boxes += 1 if entry["evidence_accepted"] else 0

        def stats(values: list[float]) -> dict[str, Any]:
            ordered = sorted(values)
            n = len(ordered)
            return {
                "n": n,
                "median_seconds": round(ordered[n // 2], 1) if n else None,
                "total_seconds": round(sum(ordered), 1) if n else None,
            }

        return {
            # FR-9.4 is a distinct metric from FR-9.3 and is reported as one.
            "evidence_acceptance": {
                "answered": box_answers,
                "accepted": accepted_boxes,
                "rate": round(accepted_boxes / box_answers, 3) if box_answers else None,
            },
            "by_role": {role: stats(values) for role, values in sorted(by_role.items())},
            "note": (
                "Reviewer-seconds are reported per role and never pooled. Only decisions by a "
                "domain reviewer count toward FR-9.3; see docs/reviewer-protocol.md."
            ),
        }

    # -- writing -------------------------------------------------------------------------

    def adjudicate(self, body: dict[str, Any]) -> dict[str, Any]:
        """Record one decision. FR-7.6 / FR-8.9 / FR-9.3 / FR-9.4.

        The ``Redline`` is rehydrated from the bundle rather than rebuilt from the request, so a
        client cannot alter what it is deciding about by editing the payload it posts back. The
        only things taken from the request are the things a human actually supplies.
        """
        from errata_spec import Decision, Redline

        sku = str(body.get("sku") or "")
        attribute = str(body.get("attribute") or "")
        if not sku or not attribute:
            raise ValueError("sku and attribute are required")

        redlines_path = self.bundles / sku / "redlines.json"
        if not redlines_path.exists():
            raise FileNotFoundError(f"no bundle for {sku}")

        # The human's inputs are checked FIRST. They are cheap to check and they are the only
        # part the reviewer can fix; rehydrating the Redline first meant a missing actor surfaced
        # as a six-line pydantic dump about fields the reviewer has never heard of. An error
        # message is part of the interface.
        decided_by = str(body.get("decided_by") or "").strip()
        if not decided_by:
            raise ValueError("decided_by is required: a decision with no actor is not a decision")
        decision = Decision(str(body.get("decision")))

        redlines = json.loads(redlines_path.read_text(encoding="utf-8"))
        finding = next(
            (f for f in redlines.get("findings", []) if f.get("attribute") == attribute),
            None,
        )
        if finding is None or "redline" not in finding:
            raise ValueError(f"{sku}/{attribute} has no redline in its bundle")

        redline = Redline.model_validate(finding["redline"])

        seconds = body.get("seconds_to_decision")
        with self._lock:
            adjudication, claim = self._ledger().adjudicate(
                redline,
                decision=decision,
                decided_by=decided_by,
                note=str(body.get("note") or ""),
                seconds_to_decision=float(seconds) if seconds is not None else None,
                evidence_accepted=body.get("evidence_accepted"),
                second_adjudicator=str(body.get("second_adjudicator") or "").strip(),
                raw_score=body.get("raw_score"),
                decided_by_role=str(body.get("decided_by_role") or ""),
                presented_utc=str(body.get("presented_utc") or ""),
                decided_utc=str(body.get("decided_utc") or datetime.now(UTC).isoformat()),
            )

        return {
            "ok": True,
            "decision": decision.value,
            "claim_id": str(claim.claim_id),
            "decided_at": adjudication.decided_at.isoformat(),
            "supersedes": str(claim.supersedes) if claim.supersedes else None,
        }


# ── HTTP ────────────────────────────────────────────────────────────────────────────────

_JSON = "application/json; charset=utf-8"


class _Handler(BaseHTTPRequestHandler):
    service: ConsoleService
    quiet: bool = False

    server_version = "errata-console"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        if not self.quiet:
            sys.stderr.write(f"  {self.command} {self.path}\n")

    # -- helpers -------------------------------------------------------------------------

    def _send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", _JSON)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self._send_json({"error": "not found"}, 404)
            return
        kind, _ = mimetypes.guess_type(str(path))
        self.send_response(200)
        self.send_header("Content-Type", kind or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        # No caching: this is a development and operator tool, and a stale console showing a
        # decision that was not recorded is the worst possible failure mode for it.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _resolve(self, base: Path, relative: str) -> Path | None:
        """Join and confirm the result is still inside ``base``. Path traversal is not clever."""
        candidate = (base / relative.lstrip("/")).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            return None
        return candidate

    # -- routes --------------------------------------------------------------------------

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)

        try:
            # `/` is the front door and it is the SITE, not the console. A tool
            # that opens on its own working surface assumes everyone arriving
            # already knows what it is.
            redirects = {
                "/": "/web/site/",
                "/site": "/web/site/",
                "/console": "/web/console/",
                "/console/": "/web/console/",
                "/datum": "/web/datum/",
                "/datum/": "/web/datum/",
            }
            if path in redirects:
                self.send_response(302)
                self.send_header("Location", redirects[path])
                self.end_headers()
                return

            if path == "/api/queue":
                self._send_json(self.service.queue())
                return
            if path == "/api/session":
                self._send_json(self.service.session())
                return
            if path == "/api/health":
                self._send_json({"ok": True, "bundles": str(self.service.bundles)})
                return

            if path.startswith("/api/bundle/"):
                target = self._resolve(self.service.bundles, path[len("/api/bundle/"):])
                if target is None or not target.is_file():
                    self._send_json({"error": "not found"}, 404)
                    return
                self._send_file(target)
                return

            if path.startswith("/web/"):
                target = self._resolve(self.service.root / WEB_ROOT, path[len("/web/"):])
                if target is None:
                    self._send_json({"error": "not found"}, 404)
                    return
                if target.is_dir():
                    target = target / "index.html"
                if not target.is_file():
                    self._send_notfound_page()
                    return
                self._send_file(target)
                return

            self._send_notfound_page()
        except BrokenPipeError:
            pass
        except Exception as error:
            self._send_json({"error": str(error)}, 500)

    def _send_notfound_page(self) -> None:
        page = self.service.root / WEB_ROOT / "site" / "404.html"
        if page.is_file():
            data = page.read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path != "/api/adjudicate":
            self._send_json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            self._send_json(self.service.adjudicate(body))
        except ValueError as error:
            # Includes the FR-8.9 two-signature refusal raised by Redline itself. It is a 422 and
            # not a 500: the request was understood and declined, and the console shows the reason
            # verbatim rather than a generic failure.
            self._send_json({"ok": False, "error": str(error)}, 422)
        except FileNotFoundError as error:
            self._send_json({"ok": False, "error": str(error)}, 404)
        except Exception as error:
            self._send_json({"ok": False, "error": str(error)}, 500)


def serve(
    *,
    root: Path,
    bundles: Path,
    ledger: Path,
    host: str = "127.0.0.1",
    port: int = 8099,
    quiet: bool = False,
) -> None:
    service = ConsoleService(root=root, bundles=bundles, ledger_path=ledger)
    handler = type("Handler", (_Handler,), {"service": service, "quiet": quiet})
    httpd = ThreadingHTTPServer((host, port), handler)

    print(f"  errata console   http://{host}:{port}/web/console/")
    print(f"  design system    http://{host}:{port}/web/datum/")
    print(f"  bundles          {bundles}")
    print(f"  ledger           {ledger}")
    if host not in ("127.0.0.1", "localhost"):
        print(
            "\n  WARNING: bound to a non-loopback interface. This console shows a customer's\n"
            "  catalog beside a manufacturer's copyrighted document, and it has no\n"
            "  authentication. Everyone who can reach this port can read both.\n"
        )
    print("\n  Ctrl-C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="errata-bundle serve",
        description="The reviewer console, with adjudication wired to the real ledger.",
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--bundles", type=Path, default=DEFAULT_BUNDLES)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="loopback by default. Binding elsewhere exposes an unauthenticated console.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    serve(
        root=args.root,
        bundles=args.bundles,
        ledger=args.ledger,
        host=args.host,
        port=args.port,
        quiet=args.quiet,
    )
    return 0
