"""build_price_book piece<->weight bridge.

Count-unit canonicals ("2 ks cibule") are sold by weight at Rohlík
("Cibule žlutá, síť 1 kg @ 19.90"). Before the bridge, build_price_book
discarded the weight-priced product on a dimension mismatch, so onion/garlic/
lemon/etc. never reached the price book despite a real, current catalog price.
With a typical piece weight the real price seeds the book as a per-piece price.
"""
from io import StringIO
from unittest.mock import patch

import yaml
from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CanonicalIngredient
from diet_planner.tests.factories import make_canonical, make_price


class BuildPriceBookPieceWeightBridgeTest(TestCase):
    def _build(self, weights):
        out = StringIO()
        with patch(
            'diet_planner.management.commands.build_price_book.load_piece_weights',
            return_value=weights,
        ):
            call_command('build_price_book', '--stdout', stdout=out)
        return yaml.safe_load(out.getvalue())['prices']

    def test_count_canonical_sold_by_weight_is_priced_per_piece(self):
        make_canonical('cibule', default_unit='ks')
        make_price(
            store_code='ROHLIK', normalized_name='cibule žlutá síť',
            price='19.90', package_size='1', package_unit='kg',
            canonical=CanonicalIngredient.objects.get(slug='cibule'),
        )
        book = self._build({'cibule': 110.0})
        self.assertIn('cibule', book)
        entry = book['cibule']
        self.assertEqual(entry['unit'], 'ks')
        # 19.90/kg = 0.0199/g; × 110 g/piece ≈ 2.19 CZK per onion.
        self.assertAlmostEqual(entry['price_per_unit'], 19.90 / 1000 * 110, places=2)

    def test_no_piece_weight_means_still_skipped(self):
        # Guard: without a piece weight we must NOT invent a cross-dimension
        # price — the product is legitimately unpriceable for a count canonical.
        make_canonical('zázvor-kus', default_unit='ks')
        make_price(
            store_code='ROHLIK', normalized_name='zázvor kus',
            price='12.00', package_size='100', package_unit='g',
            canonical=CanonicalIngredient.objects.get(slug='zazvor-kus'),
        )
        book = self._build({})  # no weights
        self.assertNotIn('zazvor-kus', book)
