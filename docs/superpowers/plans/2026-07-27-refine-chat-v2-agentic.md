# Refine Chat v2 (Agentic + Web Recipe Acquisition) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the template-driven refine chat with a Gemini tool-loop agent that authors every reply, searches the corpus through code-enforced gates, and can research the web for brand-new recipes via a background Celery job.

**Architecture:** A new `refine_agent` service runs a ≤3-round Gemini function-calling loop with two tools: `search_corpus` (wraps the existing `eligible_recipes_for_slot` + `score_recipe`) and `research_web` (creates a `RecipeResearchJob` + enqueues Celery). The Celery task discovers source URLs and funnels them through the existing `curate_from_source` pipeline, saving drafts with `origin=chat_web, created_for_user=<user>`. The frontend renders LLM-authored `reply_text` and polls the job endpoint. Everything is behind `REFINE_CHAT_AGENT_ENABLED`; any agent failure falls back to the v1 facet path.

**Tech Stack:** Django 5.1 + DRF, Celery/Redis, `google-generativeai` (old SDK — function calling via `tools=[{function_declarations}]`, grounding via `tools='google_search_retrieval'` best-effort), React 18 + vitest.

**Spec:** `docs/superpowers/specs/2026-07-27-chat-recipe-acquisition-design.md`

**Conventions:** All LLM interaction must be injectable for tests (no network in CI — same pattern as `refine_conversation(generate=...)`). Run backend tests with `python -m pytest diet_planner/tests/... -v` from repo root. Frontend tests: `cd frontend && npx vitest run src/components/recipe/RecipeRefineChat.test.tsx`.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `diet_planner/models/curated.py` | modify | `CuratedRecipe.origin` + `created_for_user`; new `RecipeResearchJob` |
| `diet_planner/models/__init__.py` | modify | export `RecipeResearchJob` |
| `diet_planner/migrations/` | generate | additive migration |
| `diet_planner/services/recipe_retrieval.py` | modify | `enforce_mapping` param on `eligible_recipes_for_slot` |
| `diet_planner/services/recipe_research.py` | create | cap check, source discovery, `run_research_job` |
| `diet_planner/services/refine_agent.py` | create | tool-loop agent (`run_refine_turn`), Gemini session wrapper |
| `diet_planner/tasks.py` | modify | `research_recipe_task` |
| `diet_planner/views.py` | modify | agent wiring in `RecipeRefineView`, accept-pool extension, `RecipeResearchJobView` |
| `diet_planner/urls.py` | modify | `recipes/research/<int:job_id>/` route |
| `llm_diet_planner_project/settings.py` | modify | `REFINE_CHAT_AGENT_ENABLED` flag |
| `diet_planner/tests/test_recipe_research.py` | create | discovery, job runner, cap |
| `diet_planner/tests/test_refine_agent.py` | create | tool loop unit tests |
| `diet_planner/tests/test_recipe_refine_agent.py` | create | endpoint wiring, accept gate, job view |
| `frontend/src/lib/refineRecipe.ts` | modify | v2 response fields + `researchStatus()` |
| `frontend/src/components/recipe/RecipeRefineChat.tsx` | modify | reply_text rendering + polling state machine |
| `frontend/src/components/recipe/RecipeRefineChat.test.tsx` | modify | polling/reply tests |

---

### Task 1: Model changes — `origin`, `created_for_user`, `RecipeResearchJob`

