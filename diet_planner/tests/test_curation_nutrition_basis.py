"""Curation must not admit recipes whose `base_nutrition` holds ONE portion.

`base_nutrition` is contractually the total for `base_servings`. The curation
model repeatedly wrote a per-portion figure there instead, which understates a
recipe by 4x-16x and makes `portions_for_target` OVER-SERVE it — the corpus-wide
bug repaired by `repair_nutrition_basis` on 2026-08-25.

The prompt is the first line of defence and is probabilistic, so intake carries
the second: the same ingredient-energy evidence the repair command uses, applied
before the recipe is ever saved.
"""
from unittest.mock import patch

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import CanonicalIngredient
from diet_planner.services import recipe_curation


def _curated(**overrides):
    """A muffin batch: 12 portions, per-portion calories in base_nutrition."""
    payload = {
        "name_cs": "Mrkvové muffiny",
        "name_en": "Carrot muffins",
        "description": "Vláčné mrkvové muffiny.",
        "meal_types": ["breakfast"],
        "cuisine": "czech",
        "difficulty": "easy",
        "dietary_tags": [],
        "ingredients": [
            {"name": "hladká mouka", "quantity": 500, "unit": "g"},
            {"name": "cukr", "quantity": 200, "unit": "g"},
            {"name": "mrkev", "quantity": 300, "unit": "g"},
            {"name": "slunečnicový olej", "quantity": 100, "unit": "ml"},
        ],
        "instructions": [{"text": "Smíchej suroviny a peč 25 minut při 180 °C."}],
        "base_servings": 12,
        # 273 kcal is ONE muffin — the bug.
        "base_nutrition": {"calories": 273, "protein": 5, "carbs": 35, "fat": 12},
        "prep_time": 15,
        "cook_time": 25,
    }
    payload.update(overrides)
    return payload


class CurationNutritionBasisGateTest(TestCase):
    def setUp(self):
        # mouka / cukr / slunečnicový olej are seeded by migration 0022;
        # these two are not, and the energy estimate needs their categories.
        CanonicalIngredient.objects.create(
            name="Carrot", name_cs="Mrkev", slug="test-carrot",
            category=CanonicalIngredient.Category.VEGETABLES,
        )
        CanonicalIngredient.objects.create(
            name="Egg", name_cs="Vejce", slug="test-egg",
            category=CanonicalIngredient.Category.EGGS,
        )

    def _curate(self, curated):
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = curated
            return recipe_curation.curate_from_source(
                {"source_url": "https://example.test/muffiny", "source_name": "Example"},
                run_judge=False,
            )

    def test_per_portion_base_nutrition_is_corrected_to_the_whole_recipe(self):
        """The ingredients carry ~3600 kcal, so 273 must be one of twelve."""
        result = self._curate(_curated())

        self.assertTrue(result.ok, result.error)
        recipe = CuratedRecipe.objects.get(source_url="https://example.test/muffiny")
        self.assertEqual(recipe.base_nutrition["calories"], 3276)
        self.assertEqual(recipe.base_nutrition["protein"], 60)
        self.assertEqual(recipe.base_nutrition["carbs"], 420)
        self.assertEqual(recipe.base_nutrition["fat"], 144)

    def test_piece_counted_recipe_is_left_alone(self):
        """4 hard-boiled eggs really are 300 kcal — multiplying invents 900."""
        result = self._curate(_curated(
            name_cs="Vařená vejce natvrdo",
            ingredients=[{"name": "vejce", "quantity": 240, "unit": "g"}],
            base_servings=4,
            base_nutrition={"calories": 300, "protein": 24, "carbs": 2, "fat": 21},
        ))

        self.assertTrue(result.ok, result.error)
        recipe = CuratedRecipe.objects.get(source_url="https://example.test/muffiny")
        self.assertEqual(recipe.base_nutrition["calories"], 300)

    def test_a_correct_recipe_is_untouched(self):
        """The whole-recipe reading already agrees with the ingredients."""
        result = self._curate(_curated(
            base_nutrition={"calories": 3600, "protein": 60, "carbs": 420, "fat": 144},
        ))

        self.assertTrue(result.ok, result.error)
        recipe = CuratedRecipe.objects.get(source_url="https://example.test/muffiny")
        self.assertEqual(recipe.base_nutrition["calories"], 3600)


class CurationPromptStatesTheBasisTest(TestCase):
    """The prompt said 'per base_servings', which reads as 'per serving'."""

    def _prompt(self):
        from diet_planner.llm_service import GeminiService
        captured = {}

        class _Response:
            text = '{"name_cs": "x"}'

        class _Model:
            def __init__(self, **kwargs):
                pass

            def generate_content(self, prompt, **kwargs):
                captured['prompt'] = prompt
                return _Response()

        with patch('diet_planner.llm_service.genai.GenerativeModel', _Model):
            GeminiService().curate_recipe_to_czech(
                source_title="Test", source_material="material",
            )
        # Collapse wrapping: what matters is that the prompt SAYS this, not
        # where the line breaks fall.
        return ' '.join(captured['prompt'].split())

    def test_prompt_does_not_say_per_base_servings(self):
        self.assertNotIn("per base_servings", self._prompt())

    def test_prompt_demands_the_whole_recipe_total(self):
        prompt = self._prompt().lower()
        self.assertIn("total for the whole recipe", prompt)
        self.assertIn("not per portion", prompt)
