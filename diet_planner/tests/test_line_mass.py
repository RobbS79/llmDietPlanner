from django.test import SimpleTestCase

from diet_planner.services.ingredient_mass import estimate_mass_g
from diet_planner.services.line_mass import line_grams
from diet_planner.services.nutrition_lookups import NutrientRow
from diet_planner.services.unit_vocab import normalize_unit, to_base, unit_kind


def row(density=None, piece=None, unit_weights=None):
    return NutrientRow(kcal=100, protein=1, carbs=1, fat=1, density=density,
                       piece_weight_g=piece, unit_weights=unit_weights or {})


class UnitVocabTest(SimpleTestCase):
    def test_aliases_normalise_across_languages(self):
        for raw, code in [('G', 'g'), ('gramů', 'g'), ('dkg', 'dkg'), ('dag', 'dkg'), ('Kg.', 'kg'),
                          ('ML', 'ml'), ('dl', 'dl'), ('lžíce', 'tbsp'), ('lžic', 'tbsp'), ('pl', 'tbsp'),
                          ('lžička', 'tsp'), ('čl', 'tsp'), ('hrnek', 'cup'), ('šálek', 'cup'),
                          ('ks', 'ks'), ('kusů', 'ks'), ('stroužek', 'stroužek'), ('stroužky', 'stroužek'),
                          ('plátek', 'plátek'), ('svazek', 'svazek'), ('hrst', 'hrst'), ('špetka', 'špetka'),
                          ('konzerva', 'konzerva'), ('plechovka', 'konzerva'), ('balení', 'balení')]:
            self.assertEqual(normalize_unit(raw), code, raw)

    def test_unit_kind(self):
        self.assertEqual(unit_kind('kg'), 'mass')
        self.assertEqual(unit_kind('tbsp'), 'volume')
        self.assertEqual(unit_kind('ks'), 'count')
        self.assertEqual(unit_kind('stroužek'), 'count')
        self.assertIsNone(unit_kind('furlong'))


class ToBaseTest(SimpleTestCase):
    def test_konzerva_and_sklenice_stay_unpriced(self):
        self.assertEqual(to_base(1, 'konzerva'), (1, None))
        self.assertEqual(to_base(1, 'sklenice'), (1, None))
        self.assertEqual(to_base(1, 'cl'), (10, 'volume'))

    def test_only_spetka_bridges_garnish_to_pricing(self):
        self.assertEqual(to_base(1, 'špetka'), (0.3, 'volume'))
        self.assertEqual(to_base(1, 'snítka'), (1, None))
        self.assertEqual(to_base(1, 'lístek'), (1, None))


class NewUnitsTest(SimpleTestCase):
    def test_new_aliases(self):
        for raw, code in [('svazku', 'svazek'), ('snítek', 'snítka'), ('větvička', 'snítka'),
                          ('větvičky', 'snítka'), ('větviček', 'snítka'), ('vetvicka', 'snítka'),
                          ('listy', 'lístek'), ('list', 'lístek'), ('lístku', 'lístek'),
                          ('hlava', 'hlava'), ('hlávky', 'hlava'), ('hlavičky', 'hlava'),
                          ('cm', 'cm'), ('dávky', 'dávka'), ('odměrka', 'dávka'), ('scoop', 'dávka')]:
            self.assertEqual(normalize_unit(raw), code, raw)

    def test_count_kinds_unpriced_and_weighed_via_unit_weights(self):
        for code in ('hlava', 'cm', 'dávka'):
            self.assertEqual(unit_kind(code), 'count')
            self.assertEqual(to_base(2, code), (2, None))
        ginger = row(unit_weights={'cm': 6})
        self.assertEqual(line_grams({'quantity': 3, 'unit': 'cm'}, ginger).grams, 18)
        self.assertEqual(line_grams({'quantity': 1, 'unit': 'hlava'}, row(piece=50)).reason, 'no_unit_weight')


