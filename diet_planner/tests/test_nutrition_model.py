"""Per-100 g nutrition lives on the canonical ingredient; the YAML seeds it."""
from decimal import Decimal
from io import StringIO
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CanonicalIngredient, CuratedRecipe
from diet_planner.services.nutrition_lookups import nutrition_table
from diet_planner.services.piece_weights import load_piece_weights, clear_cache


class NutritionFieldsTest(TestCase):
    def test_has_nutrition_requires_all_four_nutrients(self):
        c = CanonicalIngredient.objects.create(name='Chicken breast', slug='t-chicken',
                                               kcal_per_100g=165, protein_per_100g=31,
                                               carbs_per_100g=0, fat_per_100g=3.6)
        self.assertTrue(c.has_nutrition)
        c.fat_per_100g = None
        self.assertFalse(c.has_nutrition)

    def test_curated_recipe_defaults_to_no_blockers(self):
        r = CuratedRecipe.objects.create(name_cs='x', base_servings=1)
        self.assertEqual(r.nutrition_blockers, [])


class SeedNutritionTest(TestCase):
    def _seed(self, yaml_text):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False, encoding='utf-8') as fh:
            fh.write(yaml_text)
        out = StringIO()
        call_command('seed_canonical_ingredients', file=fh.name, stdout=out)
        Path(fh.name).unlink()
        return out.getvalue()

    def test_seed_writes_nutrition_density_and_unit_weights(self):
        self._seed("""
- name: olive oil
  name_cs: olivový olej
  category: oils
  nutrition:
    kcal: 884
    protein: 0
    carbs: 0
    fat: 100
    density: 0.92
    source: usda:171413
- name: garlic
  name_cs: česnek
  category: vegetables
  nutrition:
    kcal: 149
    protein: 6.4
    carbs: 33.1
    fat: 0.5
    piece_weight_g: 40
    unit_weights: {stroužek: 5}
    source: usda:169230
""")
        oil = CanonicalIngredient.objects.get(slug='olive-oil')
        self.assertEqual(oil.kcal_per_100g, Decimal('884'))
        self.assertEqual(oil.density_g_per_ml, Decimal('0.920'))
        self.assertEqual(oil.nutrition_source, 'usda:171413')
        garlic = CanonicalIngredient.objects.get(slug='garlic')
        self.assertEqual(garlic.avg_piece_weight_g, Decimal('40'))
        self.assertEqual(garlic.unit_weights, {'stroužek': 5})
        self.assertTrue(garlic.has_nutrition)

    def test_seed_without_nutrition_block_leaves_fields_null(self):
        self._seed("- name: mystery\n  category: other\n")
        c = CanonicalIngredient.objects.get(slug='mystery')
        self.assertIsNone(c.kcal_per_100g)
        self.assertFalse(c.has_nutrition)

    def test_nutrition_table_and_piece_weights_read_the_db(self):
        self._seed("""
- name: onion
  category: vegetables
  nutrition: {kcal: 40, protein: 1.1, carbs: 9.3, fat: 0.1, piece_weight_g: 110, source: usda:170000}
""")
        clear_cache()
        row = nutrition_table()['onion']
        self.assertEqual((row.kcal, row.protein, row.carbs, row.fat), (40.0, 1.1, 9.3, 0.1))
        self.assertEqual(row.piece_weight_g, 110.0)
        self.assertIsNone(row.density)
        self.assertEqual(load_piece_weights()['onion'], 110.0)
