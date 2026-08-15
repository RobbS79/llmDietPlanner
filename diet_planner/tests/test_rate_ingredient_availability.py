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
