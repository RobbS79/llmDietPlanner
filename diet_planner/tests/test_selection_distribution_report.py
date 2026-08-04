"""Tests for the selection_distribution_report management command.

The command is the before/after measurement harness for serving-concentration
fixes: it simulates plan generation for a fixed persona set (no LLM calls) and
reports how serves distribute across the published corpus.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def make_recipe(slug, **kw):
    defaults = dict(
        slug=slug,
        name_cs=slug,
        status=CuratedRecipe.Status.PUBLISHED,
        meal_types=['breakfast', 'lunch', 'dinner'],
        dietary_tags=[],
        cuisine=kw.pop('cuisine', 'czech'),
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice'}],
        instructions=[{'text': 'Uvař.'}],
        base_servings=2,
        base_nutrition={'calories': 500},
        source_url='https://example.test/r',
        source_name='test',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class SelectionDistributionReportTests(TestCase):
    def setUp(self):
        for i in range(8):
            make_recipe(f'dish-{i}', cuisine=['czech', 'italian', 'asian', 'mexican'][i % 4])

    def run_command(self, *args):
        out = StringIO()
        call_command('selection_distribution_report', *args, stdout=out)
        return out.getvalue()

    def test_reports_distribution_metrics(self):
        output = self.run_command('--regens', '3', '--days', '3')
        self.assertIn('published pool:', output)
        self.assertIn('total serves:', output)
        self.assertIn('distinct recipes served:', output)
        self.assertIn('never-served:', output)
        self.assertIn('top-15 share:', output)
        self.assertIn('day1-lunch repeat rate:', output)

    def test_serves_at_least_one_recipe(self):
        output = self.run_command('--regens', '2', '--days', '2')
        distinct = int(output.split('distinct recipes served:')[1].split()[0])
        self.assertGreaterEqual(distinct, 1)

    def test_deterministic_for_same_inputs(self):
        self.assertEqual(
            self.run_command('--regens', '2', '--days', '2'),
            self.run_command('--regens', '2', '--days', '2'),
        )
