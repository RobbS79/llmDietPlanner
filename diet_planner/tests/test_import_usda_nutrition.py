import csv, difflib, json, re, shutil, tempfile
from io import StringIO
from pathlib import Path

import yaml
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from diet_planner.management.commands.import_usda_nutrition import (
    best_match, derive_density, derive_piece_weights, nutrients_of,
)

FIX = Path(__file__).parent / 'fixtures' / 'usda_sr_legacy_slice.json'
REAL_YAML = Path(__file__).resolve().parents[1] / 'data' / 'canonical_ingredients.yaml'


def _food(desc, *portions, fdc=1):
    """Inline SR-shaped food; portions are (gramWeight, modifier) with measureUnit 'undetermined'."""
    return {'fdcId': fdc, 'description': desc, 'foodNutrients': [],
            'foodPortions': [{'gramWeight': g, 'amount': 1.0, 'measureUnit': {'name': 'undetermined'},
                              'modifier': m} for g, m in portions]}


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
        pool = [{'fdcId': 1, 'description': 'Tomatoes, red, ripe, canned, with salt added'},
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

    def test_variant_colour_and_oil_penalties(self):
        pool = [{'fdcId': 1, 'description': 'Bacon, meatless'},
                {'fdcId': 2, 'description': 'Pork, cured, bacon, unprepared'},
                {'fdcId': 3, 'description': 'Oil, olive, salad or cooking'},
                {'fdcId': 4, 'description': 'Olives, ripe, canned (small-extra large)'},
                {'fdcId': 5, 'description': 'Nuts, walnuts, black, dried'},
                {'fdcId': 6, 'description': 'Nuts, walnuts, english'},
                {'fdcId': 7, 'description': 'Milk, reduced fat, fluid, 2% milkfat'},
                {'fdcId': 8, 'description': 'Milk, whole, 3.25% milkfat'}]
        self.assertEqual(best_match('bacon', pool, category='meat')[0]['fdcId'], 2)
        self.assertEqual(best_match('olives', pool, category='canned')[0]['fdcId'], 4)
        self.assertEqual(best_match('walnuts', pool, category='nuts')[0]['fdcId'], 6)
        self.assertEqual(best_match('milk', pool, category='dairy')[0]['fdcId'], 8)

    def test_variant_phrases_and_percent_tokens(self):
        pool = [{'fdcId': 1, 'description': 'Milk, whole, 3.25% milkfat, with added vitamin D'},
                {'fdcId': 2, 'description': 'Milk, reduced fat, fluid, 2% milkfat, with added vitamin A and vitamin D'},
                {'fdcId': 3, 'description': 'Milk, lowfat, fluid, 1% milkfat, with added vitamin A and vitamin D'},
                {'fdcId': 4, 'description': 'Beef, ground, 70% lean meat / 30% fat, raw'},
                {'fdcId': 5, 'description': 'Beef, ground, 85% lean meat / 15% fat, raw'},
                {'fdcId': 6, 'description': 'Beef, ground, 90% lean meat / 10% fat, raw'}]
        self.assertEqual(best_match('milk', pool, category='dairy', query='milk reduced fat 2%')[0]['fdcId'], 2)
        self.assertEqual(best_match('beef mince', pool, category='meat', query='beef ground 85% lean')[0]['fdcId'], 5)


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

    def test_piece_weights_skip_measures_and_prefer_medium(self):
        almonds = _food('Nuts, almonds', (28.35, 'oz (23 whole kernels)'), (1.2, 'almond'), (143, 'cup, whole'))
        self.assertIsNone(derive_piece_weights(almonds)['piece_weight_g'])          # not the 28.4 g ounce
        cabbage = _food('Cabbage, raw', (33, 'leaf, large'), (908, 'head, medium (about 5-3/4" dia)'),
                        (89, 'cup, chopped'), (23, 'leaf, medium'), (15, 'leaf'))
        pw = derive_piece_weights(cabbage)
        self.assertEqual(pw['piece_weight_g'], 908.0)                              # a head, not a leaf
        self.assertEqual(pw['unit_weights'], {'lístek': 15.0})                     # plain "leaf" wins
        berries = _food('Strawberries, raw', (232, 'cup, pureed'), (18, 'large (1-3/8" dia)'),
                        (12, 'medium (1-1/4" dia)'), (27, 'extra large (1-5/8" dia)'))
        self.assertEqual(derive_piece_weights(berries)['piece_weight_g'], 12.0)
        romaine = _food('Lettuce, cos or romaine, raw', (47, 'cup shredded'), (6, 'leaf inner'), (28, 'leaves'))
        self.assertIn('lístek', derive_piece_weights(romaine)['unit_weights'])      # leaves -> leaf

    def test_density_skips_cut_forms_and_rejects_implausible(self):
        cabbage = _food('Cabbage, raw', (89, 'cup, chopped'), (70, 'cup, shredded'))
        self.assertIsNone(derive_density(cabbage))
        onion = _food('Onions, raw', (10, 'tbsp chopped'), (160, 'cup, chopped'))
        self.assertIsNone(derive_density(onion))
        honey = _food('Honey', (339, 'cup'), (21, 'tbsp'))
        self.assertAlmostEqual(derive_density(honey), 1.4, places=3)               # tbsp preferred
        weird = _food('Spices, saffron', (0.7, 'tbsp'), (2000, 'cup'))
        self.assertIsNone(derive_density(weird))                                   # 0.047 and 8.3 g/ml


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
        self.assertIn('query', rows['olive-oil'])
        self.assertEqual(rows['bread-dumpling']['kcal'], '200')                     # kept_manual carries values
        self.assertEqual(rows['bread-dumpling']['notes'], 'manual:czech table')

    def test_usda_query_read_from_block_or_top_level_and_written_into_block(self):
        y = self._yaml("- name: flour\n  category: baking\n  nutrition:\n    usda_query: wheat flour all-purpose\n"
                       "    note_x: keep me\n- name: flour two\n  category: baking\n"
                       "  usda_query: wheat flour all-purpose\n")
        call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(y), write_yaml=True, stdout=StringIO())
        a, b = yaml.safe_load(y.read_text(encoding='utf-8'))
        self.assertEqual(a['nutrition']['source'], 'usda:169761')
        self.assertEqual(a['nutrition']['usda_query'], 'wheat flour all-purpose')
        self.assertEqual(a['nutrition']['note_x'], 'keep me')
        self.assertEqual(b['nutrition']['source'], 'usda:169761')
        self.assertEqual(b['nutrition']['usda_query'], 'wheat flour all-purpose')
        self.assertEqual(list(a['nutrition'])[-1], 'source')

    def test_refuses_to_append_duplicate_nutrition_key(self):
        text = "- name: garlic\n  category: vegetables\n# a column-0 comment inside the entry\n  nutrition:\n    piece_weight_g: 5\n"
        y = self._yaml(text)
        with self.assertRaises(CommandError):
            call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(y), write_yaml=True, stdout=StringIO())
        self.assertEqual(y.read_text(encoding='utf-8'), text)

    def test_write_yaml_on_real_file_only_touches_nutrition_blocks(self):
        tmp = Path(tempfile.mkdtemp()) / 'canonical_ingredients.yaml'
        shutil.copy(REAL_YAML, tmp)
        before = tmp.read_text(encoding='utf-8')
        call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(tmp), write_yaml=True, stdout=StringIO())
        after = tmp.read_text(encoding='utf-8')
        self.assertNotEqual(before, after)
        b_lines, a_lines = before.splitlines(), after.splitlines()
        self.assertEqual(sum(l.lstrip().startswith('#') for l in a_lines),
                         sum(l.lstrip().startswith('#') for l in b_lines))
        inline = lambda ls: sum('#' in l and not l.lstrip().startswith('#') for l in ls)
        self.assertEqual(inline(a_lines), inline(b_lines))
        # Removed lines may only be key lines of nutrition blocks, one per replaced key.
        in_block, block_lines = False, set()
        for i, l in enumerate(b_lines):
            if re.match(r'^  nutrition:', l):
                in_block = True
                continue
            if in_block and l.startswith('    '):
                block_lines.add(i)
            else:
                in_block = False
        sm = difflib.SequenceMatcher(a=b_lines, b=a_lines, autojunk=False)
        removed = [i for op, i1, i2, _, _ in sm.get_opcodes() if op in ('replace', 'delete') for i in range(i1, i2)]
        self.assertTrue(set(removed) <= block_lines, [b_lines[i] for i in removed if i not in block_lines])
        old, new = yaml.safe_load(before), yaml.safe_load(after)
        self.assertEqual(len(old), len(new))
        for o, n in zip(old, new):
            self.assertEqual({k: v for k, v in o.items() if k != 'nutrition'},
                             {k: v for k, v in n.items() if k != 'nutrition'})
        garlic = next(e for e in new if e['name'] == 'garlic')['nutrition']
        self.assertEqual(garlic['source'], 'usda:169230')
        self.assertEqual(garlic['piece_weight_g'], 5)                               # hand-set kept
        self.assertIn('# one clove', after)                                         # its comment too
        self.assertIn('kcal', next(e for e in new if e['name'] == 'olive oil')['nutrition'])

    def test_low_confidence_rows_are_left_for_review(self):
        y = self._yaml("- name: dragon fruit\n  category: fruits\n")
        out = StringIO()
        call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(y), write_yaml=True, stdout=out)
        self.assertEqual(y.read_text(encoding='utf-8'), "- name: dragon fruit\n  category: fruits\n")

    def test_existing_piece_weight_and_unit_weights_are_kept(self):
        y = self._yaml("- name: garlic\n  category: vegetables\n  nutrition: {piece_weight_g: 5, unit_weights: {stroužek: 5}}\n")
        call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(y), write_yaml=True, stdout=StringIO())
        n = yaml.safe_load(y.read_text(encoding='utf-8'))[0]['nutrition']
        self.assertEqual(n['piece_weight_g'], 5)              # hand-set piece weight wins
        self.assertEqual(n['unit_weights'], {'stroužek': 5})   # hand-set unit weight wins over USDA 3 g
        self.assertEqual(n['source'], 'usda:169230')
