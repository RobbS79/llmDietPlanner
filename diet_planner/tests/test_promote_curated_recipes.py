"""Tests for the promote_curated_recipes management command."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(**kw):
    """CuratedRecipe factory for promotion tests."""
    defaults = dict(
        name_cs=kw.pop('name_cs', 'Test dish'),
        slug=kw.pop('slug', None),  # will autogenerate
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
        source_url=kw.pop('source_url', 'https://example.test/r1'),
        source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class PromoteCatalogMappedTest(TestCase):
    def test_catalog_mapped_draft_is_promoted(self):
        r = _recipe(source_url='https://example.test/r-mapped')
        # All ingredients have canonical set → is_catalog_mapped() is True.
        self.assertTrue(r.is_catalog_mapped())

        out = StringIO()
        call_command('promote_curated_recipes', stdout=out)

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.PUBLISHED)
        self.assertIn('promoted=1', out.getvalue())


class PromoteSkipsUnmappedTest(TestCase):
    def test_unmapped_draft_stays_draft(self):
        # Ingredient has no canonical and no catalog_id → not catalog-mapped.
        r = _recipe(
            source_url='https://example.test/r-unmapped',
            ingredients=[{'name': 'mystery-spice', 'quantity': 1, 'unit': 'tsp'}],
        )
        self.assertFalse(r.is_catalog_mapped())

        out = StringIO()
        call_command('promote_curated_recipes', stdout=out)

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.DRAFT)
        self.assertIn('skipped_unmapped=1', out.getvalue())


class PromoteDryRunTest(TestCase):
    def test_dry_run_does_not_save(self):
        r = _recipe(source_url='https://example.test/r-dry')
        self.assertTrue(r.is_catalog_mapped())

        out = StringIO()
        call_command('promote_curated_recipes', '--dry-run', stdout=out)

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.DRAFT)  # unchanged
        self.assertIn('promoted=1', out.getvalue())
        self.assertIn('[dry-run]', out.getvalue())


class PromoteJudgeGateTest(TestCase):
    def test_below_min_verdict_is_skipped(self):
        r = _recipe(
            source_url='https://example.test/r-judge-low',
            quality_score={'ran': True, 'verdict': 'unknown'},
        )
        self.assertTrue(r.is_catalog_mapped())

        out = StringIO()
        call_command(
            'promote_curated_recipes',
            '--min-judge-verdict', 'minor_issues',
            stdout=out,
        )

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.DRAFT)
        self.assertIn('skipped_judge=1', out.getvalue())

    def test_at_or_above_min_verdict_is_promoted(self):
        r = _recipe(
            source_url='https://example.test/r-judge-ok',
            quality_score={'ran': True, 'verdict': 'coherent'},
        )

        out = StringIO()
        call_command(
            'promote_curated_recipes',
            '--min-judge-verdict', 'minor_issues',
            stdout=out,
        )

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.PUBLISHED)
        self.assertIn('promoted=1', out.getvalue())
