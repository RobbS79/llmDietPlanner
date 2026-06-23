"""recipe_deals active-only matching.

A deal is ACTIVE only inside its real validity window (valid_from <= now <
valid_until, non-null end), from a real LEAFLET_DISCOUNT record tied to a
canonical. Future-dated (planned), expired, open-ended, non-leaflet, and
canonical-less records are never ACTIVE.
"""
from django.test import TestCase

from diet_planner.models import PriceSourceType
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.services.recipe_deals import recipe_deals
from diet_planner.tests.factories import make_canonical, make_price, make_store


class RecipeDealsTest(TestCase):
    def setUp(self):
        make_store('LIDL_CZ', name='Lidl')
        make_store('ALBERT_CZ', name='Albert')
        # name_cs='cibule' so resolve_canonical('cibule') maps here (resolver is
        # DB-based over name/name_cs/name_sk + aliases). clear_cache() drops the
        # process-cached normalized index after seeding new rows.
        self.onion = make_canonical('onion', default_unit='ks', name_cs='cibule')
        clear_cache()

    def _leaflet(self, canonical, *, store='LIDL_CZ', name='cibule',
                 offset=0, days=7, url='http://lidl.cz/cibule'):
        return make_price(
            store_code=store, normalized_name=name, price='9.90',
            source_type=PriceSourceType.LEAFLET_DISCOUNT, canonical=canonical,
            valid_from_offset_days=offset, valid_for_days=days, source_url=url,
        )

    def test_active_deal_is_matched(self):
        self._leaflet(self.onion)
        out = recipe_deals([{'name': 'cibule', 'canonical': 'onion',
                             'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 1)
        self.assertEqual(out['total'], 1)
        deal = out['deals'][0]
        self.assertEqual(deal['canonical'], 'onion')
        self.assertEqual(deal['shop'], 'Lidl')
        self.assertEqual(deal['source_url'], 'http://lidl.cz/cibule')
        self.assertEqual(deal['ingredient'], 'cibule')
        self.assertIsInstance(deal['valid_until'], str)   # ISO-8601, JSON-safe

    def test_future_dated_planned_deal_excluded(self):
        self._leaflet(self.onion, offset=3)   # starts in 3 days
        out = recipe_deals([{'canonical': 'onion', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 0)

    def test_expired_deal_excluded(self):
        self._leaflet(self.onion, offset=-10, days=7)  # ended 3 days ago
        out = recipe_deals([{'canonical': 'onion', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 0)

    def test_open_ended_deal_excluded(self):
        pr = self._leaflet(self.onion)
        pr.valid_until = None
        pr.save(update_fields=['valid_until'])
        out = recipe_deals([{'canonical': 'onion', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 0)

    def test_regular_price_is_not_a_deal(self):
        make_price(store_code='LIDL_CZ', normalized_name='cibule', price='9.90',
                   source_type=PriceSourceType.STORE_REGULAR, canonical=self.onion)
        out = recipe_deals([{'canonical': 'onion', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 0)

    def test_canonical_resolved_from_name_when_slug_absent(self):
        self._leaflet(self.onion)
        out = recipe_deals([{'name': 'cibule', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 1)

    def test_unmatched_ingredient_counts_toward_total_only(self):
        self._leaflet(self.onion)
        out = recipe_deals([
            {'canonical': 'onion', 'quantity': 1, 'unit': 'ks'},
            {'name': 'mystery', 'canonical': 'mystery-xyz', 'quantity': 1, 'unit': 'g'},
        ])
        self.assertEqual(out['matched'], 1)
        self.assertEqual(out['total'], 2)

    def test_optional_ingredient_ignored(self):
        self._leaflet(self.onion)
        out = recipe_deals([
            {'canonical': 'onion', 'quantity': 1, 'unit': 'ks'},
            {'canonical': 'onion', 'quantity': 1, 'unit': 'ks', 'optional': True},
        ])
        self.assertEqual(out['total'], 1)   # optional not counted
        self.assertEqual(out['matched'], 1)

    def test_deduped_to_one_deal_per_canonical(self):
        self._leaflet(self.onion, store='LIDL_CZ')
        self._leaflet(self.onion, store='ALBERT_CZ', url='http://albert.cz/c')
        out = recipe_deals([
            {'canonical': 'onion', 'quantity': 1, 'unit': 'ks'},
            {'canonical': 'onion', 'quantity': 2, 'unit': 'ks'},
        ])
        self.assertEqual(out['matched'], 1)
        self.assertEqual(len(out['deals']), 1)

    def test_empty_ingredients(self):
        self.assertEqual(recipe_deals([]), {'matched': 0, 'total': 0, 'deals': []})
