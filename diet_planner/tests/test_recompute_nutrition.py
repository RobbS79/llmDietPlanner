import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.tests.factories import make_canonical


class RecomputeNutritionTest(TestCase):
    def setUp(self):
        make_canonical('Chicken breast', slug='chicken-breast', kcal_per_100g=165, protein_per_100g=31,
                       carbs_per_100g=0, fat_per_100g=3.6)
        make_canonical('Rice basmati', slug='rice-basmati', kcal_per_100g=360, protein_per_100g=7,
                       carbs_per_100g=79, fat_per_100g=0.6)
        make_canonical('Mystery', slug='mystery')   # no nutrition
        self.ok = CuratedRecipe.objects.create(
            name_cs='Kuře s rýží', status='published', base_servings=2, dish_role='main',
            base_nutrition={'calories': 900, 'protein': 50, 'carbs': 80, 'fat': 20},
            ingredients=[{'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g', 'canonical': 'chicken-breast'},
                         {'name': 'rýže', 'quantity': 200, 'unit': 'g', 'canonical': 'rice-basmati'}])
        self.bad = CuratedRecipe.objects.create(
            name_cs='Záhada', status='published', base_servings=1, dish_role='main',
            base_nutrition={'calories': 500},
            ingredients=[{'name': 'záhada', 'quantity': 100, 'unit': 'g', 'canonical': 'mystery'},
                         {'name': 'olej', 'quantity': 2, 'unit': 'lžíce', 'canonical': 'chicken-breast'}])

    def test_dry_run_reports_deltas_and_worklist_without_writing(self):
        out = StringIO()
        call_command('recompute_nutrition', stdout=out)
        text = out.getvalue()
        self.assertIn('Kuře s rýží', text)
        self.assertIn('900 -> 1380', text)
        self.assertIn('mystery', text)          # worklist by (canonical, unit, reason)
        self.assertIn('no_nutrition', text)
        self.assertIn('no_density', text)
        self.assertIn('complete=1 incomplete=1', text)
        self.ok.refresh_from_db()
        self.assertEqual(self.ok.base_nutrition['calories'], 900)

    def test_apply_refuses_while_a_published_recipe_is_incomplete(self):
        with self.assertRaises(CommandError):
            call_command('recompute_nutrition', apply=True, stdout=StringIO())
        self.ok.refresh_from_db()
        self.assertEqual(self.ok.base_nutrition['calories'], 900)

    def test_apply_with_skip_incomplete_writes_complete_rows_and_reversal_map(self):
        out = StringIO()
        call_command('recompute_nutrition', apply=True, skip_incomplete=True, stdout=out)
        self.ok.refresh_from_db(); self.bad.refresh_from_db()
        self.assertEqual(self.ok.base_nutrition['calories'], 1380)
        self.assertEqual(self.ok.base_nutrition['source'], 'computed')
        self.assertEqual(self.ok.nutrition_blockers, [])
        self.assertEqual(self.bad.base_nutrition['calories'], 500)
        self.assertEqual({b['reason'] for b in self.bad.nutrition_blockers}, {'no_nutrition', 'no_density'})
        text = out.getvalue()
        self.assertIn('REVERSAL', text)
        rev = json.loads(text.split('REVERSAL')[1].strip().splitlines()[0])
        self.assertEqual(rev[str(self.ok.pk)]['calories'], 900)

    def test_report_csv(self):
        import csv, tempfile
        path = tempfile.mktemp(suffix='.csv')
        call_command('recompute_nutrition', report=path, stdout=StringIO())
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
        self.assertEqual({r['slug'] for r in rows}, {self.ok.slug, self.bad.slug})

    def test_implausible_computed_value_is_not_written(self):
        big = CuratedRecipe.objects.create(
            name_cs='Obří kuře', status='published', base_servings=1, dish_role='main',
            base_nutrition={'calories': 600},
            ingredients=[{'name': 'kuřecí prsa', 'quantity': 5000, 'unit': 'g', 'canonical': 'chicken-breast'}])
        call_command('recompute_nutrition', apply=True, skip_incomplete=True, stdout=StringIO())
        big.refresh_from_db()
        self.assertEqual(big.base_nutrition['calories'], 600)
        self.assertIn('implausible', {b['reason'] for b in big.nutrition_blockers})
