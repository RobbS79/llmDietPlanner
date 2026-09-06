"""A newly curated recipe leaves intake with dish_role/meal_types/side_options/
dish_family set, so the corpus never drifts back to untagged."""
import json
from unittest.mock import patch

from django.test import TestCase

from diet_planner.models import Availability, CuratedRecipe
from diet_planner.services import recipe_curation
from diet_planner.tests.factories import make_canonical

_CURATED = {
    "name_cs": "Lečo s klobásou",
    "name_en": "Lecho with sausage",
    "description": "Rychlá večeře.",
    "meal_types": ["lunch", "dinner"],
    "cuisine": "czech",
    "difficulty": "easy",
    "dietary_tags": [],
    "ingredients": [{"name": "sůl", "quantity": 5, "unit": "g"}],
    "instructions": [{"text": "Osmahni cibuli, přidej papriky a rajčata, vejce, podávej s chlebem."}],
    "base_servings": 2,
    "base_nutrition": {"calories": 900},
    "prep_time": 10,
    "cook_time": 20,
}


class CurationClassifiesTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)

    def _run(self, answer):
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = _CURATED
            gem.return_value.classify_dishes.return_value = answer
            return recipe_curation.curate_from_source(
                {"source_url": "https://example.test/leco", "source_name": "Example"},
                run_judge=False, enforce_plausibility=False,
            )

    def test_new_recipe_is_tagged_and_overridden(self):
        # LLM says main; the shipped by_family override for 'leco' pins supper/dinner/chleb.
        answer = json.dumps([{'slug': 'leco-s-klobasou', 'dish_role': 'main',
                              'meal_types': ['lunch', 'dinner'], 'side_options': [],
                              'dish_family': 'leco'}])
        result = self._run(answer)
        self.assertTrue(result.ok, result.error)
        r = CuratedRecipe.objects.get()
        self.assertEqual(r.dish_role, 'supper')
        self.assertEqual(r.meal_types, ['dinner'])
        self.assertEqual(r.side_options, ['chleb'])
        self.assertEqual(r.dish_family, 'leco')

    def test_classifier_failure_leaves_recipe_untagged_but_saved(self):
        result = self._run('not json')
        self.assertTrue(result.ok, result.error)
        r = CuratedRecipe.objects.get()
        self.assertEqual(r.dish_role, '')
        self.assertEqual(r.meal_types, ['lunch', 'dinner'])  # curation's own value kept