**Files:**
- Modify: `diet_planner/models/curated.py`
- Modify: `diet_planner/models/__init__.py`
- Test: `diet_planner/tests/test_recipe_research.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `diet_planner/tests/test_recipe_research.py`:

```python
"""Web recipe acquisition: models, source discovery, research job runner.

Spec: docs/superpowers/specs/2026-07-27-chat-recipe-acquisition-design.md.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from diet_planner.models import CuratedRecipe, RecipeResearchJob
from diet_planner.tests.test_recipe_replace import make_recipe


class ChatWebFieldsTest(TestCase):
    def test_defaults_keep_existing_rows_curated_and_ownerless(self):
        r = make_recipe(name_cs='Obyčejný guláš')
        self.assertEqual(r.origin, CuratedRecipe.Origin.CURATED)
        self.assertIsNone(r.created_for_user)

    def test_chat_web_draft_carries_owner(self):
        user = get_user_model().objects.create(username='hledac')
        r = make_recipe(
            name_cs='Web nález', status=CuratedRecipe.Status.DRAFT,
            origin=CuratedRecipe.Origin.CHAT_WEB, created_for_user=user,
        )
        self.assertEqual(r.created_for_user, user)
        self.assertEqual(user.chat_recipes.count(), 1)


class RecipeResearchJobModelTest(TestCase):
    def test_lifecycle_fields(self):
        user = get_user_model().objects.create(username='hledac2')
        job = RecipeResearchJob.objects.create(
            user=user, meal_identifier='1:1:lunch:0', query='pravé thajské curry',
        )
        self.assertEqual(job.status, RecipeResearchJob.Status.QUEUED)
        self.assertIsNone(job.result_recipe)
        self.assertEqual(job.fail_reason, '')
        self.assertEqual(job.reply_text, '')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest diet_planner/tests/test_recipe_research.py -v`
Expected: FAIL — `ImportError: cannot import name 'RecipeResearchJob'`.

- [ ] **Step 3: Implement the model changes**

In `diet_planner/models/curated.py`, add to imports:

```python
from django.conf import settings as django_settings
```

Inside `CuratedRecipe`, after the `Status` choices class, add:

```python
    class Origin(models.TextChoices):
        CURATED = 'curated', 'Curated batch'
        CHAT_WEB = 'chat_web', 'Chat web research'
```

After the `status` field, add:

```python
    origin = models.CharField(
        max_length=10,
        choices=Origin.choices,
        default=Origin.CURATED,
        db_index=True,
        help_text="curated = batch pipeline; chat_web = user-triggered web research",
    )
    created_for_user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='chat_recipes',
        help_text="Requester of a chat_web draft; only their plan may use it pre-publish",
    )
```

At the end of the file, add:

```python
class RecipeResearchJob(models.Model):
    """One user-triggered web recipe research run, polled by the refine chat."""

    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        SEARCHING = 'searching', 'Searching'
        CURATING = 'curating', 'Curating'
        READY = 'ready', 'Ready'
        FAILED = 'failed', 'Failed'

    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='research_jobs',
    )
    meal_identifier = models.CharField(max_length=64)
    query = models.CharField(max_length=300)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True,
    )
    result_recipe = models.ForeignKey(
        CuratedRecipe, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='research_jobs',
    )
    fail_reason = models.CharField(
        max_length=60, blank=True,
        help_text="machine code: no_sources / all_sources_failed / gates_failed / error",
    )
    reply_text = models.TextField(
        blank=True, help_text="Czech chat line shown when the job finishes",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"research #{self.pk} [{self.status}] {self.query[:40]}"
```

In `diet_planner/models/__init__.py`, change the curated import block to:

```python
from .curated import (  # noqa: F401
    CuratedRecipe,
    RecipeResearchJob,
)
```

- [ ] **Step 4: Generate the migration**

Run: `python manage.py makemigrations diet_planner`
Expected: one new migration adding two fields to `curatedrecipe` and creating `reciperesearchjob`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest diet_planner/tests/test_recipe_research.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add diet_planner/models/ diet_planner/migrations/ diet_planner/tests/test_recipe_research.py
git commit -m "feat(refine-v2): CuratedRecipe origin/owner fields + RecipeResearchJob model"
```

---

### Task 2: `enforce_mapping` parameter on `eligible_recipes_for_slot`

The accept path must admit a user's own `chat_web` draft even when not fully catalog-mapped (spec decision 1) — via an explicit parameter, never by weakening the shared default.

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py:176-203`
- Test: `diet_planner/tests/test_recipe_research.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_recipe_research.py`:

```python
from diet_planner.services.recipe_retrieval import eligible_recipes_for_slot


class EnforceMappingParamTest(TestCase):
    def _unmapped_draft(self, **kw):
        return make_recipe(
            name_cs=kw.pop('name_cs', 'Nemapovaný nález'),
            status=CuratedRecipe.Status.DRAFT,
            origin=CuratedRecipe.Origin.CHAT_WEB,
            ingredients=[{'name': 'dračí ovoce', 'quantity': 1, 'unit': 'ks'}],
            **kw,
        )

    def test_default_still_excludes_unmapped(self):
        r = self._unmapped_draft()
        self.assertEqual(eligible_recipes_for_slot('lunch', set(), pool=[r]), [])

    def test_enforce_mapping_false_admits_unmapped(self):
        r = self._unmapped_draft(name_cs='Nemapovaný nález 2')
        out = eligible_recipes_for_slot('lunch', set(), pool=[r], enforce_mapping=False)
        self.assertEqual([x.id for x in out], [r.id])

    def test_other_gates_still_apply_when_mapping_relaxed(self):
        r = self._unmapped_draft(name_cs='Nemapovaný nález 3', meal_types=['breakfast'])
        self.assertEqual(
            eligible_recipes_for_slot('lunch', set(), pool=[r], enforce_mapping=False), [],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest diet_planner/tests/test_recipe_research.py -k EnforceMapping -v`
Expected: FAIL — `TypeError: eligible_recipes_for_slot() got an unexpected keyword argument 'enforce_mapping'`.

- [ ] **Step 3: Implement**

In `diet_planner/services/recipe_retrieval.py`, change the signature and the mapping check:

```python
def eligible_recipes_for_slot(
    slot: str,
    required_tags: Set[str],
    *,
    pool: Optional[List[CuratedRecipe]] = None,
    status: str = CuratedRecipe.Status.PUBLISHED,
    exclude_ids: Optional[Set[int]] = None,
    facets: Optional[PromptFacets] = None,
    enforce_mapping: bool = True,
) -> List[CuratedRecipe]:
    """Recipes that pass the HARD GATE for one slot (incl. prompt facets).

    `enforce_mapping=False` relaxes ONLY the catalog-mapping gate — used for a
    user's own chat_web drafts (spec 2026-07-27, decision 1). All other gates
    (slot, dietary, facets) always apply."""
```

and inside the loop replace:

```python
        if not r.is_catalog_mapped():
            continue
```

with:

```python
        if enforce_mapping and not r.is_catalog_mapped():
            continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest diet_planner/tests/test_recipe_research.py diet_planner/tests/test_recipe_retrieval.py -v`
(If `test_recipe_retrieval.py` doesn't exist, run the whole dir: `python -m pytest diet_planner/tests/ -k retrieval -v`.)
Expected: new tests PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_recipe_research.py
git commit -m "feat(refine-v2): opt-out mapping gate for own chat_web drafts"
```

---

### Task 3: `recipe_research` service — daily cap, source discovery, job runner

**Files:**
- Create: `diet_planner/services/recipe_research.py`
- Test: `diet_planner/tests/test_recipe_research.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_recipe_research.py`:

```python
from unittest.mock import patch

from diet_planner.services import recipe_research
from diet_planner.services.recipe_curation import CurationResult


class DailyCapTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='kapan')

    def test_cap_allows_first_five_then_blocks(self):
        for i in range(recipe_research.DAILY_CAP):
            self.assertTrue(recipe_research.can_start_research(self.user))
            RecipeResearchJob.objects.create(
                user=self.user, meal_identifier='1:1:lunch:0', query=f'q{i}',
            )
        self.assertFalse(recipe_research.can_start_research(self.user))

    def test_cap_is_per_user(self):
        other = get_user_model().objects.create(username='jiny')
        for i in range(recipe_research.DAILY_CAP):
            RecipeResearchJob.objects.create(
                user=other, meal_identifier='1:1:lunch:0', query=f'q{i}',
            )
        self.assertTrue(recipe_research.can_start_research(self.user))


class DiscoverSourcesTest(TestCase):
    def test_parses_json_and_filters_bad_urls(self):
        raw = ('```json\n[{"url": "https://site.cz/recept", "name": "Site"},'
               ' {"url": "ftp://bad", "name": "x"},'
               ' {"url": "https://site.cz/recept", "name": "dupe"},'
               ' {"name": "no url"}]\n```')
        out = recipe_research.discover_recipe_sources('thajské curry', generate=lambda p: raw)
        self.assertEqual(out, [{'url': 'https://site.cz/recept', 'name': 'Site'}])

    def test_llm_failure_returns_empty(self):
        def boom(prompt):
            raise RuntimeError('down')
        self.assertEqual(recipe_research.discover_recipe_sources('x', generate=boom), [])


def _ok_result(url, recipe):
    res = CurationResult(source_url=url)
    res.ok = True
    res.recipe = recipe
    return res


def _fail_result(url, error='fetch failed'):
    res = CurationResult(source_url=url)
    res.error = error
    return res


class RunResearchJobTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='hledac3')
        from diet_planner.models import DietaryGoal
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.job = RecipeResearchJob.objects.create(
            user=self.user, meal_identifier=f'{self.goal.id}:1:lunch:0',
            query='thajské zelené curry',
        )

    def _draft(self, **kw):
        """In-memory unsaved draft, as curate_from_source(persist=False) yields."""
        r = CuratedRecipe(
            name_cs=kw.pop('name_cs', 'Zelené curry'),
            meal_types=kw.pop('meal_types', ['dinner']),
            dietary_tags=kw.pop('dietary_tags', []),
            ingredients=[{'name': 'kokosové mléko', 'quantity': 400, 'unit': 'ml'}],
            instructions=[{'text': 'Vař.', 'time_min': 20, 'tip': None}],
            base_servings=2,
            source_url=kw.pop('source_url', 'https://curry.example/r'),
            source_name='Curry Example',
            status=CuratedRecipe.Status.DRAFT,
        )
        for k, v in kw.items():
            setattr(r, k, v)
        return r

    @patch('diet_planner.services.recipe_research.curate_from_source')
    @patch('diet_planner.services.recipe_research.discover_recipe_sources')
    def test_happy_path_saves_owned_draft_and_marks_ready(self, disc, curate):
        disc.return_value = [{'url': 'https://curry.example/r', 'name': 'Curry Example'}]
        curate.return_value = _ok_result('https://curry.example/r', self._draft())
        recipe_research.run_research_job(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, RecipeResearchJob.Status.READY)
        saved = self.job.result_recipe
        self.assertIsNotNone(saved.pk)
        self.assertEqual(saved.origin, CuratedRecipe.Origin.CHAT_WEB)
        self.assertEqual(saved.created_for_user, self.user)
        self.assertEqual(saved.status, CuratedRecipe.Status.DRAFT)
        # Requested slot is guaranteed present so the accept gate can pass.
        self.assertIn('lunch', saved.meal_types)
        self.assertIn(saved.name_cs, self.job.reply_text)
        # persist=False is mandatory — the runner owns the save.
        self.assertFalse(curate.call_args.kwargs.get('persist', True))

    @patch('diet_planner.services.recipe_research.curate_from_source')
    @patch('diet_planner.services.recipe_research.discover_recipe_sources')
    def test_falls_through_bad_sources_to_first_good(self, disc, curate):
        disc.return_value = [
            {'url': 'https://a.example/1', 'name': 'A'},
            {'url': 'https://b.example/2', 'name': 'B'},
        ]
        curate.side_effect = [
            _fail_result('https://a.example/1'),
            _ok_result('https://b.example/2', self._draft(source_url='https://b.example/2')),
        ]
        recipe_research.run_research_job(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, RecipeResearchJob.Status.READY)

    @patch('diet_planner.services.recipe_research.curate_from_source')
    @patch('diet_planner.services.recipe_research.discover_recipe_sources')
    def test_dietary_violation_is_gates_failed(self, disc, curate):
        # Vegan profile, recipe lacks the tag -> honest failure, never served.
        profile = self.user.profile
        profile.dietary_preferences = {'dietary_styles': ['vegan'], 'allergies': []}
        profile.save()
        disc.return_value = [{'url': 'https://curry.example/r', 'name': 'C'}]
        curate.return_value = _ok_result('https://curry.example/r', self._draft())
        recipe_research.run_research_job(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, RecipeResearchJob.Status.FAILED)
        self.assertEqual(self.job.fail_reason, 'gates_failed')
        self.assertTrue(self.job.reply_text)

    @patch('diet_planner.services.recipe_research.discover_recipe_sources')
    def test_no_sources_fails_honestly(self, disc):
        disc.return_value = []
        recipe_research.run_research_job(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, RecipeResearchJob.Status.FAILED)
        self.assertEqual(self.job.fail_reason, 'no_sources')

    @patch('diet_planner.services.recipe_research.curate_from_source')
    @patch('diet_planner.services.recipe_research.discover_recipe_sources')
    def test_existing_published_source_url_is_reused(self, disc, curate):
        existing = make_recipe(name_cs='Už máme', source_url='https://known.example/r')
        disc.return_value = [{'url': 'https://known.example/r', 'name': 'Known'}]
        skipped = CurationResult(source_url='https://known.example/r')
        skipped.ok = True
        skipped.skipped = True
        curate.return_value = skipped
        recipe_research.run_research_job(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, RecipeResearchJob.Status.READY)
        self.assertEqual(self.job.result_recipe_id, existing.id)
```

Note: if `self.user.profile` doesn't exist in the test factory, mirror how
`diet_planner/tests/` sets profiles elsewhere (grep `dietary_preferences` in
tests) — the intent of the test is a required-tag the draft lacks.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest diet_planner/tests/test_recipe_research.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'can_start_research'` etc.

- [ ] **Step 3: Implement `diet_planner/services/recipe_research.py`**

```python
"""
Chat-triggered web recipe acquisition (refine chat v2).

