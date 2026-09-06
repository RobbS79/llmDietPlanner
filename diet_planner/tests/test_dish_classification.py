"""Gemini dish classification: parsing, vocabulary validation, overrides."""
import json
from types import SimpleNamespace

from django.test import TestCase

from diet_planner.services import dish_classification as dc


def recipe(slug, name='X', **kw):
    base = dict(slug=slug, name_cs=name, description='', meal_types=['lunch'],
                ingredients=[{'name': 'sůl'}], base_servings=2,
                base_nutrition={'calories': 600}, cuisine='czech')
    base.update(kw)
    return SimpleNamespace(**base)


class ParseAnswerTest(TestCase):
    def test_parses_all_four_fields(self):
        raw = json.dumps([{'slug': 'leco', 'dish_role': 'supper', 'meal_types': ['dinner'],
                           'side_options': ['chleb'], 'dish_family': 'leco'}])
        out = dc.parse_answer(raw)
        c = out['leco']
        self.assertEqual((c.dish_role, c.meal_types, c.side_options, c.dish_family),
                         ('supper', ['dinner'], ['chleb'], 'leco'))
        self.assertEqual(c.problems, [])

    def test_unknown_values_are_dropped_and_reported(self):
        raw = json.dumps([{'slug': 'x', 'dish_role': 'banquet', 'meal_types': ['brunch', 'lunch'],
                           'side_options': ['sushi', 'ryze'], 'dish_family': 'Kuře Pečené'}])
        c = dc.parse_answer(raw)['x']
        self.assertEqual(c.dish_role, '')
        self.assertEqual(c.meal_types, ['lunch'])
        self.assertEqual(c.side_options, ['ryze'])
        self.assertEqual(c.dish_family, 'kure-pecene')
        self.assertTrue(any('banquet' in p for p in c.problems))

    def test_light_is_never_accepted_from_the_llm(self):
        c = dc.parse_answer(json.dumps([{'slug': 'x', 'dish_role': 'light'}]))['x']
        self.assertEqual(c.dish_role, '')

    def test_garbage_is_empty_dict(self):
        self.assertEqual(dc.parse_answer('not json'), {})
        self.assertEqual(dc.parse_answer('{"a": 1}'), {})


class ClassifyRecipesTest(TestCase):
    def test_batches_and_keys_by_slug(self):
        calls = []

        def gen(system, user):
            asked = [i['slug'] for i in json.loads(user)]
            calls.append(asked)
            return json.dumps([{'slug': s, 'dish_role': 'main', 'meal_types': ['lunch'],
                                'side_options': [], 'dish_family': s} for s in asked])
        recipes = [recipe(f'r{i}') for i in range(30)]
        out = dc.classify_recipes(recipes, generate=gen, batch_size=25)
        self.assertEqual(len(calls), 2)
        self.assertEqual(set(out), {r.slug for r in recipes})

    def test_failed_batch_is_skipped_not_raised(self):
        def gen(system, user):
            raise RuntimeError('boom')
        self.assertEqual(dc.classify_recipes([recipe('a')], generate=gen), {})


class OverridesTest(TestCase):
    OVR = {
        'by_slug': {'domaci-leco': {'dish_role': 'side', 'meal_types': ['small_meal'], 'side_options': []}},
        'by_family': {'leco': {'dish_role': 'supper', 'meal_types': ['dinner'], 'side_options': ['chleb']}},
    }

    def _c(self, **kw):
        base = dict(dish_role='main', meal_types=['lunch', 'dinner'], side_options=[], dish_family='leco')
        base.update(kw)
        return dc.Classification(**base)

    def test_family_override_applies(self):
        out = dc.apply_overrides('leco-s-klobasou', self._c(), overrides=self.OVR)
        self.assertEqual((out.dish_role, out.meal_types, out.side_options), ('supper', ['dinner'], ['chleb']))

    def test_slug_override_beats_family(self):
        out = dc.apply_overrides('domaci-leco', self._c(), overrides=self.OVR)
        self.assertEqual(out.dish_role, 'side')
        self.assertEqual(out.meal_types, ['small_meal'])

    def test_override_sets_only_named_fields(self):
        ovr = {'by_slug': {'x': {'dish_family': 'gulas'}}, 'by_family': {}}
        out = dc.apply_overrides('x', self._c(dish_family=''), overrides=ovr)
        self.assertEqual(out.dish_family, 'gulas')
        self.assertEqual(out.dish_role, 'main')

    def test_shipped_file_parses_and_pins_leco(self):
        ovr = dc.load_overrides()
        self.assertEqual(ovr['by_family']['leco']['dish_role'], 'supper')
        self.assertEqual(ovr['by_slug']['domaci-leco']['dish_role'], 'side')
        for section in ('by_slug', 'by_family'):
            for key, entry in ovr[section].items():
                self.assertRegex(key, r'^[a-z0-9-]+$')
                self.assertTrue(set(entry) <= {'dish_role', 'meal_types', 'side_options', 'dish_family', 'note'}, key)
