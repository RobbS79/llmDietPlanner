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


class PromoteTest(TestCase):
    def test_promote_skips_nutrition_blocked_and_uncomputed(self):
        base = dict(ingredients=[{'name': 'x', 'quantity': 1, 'unit': 'g', 'canonical': 'chicken-breast'}], base_servings=1)
        ok = CuratedRecipe.objects.create(name_cs='ok', base_nutrition={'calories': 1, 'protein': 0, 'carbs': 0, 'fat': 0, 'source': 'computed'}, **base)
        blocked = CuratedRecipe.objects.create(name_cs='blocked', nutrition_blockers=[{'reason': 'no_density'}], **base)
        legacy = CuratedRecipe.objects.create(name_cs='legacy', base_nutrition={'calories': 500}, **base)
        out = StringIO()
        call_command('promote_curated_recipes', stdout=out)
        self.assertEqual(CuratedRecipe.objects.get(pk=ok.pk).status, CuratedRecipe.Status.PUBLISHED)
        self.assertEqual(CuratedRecipe.objects.get(pk=blocked.pk).status, CuratedRecipe.Status.DRAFT)
        self.assertEqual(CuratedRecipe.objects.get(pk=legacy.pk).status, CuratedRecipe.Status.DRAFT)
        self.assertIn('skipped_nutrition=2', out.getvalue())


class PromptTest(TestCase):
    def test_curation_prompt_no_longer_asks_for_base_nutrition(self):
        from diet_planner.llm_service import GeminiService
        with patch('diet_planner.llm_service.genai.GenerativeModel') as gm:
            gm.return_value.generate_content.return_value.text = '{"name_cs": "x"}'
            GeminiService().curate_recipe_to_czech(source_title='t', source_material='m', source_url='u', source_lang_hint='')
            prompt = gm.return_value.generate_content.call_args.args[0]
        self.assertNotIn('base_nutrition', prompt)
        self.assertIn('base_servings', prompt)
