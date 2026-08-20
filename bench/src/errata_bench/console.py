"""Console encoding, forced at the entry point.

Both CLIs print the spec's section marks (§), the en-dashes in interval notation, and the
metric names carried over from the standards -- and `errata-r0 status` is the first command a
judge, a customer or a fresh session runs.

On Windows, Python selects the *locale* encoding for stdout when it is not a terminal (cp1252
here), so `§4` leaves the process as byte 0xA7 and arrives anywhere expecting UTF-8 as a
replacement character. The output is then wrong in exactly the place the reader is being asked
to trust a number.

Fixing this in the operator's environment (`PYTHONUTF8=1`, `chcp 65001`) works and is not good
enough: it makes correct output conditional on something the reader has to know to do. The
process decides its own output encoding.
"""

from __future__ import annotations

import sys
from typing import TextIO


def force_utf8_output() -> None:
    """Reconfigure stdout and stderr to UTF-8, in place.

    Idempotent, and a no-op on a stream that is already UTF-8 or that does not support
    reconfiguration (a captured or replaced stream under test, for instance). Never raises:
    a CLI must not die over the encoding of its own progress output.
    """
    for stream in (sys.stdout, sys.stderr):
        _reconfigure(stream)


def _reconfigure(stream: TextIO | None) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
    if encoding in {"utf8", "utf8sig"}:
        return
    try:
        reconfigure(encoding="utf-8")
    except (ValueError, OSError):  # pragma: no cover -- stream already detached or unusable
        return
