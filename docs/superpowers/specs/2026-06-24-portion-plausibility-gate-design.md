# Curation-Time Portion-Plausibility Gate — Design

**Date:** 2026-06-24
**Status:** Approved (approach), pending spec review
**Author:** Robert Soroka (with Claude)

## Summary

Add a sanity gate to recipe curation that rejects recipes whose per-portion
quantities are physically implausible (e.g. **680 g of chicken for one
portion**). The same pure detector also backs a read-only audit command we run
against the existing corpus to find offenders and calibrate thresholds.

Two surfaces, one detector:

1. **Gate** — `curate_from_source` soft-rejects an implausible recipe before it
   persists (it never publishes). Mirrors the existing "no instructions"
   reject; honors curation's "never raises" contract.
2. **Audit** — `manage.py audit_portion_plausibility` reports offenders and the
   per-portion mass distribution across the corpus. Zero writes. Run it first
   to calibrate thresholds on real data, then rely on the gate.

The detector is the **single source of truth**; gate and audit both call it.

## Problem / Motivation

Per-recipe portion scaling is live (`[[recipe-deals-headline]]`,
`2026-06-23-per-recipe-portion-scaling-design.md`). The frontend faithfully
scales ingredient quantities against `base_servings`. That makes a pre-existing
data problem newly visible: some recipes carry quantities that, divided by
their stated `base_servings`, yield absurd per-portion amounts.

Root cause: `base_servings` is author/LLM-supplied and trusted blindly
(`recipe_curation.py:233`, `max(1, _as_int(...) or 1)` — defaults to **1**).
When a recipe's quantities were transcribed for a 4-serving dish but
`base_servings` lands on 1, **every** ingredient is inflated ~4×. The stepper
surfaces it as "680 g chicken / 1 portion."

Because a `base_servings` error inflates everything proportionally, the most
robust detector is **total weighable mass per portion**, complemented by a
**single-ingredient cap** that directly targets the headline symptom.

There is currently no plausibility check anywhere in the curation pipeline.

## Scope

**In scope:**
- Pure detector function + thresholds.
- Read-only audit management command.
- Soft-reject gate wired into `curate_from_source`.
- Unit tests (detector) + one curation test (flagged recipe not persisted).

**Out of scope (explicit):**
- The "1,5 vejce" fractional-discrete-unit rounding — a separate *frontend*
  problem (`portions.ts` rounds `ks`/counted units to halves/decimals). Filed
  as a fast follow-up spec.
- Auto-correcting `base_servings` (rejected in favor of flag-and-fix-by-hand).
- Backfilling/repairing existing offenders — the audit lists them; cleanup is
  manual, later.

## Components

### 1. Detector — `diet_planner/services/recipe_plausibility.py` (new)

Pure, no I/O, never raises.

```
SINGLE_CAP_G   = 500     # max weighable mass of one ingredient per portion
TOTAL_CEILING_G = 1200   # max total weighable mass per portion

@dataclass
class PlausibilityResult:
    ok: bool
    reasons: list[str]              # human-readable, e.g. "kuřecí prsa: 680 g/portion > 500"
    per_portion_total_g: float
    per_portion_max_single_g: float
    offenders: list[dict]           # [{name, grams_per_portion}] over the single cap

def check_portion_plausibility(
    ingredients: list[dict],
    base_servings: int,
) -> PlausibilityResult: ...
```

Rules:
- Weighable rows only: `unit` (lowercased, trimmed) in `{"g", "ml"}`, treating
  **ml ≈ g** (food density ~1; adequate for a sanity gate). All other units
  (`ks`, `lžíce`, …), to-taste rows, and non-numeric/`≤0` quantities are
  ignored — under-counting only makes the gate *more* conservative.
- `servings = base_servings if base_servings > 0 else 1`.
- `per_portion_total_g = sum(weighable grams) / servings`.
- `per_portion_max_single_g = max(weighable grams) / servings` (0 if none).
- `ok = False` when `per_portion_total_g > TOTAL_CEILING_G` **or**
  `per_portion_max_single_g > SINGLE_CAP_G`. `reasons` records which fired and
  the offending numbers.
