"""Replace / recipe detail / cooked toggle on a POOL plan."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from diet_planner.models import DietaryPlan, DietaryGoal, MealInstance, Recipe
from diet_planner.services.recipe_retrieval import scale_recipe_to_meal
from diet_planner.tests.test_recipe_replace import make_recipe


class PoolPlanBase(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='p', country='CZ', currency='CZK', language_code='cs', dinners=2, lunches=1)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.a = make_recipe(name_cs='Guláš', dish_family='gulas', meal_types=['lunch', 'dinner'])
        self.b = make_recipe(name_cs='Řízek', dish_family='rizek', meal_types=['lunch', 'dinner'])
        self.c = make_recipe(name_cs='Segedín', dish_family='gulas', meal_types=['lunch', 'dinner'])
        self.d = make_recipe(name_cs='Svíčková', dish_family='svickova', meal_types=['lunch', 'dinner'])
        self.e = make_recipe(name_cs='Kuře na paprice', dish_family='kure', meal_types=['lunch', 'dinner'])
        g = self.goal.id

        def meal(r, slot, i):
            m = scale_recipe_to_meal(r)
            m.update({'slot': slot, 'index': i, 'meal_identifier': f'{g}:{slot}:{i}'})
            return m
        self.plan = DietaryPlan.objects.create(dietary_goal=self.goal, currency='CZK', days=[], meals=[
            meal(self.a, 'lunch', 0), meal(self.b, 'dinner', 0), meal(self.d, 'dinner', 1)])

    def _ident(self, slot, i):
        return f'{self.goal.id}:{slot}:{i}'


class PoolReplaceTest(PoolPlanBase):
    def test_replace_writes_the_pool_position_and_avoids_families_in_pool(self):
        # Replacing dinner:0 (Řízek) must not pick Segedín (family gulas already at lunch)
        url = reverse('diet_planner:recipe-replace', kwargs={'meal_identifier': self._ident('dinner', 0)})
        resp = self.client.post(url, {'hint': ''}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()['data']['replaced'], resp.content)
        self.plan.refresh_from_db()
        new = self.plan.meals[1]
        self.assertEqual((new['slot'], new['index'], new['meal_identifier']), ('dinner', 0, self._ident('dinner', 0)))
        self.assertEqual(new['curated_recipe_id'], self.e.id)   # not Segedín (gulas family already at lunch)
        self.assertTrue(Recipe.objects.filter(meal_identifier=self._ident('dinner', 0)).exists())

    def test_recipe_detail_resolves_pool_identifier(self):
        resp = self.client.get(f"/api/recipes/{self._ident('dinner', 1)}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['data']['name'], 'Svíčková')

    def test_recipe_detail_unknown_position_404(self):
        resp = self.client.get(f"/api/recipes/{self._ident('dinner', 5)}/")
        self.assertEqual(resp.status_code, 404)

    def test_cooked_toggle_stores_slot_without_day(self):
        resp = self.client.patch(f"/api/meals/{self._ident('lunch', 0)}/", {'is_cooked': True, 'meal_name': 'Guláš'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        mi = MealInstance.objects.get(meal_identifier=self._ident('lunch', 0))
        self.assertEqual(mi.meal_type, 'lunch')
        self.assertIsNone(mi.day_number)
        self.assertEqual(mi.dietary_goal_id, self.goal.id)

    def test_legacy_identifier_on_pool_plan_is_404(self):
        resp = self.client.get(f"/api/recipes/{self.goal.id}:1:dinner:0/")
        self.assertEqual(resp.status_code, 404)

    def test_malformed_identifier_is_400(self):
        resp = self.client.get("/api/recipes/1:brunch:0/")
        self.assertEqual(resp.status_code, 400)
