# Uvařto First Visit: Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the API the new landing page needs: anonymous instant search over the recipe collection, this week's deals, a combined shopping list, saved lists with a free-tier limit, a simpler plan request, and abuse limits.

**Architecture:** New thin views in `diet_planner/views_discover.py` call focused services:
- `services/discover.py`: understanding plus selection, reusing `prompt_facets` and `recipe_retrieval`.
- `services/discover_cards.py`: card and sheet payloads.
- `services/discover_guard.py`: LLM budget, cache and Turnstile.
- `services/shopping_compose.py`: merging and rounding.

Saved lists are a new model with the entitlement check in `billing/entitlements.py`. Registration gets email normalisation and a disposable-domain block.

**Tech stack:** Django 5.1, DRF, Pydantic schemas, pytest + Django TestCase, Redis through Django's built-in `RedisCache` (LocMem in tests).

**Spec:** `docs/superpowers/specs/2026-11-03-uvarto-first-visit-design.md`. Frontend plan: `docs/superpowers/plans/2026-11-03-uvarto-first-visit-frontend.md`.

**Branch:** `feat/uvarto-launch` (contains the Uvařto rename and migration `diet_planner/0043`).

**How to run tests (all tasks):** use CI's environment, from the repo root.

```bash
export SECRET_KEY=ci-test-secret-key FIELD_ENCRYPTION_KEY='A3xtMz5NmwN6oYF5JJGiBXCxTLrf6vSL272zJSfyC-w=' DEBUG=True GEMINI_API_KEY=ci-dummy-not-a-real-key
unset DATABASE_URL
python3 -m pytest <path> -q -p no:cacheprovider
```

If the repo `.env` exists, it points at prod Supabase. Run tests from a copy without `.env`, or make sure `DATABASE_URL` is unset AND `.env` has no `DATABASE_URL` line before running. **Never run tests against prod.**

---

## File map

| File | Responsibility |
|---|---|
| Create `diet_planner/services/discover.py` | `discover(q, page, *, llm_allowed, generate)` returns understood labels, recipes, exact and fallback flags |
| Create `diet_planner/services/discover_cards.py` | `recipe_card()` and `recipe_sheet()` payloads for `CuratedRecipe` |
| Create `diet_planner/services/discover_guard.py` | Daily LLM budget, result cache, Turnstile challenge state |
| Create `diet_planner/services/shopping_compose.py` | `compose_shopping_list(recipes, people)` |
| Create `diet_planner/throttles.py` | `DiscoverDayThrottle`, `DiscoverBurstThrottle`, `ComposeThrottle` |
| Create `diet_planner/views_discover.py` | Discover, recipe sheet, deals, compose and saved-list views |
| Create `diet_planner/models/shopping.py` + migration `0044` | `SavedShoppingList` |
| Modify `diet_planner/models/__init__.py` | Export the new model |
| Modify `diet_planner/urls.py` | New routes |
| Modify `billing/entitlements.py` | `saved_list_allowance(user)` |
| Modify `diet_planner/schemas.py` | City optional, country CZ default, language `cs` default, `pinned_recipe_ids` |
| Modify `diet_planner/services/recipe_retrieval.py` | Pinned recipes fill pool slots first |
| Modify `diet_planner/services/prompt_facets.py` | `meal_prep` style ("krabičky") |
| Create `login_app/email_rules.py` | `normalise_email()`, `is_disposable()` |
| Modify `login_app/views.py` | Use the email rules plus a `signup` throttle in `RegistrationView` |
| Modify `llm_diet_planner_project/settings.py` | `CACHES`, throttle rates, Turnstile and budget settings |
| Create `diet_planner/management/commands/recategorize_recipe_images.py` | Repair stored wrong `food_category` |

---

### Task 1: Cache and throttle settings

**Files:**
- Modify: `llm_diet_planner_project/settings.py` (the `REST_FRAMEWORK` block around line 160 and the end of the file)
- Test: `diet_planner/tests/test_discover_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_discover_settings.py
from django.conf import settings
from django.test import SimpleTestCase


class DiscoverSettingsTest(SimpleTestCase):
    def test_throttle_scopes_exist(self):
        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        for scope in ('discover', 'discover_burst', 'compose', 'signup'):
            self.assertIn(scope, rates)

    def test_defaults(self):
        self.assertEqual(settings.DISCOVER_DAILY_LLM_BUDGET, 500)
        self.assertEqual(settings.DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE, 3)
        self.assertEqual(settings.TURNSTILE_SECRET_KEY, '')

    def test_cache_falls_back_to_locmem_without_url(self):
        self.assertIn('LocMemCache', settings.CACHES['default']['BACKEND'])
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_discover_settings.py -q -p no:cacheprovider`
Expected: FAIL with `KeyError` / `AttributeError`.

- [ ] **Step 3: Add the settings**

In `DEFAULT_THROTTLE_RATES`, add four entries after `'resend_verification': '5/hour',`:

```python
        'discover': '20/day',
        'discover_burst': '6/min',
        'compose': '60/hour',
        'signup': '5/day',
```

At the end of `settings.py`, add:

```python
# --- First-visit discover (spec 2026-11-03) ---------------------------------
# Shared cache: throttles, the daily LLM budget and discover results must be
# shared across Gunicorn workers, so prod points CACHE_URL at Redis. Tests and
# local runs without it use per-process LocMem.
CACHE_URL = config('CACHE_URL', default='')
if CACHE_URL:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                          'LOCATION': CACHE_URL, 'TIMEOUT': 60 * 60 * 24}}
else:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

DISCOVER_DAILY_LLM_BUDGET = config('DISCOVER_DAILY_LLM_BUDGET', default=500, cast=int)
DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE = 3
DISCOVER_LLM_TIMEOUT_SECONDS = 5
TURNSTILE_SITE_KEY = config('TURNSTILE_SITE_KEY', default='')
TURNSTILE_SECRET_KEY = config('TURNSTILE_SECRET_KEY', default='')
FREE_SAVED_LISTS_PER_MONTH = 3
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python3 -m pytest diet_planner/tests/test_discover_settings.py -q -p no:cacheprovider`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add llm_diet_planner_project/settings.py diet_planner/tests/test_discover_settings.py
git commit -m "feat(discover): cache, throttle and budget settings"
```

---

### Task 2: Throttle classes that count everyone, not just anonymous users

**Files:**
- Create: `diet_planner/throttles.py`
- Test: `diet_planner/tests/test_discover_throttles.py`

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_discover_throttles.py
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, RequestFactory
from rest_framework.request import Request

from diet_planner.throttles import DiscoverDayThrottle


class DiscoverThrottleTest(TestCase):
    def setUp(self):
        cache.clear()

    def _req(self, user=None, ip='1.2.3.4'):
        raw = RequestFactory().post('/api/discover/', REMOTE_ADDR=ip)
        req = Request(raw)
        if user is not None:
            req.user = user
        return req

    def test_anonymous_key_is_ip(self):
        key = DiscoverDayThrottle().get_cache_key(self._req(), view=None)
        self.assertIn('1.2.3.4', key)

    def test_authenticated_users_are_throttled_by_user_id(self):
        user = get_user_model().objects.create(username='u1')
        key = DiscoverDayThrottle().get_cache_key(self._req(user), view=None)
        self.assertIn(f'user-{user.pk}', key)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_discover_throttles.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: diet_planner.throttles`.

- [ ] **Step 3: Implement**

