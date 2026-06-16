# Dietary Restriction Enforcement & Shopping-List Parity — Design

**Date:** 2026-06-13
**Trigger:** Plan #110 was prompted as gluten-free; the first recipe contained
flour, yet flour did not appear in the shopping list. Two distinct bugs
exposed by one report.
**Scope:** `diet_planner/` only. Both LLM generation paths
(`process_dietary_goal_catalog_task` and `process_dietary_goal_task`).
**Non-goals:** Migrating the legacy path to `PriceResolver` (separate ticket);
solving Czech morphology beyond stem matching; building a general allergen NLU.

---

## 1. Root Causes (verified)

### 1a. Allergen leak

The user's "gluten free" reaches Gemini only as raw text inside
`user_prompt`. The two LLM entry points relevant here have no allergen
guardrail in their system prompts:

- `diet_planner/llm_service.py:350-399` — `generate_meal_plan_only` system
  prompt has only leftover-reuse rules.
- `diet_planner/llm_service.py:1442-1574` — `generate_catalog_constrained_plan`
  likewise has no explicit restriction rule.

A real exclusion vocabulary exists (`DIETARY_EXCLUSIONS` in
`diet_planner/services/catalog.py:59`, including the entries `mouka`,
`těstovin`, `chléb`, `pečivo`, `rohlík`, `houska`, `flour`, `pasta`, `bread`,
`roll`, `wheat`, `pšenič` for `gluten_free`), but it is only consulted by
`CatalogService._filter_by_dietary_restrictions`
(`diet_planner/services/catalog.py:253-279`), which reads the structured
`goal.dietary_restrictions` field — **never** `goal.prompt`.
A separate keyword map at `diet_planner/services/recipe_retrieval.py:43-52`
does parse freeform text into tags, but it is only used by recipe retrieval,
not by the generation pipeline.

Consequence: with `CATALOG_CONSTRAINED_GENERATION = True`
(`llm_diet_planner_project/settings.py:291`, the default), a user who types
"gluten free" into the prompt without populating `dietary_restrictions` gets
an unfiltered catalog and an unguarded LLM. Flour can land in any recipe.

### 1b. Shopping-list parity

The legacy path (`process_dietary_goal_task`, `tasks.py:1449-1493`) generates
the shopping list with a second Gemini call. That call is fed a
**truncated** summary of the meal plan:

```python
# diet_planner/llm_service.py:477
days_summary = json_module.dumps(meal_plan_days, ensure_ascii=False)[:5000]
```

Output is whatever Gemini returns in `shopping_list`. A deterministic
aggregator `aggregate_ingredients_from_meals` exists at `tasks.py:420` but
is only called on the catalog path (`tasks.py:2116`). Ingredients can,
and do, fall out of the shopping list while still appearing in recipes.

### 1c. Which path did plan #110 use?

Likely the catalog path (`CATALOG_CONSTRAINED_GENERATION` defaults to True).
The catalog path's allergen handling is broken in mode 1a above. The legacy
path remains reachable via the sparse-catalog fallback at
`tasks.py:2076-2081`, which routes to `process_dietary_goal_task` when the
catalog has fewer than ten products. Both paths therefore need the fix.

---

## 2. Architecture

One new module, one prompt refactor, one task refactor — applied uniformly
to both pipelines.

```
diet_planner/services/
  ├── restrictions.py        NEW   resolver + validator + repair + swap map
  ├── catalog.py             EDIT  CatalogService consumes resolved exclusions
  └── recipe_retrieval.py    EDIT  _DIETARY_KEYWORDS moved into restrictions.py
                                   and re-exported (or imported) to keep one map

diet_planner/llm_service.py  EDIT
  ├── _build_meal_system_prompt(goal, exclusions, single_meal=False)  NEW helper
  ├── generate_meal_plan_only(..., exclusions)                        EDIT
  ├── generate_catalog_constrained_plan(..., exclusions)              EDIT
  ├── generate_shopping_list_with_prices(aggregated_items, ...)       EDIT (signature)
  └── regenerate_meal(meal, goal, exclusions)                         NEW

diet_planner/tasks.py        EDIT
  ├── process_dietary_goal_task()             reorder to 1→2→3→4→5
  └── process_dietary_goal_catalog_task()     insert validator + repair phase
```

### 2.1 `restrictions.py`

