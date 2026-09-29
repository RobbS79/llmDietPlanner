from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal, DietaryPlan


class PlanSerializerPoolTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('s', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_pool_goal_detail(self):
        goal = DietaryGoal.objects.create(user=self.user, prompt='p', country='CZ', dinners=2, snacks=1,
                                          status=DietaryGoal.StatusChoices.COMPLETED)
        DietaryPlan.objects.create(dietary_goal=goal, currency='CZK', days=[],
                                   meals=[{'slot': 'dinner', 'index': 0, 'name': 'A'}],
                                   grounding_debug={'shortfall': {'dinner': 1}})
        data = self.client.get(f'/api/goals/{goal.id}/').json()['data']
        self.assertEqual(data['counts'], {'breakfast': 0, 'lunch': 0, 'dinner': 2, 'small_meal': 0, 'snack': 1})
        self.assertTrue(data['is_pool'])
        plan = data['dietary_plan']
        self.assertEqual(plan['meals'][0]['name'], 'A')
        self.assertEqual(plan['days'], [])
        self.assertEqual(plan['shortfall'], {'dinner': 1})

    def test_legacy_goal_detail_keeps_days(self):
        goal = DietaryGoal.objects.create(user=self.user, prompt='p', country='CZ', num_days=1,
                                          status=DietaryGoal.StatusChoices.COMPLETED)
        DietaryPlan.objects.create(dietary_goal=goal, currency='CZK',
                                   days=[{'day_number': 1, 'lunch': {'name': 'L'}}])
        data = self.client.get(f'/api/goals/{goal.id}/').json()['data']
        self.assertFalse(data['is_pool'])
        self.assertEqual(data['num_days'], 1)
        self.assertEqual(data['dietary_plan']['days'][0]['lunch']['name'], 'L')
        self.assertIsNone(data['dietary_plan']['meals'])
        self.assertEqual(data['dietary_plan']['shortfall'], {})

    def test_list_serializer_exposes_counts(self):
        DietaryGoal.objects.create(user=self.user, prompt='p', country='CZ', dinners=4)
        data = self.client.get('/api/goals/list/').json()['data']
        self.assertEqual(data[0]['dinners'], 4)
        self.assertEqual(data[0]['counts']['dinner'], 4)
