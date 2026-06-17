from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.services.recipe_retrieval import (
    published_cuisine_vocab,
    recipe_matches_facets,
)


def _recipe(**kw):
    defaults = dict(
        name_cs='Test', slug=kw.get('slug', 'test'),
        meal_types=['dinner'], cuisine='italian',
        dietary_tags=[], status=CuratedRecipe.Status.PUBLISHED,
        ingredients=[{'name': 'Chicken breast', 'canonical': 'chicken', 'quantity': 200, 'unit': 'g'}],
        instructions=[{'text': 'cook'}], base_nutrition={'calories': 500},
        source_url='https://example.com/r', source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class RecipeMatchesFacetsTest(TestCase):
    def test_empty_facets_match_everything(self):
        r = _recipe(slug='a')
        self.assertTrue(recipe_matches_facets(r, PromptFacets()))

    def test_cuisine_in_set_passes(self):
        r = _recipe(slug='b', cuisine='italian')
        self.assertTrue(recipe_matches_facets(r, PromptFacets(cuisines={'italian'})))

    def test_cuisine_not_in_set_blocked(self):
        r = _recipe(slug='c', cuisine='asian')
        self.assertFalse(recipe_matches_facets(r, PromptFacets(cuisines={'italian'})))

    def test_cuisineless_recipe_blocked_when_cuisine_demanded(self):
        r = _recipe(slug='d', cuisine='')
        self.assertFalse(recipe_matches_facets(r, PromptFacets(cuisines={'italian'})))

    def test_wanted_ingredient_hit_passes(self):
        r = _recipe(slug='e')  # has canonical 'chicken'
        self.assertTrue(recipe_matches_facets(r, PromptFacets(wanted_ingredients={'chicken'})))

    def test_wanted_ingredient_miss_blocked(self):
        r = _recipe(slug='f')
        self.assertFalse(recipe_matches_facets(r, PromptFacets(wanted_ingredients={'tofu'})))

    def test_avoided_ingredient_present_blocked(self):
        r = _recipe(slug='g')  # name 'Chicken breast'
        self.assertFalse(recipe_matches_facets(r, PromptFacets(avoided_ingredients={'chicken'})))

    def test_published_cuisine_vocab_distinct_nonempty_lower(self):
        _recipe(slug='h', cuisine='Italian')
        _recipe(slug='i', cuisine='asian')
        _recipe(slug='j', cuisine='')
        self.assertEqual(published_cuisine_vocab(), ['asian', 'italian'])
