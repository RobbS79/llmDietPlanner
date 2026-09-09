"""attach_demand_terms: copies the demand map onto CuratedRecipe rows."""
import json
import tempfile
from io import StringIO
from pathlib import Path

import yaml
from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(slug, name_cs, **kw):
    defaults = dict(
        slug=slug, name_cs=name_cs, meal_types=['lunch', 'dinner'], ingredients=[], instructions=[],
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class DemandFieldsTests(TestCase):
    def test_new_rows_carry_null_demand_fields(self):
        r = _recipe('x', 'X')
        self.assertEqual(r.demand_term, '')
        self.assertIsNone(r.demand_score)
        self.assertIsNone(r.demand_peak_month)
        self.assertIsNone(r.owner_rating)


def _write_map(path, terms):
    path.write_text(yaml.safe_dump({'anchor': 'guláš', 'terms': terms}, allow_unicode=True), encoding='utf-8')


class AttachDemandTermsTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.map_path = self.tmp / 'map.yaml'
        self.ovr_path = self.tmp / 'overrides.yaml'
        _write_map(self.map_path, [
            {'term': 'guláš', 'demand': 100.0, 'kind': 'dish', 'slot': 'main', 'peak_month': None},
            {'term': 'lečo', 'demand': 19.8, 'kind': 'dish', 'slot': 'main', 'peak_month': 8},
            {'term': 'salát', 'demand': 192.8, 'kind': 'category', 'slot': 'light'},
        ])
        self.ovr_path.write_text('domaci-leco: lečo\n', encoding='utf-8')
        self.gulas = _recipe('hovezi-gulas', 'Hovězí guláš')
        self.leco = _recipe('domaci-leco', 'Základ na lečo')   # only the override can attach this
        self.salad = _recipe('caprese-salat', 'Caprese salát')
        self.other = _recipe('pad-thai', 'Pad Thai')

    def _run(self, *args):
        out = StringIO()
        call_command('attach_demand_terms', '--map', str(self.map_path),
                     '--overrides', str(self.ovr_path), *args, stdout=out)
        for r in (self.gulas, self.leco, self.salad, self.other):
            r.refresh_from_db()
        return out.getvalue()

    def test_attaches_by_name_and_override_and_leaves_others_blank(self):
        out = self._run()
        self.assertEqual((self.gulas.demand_term, self.gulas.demand_score, self.gulas.demand_peak_month),
                         ('guláš', 100.0, None))
        self.assertEqual((self.leco.demand_term, self.leco.demand_score, self.leco.demand_peak_month),
                         ('lečo', 19.8, 8))
        self.assertEqual(self.salad.demand_term, '')     # category rows never attach
        self.assertEqual(self.other.demand_term, '')
        self.assertIn('hovezi-gulas', out)                # tier-2 attaches are listed for review
        self.assertIn('attached=2', out)

    def test_dry_run_writes_nothing(self):
        out = self._run('--dry-run')
        self.assertEqual(self.gulas.demand_term, '')
        self.assertIn('attached=2', out)

    def test_rerun_is_idempotent_and_clears_a_term_that_no_longer_matches(self):
        self._run()
        _write_map(self.map_path, [{'term': 'lečo', 'demand': 19.8, 'kind': 'dish', 'slot': 'main', 'peak_month': 8}])
        self._run()
        self.assertEqual(self.gulas.demand_term, '')
        self.assertIsNone(self.gulas.demand_score)
        self.assertEqual(self.leco.demand_term, 'lečo')

    def test_ratings_json_sets_owner_rating(self):
        ratings = self.tmp / 'ratings.json'
        ratings.write_text(json.dumps([{'slug': 'hovezi-gulas', 'score': 5}, {'slug': 'unknown', 'score': 1}]),
                           encoding='utf-8')
        out = self._run('--ratings', str(ratings))
        self.assertEqual(self.gulas.owner_rating, 5)
        self.assertIsNone(self.other.owner_rating)
        self.assertIn('ratings=1', out)
