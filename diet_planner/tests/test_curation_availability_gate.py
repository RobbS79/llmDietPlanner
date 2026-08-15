"""Integration test: the availability gate rejects unshoppable new recipes."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from diet_planner.models import Availability, CuratedRecipe
from diet_planner.services import recipe_curation
from diet_planner.tests.factories import make_canonical

_CURATED = {
    "name_cs": "Salát s tahini",
    "name_en": "Tahini salad",
    "description": "Svěží salát.",
    "meal_types": ["lunch"],
    "cuisine": "mediterranean",
    "difficulty": "easy",
    "dietary_tags": [],
    "ingredients": [
        {"name": "sůl", "quantity": 5, "unit": "g"},
        {"name": "tahini", "quantity": 30, "unit": "g"},
    ],
    "instructions": [{"text": "Smíchej suroviny a podávej."}],
    "base_servings": 2,
    "base_nutrition": {"calories": 400},
    "prep_time": 10,
    "cook_time": 0,
}


class CurationAvailabilityGateTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)
        make_canonical('tahini', availability=Availability.SPECIALTY)

    def _run(self, **kwargs):
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = _CURATED
            return recipe_curation.curate_from_source(
                {"source_url": "https://example.test/salat", "source_name": "Example"},
                run_judge=False,
                **kwargs,
            )

    @override_settings(AVAILABILITY_GATE_ENABLED=True)
    def test_rejects_specialty_ingredient(self):
        result = self._run()
        self.assertFalse(result.ok)
        self.assertTrue(result.error.startswith('unshoppable ingredients:'))
        self.assertIn('tahini', result.error)
        self.assertEqual(CuratedRecipe.objects.count(), 0)

    @override_settings(AVAILABILITY_GATE_ENABLED=True)
    def test_enforce_availability_false_bypasses_the_gate(self):
        result = self._run(enforce_availability=False)
        self.assertTrue(result.ok)
        self.assertEqual(CuratedRecipe.objects.count(), 1)

    @override_settings(AVAILABILITY_GATE_ENABLED=False)
    def test_flag_off_bypasses_the_gate(self):
        result = self._run()
        self.assertTrue(result.ok)
        self.assertEqual(CuratedRecipe.objects.count(), 1)

    @override_settings(AVAILABILITY_GATE_ENABLED=True)
    def test_unrated_ingredient_also_blocks(self):
        make_canonical('záhadná věc')  # UNRATED
        payload = dict(_CURATED)
        payload['ingredients'] = [
            {"name": "sůl", "quantity": 5, "unit": "g"},
            {"name": "záhadná věc", "quantity": 5, "unit": "g"},
        ]
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = payload
            result = recipe_curation.curate_from_source(
                {"source_url": "https://example.test/zahada", "source_name": "Example"},
                run_judge=False,
            )
        self.assertFalse(result.ok)
        self.assertIn('unshoppable', result.error)

    @override_settings(AVAILABILITY_GATE_ENABLED=True)
    def test_all_common_recipe_passes(self):
        payload = dict(_CURATED)
        payload['ingredients'] = [{"name": "sůl", "quantity": 5, "unit": "g"}]
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = payload
            result = recipe_curation.curate_from_source(
                {"source_url": "https://example.test/sul", "source_name": "Example"},
                run_judge=False,
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.recipe.shopping_difficulty, Availability.COMMON)