Single source of truth for everything restriction-related. Public surface:

```python
@dataclass(frozen=True)
class ResolvedRestrictions:
    tags: frozenset[str]            # e.g. {'gluten_free', 'vegan'}
    exclusion_keywords: frozenset[str]   # union of DIETARY_EXCLUSIONS[tag]
                                         # plus parsed freeform allergens
    freeform_allergens: frozenset[str]   # e.g. {'peanut', 'sesame'}

class RestrictionResolver:
    def resolve(self, goal: DietaryGoal) -> ResolvedRestrictions: ...
    @staticmethod
    def parse_freeform(text: str) -> tuple[frozenset[str], frozenset[str]]:
        """Returns (tag_set, allergen_set) parsed from freeform Czech/English."""

@dataclass(frozen=True)
class Violation:
    meal_key: str           # 'day_2.lunch', 'day_3.snacks[1]'
    matched_keyword: str    # 'mouka'
    matched_in: str         # 'ingredients' | 'instructions'
    ingredient_name: str | None

def validate_meal_against_exclusions(
    meal: dict, exclusion_keywords: frozenset[str]
) -> list[Violation]: ...

def try_deterministic_swap(
    violation: Violation, exclusions: ResolvedRestrictions
) -> dict | None:
    """Returns a patched meal if a clean 1:1 swap applies, else None."""
```

The deterministic swap map is a module-level constant inside
`restrictions.py`. Initial entries:

```python
DETERMINISTIC_SWAPS = {
    'gluten_free': {
        'mouka':       'bezlepková mouka',
        'těstoviny':   'bezlepkové těstoviny',
        'chléb':       'bezlepkový chléb',
        'rohlík':      'bezlepkový rohlík',
        'houska':      'bezlepková houska',
        'pasta':       'gluten-free pasta',
        'bread':       'gluten-free bread',
        'flour':       'gluten-free flour',
    },
    'lactose_free': {
        'mléko':       'bezlaktózové mléko',
        'smetana':     'bezlaktózová smetana',
        'jogurt':      'bezlaktózový jogurt',
        'milk':        'lactose-free milk',
        'cream':       'lactose-free cream',
        'yogurt':      'lactose-free yogurt',
    },
    # vegan / vegetarian: no clean 1:1 swap (chicken → ??). Always re-prompt.
}
```

The freeform-allergen parser uses a **fixed vocabulary** (nuts, peanuts,
soy, sesame, eggs, shellfish, fish). It recognises phrasings such as
`alergie na <X>`, `bez <X>`, `allergic to <X>`, `<X>-free`. Anything outside
the vocabulary is ignored. This is explicitly not a general NLU.

### 2.2 LLM service changes

`generate_meal_plan_only` and `generate_catalog_constrained_plan` share
a new helper `_build_meal_system_prompt(goal, exclusions, single_meal=False)`
that interpolates a hard-rule block when `exclusions.exclusion_keywords` is
non-empty:

```
DIETARY RESTRICTIONS (non-negotiable):
- The user requires: gluten_free, vegan.
- The user has reported allergies to: peanut, sesame.
- The following ingredient keywords are FORBIDDEN in ingredients[] AND
  instructions[] for ALL meals: mouka, těstoviny, chléb, ... (full list).
- If a traditional recipe would require a forbidden ingredient, substitute
  a compliant alternative (e.g. bezlepková mouka instead of mouka).
- Violations will cause the meal to be rejected.
```

`regenerate_meal(meal, goal, exclusions)` is a new method that reuses the
same system-prompt helper with `single_meal=True`. It returns a single
meal dict matching the original schema.

`generate_shopping_list_with_prices` is renamed in spirit (signature
changes; name preserved for callers): it now takes the *aggregated* list
produced by `aggregate_ingredients_from_meals`, not raw days. The
`days_summary[:5000]` truncation is removed. Gemini's job becomes pure
price/product matching over a list it cannot shorten.

### 2.3 Task changes — both paths

`process_dietary_goal_catalog_task`:

```
1. resolver.resolve(goal) → exclusions
2. CatalogService.build_catalog_for_prompt(goal, exclusions=exclusions)
3. generate_catalog_constrained_plan(user_prompt, catalog_text, goal,
                                     exclusions=exclusions)
4. validator + repair loop (see §3)
5. existing Phase 3 (aggregate) and Phase 4 (PriceResolver) unchanged
```

