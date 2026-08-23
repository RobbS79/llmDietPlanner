"""Display normalization for recipe ingredients.

Catalog-constrained generation feeds the LLM catalog product strings shaped
`{brand} {name} (#{store_product_id})` so pricing can round-trip by id. The LLM
echoes them back as the meal's ingredients, and those internal strings leaked
onto the public /recepty showcase (page, SSR HTML, and recipeIngredient
JSON-LD). These convert them to a clean human name for display; clean names are
left untouched.
"""
from django.test import TestCase

from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.services.ingredient_display import (
    display_ingredient_name,
    display_ingredients,
)
from diet_planner.tests.factories import make_canonical, make_price, make_store


class IngredientDisplayNameTest(TestCase):
    def setUp(self):
        make_store('LIDL_CZ', name='Lidl')
        self.tofu = make_canonical('tofu', default_unit='g', name_cs='tofu')
        # StoreProduct #<id> is what the catalog annotation embeds.
        pr = make_price(store_code='LIDL_CZ', normalized_name='tofu',
                        display_name='Pappudia tofu', price='39.90',
                        canonical=self.tofu)
        self.sp_id = pr.store_product.id
        clear_cache()

    def test_catalog_id_string_resolves_to_canonical_name(self):
        raw = f'pappudia tofu (#{self.sp_id})'
        self.assertEqual(display_ingredient_name(raw), 'tofu')

    def test_clean_string_is_left_untouched(self):
        self.assertEqual(display_ingredient_name('cibule'), 'cibule')

    def test_clean_dict_name_is_left_untouched(self):
        entry = {'name': 'kuřecí prsa', 'quantity': 200, 'unit': 'g'}
        self.assertEqual(display_ingredient_name(entry), 'kuřecí prsa')

    def test_unresolvable_catalog_id_strips_the_annotation(self):
        # No StoreProduct with this id, no canonical for the name: at minimum
        # the internal id must never reach the page.
        raw = 'mystery brand xyz (#987654)'
        out = display_ingredient_name(raw)
        self.assertNotIn('#', out)
        self.assertNotIn('987654', out)
        self.assertEqual(out, 'mystery brand xyz')

    def test_dict_name_with_catalog_annotation_is_cleaned(self):
        entry = {'name': f'pappudia tofu (#{self.sp_id})', 'quantity': 150,
                 'unit': 'g'}
        self.assertEqual(display_ingredient_name(entry), 'tofu')


class DisplayIngredientsTest(TestCase):
    def setUp(self):
        make_store('LIDL_CZ', name='Lidl')
        self.tofu = make_canonical('tofu', default_unit='g', name_cs='tofu')
        pr = make_price(store_code='LIDL_CZ', normalized_name='tofu',
                        display_name='Pappudia tofu', price='39.90',
                        canonical=self.tofu)
        self.sp_id = pr.store_product.id
        clear_cache()

    def test_preserves_shape_and_fields(self):
        ingredients = [
            {'name': f'pappudia tofu (#{self.sp_id})', 'quantity': 150,
             'unit': 'g', 'optional': True, 'canonical': 'tofu'},
            'cibule',
        ]
        out = display_ingredients(ingredients)
        # dict stays a dict, name cleaned, every other field preserved
        self.assertEqual(out[0]['name'], 'tofu')
        self.assertEqual(out[0]['quantity'], 150)
        self.assertEqual(out[0]['unit'], 'g')
        self.assertTrue(out[0]['optional'])
        self.assertEqual(out[0]['canonical'], 'tofu')
        # string stays a string
        self.assertEqual(out[1], 'cibule')

    def test_empty_list(self):
        self.assertEqual(display_ingredients([]), [])

    def test_none_is_treated_as_empty(self):
        self.assertEqual(display_ingredients(None), [])


class RecipeSerializerIngredientDisplayTest(TestCase):
    """The public showcase serializer must never emit the internal catalog
    string. Prod QA 2026-08-23: ids 70/71/72 rendered `pappudia tofu (#2153)`
    on the page, in the SSR HTML, and in the recipeIngredient JSON-LD."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from diet_planner.models import DietaryGoal
        make_store('LIDL_CZ', name='Lidl')
        self.tofu = make_canonical('tofu', default_unit='g', name_cs='tofu')
        pr = make_price(store_code='LIDL_CZ', normalized_name='tofu',
                        display_name='Pappudia tofu', price='39.90',
                        canonical=self.tofu)
        self.sp_id = pr.store_product.id
        clear_cache()
        user = get_user_model().objects.create_user('disp', password='x')
        self.goal = DietaryGoal.objects.create(user=user, country='CZ')

    def test_serialized_ingredients_are_display_clean(self):
        from diet_planner.models import Recipe
        from diet_planner.serializers import RecipeSerializer
        recipe = Recipe.objects.create(
            meal_identifier=f'g{self.goal.id}:1:lunch:0', dietary_goal=self.goal,
            name='Tofu', servings=1,
            ingredients=[f'pappudia tofu (#{self.sp_id})'],
        )
        data = RecipeSerializer(recipe).data
        self.assertEqual(data['ingredients'], ['tofu'])