class LineGramsTest(SimpleTestCase):
    def test_mass_units(self):
        self.assertEqual(line_grams({'quantity': 300, 'unit': 'g'}, row()).grams, 300)
        self.assertEqual(line_grams({'quantity': 1.5, 'unit': 'kg'}, row()).grams, 1500)
        self.assertEqual(line_grams({'quantity': 25, 'unit': 'dkg'}, row()).grams, 250)

    def test_volume_units_need_density(self):
        oil = row(density=0.92)
        self.assertAlmostEqual(line_grams({'quantity': 200, 'unit': 'ml'}, oil).grams, 184)
        self.assertAlmostEqual(line_grams({'quantity': 2, 'unit': 'lžíce'}, oil).grams, 27.6)
        self.assertAlmostEqual(line_grams({'quantity': 1, 'unit': 'hrnek'}, oil).grams, 230)
        r = line_grams({'quantity': 200, 'unit': 'ml'}, row())
        self.assertIsNone(r.grams)
        self.assertEqual(r.reason, 'no_density')

    def test_count_units(self):
        onion = row(piece=110)
        self.assertEqual(line_grams({'quantity': 2, 'unit': 'ks'}, onion).grams, 220)
        garlic = row(piece=40, unit_weights={'stroužek': 5})
        self.assertEqual(line_grams({'quantity': 3, 'unit': 'stroužky'}, garlic).grams, 15)
        self.assertEqual(line_grams({'quantity': 1, 'unit': 'ks'}, garlic).grams, 40)
        r = line_grams({'quantity': 2, 'unit': 'ks'}, row())
        self.assertIsNone(r.grams)
        self.assertEqual(r.reason, 'no_piece_weight')
        r = line_grams({'quantity': 1, 'unit': 'plátek'}, row(piece=100))
        self.assertEqual(r.reason, 'no_unit_weight')

    def test_garnish_units_have_defaults(self):
        self.assertEqual(line_grams({'quantity': 1, 'unit': 'špetka'}, row()).grams, 1)
        self.assertEqual(line_grams({'quantity': 2, 'unit': 'snítka'}, row()).grams, 4)

    def test_to_taste_is_zero_not_a_gap(self):
        r = line_grams({'quantity': None, 'unit': None}, row())
        self.assertEqual((r.grams, r.method), (0.0, 'to_taste'))
        self.assertEqual(line_grams({'quantity': 0, 'unit': 'g'}, row()).method, 'to_taste')

    def test_unknown_unit_and_missing_row(self):
        self.assertEqual(line_grams({'quantity': 1, 'unit': 'furlong'}, row()).reason, 'unknown_unit')
        self.assertEqual(line_grams({'quantity': 100, 'unit': 'g'}, None).grams, 100)   # mass never needs a row
        self.assertEqual(line_grams({'quantity': 1, 'unit': 'ks'}, None).reason, 'no_piece_weight')

    def test_quantity_parsing(self):
        self.assertEqual(line_grams({'quantity': '1 500', 'unit': 'g'}, row()).grams, 1500)
        self.assertEqual(line_grams({'quantity': '1\u202f500', 'unit': 'g'}, row()).grams, 1500)
        for bad in ('1/2', 'cca 200'):
            r = line_grams({'quantity': bad, 'unit': 'g'}, row())
            self.assertEqual((r.grams, r.reason), (None, 'bad_quantity'), bad)
        self.assertEqual(line_grams({'quantity': '', 'unit': 'g'}, row()).method, 'to_taste')
        self.assertEqual(line_grams({'quantity': '  ', 'unit': 'g'}, row()).method, 'to_taste')

    def test_mg_and_dotted_units(self):
        self.assertAlmostEqual(line_grams({'quantity': 500, 'unit': 'mg'}, row()).grams, 0.5)
        self.assertEqual(normalize_unit('dl.'), 'dl')
        self.assertEqual(normalize_unit('Ks.'), 'ks')

    def test_czech_decimal_comma(self):
        self.assertEqual(line_grams({'quantity': '1,5', 'unit': 'kg'}, row()).grams, 1500)


class IngredientMassParityTest(SimpleTestCase):
    def test_estimate_mass_still_lower_bound_via_line_grams(self):
        est = estimate_mass_g([
            {'quantity': 200, 'unit': 'g'},
            {'quantity': 2, 'unit': 'ks', 'canonical': 'onion'},
            {'quantity': 1, 'unit': 'ks', 'canonical': 'unknown'},
        ], {'onion': 110})
        self.assertEqual(est.grams, 420)
        self.assertEqual((est.known_lines, est.unknown_lines), (2, 1))
