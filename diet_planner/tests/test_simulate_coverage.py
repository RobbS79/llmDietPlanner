"""The farm command: no LLM in the default mode, no DB writes, ever."""
import copy
import re
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import mock

import yaml
from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability

DEMAND_YAML = {
    'terms': [
        {'term': 'Hovězí guláš', 'rank': 1, 'source': 'toprecepty.cz',
         'category': 'maso', 'slot_hint': 'dinner', 'in_scope': True,
         'canonicals': ['beef'], 'folded': 'hovezi gulas'},
        {'term': 'Bublanina', 'rank': 2, 'source': 'toprecepty.cz',
         'category': 'moucniky', 'slot_hint': None, 'in_scope': False,
         'canonicals': [], 'folded': 'bublanina'},
    ],
}
TEMPLATES_YAML = {'templates': [{'template': 'Mám {ingredient}, co uvařit?',
                                 'observed': 3}]}


def _recipe(slug, **kw):
    defaults = dict(
        slug=slug, name_cs=slug, meal_types=['dinner'], base_servings=2,
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
        shopping_difficulty=Availability.COMMON, shopping_blockers=[],
        ingredients=[{'name': 'sůl', 'canonical': 'salt', 'quantity': 5,
                      'unit': 'g', 'catalog_id': 1}],
        instructions=[{'text': 'Uvařte.'}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class SimulateCoverageTests(TestCase):
    def setUp(self):
        self.demand = '/tmp/farm_demand.yaml'
        self.templates = '/tmp/farm_templates.yaml'
        with open(self.demand, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(DEMAND_YAML, fh, allow_unicode=True)
        with open(self.templates, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(TEMPLATES_YAML, fh, allow_unicode=True)

    def _run(self, *extra):
        out = StringIO()
        call_command('simulate_coverage', '--demand', self.demand,
                     '--templates', self.templates, '--queries', '6',
                     '--seed', '42', *extra, stdout=out)
        return out.getvalue()

    def _write_demand(self, **overrides):
        payload = copy.deepcopy(DEMAND_YAML)
        payload.update(overrides)
        with open(self.demand, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(payload, fh, allow_unicode=True)

    def test_report_states_the_seed_so_runs_are_comparable(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        self.assertIn('seed=42', self._run())

    def test_report_carries_demand_coverage_and_slot_fill(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        report = self._run()
        self.assertIn('demand coverage', report)
        self.assertIn('strict', report)
        self.assertIn('loose', report)
        self.assertIn('slots filled', report)

    def test_default_mode_makes_no_llm_call(self):
        """`direct` facets exist so the corpus can be measured for free."""
        _recipe('gulas', name_cs='Hovězí guláš')
        with mock.patch(
                'diet_planner.management.commands.simulate_coverage'
                '.extract_prompt_facets') as extract:
            self._run()
        extract.assert_not_called()

    def test_extract_facets_mode_reports_extraction_reliability(self):
        from diet_planner.services.prompt_facets import PromptFacets
        _recipe('gulas', name_cs='Hovězí guláš')
        with mock.patch(
                'diet_planner.management.commands.simulate_coverage'
                '.extract_prompt_facets',
                side_effect=[PromptFacets(), PromptFacets(wanted_ingredients={'guláš'})]
                            * 3) as extract:
            report = self._run('--extract-facets')
        self.assertTrue(extract.called)
        self.assertIn('empty-facet rate', report)

    def test_the_farm_writes_nothing_to_the_database(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        before = CuratedRecipe.objects.count()
        self._run()
        self.assertEqual(CuratedRecipe.objects.count(), before)

    def test_a_missing_demand_snapshot_is_loud(self):
        """An empty demand list would print perfect coverage over nothing."""
        report = StringIO()
        call_command('simulate_coverage', '--demand', '/tmp/does_not_exist.yaml',
                     '--templates', self.templates, stdout=report)
        self.assertIn('no demand snapshot', report.getvalue())

    def test_cross_diet_pairings_are_reported_separately(self):
        """A vegan persona asking for beef can only fail the dietary gate;
        counting those as plain corpus failures would overstate the gap."""
        _recipe('gulas', name_cs='Hovězí guláš')
        self.assertIn('cross-diet', self._run('--queries', '40'))

    def test_biggest_drop_is_reported(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        self.assertIn('biggest drop', self._run())

    def test_empty_corpus_warns_loudly(self):
        """0 published recipes must not be read as a clean coverage number —
        it means nothing was measured at all."""
        report = self._run()
        self.assertIn('EMPTY', report)
        self.assertIn('load_curated_corpus', report)

    def test_empty_corpus_does_not_claim_every_query_was_servable(self):
        report = self._run()
        self.assertNotIn(
            'every simulated query found at least one servable recipe', report)

    def test_recipes_present_and_all_queries_servable_claims_success(self):
        """A recipe that fully covers every slot/dietary/facet combination in
        the fixture personas must produce the success claim — proving the
        claim is reachable, not just suppressed."""
        _recipe('gulas', name_cs='Hovězí guláš',
                meal_types=['breakfast', 'lunch', 'dinner'],
                dietary_tags=['vegan', 'vegetarian', 'gluten_free'],
                ingredients=[{'name': 'guláš', 'canonical': 'gulas',
                              'quantity': 300, 'unit': 'g', 'catalog_id': 2}])
        report = self._run()
        self.assertIn(
            'every simulated query found at least one servable recipe', report)

    def test_header_states_corpus_size(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        self.assertIn('corpus=1 published recipes', self._run())

    def test_report_prints_the_snapshots_proxy_caveat(self):
        """The spec places the 'not demand truth' caveat in the report
        itself — nobody reading stdout should have to go dig up the YAML
        to find out these ranks are a dish-first proxy."""
        _recipe('gulas', name_cs='Hovězí guláš')
        self._write_demand(note='This is a proxy, not demand truth — read '
                                 'me before trusting the headline number.')
        report = self._run()
        self.assertIn(
            'This is a proxy, not demand truth — read me before trusting '
            'the headline number.', report)

    def test_missing_generated_at_says_age_unknown_rather_than_crashing(self):
        """The committed snapshot predates this field — must degrade
        gracefully, not raise."""
        _recipe('gulas', name_cs='Hovězí guláš')
        report = self._run()  # DEMAND_YAML carries no generated_at
        self.assertIn('age unknown, rebuild with --refresh', report)

    def test_report_prints_snapshot_age_when_generated_at_present(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        self._write_demand(generated_at=datetime.now(timezone.utc).isoformat())
        report = self._run()
        self.assertIn('snapshot age', report)
        self.assertNotIn('age unknown, rebuild with --refresh', report)

    def test_a_stale_snapshot_warns_the_market_may_have_moved(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        stale = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        self._write_demand(generated_at=stale)
        report = self._run()
        self.assertIn('may no longer reflect the market', report)

    def test_a_fresh_snapshot_does_not_warn(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        fresh = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self._write_demand(generated_at=fresh)
        report = self._run()
        self.assertNotIn('may no longer reflect the market', report)

    def test_demand_coverage_reports_headline_and_full_cutoffs_separately(self):
        """DWC@20 (headline demand) and DWC@top-n (long tail) must be
        reported separately — without the split the report cannot say
        whether gaps are in the dishes people most want or only the tail."""
        terms = [
            {'term': f'Dish {i}', 'rank': i, 'source': 'x', 'category': 'maso',
             'slot_hint': 'dinner', 'in_scope': True, 'canonicals': [],
             'folded': f'dish {i}'}
            for i in range(1, 26)
        ]
        with open(self.demand, 'w', encoding='utf-8') as fh:
            yaml.safe_dump({'terms': terms}, fh, allow_unicode=True)
        report = self._run()
        self.assertIn('@20', report)
        self.assertIn('@200', report)  # default --top-n
        match = re.search(r'@20[^\n]*\n\s*scored terms[^:]*:\s*(\d+)', report)
        self.assertIsNotNone(match)
        self.assertLessEqual(int(match.group(1)), 20)

    def test_queries_zero_blames_the_flag_not_the_data(self):
        """--queries 0 is an empty run by request, not a corpus/data gap —
        the two causes must read differently, and demand coverage (which
        does not depend on generated queries) must still be reported."""
        _recipe('gulas', name_cs='Hovězí guláš')
        report = self._run('--queries', '0')
        self.assertIn('--queries=0', report)
        self.assertNotIn('no in-scope demand terms', report)
        self.assertIn('demand coverage', report)

    def test_no_in_scope_demand_still_blames_the_data_not_the_flag(self):
        """Regression guard for the queries=0 fix: the genuine data-cause
        message must still fire when demand truly has nothing in scope."""
        self._write_demand(terms=[{
            'term': 'Bublanina', 'rank': 1, 'source': 'x', 'category': 'moucniky',
            'slot_hint': None, 'in_scope': False, 'canonicals': [], 'folded': 'bublanina',
        }])
        report = self._run()
        self.assertIn('no in-scope demand terms', report)