A RecipeResearchJob is created by the refine agent's `research_web` tool and
executed by `research_recipe_task`. Flow: discover candidate source URLs
(Gemini, Google-Search-grounded when the SDK/model supports it) -> run each
through the existing `curate_from_source` pipeline -> save the first success
as a draft owned by the requesting user (origin=chat_web).

Integrity policy (spec 2026-07-27, decision 1):
  * portion plausibility: HARD (curate_from_source enforces it)
  * attribution:          HARD (no fetched source page -> no recipe)
  * dietary tags:         HARD (checked here against the goal/profile)
  * catalog mapping:      SOFT (unmapped ingredients kept, simply unpriced)

Everything is fail-soft: the job ends `ready` or `failed`, never raises out.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable, Dict, List, Optional

from django.conf import settings
from django.utils import timezone

from diet_planner.models import CuratedRecipe, DietaryGoal, RecipeResearchJob
from diet_planner.services.recipe_curation import (
    _save_with_unique_slug,
    curate_from_source,
)
from diet_planner.services.recipe_retrieval import required_tags_for_goal

logger = logging.getLogger(__name__)

DAILY_CAP = 5
MAX_SOURCES = 5

_FAIL_REPLIES = {
    'no_sources': 'Bohužel jsem na webu nenašel žádný vhodný recept. Zkuste to prosím popsat jinak.',
    'all_sources_failed': 'Našel jsem pár receptů, ale žádný se nepodařilo spolehlivě zpracovat. Zkuste to prosím jinak nebo později.',
    'gates_failed': 'Recept jsem našel, ale neodpovídá vašim stravovacím omezením, takže ho nenabídnu.',
    'error': 'Při hledání receptu se něco pokazilo. Zkuste to prosím znovu.',
}


def can_start_research(user) -> bool:
    """True while the user is under DAILY_CAP jobs since local midnight."""
    today = timezone.localdate()
    used = RecipeResearchJob.objects.filter(user=user, created_at__date=today).count()
    return used < DAILY_CAP


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

_DISCOVERY_PROMPT = (
    "Find up to {n} real, currently reachable web pages with a full recipe for: "
    "\"{query}\". Prefer well-known recipe sites with schema.org/Recipe markup; "
    "any language is fine (it will be translated). Return ONLY a JSON array of "
    "objects: [{{\"url\": \"https://...\", \"name\": \"site or creator name\"}}]. "
    "Concrete recipe pages only — no category pages, no search results, no video-only pages."
)


def _default_discovery_generate(prompt: str) -> str:
    """Gemini call for URL discovery. Tries Google-Search grounding; on any SDK
    /model rejection falls back to an ungrounded call. Hallucinated URLs are
    harmless downstream: curate_from_source must successfully fetch and parse a
    page, so a dead link just gets skipped."""
    import google.generativeai as genai

    genai.configure(api_key=getattr(settings, 'GEMINI_API_KEY', None))
    model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash')
    try:
        model = genai.GenerativeModel(model_name, tools='google_search_retrieval')
        resp = model.generate_content(prompt)
        return getattr(resp, 'text', '') or ''
    except Exception as exc:
        logger.info("recipe_research: grounded discovery unavailable (%s), going ungrounded", exc)
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(prompt)
        return getattr(resp, 'text', '') or ''


def _strip_code_fence(text: str) -> str:
    t = (text or '').strip()
    if t.startswith('```'):
        t = t.split('\n', 1)[-1] if '\n' in t else t
        if t.endswith('```'):
            t = t[:-3]
        if t.lstrip().startswith('json'):
            t = t.lstrip()[4:]
    return t.strip()


def discover_recipe_sources(
    query: str,
    *,
    generate: Optional[Callable[[str], str]] = None,
) -> List[Dict[str, str]]:
    """Up to MAX_SOURCES {'url','name'} entries. Never raises; failure -> []."""
    gen = generate or _default_discovery_generate
    try:
        raw = gen(_DISCOVERY_PROMPT.format(n=MAX_SOURCES, query=query.strip()))
        data = json.loads(_strip_code_fence(raw))
    except Exception as exc:
        logger.warning("recipe_research: discovery failed for %r: %s", query, exc)
        return []
    out: List[Dict[str, str]] = []
    seen = set()
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        url = str(item.get('url') or '').strip()
        if not re.match(r'^https?://', url) or url in seen:
            continue
        seen.add(url)
        out.append({'url': url, 'name': str(item.get('name') or '').strip()})
        if len(out) >= MAX_SOURCES:
            break
    return out


# ---------------------------------------------------------------------------
# Job runner
# ---------------------------------------------------------------------------

def _slot_of(meal_identifier: str) -> str:
    parts = (meal_identifier or '').split(':')
    return parts[2] if len(parts) > 2 else 'lunch'


def _goal_of(job: RecipeResearchJob) -> Optional[DietaryGoal]:
    parts = (job.meal_identifier or '').split(':')
    try:
        return DietaryGoal.objects.get(id=int(parts[0]), user=job.user)
    except Exception:
        return None


def _finish(job: RecipeResearchJob, *, status: str, fail_reason: str = '',
            recipe: Optional[CuratedRecipe] = None, reply_text: str = '') -> None:
    job.status = status
    job.fail_reason = fail_reason
    job.result_recipe = recipe
    job.reply_text = reply_text or _FAIL_REPLIES.get(fail_reason, '')
    job.save(update_fields=['status', 'fail_reason', 'result_recipe', 'reply_text', 'updated_at'])


def run_research_job(job_id: int) -> Dict[str, str]:
    """Execute one research job end-to-end. Never raises; returns a small
    status dict for the Celery result backend."""
    try:
        job = RecipeResearchJob.objects.get(id=job_id)
    except RecipeResearchJob.DoesNotExist:
        return {'status': 'missing'}
    try:
        return _run(job)
    except Exception as exc:  # noqa: BLE001 — job must end in a terminal state
        logger.exception("recipe_research: job %s crashed: %s", job_id, exc)
        _finish(job, status=RecipeResearchJob.Status.FAILED, fail_reason='error')
        return {'status': 'failed', 'reason': 'error'}


def _run(job: RecipeResearchJob) -> Dict[str, str]:
    slot = _slot_of(job.meal_identifier)
    goal = _goal_of(job)
    required_tags = required_tags_for_goal(goal) if goal else set()

    job.status = RecipeResearchJob.Status.SEARCHING
    job.save(update_fields=['status', 'updated_at'])
    sources = discover_recipe_sources(job.query)
    if not sources:
        _finish(job, status=RecipeResearchJob.Status.FAILED, fail_reason='no_sources')
        return {'status': 'failed', 'reason': 'no_sources'}

    job.status = RecipeResearchJob.Status.CURATING
    job.save(update_fields=['status', 'updated_at'])

    saw_gate_failure = False
    for src in sources:
        result = curate_from_source(
            {'dish_name': job.query, 'source_url': src['url'], 'source_name': src['name']},
            persist=False,
        )
        if result.skipped:
            # Source already in corpus: reuse it if the requester may see it.
            existing = CuratedRecipe.objects.filter(source_url=src['url']).first()
            if existing and (
                existing.status == CuratedRecipe.Status.PUBLISHED
                or existing.created_for_user_id == job.user_id
            ):
                if not required_tags.issubset(set(existing.dietary_tags or [])):
                    saw_gate_failure = True
                    continue
                _finish(
                    job, status=RecipeResearchJob.Status.READY, recipe=existing,
                    reply_text=_ready_reply(existing),
                )
                return {'status': 'ready'}
            continue
        if not result.ok or result.recipe is None:
            continue

        recipe = result.recipe
        # Dietary tags are a HARD gate — accept would reject it anyway; fail
        # here with an honest reason instead of a dead-end card.
        if not required_tags.issubset(set(recipe.dietary_tags or [])):
            saw_gate_failure = True
            continue
        # Guarantee the requested slot so the accept gate can pass.
        if slot not in (recipe.meal_types or []):
            recipe.meal_types = list(recipe.meal_types or []) + [slot]

        recipe.origin = CuratedRecipe.Origin.CHAT_WEB
        recipe.created_for_user = job.user
        try:
            _save_with_unique_slug(recipe)
        except Exception as exc:  # noqa: BLE001
            logger.warning("recipe_research: save failed for %s: %s", src['url'], exc)
            continue
        _finish(
            job, status=RecipeResearchJob.Status.READY, recipe=recipe,
            reply_text=_ready_reply(recipe),
        )
        return {'status': 'ready'}

    reason = 'gates_failed' if saw_gate_failure else 'all_sources_failed'
    _finish(job, status=RecipeResearchJob.Status.FAILED, fail_reason=reason)
    return {'status': 'failed', 'reason': reason}


