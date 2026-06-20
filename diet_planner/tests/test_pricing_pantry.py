"""
Tests for pantry-staple pro-rated pricing and canonical ingredient lookup.

Covers:
- calculate_package_aware_price(is_staple=True) returns raw fraction × price
- calculate_package_aware_price(is_staple=False) keeps the ceil-to-whole-package behavior
- resolve_canonical matches by EN/CS/SK name and IngredientAlias, case-insensitive
"""
from decimal import Decimal

from django.test import TestCase

from diet_planner.tasks import calculate_package_aware_price
from diet_planner.services.canonical_lookup import _strip_descriptors, resolve_canonical


class CalculatePackageAwarePriceTest(TestCase):
    """Unit tests for the pricing function — no DB, no LLM, just math."""

    def _item(self, **overrides):
        base = {
            'ingredient': 'olive oil',
            'quantity': 10,
            'unit': 'ml',
            'price': 150,
            'product_unit': 'ml',
            'package_size': 500,
            'currency': 'CZK',
        }
        base.update(overrides)
        return base

    def test_grocery_rounds_up_to_whole_packages(self):
        # Need 400g, package is 500g at 39 CZK → 1 package × 39 = 39 CZK
        item = self._item(ingredient='chicken', quantity=400, unit='g', price=39, product_unit='g', package_size=500)
        price = calculate_package_aware_price(item)
        self.assertEqual(price, Decimal('39'))

    def test_grocery_buys_multiple_packages(self):
        # Need 800g, package is 500g at 39 CZK → 2 packages × 39 = 78 CZK
        item = self._item(ingredient='chicken', quantity=800, unit='g', price=39, product_unit='g', package_size=500)
        price = calculate_package_aware_price(item)
        self.assertEqual(price, Decimal('78'))

    def test_staple_prorates_by_fraction(self):
        # Need 10ml of a 500ml bottle at 150 CZK → 10/500 × 150 = 3 CZK
        item = self._item()
        price = calculate_package_aware_price(item, is_staple=True)
        self.assertEqual(price, Decimal('3'))

    def test_staple_populates_pantry_display_fields(self):
        item = self._item(quantity=25, unit='ml', price=150, package_size=500)
        calculate_package_aware_price(item, is_staple=True)
        self.assertEqual(item['fraction_used'], 0.05)
        self.assertEqual(item['pantry_pack_price'], 150.0)
        self.assertEqual(item['pantry_package_size'], 500.0)
        self.assertEqual(item['pantry_package_unit'], 'ml')

    def test_staple_handles_tiny_fraction(self):
        # 1g salt of a 500g bag at 10 CZK → 1/500 × 10 = 0.02 CZK
        item = self._item(ingredient='salt', quantity=1, unit='g', price=10, product_unit='g', package_size=500)
        price = calculate_package_aware_price(item, is_staple=True)
        self.assertEqual(price, Decimal('0.02'))

    def test_staple_default_is_false(self):
        # Without is_staple=True, behavior matches grocery (rounds up)
        item = self._item()
        price = calculate_package_aware_price(item)  # default is_staple=False
        # 10ml of 500ml bottle → ceil(10/500) = 1 package × 150 = 150
        self.assertEqual(price, Decimal('150'))

    def test_unit_conversion_kg_to_g(self):
        # Need 1.2kg, product is 1kg pack at 89.90 → 2 packages × 89.90 = 179.80
        item = self._item(ingredient='flour', quantity=1.2, unit='kg', price=89.90, product_unit='kg', package_size=1)
        price = calculate_package_aware_price(item)
        self.assertEqual(price, Decimal('179.80'))


