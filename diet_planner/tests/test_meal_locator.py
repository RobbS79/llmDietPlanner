# diet_planner/tests/test_meal_locator.py
"""One module resolves both identifier shapes:
   pool   <goal>:<slot>:<index>            e.g. 151:dinner:3
   legacy <goal>:<day>:<type>[:<index>]    e.g. 150:2:small_meal:1 / 150:2:lunch
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from diet_planner.services.meal_locator import (
    MealRef, iter_plan_meals, locate_meal, parse_meal_identifier,
    plan_meals_field, pool_identifier, set_meal,
)


class ParseTest(SimpleTestCase):
    def test_pool_identifier(self):
        ref = parse_meal_identifier('151:dinner:3')
        self.assertEqual(ref, MealRef(goal_id=151, slot='dinner', index=3, day_number=None))
        self.assertFalse(ref.is_legacy)

    def test_legacy_four_part(self):
        ref = parse_meal_identifier('150:2:small_meal:1')
        self.assertEqual(ref, MealRef(goal_id=150, slot='small_meal', index=1, day_number=2))
        self.assertTrue(ref.is_legacy)

    def test_legacy_three_part_defaults_index(self):
        self.assertEqual(parse_meal_identifier('150:2:lunch'),
                         MealRef(goal_id=150, slot='lunch', index=0, day_number=2))

    def test_rejects_unknown_slot_and_short_forms(self):
        for bad in ('1:brunch:0', '1:2:brunch:0', '1:dinner', 'x:dinner:0', '1:dinner:x', '1'):
            with self.assertRaises(ValueError, msg=bad):
                parse_meal_identifier(bad)

    def test_pool_identifier_roundtrip(self):
        ident = pool_identifier(151, 'snack', 2)
        self.assertEqual(ident, '151:snack:2')
        self.assertEqual(parse_meal_identifier(ident).identifier, ident)


def _pool_plan():
    return SimpleNamespace(days=[], meals=[
        {'slot': 'dinner', 'index': 0, 'name': 'Guláš', 'meal_identifier': '151:dinner:0'},
        {'slot': 'dinner', 'index': 1, 'name': 'Řízek', 'meal_identifier': '151:dinner:1'},
        {'slot': 'snack', 'index': 0, 'name': 'Jablko', 'meal_identifier': '151:snack:0'},
    ])


def _legacy_plan():
    return SimpleNamespace(meals=None, days=[
        {'day_number': 1, 'lunch': {'name': 'Oběd 1'}, 'small_meals': [{'name': 'S1'}, {'name': 'S2'}], 'snacks': []},
        {'day_number': 2, 'dinner': {'name': 'Večeře 2'}, 'small_meals': [], 'snacks': [{'name': 'Jablko'}]},
    ])


class LocateTest(SimpleTestCase):
    def test_locate_in_pool(self):
        self.assertEqual(locate_meal(_pool_plan(), parse_meal_identifier('151:dinner:1'))['name'], 'Řízek')
        self.assertIsNone(locate_meal(_pool_plan(), parse_meal_identifier('151:dinner:7')))
        self.assertIsNone(locate_meal(_pool_plan(), parse_meal_identifier('151:lunch:0')))

    def test_locate_in_legacy(self):
        plan = _legacy_plan()
        self.assertEqual(locate_meal(plan, parse_meal_identifier('150:1:lunch:0'))['name'], 'Oběd 1')
        self.assertEqual(locate_meal(plan, parse_meal_identifier('150:1:small_meal:1'))['name'], 'S2')
        self.assertEqual(locate_meal(plan, parse_meal_identifier('150:2:snack:0'))['name'], 'Jablko')
        self.assertIsNone(locate_meal(plan, parse_meal_identifier('150:3:lunch:0')))
        self.assertIsNone(locate_meal(plan, parse_meal_identifier('150:1:dinner:0')))

    def test_legacy_identifier_never_resolves_in_pool_plan_and_vice_versa(self):
        self.assertIsNone(locate_meal(_pool_plan(), parse_meal_identifier('151:1:dinner:0')))
        self.assertIsNone(locate_meal(_legacy_plan(), parse_meal_identifier('150:dinner:0')))


class SetTest(SimpleTestCase):
    def test_set_in_pool_replaces_by_slot_and_index(self):
        plan = _pool_plan()
        ok = set_meal(plan, parse_meal_identifier('151:dinner:1'), {'name': 'Svíčková'})
        self.assertTrue(ok)
        self.assertEqual(plan.meals[1]['name'], 'Svíčková')
        self.assertEqual(plan.meals[1]['slot'], 'dinner')
        self.assertEqual(plan.meals[1]['index'], 1)
        self.assertEqual(plan.meals[1]['meal_identifier'], '151:dinner:1')

    def test_set_in_pool_unknown_position_is_false(self):
        self.assertFalse(set_meal(_pool_plan(), parse_meal_identifier('151:dinner:9'), {'name': 'x'}))

    def test_set_in_legacy_dict_and_list_slots(self):
        plan = _legacy_plan()
        self.assertTrue(set_meal(plan, parse_meal_identifier('150:1:lunch:0'), {'name': 'Nový oběd'}))
        self.assertEqual(plan.days[0]['lunch']['name'], 'Nový oběd')
        self.assertTrue(set_meal(plan, parse_meal_identifier('150:1:small_meal:0'), {'name': 'Nová S1'}))
        self.assertEqual(plan.days[0]['small_meals'][0]['name'], 'Nová S1')
        self.assertFalse(set_meal(plan, parse_meal_identifier('150:1:snack:0'), {'name': 'x'}))


class IterTest(SimpleTestCase):
    def test_iter_pool_and_legacy(self):
        self.assertEqual([m['name'] for m in iter_plan_meals(_pool_plan())], ['Guláš', 'Řízek', 'Jablko'])
        self.assertEqual([m['name'] for m in iter_plan_meals(_legacy_plan())],
                         ['Oběd 1', 'S1', 'S2', 'Večeře 2', 'Jablko'])

    def test_plan_meals_field(self):
        self.assertEqual(plan_meals_field(_pool_plan()), 'meals')
        self.assertEqual(plan_meals_field(_legacy_plan()), 'days')


class StrictParseTest(SimpleTestCase):
    def test_rejects_non_canonical_integers(self):
        for bad in ('01:dinner:0', '1:dinner:01', '1:dinner:-1', '1:dinner:1_0',
                    '1:2:lunch:-1', '1: 2:lunch:0'):
            with self.assertRaises(ValueError, msg=bad):
                parse_meal_identifier(bad)

    def test_identifier_roundtrip_and_three_part_canonicalised(self):
        for ident in ('151:dinner:3', '150:2:small_meal:1'):
            self.assertEqual(parse_meal_identifier(ident).identifier, ident)
        self.assertEqual(parse_meal_identifier('150:2:lunch').identifier, '150:2:lunch:0')

    def test_empty_legacy_index_is_zero(self):
        self.assertEqual(parse_meal_identifier('1:2:dinner:').index, 0)


class RobustnessTest(SimpleTestCase):
    def test_non_dict_entries_skipped_and_not_located(self):
        pool = SimpleNamespace(days=[], meals=['junk', {'slot': 'dinner', 'index': 0, 'name': 'A'}])
        self.assertEqual([m['name'] for m in iter_plan_meals(pool)], ['A'])
        legacy = SimpleNamespace(meals=None, days=[
            {'day_number': 1, 'small_meals': [None, {'name': 'S2'}]}])
        self.assertEqual([m['name'] for m in iter_plan_meals(legacy)], ['S2'])
        self.assertIsNone(locate_meal(legacy, parse_meal_identifier('1:1:small_meal:0')))
        pool2 = SimpleNamespace(days=[], meals=['junk'])
        self.assertIsNone(locate_meal(pool2, parse_meal_identifier('1:dinner:0')))

    def test_empty_pool_is_pool(self):
        self.assertEqual(plan_meals_field(SimpleNamespace(meals=[], days=[])), 'meals')

    def test_set_legacy_guards(self):
        plan = SimpleNamespace(meals=None, days=[{'day_number': 1, 'small_meals': 'oops'}])
        self.assertFalse(set_meal(plan, parse_meal_identifier('1:1:small_meal:0'), {'name': 'x'}))
        self.assertFalse(set_meal(plan, parse_meal_identifier('1:9:lunch:0'), {'name': 'x'}))
