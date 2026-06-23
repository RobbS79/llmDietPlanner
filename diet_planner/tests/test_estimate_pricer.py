"""
Static price-book loader — shared pricing primitives.
See [[pricing-pivot-static-book]]. The whole-plan EstimatePricer has been
removed; what remains is the committed book loader used by the per-recipe engine.
"""
from django.test import TestCase


class PriceBookFileTest(TestCase):
    """The committed book loads and is shaped as the pricer expects."""

    def test_book_loads_and_has_entries(self):
        from diet_planner.services.estimate_pricer import _load_book, reload_book
        reload_book()
        book = _load_book()
        self.assertEqual(book['currency'], 'CZK')
        self.assertGreater(len(book['prices']), 50)
        # every entry has the fields the pricer reads
        for slug, e in book['prices'].items():
            self.assertIn('pack', e)
            self.assertIn('price_per_unit', e)
            self.assertIn('unit', e)