def _ready_reply(recipe: CuratedRecipe) -> str:
    src = f" (podle {recipe.source_name})" if recipe.source_name else ""
    return f"Našel jsem na webu recept: {recipe.name_cs}{src}. Mrkněte na návrh níže."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest diet_planner/tests/test_recipe_research.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/recipe_research.py diet_planner/tests/test_recipe_research.py
git commit -m "feat(refine-v2): web research service — cap, source discovery, job runner"
```

---

### Task 4: Celery task `research_recipe_task`

**Files:**
- Modify: `diet_planner/tasks.py` (add near the other `@shared_task`s, e.g. after `scrape_leaflet_task`)
- Test: `diet_planner/tests/test_recipe_research.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_recipe_research.py`:

```python
class ResearchTaskTest(TestCase):
    def test_task_delegates_to_runner(self):
        from diet_planner.tasks import research_recipe_task
        with patch('diet_planner.services.recipe_research.run_research_job') as run:
            run.return_value = {'status': 'ready'}
            out = research_recipe_task.run(123)
        run.assert_called_once_with(123)
        self.assertEqual(out, {'status': 'ready'})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest diet_planner/tests/test_recipe_research.py::ResearchTaskTest -v`
Expected: FAIL — `ImportError: cannot import name 'research_recipe_task'`.

- [ ] **Step 3: Implement in `diet_planner/tasks.py`**

```python
@shared_task(bind=True, max_retries=0)
def research_recipe_task(self, job_id: int) -> Dict[str, Any]:
    """Refine-chat web recipe research (spec 2026-07-27). No Celery retries:
    the runner is internally fail-soft and always leaves the job in a terminal
    ready/failed state the chat can render honestly."""
    from diet_planner.services import recipe_research
    return recipe_research.run_research_job(job_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest diet_planner/tests/test_recipe_research.py::ResearchTaskTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/tasks.py diet_planner/tests/test_recipe_research.py
git commit -m "feat(refine-v2): research_recipe_task celery entrypoint"
```

---

### Task 5: `refine_agent` service — the tool loop

**Files:**
- Create: `diet_planner/services/refine_agent.py`
- Test: `diet_planner/tests/test_refine_agent.py` (new)

The agent session is injectable: tests pass a `session_factory` producing a fake with scripted steps. The real session wraps `google-generativeai` chat + function calling and is NOT unit-tested (network); it is exercised in prod QA.

**Final-message contract:** the model's last message must be JSON `{"reply": "<czech text>", "candidate_id": <int|null>}`. `candidate_id` is honored only if it was returned by the last `search_corpus` call — the model cannot fabricate a card.

- [ ] **Step 1: Write the failing tests**

Create `diet_planner/tests/test_refine_agent.py`:

```python
"""Refine agent tool loop (refine chat v2).

Spec: docs/superpowers/specs/2026-07-27-chat-recipe-acquisition-design.md.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from diet_planner.models import RecipeResearchJob
from diet_planner.services import refine_agent
from diet_planner.tests.test_recipe_replace import make_recipe


class FakeSession:
    """Scripted agent session. Each entry is what send()/send_tool_result()
    should return next: {'text': ..., 'tool_call': ...}."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.tool_results = []

    def send_text(self, text):
        self.first_message = text
        return self.steps.pop(0)

    def send_tool_result(self, name, payload):
        self.tool_results.append((name, payload))
        return self.steps.pop(0)


def _final(reply, candidate_id=None):
    import json
    return {'tool_call': None,
            'text': json.dumps({'reply': reply, 'candidate_id': candidate_id})}


def _call(name, **args):
    return {'tool_call': {'name': name, 'args': args}, 'text': None}


class RefineAgentTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='agentik')
        self.recipe = make_recipe(name_cs='Kuřecí rizoto')

    def _turn(self, steps, **kw):
        session = FakeSession(steps)
        result = refine_agent.run_refine_turn(
            user=self.user,
            meal_identifier=kw.pop('meal_identifier', '1:1:lunch:0'),
            meal_type='lunch',
            current_meal={'name': 'Menemen', 'description': 'vejce s rajčaty'},
            required_tags=kw.pop('required_tags', set()),
            pool=kw.pop('pool', [self.recipe]),
            exclude_ids=set(),
            used_recipe_ids=set(),
            used_cuisines=[],
            messages=[{'role': 'user', 'text': 'něco jiného k obědu'}],
            session_factory=lambda system_prompt: session,
        )
        return result, session

    def test_plain_conversation_no_tools(self):
        result, session = self._turn([_final('Rád pomůžu — na co máte chuť?')])
        self.assertEqual(result.reply_text, 'Rád pomůžu — na co máte chuť?')
        self.assertIsNone(result.candidate)
        self.assertIsNone(result.research_job_id)
        # Current recipe context must reach the model.
        self.assertIn('Menemen', session.first_message)
        self.assertIn('lunch', session.first_message)

    def test_corpus_pick_resolves_candidate_from_tool_results(self):
        result, session = self._turn([
            _call('search_corpus', wanted_ingredients=['kuřecí']),
            _final('Co třeba Kuřecí rizoto?', candidate_id=self.recipe.id),
        ])
        self.assertEqual(result.candidate.id, self.recipe.id)
        name, payload = session.tool_results[0]
        self.assertEqual(name, 'search_corpus')
        self.assertEqual(payload['candidates'][0]['id'], self.recipe.id)

    def test_fabricated_candidate_id_is_dropped(self):
        result, _ = self._turn([
            _call('search_corpus'),
            _final('Co třeba tohle?', candidate_id=999999),
        ])
        self.assertIsNone(result.candidate)
        self.assertEqual(result.reply_text, 'Co třeba tohle?')

    def test_dietary_tags_always_reach_the_gate(self):
        # Pool recipe lacks the vegan tag -> tool must return zero candidates
        # no matter what the model asked for.
        result, session = self._turn(
            [
                _call('search_corpus', wanted_ingredients=['kuřecí']),
                _final('Nic veganského tu nemám.'),
            ],
            required_tags={'vegan'},
        )
        _, payload = session.tool_results[0]
        self.assertEqual(payload['candidates'], [])

    def test_research_web_creates_job_and_returns_id(self):
        result, session = self._turn([
            _call('research_web', query='pravý ramen'),
            _final('Hledám recept na webu, chvilku strpení…'),
        ])
        job = RecipeResearchJob.objects.get(id=result.research_job_id)
        self.assertEqual(job.user, self.user)
        self.assertEqual(job.query, 'pravý ramen')
        self.assertEqual(job.meal_identifier, '1:1:lunch:0')

    def test_cap_reached_is_reported_as_tool_error(self):
        from diet_planner.services import recipe_research
        for i in range(recipe_research.DAILY_CAP):
            RecipeResearchJob.objects.create(
                user=self.user, meal_identifier='1:1:lunch:0', query=f'q{i}',
            )
        result, session = self._turn([
            _call('research_web', query='pátý pokus'),
            _final('Dnes už jsme limit hledání vyčerpali.'),
        ])
        self.assertIsNone(result.research_job_id)
        _, payload = session.tool_results[0]
        self.assertEqual(payload.get('error'), 'cap_reached')
        # No sixth job row.
        self.assertEqual(RecipeResearchJob.objects.filter(user=self.user).count(),
                         recipe_research.DAILY_CAP)

    def test_tool_round_bound_forces_reply(self):
        # Model keeps calling tools; after MAX_TOOL_ROUNDS the loop must stop
        # and surface whatever text is available (fallback line).
        steps = [_call('search_corpus')] * (refine_agent.MAX_TOOL_ROUNDS + 1)
        result, _ = self._turn(steps)
        self.assertTrue(result.reply_text)  # never empty

    def test_unparseable_final_message_degrades_to_raw_text(self):
        result, _ = self._turn([{'tool_call': None, 'text': 'prostě text bez JSONu'}])
        self.assertEqual(result.reply_text, 'prostě text bez JSONu')
        self.assertIsNone(result.candidate)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest diet_planner/tests/test_refine_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: ... refine_agent`.

- [ ] **Step 3: Implement `diet_planner/services/refine_agent.py`**

```python
"""
Refine chat v2: agentic tool loop (spec 2026-07-27).

`run_refine_turn` drives one preview turn: Gemini (function calling) converses
about the CURRENT recipe and may call:

  * search_corpus  — top-5 pre-gated corpus candidates. Eligibility (slot,
    dietary, mapping) is computed IN CODE; the model only chooses among what
    the gate returns and can never fabricate a card (candidate ids are
    validated against the tool's own results).
  * research_web   — creates a RecipeResearchJob + enqueues the Celery task;
    the chat polls it separately.

The caller (RecipeRefineView) treats ANY exception here as "fall back to the
v1 facet path", so this module may raise freely on unexpected states.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Set

from django.conf import settings

from diet_planner.models import CuratedRecipe, RecipeResearchJob
from diet_planner.services import recipe_research
from diet_planner.services.recipe_retrieval import (
    eligible_recipes_for_slot,
    score_recipe,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
TOP_N = 5

_FALLBACK_REPLY = 'Omlouvám se, teď mi to nemyslí. Zkuste to prosím ještě jednou.'

_SYSTEM_PROMPT = (
    "Jsi přátelský kuchařský asistent služby Vařto. Pomáháš uživateli vybrat "
    "náhradu za JEDNO jídlo v jeho jídelníčku. Odpovídáš VŽDY česky, stručně "
    "(1–3 věty), přirozeně a konkrétně.\n"
    "Pravidla:\n"
    "1. Jídla smíš nabízet POUZE z výsledků nástroje search_corpus. Nikdy si "
    "recept nevymýšlej.\n"
    "2. Když v databázi nic vhodného není, nebo chce uživatel něco speciálního, "
    "zavolej research_web — a řekni uživateli, že hledáš na internetu (najde se "
    "to na pozadí, výsledek přijde do chatu).\n"
    "3. Nikdy nezmiňuj ceny ani dostupnost surovin.\n"
    "4. Nikdy netvrď, že jsi něco hledal, pokud jsi nástroj nezavolal.\n"
    "5. Respektuj uvedená stravovací omezení uživatele i v konverzaci.\n"
    "Poslední zpráva každého tahu MUSÍ být pouze JSON objekt: "
    '{"reply": "<tvá česká odpověď>", "candidate_id": <id z search_corpus nebo null>}.'
)

_SEARCH_CORPUS_DECL = {
    'name': 'search_corpus',
    'description': (
        'Search the curated recipe database for the current meal slot. Returns '
        'up to 5 eligible candidates. Dietary restrictions are enforced '
        'automatically; do not pass them.'
    ),
    'parameters': {
        'type': 'object',
        'properties': {
            'cuisines': {'type': 'array', 'items': {'type': 'string'},
                         'description': 'lowercase cuisine slugs'},
            'wanted_ingredients': {'type': 'array', 'items': {'type': 'string'}},
            'avoided_ingredients': {'type': 'array', 'items': {'type': 'string'}},
            'styles': {'type': 'array', 'items': {'type': 'string'},
                       'description': 'e.g. quick, comfort, light'},
            'emphases': {'type': 'array', 'items': {'type': 'string'},
                         'description': 'high_protein, low_carb, low_calorie, budget'},
        },
    },
}

_RESEARCH_WEB_DECL = {
    'name': 'research_web',
    'description': (
        'Start a background web search for a brand-new recipe not in the '
        'database. Use when the corpus cannot satisfy the request or the user '
        'asks for something special. Returns a job id; the result arrives in '
        'the chat later.'
    ),
    'parameters': {
        'type': 'object',
        'properties': {
            'query': {'type': 'string',
                      'description': 'what to search for, in Czech or English'},
        },
        'required': ['query'],
    },
}


@dataclass
class AgentTurn:
    reply_text: str
    candidate: Optional[CuratedRecipe] = None
    research_job_id: Optional[int] = None


class GeminiAgentSession:
    """Thin wrapper over google-generativeai chat + function calling. All SDK
    types stay inside this class so the loop is testable with a fake."""

    def __init__(self, system_prompt: str):
        import google.generativeai as genai

        genai.configure(api_key=getattr(settings, 'GEMINI_API_KEY', None))
        self._genai = genai
        model = genai.GenerativeModel(
            model_name=getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash'),
            system_instruction=system_prompt,
            tools=[{'function_declarations': [_SEARCH_CORPUS_DECL, _RESEARCH_WEB_DECL]}],
        )
        self._chat = model.start_chat()

    def send_text(self, text: str) -> Dict:
        return self._parse(self._chat.send_message(text))

    def send_tool_result(self, name: str, payload: Dict) -> Dict:
        part = self._genai.protos.Part(
            function_response=self._genai.protos.FunctionResponse(
                name=name, response={'result': payload},
            )
        )
        return self._parse(self._chat.send_message(part))

    @staticmethod
    def _parse(resp) -> Dict:
        try:
            parts = resp.candidates[0].content.parts
        except (AttributeError, IndexError):
            return {'tool_call': None, 'text': ''}
        for part in parts:
            fc = getattr(part, 'function_call', None)
            if fc is not None and getattr(fc, 'name', ''):
                return {'tool_call': {'name': fc.name, 'args': dict(fc.args or {})},
                        'text': None}
        try:
            text = resp.text or ''
        except Exception:
            text = ''
        return {'tool_call': None, 'text': text}


def _context_message(
    *, meal_type: str, current_meal: Dict, required_tags: Set[str],
    used_cuisines: Sequence[str], messages: List[Dict],
) -> str:
    transcript = '\n'.join(f"{m['role']}: {m['text']}" for m in messages)
    return (
        f"Slot: {meal_type}\n"
        f"Aktuální jídlo: {current_meal.get('name') or '(neznámé)'} — "
        f"{current_meal.get('description') or ''}\n"
        f"Stravovací omezení (vynucená systémem): "
        f"{', '.join(sorted(required_tags)) or 'žádná'}\n"
        f"Kuchyně už použité v plánu: {', '.join(used_cuisines) or 'žádné'}\n"
        f"Konverzace:\n{transcript}"
    )


def _tool_search_corpus(
    args: Dict, *, meal_type: str, required_tags: Set[str],
    pool: List[CuratedRecipe], exclude_ids: Set[int],
    used_recipe_ids: Set[int], used_cuisines: Sequence[str],
) -> Dict:
    """Execute search_corpus: hard gate in code, model-supplied soft criteria."""
    from diet_planner.services.prompt_facets import PromptFacets

    def _set(key):
        v = args.get(key)
        return {str(x).strip().lower() for x in v if str(x).strip()} if isinstance(v, (list, tuple)) else set()

    facets = PromptFacets(
        cuisines=_set('cuisines'),
        wanted_ingredients=_set('wanted_ingredients'),
        avoided_ingredients=_set('avoided_ingredients'),
        styles=_set('styles'),
        emphases=_set('emphases'),
    )
    active = None if facets.is_empty() else facets
    candidates = eligible_recipes_for_slot(
        meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=active,
    )
    if not candidates and active is not None:
        # Soft criteria too narrow — retry unsteered so the model can say so
        # honestly and still offer the best available dish.
        candidates = eligible_recipes_for_slot(
            meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=None,
        )
    ranked = sorted(
        candidates,
        key=lambda r: score_recipe(
            r, used_recipe_ids=used_recipe_ids, used_cuisines=used_cuisines, facets=active,
        ),
        reverse=True,
    )[:TOP_N]
    return {
        'candidates': [
            {
                'id': r.id,
                'name': r.name_cs,
                'description': r.description,
                'total_time': r.total_time or None,
                'calories': (r.base_nutrition or {}).get('calories'),
                'cuisine': r.cuisine,
                'dietary_tags': r.dietary_tags or [],
            }
            for r in ranked
        ],
    }


def _tool_research_web(args: Dict, *, user, meal_identifier: str):
    """Execute research_web: cap check + job creation + enqueue. Returns
    (payload_for_model, job_id_or_None)."""
    query = str(args.get('query') or '').strip()[:300]
    if not query:
        return {'error': 'empty_query'}, None
    if not recipe_research.can_start_research(user):
        return {'error': 'cap_reached',
                'detail': 'Deník limit hledání na webu je vyčerpán (5/den).'}, None
    job = RecipeResearchJob.objects.create(
        user=user, meal_identifier=meal_identifier, query=query,
    )
    from diet_planner.tasks import research_recipe_task
    research_recipe_task.delay(job.id)
    return {'job_id': job.id, 'status': 'queued'}, job.id


def _parse_final(text: str) -> Dict:
    """Final-message contract: JSON {reply, candidate_id}. A non-JSON reply
    degrades to plain text (reply=text, no candidate)."""
    from diet_planner.services.prompt_facets import _strip_code_fence
    stripped = _strip_code_fence(text or '')
    try:
        data = json.loads(stripped)
        if isinstance(data, dict) and isinstance(data.get('reply'), str):
            cid = data.get('candidate_id')
            return {'reply': data['reply'].strip(),
                    'candidate_id': cid if isinstance(cid, int) else None}
    except Exception:
        pass
    return {'reply': (text or '').strip(), 'candidate_id': None}


def run_refine_turn(
    *,
    user,
    meal_identifier: str,
    meal_type: str,
    current_meal: Dict,
    required_tags: Set[str],
    pool: List[CuratedRecipe],
    exclude_ids: Set[int],
    used_recipe_ids: Set[int],
    used_cuisines: Sequence[str],
    messages: List[Dict],
    session_factory: Optional[Callable[[str], object]] = None,
) -> AgentTurn:
    """One preview turn of the v2 agent. May raise — the caller falls back to
    the v1 facet path on any exception."""
    factory = session_factory or GeminiAgentSession
    session = factory(_SYSTEM_PROMPT)

    offered_ids: Set[int] = set()
    research_job_id: Optional[int] = None

    out = session.send_text(_context_message(
        meal_type=meal_type, current_meal=current_meal, required_tags=required_tags,
        used_cuisines=used_cuisines, messages=messages,
    ))
    for _ in range(MAX_TOOL_ROUNDS):
        call = out.get('tool_call')
        if not call:
            break
        name, args = call.get('name'), call.get('args') or {}
        if name == 'search_corpus':
            payload = _tool_search_corpus(
                args, meal_type=meal_type, required_tags=required_tags, pool=pool,
                exclude_ids=exclude_ids, used_recipe_ids=used_recipe_ids,
                used_cuisines=used_cuisines,
            )
            offered_ids = {c['id'] for c in payload['candidates']}
            out = session.send_tool_result(name, payload)
        elif name == 'research_web':
            payload, job_id = _tool_research_web(
                args, user=user, meal_identifier=meal_identifier,
            )
            if job_id is not None:
                research_job_id = job_id
            out = session.send_tool_result(name, payload)
        else:
            out = session.send_tool_result(name or 'unknown', {'error': 'unknown_tool'})

    final = _parse_final(out.get('text') or '')
    reply = final['reply'] or _FALLBACK_REPLY

    candidate = None
    cid = final['candidate_id']
    if cid is not None and cid in offered_ids:
        candidate = next((r for r in pool if r.id == cid), None)

    return AgentTurn(reply_text=reply, candidate=candidate,
                     research_job_id=research_job_id)
```

Note: `_parse_final` imports `_strip_code_fence` from `prompt_facets` (the
existing shared implementation) — `recipe_research.py` carries its own copy
only because it predates nothing; if you prefer, point `recipe_research` at
the `prompt_facets` helper too and delete its local copy.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest diet_planner/tests/test_refine_agent.py -v`
Expected: PASS (8 tests). Note the Celery enqueue in `test_research_web_creates_job_and_returns_id` — `research_recipe_task.delay` will try to reach Redis in CI. If it errors, patch it in the test OR (better) guard in `_tool_research_web`:

```python
    try:
        research_recipe_task.delay(job.id)
    except Exception:  # broker down — run inline as a last resort
        logger.warning("refine_agent: broker unavailable, running research inline")
        recipe_research.run_research_job(job.id)
```

With `CELERY_TASK_ALWAYS_EAGER` in test settings this is moot; check
`llm_diet_planner_project/settings.py` for the eager flag and patch `delay` in
tests if not set.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/refine_agent.py diet_planner/tests/test_refine_agent.py
git commit -m "feat(refine-v2): agentic tool loop with code-gated corpus search and web research"
```

---

### Task 6: Settings flag + wire the agent into `RecipeRefineView`

**Files:**
- Modify: `llm_diet_planner_project/settings.py` (next to `RECIPE_GROUNDING_ENABLED`, line ~385)
- Modify: `diet_planner/views.py` (`RecipeRefineView.post`, line ~812; `_accept`, line ~883)
- Test: `diet_planner/tests/test_recipe_refine_agent.py` (new)

- [ ] **Step 1: Add the flag**

In `llm_diet_planner_project/settings.py` after `RECIPE_GROUNDING_ENABLED`:

```python
REFINE_CHAT_AGENT_ENABLED = config('REFINE_CHAT_AGENT_ENABLED', default=False, cast=bool)
```

- [ ] **Step 2: Write the failing tests**

Create `diet_planner/tests/test_recipe_refine_agent.py`:

```python
"""Refine endpoint v2 wiring: agent behind flag, accept-pool extension, job view.

