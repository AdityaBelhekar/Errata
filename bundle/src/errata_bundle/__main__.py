"""``python -m errata_bundle`` -- build bundles, or run the FE-2.5 projection gate."""

from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import Counter


def _probe(argv: list[str]) -> int:
    """The FE-2.5 gate: do evidence boxes land on the words, across a corpus?"""
    from .probe import probe_document

    parser = argparse.ArgumentParser(prog="errata-bundle probe")
    parser.add_argument("paths", nargs="*", default=["var/**/*.pdf"])
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--words", type=int, default=40)
    parser.add_argument("--zoom", type=float, default=2.0)
    args = parser.parse_args(argv)

    files: list[str] = []
    seen: set[str] = set()
    for pattern in args.paths:
        for path in sorted(glob.glob(pattern, recursive=True)):
            name = os.path.basename(path)
            if name not in seen:
                seen.add(name)
                files.append(path)

    if not files:
        print("no documents matched")
        return 1

    print(f"{'document':46} {'pg':>3} {'meas':>5} {'unme':>5} {'mode':>9} {'agree':>6}  verdict")
    print("-" * 92)

    offsets: Counter = Counter()
    failing: list[str] = []
    pages = 0

    for path in files:
        for probe in probe_document(
            path, pages=args.pages, words_per_page=args.words, zoom=args.zoom
        ):
            pages += 1
            for word in probe.measurable:
                offsets[word.offset] += 1
            if not probe.clean:
                failing.append(f"{os.path.basename(path)} p{probe.page}")
            print(
                f"{os.path.basename(path)[:46]:46} {probe.page:3} {len(probe.measurable):5} "
                f"{len(probe.unmeasurable):5} {probe.modal_offset!s:>9} "
                f"{probe.agreement:6.0%}  {'CLEAN' if probe.clean else 'FAIL'}"
            )

    total = sum(offsets.values()) or 1
    print("-" * 92)
    print(f"pages probed: {pages}   pages failing: {len(failing)}")
    print(f"words registering at (0,0): {offsets[(0, 0)]}/{total} = {100 * offsets[(0, 0)] / total:.1f}%")
    print(f"offset histogram (top 5): {offsets.most_common(5)}")

    if failing:
        print(
            "\nFailing pages are not automatically a transform fault. A page whose text layer is "
            "OCR over a scan will never register, because the OCR boxes are approximations of ink "
            "the renderer draws from an image. Check whether the document is born-digital before "
            "changing any geometry -- see finding G-2 in docs/frontend/FE-2.5-CONTRACT.md."
        )
        print("  " + "\n  ".join(failing))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "probe":
        return _probe(argv[1:])
    if argv and argv[0] == "build":
        from .build import main as build_main

        return build_main(argv[1:])
    if argv and argv[0] == "serve":
        from .serve import main as serve_main

        return serve_main(argv[1:])
    print(
        "usage: python -m errata_bundle {build,probe} ...\n\n"
        "  build   audit a catalog and write one Evidence Bundle per finding\n"
        "  probe   the FE-2.5 gate: register evidence boxes against rendered ink\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
