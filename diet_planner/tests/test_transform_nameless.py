"""
Issue #47 root cause 6: the base LLM plan can emit meal entries with no name
(plan 131 shipped a blank `small_meals[0]` card with name=None). Transform must
drop such entries instead of rendering empty meal cards.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal
from diet_planner.tasks import transform_days_to_new_format


class TransformDropsNamelessMealsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user('t', password='x')
        cls.goal = DietaryGoal.objects.create(
            user=user, prompt='p', country='CZ', city='Prague', num_days=1,
        )

    def test_nameless_small_meal_dropped(self):
        days = [{
            'day_number': 1,
            'lunch': {'name': 'Oběd'},
            'small_meals': [{'name': None}, {'name': 'Svačina'}],
            'snacks': [{}],
        }]
        out = transform_days_to_new_format(days, self.goal)
        self.assertEqual([m['name'] for m in out[0]['small_meals']], ['Svačina'])
        self.assertEqual(out[0]['snacks'], [])

    def test_nameless_main_meal_dropped(self):
        days = [{
            'day_number': 1,
            'breakfast': {'name': ''},
            'lunch': {'name': 'Oběd'},
            'dinner': {'name': None},
        }]
        out = transform_days_to_new_format(days, self.goal)
        self.assertNotIn('breakfast', out[0])
        self.assertNotIn('dinner', out[0])
        self.assertEqual(out[0]['lunch']['name'], 'Oběd')

    def test_named_meals_kept_intact(self):
        days = [{
            'day_number': 1,
            'breakfast': {'name': 'Snídaně'},
            'small_meals': [{'name': 'Svačina'}],
        }]
        out = transform_days_to_new_format(days, self.goal)
        self.assertEqual(out[0]['breakfast']['name'], 'Snídaně')
        self.assertEqual(len(out[0]['small_meals']), 1)