`process_dietary_goal_task` (legacy / sparse-catalog fallback):

```
1. resolver.resolve(goal) → exclusions
2. generate_meal_plan_only(user_prompt, shop_url, goal,
                           exclusions=exclusions)
3. validator + repair loop (see §3)
4. aggregate_ingredients_from_meals(days)        ← NEW on this path
5. generate_shopping_list_with_prices(aggregated_list, shop_url, goal)
6. validate_shopping_item, persist
```

`CatalogService.build_catalog_for_prompt` gains an `exclusions` kwarg.
`_filter_by_dietary_restrictions` is replaced with a routine that consumes
`exclusions.exclusion_keywords` directly. The old code path (reading
`goal.dietary_restrictions`) is removed — the resolver now owns that field
too.

---

## 3. Validator and Repair Loop

Termination contract:

- Each meal may be re-prompted **at most twice**.
- After two re-prompts, if a deterministic 1:1 swap exists in
  `DETERMINISTIC_SWAPS[tag]` for every remaining violation, apply it and
  proceed.
- Otherwise, set `DietaryGoal.status = FAILED` with
  `error_message = "Restriction violation in <meal_key>: <keyword> after N attempts"`
  and abort. The plan is not stored as a "completed-with-banner" plan.
  Rationale: serving a known-bad gluten-free plan to a celiac user is a
  medical/refund event; failing the generation lets the user retry.
- A per-plan re-prompt budget caps total surgical re-prompts at **6** to
  bound LLM cost if Gemini is misbehaving systemically. Exhausting the
  budget triggers the same `FAILED` outcome.

The validator scans both `ingredients[].name` and each `instructions[]`
line for case-folded substring matches against `exclusion_keywords`
(diacritics preserved — Czech relies on them). Same shape as
`_filter_by_dietary_restrictions` uses today, so behavior is consistent
with the rest of the codebase.

**Compliance-modifier suppression.** Naïve substring matching would
mis-flag the deterministic swap targets themselves: `"bezlepková mouka"`
contains the keyword `"mouka"`. The validator therefore keeps a per-tag
allowlist of compliance modifiers; when a forbidden keyword appears
within a token-window immediately preceded by such a modifier, the
match is suppressed.

```python
COMPLIANCE_MODIFIERS = {
    'gluten_free':  ['bezlepk', 'gluten-free', 'gluten free', 'gf '],
    'lactose_free': ['bezlaktóz', 'lactose-free', 'lactose free'],
    'dairy_free':   ['bez mlék', 'dairy-free', 'dairy free'],
    'vegan':        ['veganské', 'veganská', 'veganský', 'vegan'],
}
```

The suppression window is the same ingredient string (for
`ingredients[].name`) or the same sentence (for `instructions[]`).
Concretely: a forbidden keyword K with modifier prefix M_tag matches
iff `M_tag` is a substring of the string under inspection AND appears
before K within that string.

---

## 4. Data Flow Summary

```
┌──────────────────────────────────────────────────────────────┐
│ Common to both paths                                          │
│                                                               │
│   goal.prompt + goal.dietary_restrictions                     │
│              │                                                │
│              ▼                                                │
│   RestrictionResolver.resolve(goal)                           │
│              │                                                │
│              ▼                                                │
│   ResolvedRestrictions(tags, exclusion_keywords, allergens)   │
└──────────────────────────────────────────────────────────────┘
              │                              │
              ▼                              ▼
   ┌──────────────────────┐       ┌──────────────────────┐
   │ Catalog path         │       │ Legacy path          │
   │                      │       │                      │
   │ CatalogService       │       │ generate_meal_plan_  │
   │  (filters catalog)   │       │  only(exclusions)    │
   │      │               │       │      │               │
   │      ▼               │       │      ▼               │
   │ generate_catalog_    │       │ days[]               │
   │  constrained_plan(   │       │      │               │
   │  exclusions)         │       │      ▼               │
   │      │               │       │ validate + repair    │
   │      ▼               │       │      │               │
   │ days[]               │       │      ▼               │
   │      │               │       │ aggregate_           │
   │      ▼               │       │  ingredients_from_   │
   │ validate + repair    │       │  meals(days)         │
   │      │               │       │      │               │
   │      ▼               │       │      ▼               │
   │ aggregate (existing) │       │ generate_shopping_   │
   │      │               │       │  list_with_prices(   │
   │      ▼               │       │  aggregated_list)    │
   │ PriceResolver        │       │      │               │
   │  (existing)          │       │      ▼               │
   │      │               │       │ persist              │
   │      ▼               │       │                      │
   │ persist              │       │                      │
   └──────────────────────┘       └──────────────────────┘
```

