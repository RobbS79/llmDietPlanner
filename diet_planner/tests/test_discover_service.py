from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.discover import discover, understood_labels
from diet_planner.services.prompt_facets import PromptFacets


def _recipe(slug, name, ingredients, **kw):
    d = dict(slug=slug, name_cs=name, meal_types=['lunch', 'dinner'], dish_role='main',
             ingredients=[{'name': n, 'canonical': c} for n, c in ingredients],
             instructions=['x'], source_url=f'https://e.com/{slug}', source_name='E',
             status=CuratedRecipe.Status.PUBLISHED, prep_time=10, cook_time=10)
    d.update(kw)
    return CuratedRecipe.objects.create(**d)


class DiscoverServiceTest(TestCase):
    def setUp(self):
        self.chicken = _recipe('kure', 'Kuře s rýží', [('kuřecí prsa', 'chicken-breast'), ('rýže', 'rice')])
        self.lentil = _recipe('cocka', 'Čočkový guláš', [('čočka', 'lentils'), ('cibule', 'onion')],
                              dietary_tags=['vegetarian'])
        self.pork = _recipe('rizek', 'Vepřový řízek', [('vepřová kýta', 'pork-leg')], cook_time=50)
        _recipe('side', 'Rýže', [('rýže', 'rice')], dish_role='side')  # never a main

    def _gen(self, payload):
        return lambda system, user: payload

    def test_wanted_ingredient_is_exact_and_first(self):
        out = discover('co uvařit z kuřecích prsou', 0, llm_allowed=True,
                       generate=self._gen('{"wanted_ingredients": ["kuřecí prsa"]}'))
        self.assertTrue(out['exact'])
        self.assertFalse(out['fallback'])
        self.assertEqual(out['recipes'][0].id, self.chicken.id)
        self.assertIn('kuřecí prsa', out['understood'])

    def test_vegetarian_rule_is_a_hard_gate(self):
        out = discover('bez masa', 0, llm_allowed=True,
                       generate=self._gen('{"dietary": ["vegetarian"]}'))
        self.assertEqual([r.id for r in out['recipes']], [self.lentil.id])

    def test_time_limit_excludes_slow_dishes(self):
        out = discover('do 30 minut', 0, llm_allowed=True,
                       generate=self._gen('{"max_time_minutes": 30}'))
        self.assertNotIn(self.pork.id, [r.id for r in out['recipes']])

    def test_no_match_returns_nearest_not_exact(self):
        out = discover('chci kachnu', 0, llm_allowed=True,
                       generate=self._gen('{"wanted_ingredients": ["kachna"]}'))
        self.assertFalse(out['exact'])
        self.assertTrue(out['recipes'])

    def test_sides_never_appear(self):
        out = discover('rýže', 0, llm_allowed=False)
        self.assertNotIn('Rýže', [r.name_cs for r in out['recipes']])

    def test_text_fallback_when_llm_not_allowed(self):
        out = discover('kuřecí prsa', 0, llm_allowed=False)
        self.assertTrue(out['fallback'])
        self.assertEqual(out['recipes'][0].id, self.chicken.id)

    def test_llm_failure_falls_back(self):
        def boom(system, user):
            raise TimeoutError('slow')
        out = discover('kuřecí prsa', 0, llm_allowed=True, generate=boom)
        self.assertTrue(out['fallback'])

    def test_paging(self):
        out = discover('', 0, llm_allowed=False, page_size=2)
        self.assertEqual(len(out['recipes']), 2)
        self.assertTrue(out['has_more'])

    def test_understood_labels_are_czech(self):
        f = PromptFacets(dietary={'vegetarian'}, max_time_minutes=30, emphases={'low_carb'},
                         styles={'meal_prep'})
        self.assertEqual(understood_labels(f),
                         ['bez masa', 'do 30 minut', 'méně sacharidů', 'do krabiček'])

    def test_filler_only_text_query_is_not_exact(self):
        out = discover('chci něco uvařit', 0, llm_allowed=False)
        self.assertFalse(out['exact'])
        self.assertTrue(out['recipes'])

    def test_dietary_rule_survives_no_exact_fallback(self):
        # Nothing vegetarian fits 5 minutes: the nearest list may relax the
        # time limit, never the dietary rule.
        out = discover('bez masa do 5 minut', 0, llm_allowed=True,
                       generate=self._gen('{"dietary": ["vegetarian"], "max_time_minutes": 5}'))
        self.assertFalse(out['exact'])
        self.assertEqual([r.id for r in out['recipes']], [self.lentil.id])
