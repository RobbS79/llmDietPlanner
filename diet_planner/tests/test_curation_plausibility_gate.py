"""Integration test: the plausibility gate rejects implausible recipes."""
from unittest.mock import patch

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services import recipe_curation

# Exercises the single-ingredient (SINGLE_CAP_G) path; the total-ceiling path
# is covered by test_recipe_plausibility.py.
_CURATED_IMPLAUSIBLE = {
    "name_cs": "Pečené kuře",
    "name_en": "Roast chicken",
    "description": "Jednoduché pečené kuře.",
    "meal_types": ["lunch"],
    "cuisine": "czech",
    "difficulty": "easy",
    "dietary_tags": [],
    "ingredients": [{"name": "kuřecí prsa", "quantity": 680, "unit": "g"}],
    "instructions": [{"text": "Upeč kuře v troubě, dokud není propečené."}],
    "base_servings": 1,
    "base_nutrition": {"calories": 600},
    "prep_time": 10,
    "cook_time": 40,
}


class CurationPlausibilityGateTest(TestCase):
    def _run(self, enforce):
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = _CURATED_IMPLAUSIBLE
            return recipe_curation.curate_from_source(
                {"source_url": "https://example.test/kure", "source_name": "Example"},
                run_judge=False,
                enforce_plausibility=enforce,
            )

    def test_rejects_implausible_recipe(self):
        result = self._run(enforce=True)
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertTrue(result.error.startswith("implausible portion:"))
        self.assertEqual(CuratedRecipe.objects.count(), 0)

    def test_allows_when_enforcement_disabled(self):
        result = self._run(enforce=False)
        self.assertTrue(result.ok)
        self.assertIsNone(result.error)
        self.assertEqual(CuratedRecipe.objects.count(), 1)
