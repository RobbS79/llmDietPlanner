"""Tests for the audit_portion_plausibility management command."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(slug, ingredients, *, base_servings=1, status=None):
    return CuratedRecipe.objects.create(
        name_cs=f"Recipe {slug}",
        slug=slug,
        status=status or CuratedRecipe.Status.PUBLISHED,
        meal_types=['lunch'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=ingredients,
        instructions=[{'text': 'cook'}],
        base_servings=base_servings,
        base_nutrition={'calories': 500},
        source_url=f'https://example.test/{slug}',
        source_name='Example',
    )


class AuditPortionPlausibilityTest(TestCase):
    def test_flags_implausible_and_lists_offender(self):
        _recipe('good', [{'name': 'rýže', 'quantity': 320, 'unit': 'g'}], base_servings=4)
        _recipe('bad', [{'name': 'kuřecí prsa', 'quantity': 680, 'unit': 'g'}], base_servings=1)

        out = StringIO()
        call_command('audit_portion_plausibility', '--status', 'published', stdout=out)
        text = out.getvalue()

        self.assertIn('Scanned 2', text)
        self.assertIn('Flagged 1', text)
        self.assertIn('bad', text)
        self.assertNotIn('good:', text)  # 'good' is not listed as an offender row

    def test_status_filter_limits_scope(self):
        _recipe('draft-bad', [{'name': 'kuře', 'quantity': 680, 'unit': 'g'}],
                base_servings=1, status=CuratedRecipe.Status.DRAFT)

        out = StringIO()
        call_command('audit_portion_plausibility', '--status', 'published', stdout=out)
        self.assertIn('Scanned 0', out.getvalue())
