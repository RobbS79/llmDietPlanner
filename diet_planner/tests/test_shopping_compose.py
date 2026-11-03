# diet_planner/tests/test_shopping_compose.py
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.shopping_compose import compose_shopping_list, shopping_amount


def _r(slug, ings, servings=1):
    return CuratedRecipe.objects.create(
        slug=slug, name_cs=slug, meal_types=['dinner'], dish_role='main', base_servings=servings,
        ingredients=[{'name': n, 'canonical': c, 'quantity': q, 'unit': u} for n, c, q, u in ings],
        instructions=['x'], source_url='https://e.com', source_name='E',
        status=CuratedRecipe.Status.PUBLISHED)


class ShoppingAmountTest(TestCase):
    def test_rounding_rules(self):
        self.assertEqual(shopping_amount(0.4, 'ks'), (1, 'ks'))
        self.assertEqual(shopping_amount(2.25, 'stroužky'), (3, 'stroužky'))
        self.assertEqual(shopping_amount(163, 'g'), (160, 'g'))
        self.assertEqual(shopping_amount(3, 'g'), (10, 'g'))
        self.assertEqual(shopping_amount(0.6, 'lžíce'), (None, 'lžíce'))
        self.assertEqual(shopping_amount(0.25, 'l'), (0.3, 'l'))
        self.assertEqual(shopping_amount(None, 'g'), (None, 'g'))


class ComposeTest(TestCase):
    def test_merges_same_canonical_and_unit_and_scales_by_people(self):
        a = _r('a', [('česnek', 'garlic', 2, 'stroužky'), ('rýže', 'rice', 200, 'g')], servings=2)
        b = _r('b', [('česnek', 'garlic', 1, 'stroužky'), ('rýže', 'rice', 1, 'hrnek')], servings=1)
        lines = compose_shopping_list([a, b], people=2, deal_index={})
        garlic = [l for l in lines if l['canonical'] == 'garlic']
        self.assertEqual(len(garlic), 1)
        self.assertEqual(garlic[0]['amount'], 4)          # 2/2*2 + 1/1*2 = 4
        self.assertEqual(garlic[0]['needed_by'], 2)
        rice = [l for l in lines if l['canonical'] == 'rice']
        self.assertEqual(len(rice), 2)                    # g and hrnek do not merge

    def test_deal_lines_carry_the_deal_and_come_first(self):
        a = _r('a', [('rýže', 'rice', 100, 'g'), ('česnek', 'garlic', 1, 'ks')])
        deal = {'canonical': 'garlic', 'shop': 'Tesco', 'display_name': 'Česnek',
                'valid_until': '2026-11-04T05:59:59+00:00'}
        lines = compose_shopping_list([a], people=1, deal_index={'garlic': deal})
        self.assertEqual(lines[0]['canonical'], 'garlic')
        self.assertEqual(lines[0]['deal']['shop'], 'Tesco')
        self.assertIsNone(lines[1]['deal'])

    def test_people_is_clamped(self):
        a = _r('a', [('rýže', 'rice', 100, 'g')])
        self.assertEqual(compose_shopping_list([a], people=99, deal_index={})[0]['amount'], 600)
