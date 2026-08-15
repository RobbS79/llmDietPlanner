"""Availability rating: model defaults and the pure rollup."""
from django.test import TestCase

from diet_planner.models import Availability, CanonicalIngredient


class AvailabilityFieldTest(TestCase):
    def test_new_canonical_defaults_to_unrated(self):
        ci = CanonicalIngredient.objects.create(
            name='tahini', name_cs='tahini', slug='tahini',
        )
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
