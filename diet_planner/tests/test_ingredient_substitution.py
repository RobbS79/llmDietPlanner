"""Availability substitution: model fields and the pure planner."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CanonicalIngredient, CuratedRecipe, IngredientAlias
from diet_planner.models.catalog import IngredientSubstitute
from diet_planner.services.ingredient_substitution import (
    IngredientChange, diff_applied_changes, disclosed_swaps)


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


class LoadSubstitutionsTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())

    def test_load_creates_availability_rows(self):
        out = StringIO()
        call_command('load_availability_substitutions', stdout=out)
        row = IngredientSubstitute.objects.filter(
            ingredient__slug='vanilla-extract', substitute__slug='vanilla-aroma',
        ).first()
        self.assertIsNotNone(row, "vanilla-extract -> vanilla-aroma row missing")
        self.assertEqual(row.purpose, IngredientSubstitute.Purpose.AVAILABILITY)
        self.assertIn('loaded=', out.getvalue())

    def test_tapioca_starch_swaps_to_potato_starch(self):
        """OWNER-SETTLED 2026-08-23: the sole specialty blocker on
        bezlepkove-livance. potato-starch (Solamyl) is common + gluten-free, so
        the swap is safe on a gluten_free recipe."""
        from diet_planner.services.ingredient_substitution import _TAG_INCOMPATIBLE
        call_command('load_availability_substitutions', stdout=StringIO())
        self.assertTrue(IngredientSubstitute.objects.filter(
            ingredient__slug='tapioca-starch', substitute__slug='potato-starch',
            purpose=IngredientSubstitute.Purpose.AVAILABILITY).exists())
        self.assertNotIn('potato-starch', _TAG_INCOMPATIBLE['gluten_free'])

    def test_load_is_idempotent(self):
        call_command('load_availability_substitutions', stdout=StringIO())
        first = IngredientSubstitute.objects.count()
        out = StringIO()
        call_command('load_availability_substitutions', stdout=out)
        self.assertEqual(IngredientSubstitute.objects.count(), first)
        self.assertIn('created=0', out.getvalue())

    def test_load_does_not_touch_preference_rows(self):
        """A hand-made preference row for the same pair must survive untouched."""
        a = CanonicalIngredient.objects.get(slug='vanilla-extract')
        b = CanonicalIngredient.objects.get(slug='vanilla-sugar')
        IngredientSubstitute.objects.create(ingredient=a, substitute=b)
        call_command('load_availability_substitutions', stdout=StringIO())
        row = IngredientSubstitute.objects.get(ingredient=a, substitute=b)
        self.assertEqual(row.purpose, IngredientSubstitute.Purpose.PREFERENCE)

    def test_every_swap_target_reads_as_a_lowercase_ingredient(self):
        """`new_name` is spliced into an ingredient line, so a capitalised
        canonical (`Řepkový olej`) reads there as a proper noun. Every other
        target in the table is lowercase; this keeps the odd one out honest."""
        import yaml
        from pathlib import Path
        from django.conf import settings
        rows = yaml.safe_load(
            (Path(settings.BASE_DIR) / 'diet_planner' / 'data'
             / 'ingredient_substitutions_cz.yaml').read_text(encoding='utf-8'))
        call_command('seed_canonical_ingredients', stdout=StringIO())
        offenders = [
            c.slug for c in CanonicalIngredient.objects.filter(
                slug__in={r['substitute'] for r in rows})
            if c.name_cs[:1].isupper()
        ]
        self.assertEqual(offenders, [], f'capitalised swap target(s): {offenders}')

    def test_a_row_dropped_from_the_yaml_is_dropped_from_the_table(self):
        """The file is the table. The loader only ever upserted, so retiring a
        swap in the YAML left it live in every already-seeded database — prod
        included, where the retired pair would have kept firing."""
        import os
        import tempfile
        call_command('load_availability_substitutions', stdout=StringIO())
        self.assertTrue(IngredientSubstitute.objects.filter(
            ingredient__slug='tamari', substitute__slug='soy-sauce').exists())

        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False,
                                         encoding='utf-8') as fh:
            fh.write('- ingredient: vanilla-extract\n  substitute: vanilla-aroma\n')
            path = fh.name
        try:
            out = StringIO()
            call_command('load_availability_substitutions', f'--path={path}',
                         stdout=out)
        finally:
            os.unlink(path)

        self.assertFalse(
            IngredientSubstitute.objects.filter(
                ingredient__slug='tamari', substitute__slug='soy-sauce').exists(),
            'a swap absent from the YAML survived the load')
        self.assertTrue(IngredientSubstitute.objects.filter(
            ingredient__slug='vanilla-extract',
            substitute__slug='vanilla-aroma').exists())
        self.assertIn('removed=', out.getvalue())

    def test_pruning_spares_hand_made_rows(self):
        """Only rows this table owns may be pruned. A preference/dietary swap
        is not in the YAML by design and must survive every load."""
        hand_made = IngredientSubstitute.objects.create(
            ingredient=CanonicalIngredient.objects.get(slug='vanilla-extract'),
            substitute=CanonicalIngredient.objects.get(slug='vanilla-sugar'))
        call_command('load_availability_substitutions', stdout=StringIO())
        self.assertTrue(IngredientSubstitute.objects.filter(pk=hand_made.pk).exists())

    def test_unknown_slug_fails_loudly(self):
        """A typo in the table must not silently skip a swap."""
        import os
        import tempfile
        from django.core.management.base import CommandError
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False,
                                         encoding='utf-8') as fh:
            fh.write("- ingredient: no-such-slug\n  substitute: vanilla-aroma\n")
            path = fh.name
        try:
            with self.assertRaises(CommandError) as ctx:
                call_command('load_availability_substitutions', f'--path={path}',
                             stdout=StringIO())
            self.assertIn('no-such-slug', str(ctx.exception))
        finally:
            os.unlink(path)

    def test_swap_target_must_be_obtainable(self):
        """Swapping one unbuyable ingredient for another is pointless.

        Only enforced once the target carries a rating — an unrated target is
        something we cannot judge, not something known to be bad.
        """
        import os
        import tempfile
        from django.core.management.base import CommandError
        call_command('rate_ingredient_availability', stdout=StringIO())
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False,
                                         encoding='utf-8') as fh:
            fh.write("- ingredient: maple-syrup\n  substitute: tahini\n")
            path = fh.name
        try:
            with self.assertRaises(CommandError) as ctx:
                call_command('load_availability_substitutions', f'--path={path}',
                             stdout=StringIO())
            self.assertIn('tahini', str(ctx.exception))
        finally:
            os.unlink(path)

    def test_shipped_table_targets_are_all_common(self):
        """Guards the real data file: every swap must land on a one-stop item."""
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        for row in IngredientSubstitute.objects.filter(
                purpose=IngredientSubstitute.Purpose.AVAILABILITY):
            self.assertEqual(
                row.substitute.availability, 'common',
                f'{row.ingredient.slug} -> {row.substitute.slug} lands on a '
                f'{row.substitute.availability} ingredient')


def _recipe(**kw):
    defaults = dict(
        slug='test-recipe', name_cs='Testovací recept',
        meal_types=['dinner'], ingredients=[], instructions=[],
        base_servings=2, source_url='https://example.com/r',
        source_name='Example', status=CuratedRecipe.Status.PUBLISHED,
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class PlanSubstitutionsTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        from diet_planner.services.ingredient_substitution import substitution_table
        self.table = substitution_table()

    def test_fully_covered_recipe_is_saveable(self):
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertTrue(plan.saveable)
        self.assertEqual(len(plan.changes), 1)
        change = plan.changes[0]
        self.assertEqual(change.old_name, 'vanilkový extrakt')
        self.assertEqual(change.new_name, 'vanilkové aroma')
        self.assertEqual(change.new_canonical, 'vanilla-aroma')
        self.assertEqual(change.new_unit, 'ml')

    def test_uncovered_specialty_blocks_the_whole_plan(self):
        """A specialty item we cannot swap leaves the recipe unservable — change
        nothing, because retrieval gates the recipe out either way."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'list'},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertFalse(plan.saveable)
        self.assertEqual(plan.blocking, ['nori'])
        self.assertEqual(plan.changes, [])

    def test_uncovered_findable_does_not_block_a_specialty_rescue(self):
        """`findable` is 'bigger shop', not 'unbuyable', and retrieval never
        gates it. Refusing the rescue over one leaves the recipe invisible for
        no gain — the swap still happens, the findable item is reported."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'tahini', 'canonical': 'tahini', 'quantity': 30, 'unit': 'g'},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertTrue(plan.saveable)
        self.assertEqual(plan.blocking, [])
        self.assertEqual(plan.uncovered, ['tahini'])
        self.assertEqual(len(plan.changes), 1)
        self.assertEqual(plan.changes[0].new_canonical, 'vanilla-aroma')

    def test_common_recipe_needs_no_plan(self):
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'}])
        plan = plan_substitutions(r, self.table)
        self.assertFalse(plan.saveable)
        self.assertEqual(plan.changes, [])
        self.assertEqual(plan.uncovered, [])

    def test_conversion_factor_scales_quantity(self):
        from diet_planner.services.ingredient_substitution import (
            SubstitutionRule, plan_substitutions,
        )
        table = {'vanilla-extract': SubstitutionRule(
            old_slug='vanilla-extract', new_slug='vanilla-aroma',
            new_name='vanilkové aroma', conversion_factor=2.0,
            new_unit='ml', quality_score=0.9)}
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 3, 'unit': 'lžička'}])
        plan = plan_substitutions(r, table)
        self.assertEqual(plan.changes[0].new_quantity, 6.0)

    def test_stale_catalog_id_is_dropped(self):
        """catalog_id points at a StoreProduct for the OLD ingredient."""
        from diet_planner.services.ingredient_substitution import (
            apply_changes_to_ingredients, plan_substitutions,
        )
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička', 'catalog_id': 4242}])
        plan = plan_substitutions(r, self.table)
        rewritten = apply_changes_to_ingredients(r.ingredients, plan)
        self.assertNotIn('catalog_id', rewritten[0])
        self.assertEqual(rewritten[0]['canonical'], 'vanilla-aroma')
        self.assertEqual(rewritten[0]['name'], 'vanilkové aroma')

    def test_apply_does_not_mutate_the_input(self):
        """The caller snapshots the original — it must not be aliased."""
        from diet_planner.services.ingredient_substitution import (
            apply_changes_to_ingredients, plan_substitutions,
        )
        original = [{'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
                     'quantity': 1, 'unit': 'lžička'}]
        r = _recipe(ingredients=original)
        plan = plan_substitutions(r, self.table)
        apply_changes_to_ingredients(original, plan)
        self.assertEqual(original[0]['canonical'], 'vanilla-extract')
        self.assertEqual(original[0]['name'], 'vanilkový extrakt')

    def test_gluten_free_recipe_refuses_gluten_bearing_swap(self):
        """tamari -> soy sauce silently breaks a gluten_free promise."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(dietary_tags=['gluten_free'], ingredients=[
            {'name': 'tamari', 'canonical': 'tamari', 'quantity': 20, 'unit': 'ml'}])
        plan = plan_substitutions(r, self.table)
        self.assertFalse(plan.saveable)
        self.assertEqual(plan.uncovered, ['tamari'])

    def test_vegan_recipe_refuses_honey_swap(self):
        """maple-syrup -> med is fine generally, never in a vegan recipe."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(dietary_tags=['vegan'], ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 30, 'unit': 'ml'}])
        plan = plan_substitutions(r, self.table)
        self.assertFalse(plan.saveable)
        self.assertEqual(plan.uncovered, ['maple-syrup'])

    def test_non_vegan_recipe_still_gets_the_honey_swap(self):
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 30, 'unit': 'ml'}])
        plan = plan_substitutions(r, self.table)
        self.assertTrue(plan.saveable)
        self.assertEqual(plan.changes[0].new_canonical, 'honey')

    def test_optional_ingredients_are_ignored(self):
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
            {'name': 'tahini', 'canonical': 'tahini', 'quantity': 30,
             'unit': 'g', 'optional': True},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertEqual(plan.uncovered, [])

    def test_summary_reads_as_the_adaptation_note(self):
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'}])
        plan = plan_substitutions(r, self.table)
        self.assertEqual(plan.summary(), 'vanilkový extrakt → vanilkové aroma')

    def test_string_ingredients_do_not_crash(self):
        """Older corpus rows store bare strings instead of dicts."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=['vanilkový extrakt', {'name': 'sůl',
                                                       'canonical': 'salt'}])
        plan = plan_substitutions(r, self.table)
        self.assertEqual(plan.changes, [])


