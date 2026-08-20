"""NFR-7 -- licence hygiene, as a check a build can fail on rather than a paragraph in NOTICE.

The requirement has an acceptance criterion and it names the mechanism: *"CI licence check on
every build."* Three things have to be true and until now all three were true by somebody
remembering:

1. **Apache-2.0 for open components.** Every distribution declares it, and the tree carries the
   licence text.
2. **ODC-By attribution for ETIM.** ETIM's classes, features, units and value lists are used under
   the Open Data Commons Attribution Licence, which requires attribution *wherever the content is
   surfaced*. NOTICE has to name the licence, the licensor and the URL.
3. **No licensed dictionary content committed.** ECLASS ships as an adapter that reads the
   customer's own licensed dictionary (ADR-003). Not one ECLASS IRDI may be in the tree, and --
   the part that actually matters -- not one may be in a built wheel, because package-data globs
   are exactly how a file nobody meant to ship gets shipped.

A fourth check is here because it is the one that bites in practice and nobody had written it:

4. **Every third-party runtime dependency is under a permissive licence.** Apache-2.0 is a
   permissive licence and a repository distributed under it cannot carry a copyleft dependency
   into a customer's build without saying so. The allowlist is by licence family, and an
   unrecognised licence is a **finding, not a pass** -- the failure mode here is a dependency
   whose metadata says nothing being waved through because the check could not read it.

**What this module does not do.** It does not read a licence out of a file and decide whether the
text really is Apache-2.0; it checks declarations and the absence of content. That is worth saying
plainly rather than letting a green tick imply a legal review happened. What it catches is drift:
a distribution added without a licence field, an ECLASS code pasted into a fixture, a dependency
added with a licence nobody looked at.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import yaml

from .eclass import EclassContentFound, assert_clean, scan, scan_distribution

__all__ = [
    "DECISIONS_FILE",
    "PERMISSIVE_LICENCES",
    "REQUIRED_LICENCE",
    "LicenceDecision",
    "LicenceReport",
    "check_licences",
    "load_decisions",
]

REPO_ROOT = Path(__file__).resolve().parents[3]

#: What every distribution in this repository must declare.
REQUIRED_LICENCE = "Apache-2.0"

#: The seven distributions. Listed rather than globbed: a new one that forgets a licence field
#: should fail this check, and a glob would simply not see it.
DISTRIBUTIONS = ("valuesem", "spec", "comparator", "bench", "audit", "scale", "ecosystem")

#: Licence families a repository distributed under Apache-2.0 may depend on without further
#: thought. Matched as a substring of the declared licence string, lowercased, because the
#: metadata field is free text and "MIT License", "MIT" and "Expat" are all the same licence.
#:
#: Weak copyleft (LGPL, MPL) is deliberately ABSENT rather than allowed. It is usually fine when a
#: dependency is merely imported, and "usually fine" is a judgment for a person to record against a
#: named dependency, not a default this check should make on their behalf.
PERMISSIVE_LICENCES = (
    "apache",
    "mit",
    "bsd",
    "isc",
    "psf",
    "python software foundation",
    "zlib",
    "unlicense",
    "public domain",
    "expat",
)

#: Attribution ODC-By requires, and the phrases that evidence it. All must be present in NOTICE.
ODC_BY_MARKERS = (
    "Open Data Commons Attribution",
    "opendatacommons.org/licenses/by",
    "ETIM International",
)


#: Where recorded decisions live. A dependency whose licence is not permissive must appear here
#: or the check fails -- see the file's own header for why that is the mechanism rather than a
#: wider allowlist.
DECISIONS_FILE = REPO_ROOT / "data" / "licences" / "third-party-decisions.yaml"


@dataclass(frozen=True, slots=True)
class LicenceDecision:
    """One non-permissive dependency, and the state of the decision about it."""

    dependency: str
    licence: str
    status: str
    owner: str
    reviewed: str
    body: dict

    @property
    def accepted(self) -> bool:
        return self.status == "acknowledged"

    def summary(self) -> str:
        return (
            f"{self.dependency} is {self.licence} -- {self.status.upper()}, "
            f"owner {self.owner}, reviewed {self.reviewed}"
        )


def load_decisions(path: Path | str = DECISIONS_FILE) -> dict[str, LicenceDecision]:
    """Recorded licence decisions, by dependency name. Absent file means no decisions recorded."""
    path = Path(path)
    if not path.exists():
        return {}
    document = yaml.safe_load(path.read_text("utf-8")) or {}
    decisions: dict[str, LicenceDecision] = {}
    for entry in document.get("decisions", ()):
        name = str(entry["dependency"]).lower()
        decisions[name] = LicenceDecision(
            dependency=str(entry["dependency"]),
            licence=str(entry.get("licence", "")),
            status=str(entry.get("status", "open")),
            owner=str(entry.get("owner", "UNASSIGNED")),
            reviewed=str(entry.get("reviewed", "")),
            body=dict(entry),
        )
    return decisions


@dataclass(frozen=True, slots=True)
class LicenceReport:
    checked: tuple[str, ...]
    findings: tuple[str, ...]
    acknowledged: tuple[LicenceDecision, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.findings

    def text(self) -> str:
        lines = ["NFR-7 -- licence hygiene", ""]
        lines += [f"  ok    {name}" for name in self.checked]
        for decision in self.acknowledged:
            # Printed on every run, at the top of the report, for as long as the risk is
            # outstanding. An acknowledged risk that stops being visible has become a forgotten one.
            lines.append("")
            lines.append(f"  RISK  {decision.summary()}")
            for key in ("the_risk", "decision_required"):
                text = str(decision.body.get(key, "")).strip()
                if text:
                    lines.append(f"        {key}:")
                    lines += [f"          {line}" for line in text.splitlines()]
        if self.findings:
            lines.append("")
            lines += [f"  FAIL  {finding}" for finding in self.findings]
            lines.append("")
            lines.append(f"  {len(self.findings)} finding(s). NFR-7 is not met.")
        elif self.acknowledged:
            lines.append("")
            lines.append(
                f"  No blocking findings. {len(self.acknowledged)} acknowledged licence risk(s) "
                "remain outstanding and are printed in full above. NFR-7 is met; the risk is not "
                "closed, and a build that goes green on it has not made it go away."
            )
        else:
            lines.append("")
            lines.append("  All licence checks passed.")
        return "\n".join(lines)


def _declared_licence(pyproject: Path) -> str:
    project = tomllib.loads(pyproject.read_text("utf-8")).get("project", {})
    licence = project.get("license", "")
    if isinstance(licence, dict):
        # PEP 621's older table form. Accepted, and normalised so the comparison below is one
        # comparison rather than two shapes with two code paths.
        licence = licence.get("text", "") or licence.get("file", "")
    return str(licence)


def _dependency_licence(name: str) -> str:
    """The licence a distribution declares, from whichever field it used.

    Setuptools, hatch and flit disagree about where this goes -- ``License``, ``License-Expression``
    or a ``License :: OSI Approved :: ...`` classifier -- so all three are read. An empty result
    means the package declared nothing findable, which this module treats as a finding rather than
    as permission.
    """
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return ""

    for field in ("License-Expression", "License"):
        value = meta.get(field, "") or ""
        if value and value.strip().upper() != "UNKNOWN":
            return value

    classifiers = meta.get_all("Classifier") or []
    for classifier in classifiers:
        if classifier.startswith("License :: "):
            return classifier.rsplit(" :: ", 1)[-1]
    return ""


def _runtime_dependencies() -> set[str]:
    """Third-party runtime dependencies of the seven distributions, excluding our own.

    Read from the pyprojects rather than from the lock file: the lock carries the dev toolchain
    too, and pytest's licence is not something a customer ever receives.
    """
    names: set[str] = set()
    for distribution in DISTRIBUTIONS:
        pyproject = REPO_ROOT / distribution / "pyproject.toml"
        if not pyproject.exists():
            continue
        project = tomllib.loads(pyproject.read_text("utf-8")).get("project", {})
        for requirement in project.get("dependencies", ()):
            name = (
                str(requirement)
                .split(";")[0]
                .split("[")[0]
                .split(">=")[0]
                .split("==")[0]
                .split("<")[0]
                .split("~")[0]
                .strip()
            )
            if name and not name.lower().startswith("errata-"):
                names.add(name)
    return names


def check_licences(*, distributions: tuple[Path, ...] = ()) -> LicenceReport:
    """Run every NFR-7 check. ``distributions`` are built wheels/sdists to scan, if any."""
    checked: list[str] = []
    findings: list[str] = []
    acknowledged: list[LicenceDecision] = []
    decisions = load_decisions()

    # 1. Apache-2.0 on every distribution, and the licence text present.
    for name in DISTRIBUTIONS:
        pyproject = REPO_ROOT / name / "pyproject.toml"
        if not pyproject.exists():
            findings.append(f"{name}/pyproject.toml is missing")
            continue
        declared = _declared_licence(pyproject)
        if REQUIRED_LICENCE.lower() not in declared.lower():
            findings.append(
                f"{name} declares licence {declared!r}, not {REQUIRED_LICENCE}. NFR-7 requires "
                "Apache-2.0 for every open component."
            )
        else:
            checked.append(f"{name} declares {REQUIRED_LICENCE}")

    if not (REPO_ROOT / "LICENSE").exists():
        findings.append("LICENSE is absent from the repository root")
    else:
        checked.append("LICENSE present")

    # 2. ODC-By attribution for ETIM, in NOTICE, where ODC-By requires it.
    notice_path = REPO_ROOT / "NOTICE"
    if not notice_path.exists():
        findings.append("NOTICE is absent; ODC-By requires attribution wherever ETIM is surfaced")
    else:
        notice = notice_path.read_text("utf-8")
        missing = [marker for marker in ODC_BY_MARKERS if marker not in notice]
        if missing:
            findings.append(
                f"NOTICE does not carry the ODC-By attribution ETIM requires; missing {missing}"
            )
        else:
            checked.append("NOTICE carries the ODC-By attribution for ETIM")

    # 3. No ECLASS content -- in the tree, and in anything built from it.
    reports = [scan()]
    reports += [scan_distribution(path) for path in distributions]
    try:
        assert_clean(reports)
    except EclassContentFound as exc:
        findings.append(str(exc))
    else:
        where = "the working tree" + (
            f" and {len(distributions)} built distribution(s)" if distributions else ""
        )
        checked.append(f"no ECLASS content in {where} (ADR-003, FR-9.8)")

    # 4. Every third-party runtime dependency is permissively licensed.
    for name in sorted(_runtime_dependencies()):
        declared = _dependency_licence(name)
        if not declared:
            findings.append(
                f"runtime dependency {name!r} declares no licence this check can read. That is a "
                "finding rather than a pass: a dependency whose terms nobody looked at is exactly "
                "what this check exists to surface."
            )
            continue
        lowered = declared.lower()
        if any(family in lowered for family in PERMISSIVE_LICENCES):
            checked.append(f"{name} is {declared.splitlines()[0][:60]}")
            continue

        decision = decisions.get(name.lower())
        if decision is None:
            findings.append(
                f"runtime dependency {name!r} is licensed {declared.splitlines()[0][:80]!r}, which "
                "is not on the permissive allowlist and has no entry in "
                f"{DECISIONS_FILE.name}. Record the decision against the dependency by name -- do "
                "not widen PERMISSIVE_LICENCES to make this pass."
            )
        elif decision.accepted:
            acknowledged.append(decision)
        else:
            findings.append(
                f"runtime dependency {name!r} is licensed {declared.splitlines()[0][:80]!r} and "
                f"its decision is recorded as {decision.status!r}, which is not an acceptance. "
                "An unresolved licence risk must not sit quietly in a green build."
            )

    return LicenceReport(
        checked=tuple(checked),
        findings=tuple(findings),
        acknowledged=tuple(acknowledged),
    )