Spec: docs/superpowers/specs/2026-07-27-chat-recipe-acquisition-design.md.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from diet_planner.models import CuratedRecipe, DietaryGoal, DietaryPlan, RecipeResearchJob
from diet_planner.services.refine_agent import AgentTurn
from diet_planner.tests.test_recipe_replace import make_recipe


class RefineAgentEndpointBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='sefkuchar')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.current = make_recipe(name_cs='Menemen', source_url='https://ex.test/menemen')
        self.other = make_recipe(name_cs='Rizoto', source_url='https://ex.test/rizoto')
        from diet_planner.services.recipe_retrieval import scale_recipe_to_meal
        meal = scale_recipe_to_meal(self.current)
        self.meal_identifier = f'{self.goal.id}:1:lunch:0'
        meal['meal_identifier'] = self.meal_identifier
        self.plan = DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{'day_number': 1, 'lunch': meal, 'small_meals': [], 'snacks': []}],
            currency='CZK',
        )

    def _url(self):
        return reverse('diet_planner:recipe-refine',
                       kwargs={'meal_identifier': self.meal_identifier})


@override_settings(REFINE_CHAT_AGENT_ENABLED=True)
class AgentPreviewTest(RefineAgentEndpointBase):
    @patch('diet_planner.views.run_refine_turn')
    def test_v2_response_shape(self, turn):
        turn.return_value = AgentTurn(
            reply_text='Co třeba Rizoto?', candidate=self.other, research_job_id=None,
        )
        r = self.client.post(self._url(), {
            'messages': [{'role': 'user', 'text': 'něco jiného'}], 'rejected_ids': [],
        }, format='json')
        data = r.json()['data']
        self.assertEqual(data['reply_text'], 'Co třeba Rizoto?')
        self.assertEqual(data['candidate']['curated_recipe_id'], self.other.id)
        self.assertIsNone(data['research_job_id'])

    @patch('diet_planner.views.run_refine_turn')
    def test_agent_crash_falls_back_to_v1(self, turn):
        turn.side_effect = RuntimeError('LLM down')
        with patch('diet_planner.views.refine_conversation') as v1:
            from diet_planner.services.prompt_facets import PromptFacets
            v1.return_value = (PromptFacets(), None)
            r = self.client.post(self._url(), {
                'messages': [{'role': 'user', 'text': 'něco'}], 'rejected_ids': [],
            }, format='json')
        data = r.json()['data']
        self.assertNotIn('reply_text', data)          # v1 shape
        self.assertIn('candidate', data)

    @patch('diet_planner.views.run_refine_turn')
    def test_flag_off_serves_v1(self, turn):
        with override_settings(REFINE_CHAT_AGENT_ENABLED=False):
            with patch('diet_planner.views.refine_conversation') as v1:
                from diet_planner.services.prompt_facets import PromptFacets
                v1.return_value = (PromptFacets(), None)
                self.client.post(self._url(), {
                    'messages': [{'role': 'user', 'text': 'x'}], 'rejected_ids': [],
                }, format='json')
        turn.assert_not_called()


