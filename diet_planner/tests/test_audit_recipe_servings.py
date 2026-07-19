"""Servings audit on the public showcase: detection, proposals, apply semantics."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from diet_planner.management.commands.audit_recipe_servings import (
    audit_recipe,
    normalize_weighable,
    propose_servings,
)
from diet_planner.models import DietaryGoal, Recipe


INSTRUCTIONS = [
    'Brambory nastrouhejte najemno a smíchejte s moukou a solí na těsto.',
    'Lžící vykrajujte halušky do vroucí vody a vařte, dokud nevyplavou.',
    'Smíchejte s brynzou a podávejte posypané opečenou slaninou.',
]


class HelpersTest(TestCase):
    def test_normalize_weighable_converts_kg_and_l(self):
        rows = normalize_weighable([
            {'name': 'brambory', 'quantity': '1,5', 'unit': 'kg'},
            {'name': 'vývar', 'quantity': 0.5, 'unit': 'l'},
            {'name': 'mouka', 'quantity': 500, 'unit': 'g'},
            {'name': 'sůl', 'quantity': None, 'unit': 'kg'},
        ])
        self.assertEqual(rows[0], {'name': 'brambory', 'quantity': 1500.0, 'unit': 'g'})
        self.assertEqual(rows[1], {'name': 'vývar', 'quantity': 500.0, 'unit': 'ml'})
        self.assertEqual(rows[2]['unit'], 'g')
        # Unparseable quantity passes through untouched rather than crashing.
        self.assertEqual(rows[3]['unit'], 'kg')

    def test_propose_servings_backs_out_portions_from_total_mass(self):
        # 2250 g at "1 porce" → 5 portions of 450 g.
        self.assertEqual(propose_servings(2250.0, 1), 5)
        # Never proposes 0, capped at the stepper maximum.
        self.assertEqual(propose_servings(100.0, 1), 1)
        self.assertEqual(propose_servings(20000.0, 1), 20)


class AuditRecipeTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )

    def _recipe(self, ident, servings, ingredients):
        return Recipe.objects.create(
            meal_identifier=ident, dietary_goal=self.goal,
            name='Bramborové halušky', servings=servings,
            instructions=INSTRUCTIONS, ingredients=ingredients,
        )

    def test_plausible_recipe_is_ok(self):
        recipe = self._recipe('g:1:lunch:0', 4, [
            {'name': 'brambory', 'quantity': 800, 'unit': 'g'},
            {'name': 'mouka', 'quantity': 300, 'unit': 'g'},
        ])
        status, _ = audit_recipe(recipe)
        self.assertEqual(status, 'ok')

    def test_halusky_case_kg_at_one_serving_gets_fixed(self):
        # The prod bug: kg-denominated quantities with servings=1.
        recipe = self._recipe('g:2:lunch:0', 1, [
            {'name': 'brambory', 'quantity': '1,5', 'unit': 'kg'},
            {'name': 'hrubá mouka', 'quantity': 0.5, 'unit': 'kg'},
            {'name': 'brynza', 'quantity': 250, 'unit': 'g'},
        ])
        status, detail = audit_recipe(recipe)
        self.assertEqual(status, 'fix')
        self.assertEqual(detail['proposed'], 5)  # 2250 g / 450 g

    def test_absurd_mass_is_unpublished_not_fixed(self):
        recipe = self._recipe('g:3:lunch:0', 1, [
            {'name': 'brambory', 'quantity': 20, 'unit': 'kg'},
        ])
        status, detail = audit_recipe(recipe)
        self.assertEqual(status, 'unpublish')
        self.assertEqual(detail['proposed'], 20)  # capped, still 1000 g/portion


class ApplyCommandTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.fixable = Recipe.objects.create(
            meal_identifier='g:1:lunch:0', dietary_goal=self.goal,
            name='Bramborové halušky', servings=1, instructions=INSTRUCTIONS,
            ingredients=[{'name': 'brambory', 'quantity': '1,5', 'unit': 'kg'},
                         {'name': 'mouka', 'quantity': 500, 'unit': 'g'}],
        )
        self.hopeless = Recipe.objects.create(
            meal_identifier='g:2:lunch:0', dietary_goal=self.goal,
            name='Obří guláš', servings=1, instructions=INSTRUCTIONS,
            ingredients=[{'name': 'hovězí', 'quantity': 25, 'unit': 'kg'}],
        )

    def test_dry_run_changes_nothing(self):
        out = StringIO()
        call_command('audit_recipe_servings', stdout=out)
        self.fixable.refresh_from_db()
        self.hopeless.refresh_from_db()
        self.assertEqual(self.fixable.servings, 1)
        self.assertTrue(self.hopeless.is_public)
        self.assertIn('Dry run', out.getvalue())

    def test_apply_fixes_servings_and_unpublishes_hopeless_rows(self):
        out = StringIO()
        call_command('audit_recipe_servings', '--apply', stdout=out)
        self.fixable.refresh_from_db()
        self.hopeless.refresh_from_db()
        self.assertEqual(self.fixable.servings, 4)  # 2000 g / 450
        self.assertTrue(self.fixable.is_public)
        # Unpublished via queryset .update(): save() would have re-promoted it.
        self.assertFalse(self.hopeless.is_public)
