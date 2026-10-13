# Backfilling the prose the availability rescue left stale

**Date:** 2026-08-26
**Status:** design approved, not implemented
**Depends on:** PR #80 (`94b21b9`, live on prod 2026-08-26)

## The problem

`apply_availability_substitutions` rescues un-shoppable recipes by swapping
ingredients, rewriting the affected instruction steps, and disclosing the swap
in `adaptation_note`. Until PR #80 it did **not** rewrite the surrounding
prose, and it skipped `optional` ingredient entries entirely. PR #80 closes
both gaps — but only for adaptations made from now on.

The rows already adapted are unreachable. The command's queryset is

```python
qs = CuratedRecipe.objects.exclude(
    shopping_difficulty=Availability.COMMON,
).filter(adaptation_note='').order_by('id')
```

and `--slug` is ANDed onto that filter, so no invocation of the existing
command can touch a recipe that already carries a note. All 67 adapted rows on
prod fall in that hole.

## What is actually broken

Measured on prod 2026-08-26 by a read-only, no-LLM audit (scratchpad
`audit_adaptations2.py`), using the strict all-stems `_names` matcher and
reading every hit by hand:

| Surface | Genuinely stale |
|---|---|
| Required ingredient lines | 0 |
| Instruction steps | 0 |
| **Optional ingredient lines** | **4 lines / 3 recipes** |
| **Prose (name + description)** | **8 fields / 7 recipes** |

The stale prose:

| Slug | Status | Field(s) | Swap |
|---|---|---|---|
| `ovesna-kase-s-javorovym-sirupem-a-skorici` | published | name + desc | javorový sirup → med |
| `zdravy-bananovy-chleb` | published | desc | javorový sirup → med |
| `javorove-bananove-muffiny` | published | desc | javorový sirup → med |
| `zdrave-bananove-muffiny` | draft | desc | javorový sirup → med |
| `snidanove-tacos` | published | desc | pico de gallo → salsa |
| `mexicke-kureci-nudle-z-cukety` | published | desc | pico de gallo → salsa |
| `taco-salat` | published | desc | pico de gallo → salsa |

The stale optional lines: `ovesna-kase-…` (javorový sirup),
`ovesne-livance` (javorový sirup, avokádový olej), `bezlepkove-livance`
(javorový sirup).

Note that this audit also **settles the open question** of whether the
2026-08-18/19 runs, which applied rewrites while the coherence judge was
failing open, did any damage: they did not. Required ingredients and steps are
clean across all 67 rows.

## Why the two residues need different machinery

`plan_substitutions()` reads the recipe's **current** ingredients. On an
already-adapted row:

- required entries were swapped, so their canonicals are now `COMMON` and are
  skipped — `plan.changes` comes back **empty**;
- optional entries were never swapped, so they are still non-common and a rule
  is found — they land in `plan.optional_changes`;
- therefore `plan.saveable = bool(plan.changes) and not plan.blocking` is
  **False**.

So re-planning yields the optional residue for free but yields *nothing at all*
for the prose residue: the swaps the prose contradicts have already been
applied to the ingredient list, so they no longer appear in any plan. The
change list has to be reconstructed from what the row records.

## Design

A new management command, `backfill_adaptation_prose`. Not a flag on the
existing command: that command's contract is "rescue an un-adapted recipe", and
this one's is "finish a rewrite already disclosed". Overloading one queryset
with both meanings is how the hole appeared in the first place.

**Queryset:** `CuratedRecipe.objects.exclude(adaptation_note='').order_by('id')`
— the exact complement of the rescue command's filter. Options `--slug`,
`--limit`, `--dry-run`, `--skip-judge`, mirroring the existing command.

The command runs across **all** adapted rows; the `_drops()` gate decides which
ones cost anything. If it fires on a row the strict audit missed, that row is
worth fixing too.

### Step 1 — optional ingredient lines (no LLM)

Re-plan the current row with today's substitution table, then apply the subset
of `plan.optional_changes` that this row **has already disclosed** — that is,
where the same `old_name → new_name` swap appears in the original-vs-current
diff or is named in `adaptation_note`. Applied via the existing
`apply_changes_to_ingredients`.

This deliberately bypasses the `saveable` guard, and the "already disclosed"
restriction is what earns that. The guard exists so an optional-only plan
cannot "rewrite a credited recipe for a garnish" — a rule about *introducing* a
change. Within the restriction nothing new is introduced: the
`adaptation_note` already tells the reader `javorový sirup → med`, and an
optional line still reading `javorový sirup` is the row contradicting its own
published disclosure. Applying it makes the recipe honest.

An optional entry whose swap is **not** already disclosed is skipped and
reported, not applied. Swapping it would be a fresh editorial change to
someone else's credited recipe, made without a rescue to justify it — exactly
what the guard is for. All four known stale lines pass the restriction, because
in each case the same ingredient was also swapped in a required entry.

