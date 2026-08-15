"""Availability rating: model defaults and the pure rollup."""
from django.test import TestCase

from diet_planner.models import Availability, CanonicalIngredient, CuratedRecipe


class AvailabilityFieldTest(TestCase):
    def test_new_canonical_defaults_to_unrated(self):
        ci = CanonicalIngredient.objects.create(
            name='tahini', name_cs='tahini', slug='tahini',
        )
        ci.refresh_from_db()
        self.assertEqual(ci.availability, Availability.UNRATED)
        self.assertEqual(ci.availability_note, '')

    def test_availability_note_is_optional_free_text(self):
        ci = CanonicalIngredient.objects.create(
            name='kale', name_cs='kadeřávek', slug='kale',
            availability=Availability.FINDABLE,
            availability_note='velké Albert/Kaufland sezónně',
        )
        ci.refresh_from_db()
        self.assertEqual(ci.availability, 'findable')
        self.assertEqual(ci.availability_note, 'velké Albert/Kaufland sezónně')


class ShoppingDifficultyFieldTest(TestCase):
    def _recipe(self, **kw):
        defaults = dict(
            slug='test-dish', name_cs='Testovací jídlo',
            source_url='https://example.test/x', source_name='Example',
        )
        defaults.update(kw)
        return CuratedRecipe.objects.create(**defaults)

    def test_defaults_mean_not_yet_computed(self):
        r = self._recipe()
        self.assertEqual(r.shopping_difficulty, Availability.UNRATED)
        self.assertEqual(r.shopping_blockers, [])
        self.assertEqual(r.adaptation_note, '')
        self.assertIsNone(r.original_ingredients)

    def test_fields_round_trip(self):
        r = self._recipe(
            slug='test-dish-2',
            shopping_difficulty=Availability.SPECIALTY,
            shopping_blockers=['tahini', 'sumac'],
            adaptation_note='Upraveno pro dostupnost v českých obchodech',
            original_ingredients=[{'name': 'tahini', 'quantity': 30, 'unit': 'g'}],
        )
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, 'specialty')
        self.assertEqual(r.shopping_blockers, ['tahini', 'sumac'])
        self.assertEqual(r.original_ingredients[0]['name'], 'tahini')
