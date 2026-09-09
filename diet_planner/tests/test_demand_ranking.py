"""Demand terms in score_recipe: demand beats reuse, wanted hits beat demand,
season only in window, owner rating only breaks near-ties, blank scores 0."""
from unittest import mock

from django.test import TestCase

from diet_planner.models import CanonicalIngredient, CuratedRecipe
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.services.recipe_retrieval import (
    _DEMAND_WEIGHT, _SAMPLING_WINDOW, _SEASON_BONUS, _demand_terms, score_recipe,
)


def _recipe(slug, canonicals, **kw):
    defaults = dict(
        name_cs=slug, slug=slug, meal_types=['lunch', 'dinner'], cuisine='czech',
        dietary_tags=[], status=CuratedRecipe.Status.PUBLISHED,
        ingredients=[{'name': c, 'canonical': c, 'quantity': 100, 'unit': 'g'} for c in canonicals],
        instructions=[{'text': 'cook'}], base_nutrition={'calories': 500},
        source_url='https://example.com/r', source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


KW = dict(used_recipe_ids=set(), used_cuisines=[])


class DemandTermTests(TestCase):
    def test_blank_demand_adds_nothing(self):
        # A recipe with no demand term must rank exactly as before the feature:
        # the demand block contributes 0, whatever the other terms add (the
        # easy-difficulty default alone is worth 2.0).
        a = _recipe('a', ['onion'])
        self.assertEqual(_demand_terms(a), 0.0)
        self.assertEqual(score_recipe(a, **KW), score_recipe(_recipe('b', ['onion']), **KW))

    def test_demand_beats_maximal_ingredient_reuse(self):
        shared = ['onion', 'pepper', 'tomato', 'egg', 'sausage'] + [f'c{i}' for i in range(10)]
        wanted = _recipe('gulas', ['beef'], demand_term='guláš', demand_score=100.0)
        overlap = _recipe('leco', shared)
        kw = dict(KW, used_canonicals=set(shared))
        self.assertGreater(score_recipe(wanted, **kw), score_recipe(overlap, **kw))

    def test_wanted_hit_still_beats_top_demand(self):
        CanonicalIngredient.objects.update_or_create(
            slug='salmon',
            defaults=dict(name='salmon', name_cs='losos', category=CanonicalIngredient.Category.FISH),
        )
        clear_cache()
        popular = _recipe('gulas', ['beef'], demand_term='guláš', demand_score=100.0)
        asked = _recipe('losos', ['salmon'])
        kw = dict(KW, facets=PromptFacets(wanted_ingredients={'losos'}))
        self.assertGreater(score_recipe(asked, **kw), score_recipe(popular, **kw))

    def test_demand_is_log_scaled(self):
        top = _recipe('a', [], demand_term='guláš', demand_score=100.0)
        mid = _recipe('b', [], demand_term='lečo', demand_score=20.0)
        low = _recipe('c', [], demand_term='x', demand_score=1.0)
        base = score_recipe(_recipe('blank', []), **KW)
        s_top, s_mid, s_low = (score_recipe(r, **KW) - base for r in (top, mid, low))
        self.assertAlmostEqual(s_top, _DEMAND_WEIGHT, places=6)
        self.assertGreater(s_mid, s_low)
        self.assertGreater(s_mid, _DEMAND_WEIGHT * 0.5)   # 20 of 100 still reads as "wanted"

    def test_season_bonus_only_inside_the_window(self):
        kapr = _recipe('kapr', [], demand_term='kapr', demand_score=50.0, demand_peak_month=12)
        with mock.patch('diet_planner.services.recipe_retrieval._current_month', return_value=12):
            in_peak = score_recipe(kapr, **KW)
        with mock.patch('diet_planner.services.recipe_retrieval._current_month', return_value=1):
            adjacent = score_recipe(kapr, **KW)
        with mock.patch('diet_planner.services.recipe_retrieval._current_month', return_value=6):
            off = score_recipe(kapr, **KW)
        self.assertAlmostEqual(in_peak - off, _SEASON_BONUS)
        self.assertAlmostEqual(adjacent - off, _SEASON_BONUS)   # ±1 month, wrapping Dec→Jan

    def test_owner_rating_moves_less_than_the_sampling_window(self):
        loved = _recipe('a', [], demand_term='guláš', demand_score=100.0, owner_rating=5)
        meh = _recipe('b', [], demand_term='guláš', demand_score=100.0, owner_rating=1)
        unrated = _recipe('c', [], demand_term='guláš', demand_score=100.0)
        s_loved, s_meh, s_unrated = (score_recipe(r, **KW) for r in (loved, meh, unrated))
        self.assertGreater(s_loved, s_unrated)
        self.assertGreater(s_unrated, s_meh)
        self.assertLessEqual(s_loved - s_meh, 2 * _SAMPLING_WINDOW)
        self.assertLessEqual(abs(s_loved - s_unrated), _SAMPLING_WINDOW)
