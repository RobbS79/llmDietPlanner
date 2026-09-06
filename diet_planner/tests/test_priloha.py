"""The fixed příloha table and its data dependencies."""
from pathlib import Path

import yaml
from django.conf import settings
from django.test import TestCase
from django.utils.text import slugify

DATA = Path(settings.BASE_DIR) / 'diet_planner' / 'data'


def canonical_slugs():
    with open(DATA / 'canonical_ingredients.yaml', encoding='utf-8') as fh:
        return {slugify(e['name']) for e in yaml.safe_load(fh)}


def price_book_slugs():
    with open(DATA / 'canonical_prices.yaml', encoding='utf-8') as fh:
        book = yaml.safe_load(fh)
    return set((book.get('prices') or book).keys())


class BreadDumplingCanonicalTest(TestCase):
    def test_dictionary_has_bread_dumpling(self):
        self.assertIn('bread-dumpling', canonical_slugs())

    def test_price_book_has_bread_dumpling(self):
        self.assertIn('bread-dumpling', price_book_slugs())

    def test_availability_has_bread_dumpling_common(self):
        with open(DATA / 'ingredient_availability.yaml', encoding='utf-8') as fh:
            rows = {r['slug']: r for r in yaml.safe_load(fh)}
        self.assertEqual(rows['bread-dumpling']['availability'], 'common')
