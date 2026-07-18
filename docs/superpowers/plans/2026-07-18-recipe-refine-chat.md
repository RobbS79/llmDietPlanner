# Conversational Recipe Swap ("Refine Chat") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-shot "Vyměnit recept" hint panel with a chat that gathers preferences over up to 8 user messages and previews curated-recipe candidates, committing the swap only when the user accepts one.

**Architecture:** Stateless backend — one new endpoint `POST /recipes/<meal_identifier>/refine/` with a preview mode (one combined Gemini flash call → cumulative facets + Czech follow-up question, then deterministic corpus scoring; **no writes**) and an accept mode (re-validates eligibility, commits via logic shared with `RecipeReplaceView`). Frontend holds all chat state in a component; state is discarded on close. Every candidate is a published `CuratedRecipe` with intact `canonical`/`catalog_id` — the LLM never authors recipe content.

**Tech Stack:** Django 5.1 + DRF, google.generativeai (gemini-2.5-flash), React 18 + TypeScript + @tanstack/react-query, vitest + testing-library, pytest (Django TestCase style).

**Spec:** `docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md`

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `diet_planner/services/refine_chat.py` | Create | Conversation → (PromptFacets, Czech question); message clamping; never-raises |
| `diet_planner/tests/test_refine_chat.py` | Create | Service tests |
| `diet_planner/views.py` | Modify | Extract shared slot/commit helpers from `RecipeReplaceView` (lines 566-700); add `RecipeRefineView` |
| `diet_planner/urls.py` | Modify | Add `recipes/<meal_identifier>/refine/` route (before the recipe-detail catch-all) |
| `diet_planner/tests/test_recipe_refine.py` | Create | Endpoint tests (preview + accept) |
| `frontend/src/lib/refineRecipe.ts` | Create | Typed API client (preview + accept) |
| `frontend/src/lib/refineRecipe.test.ts` | Create | Client tests |
| `frontend/src/components/recipe/RecipeRefineChat.tsx` | Create | Chat panel component (all conversation state) |
| `frontend/src/components/recipe/RecipeRefineChat.test.tsx` | Create | Component tests |
| `frontend/src/pages/RecipePage.tsx` | Modify | Swap hint panel for `RecipeRefineChat`; keep cache-swap/invalidation logic |
| `frontend/src/pages/RecipePage.replace.test.tsx` | Delete | Superseded (tests the removed hint panel) |
| `frontend/src/pages/RecipePage.refine.test.tsx` | Create | Slim page-level integration test |
| `frontend/src/lib/replaceRecipe.ts` + `.test.ts` | Delete | No longer called from the web app (backend `/replace/` endpoint **stays**, still tested) |

Test commands used throughout (match CI):
- Backend: `cd /opt/llmDietPlanner && python -m pytest diet_planner/tests/<file> -v`
- Frontend: `cd /opt/llmDietPlanner/frontend && npx vitest run <file>` and `npx tsc --noEmit`

---

### Task 1: Refine-chat service (conversation → facets + question)

**Files:**
- Create: `diet_planner/services/refine_chat.py`
- Test: `diet_planner/tests/test_refine_chat.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Refine-chat service: conversation -> (PromptFacets, Czech follow-up question).

Never raises: any LLM/parse failure yields (empty facets, None) so the caller
degrades to an unsteered pick.
Spec: docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
"""
from django.test import SimpleTestCase

from diet_planner.services.refine_chat import (
    MAX_TOTAL_MESSAGES,
    MAX_USER_MESSAGES,
    clamp_messages,
    refine_conversation,
)


def msgs(*pairs):
    return [{'role': r, 'text': t} for r, t in pairs]


class ClampMessagesTest(SimpleTestCase):
    def test_drops_malformed_entries_and_trims_text(self):
        raw = [
            {'role': 'user', 'text': 'a' * 900},
            {'role': 'bogus', 'text': 'x'},
            'not-a-dict',
            {'role': 'assistant', 'text': '   '},
            {'role': 'assistant', 'text': 'ok'},
        ]
        clean = clamp_messages(raw)
        self.assertEqual([m['role'] for m in clean], ['user', 'assistant'])
        self.assertEqual(len(clean[0]['text']), 500)

    def test_caps_total_and_user_message_counts(self):
        # 20 user messages -> at most MAX_TOTAL_MESSAGES entries and at most
        # MAX_USER_MESSAGES user entries, keeping the NEWEST ones.
        raw = msgs(*[('user', f'm{i}') for i in range(20)])
        clean = clamp_messages(raw)
        self.assertLessEqual(len(clean), MAX_TOTAL_MESSAGES)
        self.assertLessEqual(sum(1 for m in clean if m['role'] == 'user'), MAX_USER_MESSAGES)
        self.assertEqual(clean[-1]['text'], 'm19')

    def test_non_list_becomes_empty(self):
        self.assertEqual(clamp_messages(None), [])
        self.assertEqual(clamp_messages('hi'), [])


class RefineConversationTest(SimpleTestCase):
    def test_happy_path_returns_facets_and_question(self):
        def fake_gen(system_prompt, user_text):
            # The transcript must reach the LLM (both turns).
            assert 'něco lehčího' in user_text and 'assistant' in user_text
            return ('{"cuisines": ["czech"], "wanted_ingredients": ["kuřecí"],'
                    ' "avoided_ingredients": [], "styles": ["light"], "emphases": [],'
                    ' "question": "Chcete to spíš rychlé?"}')

        facets, question = refine_conversation(
            msgs(('user', 'něco lehčího'), ('assistant', 'Co třeba salát?')),
            language='cs', cuisine_vocab=['czech', 'italian'], generate=fake_gen,
        )
        self.assertEqual(facets.wanted_ingredients, {'kuřecí'})
        self.assertEqual(facets.cuisines, {'czech'})
        self.assertEqual(question, 'Chcete to spíš rychlé?')

    def test_cuisines_outside_vocab_are_dropped(self):
        def fake_gen(sp, ut):
            return '{"cuisines": ["martian"], "question": null}'
        facets, question = refine_conversation(
            msgs(('user', 'cokoli')), language='cs', cuisine_vocab=['czech'], generate=fake_gen,
        )
        self.assertEqual(facets.cuisines, set())
        self.assertIsNone(question)

    def test_null_or_blank_question_becomes_none(self):
        def fake_gen(sp, ut):
            return '{"wanted_ingredients": ["tofu"], "question": "   "}'
        facets, question = refine_conversation(
            msgs(('user', 'tofu')), language='cs', cuisine_vocab=[], generate=fake_gen,
        )
        self.assertEqual(facets.wanted_ingredients, {'tofu'})
        self.assertIsNone(question)

    def test_malformed_json_yields_empty_facets_and_no_question(self):
        facets, question = refine_conversation(
            msgs(('user', 'ahoj')), language='cs', cuisine_vocab=[],
            generate=lambda sp, ut: 'not json at all',
        )
        self.assertTrue(facets.is_empty())
        self.assertIsNone(question)

    def test_generate_exception_yields_empty_facets_and_no_question(self):
        def boom(sp, ut):
            raise RuntimeError('LLM down')
        facets, question = refine_conversation(
            msgs(('user', 'ahoj')), language='cs', cuisine_vocab=[], generate=boom,
        )
        self.assertTrue(facets.is_empty())
        self.assertIsNone(question)

    def test_no_user_messages_makes_no_llm_call(self):
        calls = []
        def spy(sp, ut):
            calls.append(1)
            return '{}'
        facets, question = refine_conversation(
            msgs(('assistant', 'Co třeba?')), language='cs', cuisine_vocab=[], generate=spy,
        )
        self.assertTrue(facets.is_empty())
        self.assertIsNone(question)
        self.assertEqual(calls, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest diet_planner/tests/test_refine_chat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.refine_chat'`