class AcceptChatDraftTest(RefineAgentEndpointBase):
    def _chat_draft(self, owner, name='Web nález'):
        return make_recipe(
            name_cs=name, status=CuratedRecipe.Status.DRAFT,
            origin=CuratedRecipe.Origin.CHAT_WEB, created_for_user=owner,
            source_url=f'https://web.test/{name}',
            ingredients=[{'name': 'dračí ovoce', 'quantity': 1, 'unit': 'ks'}],  # unmapped
        )

    def test_own_unmapped_chat_draft_is_acceptable(self):
        draft = self._chat_draft(self.user)
        r = self.client.post(self._url(), {'accept': draft.id}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['data']['replaced'])

    def test_foreign_chat_draft_is_rejected(self):
        stranger = get_user_model().objects.create(username='cizinec')
        draft = self._chat_draft(stranger, name='Cizí nález')
        r = self.client.post(self._url(), {'accept': draft.id}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_ordinary_draft_still_rejected(self):
        d = make_recipe(name_cs='Neveřejný', status=CuratedRecipe.Status.DRAFT,
                        source_url='https://ex.test/nev')
        r = self.client.post(self._url(), {'accept': d.id}, format='json')
        self.assertEqual(r.status_code, 400)


class ResearchJobViewTest(RefineAgentEndpointBase):
    def _job(self, **kw):
        return RecipeResearchJob.objects.create(
            user=kw.pop('user', self.user), meal_identifier=self.meal_identifier,
            query='ramen', **kw,
        )

    def _jurl(self, job):
        return reverse('diet_planner:recipe-research-job', kwargs={'job_id': job.id})

    def test_owner_sees_status_and_ready_candidate(self):
        draft = make_recipe(name_cs='Ramen z webu', status=CuratedRecipe.Status.DRAFT,
                            origin=CuratedRecipe.Origin.CHAT_WEB,
                            created_for_user=self.user,
                            source_url='https://web.test/ramen')
        job = self._job(status=RecipeResearchJob.Status.READY,
                        result_recipe=draft, reply_text='Našel jsem: Ramen z webu.')
        r = self.client.get(self._jurl(job))
        data = r.json()['data']
        self.assertEqual(data['status'], 'ready')
        self.assertEqual(data['candidate']['curated_recipe_id'], draft.id)
        self.assertEqual(data['reply_text'], 'Našel jsem: Ramen z webu.')

    def test_pending_job_has_no_candidate(self):
        job = self._job()
        data = self.client.get(self._jurl(job)).json()['data']
        self.assertEqual(data['status'], 'queued')
        self.assertIsNone(data['candidate'])

    def test_foreign_job_404(self):
        stranger = get_user_model().objects.create(username='slidil')
        job = self._job(user=stranger)
        self.assertEqual(self.client.get(self._jurl(job)).status_code, 404)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest diet_planner/tests/test_recipe_refine_agent.py -v`
Expected: FAIL — `ImportError` (`run_refine_turn` not imported in views), `NoReverseMatch` for the job route.

- [ ] **Step 4: Implement the view wiring**

In `diet_planner/views.py` imports, add:

```python
from .models import RecipeResearchJob
from .services.refine_agent import run_refine_turn
```

In `RecipeRefineView.post`, right after the `messages = clamp_messages(...)` /
`rejected` / `exclude_ids` block (views.py:827-832) and BEFORE the
`refine_conversation` call, insert:

```python
        if getattr(settings, 'REFINE_CHAT_AGENT_ENABLED', False):
            try:
                turn = run_refine_turn(
                    user=request.user,
                    meal_identifier=meal_identifier,
                    meal_type=ctx.meal_type,
                    current_meal=ctx.current_meal,
                    required_tags=required_tags,
                    pool=pool,
                    exclude_ids=exclude_ids,
                    used_recipe_ids=used_recipe_ids,
                    used_cuisines=used_cuisines,
                    messages=messages,
                )
                return Response({
                    "status": "success",
                    "data": {
                        "reply_text": turn.reply_text,
                        "candidate": (
                            _candidate_payload(turn.candidate, None)
                            if turn.candidate else None
                        ),
                        "research_job_id": turn.research_job_id,
                        "question": None,
                        "hint_matched": None,
                    },
                }, status=200)
            except Exception:
                # refine_agent_fallback: v1 path below still serves the turn.
                logger.warning("refine_agent_fallback", exc_info=True)
```

(`settings` is already imported in views.py — verify; if not, `from django.conf import settings`. `logger` likewise — reuse the module logger.)

In `RecipeRefineView._accept` (views.py:883), replace the candidates lookup with:

```python
        exclude_ids = {current_id} if current_id else set()
        candidates = eligible_recipes_for_slot(
            ctx.meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=None,
        )
        # Spec 2026-07-27 decision 1: the requester's own chat_web drafts are
        # acceptable without full catalog mapping (their unmapped ingredients
        # simply carry no price/deals data).
        own_drafts = list(CuratedRecipe.objects.filter(
            origin=CuratedRecipe.Origin.CHAT_WEB,
            created_for_user=request.user,
            status=CuratedRecipe.Status.DRAFT,
        ))
        candidates += eligible_recipes_for_slot(
            ctx.meal_type, required_tags, pool=own_drafts, exclude_ids=exclude_ids,
            facets=None, enforce_mapping=False,
        )
```

Add `RecipeResearchJobView` after `RecipeRefineView`:

```python
class RecipeResearchJobView(APIView):
    """Poll target for chat web-research jobs. Owner-only; foreign ids 404."""
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id: int) -> Response:
        try:
            job = RecipeResearchJob.objects.get(id=job_id, user=request.user)
        except RecipeResearchJob.DoesNotExist:
            return Response({"status": "error", "error": "Not found"}, status=404)
        candidate = None
        if job.status == RecipeResearchJob.Status.READY and job.result_recipe:
            candidate = _candidate_payload(job.result_recipe, None)
        return Response({
            "status": "success",
            "data": {
                "status": job.status,
                "reply_text": job.reply_text or None,
                "candidate": candidate,
            },
        }, status=200)
