"""Web recipe acquisition: models, source discovery, research job runner.

Spec: docs/superpowers/specs/2026-07-27-chat-recipe-acquisition-design.md.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from diet_planner.models import CuratedRecipe, RecipeResearchJob
from diet_planner.services.recipe_retrieval import eligible_recipes_for_slot
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

    @patch('diet_planner.services.recipe_research.curate_from_source')
    @patch('diet_planner.services.recipe_research.discover_recipe_sources')
    def test_reused_published_recipe_missing_slot_falls_through(self, disc, curate):
        # Published, but doesn't cover the requested slot and isn't ours to
        # amend -> must not be served (accept would 400 on meal_type gate);
        # the job should fall through to the next source instead.
        existing = make_recipe(
            name_cs='Publikovaná večeře', source_url='https://known.example/r',
            meal_types=['dinner'],
        )
        disc.return_value = [
            {'url': 'https://known.example/r', 'name': 'Known'},
            {'url': 'https://curry.example/r', 'name': 'Curry Example'},
        ]
        skipped = CurationResult(source_url='https://known.example/r')
        skipped.ok = True
        skipped.skipped = True
        curate.side_effect = [
            skipped,
            _ok_result('https://curry.example/r', self._draft()),
        ]
        recipe_research.run_research_job(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, RecipeResearchJob.Status.READY)
        self.assertNotEqual(self.job.result_recipe_id, existing.id)

    @patch('diet_planner.services.recipe_research.curate_from_source')
    @patch('diet_planner.services.recipe_research.discover_recipe_sources')
    def test_reused_own_draft_missing_slot_is_amended(self, disc, curate):
        # Our own prior chat_web draft: we own it, so it's fine to append the
        # requested slot rather than skip a recipe we could otherwise reuse.
        existing = make_recipe(
            name_cs='Můj dřívější nález', source_url='https://known.example/r',
            meal_types=['dinner'], status=CuratedRecipe.Status.DRAFT,
            origin=CuratedRecipe.Origin.CHAT_WEB, created_for_user=self.user,
        )
        disc.return_value = [{'url': 'https://known.example/r', 'name': 'Known'}]
        skipped = CurationResult(source_url='https://known.example/r')
        skipped.ok = True
        skipped.skipped = True
        curate.return_value = skipped
        recipe_research.run_research_job(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, RecipeResearchJob.Status.READY)
        self.assertEqual(self.job.result_recipe_id, existing.id)
        existing.refresh_from_db()
        self.assertIn('lunch', existing.meal_types)

    @patch('diet_planner.services.recipe_research.curate_from_source')
    @patch('diet_planner.services.recipe_research.discover_recipe_sources')
    def test_curate_from_source_crash_is_caught(self, disc, curate):
        # Core never-raises contract: any exception mid-pipeline must end the
        # job FAILED/error, not escape run_research_job.
        disc.return_value = [{'url': 'https://curry.example/r', 'name': 'Curry Example'}]
        curate.side_effect = RuntimeError('boom')
        result = recipe_research.run_research_job(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(result, {'status': 'failed', 'reason': 'error'})
        self.assertEqual(self.job.status, RecipeResearchJob.Status.FAILED)
        self.assertEqual(self.job.fail_reason, 'error')


class GoalResolutionTest(TestCase):
    """A HARD gate (dietary tags) can't be checked without the goal, so a job
    whose goal can't be resolved must hard-fail rather than silently skip it."""

    def test_missing_goal_hard_fails(self):
        user = get_user_model().objects.create(username='bezcile')
        job = RecipeResearchJob.objects.create(
            user=user, meal_identifier='999999:1:lunch:0', query='cokoliv',
        )
        recipe_research.run_research_job(job.id)
        job.refresh_from_db()
        self.assertEqual(job.status, RecipeResearchJob.Status.FAILED)
        self.assertEqual(job.fail_reason, 'error')

    def test_malformed_meal_identifier_hard_fails(self):
        user = get_user_model().objects.create(username='divnyid')
        job = RecipeResearchJob.objects.create(
            user=user, meal_identifier='not-an-identifier', query='cokoliv',
        )
        recipe_research.run_research_job(job.id)
        job.refresh_from_db()
        self.assertEqual(job.status, RecipeResearchJob.Status.FAILED)
        self.assertEqual(job.fail_reason, 'error')
