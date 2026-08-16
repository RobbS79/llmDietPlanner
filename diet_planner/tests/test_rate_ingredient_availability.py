"""CSV -> YAML import and YAML -> DB rating."""
import csv
import tempfile
from pathlib import Path

import yaml
from django.core.management import CommandError, call_command
from django.test import TestCase

from diet_planner.models import Availability, CanonicalIngredient
from diet_planner.tests.factories import make_canonical

_COLUMNS = ['REVIEW', 'recipes', 'slug', 'name_cs', 'category',
            'claude_tier', 'confidence', 'claude_note', 'YOUR_TIER', 'YOUR_NOTE']


def write_csv(path, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in _COLUMNS})


class ImportAvailabilityReviewTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.csv_path = self.tmp / 'review.csv'
        self.yaml_path = self.tmp / 'availability.yaml'

    def _run(self):
        call_command('import_availability_review',
                     csv_file=str(self.csv_path), out=str(self.yaml_path))
        return yaml.safe_load(self.yaml_path.read_text(encoding='utf-8'))

    def test_claude_tier_is_used_when_owner_left_it_blank(self):
        write_csv(self.csv_path, [
            {'slug': 'tahini', 'claude_tier': 'specialty',
             'confidence': 'high', 'claude_note': 'asian shops'},
        ])
        data = self._run()
        self.assertEqual(data[0]['slug'], 'tahini')
        self.assertEqual(data[0]['availability'], 'specialty')
        self.assertEqual(data[0]['confidence'], 'high')
        self.assertEqual(data[0]['note'], 'asian shops')

    def test_owner_tier_overrides_and_marks_confidence_owner(self):
        write_csv(self.csv_path, [
            {'slug': 'smoked-paprika', 'claude_tier': 'findable',
             'confidence': 'low', 'claude_note': 'Lidl?',
             'YOUR_TIER': 'common', 'YOUR_NOTE': 'everywhere'},
        ])
        data = self._run()
        self.assertEqual(data[0]['availability'], 'common')
        self.assertEqual(data[0]['confidence'], 'owner')
        self.assertEqual(data[0]['note'], 'everywhere')

    def test_owner_tier_is_normalised_and_validated(self):
        write_csv(self.csv_path, [
            {'slug': 'x', 'claude_tier': 'common', 'confidence': 'high',
             'YOUR_TIER': '  COMMON '},
        ])
        self.assertEqual(self._run()[0]['availability'], 'common')

    def test_unknown_tier_is_a_hard_error(self):
        write_csv(self.csv_path, [
            {'slug': 'x', 'claude_tier': 'common', 'confidence': 'high',
             'YOUR_TIER': 'maybe'},
        ])
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn('maybe', str(ctx.exception))


class RateIngredientAvailabilityTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.yaml_path = self.tmp / 'availability.yaml'
        # Migration 0022 seeds ~62 staples into every DB, this one included.
        # The command demands a rating for *every* canonical, so clear the
        # table to assert on exactly the two rows under test.
        CanonicalIngredient.objects.all().delete()
        make_canonical('tahini')
        make_canonical('sůl')

    def _write(self, rows):
        self.yaml_path.write_text(
            yaml.safe_dump(rows, allow_unicode=True), encoding='utf-8')

    def _run(self, **kw):
        call_command('rate_ingredient_availability', file=str(self.yaml_path), **kw)

    def _full(self):
        return [
            {'slug': 'tahini', 'availability': 'specialty',
             'confidence': 'high', 'note': 'asian shops'},
            {'slug': 'sul', 'availability': 'common',
             'confidence': 'high', 'note': ''},
        ]

    def test_applies_ratings_and_notes(self):
        self._write(self._full())
        self._run()
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='tahini').availability, 'specialty')
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='tahini').availability_note,
            'asian shops')
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='sul').availability, 'common')

    def test_is_idempotent(self):
        self._write(self._full())
        self._run()
        self._run()
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='tahini').availability, 'specialty')

    def test_dry_run_writes_nothing(self):
        self._write(self._full())
        self._run(dry_run=True)
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='tahini').availability,
            Availability.UNRATED)

    def test_missing_canonical_is_a_hard_error(self):
        # 'sul' deliberately absent from the YAML: growing the dictionary must
        # not silently leave rows unrated.
        self._write([{'slug': 'tahini', 'availability': 'specialty',
                      'confidence': 'high', 'note': ''}])
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn('sul', str(ctx.exception))

    def test_yaml_row_for_unknown_slug_is_a_hard_error(self):
        rows = self._full() + [{'slug': 'ghost', 'availability': 'common',
                                'confidence': 'high', 'note': ''}]
        self._write(rows)
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn('ghost', str(ctx.exception))
