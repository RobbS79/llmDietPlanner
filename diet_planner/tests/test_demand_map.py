"""Demand map: the committed Trends data and the loader that reads it."""
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.demand_map import (
    DemandTerm, load_demand_map, load_overrides, match_demand_term,
)


class DemandMapFileTests(SimpleTestCase):
    def test_committed_map_loads_and_is_anchored_on_gulas(self):
        terms = load_demand_map()
        self.assertIn('guláš', terms)
        self.assertEqual(terms['guláš'].demand, 100.0)
        self.assertEqual(terms['guláš'].kind, 'dish')

    def test_every_row_has_the_fields_ranking_needs(self):
        for term in load_demand_map().values():
            self.assertIsInstance(term, DemandTerm)
            self.assertGreaterEqual(term.demand, 0.0)
            self.assertIn(term.kind, {'dish', 'category', 'restaurant', 'intent'})
            self.assertTrue(term.peak_month is None or 1 <= term.peak_month <= 12)

    def test_slovak_alias_is_carried(self):
        self.assertIn('sviečková', load_demand_map()['svíčková'].aliases)

    def test_overrides_file_loads_as_slug_to_term(self):
        overrides = load_overrides()
        self.assertEqual(overrides.get('leco'), 'lečo')

    def test_loader_rejects_a_row_without_demand(self):
        bad = Path('/tmp/bad_demand_map.yaml')
        bad.write_text('anchor: guláš\nterms:\n  - term: x\n    kind: dish\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_demand_map(bad)


def _recipe(slug, name_cs):
    return CuratedRecipe.objects.create(
        slug=slug, name_cs=name_cs, meal_types=['lunch'], ingredients=[], instructions=[],
        source_url=f'https://example.com/{slug}', source_name='Example',
    )


class MatchDemandTermTests(TestCase):
    def setUp(self):
        self.terms = {
            'guláš': DemandTerm('guláš', 100.0, 'dish', 'main'),
            'segedínský guláš': DemandTerm('segedínský guláš', 18.4, 'dish', 'main', aliases=['segedínsky guláš']),
            'salát': DemandTerm('salát', 192.8, 'category', 'light'),
            'řízek': DemandTerm('řízek', 48.5, 'dish', 'main', aliases=['rezeň']),
        }

    def test_override_wins_over_name(self):
        r = _recipe('leco', 'Lečo')
        terms = {**self.terms, 'lečo': DemandTerm('lečo', 19.8, 'dish', 'main')}
        term, how = match_demand_term(r, terms, {'leco': 'lečo'})
        self.assertEqual((term.term, how), ('lečo', 'override'))

    def test_name_match_prefers_the_higher_demand_term(self):
        r = _recipe('hovezi-gulas', 'Hovězí guláš')
        term, how = match_demand_term(r, self.terms, {})
        self.assertEqual((term.term, how), ('guláš', 'name'))

    def test_slovak_alias_matches(self):
        r = _recipe('bravcovy-rezen', 'Bravčový rezeň')
        term, _ = match_demand_term(r, self.terms, {})
        self.assertEqual(term.term, 'řízek')

    def test_category_rows_never_attach(self):
        r = _recipe('caprese-salat', 'Caprese salát')
        term, how = match_demand_term(r, self.terms, {})
        self.assertEqual((term, how), (None, ''))

    def test_no_match_is_blank(self):
        r = _recipe('pad-thai', 'Pad Thai')
        self.assertEqual(match_demand_term(r, self.terms, {}), (None, ''))


class MatcherPrecisionTests(TestCase):
    """Found on the first prod dry-run (2026-09-09): 316 attaches, of which the
    generic single-word terms and the demand-wins tie rule produced clear
    mistakes. These pin the corrections."""

    def setUp(self):
        self.terms = {
            'bramboráky': DemandTerm('bramboráky', 19.0, 'dish', 'main', aliases=['bramborové placky']),
            'bramboračka': DemandTerm('bramboračka', 11.4, 'dish', 'soup'),
            'knedlíky': DemandTerm('knedlíky', 56.0, 'dish', 'side'),
            'vepřo knedlo zelo': DemandTerm('vepřo knedlo zelo', 2.8, 'dish', 'main'),
            'steak': DemandTerm('steak', 79.0, 'dish', 'main'),
            'guláš': DemandTerm('guláš', 100.0, 'dish', 'main'),
        }

    def test_single_word_term_needs_the_same_word_not_a_shared_stem(self):
        self.assertIsNone(match_demand_term(_recipe('brambory-hasselback', 'Brambory Hasselback'), self.terms, {})[0])
        self.assertIsNone(match_demand_term(_recipe('bramborova-kase', 'Dokonalá bramborová kaše'), self.terms, {})[0])
        self.assertEqual(match_demand_term(_recipe('klasicka-bramboracka', 'Klasická bramboračka'), self.terms, {})[0].term, 'bramboračka')
        self.assertEqual(match_demand_term(_recipe('krupave-bramboraky', 'Křupavé bramboráky'), self.terms, {})[0].term, 'bramboráky')

    def test_single_word_term_still_tolerates_inflection(self):
        self.assertEqual(match_demand_term(_recipe('hovezi-gulas', 'Hovězí guláš'), self.terms, {})[0].term, 'guláš')
        self.assertEqual(match_demand_term(_recipe('gulas-z-krkovice', 'Guláš z krkovice'), self.terms, {})[0].term, 'guláš')

    def test_alias_rescues_the_placky_spelling(self):
        self.assertEqual(match_demand_term(_recipe('pecene-bramborove-placky', 'Pečené bramborové placky'), self.terms, {})[0].term, 'bramboráky')

    def test_more_specific_term_beats_a_generic_one_with_higher_demand(self):
        term, _ = match_demand_term(_recipe('vepro-knedlo-zelo', 'Vepřo knedlo zelo'), self.terms, {})
        self.assertEqual(term.term, 'vepřo knedlo zelo')

    def test_override_can_pin_a_recipe_to_no_term(self):
        r = _recipe('kvetakovy-steak', 'Květákový steak')
        self.assertEqual(match_demand_term(r, self.terms, {})[0].term, 'steak')   # by name it would attach
        self.assertEqual(match_demand_term(r, self.terms, {'kvetakovy-steak': ''}), (None, 'override'))
