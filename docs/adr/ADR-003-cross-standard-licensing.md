# ADR-003 — Cross-standard mapping under asymmetric licensing

**Status:** Accepted · **Date:** 17 August 2026

## Context

Verified in the Phase 4 pass:

- **ETIM** — the Classification Model and the MC extension are published under the **Open Data
  Commons Attribution Licence (ODC-By)**: share, adapt and redistribute derivatives, with
  attribution. Caveat: the free international distribution covers the coding structure and 'ETIM
  English' plus Belgian-Flemish, Belgian-French, German, Italian, Finnish and Norwegian — **not all
  local language versions**.
- **ECLASS** — requires a licence. Types: Single License, Concordance License, Pay per IRDI, or
  association membership. Fees are calculated by company size, counting employees including all
  >50% subsidiaries. ECLASS 16.0 carries roughly 50,000 classes and 23,000 properties and is the
  richer target.
- **UNSPSC** — a four-level hierarchy (Segment, Family, Class, Commodity) as an eight-digit code,
  each level a two-character numeric value plus a textual description. **There is no attribute
  layer to map to.**

The open-source strategy needs a mapping asset, and half the map has a licence gate.

## Options considered

| Option | Complexity | Cost | Scalability | Maintenance | Legal exposure |
|---|---|---|---|---|---|
| **A.** Ship ETIM + ECLASS mappings openly | Low | Low | High | Moderate | **Unacceptable — redistributes licensed content** |
| **B.** ETIM-only open; ECLASS via bring-your-own-licence adapter | Medium | Low | High | Two code paths | Clean. Customer's licence, customer's data, our code |
| **C.** Buy an ECLASS licence, ship the map closed | Medium | Recurring fee scaling with our headcount | High | Single path | Clean but kills the open contribution |
| **D.** Join ECLASS e.V. as a member | Low | Membership fee | High | Single path | Clean, plus standards-body access — but membership terms are not redistribution rights |

## Decision

**B, with D as a deliberate later move.**

Ship openly:

- the ETIM class and attribute layer (ODC-By, attributed in [NOTICE](../../NOTICE)), and
- the **ETIM ↔ UNSPSC attribute bridge** — the specific documented hole. Since UNSPSC provides an
  eight-digit code with no attribute layer, anyone wanting parametric filtering from a
  UNSPSC-classified catalog must build that bridge themselves.

ECLASS support ships as an adapter that reads the customer's own licensed dictionary files at
runtime. **No ECLASS content in the repository, the container image, or the benchmark set.**

Pursue ECLASS e.V. membership once revenue exists — for standing in the standards process, not for
redistribution rights.

## How this is enforced

- `/eclass-adapter` is specified to contain code only, and is verified by inspection of build
  artifacts (FR-9.8).
- `NOTICE` states the attribution and the exclusion explicitly.
- Manufacturer datasheets are copyrighted and are **never redistributed**: the gold set ships as
  URLs, content hashes, page-level annotation layers, bounding-box coordinates and gold values,
  with a fetch script reconstructing the corpus locally (FR-9.5). `.gitignore` excludes `*.pdf`.
- Licence hygiene is a CI check on every build (NFR-7).

## Consequences

**Easier.** Publishing without legal review on every release. The ETIM↔UNSPSC bridge becomes a
genuine free contribution to a real hole rather than a repackaging of someone's licensed asset.
ETIM-region adoption.

**Harder.** ECLASS-first customers — largely German industrial and Siemens Teamcenter shops — need
a licence before onboarding, which is a real sales-cycle tax. Two mapping code paths to maintain.
The free ETIM tier does not include all local language versions, so multi-language customers hit a
gap we did not create and must still explain.

**Revisit when:** ECLASS licensing terms change, or a customer's own licence permits derivative
redistribution that would let a shared map exist legally.
