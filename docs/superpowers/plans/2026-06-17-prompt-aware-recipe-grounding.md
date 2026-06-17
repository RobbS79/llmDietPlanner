# Prompt-aware Recipe Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `overlay_curated_recipes` respect the user's free-text prompt, so a curated recipe replaces the (already prompt-aware) LLM meal only when it genuinely fits the request — otherwise the generated meal stays.

**Architecture:** One Gemini call per plan turns the free-text prompt into structured `PromptFacets` (cuisines / wanted+avoided ingredients / styles / emphases). Recipe selection then applies those facets as **hard gates** (cuisine + wanted/avoided ingredients) plus **soft rank** bonuses. Slots with no facet-eligible recipe are left generated — that is the coherence fallback. Parsed facets + coverage are persisted to a new `DietaryPlan.grounding_debug` field for debuggability. No new infra (no pgvector).

**Tech Stack:** Django 5.1, Python 3.11, `google.generativeai` (Gemini 2.5 Flash), Django test runner, Postgres (dev: local `db` container), Docker Compose (`docker-compose` standalone binary on the dev droplet).

**Spec:** `docs/superpowers/specs/2026-06-17-prompt-aware-recipe-grounding-design.md`

---

## Environment & test command (read first)

This repo runs in Docker. There is **no local venv**; tests run inside the `web`
image against the local `db` container. The committed image is stale (missing
`django-otp`, `stripe`, etc.), so **Task 0 rebuilds it once**. After that, the
canonical test command is:

```bash
cd /opt/llmDietPlanner
PGPW=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)
docker-compose run --rm --no-deps \
  -e DATABASE_URL="postgresql://postgres:${PGPW}@db:5432/llm_diet_planner" \
  web python manage.py test <TEST_TARGET> -v2
```

Throughout this plan, **“Run: TESTCMD <target>”** means substitute `<target>`
into the command above. Use `docker-compose` (with hyphen), **not** `docker
compose` — the v2 plugin is not installed here.

**File-structure map (Part 2):**

| File | Responsibility |
|------|----------------|
| `diet_planner/services/prompt_facets.py` (new) | `PromptFacets` dataclass + `extract_prompt_facets` (LLM → facets). Dependency-free; takes `cuisine_vocab` as an argument so it never imports `recipe_retrieval`. |
| `diet_planner/services/recipe_retrieval.py` (modify) | `published_cuisine_vocab`, `recipe_matches_facets` hard gate, facet params on `eligible_recipes_for_slot` / `score_recipe` / `select_recipes_for_plan`, facet extraction + `facets` in `overlay_curated_recipes`'s return. |
| `diet_planner/models/core.py` (modify) | `DietaryPlan.grounding_debug` JSONField. |
| `diet_planner/tasks.py` (modify) | Capture overlay `facets`+`coverage` and persist to `grounding_debug` at both create sites. |
| `diet_planner/tests/test_prompt_facets.py` (new) | Unit tests for facet extraction/coercion. |
| `diet_planner/tests/test_recipe_facets.py` (new) | Unit tests for gate/score/select/overlay with facets. |

---

## Task 1: Commit the already-implemented prompt-surfacing change (Part 1)