- Quantity parsing reuses the existing tolerant coercion (numeric, or Czech
  decimal-comma string like `"1,5"`); a value that won't parse is skipped, not
  an error.

Thresholds are provisional constants — calibrated from audit output before the
gate is relied upon.

### 2. Audit — `manage.py audit_portion_plausibility` (new)

Read-only. Options:
- `--status {published,draft,all}` (default `published`).
- `--csv <path>` optional machine-readable dump.

Output:
- Total scanned, count flagged, % flagged.
- Percentile distribution of `per_portion_total_g` (p50/p75/p90/p95/max) — the
  empirical basis for setting `TOTAL_CEILING_G`.
- Per offender: `slug`, `name_cs`, `base_servings`, `per_portion_total_g`,
  worst ingredient + its grams/portion, which rule fired.

No model writes. This is the calibration and triage tool.

### 3. Gate — `curate_from_source` (`recipe_curation.py`)

After `build_recipe_fields(...)`, before the judge/persist block:

```
if enforce_plausibility:
    p = check_portion_plausibility(fields["ingredients"], fields["base_servings"])
    if not p.ok:
        result.error = "implausible portion: " + "; ".join(p.reasons)
        return result
```

- New param `enforce_plausibility: bool = True` on `curate_from_source` (keeps
  it togglable for tests and staged rollout).
- Soft reject: sets `result.error`, returns a non-ok `CurationResult`, persists
  nothing — identical shape to the existing `"no instructions after curation"`
  path. Never raises.

## Data Flow

```
curate_from_source(entry, enforce_plausibility=True)
  → build_recipe_fields(curated)            # ingredients + base_servings
  → check_portion_plausibility(...)         # NEW
       ok      → judge → _save_with_unique_slug (status=DRAFT, unchanged)
       not ok  → result.error set, return (no persist)

manage.py audit_portion_plausibility --status published
  → for each CuratedRecipe: check_portion_plausibility(...)
  → aggregate + print report (no writes)
```

## Error Handling

- Detector is pure and total: guards `base_servings ≤ 0`, skips unparseable /
  non-positive quantities, returns `ok=True` with zeroed metrics for a recipe
  that has no weighable ingredients (nothing to judge → not implausible).
- Gate failure is a soft reject (`result.error`), consistent with
  `curate_from_source`'s documented "never raises."
- Audit command catches per-recipe errors and continues (one bad row never
  aborts the report), printing a trailing list of skipped rows.

## Testing

Detector (TDD, pure unit tests — write first):
- Normal 4-serving dish → `ok=True`.
- 680 g chicken at `base_servings=1` → trips single cap, `ok=False`.
- Dish inflated ~4× (base 1, should be 4) → trips total ceiling.
- `ml`-heavy soup within bounds → `ok=True` (ml treated as g).
- `ks` / to-taste / non-numeric / `base_servings=0` → handled, no crash.
- Recipe with no weighable rows → `ok=True`.

Curation integration:
- `curate_from_source(..., enforce_plausibility=True)` on a fixture with an
  implausible recipe → `result.ok is False`, `result.error` startswith
  `"implausible portion:"`, and `CuratedRecipe.objects.count()` unchanged.
- Same fixture with `enforce_plausibility=False` → persists as before.

## Rollout Sequence

1. Land detector + audit + tests (gate code present, `enforce_plausibility`
   defaults `True` but no curation runs automatically — see
   `[[recipe-curation-trigger]]`).
2. Run `audit_portion_plausibility` against prod (372 recipes) via the existing
   DO Console harness. Read the distribution.
3. Calibrate `SINGLE_CAP_G` / `TOTAL_CEILING_G` from real percentiles; commit.
4. Triage the flagged existing recipes by hand (fix `base_servings` or unpublish).

## Open Questions

- Final threshold values — deferred to audit output (step 2–3 above).
- Whether to also emit a Czech-friendly `reasons` string for the admin (the
  audit prints English diagnostics; the gate's `result.error` is internal).
