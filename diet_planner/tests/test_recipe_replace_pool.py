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


class PoolCookedToggleOwnershipTest(PoolPlanBase):
    def test_patch_on_another_users_goal_is_404_and_creates_nothing(self):
        other = User.objects.create(username='cizi')
        foreign = DietaryGoal.objects.create(
            user=other, prompt='p', country='CZ', currency='CZK', language_code='cs')
        resp = self.client.patch(
            f'/api/meals/{foreign.id}:lunch:0/', {'is_cooked': True, 'meal_name': 'x'}, format='json')
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(MealInstance.objects.filter(meal_identifier=f'{foreign.id}:lunch:0').exists())


class PoolRefineAcceptTest(PoolPlanBase):
    def test_accept_writes_the_pool_position_resets_cooked_and_returns_previous(self):
        ident = self._ident('dinner', 0)
        MealInstance.objects.create(
            meal_identifier=ident, user=self.user, dietary_goal=self.goal,
            meal_name='Řízek', day_number=None, meal_type='dinner', is_cooked=True)
        url = reverse('diet_planner:recipe-refine', kwargs={'meal_identifier': ident})
        resp = self.client.post(url, {'accept': self.e.id}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()['data']
        self.assertTrue(data['replaced'])
        self.assertEqual(data['previous']['curated_recipe_id'], self.b.id)
        self.plan.refresh_from_db()
        new = self.plan.meals[1]
        self.assertEqual((new['slot'], new['index'], new['meal_identifier']), ('dinner', 0, ident))
        self.assertEqual(new['curated_recipe_id'], self.e.id)
        # untouched neighbours
        self.assertEqual(self.plan.meals[0]['curated_recipe_id'], self.a.id)
        self.assertEqual(self.plan.meals[2]['curated_recipe_id'], self.d.id)
        self.assertFalse(MealInstance.objects.get(meal_identifier=ident, user=self.user).is_cooked)


class FamilyRelaxationTest(TestCase):
    """Spec §8: never repeat a family already in the pool — unless that leaves
    no candidate at all, then a repeat beats 'no alternatives'."""

    def setUp(self):
        self.user = User.objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='p', country='CZ', currency='CZK', language_code='cs', dinners=1, lunches=1)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.a = make_recipe(name_cs='Guláš', dish_family='gulas', meal_types=['lunch', 'dinner'])
        self.b = make_recipe(name_cs='Řízek', dish_family='rizek', meal_types=['lunch', 'dinner'])
        self.c = make_recipe(name_cs='Segedín', dish_family='gulas', meal_types=['lunch', 'dinner'])
        g = self.goal.id

        def meal(r, slot, i):
            m = scale_recipe_to_meal(r)
            m.update({'slot': slot, 'index': i, 'meal_identifier': f'{g}:{slot}:{i}'})
            return m
        self.plan = DietaryPlan.objects.create(dietary_goal=self.goal, currency='CZK', days=[], meals=[
            meal(self.a, 'lunch', 0), meal(self.b, 'dinner', 0)])
        self.ident = f'{g}:dinner:0'

    def test_replace_falls_back_to_a_repeated_family_when_nothing_else_fits(self):
        url = reverse('diet_planner:recipe-replace', kwargs={'meal_identifier': self.ident})
        resp = self.client.post(url, {'hint': ''}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()['data']['replaced'], resp.content)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.meals[1]['curated_recipe_id'], self.c.id)

    def test_refine_accept_of_a_relaxed_candidate_succeeds(self):
        url = reverse('diet_planner:recipe-refine', kwargs={'meal_identifier': self.ident})
        resp = self.client.post(url, {'accept': self.c.id}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()['data']['replaced'])
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.meals[1]['curated_recipe_id'], self.c.id)