- [ ] **Step 3: Write the implementation**

```python
"""
Refine-chat: conversation -> (PromptFacets, next Czech follow-up question).

One combined flash call per preview turn. Same never-raise contract as
prompt_facets: any LLM/parse failure yields (empty facets, None) so the caller
degrades to an unsteered pick.
Spec: docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
"""
from __future__ import annotations

import json
import logging
from typing import Callable, List, Optional, Tuple

from .prompt_facets import (
    PromptFacets,
    _coerce_facets,
    _default_generate,
    _strip_code_fence,
)

logger = logging.getLogger(__name__)

MAX_USER_MESSAGES = 8
MAX_TOTAL_MESSAGES = 16
MAX_MESSAGE_CHARS = 500

_SYSTEM_PROMPT_TEMPLATE = (
    "You are helping a user pick a replacement dish for ONE meal slot in their "
    "Czech meal plan. From the conversation so far, extract CUMULATIVE facets "
    "(later user messages win on conflicts) and write ONE short follow-up "
    "question in Czech that would most narrow the choice further.\n"
    "Return ONLY a JSON object with these keys (facet arrays are short "
    "lowercase strings, [] when unsure):\n"
    '  "cuisines": choose only from this exact list: {vocab};\n'
    '  "wanted_ingredients": key ingredients the user wants;\n'
    '  "avoided_ingredients": ingredients the user wants to avoid;\n'
    '  "styles": e.g. quick, comfort, light;\n'
    '  "emphases": choose from high_protein, low_carb, low_calorie, budget;\n'
    '  "question": one short question in Czech (max 15 words), or null when the '
    "conversation already gives enough signal.\n"
    "The question must never mention prices, availability, or name a specific "
    "recipe. No prose, JSON only."
)


def clamp_messages(messages) -> List[dict]:
    """Validate + cap raw request messages: well-formed entries only, each text
    trimmed to MAX_MESSAGE_CHARS, newest MAX_TOTAL_MESSAGES kept, and oldest
    entries dropped until at most MAX_USER_MESSAGES user messages remain."""
    if not isinstance(messages, list):
        return []
    clean: List[dict] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get('role')
        text = str(m.get('text') or '').strip()
        if role not in ('user', 'assistant') or not text:
            continue
        clean.append({'role': role, 'text': text[:MAX_MESSAGE_CHARS]})
    clean = clean[-MAX_TOTAL_MESSAGES:]
    while sum(1 for m in clean if m['role'] == 'user') > MAX_USER_MESSAGES:
        clean.pop(0)
    return clean


def refine_conversation(
    messages: List[dict],
    *,
    language: str,
    cuisine_vocab: List[str],
    generate: Optional[Callable[[str, str], str]] = None,
) -> Tuple[PromptFacets, Optional[str]]:
    """Extract cumulative facets + the next Czech question from a chat. Never
    raises; a conversation with no user message makes no LLM call at all."""
    convo = clamp_messages(messages)
    if not any(m['role'] == 'user' for m in convo):
        return PromptFacets(), None
    gen = generate or _default_generate
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(vocab=', '.join(cuisine_vocab) or '(none)')
    transcript = '\n'.join(f"{m['role']}: {m['text']}" for m in convo)
    try:
        raw = gen(system_prompt, f"Language: {language}\nConversation:\n{transcript}")
        data = json.loads(_strip_code_fence(raw))
        facets = _coerce_facets(data, cuisine_vocab=cuisine_vocab)
        q = data.get('question') if isinstance(data, dict) else None
        question = str(q).strip() if isinstance(q, str) and str(q).strip() else None
        return facets, question
    except Exception as exc:  # noqa: BLE001 - defensive by design
        logger.warning("Refine-chat extraction failed, using empty facets: %s", exc)
        return PromptFacets(), None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest diet_planner/tests/test_refine_chat.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/refine_chat.py diet_planner/tests/test_refine_chat.py
git commit -m "feat(refine-chat): conversation -> facets + Czech question service"
```

---

### Task 2: Extract shared slot/commit helpers from RecipeReplaceView (pure refactor)

**Files:**
- Modify: `diet_planner/views.py:566-700` (`RecipeReplaceView`)
- Existing tests must stay green: `diet_planner/tests/test_recipe_replace.py`

No new tests in this task — it is a behavior-preserving refactor gated by the existing suite.

- [ ] **Step 1: Add the three module-level helpers directly above `class RecipeReplaceView`**

```python
def _locate_plan_slot(user, meal_identifier: str):
    """Resolve a meal identifier to its plan slot for `user`.

    Returns (ctx, None) on success where ctx has .goal, .plan, .target_day,
    .meal_type, .current_meal — or (None, error Response) on any failure.
    Shared by RecipeReplaceView and RecipeRefineView so both address slots
    identically."""
    from types import SimpleNamespace
    try:
        goal_id, day_number, meal_type = _parse_meal_identifier(meal_identifier)
    except (ValueError, IndexError):
        return None, Response({"status": "error", "error": "Invalid meal identifier format"}, status=400)
    try:
        goal = DietaryGoal.objects.get(id=goal_id, user=user)
    except DietaryGoal.DoesNotExist:
        return None, Response({"status": "error", "error": "Goal not found"}, status=404)
    try:
        plan = goal.dietary_plan
    except DietaryPlan.DoesNotExist:
        return None, Response({"status": "error", "error": "Plan not found"}, status=404)
    target_day = next(
        (d for d in (plan.days or []) if d.get('day_number') == day_number), None,
    )
    current_meal = target_day.get(meal_type) if isinstance(target_day, dict) else None
    if not isinstance(current_meal, dict):
        return None, Response({"status": "error", "error": "Meal not found in plan"}, status=404)
    return SimpleNamespace(
        goal=goal, plan=plan, target_day=target_day,
        meal_type=meal_type, current_meal=current_meal,
    ), None


def _plan_swap_state(plan, current_id):
    """Selection context for swapping one slot: (pool, used_recipe_ids,
    used_cuisines). used_recipe_ids covers every curated recipe elsewhere in
    the plan (the slot being swapped doesn't count) so a swap never duplicates
    a dish already on another day/slot."""
    used_recipe_ids: set = set()
    for d in (plan.days or []):
        for slot in ('breakfast', 'lunch', 'dinner'):
            m = d.get(slot)
            if isinstance(m, dict) and m.get('curated_recipe_id'):
                used_recipe_ids.add(m['curated_recipe_id'])
        for list_key in ('small_meals', 'snacks'):
            for m in (d.get(list_key) or []):
                if isinstance(m, dict) and m.get('curated_recipe_id'):
                    used_recipe_ids.add(m['curated_recipe_id'])
    used_recipe_ids.discard(current_id)
    pool = published_pool()
    cuisine_by_id = {r.id: (r.cuisine or '') for r in pool}
    used_cuisines = [cuisine_by_id[i] for i in used_recipe_ids if cuisine_by_id.get(i)]
    return pool, used_recipe_ids, used_cuisines


def _commit_slot_swap(*, goal, plan, target_day, meal_type, meal_identifier, chosen, user):
    """Atomically write `chosen` (a CuratedRecipe) into the slot: rewrite
    plan.days, bump usage_count, refresh the cached Recipe row IN PLACE (same
    pk — a substantive row is auto-published at /recepty/<pk>/, recreating
    would orphan that live URL), and reset cooked state. Returns the Recipe."""
    with transaction.atomic():
        new_meal = scale_recipe_to_meal(chosen)
        new_meal['meal_identifier'] = meal_identifier
        target_day[meal_type] = new_meal
        plan.save(update_fields=['days'])
        CuratedRecipe.objects.filter(pk=chosen.id).update(usage_count=F('usage_count') + 1)
        recipe, _ = Recipe.objects.update_or_create(
            meal_identifier=meal_identifier,
            defaults={
                'dietary_goal': goal,
                **_recipe_cache_fields(new_meal, new_meal.get('instructions', [])),
            },
        )
        MealInstance.objects.filter(
            meal_identifier=meal_identifier, user=user,
        ).update(is_cooked=False, cooked_at=None, meal_name=new_meal.get('name', ''))
    return recipe
```

