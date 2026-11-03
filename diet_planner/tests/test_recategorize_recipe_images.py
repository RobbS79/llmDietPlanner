from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import DietaryGoal, Recipe


class RecategorizeTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username='c')
        goal = DietaryGoal.objects.create(
            user=user, prompt='x', num_days=1, country='CZ', currency='CZK', language_code='cs')
        self.r = Recipe.objects.create(
            dietary_goal=goal, meal_identifier='g:1:dinner:0', name='Kuře Hasselback Primavera',
            servings=4, food_category='mlete-maso', ingredients=[], instructions=[])

    def test_dry_run_changes_nothing(self):
        out = StringIO()
        call_command('recategorize_recipe_images', stdout=out)
        self.r.refresh_from_db()
        self.assertEqual(self.r.food_category, 'mlete-maso')
        self.assertIn('mlete-maso -> kure', out.getvalue())

    def test_apply_fixes(self):
        call_command('recategorize_recipe_images', '--apply', stdout=StringIO())
        self.r.refresh_from_db()
        self.assertEqual(self.r.food_category, 'kure')
