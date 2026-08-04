"""Tests for the retag_dish_roles management command (dish-role backfill)."""
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
        ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g'}],
        instructions=[{'text': 'Uvař.'}],
        base_servings=2,
        base_nutrition={'calories': 600},
        source_url='https://example.test/r',
        source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


def fake_generate_for(mapping):
    """A generate stub that answers with roles from {slug: role} for whatever
    recipes the command actually asked about."""
    def _gen(system_prompt, user_text):
        asked = [item['slug'] for item in json.loads(user_text)]
        return json.dumps([
            {'slug': s, 'dish_role': mapping[s]} for s in asked if s in mapping
        ])
    return _gen


class RetagDishRolesTest(TestCase):
    def _run(self, mapping, *args):
        out = StringIO()
        with patch(
            'diet_planner.management.commands.retag_dish_roles._generate',
            side_effect=fake_generate_for(mapping),
        ):
            call_command('retag_dish_roles', *args, stdout=out)
        return out.getvalue()

    def test_tags_untagged_recipes(self):
        r1 = make_recipe('Kuřecí stehna s rýží')
        r2 = make_recipe('Fazolový salát základní')
        self._run({r1.slug: 'main', r2.slug: 'side'})
        r1.refresh_from_db(); r2.refresh_from_db()
        self.assertEqual(r1.dish_role, CuratedRecipe.DishRole.MAIN)
        self.assertEqual(r2.dish_role, CuratedRecipe.DishRole.SIDE)

    def test_dry_run_writes_nothing(self):
        r = make_recipe('Guláš')
        out = self._run({r.slug: 'main'}, '--dry-run')
        r.refresh_from_db()
        self.assertEqual(r.dish_role, '')
        self.assertIn('main', out)  # proposed role is still reported

    def test_already_tagged_skipped_without_force(self):
        r = make_recipe('Omeleta', dish_role=CuratedRecipe.DishRole.LIGHT)
        self._run({r.slug: 'main'})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, CuratedRecipe.DishRole.LIGHT)

    def test_force_retags_already_tagged(self):
        r = make_recipe('Omeleta 2', dish_role=CuratedRecipe.DishRole.MAIN)
        self._run({r.slug: 'light'}, '--force')
        r.refresh_from_db()
        self.assertEqual(r.dish_role, CuratedRecipe.DishRole.LIGHT)

    def test_invalid_role_from_llm_is_not_written(self):
        r = make_recipe('Podivné jídlo')
        out = self._run({r.slug: 'banquet'})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, '')
        self.assertIn('banquet', out)  # surfaced for the operator

    def test_drafts_are_tagged_too(self):
        r = make_recipe('Koncept', status=CuratedRecipe.Status.DRAFT)
        self._run({r.slug: 'main'})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, CuratedRecipe.DishRole.MAIN)
