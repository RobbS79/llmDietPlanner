"""Availability substitution: model fields and the pure planner."""
from django.test import TestCase

from diet_planner.models import CanonicalIngredient
from diet_planner.models.catalog import IngredientSubstitute


class SubstitutePurposeFieldTests(TestCase):
    def setUp(self):
        # get_or_create, not create: migration 0022_seed_canonical_staples
        # seeds the canonical table, so several of these slugs already exist in
        # a fresh test DB.
        self.a, _ = CanonicalIngredient.objects.get_or_create(
            slug='tamari', defaults={'name': 'tamari'})
        self.b, _ = CanonicalIngredient.objects.get_or_create(
            slug='soy-sauce',
            defaults={'name': 'soy sauce', 'name_cs': 'sójová omáčka'})

    def test_purpose_defaults_to_preference(self):
        """Existing rows must keep behaving exactly as before the migration."""
        sub = IngredientSubstitute.objects.create(ingredient=self.a, substitute=self.b)
        self.assertEqual(sub.purpose, IngredientSubstitute.Purpose.PREFERENCE)

    def test_substitute_unit_defaults_blank(self):
        sub = IngredientSubstitute.objects.create(ingredient=self.a, substitute=self.b)
        self.assertEqual(sub.substitute_unit, '')

    def test_availability_purpose_is_settable(self):
        sub = IngredientSubstitute.objects.create(
            ingredient=self.a, substitute=self.b,
            purpose=IngredientSubstitute.Purpose.AVAILABILITY,
            substitute_unit='ml',
        )
        sub.refresh_from_db()
        self.assertEqual(sub.purpose, 'availability')
        self.assertEqual(sub.substitute_unit, 'ml')