```python
# diet_planner/throttles.py
"""Throttles for the anonymous first-visit endpoints.

DRF's AnonRateThrottle skips signed-in users, but a signed-in user can still
burn Gemini calls on /api/discover/, so these key on the user id when there is
one and on the client IP otherwise.
"""
from rest_framework.throttling import SimpleRateThrottle


class _EveryoneThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            ident = f'user-{user.pk}'
        else:
            ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class DiscoverDayThrottle(_EveryoneThrottle):
    scope = 'discover'


class DiscoverBurstThrottle(_EveryoneThrottle):
    scope = 'discover_burst'


class ComposeThrottle(_EveryoneThrottle):
    scope = 'compose'
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python3 -m pytest diet_planner/tests/test_discover_throttles.py -q -p no:cacheprovider`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/throttles.py diet_planner/tests/test_discover_throttles.py
git commit -m "feat(discover): throttles keyed on user or IP"
```

---

### Task 3: Recipe card and sheet payloads

**Files:**
- Create: `diet_planner/services/discover_cards.py`
- Test: `diet_planner/tests/test_discover_cards.py`

Background:
- `CuratedRecipe` has no image or category field. Its photo is the per-dish image when `has_dish_image(slug)` is true, otherwise the category image chosen by `food_categories.guess_category(name, ingredients)`.
- `base_nutrition` is the whole-recipe total for `base_servings` portions (keys `calories`, `protein`, `carbs`, `fat`). Always divide by `base_servings`.
- `recipe_deals(ingredients, index=..., slug_cache=...)` returns `{matched, total, deals:[{canonical, shop, display_name, valid_until, ingredient}]}`.

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_discover_cards.py
from unittest import mock

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.discover_cards import recipe_card, recipe_sheet


def _recipe(**kw):
    d = dict(slug='kureci-wok', name_cs='Kuřecí wok s rýží', meal_types=['dinner'],
             dish_role='main', prep_time=10, cook_time=15, base_servings=2,
             base_nutrition={'calories': 1000, 'protein': 80, 'carbs': 90, 'fat': 30},
             ingredients=[{'name': 'kuřecí prsa', 'canonical': 'chicken-breast', 'quantity': 300, 'unit': 'g'},
                          {'name': 'česnek', 'canonical': 'garlic', 'quantity': 2, 'unit': 'stroužky'}],
             instructions=['Nakrájej maso.', 'Orestuj.', 'Přidej rýži.'],
             source_url='https://example.com/wok', source_name='Toprecepty.cz',
             status=CuratedRecipe.Status.PUBLISHED)
    d.update(kw)
    return CuratedRecipe.objects.create(**d)


DEAL = {'canonical': 'garlic', 'shop': 'Tesco', 'display_name': 'Česnek',
        'source_url': '', 'valid_until': '2026-11-04T05:59:59+00:00'}


class RecipeCardTest(TestCase):
    def test_card_is_per_portion_and_carries_deals(self):
        r = _recipe()
        with mock.patch('diet_planner.services.recipe_deals._ingredient_slug',
                        side_effect=lambda ing, cache=None: ing.get('canonical')):
            card = recipe_card(r, deal_index={'garlic': DEAL}, slug_cache={})
        self.assertEqual(card['id'], r.id)
        self.assertEqual(card['name'], 'Kuřecí wok s rýží')
        self.assertEqual(card['minutes'], 25)
        self.assertEqual(card['kcal'], 500)
        self.assertEqual(card['deals']['matched'], 1)
        self.assertEqual(card['deals']['names'], ['česnek'])
        self.assertEqual(card['image_url'], '/static/food-images/kure.webp')

    def test_missing_nutrition_is_none_not_zero(self):
        r = _recipe(slug='x', base_nutrition={})
        card = recipe_card(r, deal_index={}, slug_cache={})
        self.assertIsNone(card['kcal'])

    def test_sheet_has_macros_steps_and_source(self):
        r = _recipe()
        sheet = recipe_sheet(r, deal_index={}, slug_cache={})
        self.assertEqual(sheet['macros'], {'protein': 40, 'carbs': 45, 'fat': 15})
        self.assertEqual(len(sheet['steps']), 3)
        self.assertEqual(sheet['source'], {'name': 'Toprecepty.cz', 'url': 'https://example.com/wok'})
        self.assertEqual(sheet['ingredients'][0]['name'], 'kuřecí prsa')
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_discover_cards.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# diet_planner/services/discover_cards.py
"""Public payloads for CuratedRecipe on the first-visit landing (spec 2026-11-03).

Per-portion everywhere: base_nutrition is the whole recipe for base_servings.
Unknown nutrition is None, never 0, so the UI can hide the line.
"""
from typing import Any, Dict, Optional

from diet_planner.food_categories import guess_category
from diet_planner.food_images import dish_image_url, has_dish_image
from diet_planner.services.ingredient_display import display_ingredient_name
from diet_planner.services.recipe_deals import recipe_deals


def _servings(recipe) -> int:
    return max(int(recipe.base_servings or 1), 1)


def _per_portion(recipe, key: str) -> Optional[int]:
    value = (recipe.base_nutrition or {}).get(key)
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return int(round(value / _servings(recipe)))


def image_url(recipe) -> str:
    if has_dish_image(recipe.slug):
        return dish_image_url(recipe.slug)
    return f"/static/food-images/{guess_category(recipe.name_cs, recipe.ingredients or [])}.webp"


def _deals(recipe, deal_index, slug_cache) -> Dict[str, Any]:
    result = recipe_deals(recipe.ingredients or [], index=deal_index, slug_cache=slug_cache)
    names = []
    for deal in result['deals']:
        name = (deal.get('display_name') or deal.get('ingredient') or '').split(' ')[0].lower()
        if name and name not in names:
            names.append(name)
    return {'matched': result['matched'], 'total': result['total'],
            'names': names, 'items': result['deals']}


def recipe_card(recipe, *, deal_index, slug_cache) -> Dict[str, Any]:
    return {
        'id': recipe.id,
        'slug': recipe.slug,
        'name': recipe.name_cs,
        'image_url': image_url(recipe),
        'minutes': recipe.total_time or None,
        'kcal': _per_portion(recipe, 'calories'),
        'deals': _deals(recipe, deal_index, slug_cache),
    }


def recipe_sheet(recipe, *, deal_index, slug_cache) -> Dict[str, Any]:
    card = recipe_card(recipe, deal_index=deal_index, slug_cache=slug_cache)
    protein, carbs, fat = (_per_portion(recipe, k) for k in ('protein', 'carbs', 'fat'))
    servings = _servings(recipe)
    ingredients = []
    for ing in recipe.ingredients or []:
        if ing.get('optional'):
            continue
        qty = ing.get('quantity')
        ingredients.append({
            'name': display_ingredient_name(ing),
            'canonical': ing.get('canonical') or '',
            'quantity': (qty / servings) if isinstance(qty, (int, float)) else None,
            'unit': ing.get('unit') or '',
        })
    return {
        **card,
        'macros': ({'protein': protein, 'carbs': carbs, 'fat': fat}
                   if None not in (protein, carbs, fat) else None),
        'ingredients': ingredients,
        'steps': list(recipe.instructions or []),
        'source': {'name': recipe.source_name, 'url': recipe.source_url},
    }
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python3 -m pytest diet_planner/tests/test_discover_cards.py -q -p no:cacheprovider`
Expected: 3 passed. If `test_card...` fails on `image_url` because `guess_category` returns another category for "Kuřecí wok s rýží" (the `wok` rule comes before `kuřec`), change the expected value to `'/static/food-images/wok.webp'`. That is correct behaviour, so only the test expectation moves.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/discover_cards.py diet_planner/tests/test_discover_cards.py
git commit -m "feat(discover): per-portion recipe card and sheet payloads"
```

---

### Task 4: "Krabičky" requests understood as meal prep

**Files:**
- Modify: `diet_planner/services/prompt_facets.py` (the line `'  "styles": e.g. quick, comfort, light;\n'` inside `_SYSTEM_PROMPT_TEMPLATE`, around line 120)
- Test: `diet_planner/tests/test_prompt_facets_meal_prep.py`

Today "krabičky do práce na celý týden" extracts to empty facets (verified live on 2026-11-03, 2 of 2 attempts). The prompt has no meal-prep vocabulary.

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_prompt_facets_meal_prep.py
from django.test import SimpleTestCase

from diet_planner.services import prompt_facets


class MealPrepVocabularyTest(SimpleTestCase):
    def test_prompt_teaches_meal_prep_style(self):
        text = prompt_facets._SYSTEM_PROMPT_TEMPLATE
        self.assertIn('meal_prep', text)
        self.assertIn('krabičk', text)

    def test_meal_prep_style_survives_coercion(self):
        facets = prompt_facets.extract_prompt_facets(
            'krabičky do práce na celý týden', language='cs', cuisine_vocab=[],
            generate=lambda system, user: '{"styles": ["meal_prep"]}')
        self.assertIn('meal_prep', facets.styles)
        self.assertFalse(facets.suspect)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_prompt_facets_meal_prep.py -q -p no:cacheprovider`
Expected: `test_prompt_teaches_meal_prep_style` FAILS. The second test may already pass, because styles are free strings; keep it as a guard.

- [ ] **Step 3: Implement**

Replace the line:

```python
    '  "styles": e.g. quick, comfort, light;\n'
```

with:

