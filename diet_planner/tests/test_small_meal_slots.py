"""Small meals and snacks are first-class plan slots.

Plan 150 (2026-09-16): the goal asked for 2 small meals a day; the generator
produced them, the plan stored them, and nothing could show or open them —
they had no meal_identifier and the recipe endpoint only understood the three
dict slots (breakfast/lunch/dinner). Identifier contract for list slots:
``<goal>:<day>:small_meal:<index>`` and ``<goal>:<day>:snack:<index>``.
"""
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal, DietaryPlan
from diet_planner.tasks import transform_days_to_new_format
from diet_planner.tests.test_recipe_replace import make_recipe
from diet_planner.views import _commit_slot_swap, _locate_plan_slot, _parse_meal_identifier


def _curated_meal(name, kcal=300):
    return {
        'name': name, 'source': 'curated', 'servings': 1,
        'description': f'{name} popis',
        'instructions': ['Nakrájejte.', 'Uvařte.', 'Podávejte.'],
        'ingredients': [{'name': 'cuketa', 'quantity': 200, 'unit': 'g', 'canonical': 'zucchini'}],
        'nutritional_info': {'calories': kcal, 'protein': '10g', 'carbs': '20g', 'fat': '5g'},
    }


class TransformAssignsListSlotIdentifiersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user('t', password='x')
        cls.goal = DietaryGoal.objects.create(
            user=user, prompt='p', country='CZ', city='Prague', num_days=1,
        )

    def test_small_meals_and_snacks_get_indexed_identifiers(self):
        days = [{
            'day_number': 2,
            'lunch': {'name': 'Oběd'},
            'small_meals': [{'name': 'Polévka'}, {'name': 'Klínky'}],
            'snacks': [{'name': 'Jablko'}],
        }]
        out = transform_days_to_new_format(days, self.goal)
        g = self.goal.id
        self.assertEqual(
            [m['meal_identifier'] for m in out[0]['small_meals']],
            [f'{g}:2:small_meal:0', f'{g}:2:small_meal:1'],
        )
        self.assertEqual(out[0]['snacks'][0]['meal_identifier'], f'{g}:2:snack:0')


class ParseMealIdentifierTest(SimpleTestCase):
    def test_four_part_identifier_yields_index(self):
        self.assertEqual(_parse_meal_identifier('5:2:small_meal:1'), (5, 2, 'small_meal', 1))

    def test_three_part_identifier_defaults_index_to_zero(self):
        self.assertEqual(_parse_meal_identifier('5:2:lunch'), (5, 2, 'lunch', 0))


class ListSlotBase(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='p', num_days=1, country='CZ', currency='CZK', language_code='cs',
        )
        g = self.goal.id
        self.lunch = {**_curated_meal('Oběd', 600), 'meal_identifier': f'{g}:1:lunch:0'}
        self.small = [
            {**_curated_meal('Cuketová polévka', 260), 'meal_identifier': f'{g}:1:small_meal:0'},
            {**_curated_meal('Bramborové klínky', 240), 'meal_identifier': f'{g}:1:small_meal:1'},
        ]
        self.snacks = [{**_curated_meal('Jablko', 80), 'meal_identifier': f'{g}:1:snack:0'}]
        self.plan = DietaryPlan.objects.create(
            dietary_goal=self.goal, currency='CZK',
            days=[{'day_number': 1, 'lunch': self.lunch, 'small_meals': self.small, 'snacks': self.snacks}],
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class RecipeDetailResolvesListSlotsTest(ListSlotBase):
    def _get(self, ident):
        return self.client.get(reverse('diet_planner:recipe-detail', kwargs={'meal_identifier': ident}))

    def test_second_small_meal_opens_by_index(self):
        res = self._get(f'{self.goal.id}:1:small_meal:1')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['name'], 'Bramborové klínky')

    def test_snack_opens_by_index(self):
        res = self._get(f'{self.goal.id}:1:snack:0')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['name'], 'Jablko')

    def test_out_of_range_index_is_404_not_500(self):
        res = self._get(f'{self.goal.id}:1:small_meal:7')
        self.assertEqual(res.status_code, 404)


class RefreshCommandWritesListSlotTest(ListSlotBase):
    def test_write_plan_slot_replaces_the_small_meal_by_identifier(self):
        from diet_planner.management.commands.refresh_stale_recipe_cache import _write_plan_slot
        ident = f'{self.goal.id}:1:small_meal:1'
        new = {**_curated_meal('Nové klínky', 250), 'meal_identifier': ident}
        self.assertTrue(_write_plan_slot(self.plan, 1, 'small_meal', new))
        names = [m['name'] for m in self.plan.days[0]['small_meals']]
        self.assertEqual(names, ['Cuketová polévka', 'Nové klínky'])


class LocateAndSwapListSlotTest(ListSlotBase):
    def test_locate_returns_the_indexed_small_meal(self):
        ctx, err = _locate_plan_slot(self.user, f'{self.goal.id}:1:small_meal:1')
        self.assertIsNone(err)
        self.assertEqual(ctx.current_meal['name'], 'Bramborové klínky')
        self.assertEqual((ctx.meal_type, ctx.slot_index), ('small_meal', 1))

    def test_swap_writes_back_into_the_list_at_that_index(self):
        chosen = make_recipe(name_cs='Mrkvový salát')
        ident = f'{self.goal.id}:1:small_meal:1'
        ctx, _ = _locate_plan_slot(self.user, ident)
        _commit_slot_swap(
            goal=ctx.goal, plan=ctx.plan, target_day=ctx.target_day,
            meal_type=ctx.meal_type, slot_index=ctx.slot_index,
            meal_identifier=ident, chosen=chosen, user=self.user,
        )
        self.plan.refresh_from_db()
        names = [m['name'] for m in self.plan.days[0]['small_meals']]
        self.assertEqual(names, ['Cuketová polévka', 'Mrkvový salát'])
        self.assertEqual(self.plan.days[0]['small_meals'][1]['meal_identifier'], ident)
        self.assertEqual(self.plan.days[0]['lunch']['name'], 'Oběd')