- [ ] **Step 2: Rewrite `RecipeReplaceView.post` to use the helpers**

Replace the body of `post` (keep the class docstring and `permission_classes`) with:

```python
    def post(self, request, meal_identifier: str) -> Response:
        ctx, err = _locate_plan_slot(request.user, meal_identifier)
        if err:
            return err

        goal, plan = ctx.goal, ctx.plan
        required_tags = parse_dietary_tags(getattr(goal, 'dietary_restrictions', None))
        current_id = ctx.current_meal.get('curated_recipe_id')
        exclude_ids = {current_id} if current_id else set()
        pool, used_recipe_ids, used_cuisines = _plan_swap_state(plan, current_id)

        hint = (request.data.get('hint') or '').strip()
        facets = None
        hint_matched = None
        if hint:
            facets = extract_prompt_facets(
                hint, language=goal.language_code,
                cuisine_vocab=published_cuisine_vocab(pool=pool),
            )
            # extract_prompt_facets never raises: an LLM failure (or a hint with
            # no extractable facets) yields EMPTY facets, which match every
            # recipe. Treat that as "could not honor the hint" — a plain
            # next-best fallback reported as hint_matched=False — rather than
            # letting an unsteered pick masquerade as a successful match.
            if facets.is_empty():
                facets = None
                hint_matched = False

        def pick(active_facets):
            candidates = eligible_recipes_for_slot(
                ctx.meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=active_facets,
            )
            if not candidates:
                return None
            return max(candidates, key=lambda r: score_recipe(
                r, used_recipe_ids=used_recipe_ids, used_cuisines=used_cuisines, facets=active_facets,
            ))

        chosen = pick(facets)
        if hint and hint_matched is None:
            # A non-empty hint was applied — did it actually steer the pick?
            if chosen is None:
                # Hint too specific for the corpus — fall back to plain next-best.
                chosen = pick(None)
                hint_matched = False
            else:
                hint_matched = True

        if chosen is None:
            return Response(
                {"status": "success", "data": {"replaced": False, "reason": "no_alternatives"}},
                status=200,
            )

        recipe = _commit_slot_swap(
            goal=goal, plan=plan, target_day=ctx.target_day, meal_type=ctx.meal_type,
            meal_identifier=meal_identifier, chosen=chosen, user=request.user,
        )
        return Response({
            "status": "success",
            "data": {
                "replaced": True,
                "hint_matched": hint_matched,
                "recipe": serialize_recipe_detail(recipe),
            },
        }, status=200)
```

- [ ] **Step 3: Run the existing replace suite to prove no behavior change**

Run: `python -m pytest diet_planner/tests/test_recipe_replace.py -v`
Expected: all PASS (same tests, untouched)

- [ ] **Step 4: Commit**

```bash
git add diet_planner/views.py
git commit -m "refactor(replace): extract slot-locate/swap-state/commit helpers for reuse"
```

---

### Task 3: RecipeRefineView — preview mode (no writes)

**Files:**
- Modify: `diet_planner/views.py` (new view class after `RecipeReplaceView`)
- Modify: `diet_planner/urls.py` (route BEFORE the `recipes/<str:meal_identifier>/` catch-all)
- Test: `diet_planner/tests/test_recipe_refine.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Refine-chat endpoint (POST /api/recipes/<meal_identifier>/refine/).

Preview turns NEVER write; only an accept turn commits.
Spec: docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from diet_planner.models import CuratedRecipe, DietaryGoal, DietaryPlan, MealInstance, Recipe
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.tests.test_recipe_replace import make_recipe


class RefineTestBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _plan_with_lunch(self, recipe):
        from diet_planner.services.recipe_retrieval import scale_recipe_to_meal
        meal = scale_recipe_to_meal(recipe)
        meal['meal_identifier'] = f'{self.goal.id}:1:lunch:0'
        return DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{'day_number': 1, 'lunch': meal, 'small_meals': [], 'snacks': []}],
            currency='CZK',
        )

    def _url(self):
        return reverse(
            'diet_planner:recipe-refine',
            kwargs={'meal_identifier': f'{self.goal.id}:1:lunch:0'},
        )

    def _preview(self, messages, rejected_ids=None):
        return self.client.post(
            self._url(),
            {'messages': messages, 'rejected_ids': rejected_ids or []},
            format='json',
        )


USER_MSG = [{'role': 'user', 'text': 'něco s kuřecím'}]


class PreviewTurnTest(RefineTestBase):
    def test_returns_candidate_question_and_match_flag_without_writing(self):
        current = make_recipe(name_cs='Kuře s rýží')
        chicken = make_recipe(name_cs='Kuřecí salát', ingredients=[
            {'name': 'kuřecí prsa', 'quantity': 150, 'unit': 'g', 'canonical': 'chicken-breast'},
        ])
        plan = self._plan_with_lunch(current)
        before = plan.days

        facets = PromptFacets(wanted_ingredients={'kuřecí'})
        with patch('diet_planner.views.refine_conversation',
                   return_value=(facets, 'Chcete to spíš rychlé?')) as m:
            resp = self._preview(USER_MSG)

        self.assertEqual(resp.status_code, 200)
        m.assert_called_once()
        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], chicken.id)
        self.assertEqual(body['candidate']['name'], 'Kuřecí salát')
        self.assertEqual(body['question'], 'Chcete to spíš rychlé?')
        self.assertTrue(body['hint_matched'])
        # PREVIEW MUST NOT WRITE: plan untouched, no Recipe row churn,
        # no usage bump, no cooked-state reset.
        plan.refresh_from_db()
        self.assertEqual(plan.days, before)
        chicken.refresh_from_db()
        self.assertEqual(chicken.usage_count, 0)
        self.assertFalse(Recipe.objects.filter(name='Kuřecí salát').exists())

    def test_rejected_ids_are_excluded_from_selection(self):
        current = make_recipe(name_cs='Kuře s rýží')
        first = make_recipe(name_cs='Hovězí guláš')
        second = make_recipe(name_cs='Těstoviny', cuisine='italian')

        self._plan_with_lunch(current)
        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview(USER_MSG, rejected_ids=[first.id])

        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], second.id)

    def test_empty_facets_flags_no_match_but_still_offers_candidate(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)

        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview(USER_MSG)

        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], other.id)
        self.assertFalse(body['hint_matched'])
        self.assertIsNone(body['question'])

    def test_unmatchable_facets_fall_back_to_next_best(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš', ingredients=[
            {'name': 'hovězí', 'quantity': 150, 'unit': 'g', 'canonical': 'beef-chuck'},
        ])
        self._plan_with_lunch(current)

        facets = PromptFacets(wanted_ingredients={'tofu'})
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview(USER_MSG)

        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], other.id)
        self.assertFalse(body['hint_matched'])

    def test_all_alternatives_rejected_reports_no_alternatives(self):
        current = make_recipe(name_cs='Kuře s rýží')
        only_other = make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)

        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview(USER_MSG, rejected_ids=[only_other.id])

        body = resp.data['data']
        self.assertIsNone(body['candidate'])
        self.assertEqual(body['reason'], 'no_alternatives')

    def test_messages_are_clamped_before_the_llm_sees_them(self):
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)

        oversized = [{'role': 'user', 'text': f'zpráva {i}'} for i in range(30)]
        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)) as m:
            self._preview(oversized)

        passed = m.call_args.args[0]
        self.assertLessEqual(len(passed), 16)
        self.assertLessEqual(sum(1 for x in passed if x['role'] == 'user'), 8)

    def test_other_users_meal_is_404(self):
        current = make_recipe(name_cs='Kuře')
        make_recipe(name_cs='Hovezí')
        self._plan_with_lunch(current)
        intruder = get_user_model().objects.create(username='intruder')
        other = APIClient()
        other.force_authenticate(user=intruder)
        resp = other.post(self._url(), {'messages': USER_MSG, 'rejected_ids': []}, format='json')
        self.assertEqual(resp.status_code, 404)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest diet_planner/tests/test_recipe_refine.py -v`