```python
    '  "styles": e.g. quick, comfort, light, meal_prep — use meal_prep when the '
    'user cooks ahead or into lunchboxes ("krabičky", "krabičková", "do práce", '
    '"na celý týden dopředu", "meal prep");\n'
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python3 -m pytest diet_planner/tests/test_prompt_facets_meal_prep.py diet_planner/tests/ -q -p no:cacheprovider -k "facet"`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/prompt_facets.py diet_planner/tests/test_prompt_facets_meal_prep.py
git commit -m "fix(facets): understand krabičky / meal-prep requests"
```

---

### Task 5: Discover selection service

**Files:**
- Create: `diet_planner/services/discover.py`
- Test: `diet_planner/tests/test_discover_service.py`

Rules (spec, "Architecture"):
- **Candidates:** published, main-dish roles (the `dinner` slot rules: `main`, `supper`, `soup`, `light`, or an empty role), `meal_types` containing lunch or dinner, catalog-mapped, and not `SPECIALTY` to shop for.
- **Hard gates:** `recipe_matches_facets`, plus every `facets.dietary` tag present in `dietary_tags`.
- **Ranking:** `score_recipe(..., facets=facets)` with empty plan context. Ties are broken by id for determinism.
- **Exact:** when wanted ingredients were asked for, at least one hit is required. Otherwise any candidate counts as exact.
- **No exact candidates:** return the best-scoring published mains with `exact=False`.
- **Text fallback** (`facets is None`): every query token of 3 or more letters, accent-folded, must appear in the name or ingredient names. When no token matches, use the popular list with `exact=False`.

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_discover_service.py
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.discover import discover, understood_labels
from diet_planner.services.prompt_facets import PromptFacets


def _recipe(slug, name, ingredients, **kw):
    d = dict(slug=slug, name_cs=name, meal_types=['lunch', 'dinner'], dish_role='main',
             ingredients=[{'name': n, 'canonical': c} for n, c in ingredients],
             instructions=['x'], source_url=f'https://e.com/{slug}', source_name='E',
             status=CuratedRecipe.Status.PUBLISHED, prep_time=10, cook_time=10)
    d.update(kw)
    return CuratedRecipe.objects.create(**d)


class DiscoverServiceTest(TestCase):
    def setUp(self):
        self.chicken = _recipe('kure', 'Kuře s rýží', [('kuřecí prsa', 'chicken-breast'), ('rýže', 'rice')])
        self.lentil = _recipe('cocka', 'Čočkový guláš', [('čočka', 'lentils'), ('cibule', 'onion')],
                              dietary_tags=['vegetarian'])
        self.pork = _recipe('rizek', 'Vepřový řízek', [('vepřová kýta', 'pork-leg')], cook_time=50)
        _recipe('side', 'Rýže', [('rýže', 'rice')], dish_role='side')  # never a main

    def _gen(self, payload):
        return lambda system, user: payload

    def test_wanted_ingredient_is_exact_and_first(self):
        out = discover('co uvařit z kuřecích prsou', 0, llm_allowed=True,
                       generate=self._gen('{"wanted_ingredients": ["kuřecí prsa"]}'))
        self.assertTrue(out['exact'])
        self.assertFalse(out['fallback'])
        self.assertEqual(out['recipes'][0].id, self.chicken.id)
        self.assertIn('kuřecí prsa', out['understood'])

    def test_vegetarian_rule_is_a_hard_gate(self):
        out = discover('bez masa', 0, llm_allowed=True,
                       generate=self._gen('{"dietary": ["vegetarian"]}'))
        self.assertEqual([r.id for r in out['recipes']], [self.lentil.id])

    def test_time_limit_excludes_slow_dishes(self):
        out = discover('do 30 minut', 0, llm_allowed=True,
                       generate=self._gen('{"max_time_minutes": 30}'))
        self.assertNotIn(self.pork.id, [r.id for r in out['recipes']])

    def test_no_match_returns_nearest_not_exact(self):
        out = discover('chci kachnu', 0, llm_allowed=True,
                       generate=self._gen('{"wanted_ingredients": ["kachna"]}'))
        self.assertFalse(out['exact'])
        self.assertTrue(out['recipes'])

    def test_sides_never_appear(self):
        out = discover('rýže', 0, llm_allowed=False)
        self.assertNotIn('Rýže', [r.name_cs for r in out['recipes']])

    def test_text_fallback_when_llm_not_allowed(self):
        out = discover('kuřecí prsa', 0, llm_allowed=False)
        self.assertTrue(out['fallback'])
        self.assertEqual(out['recipes'][0].id, self.chicken.id)

    def test_llm_failure_falls_back(self):
        def boom(system, user):
            raise TimeoutError('slow')
        out = discover('kuřecí prsa', 0, llm_allowed=True, generate=boom)
        self.assertTrue(out['fallback'])

    def test_paging(self):
        out = discover('', 0, llm_allowed=False, page_size=2)
        self.assertEqual(len(out['recipes']), 2)
        self.assertTrue(out['has_more'])

    def test_understood_labels_are_czech(self):
        f = PromptFacets(dietary={'vegetarian'}, max_time_minutes=30, emphases={'low_carb'},
                         styles={'meal_prep'})
        self.assertEqual(understood_labels(f),
                         ['bez masa', 'do 30 minut', 'méně sacharidů', 'do krabiček'])
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_discover_service.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# diet_planner/services/discover.py
"""Anonymous first-visit search over the published collection (spec 2026-11-03).

One LLM call reads the request (prompt_facets); selection reuses the plan
pipeline's hard gate and ranking, with no gap filling: what the collection
cannot answer is reported as exact=False, never written by Gemini here.
"""
import concurrent.futures
import unicodedata
from typing import Any, Callable, Dict, List, Optional

from django.conf import settings

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability
from diet_planner.services.prompt_facets import PromptFacets, extract_prompt_facets
from diet_planner.services.recipe_retrieval import (
    _role_allowed, published_cuisine_vocab, published_pool, recipe_matches_facets,
    score_recipe, wanted_matcher,
)

_LABELS_DIETARY = {'vegetarian': 'bez masa', 'vegan': 'veganské', 'gluten_free': 'bez lepku',
                   'dairy_free': 'bez mléka', 'low_carb': 'méně sacharidů'}
_LABELS_EMPHASES = {'high_protein': 'hodně bílkovin', 'low_carb': 'méně sacharidů',
                    'low_calorie': 'lehčí jídla', 'budget': 'levnější suroviny'}
_LABELS_STYLES = {'quick': 'rychlé', 'light': 'lehčí jídla', 'comfort': 'poctivé jídlo',
                  'meal_prep': 'do krabiček'}


def _fold(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', (text or '').lower())
                   if not unicodedata.combining(c))


def understood_labels(facets: Optional[PromptFacets]) -> List[str]:
    if facets is None:
        return []
    labels: List[str] = []

    def add(label):
        if label and label not in labels:
            labels.append(label)

    for w in sorted(facets.wanted_ingredients):
        add(w)
    for a in sorted(facets.avoided_ingredients):
        add(f'bez: {a}')
    for d in sorted(facets.dietary):
        add(_LABELS_DIETARY.get(d, d))
    if facets.max_time_minutes:
        add(f'do {facets.max_time_minutes} minut')
    for e in sorted(facets.emphases):
        add(_LABELS_EMPHASES.get(e))
    for s in sorted(facets.styles):
        add(_LABELS_STYLES.get(s))
    for c in sorted(facets.cuisines):
        add(c)
    return labels


def _mains(pool: List[CuratedRecipe]) -> List[CuratedRecipe]:
    out = []
    for r in pool:
        if not {'lunch', 'dinner'} & set(r.meal_types or []):
            continue
        if not _role_allowed('dinner', r.dish_role or ''):
            continue
        if not r.is_catalog_mapped() or r.shopping_difficulty == Availability.SPECIALTY:
            continue
        out.append(r)
    return out


def _read_request(q: str, pool, generate) -> Optional[PromptFacets]:
    """Facets, or None when the LLM failed, timed out or found nothing usable."""
    timeout = getattr(settings, 'DISCOVER_LLM_TIMEOUT_SECONDS', 5)
    vocab = published_cuisine_vocab(pool=pool)
    kwargs = {'language': 'cs', 'cuisine_vocab': vocab}
    if generate is not None:
        kwargs['generate'] = generate
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        facets = executor.submit(extract_prompt_facets, q, **kwargs).result(timeout=timeout)
    except Exception:  # noqa: BLE001 - timeout or LLM error: text fallback
        return None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    if facets.suspect or facets.is_empty():
        return None
    return facets


def _rank(candidates, facets) -> List[CuratedRecipe]:
    scored = [(score_recipe(r, used_recipe_ids=set(), used_cuisines=[], facets=facets), -r.id, r)
              for r in candidates]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [r for _, _, r in scored]


def _text_match(q: str, mains: List[CuratedRecipe]) -> List[CuratedRecipe]:
    tokens = [t for t in _fold(q).replace(',', ' ').split() if len(t) >= 3]
    if not tokens:
        return []
    out = []
    for r in mains:
        hay = _fold(r.name_cs + ' ' + ' '.join(str(i.get('name', '')) for i in r.ingredients or []))
        if all(t[:5] in hay for t in tokens if t not in {'uvarit', 'chci', 'neco', 'doma', 'mam'}):
            out.append(r)
    return out


def discover(q: str, page: int, *, llm_allowed: bool,
             generate: Optional[Callable[[str, str], str]] = None,
             page_size: int = 4) -> Dict[str, Any]:
    q = (q or '').strip()[:300]
    pool = published_pool()
    mains = _mains(pool)
    facets = _read_request(q, pool, generate) if (q and llm_allowed) else None
    fallback = bool(q) and facets is None

    if facets is not None:
        gated = [r for r in mains
                 if recipe_matches_facets(r, facets)
                 and set(facets.dietary) <= set(r.dietary_tags or [])]
        if facets.wanted_ingredients:
            matcher = wanted_matcher(facets)
            exact_list = [r for r in gated if matcher.hits(r) > 0]
        else:
            exact_list = gated
        ranked = _rank(exact_list, facets)
        exact = bool(ranked)
        if not ranked:
            ranked = _rank(gated or mains, None)
    else:
        matched = _text_match(q, mains) if q else []
        exact = bool(matched) or not q
        ranked = _rank(matched or mains, None)

    start = max(page, 0) * page_size
    return {
        'understood': understood_labels(facets),
        'exact': exact,
        'fallback': fallback,
        'recipes': ranked[start:start + page_size],
        'has_more': len(ranked) > start + page_size,
    }
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python3 -m pytest diet_planner/tests/test_discover_service.py -q -p no:cacheprovider`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/discover.py diet_planner/tests/test_discover_service.py
git commit -m "feat(discover): collection search with facets, gates and text fallback"
```

---

### Task 6: Discover guard (LLM budget, cache, bot challenge)

**Files:**
- Create: `diet_planner/services/discover_guard.py`
- Test: `diet_planner/tests/test_discover_guard.py`

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_discover_guard.py
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from diet_planner.services import discover_guard as g


@override_settings(DISCOVER_DAILY_LLM_BUDGET=2, TURNSTILE_SECRET_KEY='')
class GuardTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_budget_allows_then_refuses(self):
        self.assertTrue(g.take_llm_slot())
        self.assertTrue(g.take_llm_slot())
        self.assertFalse(g.take_llm_slot())

    def test_alert_fires_once_at_80_percent(self):
        with mock.patch.object(g, '_alert') as alert:
            g.take_llm_slot(); g.take_llm_slot(); g.take_llm_slot()
        alert.assert_called_once()

    def test_result_cache_key_ignores_case_and_accents(self):
        self.assertEqual(g.result_key('Kuřecí  Prsa', 0), g.result_key('kureci prsa', 0))

    def test_challenge_not_needed_without_turnstile_keys(self):
        for _ in range(10):
            self.assertFalse(g.challenge_needed('1.2.3.4'))

    @override_settings(TURNSTILE_SECRET_KEY='secret', DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE=3)
    def test_challenge_after_free_searches_until_verified(self):
        for _ in range(3):
            self.assertFalse(g.challenge_needed('9.9.9.9'))
        self.assertTrue(g.challenge_needed('9.9.9.9'))
        with mock.patch.object(g, '_siteverify', return_value=True):
            self.assertTrue(g.verify_challenge('token', '9.9.9.9'))
        self.assertFalse(g.challenge_needed('9.9.9.9'))
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_discover_guard.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# diet_planner/services/discover_guard.py
"""Abuse limits for /api/discover/: daily LLM budget, result cache, Turnstile.

Everything lives in the shared Django cache (Redis on prod via CACHE_URL), so
limits hold across Gunicorn workers. Without TURNSTILE_SECRET_KEY the bot
check is off and only the throttles apply.
"""
import hashlib
import logging
import unicodedata

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)
_DAY = 60 * 60 * 24
SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


def _today() -> str:
    return timezone.localdate().isoformat()


def _alert(count: int, budget: int) -> None:
    from diet_planner.services.llm_health import default_post, notify_slack
    notify_slack(
        f':warning: Uvařto discover: {count}/{budget} LLM calls used today ({_today()}). '
        'Past the budget, search switches to text matching.',
        webhook_url=getattr(settings, 'LLM_HEALTH_SLACK_WEBHOOK_URL', ''),
        bot_token=getattr(settings, 'SLACK_BOT_TOKEN', ''),
        channel=getattr(settings, 'LLM_HEALTH_SLACK_CHANNEL', ''),
        post=default_post)


def take_llm_slot() -> bool:
    """Count one discover LLM call against today's budget. False when spent."""
    budget = int(getattr(settings, 'DISCOVER_DAILY_LLM_BUDGET', 500))
    key = f'discover:llm:{_today()}'
    cache.add(key, 0, _DAY)
    count = cache.incr(key)
    if count >= int(budget * 0.8) and cache.add(f'discover:llm-alert:{_today()}', 1, _DAY):
        try:
            _alert(count, budget)
        except Exception:  # noqa: BLE001 - an alert must never break search
            logger.exception('discover budget alert failed')
    return count <= budget


def _fold(q: str) -> str:
    q = unicodedata.normalize('NFD', (q or '').lower())
    return ' '.join(''.join(c for c in q if not unicodedata.combining(c)).split())


def result_key(q: str, page: int) -> str:
    digest = hashlib.sha256(_fold(q).encode()).hexdigest()[:32]
    return f'discover:result:{digest}:{int(page)}'


def _siteverify(token: str, ip: str) -> bool:
    resp = requests.post(SITEVERIFY_URL, timeout=5, data={
        'secret': settings.TURNSTILE_SECRET_KEY, 'response': token, 'remoteip': ip})
    return bool(resp.json().get('success'))


def challenge_needed(ident: str) -> bool:
    """Count one search; True once past the free searches and not verified."""
    if not getattr(settings, 'TURNSTILE_SECRET_KEY', ''):
        return False
    if cache.get(f'discover:verified:{ident}'):
        return False
    key = f'discover:searches:{ident}'
    cache.add(key, 0, 60 * 60)
    count = cache.incr(key)
    return count > int(getattr(settings, 'DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE', 3))


def verify_challenge(token: str, ident: str) -> bool:
    if not token:
        return False
    try:
        ok = _siteverify(token, ident)
    except Exception:  # noqa: BLE001 - Cloudflare down: let the throttles carry it
        logger.exception('turnstile siteverify failed')
        ok = True
    if ok:
        cache.set(f'discover:verified:{ident}', 1, 60 * 60)
    return ok
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python3 -m pytest diet_planner/tests/test_discover_guard.py -q -p no:cacheprovider`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/discover_guard.py diet_planner/tests/test_discover_guard.py
git commit -m "feat(discover): daily LLM budget, result cache key, Turnstile challenge"
```

---

### Task 7: Combined shopping list composer

**Files:**
- Create: `diet_planner/services/shopping_compose.py`
- Test: `diet_planner/tests/test_shopping_compose.py`

Rules:
- Lines merge only when the canonical and unit both match (case-insensitive unit).
- Quantity per line = sum over recipes of `quantity / base_servings × people`.
- Rounding for display: units starting `ks`, `stroužk`, `plátk`, `svazek`, `konzerv` or `balen` round up to an integer. `g` and `ml` round to the nearest 10 (minimum 10). Spoon or "to taste" units (`lžíc`, `lžič`, `špetk`, `dle chuti`, `hrst`) carry no amount. Anything else keeps one decimal.

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_shopping_compose.py
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.shopping_compose import compose_shopping_list, shopping_amount


def _r(slug, ings, servings=1):
    return CuratedRecipe.objects.create(
        slug=slug, name_cs=slug, meal_types=['dinner'], dish_role='main', base_servings=servings,
        ingredients=[{'name': n, 'canonical': c, 'quantity': q, 'unit': u} for n, c, q, u in ings],
        instructions=['x'], source_url='https://e.com', source_name='E',
        status=CuratedRecipe.Status.PUBLISHED)


class ShoppingAmountTest(TestCase):
    def test_rounding_rules(self):
        self.assertEqual(shopping_amount(0.4, 'ks'), (1, 'ks'))
        self.assertEqual(shopping_amount(2.25, 'stroužky'), (3, 'stroužky'))
        self.assertEqual(shopping_amount(163, 'g'), (160, 'g'))
        self.assertEqual(shopping_amount(3, 'g'), (10, 'g'))
        self.assertEqual(shopping_amount(0.6, 'lžíce'), (None, 'lžíce'))
        self.assertEqual(shopping_amount(0.25, 'l'), (0.3, 'l'))
        self.assertEqual(shopping_amount(None, 'g'), (None, 'g'))


class ComposeTest(TestCase):
    def test_merges_same_canonical_and_unit_and_scales_by_people(self):
        a = _r('a', [('česnek', 'garlic', 2, 'stroužky'), ('rýže', 'rice', 200, 'g')], servings=2)
        b = _r('b', [('česnek', 'garlic', 1, 'stroužky'), ('rýže', 'rice', 1, 'hrnek')], servings=1)
        lines = compose_shopping_list([a, b], people=2, deal_index={})
        garlic = [l for l in lines if l['canonical'] == 'garlic']
        self.assertEqual(len(garlic), 1)
        self.assertEqual(garlic[0]['amount'], 4)          # 2/2*2 + 1/1*2 = 4
        self.assertEqual(garlic[0]['needed_by'], 2)
        rice = [l for l in lines if l['canonical'] == 'rice']
        self.assertEqual(len(rice), 2)                    # g and hrnek do not merge

    def test_deal_lines_carry_the_deal_and_come_first(self):
        a = _r('a', [('rýže', 'rice', 100, 'g'), ('česnek', 'garlic', 1, 'ks')])
        deal = {'canonical': 'garlic', 'shop': 'Tesco', 'display_name': 'Česnek',
                'valid_until': '2026-11-04T05:59:59+00:00'}
        lines = compose_shopping_list([a], people=1, deal_index={'garlic': deal})
        self.assertEqual(lines[0]['canonical'], 'garlic')
        self.assertEqual(lines[0]['deal']['shop'], 'Tesco')
        self.assertIsNone(lines[1]['deal'])

    def test_people_is_clamped(self):
        a = _r('a', [('rýže', 'rice', 100, 'g')])
        self.assertEqual(compose_shopping_list([a], people=99, deal_index={})[0]['amount'], 600)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_shopping_compose.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# diet_planner/services/shopping_compose.py
"""One shopping list for several picked recipes (spec 2026-11-03).

Merges only like with like (canonical + unit): never invents a unit
conversion. Amounts are rounded the way people shop: whole pieces, tens of
grams, no amount for a spoon of something.
"""
import math
from typing import Any, Dict, List, Optional, Tuple

PEOPLE_MIN, PEOPLE_MAX = 1, 6
_WHOLE = ('ks', 'stroužk', 'stroužek', 'plátk', 'svazek', 'konzerv', 'balen')
_NO_AMOUNT = ('lžíc', 'lžič', 'špetk', 'dle chuti', 'hrst')


def shopping_amount(quantity: Optional[float], unit: str) -> Tuple[Optional[float], str]:
    unit = (unit or '').strip()
    u = unit.lower()
    if quantity is None or quantity <= 0 or any(u.startswith(p) for p in _NO_AMOUNT):
        return None, unit
    if any(u.startswith(p) for p in _WHOLE):
        return math.ceil(quantity - 1e-9), unit
    if u in ('g', 'ml'):
        return max(10, int(round(quantity / 10.0)) * 10), unit
    return round(quantity + 1e-9, 1), unit


def compose_shopping_list(recipes, *, people: int, deal_index: Dict[str, dict]) -> List[Dict[str, Any]]:
    people = min(max(int(people or 2), PEOPLE_MIN), PEOPLE_MAX)
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for recipe in recipes:
        servings = max(int(recipe.base_servings or 1), 1)
        for ing in recipe.ingredients or []:
            if ing.get('optional'):
                continue
            canonical = (ing.get('canonical') or ing.get('name') or '').strip().lower()
            unit = (ing.get('unit') or '').strip()
            key = (canonical, unit.lower())
            line = merged.setdefault(key, {
                'name': ing.get('name') or canonical, 'canonical': canonical, 'unit': unit,
                'raw': 0.0, 'has_qty': False, 'recipes': [], 'deal': deal_index.get(canonical),
            })
            qty = ing.get('quantity')
            if isinstance(qty, (int, float)) and qty > 0:
                line['raw'] += qty / servings * people
                line['has_qty'] = True
            if recipe.id not in line['recipes']:
                line['recipes'].append(recipe.id)
    out = []
    for line in merged.values():
        amount, unit = shopping_amount(line['raw'] if line['has_qty'] else None, line['unit'])
        out.append({'name': line['name'], 'canonical': line['canonical'], 'amount': amount,
                    'unit': unit, 'needed_by': len(line['recipes']), 'recipe_ids': line['recipes'],
                    'deal': line['deal']})
    out.sort(key=lambda l: (l['deal'] is None, l['name'].lower()))
    return out
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python3 -m pytest diet_planner/tests/test_shopping_compose.py -q -p no:cacheprovider`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/shopping_compose.py diet_planner/tests/test_shopping_compose.py
git commit -m "feat(shopping): combined list with like-for-like merge and shop rounding"
```

---

### Task 8: Saved shopping list model and free allowance

**Files:**
- Create: `diet_planner/models/shopping.py`
- Modify: `diet_planner/models/__init__.py` (add `from .shopping import SavedShoppingList` and append it to `__all__` if the file defines one)
- Create: migration via `makemigrations`
- Modify: `billing/entitlements.py` (append a function)
- Test: `billing/test_saved_list_allowance.py`

- [ ] **Step 1: Write the failing test**

```python
# billing/test_saved_list_allowance.py
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from billing.entitlements import saved_list_allowance
from diet_planner.models import SavedShoppingList


class SavedListAllowanceTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='free')

    def _save(self, when=None):
        lst = SavedShoppingList.objects.create(user=self.user, recipe_ids=[1], people=2)
        if when:
            SavedShoppingList.objects.filter(pk=lst.pk).update(created_at=when)

    def test_free_user_gets_three_this_month(self):
        for _ in range(3):
            self.assertTrue(saved_list_allowance(self.user)['can_save'])
            self._save()
        allowance = saved_list_allowance(self.user)
        self.assertFalse(allowance['can_save'])
        self.assertEqual(allowance['used'], 3)
        self.assertEqual(allowance['limit'], 3)

    def test_last_month_does_not_count(self):
        for _ in range(3):
            self._save(when=timezone.now() - timedelta(days=40))
        self.assertTrue(saved_list_allowance(self.user)['can_save'])

    def test_subscriber_is_unlimited(self):
        for _ in range(5):
            self._save()
        sub = mock.Mock()
        sub.is_entitled.return_value = True
        with mock.patch('billing.entitlements.active_subscription', return_value=sub):
            allowance = saved_list_allowance(self.user)
        self.assertTrue(allowance['can_save'])
        self.assertIsNone(allowance['limit'])
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest billing/test_saved_list_allowance.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError` (`SavedShoppingList` / `saved_list_allowance`).

- [ ] **Step 3: Implement the model**

```python
# diet_planner/models/shopping.py
from django.conf import settings
from django.db import models


