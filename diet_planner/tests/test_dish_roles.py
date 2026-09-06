"""Role vocabulary + corpus fields introduced by the příloha spec (2026-09-06)."""
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.nutrition_plausibility import min_portion_kcal


class DishRoleVocabularyTest(TestCase):
    # Unrelated fields that lack blank=True despite defaulting to an empty
    # list/dict — irrelevant to dish_role/side_options/dish_family, excluded
    # from full_clean() so these tests pin only what they're about.
    UNRELATED_REQUIRED_FIELDS = ['meal_types', 'dietary_tags', 'ingredients', 'instructions']

    def test_breakfast_and_supper_roles_exist(self):
        self.assertEqual(CuratedRecipe.DishRole.BREAKFAST, 'breakfast')
        self.assertEqual(CuratedRecipe.DishRole.SUPPER, 'supper')

    def test_light_is_still_accepted_as_legacy(self):
        # Untagged/legacy rows must keep deploying until the tag pass rewrites them.
        r = CuratedRecipe.objects.create(
            name_cs='Omeleta', source_url='https://example.test/omeleta', source_name='Ex',
            dish_role='light',
        )
        r.full_clean(exclude=self.UNRELATED_REQUIRED_FIELDS)
        self.assertEqual(min_portion_kcal('light'), 150.0)

    def test_new_roles_pass_field_validation(self):
        # Pins both the choices list and the max_length=10 column.
        for role in ('breakfast', 'supper'):
            r = CuratedRecipe.objects.create(
                name_cs=f'Test {role}', source_url=f'https://example.test/{role}',
                source_name='Ex', dish_role=role,
            )
            r.full_clean(exclude=self.UNRELATED_REQUIRED_FIELDS)

    def test_new_fields_default_empty(self):
        r = CuratedRecipe.objects.create(
            name_cs='Lečo', source_url='https://example.test/leco', source_name='Ex',
        )
        r.refresh_from_db()
        self.assertEqual(r.side_options, [])
        self.assertEqual(r.dish_family, '')

    def test_new_fields_round_trip(self):
        r = CuratedRecipe.objects.create(
            name_cs='Lečo', source_url='https://example.test/leco-2', source_name='Ex',
            side_options=['chleb', 'brambory'], dish_family='leco',
        )
        r.refresh_from_db()
        self.assertEqual(r.side_options, ['chleb', 'brambory'])
        self.assertEqual(r.dish_family, 'leco')

    def test_new_roles_have_a_kcal_floor(self):
        self.assertEqual(min_portion_kcal('breakfast'), 150.0)
        self.assertEqual(min_portion_kcal('supper'), 150.0)
