# Remove Whole-Plan Shopping List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the whole-plan shopping list (items, plan-level price estimate, pantry toggles, price feedback) entirely, and rip out the now-dead supporting code, leaving shopping/pricing to live only at the per-recipe level.

**Architecture:** The whole-plan shopping list is produced by two backend generation paths (legacy LLM path + catalog-constrained path), exposed via `DietaryPlanSerializer`, and rendered in `PlanView.tsx` + `ShoppingListPage.tsx`. We stop generating/storing it, strip it from the API and model, and delete the frontend surfaces. Shared pricing primitives used by the **per-recipe** engine (`recipe_pricing`, `recipe_deals`, `pricing_core`, the price book, and helpers `classify_pantry_level`/`item_is_excluded`, `_FX_FROM_CZK`/`_load_book`) are preserved.

**Tech Stack:** Django 5.1 / DRF, Celery tasks, React 18 + TypeScript + Vite, pytest (Django test runner), Vitest (frontend if present).

---

## Scope Boundary (read before starting)

**REMOVE (whole-plan-specific):**
- Backend generation: shopping-list build in `process_dietary_goal_task` (Path A) and Phases 3–4 in the catalog-constrained task (Path B).
- LLM methods: `generate_complete_plan_with_shopping_list`, `generate_shopping_list_with_prices`.
- Aggregation: `aggregate_ingredients_from_meals`, `_aggregate_meal_ingredients`, `_build_catalog_id_map`, `_log_item_details`.
- Whole-plan pricing helpers: `validate_shopping_item`, `convert_requirement_to_purchasable_units`, `calculate_package_aware_price`.
- `EstimatePricer` class + `.price()`; `compute_pricing` + `resolve_store_products` in `shopping_list_pricing.py`.
- Management command: `recompute_plan_prices`.
- Serializer fields: `shopping_list`, `pricing`, `total_price`, `pantry_price`, `pantry_basics_on`, `pantry_fridge_on`.
- Model fields: `shopping_list`, `total_price`, `pantry_price`, `pantry_basics_on`, `pantry_fridge_on` (+ migration).
- Views: pantry-toggle `PATCH` on the goal detail; `PriceFeedbackView` endpoint + URL.
- Validator: shopping-list price-coverage / total-price checks in `MealPlanValidator`.
- Frontend: shopping-list sidebar + estimate UI in `PlanView.tsx`; `ShoppingListPage.tsx` + its route; `lib/pricing.ts` whole-plan types; pantry-toggle & price-feedback API calls in `lib/api.ts`.

**KEEP (shared with per-recipe engine — do NOT touch):**
- `diet_planner/services/recipe_pricing.py`, `recipe_deals.py`, `pricing_core.py`, `canonical_lookup.py`, `piece_weights.py`.
- `diet_planner/services/estimate_pricer.py` module-level `_FX_FROM_CZK` and `_load_book` (and any private helpers they call) — only the `EstimatePricer` *class* is removed.
- `diet_planner/services/shopping_list_pricing.py` functions `classify_pantry_level`, `item_is_excluded`.
- The price book YAML + `build_price_book` command.
- `RecipeSerializer.price_range` / `.deals`, `RecipePage.tsx`.
- Recipe grounding overlay (`overlay_curated_recipes`) and `_assert_plan_has_content`.

---

## Task 1: Establish a regression baseline

**Files:**
- Test: run existing suite

- [ ] **Step 1: Run the full backend test suite to capture the current green/red baseline**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner -v1 2>&1 | tail -30`
Expected: Note which tests pass now. Many shopping-list tests will be intentionally removed/changed later; record the starting state so we can distinguish pre-existing failures from regressions.

- [ ] **Step 2: Identify plan/116's generation path (which task produced its list)**

Run: `cd /opt/llmDietPlanner && grep -n "def process_dietary_goal_task\|def process_dietary_goal_with_catalog\|generate_catalog_constrained_plan\|generate_complete_plan_with_shopping_list" diet_planner/tasks.py`
Expected: Confirms the two task entry points and their line ranges so later edits target the right functions. No code change.

---

## Task 2 (TDD): Serializer no longer exposes whole-plan shopping list or pricing

**Files:**
- Modify: `diet_planner/serializers.py` (`DietaryPlanSerializer`, ~74–161)
- Test: `diet_planner/tests/test_plan_serializer_no_shopping_list.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_plan_serializer_no_shopping_list.py
"""The plan serializer must not expose any whole-plan shopping list or
plan-level pricing. Shopping/pricing live only at the per-recipe level now."""
from django.test import TestCase