class PoolResearchJobTest(PoolPlanBase):
    def test_ready_job_candidate_is_portioned_to_the_pool_position(self):
        from diet_planner.models import RecipeResearchJob
        from diet_planner.services.recipe_retrieval import render_curated_meal
        big = make_recipe(name_cs='Thajské kari', dish_family='kari', base_servings=4,
                          base_nutrition={'calories': 2000, 'protein': 80, 'carbs': 200, 'fat': 60})
        self.plan.meals[2]['nutritional_info']['calories'] = 1000
        self.plan.save(update_fields=['meals'])
        job = RecipeResearchJob.objects.create(
            user=self.user, meal_identifier=self._ident('dinner', 1), query='kari',
            status=RecipeResearchJob.Status.READY, result_recipe=big)
        resp = self.client.get(reverse('diet_planner:recipe-research-job', kwargs={'job_id': job.id}))
        self.assertEqual(resp.status_code, 200, resp.content)
        cand = resp.json()['data']['candidate']
        expected, _ = render_curated_meal(big, target_kcal=1000, required_tags=frozenset())
        self.assertEqual(cand['calories'], expected['nutritional_info']['calories'])
        self.assertNotEqual(cand['calories'], 500)  # not the single-portion default


class ResearchIdentifierHelpersTest(TestCase):
    def test_slot_and_goal_of_pool_identifier(self):
        from diet_planner.models import RecipeResearchJob
        from diet_planner.services import recipe_research
        user = User.objects.create(username='owner')
        goal = DietaryGoal.objects.create(id=151, user=user, prompt='p', country='CZ')
        self.assertEqual(recipe_research._slot_of('151:small_meal:2'), 'small_meal')
        job = RecipeResearchJob(user=user, meal_identifier='151:small_meal:2', query='q')
        self.assertEqual(recipe_research._goal_of(job), goal)

    def test_malformed_identifier_falls_back(self):
        from diet_planner.models import RecipeResearchJob
        from diet_planner.services import recipe_research
        user = User.objects.create(username='owner')
        self.assertEqual(recipe_research._slot_of('garbage'), 'lunch')
        self.assertIsNone(recipe_research._goal_of(
            RecipeResearchJob(user=user, meal_identifier='garbage', query='q')))


class PoolStaleCacheRepairTest(PoolPlanBase):
    def setUp(self):
        super().setUp()
        self.curated = make_recipe(
            name_cs='Bramborové halušky', dish_family='halusky', base_servings=10,
            base_nutrition={'calories': 5286, 'protein': 205, 'carbs': 799, 'fat': 100},
            ingredients=[{'name': 'brambory', 'quantity': 1500, 'unit': 'g', 'canonical': 'potato'}])
        stale = scale_recipe_to_meal(self.curated, portions=10)
        stale['servings'] = 5
        stale.update({'slot': 'lunch', 'index': 0, 'meal_identifier': self._ident('lunch', 0)})
        self.plan.meals[0] = stale
        self.plan.save(update_fields=['meals'])
        self.row = self._row(self._ident('lunch', 0), stale['ingredients'])

    def _row(self, ident, ingredients):
        return Recipe.objects.create(
            meal_identifier=ident, dietary_goal=self.goal, name=self.curated.name_cs,
            servings=5, nutritional_info={'calories': 5286}, ingredients=ingredients,
            instructions=['Uvař.'], curated_recipe_slug=self.curated.slug)

    def _run(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('refresh_stale_recipe_cache', '--apply', stdout=out)
        return out.getvalue()

    def test_apply_rewrites_the_pool_position_in_place(self):
        self._run()
        self.plan.refresh_from_db()
        meal = self.plan.meals[0]
        self.assertEqual((meal['slot'], meal['index'], meal['meal_identifier']),
                         ('lunch', 0, self._ident('lunch', 0)))
        self.assertEqual(meal['servings'], 1)
        self.assertEqual(meal['nutritional_info']['calories'], 529)
        self.assertEqual(len(self.plan.meals), 3)
        self.row.refresh_from_db()
        self.assertEqual((self.row.servings, self.row.nutritional_info['calories']), (1, 529))

    def test_position_now_holding_another_dish_is_skipped(self):
        # dinner:0 holds Řízek now; a stale halušky row cached there must not overwrite it.
        moved = self._row(self._ident('dinner', 0), [])
        output = self._run()
        self.assertIn('moved', output)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.meals[1]['curated_recipe_id'], self.b.id)
        moved.refresh_from_db()
        self.assertEqual(moved.servings, 5)
