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
        self.mocks = {}
        for name, target, kwargs in (
            ('deals', 'diet_planner.views_discover.active_deal_index', {'return_value': {}}),
            # No real Gemini call from any test: the LLM read fails, text fallback runs.
            ('extract', 'diet_planner.services.discover.extract_prompt_facets',
             {'side_effect': Exception('no llm in tests')}),
            # Belt and braces: even an unpatched extraction never reaches Gemini.
            ('generate', 'diet_planner.services.prompt_facets._default_generate',
             {'side_effect': AssertionError('real Gemini call in a test')}),
        ):
            patcher = mock.patch(target, **kwargs)
            self.mocks[name] = patcher.start()
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
                 'medical_note': False, 'ranked_ids': [], 'recipes': [], 'has_more': False}
        with mock.patch('diet_planner.views_discover.discover', return_value=empty):
            resp = self.client.post('/api/discover/', {'q': 'bez masa'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'status': 'success', 'data': {
            'understood': ['bez masa'], 'exact': False, 'fallback': False,
            'medical_note': False, 'recipes': [], 'has_more': False}})

    def test_view_leaves_the_llm_budget_to_the_service(self):
        with mock.patch('diet_planner.views_discover.discover', wraps=discover_mod.discover) as d:
            self.client.post('/api/discover/', {'q': 'něco'}, format='json')
            self.client.post('/api/discover/', {'q': ''}, format='json')
        self.assertEqual([c.kwargs['llm_allowed'] for c in d.call_args_list], [True, False])

    def _many(self, n):
        for i in range(n):
            _recipe(f'k{i}', f'Kuře {i}', 'kuřecí prsa')

    def test_second_page_costs_no_llm_call(self):
        self._many(6)
        with mock.patch('diet_planner.views_discover.discover', wraps=discover_mod.discover) as d:
            first = self.client.post('/api/discover/', {'q': 'kuře', 'page': 0}, format='json').json()
            second = self.client.post('/api/discover/', {'q': 'kuře', 'page': 1}, format='json').json()
        self.assertEqual(d.call_count, 1)
        self.assertEqual(self.mocks['extract'].call_count, 1)
        self.assertEqual(len(first['data']['recipes']), 4)
        self.assertTrue(first['data']['has_more'])
        self.assertEqual(len(second['data']['recipes']), 3)
        self.assertFalse(second['data']['has_more'])
        ids = [r['id'] for r in first['data']['recipes'] + second['data']['recipes']]
        self.assertEqual(len(set(ids)), 7)

    def test_page_is_capped(self):
        with mock.patch('diet_planner.views_discover.discover', wraps=discover_mod.discover):
            resp = self.client.post('/api/discover/', {'q': '', 'page': 10_000}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['recipes'], [])
        with mock.patch('diet_planner.views_discover._ids_page', wraps=lambda ids, page: []) as p:
            self.client.post('/api/discover/', {'q': '', 'page': 99}, format='json')
        self.assertEqual(p.call_args.args[1], 14)

    def test_unpublished_since_caching_is_dropped(self):
        self.client.post('/api/discover/', {'q': 'čočka'}, format='json')
        CuratedRecipe.objects.filter(pk=self.b.pk).update(status=CuratedRecipe.Status.DRAFT)
        resp = self.client.post('/api/discover/', {'q': 'čočka'}, format='json')
        self.assertNotIn(self.b.id, [r['id'] for r in resp.json()['data']['recipes']])

    def test_cached_result_gets_a_fresh_deal_index(self):
        deal = {'canonical': 'čočka', 'shop': 'Tesco', 'display_name': 'Čočka',
                'source_url': '', 'valid_until': '2026-11-04T05:59:59+00:00'}
        self.mocks['deals'].side_effect = [{}, {'čočka': deal}]
        with mock.patch('diet_planner.services.recipe_deals._ingredient_slug',
                        side_effect=lambda ing, cache=None: ing.get('canonical')):
            first = self.client.post('/api/discover/', {'q': 'čočka'}, format='json').json()
            second = self.client.post('/api/discover/', {'q': 'čočka'}, format='json').json()
        self.assertEqual(first['data']['recipes'][0]['deals']['matched'], 0)
        self.assertEqual(second['data']['recipes'][0]['deals']['matched'], 1)

    def _ttl_for(self, q):
        fake = mock.MagicMock()
        fake.get.return_value = None
        with mock.patch('diet_planner.views_discover.cache', fake):
            self.client.post('/api/discover/', {'q': q}, format='json')
        return fake.set.call_args.args[2]

    def test_fallback_result_expires_quickly(self):
        # setUp makes every LLM read fail, so a non-empty q is a fallback.
        self.assertEqual(self._ttl_for('čočka'), 5 * 60)

    def test_exact_and_empty_results_keep_a_day(self):
        self.assertEqual(self._ttl_for(''), 24 * 60 * 60)
        exact = {'understood': [], 'exact': True, 'fallback': False, 'medical_note': False,
                 'ranked_ids': [self.a.id], 'recipes': [], 'has_more': False}
        with mock.patch('diet_planner.views_discover.discover', return_value=exact):
            self.assertEqual(self._ttl_for('kuře'), 24 * 60 * 60)

    def test_cached_output_is_ids_not_cards(self):
        fake = mock.MagicMock()
        fake.get.return_value = None
        with mock.patch('diet_planner.views_discover.cache', fake):
            self.client.post('/api/discover/', {'q': 'cukrovka'}, format='json')
        stored = fake.set.call_args.args[1]
        self.assertEqual(set(stored), {'understood', 'exact', 'fallback', 'medical_note', 'ids'})
        self.assertTrue(stored['medical_note'])
        self.assertLessEqual(len(stored['ids']), 60)

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
