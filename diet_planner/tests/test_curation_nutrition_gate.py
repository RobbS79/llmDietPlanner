"""Curation computes base_nutrition from the table; anything it cannot compute
blocks promotion instead of shipping a guess."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services import recipe_curation
from diet_planner.services.recipe_curation import apply_nutrition
from diet_planner.tests.factories import make_canonical


def _canon(name, slug, name_cs, **nut):
    return make_canonical(name, slug=slug, name_cs=name_cs, kcal_per_100g=nut.get('kcal'), protein_per_100g=nut.get('protein', 0),
                          carbs_per_100g=nut.get('carbs', 0), fat_per_100g=nut.get('fat', 0),
                          density_g_per_ml=nut.get('density'), avg_piece_weight_g=nut.get('piece'),
                          category=nut.get('category', 'other'))


def _curated(**overrides):
    payload = {
        "name_cs": "Kuře s rýží", "name_en": "Chicken with rice", "description": "Jednoduché.",
        "meal_types": ["lunch"], "cuisine": "czech", "difficulty": "easy", "dietary_tags": [],
        "ingredients": [
            {"name": "kuřecí prsa", "quantity": 400, "unit": "g"},
            {"name": "rýže", "quantity": 200, "unit": "g"},
        ],
        "instructions": [{"text": "Uvař rýži, opeč kuře."}],
        "base_servings": 2,
        "base_nutrition": {"calories": 1, "protein": 1, "carbs": 1, "fat": 1},   # Gemini's guess is ignored
        "prep_time": 10, "cook_time": 20,
    }
    payload.update(overrides)
    return payload


class ApplyNutritionTest(TestCase):
    def setUp(self):
        _canon('Chicken breast', 'chicken-breast', 'kuřecí prsa', kcal=165, protein=31, fat=3.6, category='meat')
        _canon('Rice basmati', 'rice-basmati', 'rýže', kcal=360, protein=7, carbs=79, fat=0.6, category='grains')
        recipe_curation.clear_resolver_cache()

    def test_complete_recipe_gets_computed_base_nutrition(self):
        fields = recipe_curation.build_recipe_fields(_curated(), source_url='u', source_name='s')
        self.assertEqual(fields['base_nutrition'], {})
        blockers = apply_nutrition(fields, dish_role='main')
        self.assertEqual(blockers, [])
        self.assertEqual(fields['base_nutrition']['calories'], 660 + 720)
        self.assertEqual(fields['base_nutrition']['source'], 'computed')
        self.assertEqual(fields['nutrition_blockers'], [])

    def test_unresolved_or_untabled_line_blocks(self):
        fields = recipe_curation.build_recipe_fields(
            _curated(ingredients=[{"name": "kuřecí prsa", "quantity": 400, "unit": "g"},
                                  {"name": "dračí ovoce", "quantity": 100, "unit": "g"}]),
            source_url='u', source_name='s')
        blockers = apply_nutrition(fields, dish_role='main')
        self.assertEqual(blockers[0]['reason'], 'no_canonical')
        self.assertEqual(fields['base_nutrition'], {})
        self.assertEqual(fields['nutrition_blockers'], blockers)

    def test_implausible_portion_blocks_with_reason(self):
        fields = recipe_curation.build_recipe_fields(
            _curated(ingredients=[{"name": "kuřecí prsa", "quantity": 5000, "unit": "g"}], base_servings=1),
            source_url='u', source_name='s')
        blockers = apply_nutrition(fields, dish_role='main')
        self.assertEqual(blockers[0]['reason'], 'implausible')
        self.assertGreater(blockers[0]['per_portion_kcal'], 1500)
        self.assertEqual(fields['base_nutrition']['source'], 'computed')   # kept, but blocked


    def test_zero_kcal_recipe_blocks(self):
        for ingredients in ([], [{"name": "sůl", "quantity": None, "unit": ""}]):
            fields = {"ingredients": ingredients, "base_servings": 2}
            blockers = apply_nutrition(fields, dish_role='main')
            self.assertEqual(len(blockers), 1, ingredients)
            self.assertEqual(blockers[0]['reason'], 'implausible')
            self.assertEqual(blockers[0]['detail'], 'no quantified ingredients')

    def test_required_line_blocks_even_when_a_same_name_line_is_optional(self):
        fields = {"base_servings": 2, "ingredients": [
            {"name": "kuřecí prsa", "quantity": 400, "unit": "g", "canonical": "chicken-breast"},
            {"name": "dračí ovoce", "quantity": 100, "unit": "g", "optional": True},
            {"name": "dračí ovoce", "quantity": 100, "unit": "g"},
        ]}
        blockers = apply_nutrition(fields, dish_role='main')
        self.assertEqual([(b['reason'], b['optional']) for b in blockers], [('no_canonical', False)])
        self.assertEqual(fields['base_nutrition'], {})

    def test_low_computed_portion_is_advisory_not_blocked(self):
        # 12 egg muffins, 1021 kcal total = 85 kcal each: below the breakfast
        # floor, but a real small portion, not a basis error.
        _canon('Egg', 'egg', 'vejce', kcal=143, protein=12.6, carbs=0.7, fat=9.5, category='eggs')
        fields = {"base_servings": 12, "ingredients": [
            {"name": "vejce", "quantity": 714, "unit": "g", "canonical": "egg"}]}
        blockers = apply_nutrition(fields, dish_role='breakfast')
        self.assertEqual(blockers, [])
        self.assertEqual(fields['base_nutrition']['calories'], 1021)
        self.assertEqual(fields['base_nutrition']['source'], 'computed')

    def test_ceiling_blocker_detail_names_the_ceiling(self):
        fields = {"base_servings": 1, "ingredients": [
            {"name": "kuřecí prsa", "quantity": 5000, "unit": "g", "canonical": "chicken-breast"}]}
        blockers = apply_nutrition(fields, dish_role='main')
        self.assertEqual(blockers[0]['reason'], 'implausible')
        self.assertIn('ceiling', blockers[0]['detail'])


class CurateFromSourceTest(TestCase):
    def setUp(self):
        _canon('Chicken breast', 'chicken-breast', 'kuřecí prsa', kcal=165, protein=31, fat=3.6, category='meat')
        _canon('Rice basmati', 'rice-basmati', 'rýže', kcal=360, protein=7, carbs=79, fat=0.6, category='grains')
        recipe_curation.clear_resolver_cache()

    def _curate(self, curated):
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = curated
            gem.return_value.classify_dishes.side_effect = Exception('no classifier in tests')
            return recipe_curation.curate_from_source(
                {"source_url": "https://example.test/kure", "source_name": "Example"}, run_judge=False)

    def test_saved_recipe_carries_computed_nutrition(self):
        r = self._curate(_curated())
        self.assertTrue(r.ok, r.error)
        rec = CuratedRecipe.objects.get(source_url="https://example.test/kure")
        self.assertEqual(rec.base_nutrition['source'], 'computed')
        self.assertEqual(rec.nutrition_blockers, [])

    def test_blocked_recipe_is_saved_as_draft_with_blockers(self):
        r = self._curate(_curated(ingredients=[{"name": "dračí ovoce", "quantity": 100, "unit": "g"}]))
        self.assertTrue(r.ok, r.error)
        rec = CuratedRecipe.objects.get(source_url="https://example.test/kure")
        self.assertEqual(rec.status, CuratedRecipe.Status.DRAFT)
        self.assertEqual(rec.nutrition_blockers[0]['reason'], 'no_canonical')
        self.assertEqual(rec.base_nutrition, {})


_COMPUTED = {'calories': 600, 'protein': 30, 'carbs': 70, 'fat': 20, 'source': 'computed'}
_MAPPED = dict(ingredients=[{'name': 'x', 'quantity': 1, 'unit': 'g', 'canonical': 'chicken-breast'}], base_servings=1)


class PromoteTest(TestCase):
    def test_promote_skips_nutrition_blocked_and_uncomputed(self):
        base = dict(ingredients=[{'name': 'x', 'quantity': 1, 'unit': 'g', 'canonical': 'chicken-breast'}], base_servings=1)
        ok = CuratedRecipe.objects.create(name_cs='ok', base_nutrition=_COMPUTED, **base)
        blocked = CuratedRecipe.objects.create(name_cs='blocked', nutrition_blockers=[{'reason': 'no_density'}], **base)
        legacy = CuratedRecipe.objects.create(name_cs='legacy', base_nutrition={'calories': 500}, **base)
        out = StringIO()
        call_command('promote_curated_recipes', stdout=out)
        self.assertEqual(CuratedRecipe.objects.get(pk=ok.pk).status, CuratedRecipe.Status.PUBLISHED)
        self.assertEqual(CuratedRecipe.objects.get(pk=blocked.pk).status, CuratedRecipe.Status.DRAFT)
        self.assertEqual(CuratedRecipe.objects.get(pk=legacy.pk).status, CuratedRecipe.Status.DRAFT)
        self.assertIn('skipped_nutrition=2', out.getvalue())

    def test_ids_limits_promotion_to_listed_drafts(self):
        a = CuratedRecipe.objects.create(name_cs='a', base_nutrition=_COMPUTED, **_MAPPED)
        b = CuratedRecipe.objects.create(name_cs='b', base_nutrition=_COMPUTED, **_MAPPED)
        c = CuratedRecipe.objects.create(name_cs='c', base_nutrition=_COMPUTED, **_MAPPED)
        call_command('promote_curated_recipes', '--ids', f'{a.pk},{c.pk}', stdout=StringIO())
        statuses = dict(CuratedRecipe.objects.values_list('pk', 'status'))
        self.assertEqual(statuses[a.pk], CuratedRecipe.Status.PUBLISHED)
        self.assertEqual(statuses[b.pk], CuratedRecipe.Status.DRAFT)
        self.assertEqual(statuses[c.pk], CuratedRecipe.Status.PUBLISHED)


class AdminPublishActionTest(TestCase):
    def test_mark_published_skips_uncomputed_and_blocked(self):
        from django.contrib import admin as django_admin
        from django.test import RequestFactory
        from diet_planner.admin import CuratedRecipeAdmin
        ok = CuratedRecipe.objects.create(name_cs='ok', base_nutrition=_COMPUTED, **_MAPPED)
        blocked = CuratedRecipe.objects.create(name_cs='blocked', base_nutrition=_COMPUTED,
                                               nutrition_blockers=[{'reason': 'no_density'}], **_MAPPED)
        legacy = CuratedRecipe.objects.create(name_cs='legacy', base_nutrition={'calories': 500}, **_MAPPED)
        model_admin = CuratedRecipeAdmin(CuratedRecipe, django_admin.site)
        with patch.object(model_admin, 'message_user') as msg:
            model_admin.mark_published(RequestFactory().post('/'), CuratedRecipe.objects.all())
        statuses = dict(CuratedRecipe.objects.values_list('pk', 'status'))
        self.assertEqual(statuses[ok.pk], CuratedRecipe.Status.PUBLISHED)
        self.assertEqual(statuses[blocked.pk], CuratedRecipe.Status.DRAFT)
        self.assertEqual(statuses[legacy.pk], CuratedRecipe.Status.DRAFT)
        self.assertIn('2 skipped', msg.call_args.args[1])


class PromptTest(TestCase):
    def test_curation_prompt_no_longer_asks_for_base_nutrition(self):
        from diet_planner.llm_service import GeminiService
        with patch('diet_planner.llm_service.genai.GenerativeModel') as gm:
            gm.return_value.generate_content.return_value.text = '{"name_cs": "x"}'
            GeminiService().curate_recipe_to_czech(source_title='t', source_material='m', source_url='u', source_lang_hint='')
            prompt = gm.return_value.generate_content.call_args.args[0]
        self.assertNotIn('base_nutrition', prompt)
        self.assertIn('base_servings', prompt)