class SavedShoppingList(models.Model):
    """A visitor's picked recipes kept after signup (spec 2026-11-03).

    recipe_ids are CuratedRecipe ids; the list itself is recomposed on read so
    deals and rounding are always current.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='saved_shopping_lists')
    recipe_ids = models.JSONField(default=list)
    people = models.PositiveSmallIntegerField(default=2)
    at_home = models.JSONField(default=list, help_text='canonical|unit keys marked "mám doma"')
    query = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
```

Add to `diet_planner/models/__init__.py`:

```python
from .shopping import SavedShoppingList  # noqa: E402,F401
```

Then run:

```bash
python3 manage.py makemigrations diet_planner -n saved_shopping_list
```

Expected: `diet_planner/migrations/0044_saved_shopping_list.py` is created, depending on `0043_update_site_name_uvarto`.

- [ ] **Step 4: Implement the allowance**

Append to `billing/entitlements.py`:

```python
def saved_list_allowance(user) -> dict:
    """Free accounts: FREE_SAVED_LISTS_PER_MONTH per calendar month.
    An entitled subscription: unlimited (limit None)."""
    from django.conf import settings
    from django.utils import timezone

    from diet_planner.models import SavedShoppingList

    sub = active_subscription(user)
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = SavedShoppingList.objects.filter(user=user, created_at__gte=month_start).count()
    if sub is not None and sub.is_entitled():
        return {'can_save': True, 'used': used, 'limit': None}
    limit = int(getattr(settings, 'FREE_SAVED_LISTS_PER_MONTH', 3))
    return {'can_save': used < limit, 'used': used, 'limit': limit}
```

- [ ] **Step 5: Run the test and confirm it passes**

Run: `python3 -m pytest billing/test_saved_list_allowance.py -q -p no:cacheprovider`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add diet_planner/models/shopping.py diet_planner/models/__init__.py diet_planner/migrations/0044_saved_shopping_list.py billing/entitlements.py billing/test_saved_list_allowance.py
git commit -m "feat(billing): saved shopping lists, 3 per month free, unlimited for subscribers"
```

---

### Task 9: Discover, deals, compose and saved-list views

**Files:**
- Create: `diet_planner/views_discover.py`
- Modify: `diet_planner/urls.py` (add the routes after `recipes/public/<int:pk>/`)
- Test: `diet_planner/tests/test_discover_views.py`

Response envelope, as on every other endpoint: `{"status": "success", "data": {...}}`, and on errors `{"status": "error", "code": ..., "error": ...}`.

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_discover_views.py
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from diet_planner.models import CuratedRecipe, SavedShoppingList


def _recipe(slug, name, ing):
    return CuratedRecipe.objects.create(
        slug=slug, name_cs=name, meal_types=['dinner'], dish_role='main', base_servings=1,
        ingredients=[{'name': ing, 'canonical': ing, 'quantity': 100, 'unit': 'g'}],
        instructions=['x'], source_url='https://e.com', source_name='E',
        status=CuratedRecipe.Status.PUBLISHED, prep_time=5, cook_time=10)


@override_settings(TURNSTILE_SECRET_KEY='', DISCOVER_DAILY_LLM_BUDGET=100)
class DiscoverViewsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.a = _recipe('a', 'Kuře s rýží', 'kuřecí prsa')
        self.b = _recipe('b', 'Čočková polévka', 'čočka')
        patcher = mock.patch('diet_planner.views_discover.active_deal_index', return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_discover_returns_cards(self):
        with mock.patch('diet_planner.services.discover.extract_prompt_facets',
                        side_effect=Exception('no llm in tests')):
            resp = self.client.post('/api/discover/', {'q': 'kuřecí prsa'}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['recipes'][0]['name'], 'Kuře s rýží')
        self.assertTrue(data['fallback'])

    def test_discover_result_is_cached(self):
        with mock.patch('diet_planner.views_discover.discover',
                        wraps=__import__('diet_planner.services.discover', fromlist=['discover']).discover) as d:
            self.client.post('/api/discover/', {'q': 'čočka'}, format='json')
            self.client.post('/api/discover/', {'q': 'Čočka'}, format='json')
        self.assertEqual(d.call_count, 1)

    def test_over_budget_disables_llm(self):
        with mock.patch('diet_planner.views_discover.take_llm_slot', return_value=False), \
             mock.patch('diet_planner.views_discover.discover', return_value={
                 'understood': [], 'exact': True, 'fallback': True, 'recipes': [], 'has_more': False}) as d:
            self.client.post('/api/discover/', {'q': 'něco'}, format='json')
        self.assertFalse(d.call_args.kwargs['llm_allowed'])

    @override_settings(TURNSTILE_SECRET_KEY='s', DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE=1)
    def test_challenge_required_after_free_searches(self):
        self.client.post('/api/discover/', {'q': 'a1'}, format='json')
        resp = self.client.post('/api/discover/', {'q': 'a2'}, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['code'], 'CHALLENGE_REQUIRED')

    def test_recipe_sheet(self):
        resp = self.client.get(f'/api/discover/recipe/{self.a.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['steps'], ['x'])

    def test_unpublished_recipe_is_404(self):
        CuratedRecipe.objects.filter(pk=self.a.pk).update(status=CuratedRecipe.Status.DRAFT)
        self.assertEqual(self.client.get(f'/api/discover/recipe/{self.a.id}/').status_code, 404)

    def test_deals_this_week_empty_when_none(self):
        resp = self.client.get('/api/deals/this-week/')
        self.assertEqual(resp.json()['data']['deals'], [])

    def test_compose_anonymous(self):
        resp = self.client.post('/api/shopping-list/compose/',
                                {'recipe_ids': [self.a.id, self.b.id], 'people': 2}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['data']['lines']), 2)

    def test_save_list_requires_login_and_enforces_free_limit(self):
        self.assertEqual(self.client.post('/api/shopping-lists/', {}, format='json').status_code, 401)
        user = get_user_model().objects.create(username='u')
        self.client.force_authenticate(user)
        for _ in range(3):
            ok = self.client.post('/api/shopping-lists/', {'recipe_ids': [self.a.id], 'people': 2}, format='json')
            self.assertEqual(ok.status_code, 201)
        over = self.client.post('/api/shopping-lists/', {'recipe_ids': [self.a.id], 'people': 2}, format='json')
        self.assertEqual(over.status_code, 402)
        self.assertEqual(over.json()['code'], 'LIST_LIMIT')
        self.assertEqual(SavedShoppingList.objects.filter(user=user).count(), 3)
        listing = self.client.get('/api/shopping-lists/')
        self.assertEqual(len(listing.json()['data']['lists']), 3)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_discover_views.py -q -p no:cacheprovider`
Expected: FAIL with 404s (the routes don't exist yet).

- [ ] **Step 3: Implement the views**

```python
# diet_planner/views_discover.py
"""First-visit API (spec 2026-11-03): anonymous search, sheet, deals, list."""
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.entitlements import saved_list_allowance
from diet_planner.models import CuratedRecipe, SavedShoppingList
from diet_planner.services.discover import discover
from diet_planner.services.discover_cards import recipe_card, recipe_sheet
from diet_planner.services.discover_guard import (
    challenge_needed, result_key, take_llm_slot, verify_challenge,
)
from diet_planner.services.recipe_deals import active_deal_index
from diet_planner.services.shopping_compose import compose_shopping_list
from diet_planner.throttles import ComposeThrottle, DiscoverBurstThrottle, DiscoverDayThrottle

_RESULT_TTL = 60 * 60 * 24
_MAX_LIST_RECIPES = 12


def _ok(data, code=status.HTTP_200_OK):
    return Response({'status': 'success', 'data': data}, status=code)


def _err(code, message, http):
    return Response({'status': 'error', 'code': code, 'error': message}, status=http)


def _ident(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '')) or 'unknown'


def _published(ids):
    ids = [int(i) for i in ids if str(i).isdigit()][:_MAX_LIST_RECIPES]
    by_id = {r.id: r for r in CuratedRecipe.objects.filter(
        id__in=ids, status=CuratedRecipe.Status.PUBLISHED)}
    return [by_id[i] for i in ids if i in by_id]


class DiscoverView(APIView):
    permission_classes = []
    throttle_classes = [DiscoverBurstThrottle, DiscoverDayThrottle]

    def post(self, request):
        q = str(request.data.get('q', '') or '')[:300]
        page = int(request.data.get('page', 0) or 0)
        ident = _ident(request)
        token = request.data.get('turnstile_token', '')
        if token:
            verify_challenge(token, ident)
        if challenge_needed(ident):
            return _err('CHALLENGE_REQUIRED', 'Potvrď prosím, že nejsi robot.', status.HTTP_403_FORBIDDEN)

        key = result_key(q, page)
        cached = cache.get(key)
        if cached is not None:
            return _ok(cached)

        result = discover(q, page, llm_allowed=bool(q) and take_llm_slot())
        index, slugs = active_deal_index(), {}
        data = {**result, 'recipes': [recipe_card(r, deal_index=index, slug_cache=slugs)
                                      for r in result['recipes']]}
        cache.set(key, data, _RESULT_TTL)
        return _ok(data)


class DiscoverRecipeView(APIView):
    permission_classes = []
    throttle_classes = [ComposeThrottle]

    def get(self, request, pk: int):
        recipe = get_object_or_404(CuratedRecipe, pk=pk, status=CuratedRecipe.Status.PUBLISHED)
        return _ok(recipe_sheet(recipe, deal_index=active_deal_index(), slug_cache={}))


class DealsThisWeekView(APIView):
    permission_classes = []

    def get(self, request):
        deals = sorted(active_deal_index().values(), key=lambda d: d['valid_until'])
        return _ok({'deals': [{
            'canonical': d['canonical'], 'name': d['display_name'], 'shop': d['shop'],
            'valid_until': d['valid_until'],
        } for d in deals[:12]]})


class ShoppingListComposeView(APIView):
    permission_classes = []
    throttle_classes = [ComposeThrottle]

    def post(self, request):
        recipes = _published(request.data.get('recipe_ids') or [])
        people = request.data.get('people', 2)
        lines = compose_shopping_list(recipes, people=people, deal_index=active_deal_index())
        return _ok({'recipes': [recipe_card(r, deal_index={}, slug_cache={}) for r in recipes],
                    'lines': lines})


class SavedShoppingListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        lists = SavedShoppingList.objects.filter(user=request.user)[:20]
        return _ok({'lists': [{'id': l.id, 'recipe_ids': l.recipe_ids, 'people': l.people,
                               'at_home': l.at_home, 'query': l.query,
                               'created_at': l.created_at.isoformat()} for l in lists],
                    'allowance': saved_list_allowance(request.user)})

    def post(self, request):
        allowance = saved_list_allowance(request.user)
        if not allowance['can_save']:
            return _err('LIST_LIMIT',
                        f"Tento měsíc máš {allowance['limit']} seznamy za sebou. S předplatným bez omezení.",
                        status.HTTP_402_PAYMENT_REQUIRED)
        recipes = _published(request.data.get('recipe_ids') or [])
        if not recipes:
            return _err('EMPTY_LIST', 'Seznam je prázdný.', status.HTTP_400_BAD_REQUEST)
        people = min(max(int(request.data.get('people', 2) or 2), 1), 6)
        saved = SavedShoppingList.objects.create(
            user=request.user, recipe_ids=[r.id for r in recipes], people=people,
            at_home=[str(k)[:120] for k in (request.data.get('at_home') or [])][:200],
            query=str(request.data.get('query', '') or '')[:300])
        return _ok({'id': saved.id}, status.HTTP_201_CREATED)
```

- [ ] **Step 4: Add the routes**

In `diet_planner/urls.py`, add `from diet_planner import views_discover` next to the existing `views` import, then add these after the `recipes/public/<int:pk>/` line:

```python
    path('discover/', views_discover.DiscoverView.as_view(), name='discover'),
    path('discover/recipe/<int:pk>/', views_discover.DiscoverRecipeView.as_view(), name='discover-recipe'),
    path('deals/this-week/', views_discover.DealsThisWeekView.as_view(), name='deals-this-week'),
    path('shopping-list/compose/', views_discover.ShoppingListComposeView.as_view(), name='shopping-list-compose'),
    path('shopping-lists/', views_discover.SavedShoppingListView.as_view(), name='shopping-lists'),
```

Check that the diet_planner urls are mounted under `/api/` (`grep -n "diet_planner.urls" llm_diet_planner_project/urls.py`). If the prefix differs, adjust the test URLs to match.

- [ ] **Step 5: Run the test and confirm it passes**

Run: `python3 -m pytest diet_planner/tests/test_discover_views.py -q -p no:cacheprovider`
Expected: 9 passed. The default authentication returns 401 for anonymous requests to `IsAuthenticated` views. If the project returns 403 instead, assert `in (401, 403)`.

- [ ] **Step 6: Commit**

```bash
git add diet_planner/views_discover.py diet_planner/urls.py diet_planner/tests/test_discover_views.py
git commit -m "feat(discover): search, sheet, deals, compose and saved-list endpoints"
```

---

### Task 10: Plan request without city, plus pinned recipes

**Files:**
- Modify: `diet_planner/schemas.py:63-75` (`country`, `city`, `language_code`) and add `pinned_recipe_ids`
- Modify: `diet_planner/views.py` (`DietaryGoalCreateView.post`, the `goal_data` dict around line 152)
- Modify: `diet_planner/models/core.py` (`DietaryGoal`: add `pinned_recipe_ids = models.JSONField(default=list, blank=True)`) + migration `0045`
- Modify: `diet_planner/services/recipe_retrieval.py` (`select_recipes_for_pool`)
- Test: `diet_planner/tests/test_plan_request_simple.py`

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_plan_request_simple.py
from types import SimpleNamespace

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.schemas import DietaryGoalCreateRequest
from diet_planner.services.recipe_retrieval import select_recipes_for_pool


def _r(slug):
    return CuratedRecipe.objects.create(
        slug=slug, name_cs=slug, meal_types=['dinner'], dish_role='main',
        ingredients=[{'name': 'rýže', 'canonical': 'rice'}], instructions=['x'],
        source_url='https://e.com', source_name='E', status=CuratedRecipe.Status.PUBLISHED)


class SimplePlanRequestTest(TestCase):
    def test_city_optional_country_defaults(self):
        req = DietaryGoalCreateRequest(prompt='5 večeří', dinners=5)
        self.assertEqual(req.city, '')
        self.assertEqual(req.country.value, 'CZ')
        self.assertEqual(req.language_code, 'cs')
        self.assertEqual(req.pinned_recipe_ids, [])

    def test_pinned_recipes_fill_first(self):
        recipes = [_r(f'r{i}') for i in range(4)]
        goal = SimpleNamespace(pk=1, id=1, breakfasts=0, lunches=0, dinners=3, small_meals=0, snacks=0,
                               dietary_restrictions='', prompt='', user=None,
                               derived_dietary_tags=[], pinned_recipe_ids=[recipes[3].id])
        out = select_recipes_for_pool(goal)
        ids = [m['recipe'].id for m in out['meals']]
        self.assertEqual(ids[0], recipes[3].id)
        self.assertEqual(len(set(ids)), 3)
```

If `required_tags_for_goal(goal)` reads attributes the `SimpleNamespace` lacks, the test errors with `AttributeError: <name>`. Add that attribute to the namespace with an empty value, after reading `required_tags_for_goal` in `recipe_retrieval.py:185` to confirm the right default.

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_plan_request_simple.py -q -p no:cacheprovider`
Expected: FAIL. The schema requires `country` and `city`, and the pin is ignored.

- [ ] **Step 3: Change the schema**

In `diet_planner/schemas.py`, replace the `country`, `city` and `language_code` fields with these, and add `pinned_recipe_ids` after them:

```python
    country: CountryEnum = Field(
        default=CountryEnum.CZ,
        description="Country code where user wants to buy ingredients"
    )
    city: str = Field(
        default="",
        max_length=100,
        description="Optional; leaflet deals are national, so the plan no longer asks"
    )
    language_code: str = Field(
        default="cs",
        min_length=2,
```

Keep the rest of the existing `language_code` definition unchanged. Then add:

```python
    pinned_recipe_ids: list[int] = Field(
        default_factory=list, max_length=12,
        description="CuratedRecipe ids the visitor picked before signup; filled first"
    )
```

If `CountryEnum` has no `CZ` member, use the member whose value is `'CZ'` (`grep -n "class CountryEnum" -A6 diet_planner/schemas.py`).

- [ ] **Step 4: Add the model field and the pinned fill**

In `DietaryGoal` (`diet_planner/models/core.py`), next to the pool count fields, add:

```python
    pinned_recipe_ids = models.JSONField(default=list, blank=True,
                                         help_text='CuratedRecipe ids picked before signup; fill first')
```

Run `python3 manage.py makemigrations diet_planner -n goal_pinned_recipes`.

In `DietaryGoalCreateView.post` (`diet_planner/views.py`), add this to `goal_data`:

```python
                'pinned_recipe_ids': schema.pinned_recipe_ids,
```

In `select_recipes_for_pool`, right after `filled = total = 0`, add:

```python
    pinned = [r for pid in (getattr(goal, 'pinned_recipe_ids', None) or [])
              for r in pool if r.id == pid]
```

Inside the slot loop, immediately after the `if slot in skip_slots:` block and before `candidates = eligible_recipes_for_slot(`, add:

```python
            pin = next((r for r in pinned if r.id not in used_recipe_ids
                        and _SLOT_TO_MEAL_TYPE.get(slot, slot) in (r.meal_types or [])), None)
            if pin is not None:
                meals.append({'slot': slot, 'index': index, 'recipe': pin})
                used_recipe_ids.add(pin.id)
                if pin.dish_family:
                    used_families.add(pin.dish_family)
                    used_families_count[pin.dish_family] += 1
                if pin.cuisine:
                    used_cuisines.append(pin.cuisine)
                used_canonicals |= _recipe_canonicals(pin)
                filled += 1
                continue
```

- [ ] **Step 5: Run the tests and confirm they pass, including the existing pool tests**

Run: `python3 -m pytest diet_planner/tests/test_plan_request_simple.py diet_planner/tests/test_meal_pool.py -q -p no:cacheprovider`
Expected: all pass. If an existing test posts `city` and `country`, it still passes, because the fields are only optional now.

- [ ] **Step 6: Commit**

```bash
git add diet_planner/schemas.py diet_planner/views.py diet_planner/models/core.py diet_planner/migrations/0045_goal_pinned_recipes.py diet_planner/services/recipe_retrieval.py diet_planner/tests/test_plan_request_simple.py
git commit -m "feat(plan): no city/country needed; picked recipes fill the pool first"
```

---

### Task 11: One free allowance per person at signup

**Files:**
- Create: `login_app/email_rules.py`
- Create: `login_app/data/disposable_domains.txt`
- Modify: `login_app/views.py` (`RegistrationView`, around lines 148-190)
- Test: `login_app/test_email_rules.py`

- [ ] **Step 1: Write the failing test**

```python
# login_app/test_email_rules.py
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from login_app.email_rules import is_disposable, normalise_email


class EmailRulesTest(SimpleTestCase):
    def test_gmail_dots_and_plus_collapse(self):
        self.assertEqual(normalise_email('J.An+uvarto@GMail.com'), 'jan@gmail.com')
        self.assertEqual(normalise_email('jan@googlemail.com'), 'jan@gmail.com')

    def test_other_domains_keep_dots_but_drop_plus(self):
        self.assertEqual(normalise_email('J.An+x@Seznam.cz'), 'j.an@seznam.cz')

    def test_disposable(self):
        self.assertTrue(is_disposable('a@mailinator.com'))
        self.assertTrue(is_disposable('a@10minutemail.com'))
        self.assertFalse(is_disposable('a@seznam.cz'))


class RegistrationRulesTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def _register(self, username, email):
        return self.client.post('/api/auth/register/', {
            'username': username, 'email': email,
            'password': 'heslo1234', 'passwordConfirm': 'heslo1234'}, format='json')

    def test_alias_of_existing_gmail_is_rejected(self):
        get_user_model().objects.create(username='first', email='jan@gmail.com')
        resp = self._register('second', 'j.an+2@gmail.com')
        self.assertEqual(resp.status_code, 400)

    def test_disposable_is_rejected(self):
        resp = self._register('throwaway', 'x@mailinator.com')
        self.assertEqual(resp.status_code, 400)
```

Check the registration route first with `grep -n "register" login_app/urls.py llm_diet_planner_project/urls.py`. If it isn't `/api/auth/register/`, use the real prefix in the test.

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest login_app/test_email_rules.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: login_app.email_rules`.

- [ ] **Step 3: Implement the rules**

Create `login_app/data/disposable_domains.txt`, one domain per line:

```
mailinator.com
10minutemail.com
guerrillamail.com
sharklasers.com
temp-mail.org
tempmail.com
yopmail.com
trashmail.com
getnada.com
dispostable.com
maildrop.cc
throwawaymail.com
fakeinbox.com
emailondeck.com
mohmal.com
```

```python
# login_app/email_rules.py
"""One free allowance per person (spec 2026-11-03): collapse address aliases
and refuse throwaway inboxes at registration."""
from functools import lru_cache
from pathlib import Path

_GMAIL = {'gmail.com', 'googlemail.com'}


def normalise_email(email: str) -> str:
    email = (email or '').strip().lower()
    if '@' not in email:
        return email
    local, domain = email.rsplit('@', 1)
    local = local.split('+', 1)[0]
    if domain in _GMAIL:
        local = local.replace('.', '')
        domain = 'gmail.com'
    return f'{local}@{domain}'


@lru_cache(maxsize=1)
def _disposable() -> frozenset:
    path = Path(__file__).parent / 'data' / 'disposable_domains.txt'
    return frozenset(line.strip().lower() for line in path.read_text().splitlines() if line.strip())


def is_disposable(email: str) -> bool:
    domain = (email or '').rsplit('@', 1)[-1].strip().lower()
    return domain in _disposable()


def normalised_email_taken(email: str) -> bool:
    from django.contrib.auth import get_user_model
    target = normalise_email(email)
    domain = target.rsplit('@', 1)[-1]
    candidates = get_user_model().objects.filter(email__iendswith='@' + domain) if domain != 'gmail.com' \
        else get_user_model().objects.filter(email__iregex=r'@(gmail|googlemail)\.com$')
    return any(normalise_email(u.email) == target for u in candidates.only('email'))
```

- [ ] **Step 4: Use it in `RegistrationView`**

In `login_app/views.py`, add the import `from login_app.email_rules import is_disposable, normalised_email_taken` at the top.

In `RegistrationView`, set `throttle_scope = 'signup'`. If the class has no `throttle_classes`, also add `throttle_classes = [ScopedRateThrottle]`.

Replace the existing check `if User.objects.filter(email=schema.email).exists():` with:

```python
            if is_disposable(schema.email):
                return Response(
                    {"status": "error", "error": "Na tenhle e-mail se registrovat nedá. Použij prosím svůj běžný e-mail."},
                    status=status.HTTP_400_BAD_REQUEST)
            if User.objects.filter(email=schema.email).exists() or normalised_email_taken(schema.email):
```

Keep the body of the original `if` block, the existing duplicate-email response, unchanged.

- [ ] **Step 5: Run the tests and confirm they pass, including existing login tests**

Run: `python3 -m pytest login_app -q -p no:cacheprovider`
Expected: the new tests pass, and the pre-existing failure count in `login_app` is unchanged (memory: login_app has 10 known failures quarantined in CI). Compare against the same command on `develop` if needed.

- [ ] **Step 6: Commit**

```bash
git add login_app/email_rules.py login_app/data/disposable_domains.txt login_app/views.py login_app/test_email_rules.py
git commit -m "feat(auth): one free allowance per person: alias-aware email, no throwaway inboxes"
```

---

### Task 12: Repair wrong stored photo categories

**Files:**
- Create: `diet_planner/management/commands/recategorize_recipe_images.py`
- Test: `diet_planner/tests/test_recategorize_recipe_images.py`

Background: `guess_category` already returns `kure` for "Kuře Hasselback Primavera" and "Tradiční kuře na paprice" (verified 2026-11-03), but prod `Recipe.food_category` stores `mlete-maso` and `polevka` for them. These are stale rows. Per-dish images still win.

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_recategorize_recipe_images.py
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import DietaryGoal, Recipe


class RecategorizeTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username='c')
        goal = DietaryGoal.objects.create(user=user, prompt='x', country='CZ', currency='CZK', language_code='cs')
        self.r = Recipe.objects.create(dietary_goal=goal, meal_identifier='1:dinner:0', name='Kuře Hasselback Primavera',
                                       food_category='mlete-maso', ingredients=[], instructions=[])

    def test_dry_run_changes_nothing(self):
        out = StringIO()
        call_command('recategorize_recipe_images', stdout=out)
        self.r.refresh_from_db()
        self.assertEqual(self.r.food_category, 'mlete-maso')
        self.assertIn('mlete-maso -> kure', out.getvalue())

    def test_apply_fixes(self):
        call_command('recategorize_recipe_images', '--apply', stdout=StringIO())
        self.r.refresh_from_db()
        self.assertEqual(self.r.food_category, 'kure')
```

If `Recipe.objects.create` needs more required fields, copy the `create` call from `diet_planner/tests/test_public_recipe_list_payload.py:setUp`, which is known to work, and keep `name` and `food_category` as above.

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest diet_planner/tests/test_recategorize_recipe_images.py -q -p no:cacheprovider`
Expected: FAIL with `Unknown command`.

- [ ] **Step 3: Implement**

```python
# diet_planner/management/commands/recategorize_recipe_images.py
"""Re-derive Recipe.food_category with today's guess_category.