Expected: FAIL — `NoReverseMatch: 'recipe-refine' not found`

- [ ] **Step 3: Add the route**

In `diet_planner/urls.py`, insert directly under the `recipe-replace` line (order matters — must precede `recipes/<str:meal_identifier>/`):

```python
    path('recipes/<str:meal_identifier>/refine/', views.RecipeRefineView.as_view(), name='recipe-refine'),
```

- [ ] **Step 4: Implement the view (preview mode only for now)**

In `diet_planner/views.py`, add the import next to the existing `extract_prompt_facets` import (line 55):

```python
from .services.refine_chat import clamp_messages, refine_conversation
```

Add after `RecipeReplaceView`:

```python
_EMPHASIS_CZ = {
    'high_protein': 'hodně bílkovin',
    'low_carb': 'málo sacharidů',
    'low_calorie': 'nízkokalorické',
    'budget': 'úsporné',
}


def _candidate_why(recipe, facets) -> str | None:
    """Czech 'why this candidate' line, derived IN CODE from which facets the
    candidate actually matches — never LLM-written."""
    if facets is None:
        return None
    from .services.recipe_retrieval import _ingredient_present, _recipe_ingredient_tokens
    parts: list = []
    tokens = _recipe_ingredient_tokens(recipe)
    parts += [w for w in sorted(facets.wanted_ingredients) if _ingredient_present(w, tokens)]
    if recipe.cuisine and recipe.cuisine.lower() in facets.cuisines:
        parts.append(recipe.cuisine.lower())
    tags = set(recipe.dietary_tags or [])
    parts += [_EMPHASIS_CZ[e] for e in sorted(facets.emphases & tags) if e in _EMPHASIS_CZ]
    if 'quick' in facets.styles and recipe.total_time and recipe.total_time <= 20:
        parts.append('rychlé')
    return f"Odpovídá: {', '.join(parts)}" if parts else None


def _candidate_payload(recipe, facets) -> dict:
    """Card-sized preview of a candidate. Rendered from scale_recipe_to_meal so
    the fields match exactly what an accepted swap would write."""
    meal = scale_recipe_to_meal(recipe)
    return {
        'curated_recipe_id': recipe.id,
        'name': meal['name'],
        'description': meal['description'],
        'food_category': meal['food_category'],
        'preparation_time': meal['preparation_time'],
        'calories': (meal.get('nutritional_info') or {}).get('calories'),
        'why': _candidate_why(recipe, facets),
    }


class RecipeRefineView(APIView):
    """Conversational curated swap: preview candidates turn-by-turn, commit only
    on accept. Preview turns make exactly one flash call (facets + Czech
    follow-up question) and NEVER write; every candidate is a published
    CuratedRecipe, so the catalog-mapping integrity bar is preserved.
    Spec: docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, meal_identifier: str) -> Response:
        ctx, err = _locate_plan_slot(request.user, meal_identifier)
        if err:
            return err
        goal = ctx.goal
        required_tags = parse_dietary_tags(getattr(goal, 'dietary_restrictions', None))
        current_id = ctx.current_meal.get('curated_recipe_id')
        pool, used_recipe_ids, used_cuisines = _plan_swap_state(ctx.plan, current_id)

        if request.data.get('accept') is not None:
            return self._accept(
                request, ctx=ctx, meal_identifier=meal_identifier,
                required_tags=required_tags, current_id=current_id, pool=pool,
            )

        messages = clamp_messages(request.data.get('messages'))
        rejected = {
            int(i) for i in (request.data.get('rejected_ids') or [])
            if isinstance(i, int) or (isinstance(i, str) and i.isdigit())
        }
        exclude_ids = ({current_id} if current_id else set()) | rejected

        facets, question = refine_conversation(
            messages, language=goal.language_code,
            cuisine_vocab=published_cuisine_vocab(pool=pool),
        )
        hint_matched = None
        if facets.is_empty():
            # Mirrors the replace endpoint: empty facets (LLM failure or nothing
            # extractable) match everything — report the pick as unsteered.
            facets = None
            hint_matched = False

        def pick(active_facets):
            candidates = eligible_recipes_for_slot(
                ctx.meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=active_facets,
            )
            if not candidates:
                return None
            return max(candidates, key=lambda r: score_recipe(
                r, used_recipe_ids=used_recipe_ids, used_cuisines=used_cuisines, facets=active_facets,
            ))

        chosen = pick(facets)
        if facets is not None:
            if chosen is None:
                chosen = pick(None)
                hint_matched = False
            else:
                hint_matched = True

        if chosen is None:
            return Response({
                "status": "success",
                "data": {"candidate": None, "question": None,
                         "hint_matched": hint_matched, "reason": "no_alternatives"},
            }, status=200)

        return Response({
            "status": "success",
            "data": {
                "candidate": _candidate_payload(chosen, facets),
                "question": question,
                "hint_matched": hint_matched,
            },
        }, status=200)

    def _accept(self, request, *, ctx, meal_identifier, required_tags, current_id, pool):
        return Response({"status": "error", "error": "Not implemented"}, status=501)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest diet_planner/tests/test_recipe_refine.py -v`
Expected: all PASS

- [ ] **Step 6: Run the neighbor suites (refactor safety)**

