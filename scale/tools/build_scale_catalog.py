"""Build the R2 demonstration catalog and its provenance file.

    ./.venv/Scripts/python.exe scale/tools/build_scale_catalog.py
    ./.venv/Scripts/python.exe scale/tools/build_scale_catalog.py --total 25000

The generator itself lives in :mod:`errata_scale.corpus`, inside the distribution, so that the rule
deciding what each row is can be imported by tests rather than re-implemented by them. This script
is the thin command that writes the files out.

Output lands in ``var/scale/`` -- gitignored, like every other generated artifact in this
repository. Ten thousand rows of constructed catalog is not source, and a repository that commits
its own test fixtures at that size teaches everyone to stop reading diffs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scale" / "src"))

import yaml  # noqa: E402

from errata_scale.corpus import provenance, write_catalog  # noqa: E402

REAL_CATALOG = ROOT / "audit" / "src" / "errata_audit" / "demo" / "catalog.csv"
OUT_DIR = ROOT / "var" / "scale"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--total",
        type=int,
        default=10_000,
        help="total rows, documented and constructed together (default 10000)",
    )
    parser.add_argument("--out", type=Path, default=OUT_DIR / "catalog.csv")
    parser.add_argument("--real-catalog", type=Path, default=REAL_CATALOG)
    args = parser.parse_args(argv)

    if not args.real_catalog.exists():
        print(
            f"the R1 demonstration catalog is not at {args.real_catalog}. It is the documented "
            "stratum of this corpus and the run is not honest without it; build it with "
            "audit/tools/build_demo_catalog.py first.",
            file=sys.stderr,
        )
        return 2

    real, synthetic_count, synthetic = write_catalog(
        args.out, real_catalog=args.real_catalog, target_total=args.total
    )

    document = provenance(
        real_count=real,
        synthetic=synthetic,
        real_catalog=str(args.real_catalog.relative_to(ROOT)).replace("\\", "/"),
        destination=str(args.out.relative_to(ROOT)).replace("\\", "/"),
    )
    provenance_path = args.out.with_name("provenance.yaml")
    provenance_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    total = real + synthetic_count
    print(f"wrote {args.out}")
    print(f"  {total:,} rows -- {real:,} documented (S1), {synthetic_count:,} constructed (S2)")
    print(f"  expected T0 findings  {document['expected']['findings']:,}")
    print(f"  expected T0 declines  {document['expected']['declines']:,}")
    print(f"  equivalence traps     {document['expected']['equivalence_traps']:,}")
    print(f"wrote {provenance_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