class ResolveCanonicalTest(TestCase):
    """Tests that name matching finds the seeded pantry staples."""

    def test_match_by_english_name(self):
        ci = resolve_canonical('Olive oil')
        self.assertIsNotNone(ci)
        self.assertTrue(ci.is_pantry_staple)
        self.assertEqual(ci.slug, 'olive-oil')

    def test_match_by_czech_name(self):
        ci = resolve_canonical('Sójová omáčka')
        self.assertIsNotNone(ci)
        self.assertTrue(ci.is_pantry_staple)

    def test_match_by_slovak_name(self):
        # Cumin's Slovak name is "Rímska rasca"; bare "rasca" is caraway.
        ci = resolve_canonical('Rímska rasca')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'cumin')

    def test_match_case_insensitive(self):
        self.assertIsNotNone(resolve_canonical('OLIVE OIL'))
        self.assertIsNotNone(resolve_canonical('olive oil'))
        self.assertIsNotNone(resolve_canonical('Olive Oil'))

    def test_match_via_alias(self):
        # 'salt' is an alias for 'Table salt'
        ci = resolve_canonical('salt')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'table-salt')

    def test_match_via_czech_alias(self):
        # 'sůl' is a cs alias for table salt
        ci = resolve_canonical('sůl')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'table-salt')

    def test_unknown_returns_none(self):
        self.assertIsNone(resolve_canonical('chicken breast'))
        self.assertIsNone(resolve_canonical(''))
        self.assertIsNone(resolve_canonical('   '))
        self.assertIsNone(resolve_canonical(None))

    def test_whitespace_is_stripped(self):
        self.assertIsNotNone(resolve_canonical('  Olive oil  '))

    # --- normalized fallback (recipe-grounding): scraped/LLM names carry prep
    # and quality descriptors that must not defeat the match. ---

    def test_strips_quality_descriptor_after_comma(self):
        ci = resolve_canonical('Olivový olej, kvalitní')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'olive-oil')

    def test_match_is_word_order_independent(self):
        # black pepper is seeded as "Mletý černý pepř"; recipes say "černý pepř".
        ci = resolve_canonical('čerstvě mletý černý pepř')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'black-pepper')

    def test_strips_parenthetical(self):
        ci = resolve_canonical('olivový olej (extra panenský)')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'olive-oil')

    def test_disjunction_takes_first_option(self):
        ci = resolve_canonical('olivový olej nebo řepkový olej')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'olive-oil')

    def test_strips_prepositional_tail(self):
        ci = resolve_canonical('olivový olej na smažení')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'olive-oil')

    def test_strips_unicode_vulgar_fraction(self):
        # LLM ingredient lines carry vulgar fractions ("šťáva z ½ citronu");
        # the glyph must be dropped like an ASCII quantity, not left as a token
        # that defeats the normalized match.
        ci = resolve_canonical('olivový olej ½')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'olive-oil')


