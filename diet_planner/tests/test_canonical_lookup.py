"""Brand/label-token stripping so scraped leaflet names still resolve.

Plain "Avokádo" always matched; the recall gap was branded leaflet variants
("Avokádo bio Nature's Promise"). _strip_descriptors now drops grade/label and
store-brand tokens so the normalized-multiset key is unchanged by branding.
"""
from django.test import TestCase

from diet_planner.models import CanonicalIngredient
from diet_planner.services.canonical_lookup import (
    _strip_descriptors, clear_cache, resolve_canonical,
)


class StripDescriptorsBrandTests(TestCase):
    """Pure-function: branding must not change the base key."""

    def test_brand_and_label_tokens_stripped(self):
        self.assertEqual(_strip_descriptors('Avokádo bio Nature\'s Promise'), 'avokádo')
        self.assertEqual(_strip_descriptors('Banány bio Nature\'s Promise'), 'banány')
        self.assertEqual(_strip_descriptors('Baby špenát Bio Nature\'s Promise'), 'špenát')

    def test_retail_descriptors_stripped(self):
        self.assertEqual(_strip_descriptors('Brambory konzumní rané'), 'brambory')
        self.assertEqual(_strip_descriptors('Cibule kuchyňská'), 'cibule')

    def test_plain_name_unchanged(self):
        # No branding → identical to a plain produce name (the multiset key).
        self.assertEqual(
            _strip_descriptors('Avokádo bio Nature\'s Promise'),
            _strip_descriptors('avokádo'),
        )

    def test_existing_normalization_preserved(self):
        # Word-order-independent multiset behavior must be untouched.
        self.assertEqual(
            _strip_descriptors('černý pepř mletý'),
            _strip_descriptors('pepř černý'),
        )


class ResolveCanonicalBrandTests(TestCase):
    def test_branded_leaflet_name_resolves(self):
        avocado = CanonicalIngredient.objects.create(
            name='avocado', name_cs='avokádo', slug='avocado',
        )
        clear_cache()  # rebuild the process-cached normalized index for this DB
        self.assertEqual(resolve_canonical('Avokádo bio Nature\'s Promise'), avocado)
        self.assertEqual(resolve_canonical('avokádo'), avocado)  # plain still works


class DiacriticsFoldTests(TestCase):
    """Czech users routinely type without diacritics ("kureci", "ryze");
    resolution must not silently fail on the accent-free form."""

    def setUp(self):
        from diet_planner.models import IngredientAlias
        self.chicken = CanonicalIngredient.objects.create(
            name='chicken breast', name_cs='kuřecí prsa', slug='chicken-breast',
            category='meat',
        )
        IngredientAlias.objects.create(
            canonical_ingredient=self.chicken, alias='kuřecí', language_code='cs')
        self.rice = CanonicalIngredient.objects.create(
            name='rice', name_cs='rýže', slug='rice', category='grains',
        )
        clear_cache()

    def tearDown(self):
        clear_cache()

    def test_accent_free_alias_resolves(self):
        self.assertEqual(resolve_canonical('kureci'), self.chicken)

    def test_accent_free_name_resolves(self):
        self.assertEqual(resolve_canonical('ryze'), self.rice)
        self.assertEqual(resolve_canonical('kureci prsa'), self.chicken)

    def test_accented_form_still_wins_over_fold(self):
        # Folding must never shadow an exact match.
        self.assertEqual(resolve_canonical('rýže'), self.rice)
        self.assertEqual(resolve_canonical('kuřecí'), self.chicken)


class WantedCategoryFoldTests(TestCase):
    def test_accent_free_category_words_match(self):
        from diet_planner.services.recipe_retrieval import WantedIngredientMatcher
        from diet_planner.models import CuratedRecipe
        CanonicalIngredient.objects.create(
            name='walnuts', name_cs='vlašské ořechy', slug='walnuts', category='nuts')
        clear_cache()
        recipe = CuratedRecipe(
            name_cs='Ořechová směs', slug='orechova-smes',
            meal_types=['snack'], ingredients=[
                {'name': 'vlašské ořechy', 'quantity': 50, 'unit': 'g', 'canonical': 'walnuts'},
            ],
            instructions=[], base_servings=1,
            source_url='https://example.test', source_name='t',
        )
        self.assertEqual(WantedIngredientMatcher.build(['orechy']).hits(recipe), 1)
        self.assertEqual(WantedIngredientMatcher.build(['ořechy']).hits(recipe), 1)
