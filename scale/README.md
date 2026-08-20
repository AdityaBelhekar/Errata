# `scale/` — `errata-scale`, the R2 catalog-scale audit

R1 proved one SKU could be audited against one document. R2 answers the question a buyer asks:
*what does this tell me about my whole catalog, and can two people act on it?*

## What it does

```
catalog file ─► hash-registered as an artifact ─► GROUNDABLE FRACTION (FR-8.1)
                          │                                  │
                          ▼                                  ▼
        T0  the feed against its own units, and              what can be audited at all,
            against itself -- every record, no               stated BEFORE anything is
            document needed                                  audited
                          │
                          ▼
        T1  errata_audit.audit_sku, groundable records only
                          │
                          ▼
        T2  counter-evidence -- disagreements only
                          │
          cluster (FR-8.5) ─► rank (FR-8.4) ─► T3  the drainable queue
                                                        │
                                    append-only ledger ─┴─► batch reversal (FR-8.8)
```

```bash
./.venv/Scripts/errata-scale.exe run --html var/scale/report.html
```

The exit code is the decision, not a diagnostic: **0** nothing needs a reviewer, **1** findings,
**2** could not run, **3** the run failed.

## The five things worth knowing before reading the code

**1. The groundable fraction is printed above the findings, not below them.** On the demonstration
corpus it is 2.77%. A defect count over a catalog where 97% of records have no retrievable document
is unreadable without it, and it is the number an audit vendor is most tempted to leave out.

**2. T0 is new, and it never pretends to have read a document.** It checks the feed against the
units the class declares (`rated_current` holding `0.125 kg` is wrong without opening anything) and
against itself (rows sharing a manufacturer part number that disagree). Every comparison goes
through `errata_comparator.compare_attribute` rather than string equality, so `125 g` against
`0.125 kg` resolves silently — FR-5.3 holds at T0 exactly as it holds at T1.

**3. A structural finding still cites a span.** The catalog file is bytes with a sha256, and a cell
inside it has a character span exactly like a cell inside a PDF does. `feedindex.py` registers it,
so nothing here relaxes the evidence rule to get a finding out of the door. The bbox is `None`,
which is correct: a CSV has no geometry, and none is invented.

**4. Signatures key to artifacts, never to companies.** There is no schema field for a supplier, a
brand or a vendor; `assert_no_named_organisation_field` runs at import and a test asserts that a
schema growing one is rejected. A defect count keyed to a named company, produced by a system with a
non-zero false-positive rate, published inside a customer's organisation, is defamation with a
dashboard (FR-8.6).

**5. Nothing updates and nothing deletes.** A correction is a new claim whose `supersedes` names the
old one, which is what makes batch reversal a *query* rather than a recovery project. It is checked
statically over the whole repository:

```bash
./.venv/Scripts/errata-scale.exe integrity
```

## Commands

| | |
|---|---|
| `run` | the whole catalog, T0→T3; `--html`, `--json`, `--ledger`, `--no-documents` |
| `groundable` | the inventory alone; `--bucket <name>` enumerates one to record level |
| `clusters` | error signatures with the fingerprint that grouped them |
| `queue` | the ranked queue and how much of it is drained |
| `drain` | record decisions over the queue — **scripted, and it says so on every run** |
| `reverse` | reverse a batch as a query; `--dry-run` shows what would go |
| `chain` | the supersedes chain for one SKU |
| `integrity` | FR-8.2's source scan |
| `corpus` | rebuild the demonstration catalog at any size |
| `policy` | the resolution policy this build would apply |
| `status` | what R2 can do, and what it declines to claim |

## The demonstration corpus

**Generated, not committed.** Ten thousand rows of constructed catalog is not source, and a
repository that commits fixtures at that size teaches everyone to stop reading diffs.

```bash
./.venv/Scripts/errata-scale.exe corpus --total 25000
```

| | Real | Constructed |
|---|---|---|
| the ABB S200 datasheets, and every span read from them | ✅ | |
| stratum S1 — 278 rows, from R1's generator | ✅ | |
| the value pool S2 draws from (IEC preferred series, the datasheet's weights) | ✅ | |
| **stratum S2 — 9,723 rows and every defect in them** | | **generated here** |

Mutation is by `sha256(family key) % 100`, so the corpus is reproducible from the SKU list alone in
any Python, in any iteration order, forever. A seeded RNG would tie it to a call order.

**Detection numbers therefore describe a population we created.** Grounding, where a document
exists, is empirical. That distinction is written into `var/scale/provenance.yaml`, printed by the
CLI, rendered on every HTML report, and pinned by a test — see decision **D-4** in `PHASES.md` §10.

## What R2 does not claim

- **The exit criterion asks for a *public* 10k+ catalog and this is not one.** Three independent
  hunts closed on the same negative result; `docs/R2-report.md` §7 records them. Open, not waived.
- **There is still no calibration set (FR-6.1).** Structural findings carry no probability at all
  and are ranked on blast radius alone. Every queue row says so.
- **Revenue weight and propagation count are unset**, and rendered as stated defaults rather than as
  measurements.
- Errata grades. It never enriches, and it never writes to a customer PIM (ADR-001).

## Full numbers

`docs/R2-report.md`.
