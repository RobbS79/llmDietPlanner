"""Tests for the unmapped_ingredients_report management command."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(slug, ingredients, *, status=None):
    return CuratedRecipe.objects.create(
        name_cs=f"Recipe {slug}",
        slug=slug,
        status=status or CuratedRecipe.Status.DRAFT,
        meal_types=['lunch'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=ingredients,
        instructions=[{'text': 'cook'}],
        base_servings=1,
        base_nutrition={'calories': 500},
        source_url=f'https://example.test/{slug}',
        source_name='Example',
    )


class UnmappedReportRankingTest(TestCase):
    def test_ranks_unmapped_by_frequency(self):
        _recipe('a', [
            {'name': 'rare-spice', 'quantity': 1, 'unit': 'tsp'},
            {'name': 'rice', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
        ])
        _recipe('b', [
            {'name': 'rare-spice', 'quantity': 1, 'unit': 'tsp'},
            {'name': 'odd-herb', 'quantity': 1, 'unit': 'tsp'},
        ])
        _recipe('c', [
            {'name': 'rare-spice', 'quantity': 2, 'unit': 'tsp'},
        ])

        out = StringIO()
        call_command('unmapped_ingredients_report', stdout=out)

        output = out.getvalue()
        # rare-spice appears 3 times, odd-herb 1, rice is mapped (excluded).
        self.assertIn('rare-spice', output)
        self.assertRegex(output, r'\s+3\s+rare-spice')
        self.assertIn('odd-herb', output)
        self.assertNotIn('rice', output)
        # rare-spice should appear before odd-herb (higher frequency first).
        self.assertLess(output.index('rare-spice'), output.index('odd-herb'))


class UnmappedReportCatalogIdExclusionTest(TestCase):
    def test_catalog_id_mapped_ingredient_is_excluded(self):
        _recipe('a', [
            {'name': 'salt', 'quantity': 1, 'unit': 'g', 'catalog_id': 'cat-salt-1'},
            {'name': 'mystery-x', 'quantity': 1, 'unit': 'g'},
        ])
        out = StringIO()
        call_command('unmapped_ingredients_report', stdout=out)
        output = out.getvalue()
        self.assertNotIn('salt', output)
        self.assertIn('mystery-x', output)


class UnmappedReportTopFlagTest(TestCase):
    def test_top_flag_truncates_output(self):
        for i in range(10):
            _recipe(f'r{i}', [{'name': f'ing-{i}', 'quantity': 1, 'unit': 'g'}])

        out = StringIO()
        call_command('unmapped_ingredients_report', '--top', '3', stdout=out)
        output = out.getvalue()

        # Exactly 3 ingredient lines should be present.
        ing_lines = [ln for ln in output.splitlines() if ln.strip().startswith('1  ing-')]
        self.assertEqual(len(ing_lines), 3)


class UnmappedReportCsvTest(TestCase):
    def test_csv_format(self):
        _recipe('a', [
            {'name': 'rare-spice', 'quantity': 1, 'unit': 'tsp'},
            {'name': 'rare-spice', 'quantity': 1, 'unit': 'tsp'},
        ])
        _recipe('b', [{'name': 'odd-herb', 'quantity': 1, 'unit': 'tsp'}])

        out = StringIO()
        call_command('unmapped_ingredients_report', '--csv', stdout=out)
        lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]

        self.assertEqual(lines[0], 'name,count')
        self.assertIn('rare-spice,2', lines)
        self.assertIn('odd-herb,1', lines)


class UnmappedReportStatusFilterTest(TestCase):
    def test_status_filter_excludes_other_statuses(self):
        _recipe('draft', [{'name': 'draft-only-ing', 'quantity': 1, 'unit': 'g'}])
        _recipe('pub',   [{'name': 'pub-only-ing',   'quantity': 1, 'unit': 'g'}],
                status=CuratedRecipe.Status.PUBLISHED)

        out = StringIO()
        call_command('unmapped_ingredients_report', '--status', 'published',
                     stdout=out)
        output = out.getvalue()

        self.assertIn('pub-only-ing', output)
        self.assertNotIn('draft-only-ing', output)