---

## 5. Testing Plan

Pure unit tests (no DB) for `restrictions.py`:

- `parse_freeform` recognises Czech and English phrasings for each tag and
  each allergen in the fixed vocabulary; ignores unknown words.
- `resolve` merges `goal.dietary_restrictions` (keyword scan) and
  `goal.prompt` (keyword + freeform); deduplicates.
- `validate_meal_against_exclusions` flags ingredients and instructions;
  returns empty for compliant meals.
- `try_deterministic_swap` produces a compliant meal for mapped cases;
  returns None for unmapped (vegan + chicken) and for tags with no map.
- **Anti-rot test:** for every (tag, source, target) in
  `DETERMINISTIC_SWAPS`, run `validate_meal_against_exclusions` over a
  synthetic meal whose only ingredient is `target` with the resolved
  exclusions for `{tag}`, and assert zero violations. This catches both
  "we swapped flour → wheat flour" AND "we forgot the compliance
  modifier in the suppression list," because both regressions surface
  as a non-empty violation list.

LLM-service tests (mocked Gemini):

- System prompt assembled by `_build_meal_system_prompt` contains the
  exclusion list verbatim when restrictions are present, and omits the
  block entirely when not.
- `regenerate_meal` returns a single meal in the expected schema.
- `generate_shopping_list_with_prices` is called with the aggregated list
  shape, not a truncated days summary.

Task-level tests (with mocked `GeminiService`):

- Catalog path: violation in generated meal → one re-prompt → compliant
  meal → success.
- Catalog path: persistent violation after 2 re-prompts → unmapped →
  plan is `FAILED` with descriptive error.
- Legacy path: aggregator is called; shopping list contains every
  ingredient present in `transformed_days`.
- Per-plan budget exhaustion (6 re-prompts) → plan `FAILED`.

Regression / integration:

- Reproduce plan #110 conditions (prompt = "bezlepkový týden",
  `dietary_restrictions = ''`) with a stubbed Gemini that initially
  returns flour; assert the final plan contains no `gluten_free`
  exclusion keyword in any recipe and the shopping list matches the
  recipe ingredient set 1:1.

---

## 6. Open Questions / Trade-offs Recorded

- **Stem matching vs. whole-word matching.** The existing
  `_filter_by_dietary_restrictions` does case-folded substring matching
  on product names. We mirror this for consistency and add the
  compliance-modifier suppression rule (§3) to prevent false positives
  on legitimately compliant variants. Future iteration can add proper
  Czech stemming if real-world false positives emerge. Logged as a
  known limitation, not a blocker.
- **Catalog path now serves single source.** `CatalogService` no longer
  reads `goal.dietary_restrictions` directly — only the resolver does.
  This eliminates the divergence between catalog filtering and the new
  validator, at the cost of `CatalogService` requiring an `exclusions`
  kwarg from every caller. Existing callers updated in this PR; no public
  API breakage expected.
- **Legacy path keeps an LLM pricing call.** Per user decision (Approach
  2), we did not move the legacy path to `PriceResolver` here. The
  aggregated list is now the contract handed to Gemini, so parity is
  guaranteed even though prices remain LLM-sourced. Migrating legacy to
  `PriceResolver` is a separate ticket.
- **Re-prompt budget = 6.** Chosen as ~one re-prompt per day for a 7-day
  plan. Tunable via settings if production data shows it's too tight or
  too loose.

---

## 7. Out of Scope (Explicit Non-Goals)

- LLM-fabricated prices on the legacy path. Tracked separately.
- Cross-store optimization changes. Existing `CrossStoreOptimizer` is
  unaffected; it operates on the aggregated list, which is already the
  contract.
- Curated recipe corpus changes. Recipe grounding overlay
  (`overlay_curated_recipes`) runs before the validator on the catalog
  path and produces meals already known to be compliant for their tagged
  restrictions; the validator double-checks but does not modify the
  curation pipeline.
- UI changes for the new `FAILED` outcome. The existing failure UI is
  reused with the new `error_message` shape.
