from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from diet_planner.models import CuratedRecipe, SavedShoppingList
from diet_planner.services import discover as discover_mod


def _recipe(slug, name, ing):
    return CuratedRecipe.objects.create(
        slug=slug, name_cs=name, meal_types=['dinner'], dish_role='main', base_servings=1,
        ingredients=[{'name': ing, 'canonical': ing, 'quantity': 100, 'unit': 'g'}],
        instructions=['x'], source_url='https://e.com', source_name='E',
        status=CuratedRecipe.Status.PUBLISHED, prep_time=5, cook_time=10)


@override_settings(TURNSTILE_SECRET_KEY='', DISCOVER_DAILY_LLM_BUDGET=100)
class DiscoverViewsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.a = _recipe('a', 'Kuře s rýží', 'kuřecí prsa')
        self.b = _recipe('b', 'Čočková polévka', 'čočka')
        for target, kwargs in (
            ('diet_planner.views_discover.active_deal_index', {'return_value': {}}),
            # No real Gemini call from any test: the LLM read fails, text fallback runs.
            ('diet_planner.services.discover.extract_prompt_facets',
             {'side_effect': Exception('no llm in tests')}),
        ):
            patcher = mock.patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_discover_returns_cards(self):
        resp = self.client.post('/api/discover/', {'q': 'kuřecí prsa'}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['recipes'][0]['name'], 'Kuře s rýží')
        self.assertTrue(data['fallback'])

    def test_discover_result_is_cached(self):
        with mock.patch('diet_planner.views_discover.discover', wraps=discover_mod.discover) as d:
            first = self.client.post('/api/discover/', {'q': 'čočka'}, format='json')
            second = self.client.post('/api/discover/', {'q': 'Čočka'}, format='json')
        self.assertEqual(d.call_count, 1)
        self.assertEqual(first.json(), second.json())

    def test_empty_restricted_result_passes_through(self):
        empty = {'understood': ['bez masa'], 'exact': False, 'fallback': False,
                 'recipes': [], 'has_more': False}
        with mock.patch('diet_planner.views_discover.discover', return_value=empty):
            resp = self.client.post('/api/discover/', {'q': 'bez masa'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'status': 'success', 'data': empty})

    def test_over_budget_disables_llm(self):
        with mock.patch('diet_planner.views_discover.take_llm_slot', return_value=False), \
             mock.patch('diet_planner.views_discover.discover', return_value={
                 'understood': [], 'exact': True, 'fallback': True, 'recipes': [], 'has_more': False}) as d:
            self.client.post('/api/discover/', {'q': 'něco'}, format='json')
        self.assertFalse(d.call_args.kwargs['llm_allowed'])

    @override_settings(TURNSTILE_SECRET_KEY='s', DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE=1)
    def test_challenge_required_after_free_searches(self):
        self.client.post('/api/discover/', {'q': 'a1'}, format='json')
        resp = self.client.post('/api/discover/', {'q': 'a2'}, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['code'], 'CHALLENGE_REQUIRED')

    def test_recipe_sheet(self):
        resp = self.client.get(f'/api/discover/recipe/{self.a.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['steps'], ['x'])

    def test_unpublished_recipe_is_404(self):
        CuratedRecipe.objects.filter(pk=self.a.pk).update(status=CuratedRecipe.Status.DRAFT)
        self.assertEqual(self.client.get(f'/api/discover/recipe/{self.a.id}/').status_code, 404)

    def test_deals_this_week_empty_when_none(self):
        resp = self.client.get('/api/deals/this-week/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['deals'], [])

    def test_compose_anonymous(self):
        resp = self.client.post('/api/shopping-list/compose/',
                                {'recipe_ids': [self.a.id, self.b.id], 'people': 2}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['data']['lines']), 2)

    def test_save_list_requires_login_and_enforces_free_limit(self):
        # JWTAuthentication sends a WWW-Authenticate header, so DRF answers 401, not 403.
        self.assertEqual(self.client.post('/api/shopping-lists/', {}, format='json').status_code, 401)
        user = get_user_model().objects.create(username='u')
        self.client.force_authenticate(user)
        for _ in range(3):
            ok = self.client.post('/api/shopping-lists/', {'recipe_ids': [self.a.id], 'people': 2}, format='json')
            self.assertEqual(ok.status_code, 201)
        over = self.client.post('/api/shopping-lists/', {'recipe_ids': [self.a.id], 'people': 2}, format='json')
        self.assertEqual(over.status_code, 402)
        self.assertEqual(over.json()['code'], 'LIST_LIMIT')
        self.assertEqual(SavedShoppingList.objects.filter(user=user).count(), 3)
        listing = self.client.get('/api/shopping-lists/')
        self.assertEqual(len(listing.json()['data']['lists']), 3)
