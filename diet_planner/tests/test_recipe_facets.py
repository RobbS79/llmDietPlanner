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


from diet_planner.services.recipe_retrieval import (
    eligible_recipes_for_slot,
    score_recipe,
    select_recipes_for_plan,
)


class FacetSelectionTest(TestCase):
    def _goal(self, **kw):
        # Lightweight stand-in: select_recipes_for_plan only reads attributes.
        class G:
            pass
        g = G()
        g.dietary_restrictions = kw.get('dietary_restrictions')
        g.num_days = kw.get('num_days', 1)
        g.small_meals_per_day = 0
        g.snacks_per_day = 0
        g.breakfast = False
        g.lunch = False
        g.dinner = True
        return g

    def test_eligible_excludes_off_cuisine_when_facets_given(self):
        _recipe(slug='ital', cuisine='italian')
        _recipe(slug='asia', cuisine='asian')
        facets = PromptFacets(cuisines={'italian'})
        eligible = eligible_recipes_for_slot('dinner', set(), facets=facets)
        slugs = {r.slug for r in eligible}
        self.assertEqual(slugs, {'ital'})

    def test_eligible_unconstrained_without_facets(self):
        _recipe(slug='ital2', cuisine='italian')
        _recipe(slug='asia2', cuisine='asian')
        eligible = eligible_recipes_for_slot('dinner', set())
        self.assertEqual(len({r.slug for r in eligible}), 2)

    def test_score_rewards_emphasis_match(self):
        plain = _recipe(slug='plain', dietary_tags=[])
        proteiny = _recipe(slug='prot', dietary_tags=['high_protein'])
        facets = PromptFacets(emphases={'high_protein'})
        s_plain = score_recipe(plain, used_recipe_ids=set(), used_cuisines=[], facets=facets)
        s_prot = score_recipe(proteiny, used_recipe_ids=set(), used_cuisines=[], facets=facets)
        self.assertGreater(s_prot, s_plain)

    def test_select_leaves_slot_uncovered_when_no_facet_match(self):
        _recipe(slug='only-asian', cuisine='asian')
        goal = self._goal()
        result = select_recipes_for_plan(goal, facets=PromptFacets(cuisines={'italian'}))
        self.assertEqual(result['coverage']['filled'], 0)        # nothing italian -> uncovered
        self.assertEqual(result['days'][0]['slots'], {})
