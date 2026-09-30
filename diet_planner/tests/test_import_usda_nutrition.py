import csv, json, tempfile
from io import StringIO
from pathlib import Path

import yaml
from django.core.management import call_command
from django.test import SimpleTestCase

from diet_planner.management.commands.import_usda_nutrition import (
    best_match, derive_density, derive_piece_weights, nutrients_of,
)

FIX = Path(__file__).parent / 'fixtures' / 'usda_sr_legacy_slice.json'


def foods():
    return json.loads(FIX.read_text())['SRLegacyFoods']


class MatchingTest(SimpleTestCase):
    def test_prefers_raw_over_cooked_and_canned(self):
        m, conf = best_match('chicken breast', foods(), category='meat')
        self.assertEqual(m['fdcId'], 171077)
        self.assertGreaterEqual(conf, 0.6)

    def test_usda_query_hint_overrides_name(self):
        m, _ = best_match('flour', foods(), category='baking', query='wheat flour all-purpose')
        self.assertEqual(m['fdcId'], 169761)

    def test_canned_category_allows_canned(self):
        m, _ = best_match('tomatoes', foods(), category='canned')
        self.assertEqual(m['fdcId'], 170500)

    def test_no_match_returns_none_with_zero_confidence(self):
        m, conf = best_match('dragon fruit', foods(), category='fruits')
        self.assertIsNone(m)
        self.assertEqual(conf, 0.0)


    def test_query_token_must_be_in_head_segment(self):
        pool = [{'fdcId': 1, 'description': 'Pork, cured, salt pork, raw'},
                {'fdcId': 2, 'description': 'Nuts, almond butter, plain, without salt added'},
                {'fdcId': 3, 'description': 'Salt, table'},
                {'fdcId': 4, 'description': 'Butter, salted'}]
        self.assertEqual(best_match('salt', pool, category='spices')[0]['fdcId'], 3)
        self.assertEqual(best_match('butter', pool, category='dairy')[0]['fdcId'], 4)
        m, conf = best_match('salt', pool[:2], category='spices')   # "salt" only outside the head
        self.assertIsNone(m)
        self.assertEqual(conf, 0.0)

    def test_brand_restaurant_and_snack_foods_are_excluded(self):
        pool = [{'fdcId': 1, 'description': "APPLEBEE'S, mozzarella sticks"},
                {'fdcId': 2, 'description': 'Restaurant, Italian, lasagna with meat'},
                {'fdcId': 3, 'description': 'Snacks, tortilla chips, nacho cheese'},
                {'fdcId': 4, 'description': 'Candies, NESTLE, AFTER EIGHT Mints'},
                {'fdcId': 5, 'description': 'Cheese, mozzarella, whole milk'}]
        self.assertEqual(best_match('mozzarella', pool, category='dairy')[0]['fdcId'], 5)
        for name, cat in (('lasagna', 'grains'), ('tortilla', 'grains'), ('mint', 'vegetables')):
            self.assertEqual(best_match(name, pool, category=cat), (None, 0.0), name)


class DerivationTest(SimpleTestCase):
    def test_nutrients_of(self):
        oil = next(f for f in foods() if f['fdcId'] == 171413)
        self.assertEqual(nutrients_of(oil), {'kcal': 884.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 100.0})

    def test_density_from_tbsp_or_cup(self):
        oil = next(f for f in foods() if f['fdcId'] == 171413)
        self.assertAlmostEqual(derive_density(oil), 13.5 / 15, places=3)
        milk = next(f for f in foods() if f['fdcId'] == 171265)
        self.assertAlmostEqual(derive_density(milk), 244 / 240, places=3)   # USDA cup = 240 ml
        chicken = next(f for f in foods() if f['fdcId'] == 171077)
        self.assertIsNone(derive_density(chicken))

    def test_piece_weights_from_portions(self):
        onion = next(f for f in foods() if f['fdcId'] == 170000)
        self.assertEqual(derive_piece_weights(onion), {'piece_weight_g': 110.0, 'unit_weights': {}})
        garlic = next(f for f in foods() if f['fdcId'] == 169230)
        self.assertEqual(derive_piece_weights(garlic), {'piece_weight_g': None, 'unit_weights': {'stroužek': 3.0}})
        egg = next(f for f in foods() if f['fdcId'] == 171287)
        self.assertEqual(derive_piece_weights(egg)['piece_weight_g'], 50.0)


class CommandTest(SimpleTestCase):
    def _yaml(self, text):
        f = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False, encoding='utf-8')
        f.write(text); f.close()
        return Path(f.name)

    def test_report_and_write_yaml(self):
        y = self._yaml("""# Header comment that must survive
# second header line

- name: olive oil
  category: oils
- name: chicken breast
  category: meat
- name: onion
  category: vegetables
- name: bread dumpling
  category: baking
  nutrition: {kcal: 200, protein: 7, carbs: 40, fat: 1, source: "manual:czech table"}
""")
        rep = y.with_suffix('.csv')
        out = StringIO()
        call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(y), report=str(rep),
                     write_yaml=True, stdout=out)
        rows = {r['slug']: r for r in csv.DictReader(rep.open(encoding='utf-8'))}
        self.assertEqual(rows['olive-oil']['fdc_id'], '171413')
        self.assertEqual(rows['bread-dumpling']['status'], 'kept_manual')
        text = y.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('# Header comment that must survive'))
        data = {e['name']: e for e in yaml.safe_load(text)}
        self.assertEqual(data['olive oil']['nutrition']['source'], 'usda:171413')
        self.assertAlmostEqual(data['olive oil']['nutrition']['density'], 0.9, places=2)
        self.assertEqual(data['onion']['nutrition']['piece_weight_g'], 110.0)
        self.assertEqual(data['bread dumpling']['nutrition']['source'], 'manual:czech table')
        self.assertIn('matched=3', out.getvalue())

    def test_low_confidence_rows_are_left_for_review(self):
        y = self._yaml("- name: dragon fruit\n  category: fruits\n")
        out = StringIO()
        call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(y), write_yaml=True, stdout=out)
        data = yaml.safe_load(y.read_text(encoding='utf-8'))
        self.assertEqual(data[0]['nutrition'], {'source': 'needs_review'})

    def test_existing_piece_weight_and_unit_weights_are_kept(self):
        y = self._yaml("- name: garlic\n  category: vegetables\n  nutrition: {piece_weight_g: 5, unit_weights: {stroužek: 5}}\n")
        call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(y), write_yaml=True, stdout=StringIO())
        n = yaml.safe_load(y.read_text(encoding='utf-8'))[0]['nutrition']
        self.assertEqual(n['piece_weight_g'], 5)              # hand-set piece weight wins
        self.assertEqual(n['unit_weights'], {'stroužek': 5})   # hand-set unit weight wins over USDA 3 g
        self.assertEqual(n['source'], 'usda:169230')
