# Prompt-aware recipe grounding — design

**Date:** 2026-06-17
**Status:** Approved (pending spec review)
**Author:** Robert Soroka (with Claude)

## Problem

When `RECIPE_GROUNDING_ENABLED=true`, generated meal plans drift away from the
user's request. Diagnosed concretely on plan PK 83 / goal 111 (prod): the user's
free-text `prompt` had "little to nothing in common" with the recipes shown.

Root cause: the LLM path (`llm_service.generate_meal_plan_only`) reads the
user's `prompt` and generates prompt-aware meals. But `overlay_curated_recipes`
then **swaps those meals out** for curated recipes, and the selection logic
(`select_recipes_for_plan` → `eligible_recipes_for_slot` / `score_recipe`)
**never reads the prompt**. It gates only on `dietary_restrictions` (a few parsed
tags) + meal slot + catalog-mapped, then ranks by variety/difficulty/popularity/
calories. With a ~30-recipe corpus, every user gets roughly the same dishes
regardless of what they asked for.

## Goal

Make the grounding overlay prompt-aware: a curated recipe replaces the
(already prompt-aware) LLM meal **only when it genuinely fits the prompt**;
otherwise the LLM meal stays.

## Decisions (locked)

1. **Fallback** — when no curated recipe fits a slot, keep the LLM-generated
   (prompt-aware) meal. Prompt-fit is a *threshold to earn the overlay*, not a
   tie-breaker.
2. **Matching method** — one cheap LLM call per plan extracts structured facets
   from the free-text prompt; scoring/gating against recipe metadata is then
   deterministic and unit-testable.
3. **Strictness** — explicit prompt facets (cuisine, key ingredients) act as
   **hard gates**: a contradicting curated recipe is ineligible to overlay.
4. **Observability** — persist parsed facets + coverage on the plan.

## Architecture

New `prompt_facets` service feeds prompt-awareness into the existing grounding
overlay. Selection gains hard facet-gates + soft facet-scoring. No new infra
(no pgvector). The overlay's existing "uncovered slot keeps the generated meal"
behavior becomes the coherence fallback.

```
goal.prompt (decrypted)
  → extract_prompt_facets(...)            # LLM, once per plan
  → PromptFacets
  → select_recipes_for_plan(goal, facets) # gates + ranks curated pool
  → overlay swaps ONLY facet-eligible recipes
  → ineligible / uncovered slots keep the prompt-aware LLM meal
  → persist {facets, coverage} to DietaryPlan.grounding_debug
```

## Components

### 1. Facet extraction — new `diet_planner/services/prompt_facets.py`

- `PromptFacets` dataclass:
  - `cuisines: set[str]`
  - `wanted_ingredients: set[str]`
  - `avoided_ingredients: set[str]`
  - `styles: set[str]`
  - `emphases: set[str]`
  - All default to empty sets. An empty set means "no constraint from this facet."
- `extract_prompt_facets(prompt, *, language, cuisine_vocab) -> PromptFacets`:
  - One Gemini call, JSON-only response.
  - The system prompt is handed `cuisine_vocab` (the corpus's actual distinct
    cuisine values among published recipes) and instructed to map cuisines onto
    that vocabulary, returning `[]` when unsure. Ingredients returned as
    lowercased canonical-ish nouns (CZ/EN).
  - **Defensive:** empty prompt, timeout, or unparseable output →
    **empty `PromptFacets`** → no gates → today's exact behavior. Never raises;
    logged at warning.
  - Deterministic given the LLM's JSON; unit-tested with an injected fake client.
- `published_cuisine_vocab(pool=None) -> list[str]`: sorted distinct non-empty
  `cuisine` values from the published pool.

### 2. Gating + scoring — extend `diet_planner/services/recipe_retrieval.py`

