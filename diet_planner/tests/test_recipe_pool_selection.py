"""Pool selection: exactly `count` recipes per slot, pool-wide family dedupe,
gaps recorded per (slot, index), stable per-goal seed."""
from types import SimpleNamespace

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services import recipe_retrieval as rr
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.tests.test_recipe_replace import make_recipe


def _goal(pk=1, **counts):
    base = dict(breakfasts=0, lunches=0, dinners=0, small_meals=0, snacks=0)
    base.update(counts)
    return SimpleNamespace(pk=pk, id=pk, dietary_restrictions='', **base)


class PoolCountsTest(TestCase):
    def test_pool_counts_reads_attributes_with_zero_default(self):
        self.assertEqual(rr.pool_counts(SimpleNamespace(dinners=3)),
                         {'breakfast': 0, 'lunch': 0, 'dinner': 3, 'small_meal': 0, 'snack': 0})


class SelectForPoolTest(TestCase):
    def setUp(self):
        for i in range(6):
            make_recipe(name_cs=f'Večeře {i}', meal_types=['dinner'], dish_role='main',
                        dish_family=f'fam{i}', cuisine='czech')
        for i in range(2):
            make_recipe(name_cs=f'Snídaně {i}', meal_types=['breakfast'], dish_role='breakfast',
                        dish_family=f'bf{i}')

    def test_honours_counts_exactly(self):
        out = rr.select_recipes_for_pool(_goal(dinners=4, breakfasts=2))
        slots = [(m['slot'], m['index']) for m in out['meals']]
        self.assertEqual(slots, [('breakfast', 0), ('breakfast', 1),
                                 ('dinner', 0), ('dinner', 1), ('dinner', 2), ('dinner', 3)])
        self.assertEqual(out['coverage'], {'filled': 6, 'total': 6})
        self.assertEqual(len({m['recipe'].id for m in out['meals']}), 6)

    def test_zero_count_slots_produce_nothing(self):
        out = rr.select_recipes_for_pool(_goal(dinners=1))
        self.assertEqual([m['slot'] for m in out['meals']], ['dinner'])

    def test_shortfall_recorded_as_gaps_with_slot_and_index(self):
        out = rr.select_recipes_for_pool(_goal(breakfasts=3))
        self.assertEqual(len(out['meals']), 2)
        gaps = [g for g in out['gaps'] if g['reason'] == 'no_eligible_recipes']
        self.assertEqual([(g['slot'], g['index']) for g in gaps], [('breakfast', 2)])
        self.assertNotIn('day_number', gaps[0])

    def test_family_dedupe_is_pool_wide_across_slots(self):
        CuratedRecipe.objects.all().delete()
        make_recipe(name_cs='Guláš oběd', meal_types=['lunch'], dish_role='main', dish_family='gulas')
        make_recipe(name_cs='Guláš večeře', meal_types=['dinner'], dish_role='main', dish_family='gulas')
        make_recipe(name_cs='Řízek', meal_types=['dinner'], dish_role='main', dish_family='rizek')
        out = rr.select_recipes_for_pool(_goal(lunches=1, dinners=1))
        names = {m['recipe'].name_cs for m in out['meals']}
        self.assertEqual(names, {'Guláš oběd', 'Řízek'})

    def test_family_relaxes_rather_than_starving_and_records_gap(self):
        CuratedRecipe.objects.all().delete()
        make_recipe(name_cs='A', meal_types=['dinner'], dish_role='main', dish_family='fam')
        make_recipe(name_cs='B', meal_types=['dinner'], dish_role='main', dish_family='fam')
        out = rr.select_recipes_for_pool(_goal(dinners=2))
        self.assertEqual(len(out['meals']), 2)
        self.assertIn('family_relaxed', [g['reason'] for g in out['gaps']])

    def test_same_goal_reproduces_same_pool(self):
        a = rr.select_recipes_for_pool(_goal(pk=7, dinners=3))
        b = rr.select_recipes_for_pool(_goal(pk=7, dinners=3))
        self.assertEqual([m['recipe'].id for m in a['meals']], [m['recipe'].id for m in b['meals']])

    def test_skip_slots_leaves_positions_as_gaps(self):
        out = rr.select_recipes_for_pool(_goal(dinners=2, breakfasts=1), skip_slots=('dinner',))
        self.assertEqual([m['slot'] for m in out['meals']], ['breakfast'])
        self.assertEqual([(g['slot'], g['index'], g['reason']) for g in out['gaps']],
                         [('dinner', 0, 'slot_skipped'), ('dinner', 1, 'slot_skipped')])

    def test_wanted_fit_threshold_applies_to_mains_only(self):
        facets = PromptFacets(wanted_ingredients={'losos'})
        out = rr.select_recipes_for_pool(_goal(dinners=1, breakfasts=1), facets=facets)
        self.assertEqual([m['slot'] for m in out['meals']], ['breakfast'])
        self.assertIn('wanted_fit_below_threshold', [g['reason'] for g in out['gaps']])