Run: `python -m pytest diet_planner/tests/test_recipe_replace.py diet_planner/tests/test_recipe_retrieval.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add diet_planner/views.py diet_planner/urls.py diet_planner/tests/test_recipe_refine.py
git commit -m "feat(refine-chat): preview endpoint - candidate + question, zero writes"
```

---

### Task 4: RecipeRefineView — accept mode (the only mutating path)

**Files:**
- Modify: `diet_planner/views.py` (`RecipeRefineView._accept`)
- Test: `diet_planner/tests/test_recipe_refine.py` (append)

- [ ] **Step 1: Write the failing tests (append to test_recipe_refine.py)**

```python
class AcceptTurnTest(RefineTestBase):
    def test_accept_commits_the_swap_with_all_side_effects(self):
        from django.utils import timezone
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        plan = self._plan_with_lunch(current)
        ident = f'{self.goal.id}:1:lunch:0'
        MealInstance.objects.create(
            user=self.user, dietary_goal=self.goal, meal_identifier=ident,
            meal_name='Kuře s rýží', day_number=1, meal_type='lunch',
            is_cooked=True, cooked_at=timezone.now(),
        )

        resp = self.client.post(self._url(), {'accept': other.id}, format='json')

        self.assertEqual(resp.status_code, 200)
        body = resp.data['data']
        self.assertTrue(body['replaced'])
        self.assertEqual(body['recipe']['name'], 'Hovězí guláš')
        plan.refresh_from_db()
        lunch = plan.days[0]['lunch']
        self.assertEqual(lunch['curated_recipe_id'], other.id)
        self.assertEqual(lunch['meal_identifier'], ident)
        other.refresh_from_db()
        self.assertEqual(other.usage_count, 1)
        mi = MealInstance.objects.get(meal_identifier=ident, user=self.user)
        self.assertFalse(mi.is_cooked)
        self.assertIsNone(mi.cooked_at)

    def test_accept_makes_no_llm_call(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)
        with patch('diet_planner.views.refine_conversation') as m:
            resp = self.client.post(self._url(), {'accept': other.id}, format='json')
        self.assertEqual(resp.status_code, 200)
        m.assert_not_called()

    def test_accept_rejects_ineligible_recipe_without_writing(self):
        current = make_recipe(name_cs='Kuře s rýží')
        # Wrong slot: breakfast-only recipe is NOT eligible for lunch.
        breakfast_only = make_recipe(name_cs='Ovesná kaše', meal_types=['breakfast'])
        plan = self._plan_with_lunch(current)
        before = plan.days

        resp = self.client.post(self._url(), {'accept': breakfast_only.id}, format='json')

        self.assertEqual(resp.status_code, 400)
        plan.refresh_from_db()
        self.assertEqual(plan.days, before)
        breakfast_only.refresh_from_db()
        self.assertEqual(breakfast_only.usage_count, 0)

    def test_accept_rejects_the_current_recipe_itself(self):
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)
        resp = self.client.post(self._url(), {'accept': current.id}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_accept_rejects_garbage_id(self):
        current = make_recipe(name_cs='Kuře s rýží')
        self._plan_with_lunch(current)
        resp = self.client.post(self._url(), {'accept': 'DROP TABLE'}, format='json')
        self.assertEqual(resp.status_code, 400)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python -m pytest diet_planner/tests/test_recipe_refine.py -v -k Accept`
Expected: FAIL — 501 responses from the stub

- [ ] **Step 3: Implement `_accept`**

Replace the stub in `RecipeRefineView`:

```python
    def _accept(self, request, *, ctx, meal_identifier, required_tags, current_id, pool):
        try:
            accept_id = int(request.data.get('accept'))
        except (TypeError, ValueError):
            return Response({"status": "error", "error": "Invalid accept id"}, status=400)
        # Re-validate against the SAME eligibility gate the preview used — the
        # corpus or plan may have changed between preview and accept, and a
        # crafted id must never bypass slot/dietary rules.
        exclude_ids = {current_id} if current_id else set()
        candidates = eligible_recipes_for_slot(
            ctx.meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=None,
        )
        chosen = next((r for r in candidates if r.id == accept_id), None)
        if chosen is None:
            return Response({"status": "error", "error": "Recipe not eligible for this slot"}, status=400)
        recipe = _commit_slot_swap(
            goal=ctx.goal, plan=ctx.plan, target_day=ctx.target_day, meal_type=ctx.meal_type,
            meal_identifier=meal_identifier, chosen=chosen, user=request.user,
        )
        return Response({
            "status": "success",
            "data": {"replaced": True, "recipe": serialize_recipe_detail(recipe)},
        }, status=200)
```

- [ ] **Step 4: Run the full refine + replace suites**

Run: `python -m pytest diet_planner/tests/test_recipe_refine.py diet_planner/tests/test_recipe_replace.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add diet_planner/views.py diet_planner/tests/test_recipe_refine.py
git commit -m "feat(refine-chat): accept mode commits via shared swap helper"
```

---

### Task 5: Frontend API client

**Files:**
- Create: `frontend/src/lib/refineRecipe.ts`
- Test: `frontend/src/lib/refineRecipe.test.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from '@/lib/api';
import { refinePreview, refineAccept } from './refineRecipe';

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }));

describe('refineRecipe client', () => {
  beforeEach(() => vi.clearAllMocks());

  it('refinePreview posts messages + rejected ids and unwraps data', async () => {
    const payload = { candidate: null, question: null, hint_matched: false, reason: 'no_alternatives' };
    vi.mocked(api.post).mockResolvedValue({ data: { data: payload } });

    const messages = [{ role: 'user' as const, text: 'něco lehčího' }];
    const result = await refinePreview('12:1:lunch:0', messages, [7]);

    expect(api.post).toHaveBeenCalledWith('/recipes/12:1:lunch:0/refine/', {
      messages, rejected_ids: [7],
    });
    expect(result).toEqual(payload);
  });

  it('refineAccept posts the accept id and unwraps data', async () => {
    const payload = { replaced: true, recipe: { name: 'Guláš' } };
    vi.mocked(api.post).mockResolvedValue({ data: { data: payload } });

    const result = await refineAccept('12:1:lunch:0', 99);

    expect(api.post).toHaveBeenCalledWith('/recipes/12:1:lunch:0/refine/', { accept: 99 });
    expect(result).toEqual(payload);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/refineRecipe.test.ts`
Expected: FAIL — cannot resolve `./refineRecipe`

- [ ] **Step 3: Write the implementation**

```typescript
import { api } from '@/lib/api';

/** One chat turn. Assistant entries carry the transcript text the LLM sees
 * (suggestion + question), so the backend gets the full conversation. */
export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
}

/** Card-sized candidate preview returned by a preview turn. */
export interface RefineCandidate {
  curated_recipe_id: number;
  name: string;
  description: string;
  food_category: string;
  preparation_time: number | null;
  calories: number | null;
  why: string | null;
}

export interface RefinePreviewResult {
  candidate: RefineCandidate | null;
  question: string | null;
  hint_matched: boolean | null;
  reason?: string;
}

export interface RefineAcceptResult {
  replaced: boolean;
  recipe?: Record<string, unknown>;
}

/** Preview turn: send the whole conversation; nothing is written server-side. */
export async function refinePreview(
  mealId: string,
  messages: ChatMessage[],
  rejectedIds: number[],
): Promise<RefinePreviewResult> {
  const res = await api.post(`/recipes/${mealId}/refine/`, {
    messages,
    rejected_ids: rejectedIds,
  });
  return res.data.data as RefinePreviewResult;
}

/** Accept turn: commit the previewed candidate into the plan slot. */
export async function refineAccept(mealId: string, recipeId: number): Promise<RefineAcceptResult> {
  const res = await api.post(`/recipes/${mealId}/refine/`, { accept: recipeId });
  return res.data.data as RefineAcceptResult;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/refineRecipe.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/refineRecipe.ts frontend/src/lib/refineRecipe.test.ts
git commit -m "feat(refine-chat): typed frontend client for preview/accept"
```