- `recipe_matches_facets(recipe, facets) -> bool` — the hard gate. Only
  non-empty facet sets constrain:
  - `facets.cuisines` → `recipe.cuisine` must be non-empty **and** in the set.
    (A cuisine-less recipe fails when a cuisine is demanded — protects coherence.)
  - `facets.wanted_ingredients` → recipe must contain **≥1** wanted ingredient,
    matched on `ingredient.canonical` then `ingredient.name`, case-folded
    substring.
  - `facets.avoided_ingredients` → recipe must contain **none** of them.
- `eligible_recipes_for_slot(slot, required_tags, *, pool, status, exclude_ids,
  facets=None)`: after the existing hard gate (restrictions/slot/catalog-mapped),
  also require `recipe_matches_facets(r, facets)` when `facets` is provided.
- `score_recipe(recipe, *, used_recipe_ids, used_cuisines, target_calories,
  facets=None)`: add soft bonuses so the best-fitting *eligible* recipe wins:
  - +per extra `wanted_ingredients` match beyond the first.
  - + match of `facets.emphases` (e.g. `high_protein`, `low_carb`) against
    `recipe.dietary_tags`.
  - + light bonus for `facets.styles` hints (e.g. quick → low `total_time`).
  - Exact weights tuned in implementation; all additive, none override the
    existing variety/difficulty/popularity terms.

### 3. Wiring

- `select_recipes_for_plan(goal, *, status, facets=None)` threads `facets` into
  `eligible_recipes_for_slot` and `score_recipe`.
- `overlay_curated_recipes(transformed_days, goal, *, status, facets=None)`:
  when `facets is None`, extract once from `goal.prompt` via
  `extract_prompt_facets` (decrypted on read). Computes facets a single time per
  plan, not per slot/day.
- The two call sites in `tasks.py` (~1581 and ~2193) stay unchanged — overlay
  extracts internally.

### 4. Observability — `DietaryPlan.grounding_debug`

- New nullable `JSONField` on `DietaryPlan`: `{facets: {...}, coverage: {filled,
  total}}`, written by `overlay_curated_recipes` (returned alongside the existing
  result and persisted by the task, mirroring how coverage is already handled).
- One auto-applied migration.
- Makes "why did this recipe show / why was this slot generated" answerable
  without re-running generation — the exact gap hit while diagnosing plan 111.

## Error handling

- Facet extraction failure/timeout → empty facets → overlay behaves as today
  (no regression, no crash). Logged.
- Grounding disabled / no published recipes → unchanged.
- Hard gates emptying the eligible pool for a slot → slot stays generated
  (the desired fallback).

## Testing

Unit tests (no live LLM; inject a fake extractor/client):

- `recipe_matches_facets` truth table: cuisine in / out / missing-when-demanded;
  wanted-ingredient hit / miss; avoided-ingredient hit; empty facets = no
  constraint.
- `score_recipe` with facets: ordering favors more wanted-ingredient hits and
  emphasis/dietary_tag matches.
- `select_recipes_for_plan` with facets: off-cuisine recipes never selected;
  on-cuisine selected; sparse corpus → slots left uncovered.
- `overlay_curated_recipes`: keeps the generated meal when no facet-eligible
  recipe; swaps when eligible; preserves `meal_identifier` and `source` flags;
  writes `grounding_debug`.
- `extract_prompt_facets`: parses JSON, maps onto `cuisine_vocab`, returns empty
  facets on garbage/empty/exception.
- Regression: existing `test_recipe_retrieval` suite stays green (facets default
  `None` → no behavior change).

## Out of scope (YAGNI)

- pgvector / embedding retrieval.
- Per-candidate LLM scoring.
- Corpus expansion (separate track — `docs/recipe-corpus-scaling.md`).
- Additional threshold knobs beyond the hard gates.

## Notes

- `cuisine` is a free-text `CharField`, not an enum — hence vocabulary
  normalization at extraction time against the live corpus.
- `dietary_tags` already carries `high_protein` / `low_carb`, reused for the
  `emphases` soft signal.
- The prompt is an `EncryptedTextField`; it decrypts transparently on read, so
  extraction sees plaintext while storage stays encrypted at rest. (Related:
  the prompt is now also surfaced to the user on the plan page.)
