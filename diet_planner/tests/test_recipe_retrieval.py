"""Tests for the recipe-grounding retrieval layer (B3)."""
from types import SimpleNamespace

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.recipe_retrieval import (
    eligible_recipes_for_slot,
    overlay_curated_recipes,
    parse_dietary_tags,
    scale_recipe_to_meal,
    score_recipe,
    select_recipes_for_plan,
)


def make_recipe(**kw):
    defaults = dict(
        name_cs=kw.pop('name_cs', 'Test dish'),
        status=CuratedRecipe.Status.PUBLISHED,
        meal_types=['lunch', 'dinner'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'}],
        instructions=[{'text': 'Uvař rýži.', 'time_min': 10, 'tip': None}],
        base_servings=1,
        base_nutrition={'calories': 500, 'protein': 30, 'carbs': 60, 'fat': 12},
        source_url='https://example.test/r',
        source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


def goal(**kw):
    base = dict(
        num_days=1, breakfast=True, lunch=True, dinner=True,
        small_meals_per_day=0, snacks_per_day=0, dietary_restrictions='',
    )
    base.update(kw)
    return SimpleNamespace(id=1, **base)


class ParseDietaryTagsTest(TestCase):
    def test_czech_and_english_keywords(self):
        self.assertEqual(parse_dietary_tags('Jsem vegetarián'), {'vegetarian'})
        self.assertIn('vegan', parse_dietary_tags('vegan diet'))
        self.assertIn('gluten_free', parse_dietary_tags('bezlepková dieta, celiakie'))
        self.assertEqual(parse_dietary_tags(''), set())
        self.assertEqual(parse_dietary_tags(None), set())


class HardGateTest(TestCase):
    def test_excludes_wrong_meal_type(self):
        make_recipe(name_cs='A', meal_types=['breakfast'])
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])

    def test_excludes_unpublished(self):
        make_recipe(name_cs='B', status=CuratedRecipe.Status.DRAFT)
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])

    def test_requires_dietary_tags_superset(self):
        make_recipe(name_cs='C', dietary_tags=['vegetarian'])
        self.assertEqual(len(eligible_recipes_for_slot('lunch', {'vegetarian'})), 1)
        # recipe lacking 'vegan' is filtered out
        self.assertEqual(eligible_recipes_for_slot('lunch', {'vegan'}), [])

    def test_excludes_unmapped_ingredients(self):
        # a non-optional ingredient with no canonical/catalog_id fails the gate
        make_recipe(
            name_cs='D',
            ingredients=[{'name': 'mystery', 'quantity': 1, 'unit': 'g'}],
        )
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])

    def test_optional_unmapped_ingredient_is_tolerated(self):
        make_recipe(
            name_cs='E',
            ingredients=[
                {'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
                {'name': 'ozdoba', 'quantity': 1, 'unit': 'ks', 'optional': True},
            ],
        )
        self.assertEqual(len(eligible_recipes_for_slot('lunch', set())), 1)


class ScoreTest(TestCase):
    def test_repeat_recipe_is_penalised(self):
        r = make_recipe()
        fresh = score_recipe(r, used_recipe_ids=set(), used_cuisines=[])
        repeat = score_recipe(r, used_recipe_ids={r.id}, used_cuisines=[])
        self.assertLess(repeat, fresh)

    def test_calorie_proximity_rewarded(self):
        r = make_recipe(base_nutrition={'calories': 500})
        near = score_recipe(r, used_recipe_ids=set(), used_cuisines=[], target_calories=500)
        far = score_recipe(r, used_recipe_ids=set(), used_cuisines=[], target_calories=1000)
        self.assertGreater(near, far)

    def test_ingredient_reuse_rewarded(self):
        # A recipe sharing canonicals with those already chosen scores higher,
        # so the plan converges on a smaller shopping list.
        r = make_recipe(ingredients=[
            {'name': 'kuřecí prsa', 'quantity': 150, 'unit': 'g', 'canonical': 'chicken-breast'},
            {'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
        ])
        none = score_recipe(r, used_recipe_ids=set(), used_cuisines=[])
        shared = score_recipe(r, used_recipe_ids=set(), used_cuisines=[],
                              used_canonicals={'chicken-breast', 'rice-basmati'})
        self.assertGreater(shared, none)

    def test_select_prefers_ingredient_overlap_as_tiebreaker(self):
        # Among equally-eligible same-cuisine options for the 2nd slot, the one
        # reusing the first recipe's ingredient is chosen (overlap breaks the
        # tie without overriding the cuisine-variety penalty).
        from diet_planner.services.recipe_retrieval import select_recipes_for_plan
        # usage_count fixes the first pick deterministically (chicken+rice).
        make_recipe(name_cs='Kuře s rýží', cuisine='czech', usage_count=10,
                    meal_types=['lunch', 'dinner'], ingredients=[
            {'name': 'kuřecí prsa', 'quantity': 150, 'unit': 'g', 'canonical': 'chicken-breast'},
            {'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
        ])
        make_recipe(name_cs='Kuřecí salát', cuisine='czech',
                    meal_types=['lunch', 'dinner'], ingredients=[
            {'name': 'kuřecí prsa', 'quantity': 120, 'unit': 'g', 'canonical': 'chicken-breast'},
        ])
        make_recipe(name_cs='Zelný salát', cuisine='czech',
                    meal_types=['lunch', 'dinner'], ingredients=[
            {'name': 'zelí', 'quantity': 200, 'unit': 'g', 'canonical': 'cabbage'},
        ])
        result = select_recipes_for_plan(goal(num_days=1, breakfast=False))
        chosen = result['days'][0]['slots']
        cans = set()
        for r in chosen.values():
            cans |= {i['canonical'] for i in r.ingredients}
        # 2nd slot reuses chicken rather than introducing cabbage.
        self.assertIn('chicken-breast', cans)
        self.assertNotIn('cabbage', cans)


class SelectTest(TestCase):
    def test_fills_distinct_recipes_when_pool_allows(self):
        for i in range(3):
            make_recipe(name_cs=f'Dish {i}', meal_types=['breakfast', 'lunch', 'dinner'])
        sel = select_recipes_for_plan(goal())
        slots = sel['days'][0]['slots']
        self.assertEqual(sel['coverage'], {'filled': 3, 'total': 3})
        # breakfast/lunch/dinner each got a distinct recipe (variety penalty works)
        chosen_ids = {r.id for r in slots.values()}
        self.assertEqual(len(chosen_ids), 3)

    def test_uncovered_slot_is_absent(self):
        make_recipe(name_cs='Only lunch', meal_types=['lunch'])
        sel = select_recipes_for_plan(goal())
        slots = sel['days'][0]['slots']
        self.assertIn('lunch', slots)
        self.assertNotIn('breakfast', slots)
        self.assertEqual(sel['coverage']['filled'], 1)
        self.assertEqual(sel['coverage']['total'], 3)


class ScaleTest(TestCase):
    def test_render_shape_and_attribution(self):
        r = make_recipe(source_url='https://src.test/x', source_name='Src')
        meal = scale_recipe_to_meal(r)
        self.assertEqual(meal['name'], r.name_cs)
        self.assertEqual(meal['source'], 'curated')
        self.assertEqual(meal['curated_recipe_id'], r.id)
        self.assertEqual(meal['source_url'], 'https://src.test/x')
        self.assertEqual(meal['instructions'], ['Uvař rýži.'])
        self.assertEqual(meal['ingredients'][0]['canonical'], 'rice-basmati')

    def test_scaling_factor(self):
        r = make_recipe(
            base_nutrition={'calories': 400, 'protein': 20, 'carbs': 40, 'fat': 10},
            ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'}],
        )
        meal = scale_recipe_to_meal(r, factor=2.0)
        self.assertEqual(meal['ingredients'][0]['quantity'], 200)
        self.assertEqual(meal['nutritional_info']['calories'], 800)
        self.assertEqual(meal['nutritional_info']['protein'], '40g')


class OverlayTest(TestCase):
    def _days(self):
        return [{
            'day_number': 1,
            'breakfast': {'name': 'Gen breakfast', 'meal_identifier': '1:1:breakfast:0'},
            'lunch': {'name': 'Gen lunch', 'meal_identifier': '1:1:lunch:0'},
            'dinner': {'name': 'Gen dinner', 'meal_identifier': '1:1:dinner:0'},
            'small_meals': [],
            'snacks': [],
        }]

    def test_covered_slot_replaced_uncovered_kept(self):
        make_recipe(name_cs='Real lunch', meal_types=['lunch'])
        out = overlay_curated_recipes(self._days(), goal())
        day = out['days'][0]
        # lunch overlaid with the curated recipe, identifier preserved
        self.assertEqual(day['lunch']['name'], 'Real lunch')
        self.assertEqual(day['lunch']['source'], 'curated')
        self.assertEqual(day['lunch']['meal_identifier'], '1:1:lunch:0')
        # breakfast had no eligible recipe -> kept, flagged generated
        self.assertEqual(day['breakfast']['name'], 'Gen breakfast')
        self.assertEqual(day['breakfast']['source'], 'generated')

    def test_usage_count_bumped(self):
        r = make_recipe(name_cs='Counted', meal_types=['lunch'])
        self.assertEqual(r.usage_count, 0)
        overlay_curated_recipes(self._days(), goal())
        r.refresh_from_db()
        self.assertEqual(r.usage_count, 1)
