"""Availability substitution: model fields and the pure planner."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CanonicalIngredient, IngredientAlias
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


class VanillaAromaCanonicalTests(TestCase):
    """vanilkové aroma is a product you buy, not a synonym for vanilka."""

    def test_seed_creates_distinct_vanilla_aroma(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        aroma = CanonicalIngredient.objects.filter(slug='vanilla-aroma').first()
        self.assertIsNotNone(aroma, "vanilla-aroma canonical missing")
        self.assertEqual(aroma.name_cs, 'vanilkové aroma')

    def test_vanilla_no_longer_aliases_aroma(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        from diet_planner.services.canonical_lookup import resolve_canonical
        resolved = resolve_canonical('vanilkové aroma')
        self.assertIsNotNone(resolved)
        self.assertEqual(
            resolved.slug, 'vanilla-aroma',
            "vanilkové aroma must resolve to its own canonical, not vanilka")

    def test_vanilla_aroma_is_rated_common(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        aroma = CanonicalIngredient.objects.get(slug='vanilla-aroma')
        self.assertEqual(aroma.availability, 'common')


class AliasRepointingTests(TestCase):
    """Seeding must MOVE an alias that the YAML reassigns to another canonical.

    The command upserts canonicals but created aliases with get_or_create, so a
    pre-existing alias kept pointing at its old canonical forever — the YAML
    edit that splits vanilla-aroma out of vanilla would silently no-op on any
    database that had already been seeded once (i.e. dev and prod).
    """

    def test_existing_alias_is_repointed_to_the_yaml_owner(self):
        old, _ = CanonicalIngredient.objects.get_or_create(
            slug='vanilla', defaults={'name': 'vanilla'})
        IngredientAlias.objects.update_or_create(
            alias='vanilkové aroma', language_code='cs',
            defaults={'canonical_ingredient': old},
        )

        call_command('seed_canonical_ingredients', stdout=StringIO())

        alias = IngredientAlias.objects.get(alias='vanilkové aroma', language_code='cs')
        self.assertEqual(
            alias.canonical_ingredient.slug, 'vanilla-aroma',
            "a re-seed must move the alias to the canonical the YAML gives it")

    def test_repointing_does_not_duplicate_aliases(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('seed_canonical_ingredients', stdout=StringIO())
        self.assertEqual(
            IngredientAlias.objects.filter(
                alias='vanilkové aroma', language_code='cs').count(),
            1)

    def test_reseed_is_idempotent_for_alias_owners(self):
        """Two runs must leave the same owner, not flip it back and forth.

        `plísňový sýr` was listed under BOTH czech-soft-cheese and blue-cheese,
        so once seeding started repointing, each run reversed the previous one.
        """
        call_command('seed_canonical_ingredients', stdout=StringIO())
        first = dict(
            IngredientAlias.objects.values_list('id', 'canonical_ingredient_id'))
        out = StringIO()
        call_command('seed_canonical_ingredients', stdout=out)
        second = dict(
            IngredientAlias.objects.values_list('id', 'canonical_ingredient_id'))
        self.assertEqual(first, second, 'a second seed moved alias owners')
        self.assertIn('repointed=0', out.getvalue())


class DuplicateAliasClaimTests(TestCase):
    def test_yaml_claiming_one_alias_twice_fails_loudly(self):
        """Ambiguous ownership must be a hard error, not a coin flip."""
        import tempfile, os
        from django.core.management.base import CommandError
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False,
                                         encoding='utf-8') as fh:
            fh.write(
                "- name: cheese one\n"
                "  slug: cheese-one\n"
                "  aliases:\n"
                "    - { alias: \"sporny syr\", language_code: cs }\n"
                "- name: cheese two\n"
                "  slug: cheese-two\n"
                "  aliases:\n"
                "    - { alias: \"sporny syr\", language_code: cs }\n"
            )
            path = fh.name
        try:
            with self.assertRaises(CommandError) as ctx:
                call_command('seed_canonical_ingredients', f'--file={path}',
                             stdout=StringIO())
            self.assertIn('sporny syr', str(ctx.exception))
        finally:
            os.unlink(path)

    def test_the_real_yaml_has_no_duplicate_claims(self):
        """Guards the shipped data file itself."""
        call_command('seed_canonical_ingredients', stdout=StringIO())
