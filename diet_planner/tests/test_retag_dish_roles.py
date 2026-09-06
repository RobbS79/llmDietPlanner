"""retag_dish_roles: backfill of dish_role/meal_types/side_options/dish_family
with a dry-run review report the owner reads before anything is written."""
import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def make_recipe(name_cs, **kw):
    defaults = dict(
        name_cs=name_cs,
        status=CuratedRecipe.Status.PUBLISHED,
        meal_types=['lunch', 'dinner'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'}],
        instructions=[{'text': 'Uvař.'}],
        base_servings=2,
        base_nutrition={'calories': 600},
        source_url='https://example.test/r',
        source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


def fake_generate_for(mapping):
    """{slug: {dish_role, meal_types, side_options, dish_family}} → generate stub."""
    def _gen(system_prompt, user_text):
        asked = [item['slug'] for item in json.loads(user_text)]
        return json.dumps([{'slug': s, **mapping[s]} for s in asked if s in mapping])
    return _gen


def full(role, meal_types=None, sides=None, family=''):
    return {'dish_role': role, 'meal_types': meal_types or ['lunch', 'dinner'],
            'side_options': sides or [], 'dish_family': family}


class RetagDishRolesTest(TestCase):
    def _run(self, mapping, *args):
        out = StringIO()
        with patch('diet_planner.services.dish_classification._generate',
                   side_effect=fake_generate_for(mapping)):
            call_command('retag_dish_roles', *args, stdout=out)
        return out.getvalue()

    def test_tags_untagged_recipes_with_all_fields(self):
        r = make_recipe('Lečo s klobásou')
        self._run({r.slug: full('supper', ['dinner'], ['chleb'], 'leco')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'supper')
        self.assertEqual(r.meal_types, ['dinner'])
        self.assertEqual(r.side_options, ['chleb'])
        self.assertEqual(r.dish_family, 'leco')

    def test_dry_run_writes_nothing_and_reports_change(self):
        r = make_recipe('Guláš')
        out = self._run({r.slug: full('main', sides=['knedlik'], family='gulas')}, '--dry-run')
        r.refresh_from_db()
        self.assertEqual(r.dish_role, '')
        self.assertIn('(empty) -> main', out)
        self.assertIn('knedlik', out)

    def test_already_tagged_skipped_without_force(self):
        r = make_recipe('Omeleta', dish_role=CuratedRecipe.DishRole.LIGHT)
        self._run({r.slug: full('breakfast')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'light')

    def test_force_retags_light_rows(self):
        r = make_recipe('Omeleta 2', dish_role=CuratedRecipe.DishRole.LIGHT)
        self._run({r.slug: full('breakfast', ['breakfast'])}, '--force')
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'breakfast')

    def test_invalid_role_from_llm_is_not_written(self):
        r = make_recipe('Podivné jídlo')
        out = self._run({r.slug: full('banquet')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, '')
        self.assertIn('banquet', out)

    def test_overrides_win_over_llm(self):
        r = make_recipe('Lečo')
        self._run({r.slug: full('main', ['lunch', 'dinner'], [], 'leco')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'supper')      # by_family: leco
        self.assertEqual(r.meal_types, ['dinner'])
        self.assertEqual(r.side_options, ['chleb'])

    def test_report_has_histogram_and_lunch_pool_warning(self):
        mains = [make_recipe(f'Jídlo {i}', dish_role='main') for i in range(3)]
        mapping = {m.slug: full('supper', ['dinner'], [], f'f{i}') for i, m in enumerate(mains)}
        out = self._run(mapping, '--force', '--dry-run')
        self.assertIn('Role histogram', out)
        self.assertIn('before: main 3', out)
        self.assertIn('after:', out)
        self.assertIn('Lunch pool', out)
        self.assertIn('WARNING', out)  # 0 < 15

    def test_drafts_are_tagged_too(self):
        r = make_recipe('Koncept', status=CuratedRecipe.Status.DRAFT)
        self._run({r.slug: full('main')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'main')
