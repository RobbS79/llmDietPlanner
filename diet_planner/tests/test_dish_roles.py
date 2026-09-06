"""Role vocabulary + corpus fields introduced by the příloha spec (2026-09-06)."""
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.nutrition_plausibility import min_portion_kcal


class DishRoleVocabularyTest(TestCase):
    def test_breakfast_and_supper_roles_exist(self):
        self.assertEqual(CuratedRecipe.DishRole.BREAKFAST, 'breakfast')
        self.assertEqual(CuratedRecipe.DishRole.SUPPER, 'supper')

    def test_light_is_still_accepted_as_legacy(self):
        # Untagged/legacy rows must keep deploying until the tag pass rewrites them.
        self.assertEqual(CuratedRecipe.DishRole.LIGHT, 'light')

    def test_new_fields_default_empty(self):
        r = CuratedRecipe.objects.create(
            name_cs='Lečo', source_url='https://example.test/leco', source_name='Ex',
        )
        r.refresh_from_db()
        self.assertEqual(r.side_options, [])
        self.assertEqual(r.dish_family, '')

    def test_new_roles_have_a_kcal_floor(self):
        self.assertEqual(min_portion_kcal('breakfast'), 150.0)
        self.assertEqual(min_portion_kcal('supper'), 150.0)