from diet_planner.models import DietaryGoal, DietaryPlan
from diet_planner.serializers import DietaryPlanSerializer


class PlanSerializerOmitsShoppingList(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create(username="u1")
        self.goal = DietaryGoal.objects.create(
            user=user, prompt="x", num_days=3, country="CZ", currency="CZK",
        )
        self.plan = DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{"day_number": 1, "breakfast": {"name": "Eggs", "ingredients": []}}],
            currency="CZK",
        )

    def test_serializer_drops_whole_plan_fields(self):
        data = DietaryPlanSerializer(self.plan).data
        for gone in (
            "shopping_list", "pricing", "total_price", "pantry_price",
            "pantry_basics_on", "pantry_fridge_on",
        ):
            self.assertNotIn(gone, data, f"{gone} should no longer be serialized")

    def test_serializer_keeps_days(self):
        data = DietaryPlanSerializer(self.plan).data
        self.assertIn("days", data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_plan_serializer_no_shopping_list -v2`
Expected: FAIL — `shopping_list`/`pricing`/etc. are still present.

- [ ] **Step 3: Edit `DietaryPlanSerializer`**

In `diet_planner/serializers.py`:
- Delete the field declarations `shopping_list = serializers.SerializerMethodField()` and `pricing = serializers.SerializerMethodField()`.
- Delete the methods `get_shopping_list` and `get_pricing`.
- Remove `'shopping_list'`, `'pricing'`, `'total_price'`, `'pantry_price'`, `'pantry_basics_on'`, `'pantry_fridge_on'` from both `fields` and `read_only_fields`.
- Keep `days`, `llm_usage`, `currency`, `created_at`, `updated_at`, `id`.

Resulting `Meta.fields` (and `read_only_fields`):
```python
fields = [
    'id',
    'days',
    'currency',
    'llm_usage',
    'created_at',
    'updated_at',
]
read_only_fields = [
    'id',
    'days',
    'currency',
    'llm_usage',
    'created_at',
    'updated_at',
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_plan_serializer_no_shopping_list -v2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/serializers.py diet_planner/tests/test_plan_serializer_no_shopping_list.py
git commit -m "feat(plan): drop whole-plan shopping_list + pricing from serializer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3 (TDD): Catalog-constrained task stops building & storing the shopping list (Path B)

This is the prod-default path. After grounding + `_assert_plan_has_content`, it currently runs Phase 3 (aggregate) and Phase 4 (EstimatePricer) and stores `shopping_list`/`total_price`. We remove Phases 3–4 and store an empty plan-pricing-free `DietaryPlan`.

**Files:**
- Modify: `diet_planner/tasks.py` (catalog task, Phases 3–4 around 2218–2280 and the `DietaryPlan.objects.create(...)` for that path)
- Test: `diet_planner/tests/test_catalog_no_shopping_list.py` (create)

- [ ] **Step 1: Read the exact current Phase 3/4 + create block**

Run: `cd /opt/llmDietPlanner && sed -n '2210,2300p' diet_planner/tasks.py`
Expected: See Phases 3–4 and the `DietaryPlan.objects.create(...)` call for this task. Note the exact lines and which kwargs are passed.

- [ ] **Step 2: Write the failing test**

```python
# diet_planner/tests/test_catalog_no_shopping_list.py
"""The catalog-constrained generation path must not build or store a
whole-plan shopping list anymore."""
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model

from diet_planner.models import DietaryGoal, DietaryPlan


FAKE_DAYS = [
    {"day_number": 1,
     "breakfast": {"name": "Eggs", "ingredients": [{"name": "eggs", "quantity": 2, "unit": "ks"}]}},
]


class CatalogPathOmitsShoppingList(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username="catuser")
        self.goal = DietaryGoal.objects.create(
            user=user, prompt="x", num_days=1, country="CZ", currency="CZK",
        )

    @patch("diet_planner.tasks.transform_days_to_new_format", side_effect=lambda d, g: d)
    @patch("diet_planner.tasks._assert_plan_has_content")
    @patch("diet_planner.services.recipe_retrieval.grounding_enabled", return_value=False)
    @patch("diet_planner.tasks.GeminiService")
    @patch("diet_planner.services.catalog.CatalogService")
    def test_no_shopping_list_stored(self, m_catalog_cls, m_gem, *_):
        # Minimal catalog stub so the task reaches generation.
        cat = m_catalog_cls.return_value
        cat.build_catalog_for_prompt.return_value = {"total_products": 50, "pantry_staples": []}
        cat.build_compact_prompt_text.return_value = "catalog text"
        inst = m_gem.return_value
        inst.generate_catalog_constrained_plan.return_value = {
            "response": {"days": FAKE_DAYS},
            "model": "x", "input_tokens": 1, "output_tokens": 1,
            "total_tokens": 2, "cost_usd": 0.0,
        }
        from diet_planner.tasks import process_dietary_goal_catalog_task
        # Bound Celery task — invoke the underlying function via .run().
        process_dietary_goal_catalog_task.run(self.goal.id)

        plan = DietaryPlan.objects.get(dietary_goal=self.goal)
        self.assertEqual(plan.days, FAKE_DAYS)
        # shopping_list field is being removed in a later task; until then it must be empty.
        self.assertIn(getattr(plan, "shopping_list", []), ([], None))
```
> NOTE: `_resolve_exclusions` (or equivalent) runs before catalog build in this task — if the real code calls additional collaborators before generation, add `@patch` for them until the task runs through to `DietaryPlan.objects.create`. The assertion (no shopping list stored) is the contract.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_catalog_no_shopping_list -v2`
Expected: FAIL — either Phase 3/4 still populate `shopping_list`, or the create still passes pricing kwargs.

- [ ] **Step 4: Edit the catalog task**

In the catalog-constrained task in `diet_planner/tasks.py`:
- Delete Phase 3 (the `aggregate_ingredients_from_meals(...)` call, the `_build_catalog_id_map` loop, and the `validate_shopping_item` loop).
- Delete Phase 4 (the `EstimatePricer(goal).price(...)` block and any `total_price`/`pantry_price` computation).
- Change the `DietaryPlan.objects.create(...)` for this path to pass only: `dietary_goal`, `days=transformed_days`, `currency=goal.currency`, the `llm_*` token/cost kwargs, and `grounding_debug`. Remove `shopping_list=`, `total_price=`, `pantry_price=` kwargs.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_catalog_no_shopping_list -v2`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/tasks.py diet_planner/tests/test_catalog_no_shopping_list.py
git commit -m "feat(plan): catalog path stops building whole-plan shopping list

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 (TDD): Legacy task uses meal-plan-only generation, no shopping list (Path A)

**Files:**
- Modify: `diet_planner/tasks.py` `process_dietary_goal_task` (~1540–1800)
- Test: `diet_planner/tests/test_legacy_no_shopping_list.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_legacy_no_shopping_list.py
"""Legacy generation path must call meal-plan-only generation and store no
whole-plan shopping list."""
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model

from diet_planner.models import DietaryGoal, DietaryPlan

FAKE_DAYS = [
    {"day_number": 1,
     "breakfast": {"name": "Eggs", "ingredients": [{"name": "eggs", "quantity": 2, "unit": "ks"}]}},
]


class LegacyPathOmitsShoppingList(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username="leguser")
        self.goal = DietaryGoal.objects.create(
            user=user, prompt="x", num_days=1, country="CZ", currency="CZK",
        )

    @patch("diet_planner.tasks.transform_days_to_new_format", side_effect=lambda d, g: d)
    @patch("diet_planner.tasks._assert_plan_has_content")
    @patch("diet_planner.services.recipe_retrieval.grounding_enabled", return_value=False)
    @patch("diet_planner.tasks.GeminiService")
    def test_meal_plan_only_and_no_shopping_list(self, m_gem, *_):
        inst = m_gem.return_value
        inst.generate_meal_plan_only.return_value = {
            "response": {"days": FAKE_DAYS},
            "model": "x", "input_tokens": 1, "output_tokens": 1,
            "total_tokens": 2, "cost_usd": 0.0,
        }
        from diet_planner.tasks import process_dietary_goal_task
        # Bound Celery task — invoke the underlying function via .run().
        process_dietary_goal_task.run(self.goal.id)

        inst.generate_meal_plan_only.assert_called_once()
        self.assertFalse(hasattr(inst.generate_complete_plan_with_shopping_list, "called")
                         and inst.generate_complete_plan_with_shopping_list.called)
        plan = DietaryPlan.objects.get(dietary_goal=self.goal)
        self.assertEqual(plan.days, FAKE_DAYS)
        self.assertIn(getattr(plan, "shopping_list", []), ([], None))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_legacy_no_shopping_list -v2`
Expected: FAIL — task still calls `generate_complete_plan_with_shopping_list` and stores a list.

- [ ] **Step 3: Edit `process_dietary_goal_task`**

In `diet_planner/tasks.py`:
- Replace the `llm_service.generate_complete_plan_with_shopping_list(...)` call (~1566) with `llm_service.generate_meal_plan_only(user_prompt, shop_url, goal)`.
- After it, set `days = llm_result['response'].get('days', [])`. Delete the `shopping_list_from_llm` / `total_cost_from_llm` extraction.
- Delete the entire shopping-list validation/pricing loop (`for item in shopping_list_from_llm: ...`, ~1604–1722) and the `final_total`/`calculated_total` block (~1724–1736).
- In the coherence-validation call (~1750), pass an empty list for the shopping list argument (the validator is updated in Task 7).
- Change `DietaryPlan.objects.create(...)` (~1777) to pass only `dietary_goal`, `days=transformed_days`, `currency=goal.currency`, `llm_*` kwargs from `llm_result`, and `grounding_debug`. Remove `shopping_list=`, `total_price=`, `pantry_price=`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_legacy_no_shopping_list -v2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/tasks.py diet_planner/tests/test_legacy_no_shopping_list.py
git commit -m "feat(plan): legacy path uses meal-plan-only, no shopping list

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Remove pantry-toggle PATCH and PriceFeedback endpoint

**Files:**
- Modify: `diet_planner/views.py` (PATCH on goal-detail view ~245–273; `PriceFeedbackView` ~600–670)
- Modify: `diet_planner/urls.py` (price-feedback route)
- Test: `diet_planner/tests/test_removed_endpoints.py` (create)

- [ ] **Step 1: Locate the endpoints**

Run: `cd /opt/llmDietPlanner && grep -n "PriceFeedbackView\|price-feedback\|def patch" diet_planner/views.py diet_planner/urls.py`
Expected: Shows the view class, its URL, and the `patch` method.

- [ ] **Step 2: Write the failing test**

```python
# diet_planner/tests/test_removed_endpoints.py
"""Pantry-toggle PATCH and price-feedback endpoints are removed."""
from django.test import TestCase
from django.urls import NoReverseMatch, reverse


class RemovedEndpoints(TestCase):
    def test_price_feedback_route_gone(self):
        with self.assertRaises(NoReverseMatch):
            reverse("goal-price-feedback")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_removed_endpoints -v2`
Expected: FAIL — route still resolves.

- [ ] **Step 4: Remove the code**

- In `diet_planner/views.py`: delete the `patch` method on the goal-detail view (the pantry-toggle handler) and delete the `PriceFeedbackView` class.
- In `diet_planner/urls.py`: delete the `path(... PriceFeedbackView ...)` entry and remove the now-unused import.
- Remove the `PriceFeedbackView` import from `views.py` consumers if any.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_removed_endpoints -v2`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/views.py diet_planner/urls.py diet_planner/tests/test_removed_endpoints.py
git commit -m "feat(plan): remove pantry-toggle PATCH and price-feedback endpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Rip out dead backend code (LLM methods, aggregation, whole-plan pricing)

No new behavior — pure deletion of code now unreachable. Guard with an import-smoke test so we prove the per-recipe engine still imports.

**Files:**
- Modify: `diet_planner/llm_service.py` (remove `generate_complete_plan_with_shopping_list` ~688–749, `generate_shopping_list_with_prices` ~598–687)
- Modify: `diet_planner/tasks.py` (remove `aggregate_ingredients_from_meals` ~486–598, `_aggregate_meal_ingredients` ~649–745, `_log_item_details` ~601–646, `validate_shopping_item` ~324–..., `convert_requirement_to_purchasable_units` ~1110–..., `calculate_package_aware_price` ~1267–..., `_build_catalog_id_map` ~2342–...; update the module docstring index at top of file)
- Modify: `diet_planner/services/shopping_list_pricing.py` (remove `compute_pricing` ~218–..., `resolve_store_products` if whole-plan-only; KEEP `classify_pantry_level`, `item_is_excluded`)
- Modify: `diet_planner/services/estimate_pricer.py` (remove the `EstimatePricer` class ~57–end; KEEP `_FX_FROM_CZK`, `_load_book`, and any private helpers they reference)
- Delete: `diet_planner/management/commands/recompute_plan_prices.py`
- Test: `diet_planner/tests/test_per_recipe_engine_intact.py` (create)

- [ ] **Step 1: Write the guard test (per-recipe engine still works)**

```python
# diet_planner/tests/test_per_recipe_engine_intact.py
"""After ripping out whole-plan code, the per-recipe pricing/deals engine and
the shared price-book helpers must still import and run."""
from django.test import TestCase


class PerRecipeEngineIntact(TestCase):
    def test_shared_helpers_import(self):
        from diet_planner.services.estimate_pricer import _FX_FROM_CZK, _load_book  # noqa
        from diet_planner.services.shopping_list_pricing import (  # noqa
            classify_pantry_level, item_is_excluded,
        )
        from diet_planner.services.recipe_pricing import price_recipe  # noqa
        from diet_planner.services.recipe_deals import recipe_deals  # noqa
        self.assertTrue(callable(_load_book))

    def test_price_recipe_runs(self):
        from diet_planner.services.recipe_pricing import price_recipe
        r = price_recipe([{"name": "eggs", "quantity": 2, "unit": "ks"}], servings=1, currency="CZK")
        self.assertIsNotNone(r)

    def test_whole_plan_symbols_gone(self):
        import diet_planner.tasks as t
        import diet_planner.llm_service as l
        for sym in ("aggregate_ingredients_from_meals", "validate_shopping_item",
                    "calculate_package_aware_price", "convert_requirement_to_purchasable_units"):
            self.assertFalse(hasattr(t, sym), f"{sym} should be removed from tasks")
        for sym in ("generate_complete_plan_with_shopping_list", "generate_shopping_list_with_prices"):
            self.assertFalse(hasattr(getattr(l, "GeminiService", object), sym),
                             f"{sym} should be removed from GeminiService")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_per_recipe_engine_intact -v2`
Expected: FAIL — `test_whole_plan_symbols_gone` fails because symbols still exist.

- [ ] **Step 3: Delete the dead code**

Delete each function/method/class/command listed in **Files** above. After each file, run `python -c "import ast; ast.parse(open('<file>').read())"` to confirm it still parses. Verify no remaining references with:

Run: `cd /opt/llmDietPlanner && grep -rn "aggregate_ingredients_from_meals\|generate_complete_plan_with_shopping_list\|generate_shopping_list_with_prices\|validate_shopping_item\|calculate_package_aware_price\|convert_requirement_to_purchasable_units\|_build_catalog_id_map\|compute_pricing\|EstimatePricer\|recompute_plan_prices" --include=*.py diet_planner --exclude-dir=tests`
Expected: No matches (all production references gone). If any remain, remove them.

- [ ] **Step 4: Run the guard test**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_per_recipe_engine_intact -v2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add -A
git commit -m "refactor(plan): rip out dead whole-plan shopping-list backend code

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Trim `MealPlanValidator` shopping-list checks

The validator runs over the plan + shopping list; with no shopping list, its price-coverage/total-price checks are meaningless and would emit false errors.

**Files:**
- Modify: `diet_planner/services/validation.py` (price-coverage + total-price block ~210–240)
- Test: `diet_planner/tests/test_validation_no_shopping.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_validation_no_shopping.py
"""Validator must not raise shopping-list price errors when given no list."""
from django.test import SimpleTestCase
from diet_planner.services.validation import MealPlanValidator


class ValidatorNoShopping(SimpleTestCase):
    def test_empty_shopping_list_no_price_errors(self):
        plan = {"days": [{"day_number": 1, "breakfast": {"name": "Eggs", "ingredients": []}}]}
        result = MealPlanValidator().validate(plan, [], {"num_days": 1, "language": "cs"})
        joined = " ".join(result.errors).lower()
        self.assertNotIn("price", joined)
        self.assertNotIn("items without prices", joined)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_validation_no_shopping -v2`
Expected: FAIL — validator emits low-total-price / no-price errors on the empty list.

- [ ] **Step 3: Edit `validation.py`**

Remove the `price_coverage_ratio`, `total_price`, expensive-item, and `MIN_PRICED_ITEMS_RATIO`/`MIN_TOTAL_PRICE`/`MAX_TOTAL_PRICE` checks that operate over `shopping_list`. Keep recipe-coherence checks. If `shopping_list` is now unused by the method, leave the parameter for signature stability but stop iterating it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner.tests.test_validation_no_shopping -v2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/services/validation.py diet_planner/tests/test_validation_no_shopping.py
git commit -m "refactor(validation): drop shopping-list price checks

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Remove model fields + migration

**Files:**
- Modify: `diet_planner/models/core.py` (`DietaryPlan`: remove `shopping_list`, `total_price`, `pantry_price`, `pantry_basics_on`, `pantry_fridge_on`)
- Modify: `diet_planner/admin.py` (remove `total_price` from `list_display`/fieldsets)
- Create: migration via `makemigrations`

- [ ] **Step 1: Remove admin references**

In `diet_planner/admin.py`: remove `'total_price'` from `list_display` (~89) and the `('total_price', 'currency')` fieldset (~102) → leave `('currency',)`.

- [ ] **Step 2: Remove the model fields**

In `diet_planner/models/core.py`: delete the `shopping_list`, `total_price`, `pantry_price`, `pantry_basics_on`, `pantry_fridge_on` field definitions on `DietaryPlan`.

- [ ] **Step 3: Generate the migration**

Run: `cd /opt/llmDietPlanner && python manage.py makemigrations diet_planner`
Expected: A new migration removing the five fields. Inspect it.

- [ ] **Step 4: Verify migration applies on a test DB**

Run: `cd /opt/llmDietPlanner && python manage.py migrate diet_planner --plan | tail -5 && python manage.py test diet_planner.tests.test_plan_serializer_no_shopping_list -v1`
Expected: Migration listed; serializer test still PASS.

- [ ] **Step 5: Confirm no remaining references**

Run: `cd /opt/llmDietPlanner && grep -rn "\.shopping_list\b\|\.total_price\b\|\.pantry_price\b\|pantry_basics_on\|pantry_fridge_on" --include=*.py diet_planner --exclude-dir=tests --exclude-dir=migrations`
Expected: No matches. Fix any stragglers (e.g. `cross_store_optimizer.py` uses a local dict key `'total_price'` — that is NOT the model field; leave it).

- [ ] **Step 6: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/models/core.py diet_planner/admin.py diet_planner/migrations/
git commit -m "feat(plan): drop whole-plan shopping_list + pricing model fields

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Frontend — remove shopping-list UI, page, route, and API calls

**Files:**
- Modify: `frontend/src/pages/PlanView.tsx` (remove shopping-list sidebar ~369–438, estimate UI, "View full list" button; make meal column full width)
- Delete: `frontend/src/pages/ShoppingListPage.tsx`
- Modify: `frontend/src/App.tsx` (remove `ShoppingListPage` import ~9 and `/plan/:id/shopping-list` route ~87)
- Modify: `frontend/src/lib/api.ts` (remove pantry-toggle + price-feedback calls)
- Modify: `frontend/src/lib/pricing.ts` (remove whole-plan `ShoppingListItem`/`PriceEstimate`/`DealItem` types if unused elsewhere; KEEP anything `RecipePage.tsx` imports)

- [ ] **Step 1: Find all frontend usages**

Run: `cd /opt/llmDietPlanner && grep -rn "shopping_list\|shopping-list\|ShoppingListPage\|pantry_basics_on\|pantry_fridge_on\|price-feedback\|priceFeedback\|/pricing\b\|plan\.pricing\|\.total_price" frontend/src`
Expected: Inventory of references. `lib/pricing.ts` may be shared with `RecipePage.tsx`/`PublicRecipePage.tsx` — keep the per-recipe types (`price_range`, recipe `deals`).

- [ ] **Step 2: Edit `PlanView.tsx`**

Remove the `<aside>` shopping-list block and the estimate/price summary. Change the surrounding grid so the meal-plan content spans full width (e.g. drop `lg:col-span-8` / `lg:col-span-4` split → single column). Remove the "View full list" / `navigate('/plan/:id/shopping-list')` button and any `plan.shopping_list` / `plan.pricing` references.

- [ ] **Step 3: Delete `ShoppingListPage.tsx` and its route**

```bash
cd /opt/llmDietPlanner && rm frontend/src/pages/ShoppingListPage.tsx
```
In `App.tsx`: remove the import line and the `<Route path="/plan/:id/shopping-list" ... />`.

- [ ] **Step 4: Clean `lib/api.ts` and `lib/pricing.ts`**

Remove the pantry-toggle PATCH helper and the price-feedback POST helper from `api.ts`. In `pricing.ts`, delete the whole-plan `ShoppingListItem`/`PriceEstimate`/`PriceSource` exports IF `grep` in Step 1 shows no remaining importers; otherwise leave the ones still used by recipe pages.

- [ ] **Step 5: Typecheck + build**

Run: `cd /opt/llmDietPlanner/frontend && npm run build 2>&1 | tail -30`
Expected: Build succeeds with no TypeScript errors about missing `shopping_list`/`pricing`/`ShoppingListPage`. Fix any dangling imports.

- [ ] **Step 6: Commit**

```bash
cd /opt/llmDietPlanner
git add frontend/src
git commit -m "feat(plan): remove whole-plan shopping list UI, page, route, API calls

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Remove/repair obsolete tests and run the full suite

**Files:**
- Delete/Modify: `diet_planner/tests/test_llm_service_shopping_parity.py`, `test_aggregate_ingredients.py`, `test_shopping_list_pricing.py` (whole-plan `compute_pricing`/`resolve_store_products` cases), `test_catalog_constrained.py` (recompute + shopping-list assertions), `test_estimate_pricer.py` (its `aggregate_ingredients_from_meals` helper usage + `EstimatePricer` cases), and shopping-list assertions in `test_llm_service_restrictions.py`.

- [ ] **Step 1: List tests referencing removed symbols**

Run: `cd /opt/llmDietPlanner && grep -rln "aggregate_ingredients_from_meals\|generate_complete_plan_with_shopping_list\|generate_shopping_list_with_prices\|compute_pricing\|resolve_store_products\|EstimatePricer\|recompute_plan_prices\|validate_shopping_item\|calculate_package_aware_price" diet_planner/tests`
Expected: The file list to fix.

- [ ] **Step 2: For each file, delete whole-plan-only test cases**

Remove test functions/classes that exercise removed symbols. For files testing BOTH removed and kept behavior (e.g. `test_shopping_list_pricing.py` keeps `classify_pantry_level`/`item_is_excluded` cases), delete only the `compute_pricing`/`resolve_store_products` cases. Delete `test_llm_service_shopping_parity.py` and `test_aggregate_ingredients.py` entirely (they test removed functions). In `test_estimate_pricer.py`, if it only tested `EstimatePricer`, delete it; if it tested shared book helpers, keep those and replace the `aggregate_ingredients_from_meals` input-builder with an inline literal list.

- [ ] **Step 3: Run the full backend suite**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner -v1 2>&1 | tail -30`
Expected: PASS (no errors from removed symbols). Compare against Task 1 baseline — only intended removals differ.

- [ ] **Step 4: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/tests
git commit -m "test(plan): remove obsolete whole-plan shopping-list tests

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Backend suite green**

Run: `cd /opt/llmDietPlanner && python manage.py test diet_planner -v1 2>&1 | tail -15`
Expected: OK.

- [ ] **Step 2: Frontend build green**

Run: `cd /opt/llmDietPlanner/frontend && npm run build 2>&1 | tail -15`
Expected: Build succeeds.

- [ ] **Step 3: Manual smoke (local) — plan page shows recipes, no shopping list**

Use the `/run` or `/verify` skill (or Playwright) to load a generated plan page and confirm: meal plan + per-recipe deals render; no shopping-list sidebar; `/plan/:id/shopping-list` 404s/redirects; per-recipe price/deals still work on a recipe page.
Expected: Confirmed visually.

- [ ] **Step 4: Final review**

Run: `cd /opt/llmDietPlanner && git log --oneline develop..HEAD`
Expected: The task commits above. Ready for QA per the QA workflow before merge.