---

### Task 6: RecipeRefineChat component

**Files:**
- Create: `frontend/src/components/recipe/RecipeRefineChat.tsx`
- Test: `frontend/src/components/recipe/RecipeRefineChat.test.tsx`

Czech copy in this component (EN glosses for user review — do not change without flagging):

| Czech | English gloss |
|---|---|
| `Na co máte chuť? Poradíme vám s výběrem.` | "What are you craving? We'll help you choose." (panel intro) |
| `Napište, na co máte chuť…` | "Write what you're craving…" (input placeholder) |
| `Co třeba: {name}?` | "How about: {name}?" (matched suggestion intro) |
| `Přesně podle vašeho přání jsme nic nenašli, ale co třeba: {name}?` | "We found nothing exactly matching your wish, but how about: {name}?" (unmatched intro) |
| `Použít tento recept` | "Use this recipe" (accept button) |
| `Pro tento typ jídla už nemáme další alternativu.` | "We have no further alternative for this meal type." |
| `To je pro dnešek vše — vyberte si recept, nebo začněte znovu.` | "That's all for now — pick a recipe or start over." (8-message cap) |
| `Začít znovu` | "Start over" |
| `Zavřít` | "Close" |
| `Odeslat` | "Send" (submit button aria-label) |
| `Něco se nepovedlo, zkuste to prosím znovu.` | "Something went wrong, please try again." (error toast) |

- [ ] **Step 1: Write the failing tests**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastProvider } from '@/components/ui/Toast';
import { RecipeRefineChat } from './RecipeRefineChat';
import { refinePreview, refineAccept } from '@/lib/refineRecipe';

vi.mock('@/lib/refineRecipe', () => ({ refinePreview: vi.fn(), refineAccept: vi.fn() }));
vi.mock('@/lib/food-image', () => ({ getFoodImageUrl: () => '' }));

const MEAL_ID = '12:1:lunch:0';
const CANDIDATE = {
  curated_recipe_id: 7, name: 'Kuřecí salát', description: '',
  food_category: '', preparation_time: 15, calories: 420, why: 'Odpovídá: kuřecí',
};

function setup() {
  const onAccepted = vi.fn();
  const onClose = vi.fn();
  render(
    <ToastProvider>
      <RecipeRefineChat mealId={MEAL_ID} onAccepted={onAccepted} onClose={onClose} />
    </ToastProvider>,
  );
  return { onAccepted, onClose };
}

async function send(text: string) {
  await userEvent.type(screen.getByPlaceholderText('Napište, na co máte chuť…'), text);
  await userEvent.click(screen.getByRole('button', { name: 'Odeslat' }));
}