class OptionalIngredientSwapTests(TestCase):
    """Optional lines were skipped entirely, so an adapted recipe could keep
    listing the very item it claims to have replaced.

    Measured on prod 2026-08-25: `ovesne-livance` still listed
    'avokádový olej na pánev' — a SPECIALTY item — after adaptation.

    Optional entries must never enter the gating calculus (they cannot sink a
    plan), but once a recipe is being adapted anyway they must be swapped too.
    """

    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        from diet_planner.services.ingredient_substitution import substitution_table
        self.table = substitution_table()

    def test_optional_entry_is_swapped_when_the_recipe_is_adapted_anyway(self):
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'javorový sirup na podávání', 'canonical': 'maple-syrup',
             'quantity': 30, 'unit': 'ml', 'optional': True},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertTrue(plan.saveable)
        self.assertEqual(len(plan.optional_changes), 1)
        self.assertEqual(plan.optional_changes[0].new_canonical, 'honey')
        self.assertEqual(plan.optional_changes[0].index, 1)

    def test_optional_entry_never_blocks_a_plan(self):
        """A specialty optional item must not gate the recipe out."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2,
             'unit': 'list', 'optional': True},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertTrue(plan.saveable)
        self.assertEqual(plan.blocking, [])
        self.assertEqual(plan.uncovered, [])

    def test_optional_only_recipe_is_not_adapted(self):
        """Never rewrite a credited recipe just for a garnish: an optional swap
        is a passenger on a real rescue, not a reason to start one."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 30, 'unit': 'ml', 'optional': True},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertFalse(plan.saveable)
        self.assertEqual(plan.optional_changes, [])

    def test_apply_changes_swaps_optional_entries_too(self):
        from diet_planner.services.ingredient_substitution import (
            apply_changes_to_ingredients, plan_substitutions,
        )
        ingredients = [
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'javorový sirup na podávání', 'canonical': 'maple-syrup',
             'quantity': 30, 'unit': 'ml', 'optional': True},
        ]
        r = _recipe(ingredients=ingredients)
        plan = plan_substitutions(r, self.table)
        out = apply_changes_to_ingredients(ingredients, plan)
        self.assertEqual(out[1]['canonical'], 'honey')
        self.assertTrue(out[1]['optional'], 'optional flag must survive')
        self.assertEqual(ingredients[1]['canonical'], 'maple-syrup',
                         'input must not be mutated')

    def test_summary_discloses_optional_swaps_too(self):
        """The note is what the reader — and any later audit — is told."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'javorový sirup na podávání', 'canonical': 'maple-syrup',
             'quantity': 30, 'unit': 'ml', 'optional': True},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertEqual(
            plan.summary(),
            'vanilkový extrakt → vanilkové aroma, '
            'javorový sirup na podávání → med')


class DiffAppliedChangesTests(TestCase):
    """Reconstructing the swaps a row already carries, from its own snapshot."""

    def test_reports_a_renamed_entry_with_its_index(self):
        original = [
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 2, 'unit': 'lžíce'},
        ]
        current = [
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
            {'name': 'med', 'canonical': 'honey', 'quantity': 2, 'unit': 'lžíce'},
        ]
        changes = diff_applied_changes(original, current)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].index, 1)
        self.assertEqual(changes[0].old_name, 'javorový sirup')
        self.assertEqual(changes[0].old_slug, 'maple-syrup')
        self.assertEqual(changes[0].new_name, 'med')
        self.assertEqual(changes[0].new_canonical, 'honey')
        self.assertEqual(changes[0].new_quantity, 2)
        self.assertEqual(changes[0].new_unit, 'lžíce')

    def test_ignores_entries_whose_name_did_not_change(self):
        original = [{'name': 'sůl', 'canonical': 'salt'}]
        current = [{'name': 'sůl', 'canonical': 'salt'}]
        self.assertEqual(diff_applied_changes(original, current), [])

    def test_length_mismatch_yields_nothing_rather_than_guessing(self):
        # Misaligned lists cannot be diffed positionally; refusing beats
        # inventing a swap between two unrelated ingredients.
        self.assertEqual(
            diff_applied_changes(
                [{'name': 'a'}, {'name': 'b'}], [{'name': 'a'}]),
            [])

    def test_missing_snapshot_yields_nothing(self):
        self.assertEqual(diff_applied_changes(None, [{'name': 'med'}]), [])
        self.assertEqual(diff_applied_changes([], [{'name': 'med'}]), [])

    def test_skips_non_dict_entries(self):
        # Generated (non-corpus) meals carry bare strings.
        changes = diff_applied_changes(
            ['javorový sirup', {'name': 'sůl', 'canonical': 'salt'}],
            ['med', {'name': 'sůl', 'canonical': 'salt'}])
        self.assertEqual(changes, [])

    def test_blank_name_on_either_side_is_not_a_swap(self):
        self.assertEqual(
            diff_applied_changes([{'name': ''}], [{'name': 'med'}]), [])
        self.assertEqual(
            diff_applied_changes([{'name': 'med'}], [{'name': ''}]), [])


class DisclosedSwapsTests(TestCase):
    """Which (old -> new) pairs a row has already published."""

    def test_reads_pairs_out_of_the_note(self):
        note = ('Upraveno pro dostupnost v českých obchodech: '
                'javorový sirup → med, avokádový olej → řepkový olej')
        self.assertEqual(
            disclosed_swaps(note, []),
            {('javorový sirup', 'med'), ('avokádový olej', 'řepkový olej')})

    def test_reads_pairs_out_of_the_applied_diff(self):
        changes = [IngredientChange(
            index=0, old_name='javorový sirup', old_slug='maple-syrup',
            new_name='med', new_canonical='honey',
            new_quantity=2, new_unit='lžíce')]
        self.assertEqual(
            disclosed_swaps('', changes), {('javorový sirup', 'med')})

    def test_comparison_is_case_insensitive(self):
        # The note preserves whatever case the rule carried: prod holds
        # 'avokádový olej → Řepkový olej' with a capitalised replacement.
        note = 'Upraveno pro dostupnost v českých obchodech: Javorový Sirup → Med'
        self.assertIn(('javorový sirup', 'med'), disclosed_swaps(note, []))

    def test_empty_note_and_no_changes_disclose_nothing(self):
        self.assertEqual(disclosed_swaps('', []), set())

    def test_note_without_the_prefix_is_still_parsed(self):
        self.assertEqual(
            disclosed_swaps('javorový sirup → med', []),
            {('javorový sirup', 'med')})

    def test_chunk_without_an_arrow_is_skipped(self):
        self.assertEqual(disclosed_swaps('nějaká poznámka', []), set())

    def test_unions_both_sources(self):
        # The reason this function takes two arguments: a row can carry a swap
        # in its note and another in its ingredients, and both are disclosed.
        note = ('Upraveno pro dostupnost v českých obchodech: '
                'javorový sirup → med')
        changes = [IngredientChange(
            index=0, old_name='tamari', old_slug='tamari',
            new_name='sójová omáčka', new_canonical='soy-sauce',
            new_quantity=1, new_unit='lžíce')]
        self.assertEqual(
            disclosed_swaps(note, changes),
            {('javorový sirup', 'med'), ('tamari', 'sójová omáčka')})
