"""The farm command: no LLM in the default mode, no DB writes, ever."""
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
