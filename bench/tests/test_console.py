"""The CLIs must not let the operator's code page decide whether their output is readable.

`errata-r0 status` is the first command anyone runs against this repository. It prints §
section marks and en-dashes; on Windows, Python picks the locale encoding (cp1252) for a
non-terminal stdout, and those characters arrive mangled anywhere expecting UTF-8.

These tests pin the fix at the entry point, because the failure is silent -- nothing raises,
the exit code is still 0, and the only symptom is that the number the reader is being asked to
trust is surrounded by replacement characters.
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from errata_bench.console import _reconfigure, force_utf8_output

REPO_ROOT = Path(__file__).resolve().parents[2]

#: UTF-8 encoding of U+00A7 SECTION SIGN. In cp1252 the same character is the single byte 0xA7,
#: which is what the bug emitted.
SECTION_UTF8 = b"\xc2\xa7"


class _Reconfigurable:
    """A stdout stand-in that records what encoding it was asked for.

    Deliberately not an ``io.StringIO`` subclass: ``encoding`` is a read-only property on the
    real text-IO types, so a double that needs to *change* it cannot inherit from them.
    """

    def __init__(self, encoding: str) -> None:
        self.encoding = encoding
        self.requested: list[str] = []

    def reconfigure(self, *, encoding: str) -> None:
        self.requested.append(encoding)
        self.encoding = encoding


def test_reconfigures_a_cp1252_stream_to_utf8() -> None:
    stream = _Reconfigurable("cp1252")
    _reconfigure(stream)
    assert stream.requested == ["utf-8"]
    assert stream.encoding == "utf-8"


@pytest.mark.parametrize("already", ["utf-8", "UTF-8", "utf8", "utf-8-sig"])
def test_leaves_a_utf8_stream_alone(already: str) -> None:
    """Idempotent: re-running must not churn a stream that is already correct."""
    stream = _Reconfigurable(already)
    _reconfigure(stream)
    assert stream.requested == []


def test_survives_a_stream_that_cannot_be_reconfigured() -> None:
    """pytest's captured stdout has no reconfigure(). A CLI must not die over its own
    progress output, so this is a no-op rather than an AttributeError."""
    _reconfigure(io.StringIO())
    _reconfigure(None)


def test_survives_a_stream_that_refuses_the_encoding() -> None:
    class _Detached(_Reconfigurable):
        def reconfigure(self, *, encoding: str) -> None:
            raise ValueError("underlying buffer has been detached")

    _reconfigure(_Detached("cp1252"))  # must not raise


def test_force_utf8_output_touches_both_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    out, err = _Reconfigurable("cp1252"), _Reconfigurable("cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    force_utf8_output()
    assert out.requested == ["utf-8"]
    assert err.requested == ["utf-8"]


def _run_cli(*command: str) -> bytes:
    """Run the CLI as a subprocess with stdout as a pipe.

    That is the exact condition under which Python reaches for the locale encoding, and the
    condition the bug appeared under. The environment is not given PYTHONUTF8, so the process
    -- not the operator's shell -- is what has to make this pass.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "errata_bench.cli", *command],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    assert proc.returncode in {0, 1, 2, 3}, proc.stderr.decode("utf-8", "replace")
    return proc.stdout


def test_status_emits_a_utf8_section_mark_through_a_pipe() -> None:
    raw = _run_cli("status")
    assert SECTION_UTF8 in raw, "expected a UTF-8 encoded section mark"
    assert b"\xa7" not in raw.replace(SECTION_UTF8, b""), "found a bare cp1252 section mark"
    raw.decode("utf-8")  # raises if any byte sequence is not valid UTF-8


@pytest.mark.parametrize(
    "command",
    [("status",), ("equivalence", "--show", "none"), ("coverage",), ("operating-point",)],
)
def test_every_subcommand_emits_decodable_utf8(command: tuple[str, ...]) -> None:
    """Weaker than the § assertion above, and applies to commands that may not print one.

    The point is that no subcommand emits a byte sequence that is not valid UTF-8 -- which is
    what a locale-encoded non-ASCII character looks like to any reader downstream.
    """
    _run_cli(*command).decode("utf-8")
