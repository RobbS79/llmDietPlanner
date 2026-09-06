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


from types import SimpleNamespace  # noqa: E402

from diet_planner.services.priloha import (  # noqa: E402
    SIDES, SIDE_KEYS, pick_side, side_ingredient, side_nutrition,
)


class SideTableTest(TestCase):
    def test_five_keys_in_spec_order(self):
        self.assertEqual(SIDE_KEYS, ('chleb', 'brambory', 'ryze', 'knedlik', 'testoviny'))

    def test_every_canonical_exists_in_dictionary_and_price_book(self):
        slugs = canonical_slugs()
        book = price_book_slugs()
        for side in SIDES.values():
            self.assertIn(side.canonical, slugs, side.key)
            self.assertIn(side.canonical, book, side.key)

    def test_every_row_is_complete(self):
        for side in SIDES.values():
            self.assertTrue(side.name_cs and side.with_cs and side.display, side.key)
            self.assertGreater(side.grams, 0)
            for n in (side.calories, side.protein, side.carbs, side.fat):
                self.assertGreaterEqual(n, 0)
            self.assertGreater(side.calories, 0)

    def test_dietary_breaks(self):
        self.assertIn('gluten_free', SIDES['chleb'].breaks_tags)
        self.assertIn('gluten_free', SIDES['knedlik'].breaks_tags)
        self.assertIn('vegan', SIDES['knedlik'].breaks_tags)
        self.assertIn('gluten_free', SIDES['testoviny'].breaks_tags)
        self.assertEqual(SIDES['brambory'].breaks_tags, frozenset())
        self.assertEqual(SIDES['ryze'].breaks_tags, frozenset())


class PickSideTest(TestCase):
    def _recipe(self, options):
        return SimpleNamespace(side_options=options)

    def test_first_option_wins(self):
        self.assertEqual(pick_side(self._recipe(['chleb', 'brambory']), set()).key, 'chleb')

    def test_dietary_break_skips_to_next(self):
        self.assertEqual(
            pick_side(self._recipe(['chleb', 'brambory']), {'gluten_free'}).key, 'brambory')

    def test_no_options_is_none(self):
        self.assertIsNone(pick_side(self._recipe([]), set()))
        self.assertIsNone(pick_side(self._recipe(None), set()))

    def test_no_fit_is_none(self):
        self.assertIsNone(pick_side(self._recipe(['chleb', 'knedlik']), {'gluten_free'}))

    def test_unknown_key_is_ignored(self):
        self.assertEqual(pick_side(self._recipe(['sushi', 'ryze']), set()).key, 'ryze')


class SideRenderTest(TestCase):
    def test_ingredient_scales_with_portions(self):
        ing = side_ingredient(SIDES['chleb'], portions=2)
        self.assertEqual(ing, {
            'name': 'chléb', 'quantity': 160.0, 'unit': 'g',
            'canonical': 'bread-loaf', 'catalog_id': None,
            'optional': False, 'role': 'side',
        })

    def test_nutrition_scales_with_portions(self):
        n = side_nutrition(SIDES['ryze'], portions=3)
        self.assertEqual(n['calories'], 630.0)
        self.assertEqual(n['carbs'], SIDES['ryze'].carbs * 3)
