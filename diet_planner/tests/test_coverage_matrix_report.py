"""Tests for the coverage_matrix_report management command."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _published(slug, meal_types, dietary_tags, *, mapped=True):
    ing_canonical = 'rice-basmati' if mapped else None
    ingredient = {'name': 'rice', 'quantity': 100, 'unit': 'g'}
    if ing_canonical:
        ingredient['canonical'] = ing_canonical
    return CuratedRecipe.objects.create(
        name_cs=f"Recipe {slug}",
        slug=slug,
        status=CuratedRecipe.Status.PUBLISHED,
        meal_types=meal_types,
        dietary_tags=dietary_tags,
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=[ingredient],
        instructions=[{'text': 'cook'}],
        base_servings=1,
        base_nutrition={'calories': 500},
        source_url=f'https://example.test/{slug}',
        source_name='Example',
    )


class CoverageMatrixBasicTest(TestCase):
    def test_counts_published_eligible_per_cell(self):
        _published('a', ['lunch'], [])
        _published('b', ['lunch', 'dinner'], ['vegan'])
        _published('c', ['breakfast'], ['gluten_free', 'vegan'])

        out = StringIO()
        call_command('coverage_matrix_report', stdout=out)
        output = out.getvalue()

        # The header / row labels should at least mention the standard
        # slots and tags we report on.
        self.assertIn('breakfast', output)
        self.assertIn('lunch', output)
        self.assertIn('dinner', output)
        self.assertIn('vegan', output)
        self.assertIn('gluten_free', output)
        # And the totals row/column should reflect 3 distinct published recipes.
        self.assertIn('3', output)


class CoverageMatrixUnmappedExcludedTest(TestCase):
    def test_unmapped_published_recipe_not_counted(self):
        _published('a', ['lunch'], [], mapped=False)  # not catalog-mapped
        out = StringIO()
        call_command('coverage_matrix_report', '--csv', stdout=out)
        # Sum of all cells in the lunch row should be 0.
        for ln in out.getvalue().splitlines():
            if ln.startswith('lunch,'):
                # Last column is total.
                self.assertEqual(int(ln.rsplit(',', 1)[-1]), 0)
                return
        self.fail('lunch row not present in CSV')


class CoverageMatrixDraftsExcludedTest(TestCase):
    def test_drafts_not_counted_unless_flag_set(self):
        # Create a catalog-mapped DRAFT.
        CuratedRecipe.objects.create(
            name_cs='Draft Lunch',
            slug='draft-lunch',
            status=CuratedRecipe.Status.DRAFT,
            meal_types=['lunch'],
            dietary_tags=[],
            cuisine='czech',
            difficulty=CuratedRecipe.Difficulty.EASY,
            ingredients=[
                {'name': 'rice', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
            ],
            instructions=[{'text': 'cook'}],
            base_servings=1,
            base_nutrition={'calories': 500},
            source_url='https://example.test/draft',
            source_name='Example',
        )

        out_default = StringIO()
        call_command('coverage_matrix_report', '--csv', stdout=out_default)
        out_with_drafts = StringIO()
        call_command('coverage_matrix_report', '--csv', '--include-drafts',
                     stdout=out_with_drafts)

        def lunch_total(csv_text):
            for ln in csv_text.splitlines():
                if ln.startswith('lunch,'):
                    return int(ln.rsplit(',', 1)[-1])
            return None

        self.assertEqual(lunch_total(out_default.getvalue()), 0)
        self.assertEqual(lunch_total(out_with_drafts.getvalue()), 1)
