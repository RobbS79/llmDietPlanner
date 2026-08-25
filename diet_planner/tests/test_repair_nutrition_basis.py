"""The corpus-wide repair of per-portion figures stored in base_nutrition."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import CanonicalIngredient
from diet_planner.tests.test_recipe_replace import make_recipe

# 500 kcal claimed for 4 portions of a 2.2 kg soup: a real basis bug.
WRONG_BASIS = dict(
    name_cs='Kari čočková polévka',
    base_servings=4,
    dish_role='main',
    base_nutrition={'calories': 500, 'protein': 17, 'carbs': 46, 'fat': 28},
    ingredients=[
        {'name': 'čočka', 'quantity': 400, 'unit': 'g', 'canonical': 'lentils'},
        {'name': 'vývar', 'quantity': 1800, 'unit': 'ml', 'canonical': 'stock'},
    ],
)

# 12 egg muffins: base_servings counts pieces, so the total is already right.
PIECE_SERVINGS = dict(
    name_cs='Středomořské vaječné muffiny',
    base_servings=12,
    dish_role='light',
    base_nutrition={'calories': 804, 'protein': 55.2, 'carbs': 14.4, 'fat': 56.4},
    ingredients=[
        {'name': 'vejce', 'quantity': 720, 'unit': 'g', 'canonical': 'eggs'},
        {'name': 'feta', 'quantity': 100, 'unit': 'g', 'canonical': 'feta'},
    ],
)


def _run(*args):
    out = StringIO()
    call_command('repair_nutrition_basis', *args, stdout=out)
    return out.getvalue()


class RepairNutritionBasisCommandTest(TestCase):
    def setUp(self):
        for slug, category in [('lentils', 'legumes'), ('stock', 'beverages'),
                               ('eggs', 'eggs'), ('feta', 'dairy')]:
            CanonicalIngredient.objects.create(
                name=slug, slug=slug, category=category)

    def test_dry_run_reports_the_repair_without_touching_the_row(self):
        recipe = make_recipe(**WRONG_BASIS)

        output = _run()

        recipe.refresh_from_db()
        self.assertEqual(recipe.base_nutrition['calories'], 500)
        self.assertIn('kari-cockova-polevka', output)
        self.assertIn('500 -> 2000', output)
        self.assertIn('DRY RUN', output)

    def test_apply_multiplies_the_stored_nutrition_by_base_servings(self):
        recipe = make_recipe(**WRONG_BASIS)

        _run('--apply')

        recipe.refresh_from_db()
        self.assertEqual(recipe.base_nutrition,
                         {'calories': 2000, 'protein': 68, 'carbs': 184, 'fat': 112})

    def test_apply_leaves_a_piece_counted_recipe_untouched(self):
        recipe = make_recipe(**PIECE_SERVINGS)

        output = _run('--apply')

        recipe.refresh_from_db()
        self.assertEqual(recipe.base_nutrition['calories'], 804)
        self.assertIn('macros_exceed_mass', output)

    def test_apply_prints_a_reversal_map_for_every_row_it_rewrites(self):
        make_recipe(**WRONG_BASIS)

        output = _run('--apply')

        self.assertIn('REVERSAL', output)
        self.assertIn('"kari-cockova-polevka"', output)
        self.assertIn('"calories": 500', output)

    def test_only_published_recipes_are_repaired_by_default(self):
        draft = make_recipe(status=CuratedRecipe.Status.DRAFT, **WRONG_BASIS)

        _run('--apply')

        draft.refresh_from_db()
        self.assertEqual(draft.base_nutrition['calories'], 500)

    def test_status_all_reaches_drafts(self):
        draft = make_recipe(status=CuratedRecipe.Status.DRAFT, **WRONG_BASIS)

        _run('--apply', '--status', 'all')

        draft.refresh_from_db()
        self.assertEqual(draft.base_nutrition['calories'], 2000)