describe('RecipeRefineChat', () => {
  beforeEach(() => vi.clearAllMocks());

  it('first turn shows the candidate card and the follow-up question', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: 'Chcete to spíš rychlé?', hint_matched: true,
    });
    setup();
    await send('něco s kuřecím');

    expect(refinePreview).toHaveBeenCalledWith(
      MEAL_ID, [{ role: 'user', text: 'něco s kuřecím' }], [],
    );
    expect(await screen.findByText(/Co třeba: Kuřecí salát\?/)).toBeInTheDocument();
    expect(screen.getByText(/Chcete to spíš rychlé\?/)).toBeInTheDocument();
    expect(screen.getByText('Odpovídá: kuřecí')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Použít tento recept' })).toBeInTheDocument();
  });

  it('typing again rejects the shown candidate and sends the transcript', async () => {
    vi.mocked(refinePreview)
      .mockResolvedValueOnce({ candidate: CANDIDATE, question: 'Rychlé?', hint_matched: true })
      .mockResolvedValueOnce({
        candidate: { ...CANDIDATE, curated_recipe_id: 8, name: 'Těstoviny' },
        question: null, hint_matched: true,
      });
    setup();
    await send('něco s kuřecím');
    await screen.findByText(/Co třeba: Kuřecí salát\?/);
    await send('něco jiného');

    const second = vi.mocked(refinePreview).mock.calls[1];
    expect(second[2]).toEqual([7]); // previous candidate now rejected
    // Transcript carries user turns AND the assistant turn.
    expect(second[1].map((m: any) => m.role)).toEqual(['user', 'assistant', 'user']);
  });

  it('unmatched turn uses the honest fallback phrasing', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: null, hint_matched: false,
    });
    setup();
    await send('něco s tofu');
    expect(
      await screen.findByText(/Přesně podle vašeho přání jsme nic nenašli, ale co třeba: Kuřecí salát\?/),
    ).toBeInTheDocument();
  });

  it('accept calls the API and bubbles the recipe up', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: null, hint_matched: true,
    });
    vi.mocked(refineAccept).mockResolvedValue({ replaced: true, recipe: { name: 'Kuřecí salát' } });
    const { onAccepted } = setup();
    await send('něco s kuřecím');
    await userEvent.click(await screen.findByRole('button', { name: 'Použít tento recept' }));

    expect(refineAccept).toHaveBeenCalledWith(MEAL_ID, 7);
    expect(onAccepted).toHaveBeenCalledWith({ name: 'Kuřecí salát' });
  });

  it('shows no-alternatives message with a restart action', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: null, question: null, hint_matched: false, reason: 'no_alternatives',
    });
    setup();
    await send('cokoli');
    expect(
      await screen.findByText('Pro tento typ jídla už nemáme další alternativu.'),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Začít znovu' }));
    // Restart clears everything: the input is usable again, transcript gone.
    expect(screen.queryByText('Pro tento typ jídla už nemáme další alternativu.')).toBeNull();
    expect(screen.getByPlaceholderText('Napište, na co máte chuť…')).toBeEnabled();
  });

  it('disables input after 8 user messages and shows the closing prompt', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: 'Ještě něco?', hint_matched: true,
    });
    setup();
    for (let i = 0; i < 8; i++) {
      await send(`zpráva ${i}`);
      await screen.findAllByText(/Co třeba: Kuřecí salát\?/);
    }
    expect(
      await screen.findByText('To je pro dnešek vše — vyberte si recept, nebo začněte znovu.'),
    ).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Napište, na co máte chuť…')).toBeNull();
    // The candidate is still acceptable after the cap.
    expect(screen.getByRole('button', { name: 'Použít tento recept' })).toBeInTheDocument();
  });

  it('a failed turn preserves state and restores the draft for retry', async () => {
    vi.mocked(refinePreview).mockRejectedValueOnce(new Error('boom'));
    setup();
    await send('něco s kuřecím');
    expect(
      await screen.findByText('Něco se nepovedlo, zkuste to prosím znovu.'),
    ).toBeInTheDocument();
    // The message was rolled back (not burned from the 8 budget) and the
    // draft text is back in the input.
    expect(screen.getByPlaceholderText('Napište, na co máte chuť…')).toHaveValue('něco s kuřecím');
    expect(refinePreview).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/recipe/RecipeRefineChat.test.tsx`
Expected: FAIL — cannot resolve `./RecipeRefineChat`

- [ ] **Step 3: Write the component**

Styling follows the existing panel (`bg-card border-line rounded-2xl`, green accents) — see the old hint panel in `RecipePage.tsx:222-258` for the idiom.

```tsx
import { useState } from 'react';
import { Clock, Flame, Loader2, Send } from 'lucide-react';
import { getFoodImageUrl } from '@/lib/food-image';
import { useToast } from '@/components/ui/Toast';
import {
  refineAccept,
  refinePreview,
  type ChatMessage,
  type RefineCandidate,
} from '@/lib/refineRecipe';

const MAX_USER_MESSAGES = 8;

interface RecipeRefineChatProps {
  mealId: string;
  /** Called with the swapped-in recipe (RecipeDetail shape) after a committed accept. */
  onAccepted: (recipe: Record<string, unknown>) => void;
  onClose: () => void;
}

/** Assistant transcript line: also what the backend LLM sees on later turns. */
const assistantText = (c: RefineCandidate, question: string | null, matched: boolean | null) => {
  const intro = matched === false
    ? `Přesně podle vašeho přání jsme nic nenašli, ale co třeba: ${c.name}?`
    : `Co třeba: ${c.name}?`;
  return question ? `${intro} ${question}` : intro;
};

export const RecipeRefineChat = ({ mealId, onAccepted, onClose }: RecipeRefineChatProps) => {
  const toast = useToast();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [candidate, setCandidate] = useState<RefineCandidate | null>(null);
  const [rejectedIds, setRejectedIds] = useState<number[]>([]);
  const [noAlternatives, setNoAlternatives] = useState(false);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);

  const userCount = messages.filter((m) => m.role === 'user').length;
  const capReached = userCount >= MAX_USER_MESSAGES;

  const reset = () => {
    setMessages([]);
    setCandidate(null);
    setRejectedIds([]);
    setNoAlternatives(false);
    setInput('');
  };

  const send = async () => {
    const text = input.trim();
    if (!text || pending || capReached) return;
    // Typing a new message implicitly rejects the currently shown candidate.
    const nextRejected = candidate ? [...rejectedIds, candidate.curated_recipe_id] : rejectedIds;
    const nextMessages: ChatMessage[] = [...messages, { role: 'user', text }];
    setMessages(nextMessages);
    setRejectedIds(nextRejected);
    setCandidate(null);
    setInput('');
    setNoAlternatives(false);
    setPending(true);
    try {
      const r = await refinePreview(mealId, nextMessages, nextRejected);
      if (!r.candidate) {
        setNoAlternatives(true);
        return;
      }
      setCandidate(r.candidate);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: assistantText(r.candidate!, r.question, r.hint_matched) },
      ]);
    } catch {
      // Roll back the turn so it isn't burned from the 8-message budget, and
      // put the draft back so the user can just hit send again.
      toast.error('Něco se nepovedlo, zkuste to prosím znovu.');
      setMessages(messages);
      setRejectedIds(rejectedIds);
      setCandidate(candidate);
      setInput(text);
    } finally {
      setPending(false);
    }
  };

  const accept = async () => {
    if (!candidate || pending) return;
    setPending(true);
    try {
      const r = await refineAccept(mealId, candidate.curated_recipe_id);
      if (r.replaced && r.recipe) {
        onAccepted(r.recipe);
      } else {
        toast.error('Něco se nepovedlo, zkuste to prosím znovu.');
      }
    } catch {
      toast.error('Něco se nepovedlo, zkuste to prosím znovu.');
    } finally {
      setPending(false);
    }
  };

  const imgUrl = candidate ? getFoodImageUrl(candidate.food_category, candidate.name) : '';

  return (
    <div className="rounded-2xl border border-line bg-card p-5 max-w-xl">
      <p className="text-sm font-bold text-ink mb-3">Na co máte chuť? Poradíme vám s výběrem.</p>

      {messages.length > 0 && (
        <ul className="space-y-2 mb-4">
          {messages.map((m, idx) => (
            <li
              key={idx}
              className={m.role === 'user'
                ? 'ml-8 rounded-xl bg-green-soft px-4 py-2 text-sm text-ink'
                : 'mr-8 rounded-xl bg-bg border border-line px-4 py-2 text-sm text-muted'}
            >
              {m.text}
            </li>
          ))}
        </ul>
      )}

      {candidate && (
        <div className="rounded-xl border border-green/40 bg-bg p-4 mb-4">
          {imgUrl && (
            <img src={imgUrl} alt={candidate.name} className="w-full h-32 object-cover rounded-lg mb-3" />
          )}
          <p className="font-black text-ink">{candidate.name}</p>
          {candidate.why && <p className="text-xs text-green mt-1">{candidate.why}</p>}
          <div className="flex gap-4 mt-2 text-[10px] font-black uppercase tracking-widest text-muted">
            {candidate.preparation_time != null && (
              <span className="flex items-center gap-1"><Clock size={12} className="text-green" /> {candidate.preparation_time} min</span>
            )}
            {candidate.calories != null && (
              <span className="flex items-center gap-1"><Flame size={12} className="text-green" /> {candidate.calories} kcal</span>
            )}
          </div>
          <button
            onClick={accept}
            disabled={pending}
            className="mt-4 flex items-center gap-2 px-6 h-11 bg-green text-white font-black uppercase text-[10px] tracking-widest rounded-xl disabled:opacity-60"
          >
            {pending && <Loader2 size={14} className="animate-spin" />} Použít tento recept
          </button>
        </div>
      )}

      {noAlternatives && (
        <p className="mb-4 text-sm font-medium text-paprika-strong">
          Pro tento typ jídla už nemáme další alternativu.
        </p>
      )}

      {capReached && (
        <p className="mb-4 text-sm font-medium text-muted">
          To je pro dnešek vše — vyberte si recept, nebo začněte znovu.
        </p>
      )}

      {!capReached && !noAlternatives && (
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
            placeholder="Napište, na co máte chuť…"
            disabled={pending}
            className="flex-1 h-11 px-4 bg-bg border border-line rounded-xl text-sm text-ink placeholder:text-muted focus:border-green/60 focus:outline-none disabled:opacity-60"
          />
          <button
            onClick={send}
            disabled={pending}
            aria-label="Odeslat"
            className="w-11 h-11 flex items-center justify-center bg-green text-white rounded-xl disabled:opacity-60"
          >
            {pending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      )}

      <div className="mt-4 flex gap-3">
        {(capReached || noAlternatives) && (
          <button
            onClick={reset}
            disabled={pending}
            className="px-6 h-11 bg-card border border-line text-ink font-black uppercase text-[10px] tracking-widest rounded-xl disabled:opacity-60"
          >
            Začít znovu
          </button>
        )}
        <button
          onClick={onClose}
          disabled={pending}
          className="px-6 h-11 text-muted hover:text-ink font-black uppercase text-[10px] tracking-widest rounded-xl disabled:opacity-60"
        >
          Zavřít
        </button>
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/recipe/RecipeRefineChat.test.tsx`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/recipe/RecipeRefineChat.tsx frontend/src/components/recipe/RecipeRefineChat.test.tsx
git commit -m "feat(refine-chat): chat panel component with candidate cards"
```

---

### Task 7: Wire into RecipePage, retire the old hint panel

**Files:**
- Modify: `frontend/src/pages/RecipePage.tsx`
- Delete: `frontend/src/pages/RecipePage.replace.test.tsx`, `frontend/src/lib/replaceRecipe.ts`, `frontend/src/lib/replaceRecipe.test.ts`
- Create: `frontend/src/pages/RecipePage.refine.test.tsx`

The backend `/replace/` endpoint and its tests are intentionally KEPT (the refine accept path reuses its commit logic; removing the endpoint is out of scope).

- [ ] **Step 1: Write the failing page-level test**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/ui/Toast';
import { RecipePage } from './RecipePage';
import { api } from '@/lib/api';
import { refinePreview, refineAccept } from '@/lib/refineRecipe';

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/refineRecipe', () => ({ refinePreview: vi.fn(), refineAccept: vi.fn() }));
vi.mock('@/lib/pricing', () => ({ getRecipeDeals: () => null, getShoppingList: () => [] }));
vi.mock('@/lib/food-image', () => ({ getFoodImageUrl: () => '' }));

const MEAL_ID = '12:1:lunch:0';
const RECIPE = {
  name: 'Kuře s rýží', description: '', ingredients: [],
  instructions: ['Uvař.'], servings: 1, nutritional_info: {}, source_url: '',
};
const CANDIDATE = {
  curated_recipe_id: 7, name: 'Kuřecí salát', description: '',
  food_category: '', preparation_time: 15, calories: 420, why: null,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={[`/plan/12/recept/${MEAL_ID}`]}>
          <Routes>
            <Route path="/plan/:id/recept/:mealId" element={<RecipePage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { qc, invalidateSpy };
}

describe('RecipePage refine chat integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: { data: RECIPE } });
  });

  it('opens the chat from the Vyměnit recept button', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Vyměnit recept' }));
    expect(screen.getByPlaceholderText('Napište, na co máte chuť…')).toBeInTheDocument();
  });

  it('an accepted swap updates caches and closes the chat', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: null, hint_matched: true,
    });
    vi.mocked(refineAccept).mockResolvedValue({
      replaced: true, recipe: { ...RECIPE, name: 'Kuřecí salát' },
    });
    const { qc, invalidateSpy } = renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Vyměnit recept' }));
    await userEvent.type(
      screen.getByPlaceholderText('Napište, na co máte chuť…'), 'něco s kuřecím',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Odeslat' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Použít tento recept' }));

    expect(await screen.findByText('Recept byl vyměněn.')).toBeInTheDocument();
    expect((qc.getQueryData(['recipe', MEAL_ID]) as any).name).toBe('Kuřecí salát');
    // Both the plan AND the cooked-state query must refresh, else the swapped
    // meal can show a stale "Uvařeno" badge back on the plan.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['plan', '12'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['mealInstances', '12'] });
    // Chat panel closed after accept.
    expect(screen.queryByPlaceholderText('Napište, na co máte chuť…')).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/pages/RecipePage.refine.test.tsx`
Expected: FAIL — chat placeholder not found (old hint panel still renders)

- [ ] **Step 3: Rewire RecipePage**

In `frontend/src/pages/RecipePage.tsx`:

1. Replace the import `import { replaceRecipe } from '@/lib/replaceRecipe';` with `import { RecipeRefineChat } from '@/components/recipe/RecipeRefineChat';`.
2. Delete the old panel state and handler (lines 30-71: `hint`, `pending`, `noAlternative`, `closePanel`, `handleReplace`) keeping only `panelOpen`:

```tsx
  // Conversational replace-recipe swap. See
  // docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
  const [panelOpen, setPanelOpen] = useState(false);

  const handleAccepted = (recipe: Record<string, unknown>) => {
    queryClient.setQueryData(['recipe', mealId], recipe);
    queryClient.invalidateQueries({ queryKey: ['plan', id] });
    // The swap resets MealInstance.is_cooked server-side; PlanView derives
    // its cooked badges from this separate query, so it must refresh too.
    queryClient.invalidateQueries({ queryKey: ['mealInstances', id] });
    setPanelOpen(false);
    toast.success('Recept byl vyměněn.');
  };
