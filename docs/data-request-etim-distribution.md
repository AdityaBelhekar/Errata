# Data request — ETIM class distribution (R0 gate 3 / FR-0.4)

**Status:** ready to send. Not sent — sending it is an outward-facing act and belongs to a person.
**Decision it implements:** D-1, Route B (`PHASES.md` §10).
**What it unblocks:** R0 gate 3, currently `NOT_MEASURED`. Nothing else in the project is waiting
on it, so it can sit in someone's outbox without holding anything up.

Send to whichever of these is closest to hand — any one of them is sufficient:

- **2BA** (Netherlands, 4M+ product records) — `info@2ba.nl`
- **IDEA** (North America, IDW datapool) — via `idea4industry.com`
- **ETIM International** — `info@etim-international.com`
- **any ETIM-adopting distributor** you already have a relationship with (Sonepar, Rexel, Graybar,
  WESCO, Würth). A friendly account manager is usually faster than a formal channel.

---

## What we need — two columns

```
class_id,sku_count
EC000042,18432
EC000003,9105
EC001047,412
...
```

That is the whole request. `class_id` is the ETIM `ARTCLASSID`; `sku_count` is however many
distinct sellable products are classified into it. One row per class that has at least one product.

**We do not need, and would rather not receive:**

- product identifiers, MPNs, GTINs or descriptions
- prices, volumes, margins or any commercial figure
- manufacturer or customer names
- attribute values of any kind

A histogram over class ids is not commercially sensitive in the way a product list is, which is
the main reason to ask for exactly this and nothing more.

---

## Draft message

> Subject: Request — anonymised ETIM class distribution (class id + product count)
>
> Hello,
>
> We are building an open evaluation harness for product-data quality and have hit a gap we
> cannot close from public sources. We need one anonymised histogram: for each ETIM class id, how
> many distinct products in your datapool are classified into it.
>
> Two columns — `class_id`, `sku_count` — and nothing else. No product identifiers, no
> descriptions, no attribute values, no prices, no manufacturer names. Any ETIM release (10.0 or
> 11.0) is fine, and a rough count is fine; we are measuring the *shape* of the distribution, not
> auditing your data.
>
> What it is for: we are computing how many ETIM classes could realistically clear a statistical
> confidence floor under a fixed labelling budget. On a synthetic Zipf distribution the answer is
> that a few percent of classes cover roughly three quarters of the volume — which, if it holds on
> real data, is a useful and slightly uncomfortable result for anyone planning per-class
> calibration. We would rather publish that against a real distribution than a simulated one.
>
> We are happy to (a) publish the finding with attribution, (b) publish it without naming the
> source, or (c) share the analysis privately and publish nothing — your call, and we will put it
> in writing before you send anything.
>
> If a full histogram is awkward, even the top 200 classes by count would be enough to change the
> answer from a simulation into a measurement.
>
> Thank you,

---

## When it arrives

```bash
./.venv/Scripts/errata-r0.exe coverage --distribution <file.csv>
```

**No code changes are needed.** `coverage.load_distribution` already accepts CSV, TSV, YAML and
JSON, and the column aliases include `etim_class` → `class_id`. The gate flips from
`NOT_MEASURED` to a real verdict on the strength of the file's provenance alone.

Then, in this order:

1. Register the file in `data/reference/manifest.json` with its sha256, the source, and the date —
   provenance travels with the data (FR-1.3, and the pattern the rest of `var/reference/` follows).
2. Record the provenance **in the file** so the gate does not have to infer it. An undeclared
   provenance is read as empirical and produces a caveat saying so; better to declare it.
3. Compare against the synthetic finding — 5.95% of classes / 77.39% of SKUs at a 5,000-label
   budget — and report whether the real distribution **confirms or contradicts** it. Expect
   confirmation; say so either way.
4. If class coverage is single-digit, narrow R2 scope to named high-volume classes. That is
   FR-0.4's own acceptance criterion, not an improvisation.

## What we do NOT do while waiting

Scrape a distributor and infer the ETIM class ids. The counting is easy and the crosswalk is the
whole difficulty: distributor front-ends expose their own merchandising categories, and an
inferred mapping produces a number that looks measured and is not. Under ground rule 1 that is
strictly worse than `NOT_MEASURED`.

If a **published** crosswalk from a distributor's own categories to ETIM class ids turns up, that
changes the calculus and the route reopens. Absent one, it stays shut.