Part 1 (surfacing the user's prompt on the plan page) is already implemented and
verified in the working tree but uncommitted. Commit it first so history is clean.

**Files (already modified in working tree):**
- Modify: `diet_planner/serializers.py` (added `prompt` + `dietary_restrictions` to `DietaryGoalDetailSerializer` fields + read_only_fields)
- Create: `diet_planner/tests/test_goal_detail_serializer.py`
- Modify: `frontend/src/pages/PlanView.tsx` (added "Vaše zadání" panel)

- [ ] **Step 1: Confirm the working-tree diff is exactly these three files**

Run:
```bash
cd /opt/llmDietPlanner && git status --short
```
Expected: `M diet_planner/serializers.py`, `?? diet_planner/tests/test_goal_detail_serializer.py`, `M frontend/src/pages/PlanView.tsx` (plus pre-existing unrelated changes from before this branch — leave those alone).

- [ ] **Step 2: Run the Part 1 backend test**

Run: TESTCMD `diet_planner.tests.test_goal_detail_serializer`
Expected: `Ran 3 tests ... OK`

- [ ] **Step 3: Typecheck the frontend**

Run:
```bash
cd /opt/llmDietPlanner/frontend && node_modules/.bin/tsc --noEmit; echo "exit=$?"
```
Expected: `exit=0`

- [ ] **Step 4: Commit Part 1**

```bash
cd /opt/llmDietPlanner
git add diet_planner/serializers.py diet_planner/tests/test_goal_detail_serializer.py frontend/src/pages/PlanView.tsx
git commit -m "feat(plan): surface the user's prompt + restrictions on the plan page

DietaryGoalDetailSerializer now exposes the decrypted prompt and
dietary_restrictions (read-only); PlanView renders a 'Vaše zadání' panel.
Encryption-at-rest is unchanged (decrypt-on-read for the goal owner).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 0: Rebuild the dev web image so tests run with current deps

**Files:** none (infrastructure).

- [ ] **Step 1: Rebuild the web image**

Run:
```bash
cd /opt/llmDietPlanner && docker-compose build web
```
Expected: build completes (`Successfully built` / `Built`). Takes a few minutes.

- [ ] **Step 2: Smoke-test that Django boots in the rebuilt image**

Run: TESTCMD `diet_planner.tests.test_recipe_retrieval`
Expected: the existing recipe-retrieval suite runs and ends `OK` (no `ModuleNotFoundError`).

---

## Task 2: `PromptFacets` dataclass + `_coerce_facets`

Create the dependency-free facet module with the data type and a pure coercion
helper that normalizes a raw dict (as the LLM would return) into a `PromptFacets`,
filtering cuisines to the supplied vocabulary.

**Files:**
- Create: `diet_planner/services/prompt_facets.py`
- Test: `diet_planner/tests/test_prompt_facets.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_prompt_facets.py`:
```python
from django.test import SimpleTestCase

from diet_planner.services.prompt_facets import PromptFacets, _coerce_facets


class CoerceFacetsTest(SimpleTestCase):
    VOCAB = ['czech', 'italian', 'asian']

    def test_normalizes_and_filters_cuisine_to_vocab(self):
        facets = _coerce_facets(
            {'cuisines': ['Italian', 'klingon'], 'wanted_ingredients': ['Chicken']},
            cuisine_vocab=self.VOCAB,
        )
        self.assertEqual(facets.cuisines, {'italian'})          # klingon dropped
        self.assertEqual(facets.wanted_ingredients, {'chicken'})  # lowercased

    def test_missing_keys_yield_empty_sets(self):
        facets = _coerce_facets({}, cuisine_vocab=self.VOCAB)
        self.assertTrue(facets.is_empty())

    def test_non_list_values_are_ignored(self):
        facets = _coerce_facets(
            {'cuisines': 'italian', 'avoided_ingredients': None, 'styles': ['quick']},
            cuisine_vocab=self.VOCAB,
        )
        self.assertEqual(facets.cuisines, set())     # string, not list -> ignored
        self.assertEqual(facets.avoided_ingredients, set())
        self.assertEqual(facets.styles, {'quick'})

    def test_to_debug_is_sorted_lists(self):
        facets = _coerce_facets(
            {'emphases': ['high_protein'], 'cuisines': ['asian', 'italian']},
            cuisine_vocab=self.VOCAB,
        )
        self.assertEqual(
            facets.to_debug(),
            {
                'cuisines': ['asian', 'italian'],
                'wanted_ingredients': [],
                'avoided_ingredients': [],
                'styles': [],
                'emphases': ['high_protein'],
            },
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: TESTCMD `diet_planner.tests.test_prompt_facets`
Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.prompt_facets'`.

- [ ] **Step 3: Write minimal implementation**

Create `diet_planner/services/prompt_facets.py`:
```python
"""
Free-text prompt -> structured PromptFacets, used to make recipe grounding
prompt-aware (see docs/superpowers/specs/2026-06-17-prompt-aware-recipe-grounding-design.md).

This module is intentionally dependency-free w.r.t. recipe_retrieval: it takes
`cuisine_vocab` as an argument so the caller (recipe_retrieval.overlay) owns the
corpus lookup and no import cycle is created.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class PromptFacets:
    cuisines: Set[str] = field(default_factory=set)
    wanted_ingredients: Set[str] = field(default_factory=set)
    avoided_ingredients: Set[str] = field(default_factory=set)
    styles: Set[str] = field(default_factory=set)
    emphases: Set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not (
            self.cuisines or self.wanted_ingredients or self.avoided_ingredients
            or self.styles or self.emphases
        )

    def to_debug(self) -> dict:
        return {
            'cuisines': sorted(self.cuisines),
            'wanted_ingredients': sorted(self.wanted_ingredients),
            'avoided_ingredients': sorted(self.avoided_ingredients),
            'styles': sorted(self.styles),
            'emphases': sorted(self.emphases),
        }


def _clean_list(value) -> Set[str]:
    """Lowercase + strip a list of strings; non-lists become empty."""
    if not isinstance(value, list):
        return set()
    return {str(v).strip().lower() for v in value if str(v).strip()}


def _coerce_facets(data: dict, *, cuisine_vocab: List[str]) -> PromptFacets:
    """Pure: turn a raw dict into PromptFacets, filtering cuisines to vocab."""
    vocab = {c.strip().lower() for c in (cuisine_vocab or [])}
    if not isinstance(data, dict):
        return PromptFacets()
    return PromptFacets(
        cuisines=_clean_list(data.get('cuisines')) & vocab,
        wanted_ingredients=_clean_list(data.get('wanted_ingredients')),
        avoided_ingredients=_clean_list(data.get('avoided_ingredients')),
        styles=_clean_list(data.get('styles')),
        emphases=_clean_list(data.get('emphases')),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: TESTCMD `diet_planner.tests.test_prompt_facets`
Expected: `Ran 4 tests ... OK`

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/services/prompt_facets.py diet_planner/tests/test_prompt_facets.py
git commit -m "feat(grounding): PromptFacets dataclass + _coerce_facets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `extract_prompt_facets` with injectable LLM call

Add the LLM-backed extractor. The actual Gemini call is a `generate` callable
defaulting to a real implementation, so tests inject a fake and run offline. Any
failure (bad JSON, exception, empty prompt) returns empty facets — no raise.

**Files:**
- Modify: `diet_planner/services/prompt_facets.py`
- Test: `diet_planner/tests/test_prompt_facets.py`

- [ ] **Step 1: Write the failing test (append to the test file)**

Append to `diet_planner/tests/test_prompt_facets.py`:
```python
from diet_planner.services.prompt_facets import extract_prompt_facets


class ExtractPromptFacetsTest(SimpleTestCase):
    VOCAB = ['czech', 'italian', 'asian']

    def test_parses_json_and_maps_vocab(self):
        def fake_generate(system_prompt, user_text):
            return '{"cuisines": ["italian"], "wanted_ingredients": ["chicken"], "emphases": ["high_protein"]}'

        facets = extract_prompt_facets(
            'rychlé italské večeře s kuřecím, hodně bílkovin',
            language='cs', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertEqual(facets.cuisines, {'italian'})
        self.assertEqual(facets.wanted_ingredients, {'chicken'})
        self.assertEqual(facets.emphases, {'high_protein'})

    def test_strips_markdown_code_fence(self):
        def fake_generate(system_prompt, user_text):
            return '```json\n{"cuisines": ["asian"]}\n```'

        facets = extract_prompt_facets(
            'asian food', language='en', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertEqual(facets.cuisines, {'asian'})

    def test_empty_prompt_returns_empty_without_calling_llm(self):
        calls = []

        def fake_generate(system_prompt, user_text):
            calls.append(1)
            return '{}'

        facets = extract_prompt_facets(
            '   ', language='cs', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertTrue(facets.is_empty())
        self.assertEqual(calls, [])  # short-circuited, no LLM call

    def test_garbage_output_returns_empty(self):
        def fake_generate(system_prompt, user_text):
            return 'not json at all'

        facets = extract_prompt_facets(
            'whatever', language='en', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertTrue(facets.is_empty())

    def test_generate_exception_returns_empty(self):
        def fake_generate(system_prompt, user_text):
            raise RuntimeError('LLM down')

        facets = extract_prompt_facets(
            'whatever', language='en', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertTrue(facets.is_empty())
```

- [ ] **Step 2: Run test to verify it fails**

Run: TESTCMD `diet_planner.tests.test_prompt_facets.ExtractPromptFacetsTest`
Expected: FAIL — `ImportError: cannot import name 'extract_prompt_facets'`.

- [ ] **Step 3: Write minimal implementation (append to `prompt_facets.py`)**

Append to `diet_planner/services/prompt_facets.py`:
```python
_SYSTEM_PROMPT_TEMPLATE = (
    "You extract structured facets from a user's free-text meal-plan request. "
    "Return ONLY a JSON object with these keys (all arrays of short lowercase "
    "strings, omit or use [] when unsure):\n"
    '  "cuisines": choose only from this exact list: {vocab};\n'
    '  "wanted_ingredients": key ingredients the user explicitly wants;\n'
    '  "avoided_ingredients": ingredients the user wants to avoid (beyond allergies);\n'
    '  "styles": e.g. quick, comfort, light;\n'
    '  "emphases": choose from high_protein, low_carb, low_calorie, budget.\n'
    "Do not invent cuisines outside the provided list. No prose, JSON only."
)


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith('```'):
        t = t.split('\n', 1)[-1] if '\n' in t else t
        if t.endswith('```'):
            t = t[: -3]
        if t.lstrip().startswith('json'):
            t = t.lstrip()[4:]
    return t.strip()


def _default_generate(system_prompt: str, user_text: str) -> str:
    import google.generativeai as genai
    from django.conf import settings

    genai.configure(api_key=getattr(settings, 'GEMINI_API_KEY', None))
    model = genai.GenerativeModel(
        model_name=getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash'),
        system_instruction=system_prompt,
    )
    resp = model.generate_content(user_text)
    return getattr(resp, 'text', '') or ''


def extract_prompt_facets(
    prompt: Optional[str],
    *,
    language: str,
    cuisine_vocab: List[str],
    generate: Optional[Callable[[str, str], str]] = None,
) -> PromptFacets:
    """Extract PromptFacets from free text. Never raises: any failure -> empty."""
    if not prompt or not prompt.strip():
        return PromptFacets()
    gen = generate or _default_generate
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(vocab=', '.join(cuisine_vocab) or '(none)')
    try:
        raw = gen(system_prompt, f"Language: {language}\nRequest: {prompt.strip()}")
        data = json.loads(_strip_code_fence(raw))
        return _coerce_facets(data, cuisine_vocab=cuisine_vocab)
    except Exception as exc:  # noqa: BLE001 - defensive by design
        logger.warning("Prompt facet extraction failed, using empty facets: %s", exc)
        return PromptFacets()
```

- [ ] **Step 4: Run test to verify it passes**

Run: TESTCMD `diet_planner.tests.test_prompt_facets`
Expected: `Ran 9 tests ... OK` (4 from Task 2 + 5 here).

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/services/prompt_facets.py diet_planner/tests/test_prompt_facets.py
git commit -m "feat(grounding): extract_prompt_facets (LLM facet extraction, defensive)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `published_cuisine_vocab` + `recipe_matches_facets` hard gate

Add the corpus-vocabulary helper and the hard gate in `recipe_retrieval.py`.

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py`
- Test: `diet_planner/tests/test_recipe_facets.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_recipe_facets.py`:
```python
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.services.recipe_retrieval import (
    published_cuisine_vocab,
    recipe_matches_facets,
)


def _recipe(**kw):
    defaults = dict(
        name_cs='Test', slug=kw.get('slug', 'test'),
        meal_types=['dinner'], cuisine='italian',
        dietary_tags=[], status=CuratedRecipe.Status.PUBLISHED,
        ingredients=[{'name': 'Chicken breast', 'canonical': 'chicken', 'quantity': 200, 'unit': 'g'}],
        instructions=[{'text': 'cook'}], base_nutrition={'calories': 500},
        source_url='https://example.com/r', source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class RecipeMatchesFacetsTest(TestCase):
    def test_empty_facets_match_everything(self):
        r = _recipe(slug='a')
        self.assertTrue(recipe_matches_facets(r, PromptFacets()))

    def test_cuisine_in_set_passes(self):
        r = _recipe(slug='b', cuisine='italian')
        self.assertTrue(recipe_matches_facets(r, PromptFacets(cuisines={'italian'})))

    def test_cuisine_not_in_set_blocked(self):
        r = _recipe(slug='c', cuisine='asian')
        self.assertFalse(recipe_matches_facets(r, PromptFacets(cuisines={'italian'})))

    def test_cuisineless_recipe_blocked_when_cuisine_demanded(self):
        r = _recipe(slug='d', cuisine='')
        self.assertFalse(recipe_matches_facets(r, PromptFacets(cuisines={'italian'})))

    def test_wanted_ingredient_hit_passes(self):
        r = _recipe(slug='e')  # has canonical 'chicken'
        self.assertTrue(recipe_matches_facets(r, PromptFacets(wanted_ingredients={'chicken'})))

    def test_wanted_ingredient_miss_blocked(self):
        r = _recipe(slug='f')
        self.assertFalse(recipe_matches_facets(r, PromptFacets(wanted_ingredients={'tofu'})))

    def test_avoided_ingredient_present_blocked(self):
        r = _recipe(slug='g')  # name 'Chicken breast'
        self.assertFalse(recipe_matches_facets(r, PromptFacets(avoided_ingredients={'chicken'})))

    def test_published_cuisine_vocab_distinct_nonempty_lower(self):
        _recipe(slug='h', cuisine='Italian')
        _recipe(slug='i', cuisine='asian')
        _recipe(slug='j', cuisine='')
        self.assertEqual(published_cuisine_vocab(), ['asian', 'italian'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: TESTCMD `diet_planner.tests.test_recipe_facets`
Expected: FAIL — `ImportError: cannot import name 'recipe_matches_facets'`.

- [ ] **Step 3: Write minimal implementation**

In `diet_planner/services/recipe_retrieval.py`, add the import near the top
(after the existing `from diet_planner.models import CuratedRecipe`):
```python
from diet_planner.services.prompt_facets import PromptFacets, extract_prompt_facets
```

Then add these functions (place them just after `published_pool`):
```python
def published_cuisine_vocab(
    *,
    status: str = CuratedRecipe.Status.PUBLISHED,
    pool: Optional[List[CuratedRecipe]] = None,
) -> List[str]:
    """Sorted distinct non-empty cuisines (lowercased) among published recipes."""
    recipes = pool if pool is not None else published_pool(status)
    return sorted({(r.cuisine or '').strip().lower() for r in recipes} - {''})


def _recipe_ingredient_tokens(recipe: CuratedRecipe) -> Set[str]:
    """Lowercased canonical + name tokens for ingredient matching."""
    tokens: Set[str] = set()
    for ing in (recipe.ingredients or []):
        for key in ('canonical', 'name'):
            val = ing.get(key)
            if val:
                tokens.add(str(val).strip().lower())
    return tokens


def _ingredient_present(needle: str, tokens: Set[str]) -> bool:
    return any(needle in tok for tok in tokens)


def recipe_matches_facets(recipe: CuratedRecipe, facets: PromptFacets) -> bool:
    """Hard gate. Only non-empty facet sets constrain eligibility."""
    if facets.cuisines:
        cuisine = (recipe.cuisine or '').strip().lower()
        if not cuisine or cuisine not in facets.cuisines:
            return False

    tokens = _recipe_ingredient_tokens(recipe)
    if facets.wanted_ingredients:
        if not any(_ingredient_present(w, tokens) for w in facets.wanted_ingredients):
            return False
    if facets.avoided_ingredients:
        if any(_ingredient_present(a, tokens) for a in facets.avoided_ingredients):
            return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: TESTCMD `diet_planner.tests.test_recipe_facets`
Expected: `Ran 8 tests ... OK`

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_recipe_facets.py
git commit -m "feat(grounding): published_cuisine_vocab + recipe_matches_facets hard gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Thread facets through eligibility + scoring + selection

Wire the gate into `eligible_recipes_for_slot`, add soft bonuses to
`score_recipe`, and pass `facets` through `select_recipes_for_plan`. Defaults
keep `facets=None` (or empty) → identical legacy behavior.

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py`
- Test: `diet_planner/tests/test_recipe_facets.py`

- [ ] **Step 1: Write the failing test (append)**

Append to `diet_planner/tests/test_recipe_facets.py`:
```python
from diet_planner.services.recipe_retrieval import (
    eligible_recipes_for_slot,
    score_recipe,
    select_recipes_for_plan,
)


class FacetSelectionTest(TestCase):
    def _goal(self, **kw):
        # Lightweight stand-in: select_recipes_for_plan only reads attributes.
        class G:
            pass
        g = G()
        g.dietary_restrictions = kw.get('dietary_restrictions')
        g.num_days = kw.get('num_days', 1)
        g.small_meals_per_day = 0
        g.snacks_per_day = 0
        g.breakfast = False
        g.lunch = False
        g.dinner = True
        return g

    def test_eligible_excludes_off_cuisine_when_facets_given(self):
        _recipe(slug='ital', cuisine='italian')
        _recipe(slug='asia', cuisine='asian')
        facets = PromptFacets(cuisines={'italian'})
        eligible = eligible_recipes_for_slot('dinner', set(), facets=facets)
        slugs = {r.slug for r in eligible}
        self.assertEqual(slugs, {'ital'})

    def test_eligible_unconstrained_without_facets(self):
        _recipe(slug='ital2', cuisine='italian')
        _recipe(slug='asia2', cuisine='asian')
        eligible = eligible_recipes_for_slot('dinner', set())
        self.assertEqual(len({r.slug for r in eligible}), 2)

    def test_score_rewards_emphasis_match(self):
        plain = _recipe(slug='plain', dietary_tags=[])
        proteiny = _recipe(slug='prot', dietary_tags=['high_protein'])
        facets = PromptFacets(emphases={'high_protein'})
        s_plain = score_recipe(plain, used_recipe_ids=set(), used_cuisines=[], facets=facets)
        s_prot = score_recipe(proteiny, used_recipe_ids=set(), used_cuisines=[], facets=facets)
        self.assertGreater(s_prot, s_plain)

    def test_select_leaves_slot_uncovered_when_no_facet_match(self):
        _recipe(slug='only-asian', cuisine='asian')
        goal = self._goal()
        result = select_recipes_for_plan(goal, facets=PromptFacets(cuisines={'italian'}))
        self.assertEqual(result['coverage']['filled'], 0)        # nothing italian -> uncovered
        self.assertEqual(result['days'][0]['slots'], {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: TESTCMD `diet_planner.tests.test_recipe_facets.FacetSelectionTest`
Expected: FAIL — `TypeError: eligible_recipes_for_slot() got an unexpected keyword argument 'facets'`.

- [ ] **Step 3: Write minimal implementation**

In `recipe_retrieval.py`, change `eligible_recipes_for_slot` to accept and apply
facets. Update its signature and add the gate after the existing checks:
```python
def eligible_recipes_for_slot(
    slot: str,
    required_tags: Set[str],
    *,
    pool: Optional[List[CuratedRecipe]] = None,
    status: str = CuratedRecipe.Status.PUBLISHED,
    exclude_ids: Optional[Set[int]] = None,
    facets: Optional[PromptFacets] = None,
) -> List[CuratedRecipe]:
    """Recipes that pass the HARD GATE for one slot (incl. prompt facets)."""
    meal_type = _SLOT_TO_MEAL_TYPE.get(slot, slot)
    candidates = pool if pool is not None else published_pool(status)
    exclude_ids = exclude_ids or set()

    out: List[CuratedRecipe] = []
    for r in candidates:
        if r.id in exclude_ids:
            continue
        if meal_type not in (r.meal_types or []):
            continue
        if not required_tags.issubset(set(r.dietary_tags or [])):
            continue
        if not r.is_catalog_mapped():
            continue
        if facets is not None and not recipe_matches_facets(r, facets):
            continue
        out.append(r)
    return out
```

Add a `facets` param + soft bonuses to `score_recipe` (append the bonus block
before `return score`):
```python
def score_recipe(
    recipe: CuratedRecipe,
    *,
    used_recipe_ids: Set[int],
    used_cuisines: Sequence[str],
    target_calories: Optional[float] = None,
    facets: Optional[PromptFacets] = None,
) -> float:
    """Soft-ranking score; higher is better."""
    score = 0.0

    if recipe.id in used_recipe_ids:
        score -= 100.0
    if recipe.cuisine and recipe.cuisine in used_cuisines:
        score -= 5.0 * list(used_cuisines).count(recipe.cuisine)

    if recipe.difficulty == CuratedRecipe.Difficulty.EASY:
        score += 2.0

    score += min(recipe.usage_count, 10) * 0.1

    if target_calories:
        base_cal = (recipe.base_nutrition or {}).get('calories')
        if base_cal:
            rel = abs(base_cal - target_calories) / target_calories
            score += max(0.0, 3.0 * (1.0 - rel))

    if facets is not None:
        tokens = _recipe_ingredient_tokens(recipe)
        wanted_hits = sum(1 for w in facets.wanted_ingredients if _ingredient_present(w, tokens))
        score += 0.5 * wanted_hits
        tags = set(recipe.dietary_tags or [])
        score += 1.0 * len(facets.emphases & tags)
        if 'quick' in facets.styles and recipe.total_time and recipe.total_time <= 20:
            score += 1.0

    return score
```

In `select_recipes_for_plan`, add the `facets` parameter and thread it through:
```python
def select_recipes_for_plan(
    goal: Any,
    *,
    status: str = CuratedRecipe.Status.PUBLISHED,
    facets: Optional[PromptFacets] = None,
) -> Dict[str, Any]:
```
Inside the per-slot loop, pass `facets` to both calls:
```python
            candidates = eligible_recipes_for_slot(slot_type, required_tags, pool=pool, facets=facets)
            if not candidates:
                continue
            best = max(candidates, key=lambda r: score_recipe(
                r, used_recipe_ids=used_recipe_ids, used_cuisines=used_cuisines,
                facets=facets,
            ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: TESTCMD `diet_planner.tests.test_recipe_facets`
Expected: `Ran 12 tests ... OK`

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_recipe_facets.py
git commit -m "feat(grounding): thread prompt facets through eligibility/score/select

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `overlay_curated_recipes` extracts facets once + returns them

Make the overlay extract facets from `goal.prompt` (once) and include the parsed
facets in its return value. Keep behavior identical when grounding finds no
match (slot stays generated).

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py`
- Test: `diet_planner/tests/test_recipe_facets.py`

- [ ] **Step 1: Write the failing test (append)**

Append to `diet_planner/tests/test_recipe_facets.py`:
```python
from diet_planner.services.recipe_retrieval import overlay_curated_recipes


class OverlayFacetsTest(TestCase):
    def _goal(self, prompt):
        class G:
            pass
        g = G()
        g.prompt = prompt
        g.dietary_restrictions = None
        g.language_code = 'cs'
        g.num_days = 1
        g.small_meals_per_day = 0
        g.snacks_per_day = 0
        g.breakfast = False
        g.lunch = False
        g.dinner = True
        return g

    def _days(self):
        return [{'day_number': 1, 'dinner': {'name': 'LLM dinner', 'meal_identifier': 'd1-dinner'}}]

    def test_keeps_generated_meal_when_no_facet_match(self):
        _recipe(slug='asian-only', cuisine='asian')

        def fake_extract(prompt, *, language, cuisine_vocab, generate=None):
            return PromptFacets(cuisines={'italian'})

        import diet_planner.services.recipe_retrieval as rr
        orig = rr.extract_prompt_facets
        rr.extract_prompt_facets = fake_extract
        try:
            result = overlay_curated_recipes(self._days(), self._goal('italské'))
        finally:
            rr.extract_prompt_facets = orig

        dinner = result['days'][0]['dinner']
        self.assertEqual(dinner['name'], 'LLM dinner')          # not swapped
        self.assertEqual(dinner['source'], 'generated')
        self.assertEqual(result['coverage']['filled'], 0)
        self.assertEqual(result['facets']['cuisines'], ['italian'])

    def test_swaps_when_facet_eligible(self):
        _recipe(slug='ital-dinner', cuisine='italian', name_cs='Těstoviny')

        def fake_extract(prompt, *, language, cuisine_vocab, generate=None):
            return PromptFacets(cuisines={'italian'})

        import diet_planner.services.recipe_retrieval as rr
        orig = rr.extract_prompt_facets
        rr.extract_prompt_facets = fake_extract
        try:
            result = overlay_curated_recipes(self._days(), self._goal('italské'))
        finally:
            rr.extract_prompt_facets = orig

        dinner = result['days'][0]['dinner']
        self.assertEqual(dinner['source'], 'curated')
        self.assertEqual(dinner['name'], 'Těstoviny')
        self.assertEqual(dinner['meal_identifier'], 'd1-dinner')  # preserved
        self.assertEqual(result['coverage']['filled'], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: TESTCMD `diet_planner.tests.test_recipe_facets.OverlayFacetsTest`
Expected: FAIL — `KeyError: 'facets'` (overlay does not yet return facets).

- [ ] **Step 3: Write minimal implementation**

In `recipe_retrieval.py`, update `overlay_curated_recipes`:
```python
def overlay_curated_recipes(
    transformed_days: List[Dict[str, Any]],
    goal: Any,
    *,
    status: str = CuratedRecipe.Status.PUBLISHED,
    facets: Optional[PromptFacets] = None,
) -> Dict[str, Any]:
    """Overlay real curated recipes onto facet-eligible slots of an already-
    generated plan. Uncovered/ineligible slots keep their generated meal.
    Returns {'days', 'coverage', 'facets'}.
    """
    if facets is None:
        vocab = published_cuisine_vocab(status=status)
        facets = extract_prompt_facets(
            getattr(goal, 'prompt', '') or '',
            language=getattr(goal, 'language_code', 'cs') or 'cs',
            cuisine_vocab=vocab,
        )

    selection = select_recipes_for_plan(goal, status=status, facets=facets)
    sel_by_day = {d['day_number']: d['slots'] for d in selection['days']}
```
(Leave the rest of the function body unchanged through the `usage_count` bump.)
Change the final `return` from `{'days': ..., 'coverage': ...}` to:
```python
    return {
        'days': transformed_days,
        'coverage': selection['coverage'],
        'facets': facets.to_debug(),
    }
```

> Note: the test monkeypatches `rr.extract_prompt_facets`, so the call inside the
> function must reference the module-level name `extract_prompt_facets` (it does).

- [ ] **Step 4: Run test to verify it passes**

Run: TESTCMD `diet_planner.tests.test_recipe_facets`
Expected: `Ran 14 tests ... OK`

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_recipe_facets.py
git commit -m "feat(grounding): overlay extracts prompt facets once and returns them

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `DietaryPlan.grounding_debug` field + migration

Persist parsed facets + coverage on the plan.

**Files:**
- Modify: `diet_planner/models/core.py` (DietaryPlan, near `discount_optimization`)
- Create: migration (generated)
- Test: `diet_planner/tests/test_recipe_facets.py`

- [ ] **Step 1: Write the failing test (append)**

Append to `diet_planner/tests/test_recipe_facets.py`:
```python
from django.contrib.auth.models import User
from diet_planner.models import DietaryGoal, DietaryPlan


class GroundingDebugFieldTest(TestCase):
    def test_grounding_debug_persists(self):
        user = User.objects.create_user('gd', password='x')
        goal = DietaryGoal.objects.create(
            user=user, prompt='p', country='CZ', city='Prague', num_days=1,
        )
        plan = DietaryPlan.objects.create(
            dietary_goal=goal,
            grounding_debug={'facets': {'cuisines': ['italian']}, 'coverage': {'filled': 1, 'total': 1}},
        )
        plan.refresh_from_db()
        self.assertEqual(plan.grounding_debug['coverage']['filled'], 1)

    def test_grounding_debug_defaults_null(self):
        user = User.objects.create_user('gd2', password='x')
        goal = DietaryGoal.objects.create(
            user=user, prompt='p', country='CZ', city='Prague', num_days=1,
        )
        plan = DietaryPlan.objects.create(dietary_goal=goal)
        self.assertIsNone(plan.grounding_debug)
```

- [ ] **Step 2: Run test to verify it fails**

Run: TESTCMD `diet_planner.tests.test_recipe_facets.GroundingDebugFieldTest`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'grounding_debug'`.

- [ ] **Step 3: Add the field**

In `diet_planner/models/core.py`, inside `class DietaryPlan`, add after the
`discount_optimization_applied` field:
```python
    grounding_debug = models.JSONField(
        null=True,
        blank=True,
        help_text="Recipe-grounding diagnostics: {facets, coverage} for this plan",
    )
```

- [ ] **Step 4: Generate the migration**

Run:
```bash
cd /opt/llmDietPlanner
PGPW=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)
docker-compose run --rm --no-deps \
  -e DATABASE_URL="postgresql://postgres:${PGPW}@db:5432/llm_diet_planner" \
  web python manage.py makemigrations diet_planner
```
Expected: `Migrations for 'diet_planner': ... Add field grounding_debug to dietaryplan`.

- [ ] **Step 5: Run test to verify it passes**

Run: TESTCMD `diet_planner.tests.test_recipe_facets.GroundingDebugFieldTest`
Expected: `Ran 2 tests ... OK`

- [ ] **Step 6: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/models/core.py diet_planner/migrations/
git commit -m "feat(grounding): persist {facets, coverage} on DietaryPlan.grounding_debug

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Persist grounding_debug from both task call sites

Capture the overlay's `facets`+`coverage` and store on the plan at both
`DietaryPlan.objects.create` sites.

**Files:**
- Modify: `diet_planner/tasks.py` (overlay blocks ~1580 & ~2193; create calls ~1764 & ~2274)

- [ ] **Step 1: Update the first flow (catalog-constrained, ~line 1580)**

Change the grounding block so it captures debug info:
```python
        from diet_planner.services.recipe_retrieval import grounding_enabled, overlay_curated_recipes
        grounding_debug = None
        if grounding_enabled():
            result = overlay_curated_recipes(transformed_days, goal)
            transformed_days = result['days']
            cov = result['coverage']
            grounding_debug = {'facets': result['facets'], 'coverage': cov}
            logger.info(f"{log_prefix} Recipe grounding: {cov['filled']}/{cov['total']} slots curated")
```
Then add `grounding_debug=grounding_debug,` to the `DietaryPlan.objects.create(...)`
at ~line 1764 (after `llm_cost_usd=...`).

- [ ] **Step 2: Update the second flow (~line 2193)**

```python
        from diet_planner.services.recipe_retrieval import grounding_enabled, overlay_curated_recipes
        grounding_debug = None
        if grounding_enabled():
            _grounded = overlay_curated_recipes(transformed_days, goal)
            transformed_days = _grounded['days']
            grounding_debug = {'facets': _grounded['facets'], 'coverage': _grounded['coverage']}
            logger.info(
                f"{log_prefix} Recipe grounding: "
                f"{_grounded['coverage']['filled']}/{_grounded['coverage']['total']} slots curated"
            )
```
Then add `grounding_debug=grounding_debug,` to the `DietaryPlan.objects.create(...)`
at ~line 2274 (after `llm_cost_usd=...`).

- [ ] **Step 3: Verify nothing else references the old return shape**

Run:
```bash
cd /opt/llmDietPlanner && grep -n "overlay_curated_recipes\|\['coverage'\]\|\['facets'\]" diet_planner/tasks.py
```
Expected: only the two blocks just edited; both read `['facets']` and `['coverage']`.

- [ ] **Step 4: Run the grounding + tasks-related suites**

Run: TESTCMD `diet_planner.tests.test_recipe_facets diet_planner.tests.test_recipe_retrieval diet_planner.tests.test_plan_completeness`
Expected: all pass, `OK`.

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner
git add diet_planner/tasks.py
git commit -m "feat(grounding): persist grounding_debug from both generation flows

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Full regression + branch wrap-up

**Files:** none (verification).

- [ ] **Step 1: Run the full recipe/plan test surface**

Run: TESTCMD `diet_planner.tests.test_recipe_facets diet_planner.tests.test_prompt_facets diet_planner.tests.test_recipe_retrieval diet_planner.tests.test_recipe_coherence diet_planner.tests.test_plan_completeness diet_planner.tests.test_catalog_constrained diet_planner.tests.test_goal_detail_serializer`
Expected: all pass, `OK`.

- [ ] **Step 2: Confirm the branch is clean and review the log**

Run:
```bash
cd /opt/llmDietPlanner && git status --short && git log --oneline develop..HEAD
```
Expected: clean tree; commits for Part 1, facets module, gate, threading, overlay, model field, tasks wiring.

- [ ] **Step 3: Hand back for review**

Report the coverage/behavior change and offer to open a PR into `develop`
(do not push or open the PR without explicit user approval).

---

## Self-Review notes

- **Spec coverage:** facet extraction (Tasks 2–3), hard gate cuisine+wanted+avoided (Task 4), eligibility/score/select threading (Task 5), overlay extract-once + keep-LLM-meal fallback (Task 6), `grounding_debug` persistence (Tasks 7–8), defensive empties (Task 3), tests incl. regression (Task 9). Part 1 commit (Task 1). All spec sections mapped.
- **Type/name consistency:** `PromptFacets`, `extract_prompt_facets`, `_coerce_facets`, `published_cuisine_vocab`, `recipe_matches_facets`, `_recipe_ingredient_tokens`, `_ingredient_present`, `overlay_curated_recipes(...)→{'days','coverage','facets'}`, `DietaryPlan.grounding_debug` used consistently across tasks.
- **No placeholders:** every code/test/command step is concrete.
