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
