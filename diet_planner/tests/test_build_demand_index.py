"""The snapshot builder: fetch behind a flag, never write an empty index."""
import os
import tempfile
from io import StringIO
from unittest import mock

import yaml
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

_PAGE = '''
  <div><a href="/recept/1-gulas/">Hovězí guláš</a></div>
  <div><a href="/recept/2-rizek/">Kuřecí řízek</a></div>
'''


class BuildDemandIndexTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        self.path = os.path.join(tempfile.mkdtemp(), 'demand.yaml')

    def _patched_fetch(self, page=_PAGE):
        return mock.patch(
            'diet_planner.management.commands.build_demand_index.Command._fetch',
            return_value=page)

    def test_refresh_writes_a_snapshot(self):
        with self._patched_fetch():
            call_command('build_demand_index', '--refresh', '--output', self.path,
                         stdout=StringIO())
        payload = yaml.safe_load(open(self.path, encoding='utf-8'))
        self.assertGreaterEqual(len(payload['terms']), 2)
        self.assertIn('generated_from', payload)
        first = payload['terms'][0]
        self.assertIn('term', first)
        self.assertIn('rank', first)
        self.assertIn('in_scope', first)

    def test_without_refresh_nothing_is_fetched(self):
        """The committed snapshot is the farm's input; a plain run is a no-op
        report so CI never touches the network."""
        with self._patched_fetch() as fetch:
            call_command('build_demand_index', '--output', self.path, stdout=StringIO())
        fetch.assert_not_called()

    def test_a_dead_source_never_produces_an_empty_index(self):
        """An empty demand list would make corpus coverage look perfect."""
        with self._patched_fetch(page='<html><body>no recipes here</body></html>'):
            with self.assertRaises(CommandError):
                call_command('build_demand_index', '--refresh', '--output', self.path,
                             stdout=StringIO())
        self.assertFalse(os.path.exists(self.path))

    def test_fetch_failure_keeps_the_previous_snapshot(self):
        with open(self.path, 'w', encoding='utf-8') as fh:
            yaml.safe_dump({'terms': [{'term': 'old', 'rank': 1}]}, fh)
        with mock.patch(
                'diet_planner.management.commands.build_demand_index.Command._fetch',
                side_effect=OSError('network down')):
            with self.assertRaises(CommandError):
                call_command('build_demand_index', '--refresh', '--output', self.path,
                             stdout=StringIO())
        kept = yaml.safe_load(open(self.path, encoding='utf-8'))
        self.assertEqual(kept['terms'][0]['term'], 'old')

    def test_terms_are_enriched_not_raw(self):
        """The farm reads this file directly; unenriched rows would silently
        drop every term out of the scored denominator."""
        with self._patched_fetch():
            call_command('build_demand_index', '--refresh', '--output', self.path,
                         stdout=StringIO())
        payload = yaml.safe_load(open(self.path, encoding='utf-8'))
        row = payload['terms'][0]
        for key in ('slot_hint', 'in_scope', 'canonicals', 'folded'):
            self.assertIn(key, row)

    def test_refresh_stamps_generated_at(self):
        """No timestamp means a six-month-stale snapshot reads identically
        to one built this morning — simulate_coverage needs this to report
        staleness."""
        with self._patched_fetch():
            call_command('build_demand_index', '--refresh', '--output', self.path,
                         stdout=StringIO())
        payload = yaml.safe_load(open(self.path, encoding='utf-8'))
        self.assertIn('generated_at', payload)
        from datetime import datetime
        parsed = datetime.fromisoformat(payload['generated_at'])
        self.assertIsNotNone(parsed.tzinfo)  # UTC-aware, not a naive local time

    def test_per_source_caps_terms(self):
        with self._patched_fetch():
            call_command('build_demand_index', '--refresh', '--output', self.path,
                         '--per-source', '1', stdout=StringIO())
        payload = yaml.safe_load(open(self.path, encoding='utf-8'))
        sources = [(r['source'], r['category']) for r in payload['terms']]
        self.assertEqual(len(sources), len(set(sources)))