class StripDescriptorsTest(TestCase):
    """Pure-function tests for the normalizer key. Recipe ingredient lines from
    the curation corpus carry prep-state adjectives and can/tin tails that must
    reduce to the same base key as the canonical name, so the fallback match
    lands. (DB-free: asserts the residual key, not a resolution.)"""

    def test_strips_melted_state(self):
        # "rozpuštěné máslo" / "rozpuštěný kokosový olej" — melted X is still X,
        # same product, same price; the prep state must not defeat the match.
        self.assertEqual(_strip_descriptors('rozpuštěné máslo'), 'máslo')
        self.assertEqual(_strip_descriptors('rozpuštěný kokosový olej'),
                         'kokosový olej')

    def test_strips_lukewarm_state(self):
        self.assertEqual(_strip_descriptors('vlažné mléko'), 'mléko')

    def test_strips_creamy_modifier(self):
        # creamy peanut butter -> peanut butter
        self.assertEqual(_strip_descriptors('krémové arašídové máslo'),
                         'arašídové máslo')

    def test_strips_in_can_tail(self):
        # "v konzervě" / "v plechovce" are prep/packaging tails like "z konzervy".
        self.assertEqual(_strip_descriptors('krájená rajčata v konzervě'),
                         'rajčata')

    def test_disjunction_keeps_shared_trailing_head_noun(self):
        # "kokosový nebo olivový olej" = coconut OR olive *oil*; the head noun
        # is shared and trails the last option. Taking the bare first option
        # ("kokosový") drops it; we must keep "kokosový olej".
        self.assertEqual(_strip_descriptors('kokosový nebo olivový olej'),
                         'kokosový olej')

    def test_disjunction_first_option_with_own_head_unchanged(self):
        # Regression: when the first option already carries its head noun,
        # behaviour is unchanged (don't borrow from the last option).
        self.assertEqual(_strip_descriptors('olivový olej nebo řepkový olej'),
                         'olej olivový')

    def test_strips_unsweetened_modifier(self):
        # "neslazené kokosové lupínky" / "neslazené mandlové mléko" — the
        # sugar-content qualifier is a buyable-variant note but maps to the
        # same shelf product (unsweetened still appears next to sweetened in
        # CZ stores and shares pricing). Batch-03 head: 8 occurrences across
        # the corpus, dominantly on coconut-flakes / almond-milk / nut-butter.
        self.assertEqual(_strip_descriptors('neslazené kokosové lupínky'),
                         'kokosové lupínky')
        self.assertEqual(_strip_descriptors('neslazený sójový nápoj'),
                         'nápoj sójový')

    def test_strips_ripe_modifier(self):
        # "zralé avokádo" / "zralé banány" — ripeness is a state descriptor,
        # same SKU at the till. Batch-03 head: shows up on avocado, banana,
        # mango entries.
        self.assertEqual(_strip_descriptors('zralé avokádo'), 'avokádo')
        self.assertEqual(_strip_descriptors('zralý banán'), 'banán')
        self.assertEqual(_strip_descriptors('zralá rajčata'), 'rajčata')

    # --- Batch-04 (2026-06-20) prep-state modifiers. Each is a preparation or
    # size descriptor that does not change the buyable product, so the line must
    # reduce to its base canonical key. Drawn from the post-batch-03 unmapped
    # report head (miss-exactly-1 recipes blocked on one of these). ---

    def test_strips_natural_modifier(self):
        # "přírodní arašídové máslo" — natural peanut butter is the same shelf
        # product as plain peanut butter.
        self.assertEqual(_strip_descriptors('přírodní arašídové máslo'),
                         'arašídové máslo')

    def test_strips_cooked_uvareny_modifier(self):
        # "uvařená cizrna" — cooked chickpeas; the prep state must not defeat
        # the match (sibling of the existing "vařená" form).
        self.assertEqual(_strip_descriptors('uvařená cizrna'), 'cizrna')

    def test_strips_toasted_oprazeny_modifier(self):
        # "opražené piniové oříšky" — toasted pine nuts; toasting is a prep step.
        self.assertEqual(_strip_descriptors('opražené piniové oříšky'),
                         'oříšky piniové')

    def test_strips_mashed_modifier(self):
        # "rozmačkané zralé banány" — mashed ripe bananas; both mashed and ripe
        # are states, the product is bananas.
        self.assertEqual(_strip_descriptors('rozmačkané zralé banány'),
                         'banány')

    def test_strips_crumbled_modifier(self):
        # "rozdrobený sýr feta" — crumbled feta; crumbled is a prep form.
        self.assertEqual(_strip_descriptors('rozdrobený sýr feta'), 'feta sýr')

    def test_strips_blanched_modifier(self):
        # "mandlová mouka blanšírovaná" — blanched almond flour; same product.
        self.assertEqual(_strip_descriptors('mandlová mouka blanšírovaná'),
                         'mandlová mouka')

    def test_strips_medium_size_modifier(self):
        # "střední žlutá cibule" — medium is a size; reduces to the colour+noun
        # key that the onion alias "žlutá cibule" also produces.
        self.assertEqual(_strip_descriptors('střední žlutá cibule'),
                         'cibule žlutá')

    def test_strips_hardboiled_modifier(self):
        # "vejce natvrdo" — hard-boiled eggs are still eggs.
        self.assertEqual(_strip_descriptors('vejce natvrdo'), 'vejce')

    # --- Batch-05 (2026-06-20) prep-state modifiers, same price-safe rationale.

    def test_strips_cold_modifier(self):
        # "studené máslo" — cold butter is still butter (a fridge state).
        self.assertEqual(_strip_descriptors('studené máslo'), 'máslo')

    def test_strips_grilled_modifier(self):
        # "grilovaná kukuřice" — grilled corn is still corn.
        self.assertEqual(_strip_descriptors('grilovaná kukuřice'), 'kukuřice')

    def test_strips_grated_modifier(self):
        # "nastrouhaná cuketa" — grated zucchini (sibling of strouhaný).
        self.assertEqual(_strip_descriptors('nastrouhaná cuketa'), 'cuketa')
        self.assertEqual(_strip_descriptors('nastrouhaný čerstvý zázvor'),
                         'zázvor')

    def test_strips_toasted_bread_modifier(self):
        # "opečená bageta" — pan-toasted bread is still the bread.
        self.assertEqual(_strip_descriptors('opečená bageta'), 'bageta')
