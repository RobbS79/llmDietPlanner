"""remap_curated_recipes recomputes nutrition for drafts but never blanks or
overwrites a PUBLISHED recipe's served base_nutrition (that is
recompute_nutrition --apply's job, with its reversal map)."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.tests.factories import make_canonical

LEGACY = {'calories': 500, 'protein': 20, 'carbs': 60, 'fat': 15}


class RemapNutritionTest(TestCase):
    def setUp(self):
        make_canonical('Chicken breast', slug='chicken-breast', name_cs='kuřecí prsa',
                       kcal_per_100g=165, protein_per_100g=31, carbs_per_100g=0, fat_per_100g=3.6,
                       category='meat')
        clear_cache()

    def _run(self, *args):
        call_command('remap_curated_recipes', *args, stdout=StringIO())

    def test_published_incomplete_keeps_nutrition_and_gets_blockers(self):
        r = CuratedRecipe.objects.create(
            name_cs='pub', status=CuratedRecipe.Status.PUBLISHED, base_servings=2, base_nutrition=LEGACY,
            ingredients=[{'name': 'dračí ovoce', 'quantity': 100, 'unit': 'g'}])
        self._run()
        r.refresh_from_db()
        self.assertEqual(r.base_nutrition, LEGACY)
        self.assertEqual(r.nutrition_blockers[0]['reason'], 'no_canonical')
        self.assertEqual(r.status, CuratedRecipe.Status.PUBLISHED)

    def test_published_complete_nutrition_is_not_overwritten(self):
        r = CuratedRecipe.objects.create(
            name_cs='pub', status=CuratedRecipe.Status.PUBLISHED, base_servings=2, base_nutrition=LEGACY,
            ingredients=[{'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g'}])
        self._run()
        r.refresh_from_db()
        self.assertEqual(r.base_nutrition, LEGACY)
        self.assertEqual(r.ingredients[0]['canonical'], 'chicken-breast')

    def test_draft_gets_computed_nutrition(self):
        r = CuratedRecipe.objects.create(
            name_cs='draft', base_servings=2, base_nutrition=LEGACY,
            ingredients=[{'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g'}])
        self._run()
        r.refresh_from_db()
        self.assertEqual(r.base_nutrition['source'], 'computed')
        self.assertEqual(r.base_nutrition['calories'], 660)
        self.assertEqual(r.nutrition_blockers, [])

    def test_dry_run_writes_nothing(self):
        r = CuratedRecipe.objects.create(
            name_cs='draft', base_servings=2, base_nutrition=LEGACY,
            ingredients=[{'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g'}])
        before = CuratedRecipe.objects.filter(pk=r.pk).values().get()
        self._run('--dry-run')
        self.assertEqual(CuratedRecipe.objects.filter(pk=r.pk).values().get(), before)
