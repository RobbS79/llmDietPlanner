"""
Tests for shopping-list pantry classification.

The whole-plan price-range + leaflet-deal machinery has been removed; what
remains is the pure pantry-classification decision logic (`classify_pantry_level`,
`item_is_excluded`), exercised as SimpleTestCase (no DB).

Behaviors asserted (SHOPPING_LIST_PRICING_PLAN.md Section 6):
- #2 basics ON / fridge OFF default semantics (the exclusion truth table)
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from diet_planner.services.shopping_list_pricing import (
    classify_pantry_level,
    item_is_excluded,
)


def _canonical(name='', name_cs='', name_sk='', is_pantry_staple=False):
    """Stand-in for a CanonicalIngredient — classify_pantry_level only reads
    .name, .name_cs, .name_sk, .is_pantry_staple, so a stub object suffices."""
    return SimpleNamespace(
        name=name,
        name_cs=name_cs,
        name_sk=name_sk,
        is_pantry_staple=is_pantry_staple,
    )


# --------------------------------------------------------------------------- #
# Pure functions — SimpleTestCase, no DB.
# --------------------------------------------------------------------------- #

class ClassifyPantryLevelTest(SimpleTestCase):
    def test_direct_name_hit_fridge(self):
        # English fridge basics by the passed-in ingredient name.
        self.assertEqual(classify_pantry_level('milk', None), 'fridge')
        self.assertEqual(classify_pantry_level('butter', None), 'fridge')
        self.assertEqual(classify_pantry_level('egg', None), 'fridge')
        self.assertEqual(classify_pantry_level('eggs', None), 'fridge')

    def test_direct_name_hit_czech_slovak(self):
        # Czech / Slovak names also live in FRIDGE_BASIC_NAMES.
        for name in ('mléko', 'máslo', 'vejce', 'mlieko', 'vajcia'):
            self.assertEqual(classify_pantry_level(name, None), 'fridge', name)

    def test_name_normalized_case_and_whitespace(self):
        self.assertEqual(classify_pantry_level('  MLÉKO  ', None), 'fridge')

    def test_canonical_name_hit_fridge(self):
        # Ingredient text doesn't match, but the canonical .name does.
        c = _canonical(name='butter')
        self.assertEqual(classify_pantry_level('plain unsalted spread', c), 'fridge')

    def test_canonical_name_cs_hit_fridge(self):
        c = _canonical(name='something-else', name_cs='mléko')
        self.assertEqual(classify_pantry_level('whole fat product', c), 'fridge')

    def test_canonical_name_sk_hit_fridge(self):
        c = _canonical(name='something-else', name_sk='vajcia')
        self.assertEqual(classify_pantry_level('farm fresh', c), 'fridge')

    def test_canonical_pantry_staple_dry(self):
        c = _canonical(name='olive oil', is_pantry_staple=True)
        self.assertEqual(classify_pantry_level('olivový olej', c), 'dry')

    def test_fridge_wins_over_dry(self):
        # A canonical that is BOTH a fridge basic name and pantry staple should
        # classify as 'fridge' (fridge check runs first).
        c = _canonical(name='milk', is_pantry_staple=True)
        self.assertEqual(classify_pantry_level('milk', c), 'fridge')

    def test_plain_ingredient_none(self):
        c = _canonical(name='chicken breast', is_pantry_staple=False)
        self.assertIsNone(classify_pantry_level('chicken breast', c))

    def test_no_canonical_plain_ingredient_none(self):
        self.assertIsNone(classify_pantry_level('banana', None))

    def test_empty_and_none_input(self):
        self.assertIsNone(classify_pantry_level('', None))
        self.assertIsNone(classify_pantry_level(None, None))
        self.assertIsNone(classify_pantry_level('   ', None))

    def test_canonical_with_empty_alias_fields(self):
        # Empty name_cs/name_sk must not match the empty string in the set.
        c = _canonical(name='rice', name_cs='', name_sk='', is_pantry_staple=False)
        self.assertIsNone(classify_pantry_level('rice', c))


class ItemIsExcludedTest(SimpleTestCase):
    """Truth table (decision #2): dry excluded iff basics_on, fridge excluded
    iff fridge_on, None never excluded."""

    def test_dry_excluded_only_when_basics_on(self):
        self.assertTrue(item_is_excluded('dry', basics_on=True, fridge_on=False))
        self.assertTrue(item_is_excluded('dry', basics_on=True, fridge_on=True))
        self.assertFalse(item_is_excluded('dry', basics_on=False, fridge_on=False))
        self.assertFalse(item_is_excluded('dry', basics_on=False, fridge_on=True))

    def test_fridge_excluded_only_when_fridge_on(self):
        self.assertTrue(item_is_excluded('fridge', basics_on=False, fridge_on=True))
        self.assertTrue(item_is_excluded('fridge', basics_on=True, fridge_on=True))
        self.assertFalse(item_is_excluded('fridge', basics_on=False, fridge_on=False))
        self.assertFalse(item_is_excluded('fridge', basics_on=True, fridge_on=False))

    def test_none_level_never_excluded(self):
        for basics_on in (True, False):
            for fridge_on in (True, False):
                self.assertFalse(
                    item_is_excluded(None, basics_on=basics_on, fridge_on=fridge_on),
                    (basics_on, fridge_on),
                )

    def test_default_toggle_semantics(self):
        # Decision #2 defaults: basics ON, fridge OFF.
        self.assertTrue(item_is_excluded('dry', basics_on=True, fridge_on=False))
        self.assertFalse(item_is_excluded('fridge', basics_on=True, fridge_on=False))
