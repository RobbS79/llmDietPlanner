"""Crossing demand x phrasing x persona into reproducible simulated queries."""
from django.test import TestCase

from diet_planner.services.user_simulation import (
    PERSONAS, SimulatedQuery, generate_queries, pairing_kind,
)

DEMAND = [
    {'term': 'Hovězí guláš', 'rank': 1, 'source': 'toprecepty.cz', 'category': 'maso',
     'slot_hint': 'dinner', 'in_scope': True, 'canonicals': ['beef'],
     'folded': 'hovezi gulas'},
    {'term': 'Bublanina', 'rank': 2, 'source': 'toprecepty.cz', 'category': 'moucniky',
     'slot_hint': None, 'in_scope': False, 'canonicals': [], 'folded': 'bublanina'},
    {'term': 'Kuřecí řízek', 'rank': 3, 'source': 'toprecepty.cz', 'category': 'maso',
     'slot_hint': 'dinner', 'in_scope': True, 'canonicals': ['chicken'],
     'folded': 'kureci rizek'},
]
TEMPLATES = [
    {'template': 'Mám {ingredient}, co uvařit?', 'observed': 4},
    {'template': 'jídelníček na {n} dní', 'observed': 11},
]


class GenerateQueriesTests(TestCase):
    def test_same_seed_gives_identical_queries(self):
        a = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=7, n=12)
        b = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=7, n=12)
        self.assertEqual([q.prompt_cs for q in a], [q.prompt_cs for q in b])
        self.assertEqual([q.persona for q in a], [q.persona for q in b])

    def test_different_seeds_diverge(self):
        a = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=1, n=12)
        b = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=2, n=12)
        self.assertNotEqual([q.prompt_cs for q in a], [q.prompt_cs for q in b])

    def test_out_of_scope_demand_is_never_queried(self):
        """Bublanina is real demand with no meal slot; querying it would score
        a coverage failure for a dish the planner is not meant to serve."""
        queries = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=3, n=30)
        self.assertTrue(all('Bublanina' not in q.demand_term for q in queries))

    def test_queries_carry_facets_and_demand_rank(self):
        queries = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=5, n=6)
        self.assertTrue(queries)
        for q in queries:
            self.assertIsInstance(q, SimulatedQuery)
            self.assertIsNotNone(q.facets)
            self.assertGreaterEqual(q.demand_rank, 1)
            self.assertIn(q.slot, ('breakfast', 'lunch', 'dinner', 'snack'))

    def test_persona_restrictions_reach_the_query(self):
        queries = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=9, n=40)
        vegetarian = [q for q in queries if q.persona == 'vegetarian']
        self.assertTrue(vegetarian)
        self.assertTrue(all('vegetari' in q.dietary_restrictions for q in vegetarian))

    def test_n_is_respected(self):
        self.assertEqual(len(generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=1, n=5)), 5)

    def test_empty_demand_yields_no_queries(self):
        self.assertEqual(generate_queries([], TEMPLATES, PERSONAS, seed=1, n=5), [])


class PairingKindTests(TestCase):
    def test_beef_dish_with_vegan_persona_is_cross_diet(self):
        self.assertEqual(pairing_kind(DEMAND[0], 'veganská strava'), 'cross-diet')

    def test_beef_dish_with_no_restrictions_is_normal(self):
        self.assertEqual(pairing_kind(DEMAND[0], ''), 'normal')

    def test_plant_dish_with_vegan_persona_is_normal(self):
        plant_dish = {'term': 'Čočková polévka', 'canonicals': [], 'folded': 'coctocva polevka'}
        self.assertEqual(pairing_kind(plant_dish, 'veganská strava'), 'normal')

    def test_diacritics_do_not_defeat_the_check(self):
        unaccented_dish = {'term': 'hovezi gulas', 'canonicals': [], 'folded': 'hovezi gulas'}
        self.assertEqual(pairing_kind(unaccented_dish, 'veganska strava'), 'cross-diet')

    def test_vegetarian_persona_with_meat_dish_is_cross_diet(self):
        self.assertEqual(pairing_kind(DEMAND[0], 'vegetariánská strava'), 'cross-diet')


class GenerateQueriesPairingTests(TestCase):
    def test_generate_queries_populates_pairing(self):
        queries = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=9, n=200)
        self.assertTrue(all(q.pairing in ('normal', 'cross-diet') for q in queries))
        self.assertTrue(any(q.pairing == 'cross-diet' for q in queries))