```

In `diet_planner/urls.py`, add BEFORE the `recipes/<str:meal_identifier>/...` routes (so `research` is never captured as a meal identifier):

```python
    path('recipes/research/<int:job_id>/', views.RecipeResearchJobView.as_view(), name='recipe-research-job'),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest diet_planner/tests/test_recipe_refine_agent.py diet_planner/tests/test_recipe_refine.py -v`
Expected: all PASS — v1 tests must stay green (flag defaults off).

- [ ] **Step 6: Commit**

```bash
git add llm_diet_planner_project/settings.py diet_planner/views.py diet_planner/urls.py diet_planner/tests/test_recipe_refine_agent.py
git commit -m "feat(refine-v2): agent wiring behind REFINE_CHAT_AGENT_ENABLED + job poll endpoint + accept gate for own chat drafts"
```

---

### Task 7: Frontend — API lib

**Files:**
- Modify: `frontend/src/lib/refineRecipe.ts`

- [ ] **Step 1: Extend the lib** (no standalone test — covered by component tests in Task 8)

In `frontend/src/lib/refineRecipe.ts`, extend `RefinePreviewResult` and add the poll call:

```typescript
export interface RefinePreviewResult {
  candidate: RefineCandidate | null;
  question: string | null;
  hint_matched: boolean | null;
  reason?: string;
  /** v2 agent fields — present iff REFINE_CHAT_AGENT_ENABLED on the backend. */
  reply_text?: string | null;
  research_job_id?: number | null;
}

export type ResearchJobStatus = 'queued' | 'searching' | 'curating' | 'ready' | 'failed';

export interface ResearchStatusResult {
  status: ResearchJobStatus;
  reply_text: string | null;
  candidate: RefineCandidate | null;
}