```

3. Replace the whole panel JSX block (the `{/* Replace-recipe swap */}` div, lines 213-259) with:

```tsx
        {/* Conversational replace-recipe swap */}
        <div className="mb-12">
          {!panelOpen ? (
            <button
              onClick={() => setPanelOpen(true)}
              className="flex items-center gap-2 px-5 h-11 bg-card border border-line rounded-xl text-[10px] font-black uppercase tracking-widest text-ink hover:border-green/50 transition-colors"
            >
              <RefreshCw size={14} className="text-green" /> Vyměnit recept
            </button>
          ) : (
            <RecipeRefineChat
              mealId={mealId!}
              onAccepted={handleAccepted}
              onClose={() => setPanelOpen(false)}
            />
          )}
        </div>
```

4. Delete the retired files:

```bash
git rm frontend/src/pages/RecipePage.replace.test.tsx frontend/src/lib/replaceRecipe.ts frontend/src/lib/replaceRecipe.test.ts
```

- [ ] **Step 4: Run page tests + typecheck**

Run: `cd frontend && npx vitest run src/pages/RecipePage.refine.test.tsx && npx tsc --noEmit`
Expected: tests PASS, tsc clean (any leftover `replaceRecipe` reference fails here)

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src
git commit -m "feat(refine-chat): RecipePage opens the chat; retire one-shot hint panel"
```

---

### Task 8: Full verification

- [ ] **Step 1: Full backend suite for the app**

Run: `python -m pytest diet_planner/ -v`
Expected: all PASS (note per CI memory: local runs may hit `.env`-related flakes CI doesn't — if a failure looks unrelated to this diff, verify against the CI gate on the PR)

- [ ] **Step 2: Full frontend suite + typecheck**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all PASS

- [ ] **Step 3: Verify no stray references to the removed client**

Run: `grep -rn "replaceRecipe" frontend/src/`
Expected: no output

- [ ] **Step 4: Commit any stragglers and hand off**

```bash
git status --short   # expect clean
```

Open a PR to `develop` (CI test gate runs backend + frontend). After merge and prod deploy (via `prod` branch), run `/qa-prod` covering: open a recipe → Vyměnit recept → chat turn shows a candidate + Czech question → second turn changes candidate → accept → plan shows the new dish, cooked badge cleared.

---

## Plan self-review notes

- **Spec coverage:** preview/accept modes (Tasks 3-4), one combined LLM call (Task 1), never-raise degradation (Tasks 1, 3), 8-user-message cap server (Tasks 1, 3) + UI (Task 6), implicit reject-on-type (Task 6), honest unmatched phrasing in-chat (Task 6), no-alternatives + restart (Task 6), cache swap + invalidations on accept (Task 7), Czech copy with EN glosses (Task 6 table), out-of-scope items untouched.
- **`hint_matched` semantics** intentionally mirror the replace endpoint so the two views stay conceptually identical.
- **Private-helper imports** (`_coerce_facets`, `_recipe_ingredient_tokens`, …) are within-app reuse, consistent with how the codebase already shares these modules.