A useful consequence: within this restriction `adaptation_note` can never need
extending, since every applied swap is by construction already named in it.
The note-extension logic below is therefore a correctness guard that should
never fire.

### Step 2 — prose (LLM, fail-closed)

Reconstruct the applied change list by diffing `original_ingredients` against
the ingredients **as of step 1**, index-aligned:

```python
for i, (old, new) in enumerate(zip(original, current)):
    if (old.get('name') or '') != (new.get('name') or ''):
        changes.append(IngredientChange(
            index=i,
            old_name=old.get('name') or '',
            old_slug=old.get('canonical') or '',
            new_name=new.get('name') or '',
            new_canonical=new.get('canonical') or '',
            new_quantity=new.get('quantity'),
            new_unit=new.get('unit') or '',
        ))
```

The diff is ground truth — what this row actually contains — where re-planning
from `original_ingredients` would only report what the swap *would be today*.
The substitution table has changed since these rows were adapted (the PR #72
oat-flour/tamari re-rating, the PR #75 tapioca swap), so a re-plan can name an
ingredient the list does not hold. Prose must describe the food as it stands.

`apply_changes_to_ingredients` edits entries positionally and preserves list
length, so the two lists align by index. Verified on prod: **67/67 rows usable**
— 0 missing snapshots, 0 length mismatches, 0 non-dict entries, and every row
carries 1–3 real name diffs.

The resulting changes are wrapped in a `SubstitutionPlan` and passed to PR #80's
`rewrite_prose(name_cs, description, plan)`, which keeps its fail-closed
contract: wrong shape, empty name, or a removed ingredient left standing raises
`RewriteError` and the row is left exactly as it was. The call is skipped
entirely unless `_drops()` reports that the name or description still leans on
a removed stem — that is what holds this to roughly 7 model calls rather than 67.

### Judge

Reuse `judge_curated_recipe` and `_judge_rejected` unchanged, on an unsaved
candidate, exactly as the rescue command does. A rejection discards the row's
rewrite. When the judge cannot run — the Anthropic balance being dry is the
expected case — the rewrite is applied and the fact is disclosed per row and
counted as `unjudged=N` in the summary. This matches the existing prod contract,
and the audit above establishes that unjudged rewrites came out clean.

### What else the write touches

- `adaptation_note`: append any applied swap the note does not already
  disclose, truncated to `_NOTE_MAX`. In the known data every optional swap is
  already named (the same ingredient was swapped in a required entry), so this
  is a correctness guard rather than an expected edit.
- `shopping_difficulty` / `shopping_blockers`: recomputed via
  `compute_shopping_difficulty`.
- `original_ingredients`: never overwritten — it already holds the author's
  original, and re-snapshotting would destroy the record that proves what
  changed.
- `slug`: **never** regenerated. The URL is public. Same rule as PR #80, and it
  is why `ovesna-kase-s-javorovym-sirupem-a-skorici` will keep a slug naming
  maple syrup after its title stops doing so.

## Error handling

- `original_ingredients` empty, not a list, or length-mismatched → skip the row,
  report it, do not guess. Prod has none of these, but a future row could.
- Non-dict ingredient entries (generated meals carry bare strings) → skipped
  per entry, consistent with `plan_substitutions`.
- `RewriteError` → row untouched, counted as `failed`.
- Judge rejection → row untouched, counted as `failed`.
- Every write is inside `transaction.atomic()` with an explicit
  `update_fields`.

## Testing

TDD, mirroring `test_apply_substitutions.py`. The LLM is injected as a fake, as
the existing rewrite tests already do.

1. Diff reconstruction builds the right `IngredientChange` list, index-aligned.
2. Diff ignores entries whose name is unchanged.
3. An optional-only plan **is** applied by this command when the swap is
   already disclosed — the direct contrast with the rescue command, which
   refuses it outright.
3b. An optional swap that is **not** already disclosed is skipped and reported,
   leaving the ingredient list untouched.
4. A recipe whose prose names nothing removed → **no LLM call at all**.
5. Stale prose → rewritten, name and description both saved.
6. `RewriteError` → row completely untouched.
7. Judge rejection → row completely untouched.
8. Judge unavailable → applied, `unjudged` counted and disclosed.
9. `adaptation_note` extended only when an applied swap is not already named.
10. `slug` unchanged even when `name_cs` changes.
11. Rows with unusable `original_ingredients` are skipped, not crashed on.
12. **Idempotence:** a second run over the same data writes nothing.

## Acceptance

`--dry-run` on prod first, confirming the affected set matches the 7 + 3 above.
Then a real run. Then re-run `audit_adaptations2.py`: stale prose and stale
optional lines must both report **0**, with steps and required ingredients
still at 0.