/** Poll one web-research job (v2). Owner-only on the backend. */
export async function researchStatus(jobId: number): Promise<ResearchStatusResult> {
  const res = await api.get(`/recipes/research/${jobId}/`);
  return res.data.data as ResearchStatusResult;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/refineRecipe.ts
git commit -m "feat(refine-v2): frontend API types + research job polling call"
```

---

### Task 8: Frontend — chat component (reply_text + polling)

**Files:**
- Modify: `frontend/src/components/recipe/RecipeRefineChat.tsx`
- Test: `frontend/src/components/recipe/RecipeRefineChat.test.tsx`

Behavior: when `reply_text` is present in the preview response, render it as
the assistant bubble (v2); otherwise keep the existing `assistantText`
template (v1 — flag off). When `research_job_id` arrives, show a persistent
searching bubble and poll every 5 s until ready/failed/5-minute timeout.

- [ ] **Step 1: Write the failing tests**

Open `frontend/src/components/recipe/RecipeRefineChat.test.tsx`, look at how
existing tests mock `@/lib/refineRecipe` (vi.mock) and render the component,
and add — following the file's existing mock/render helpers exactly:

```tsx
describe('v2 agent replies', () => {
  it('renders reply_text verbatim when present', async () => {
    mockedRefinePreview.mockResolvedValueOnce({
      candidate: null, question: null, hint_matched: null,
      reply_text: 'Menemen vám přijde snídaňový? Chcete něco vydatnějšího?',
      research_job_id: null,
    });
    // ...render, type 'Vypadá to jak snídaně', send...
    expect(await screen.findByText(/Chcete něco vydatnějšího/)).toBeInTheDocument();
  });

  it('starts polling when research_job_id returned and pops the card on ready', async () => {
    vi.useFakeTimers();
    mockedRefinePreview.mockResolvedValueOnce({
      candidate: null, question: null, hint_matched: null,
      reply_text: 'Hledám recept na webu…', research_job_id: 42,
    });
    mockedResearchStatus
      .mockResolvedValueOnce({ status: 'searching', reply_text: null, candidate: null })
      .mockResolvedValueOnce({
        status: 'ready',
        reply_text: 'Našel jsem: Pravý ramen.',
        candidate: { curated_recipe_id: 7, name: 'Pravý ramen', description: '',
                     food_category: '', preparation_time: 40, calories: 600, why: null },
      });
    // ...render, send a message...
    expect(await screen.findByText(/Hledám recept na webu/)).toBeInTheDocument();
    await vi.advanceTimersByTimeAsync(5_000);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(await screen.findByText(/Našel jsem: Pravý ramen/)).toBeInTheDocument();
    expect(screen.getByText('Pravý ramen')).toBeInTheDocument();  // card
    vi.useRealTimers();
  });

  it('renders failure reply_text and stops polling on failed', async () => {
    vi.useFakeTimers();
    mockedRefinePreview.mockResolvedValueOnce({
      candidate: null, question: null, hint_matched: null,
      reply_text: 'Hledám…', research_job_id: 43,
    });
    mockedResearchStatus.mockResolvedValueOnce({
      status: 'failed',
      reply_text: 'Bohužel jsem na webu nenašel žádný vhodný recept.',
      candidate: null,
    });
    // ...render, send...
    await vi.advanceTimersByTimeAsync(5_000);
    expect(await screen.findByText(/nenašel žádný vhodný recept/)).toBeInTheDocument();
    expect(mockedResearchStatus).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(mockedResearchStatus).toHaveBeenCalledTimes(1);  // stopped
    vi.useRealTimers();
  });
});
```

(Adapt `mockedRefinePreview` / `mockedResearchStatus` names and render calls to
the file's existing patterns; add `researchStatus` to the existing `vi.mock('@/lib/refineRecipe', ...)` factory.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/recipe/RecipeRefineChat.test.tsx`
Expected: new tests FAIL (reply_text ignored, no polling), old tests PASS.

- [ ] **Step 3: Implement**

In `RecipeRefineChat.tsx`:

1. Import: `import { useEffect, useRef, useState } from 'react';` and add
   `researchStatus` to the `@/lib/refineRecipe` import.

2. New state after the existing `useState` block:

```tsx
  const [researchJobId, setResearchJobId] = useState<number | null>(null);
  const [researching, setResearching] = useState(false);
  const researchStartedAt = useRef<number>(0);
```

3. In `send()`, replace the response-handling block (`if (!r.candidate) { ... } setCandidate(...); setMessages(...)`) with:

```tsx
      if (r.reply_text != null) {
        // v2 agent turn: LLM-authored reply; candidate/research are optional.
        setCandidate(r.candidate ?? null);
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', text: r.reply_text!, candidate: r.candidate ?? undefined },
        ]);
        if (r.research_job_id != null) {
          researchStartedAt.current = Date.now();
          setResearchJobId(r.research_job_id);
          setResearching(true);
        }
      } else if (!r.candidate) {
        setNoAlternatives(true);
      } else {
        setCandidate(r.candidate);
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: assistantText(r.candidate!, r.question, r.hint_matched),
            candidate: r.candidate!,
          },
        ]);
      }
```

4. Polling effect after the handlers:

```tsx
  useEffect(() => {
    if (researchJobId == null) return;
    const POLL_MS = 5_000;
    const TIMEOUT_MS = 5 * 60_000;
    let cancelled = false;
    const timer = setInterval(async () => {
      if (cancelled) return;
      if (Date.now() - researchStartedAt.current > TIMEOUT_MS) {
        setResearching(false);
        setResearchJobId(null);
        setMessages((prev) => [...prev, {
          role: 'assistant',
          text: 'Hledání trvá déle, než jsem čekal — recept se objeví ve vašich návrzích, jakmile bude hotový.',
        }]);
        return;
      }
      try {
        const s = await researchStatus(researchJobId);
        if (cancelled || (s.status !== 'ready' && s.status !== 'failed')) return;
        setResearching(false);
        setResearchJobId(null);
        if (s.status === 'ready' && s.candidate) {
          setCandidate(s.candidate);
          setMessages((prev) => [...prev, {
            role: 'assistant',
            text: s.reply_text ?? `Co třeba: ${s.candidate!.name}?`,
            candidate: s.candidate!,
          }]);
        } else {
          setMessages((prev) => [...prev, {
            role: 'assistant',
            text: s.reply_text ?? 'Recept se nepodařilo najít, zkuste to prosím jinak.',
          }]);
        }
      } catch {
        /* transient poll error — keep polling until timeout */
      }
    }, POLL_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [researchJobId]);
```

5. Searching bubble in the JSX, right after the messages `<ul>` (and keep chat input enabled):

```tsx
      {researching && (
        <div className="mr-8 flex items-center gap-2 rounded-xl bg-paper border border-line px-4 py-2 text-sm text-muted mb-4">
          <Loader2 size={14} className="animate-spin text-green" /> Hledám recept na webu…
        </div>
      )}
```

6. `reset()` additionally clears: `setResearchJobId(null); setResearching(false);`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/recipe/RecipeRefineChat.test.tsx && npx tsc --noEmit`
Expected: all PASS, typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/recipe/RecipeRefineChat.tsx frontend/src/components/recipe/RecipeRefineChat.test.tsx
git commit -m "feat(refine-v2): chat renders LLM replies + web-research polling"
```

---

### Task 9: Full verification + PR

- [ ] **Step 1: Full backend suite**

Run: `python -m pytest diet_planner/ billing/ analytics/ -v --tb=short 2>&1 | tail -30`
Expected: all pass (login_app stays quarantined per CI config).

- [ ] **Step 2: Full frontend suite + build**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass. (Do NOT run `vite build` on the dev box — it OOMs; CI covers it.)

- [ ] **Step 3: Flag-off smoke check**

Confirm `REFINE_CHAT_AGENT_ENABLED` defaults to `False` in settings and `.env.example`
mentions it (add the line `REFINE_CHAT_AGENT_ENABLED=False` if `.env.example` exists).

- [ ] **Step 4: Push branch + PR**

```bash
git push -u origin feature/refine-chat-v2-agentic
gh pr create --base develop --title "feat: refine chat v2 — agentic conversation + web recipe acquisition" --body "$(cat <<'EOF'
Implements docs/superpowers/specs/2026-07-27-chat-recipe-acquisition-design.md.

- Gemini tool-loop agent authors all chat replies (Czech); corpus candidates
  stay code-gated (slot/dietary/mapping enforced in eligible_recipes_for_slot).
- research_web tool -> RecipeResearchJob + Celery task -> existing
  curate_from_source pipeline -> draft CuratedRecipe (origin=chat_web,
  created_for_user), soft catalog mapping per spec decision 1.
- Frontend renders reply_text + polls the job endpoint; honest failure copy.
- All dark behind REFINE_CHAT_AGENT_ENABLED (default off).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

(Branch creation happens at execution start per the worktree/branch skill; if
work happened directly on develop, create the branch before pushing.)

---

## Post-merge rollout (operator checklist, not part of the code plan)

1. Merge PR → prod deploy from `prod` branch per usual flow; migration runs automatically.
2. Set `REFINE_CHAT_AGENT_ENABLED=true` on the DO app (squid-app) — same place as `RECIPE_GROUNDING_ENABLED`.
3. Run `/qa-prod` including one real web-research round trip on the QA account.
4. Watch logs for `refine_agent_fallback` frequency and research-job `failed` rate.
5. Kill switch: flag back to `false`.

## Self-review notes

- Spec coverage: data model (Task 1), mapping-gate parameter (Task 2), research
  service + cap + discovery (Task 3), Celery task (Task 4), tool loop (Task 5),
  flag + view wiring + accept extension + poll endpoint (Task 6), frontend lib
  (Task 7), chat UI + polling (Task 8), verification/rollout (Task 9 + checklist).
  Spec §"reply_text authored by the task's LLM step" is implemented as
  deterministic Czech templates in `recipe_research.py` — deliberate
  simplification, templates can't hallucinate; noted here as the one deviation.
- `_strip_code_fence`: use the `prompt_facets` one in `refine_agent` (see Task 5
  note) — do not leave a private cross-module import to `recipe_research`.
- Type consistency: `AgentTurn.candidate` is a `CuratedRecipe` instance;
  views serialize via `_candidate_payload(recipe, None)` — same as v1 accept.
  `RefinePreviewResult.reply_text` optional on the wire; frontend branches on
  its presence (v1/v2 compatibility).