Dry run by default; --apply writes. Prints `<id> <name>: old -> new` per change
so the run doubles as its own reversal record.
"""
from django.core.management.base import BaseCommand

from diet_planner.food_categories import guess_category
from diet_planner.models import Recipe


class Command(BaseCommand):
    help = 'Fix stale Recipe.food_category values (wrong stock photo).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, apply=False, **opts):
        changed = 0
        for r in Recipe.objects.only('id', 'name', 'food_category', 'ingredients').iterator():
            new = guess_category(r.name, r.ingredients or [])
            if new and new != r.food_category:
                changed += 1
                self.stdout.write(f'{r.id} {r.name}: {r.food_category} -> {new}')
                if apply:
                    Recipe.objects.filter(pk=r.pk).update(food_category=new)
        self.stdout.write(f"{'Applied' if apply else 'Dry run'}: {changed} change(s).")
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python3 -m pytest diet_planner/tests/test_recategorize_recipe_images.py -q -p no:cacheprovider`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/recategorize_recipe_images.py diet_planner/tests/test_recategorize_recipe_images.py
git commit -m "feat(images): command to repair stale recipe photo categories"
```

Prod run (owner, after deploy, through the prod console harness): first `recategorize_recipe_images`, review the list, then `--apply`. Save the printed output to `docs/qa/` as the reversal record.

---

### Task 13: Full backend gate

- [ ] **Step 1: Run the whole CI backend suite**

Run: `python3 -m pytest diet_planner billing analytics login_app social -q -p no:cacheprovider` (about 15 minutes on the dev droplet; it needs a local Redis on 6379 for Celery task tests, e.g. `docker run --rm -d --name t-redis -p 127.0.0.1:6379:6379 redis:7-alpine`)
Expected: everything passes except the known quarantined `login_app` failures.

- [ ] **Step 2: Check migrations**

Run: `python3 manage.py makemigrations --check --dry-run`
Expected: `No changes detected`.

- [ ] **Step 3: Commit any fixes, then hand over to the frontend plan.**
