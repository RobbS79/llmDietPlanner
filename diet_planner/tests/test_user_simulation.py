"""Crossing demand x phrasing x persona into reproducible simulated queries."""
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability
from diet_planner.services.user_simulation import (
    PERSONAS, SimulatedQuery, demand_coverage, gate_funnel, generate_queries,
    pairing_kind,
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


class GateFunnelTests(TestCase):
    def test_counts_shrink_monotonically_through_the_gates(self):
        _recipe('a')
        _recipe('b', dietary_tags=['vegan'])
        funnel = gate_funnel(slot='dinner', required_tags=set(), facets=None)
        counts = [funnel[k] for k in ('pool', 'slot', 'dietary', 'mapped', 'facets')]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_a_survivable_dietary_squeeze_has_no_killer(self):
        """One recipe still serves the query, so nothing killed it — the gate
        merely squeezed. `killer` means fatal; pressure is `biggest_drop`."""
        _recipe('omnivore')
        _recipe('vegan-dish', dietary_tags=['vegan'])
        funnel = gate_funnel(slot='dinner', required_tags={'vegan'}, facets=None)
        self.assertEqual(funnel['slot'], 2)
        self.assertEqual(funnel['dietary'], 1)
        self.assertIsNone(funnel['killer'])
        self.assertEqual(funnel['biggest_drop'], 'dietary')

    def test_a_fatal_dietary_gate_is_the_killer(self):
        _recipe('omnivore')
        _recipe('another-omnivore')
        funnel = gate_funnel(slot='dinner', required_tags={'vegan'}, facets=None)
        self.assertEqual(funnel['dietary'], 0)
        self.assertEqual(funnel['killer'], 'dietary')

    def test_biggest_drop_ties_break_toward_the_earlier_stage(self):
        """Two stages remove the same number of recipes: 'slot' drops 2 (two
        breakfast-only recipes never reach the dinner pool) and 'mapped'
        drops 2 (two dinner recipes with no catalog_id/canonical). Tie
        breaks toward the earlier gate in retrieval order."""
        _recipe('breakfast-1', meal_types=['breakfast'])
        _recipe('breakfast-2', meal_types=['breakfast'])
        _recipe('unmapped-1', ingredients=[
            {'name': 'tajemná surovina', 'quantity': 1, 'unit': 'ks'}])
        _recipe('unmapped-2', ingredients=[
            {'name': 'tajemná surovina', 'quantity': 1, 'unit': 'ks'}])
        _recipe('mapped-1')
        _recipe('mapped-2')
        funnel = gate_funnel(slot='dinner', required_tags=set(), facets=None)
        self.assertEqual(funnel['biggest_drop'], 'slot')

    def test_specialty_cost_is_reported_separately(self):
        """The specialty gate is unconditional inside eligible_recipes_for_slot,
        so its cost is measured directly rather than by toggling it."""
        _recipe('easy')
        _recipe('hard', shopping_difficulty=Availability.SPECIALTY,
                shopping_blockers=['tahini'])
        funnel = gate_funnel(slot='dinner', required_tags=set(), facets=None)
        self.assertEqual(funnel['specialty_cost'], 1)

    def test_wide_open_query_has_no_killer(self):
        _recipe('a')
        self.assertIsNone(gate_funnel(slot='dinner', required_tags=set(),
                                      facets=None)['killer'])

    def test_empty_slot_names_the_slot_as_killer(self):
        _recipe('a', meal_types=['breakfast'])
        funnel = gate_funnel(slot='dinner', required_tags=set(), facets=None)
        self.assertEqual(funnel['slot'], 0)
        self.assertEqual(funnel['killer'], 'slot')

    def test_empty_published_pool_names_pool_as_killer(self):
        """No recipes at all is a distinct, more fundamental failure than any
        gate emptying a non-empty pool — `killer` must never read as None
        (servable) when there was nothing to serve from in the first place."""
        funnel = gate_funnel(slot='dinner', required_tags=set(), facets=None)
        self.assertEqual(funnel['pool'], 0)
        self.assertEqual(funnel['killer'], 'pool')

    def test_wide_open_query_still_has_no_killer_when_recipes_exist(self):
        """Regression guard for the pool-killer fix: a non-empty, fully
        eligible pool must still report killer=None."""
        _recipe('a')
        funnel = gate_funnel(slot='dinner', required_tags=set(), facets=None)
        self.assertGreater(funnel['pool'], 0)
        self.assertIsNone(funnel['killer'])


class DemandCoverageTests(TestCase):
    def test_strict_match_needs_the_dish_itself(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        result = demand_coverage([DEMAND[0]], top_n=1)
        self.assertEqual(result['strict_hits'], 1)

    def test_diacritics_do_not_defeat_the_strict_match(self):
        _recipe('gulas', name_cs='Hovezi gulas')
        self.assertEqual(demand_coverage([DEMAND[0]], top_n=1)['strict_hits'], 1)

    def test_a_different_dish_is_not_a_strict_hit(self):
        _recipe('rizek', name_cs='Kuřecí řízek')
        result = demand_coverage([DEMAND[0]], top_n=1)
        self.assertEqual(result['strict_hits'], 0)

    def test_loose_match_accepts_a_canonical_overlap(self):
        """'we have something beefy' is a weaker promise than 'we have guláš',
        so it is reported as its own number."""
        _recipe('hovezi-pecene', name_cs='Hovězí pečeně',
                ingredients=[{'name': 'hovězí maso', 'canonical': 'beef',
                              'quantity': 500, 'unit': 'g', 'catalog_id': 1}])
        result = demand_coverage([DEMAND[0]], top_n=1)
        self.assertEqual(result['strict_hits'], 0)
        self.assertEqual(result['loose_hits'], 1)

    def test_out_of_scope_terms_are_excluded_from_the_denominator(self):
        result = demand_coverage(DEMAND, top_n=3)
        self.assertEqual(result['scored'], 2)
        self.assertEqual(result['out_of_scope'], 1)

    def test_top_n_limits_the_denominator(self):
        self.assertEqual(demand_coverage(DEMAND, top_n=1)['scored'], 1)

    def test_a_strict_hit_also_counts_as_loose(self):
        """loose is a superset of strict — a report where strict > loose would
        be nonsense, so pin it."""
        _recipe('gulas', name_cs='Hovězí guláš')
        result = demand_coverage([DEMAND[0]], top_n=1)
        self.assertGreaterEqual(result['loose_hits'], result['strict_hits'])

    def test_unservable_demand_is_listed_by_name(self):
        """The miss list is the corpus-acquisition shopping list; it is the
        most actionable thing the farm produces."""
        result = demand_coverage([DEMAND[0]], top_n=1)
        self.assertIn('Hovězí guláš', result['misses'])

    def test_inflected_forms_still_count_as_a_strict_hit(self):
        """'Hovězí guláš' vs 'Guláš z hovězího masa' is the same dish;
        exact-token set intersection missed it because 'hovezi' != 'hoveziho',
        which would systematically under-report the headline coverage number
        and invent corpus gaps that don't exist."""
        _recipe('gulas-z-hoveziho-masa', name_cs='Guláš z hovězího masa')
        result = demand_coverage([DEMAND[0]], top_n=1)
        self.assertEqual(result['strict_hits'], 1)

    def test_different_meats_stay_distinct_despite_the_inflection_fix(self):
        """Regression guard: without the 5-char floor, loosening word
        matching further could silently turn every řízek into every other
        řízek. Kuřecí (chicken) and Vepřový (pork) řízek must stay apart."""
        row = {'term': 'Kuřecí řízek', 'in_scope': True, 'canonicals': []}
        _recipe('veprovy-rizek', name_cs='Vepřový řízek')
        result = demand_coverage([row], top_n=1)
        self.assertEqual(result['strict_hits'], 0)

    def test_a_short_significant_word_cannot_prefix_match_a_longer_word(self):
        """Guards the 5-character floor: 'maso' (4 chars) must not loosely
        match an unrelated longer word like 'maslova' just because they
        happen to share a short prefix."""
        row = {'term': 'Maso', 'in_scope': True, 'canonicals': []}
        _recipe('maslova-babovka', name_cs='Máslová bábovka')
        result = demand_coverage([row], top_n=1)
        self.assertEqual(result['strict_hits'], 0)

    def test_a_more_specific_demand_term_is_not_satisfied_by_a_plainer_name(self):
        """Deliberate under-claim: the demand term is more specific ('na
        smetaně') than the recipe name ('Svíčková' alone), and we would
        rather under-report coverage than tell a user we have a dish we
        don't actually have on file."""
        row = {'term': 'Svíčková na smetaně', 'in_scope': True, 'canonicals': []}
        _recipe('svickova', name_cs='Svíčková')
        result = demand_coverage([row], top_n=1)
        self.assertEqual(result['strict_hits'], 0)

    def test_a_short_word_cannot_claim_a_much_longer_word_by_prefix_alone(self):
        """The absolute floor (_MIN_STEM_LEN=5) is not sufficient on its own:
        a 5-character word is an exact prefix of the much longer word below,
        which would pass the length floor alone but must still be rejected
        by the coverage-ratio guard — the same guard demand_index.py already
        applies in `_fuzzy_canonical_slug`, now ported here so a strict-side
        over-match can't inflate the headline number the way a fuzzy-side one
        already couldn't."""
        row = {'term': 'Gulas', 'in_scope': True, 'canonicals': []}
        _recipe('long-word', name_cs='Gulasovnicovitostmi')
        result = demand_coverage([row], top_n=1)
        self.assertEqual(result['strict_hits'], 0)
