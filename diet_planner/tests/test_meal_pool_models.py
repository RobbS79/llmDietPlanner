"""Pool goals carry per-slot counts; legacy day fields become optional."""
from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal, DietaryPlan, MealInstance


class PoolGoalFieldsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('pool', password='x')

    def test_pool_counts_reads_the_five_fields(self):
        goal = DietaryGoal.objects.create(
            user=self.user, prompt='p', country='CZ',
            breakfasts=2, lunches=0, dinners=5, small_meals=3, snacks=1,
        )
        self.assertEqual(goal.pool_counts(), {
            'breakfast': 2, 'lunch': 0, 'dinner': 5, 'small_meal': 3, 'snack': 1,
        })
        self.assertTrue(goal.is_pool)

    def test_legacy_goal_without_counts_is_not_pool(self):
        goal = DietaryGoal.objects.create(user=self.user, prompt='p', country='CZ', num_days=3)
        self.assertFalse(goal.is_pool)
        self.assertEqual(goal.pool_counts(), {
            'breakfast': 0, 'lunch': 0, 'dinner': 0, 'small_meal': 0, 'snack': 0,
        })

    def test_legacy_day_fields_may_be_null(self):
        goal = DietaryGoal.objects.create(
            user=self.user, prompt='p', country='CZ',
            num_days=None, breakfast=None, lunch=None, dinner=None,
            small_meals_per_day=None, snacks_per_day=None, dinners=1,
        )
        goal.refresh_from_db()
        self.assertIsNone(goal.num_days)

    def test_plan_meals_defaults_to_null_and_day_number_optional(self):
        goal = DietaryGoal.objects.create(user=self.user, prompt='p', country='CZ', dinners=1)
        plan = DietaryPlan.objects.create(dietary_goal=goal, currency='CZK', meals=[{'slot': 'dinner', 'index': 0, 'name': 'x'}])
        self.assertTrue(goal.is_pool)
        self.assertEqual(plan.meals[0]['slot'], 'dinner')
        self.assertEqual(plan.days, [])
        mi = MealInstance.objects.create(
            user=self.user, dietary_goal=goal, meal_identifier=f'{goal.id}:dinner:0',
            meal_name='x', meal_type='dinner', day_number=None,
        )
        self.assertIsNone(mi.day_number)
