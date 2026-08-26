"""The backfill command: reach, disclosure guard, prose repair, judge gate."""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe

CMD = 'diet_planner.management.commands.backfill_adaptation_prose'
NOTE = ('Upraveno pro dostupnost v českých obchodech: '
        'javorový sirup → med')


def _adapted(**kw):
    """A row the rescue already touched: ingredients swapped, prose stale."""
    defaults = dict(
        slug='javorove-muffiny', name_cs='Javorové muffiny',
        description='Muffiny slazené javorovým sirupem.',
        meal_types=['snack'], base_servings=4,
        source_url='https://example.com/r', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
        adaptation_note=NOTE,
        original_ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
        ],
        ingredients=[
            {'name': 'med', 'canonical': 'honey', 'quantity': 2, 'unit': 'lžíce'},
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
        ],
        instructions=[{'text': 'Přidejte med.', 'time_min': 1}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class ReachTests(TestCase):
    """The command's whole reason to exist: it sees rows the rescue cannot."""

    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())

    def test_reaches_an_already_adapted_row(self):
        _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny',
                                      'Muffiny slazené medem.')), \
             mock.patch(f'{CMD}.judge_curated_recipe',
                        return_value={'ran': True, 'verdict': 'coherent',
                                      'high_severity_count': 0}):
            call_command('backfill_adaptation_prose', stdout=out)
        self.assertIn('repaired=1', out.getvalue())

    def test_ignores_a_row_that_was_never_adapted(self):
        _adapted(slug='netknuty', adaptation_note='', original_ingredients=[])
        out = StringIO()
        call_command('backfill_adaptation_prose', stdout=out)
        self.assertIn('repaired=0', out.getvalue())


class OptionalLineTests(TestCase):
    """Optional entries the rescue skipped, finished only where disclosed."""

    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        # These tests are about the ingredient line, not the prose.
        prose = mock.patch(
            f'{CMD}.rewrite_prose',
            side_effect=lambda name, description, plan: (name, description))
        prose.start()
        self.addCleanup(prose.stop)
        judge = mock.patch(
            f'{CMD}.judge_curated_recipe',
            return_value={'ran': True, 'verdict': 'coherent',
                          'high_severity_count': 0})
        judge.start()
        self.addCleanup(judge.stop)

    def test_applies_an_optional_swap_the_row_already_disclosed(self):
        recipe = _adapted(ingredients=[
            {'name': 'med', 'canonical': 'honey',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 1, 'unit': 'lžíce', 'optional': True},
        ], original_ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 1, 'unit': 'lžíce', 'optional': True},
        ])
        call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        self.assertEqual(recipe.ingredients[1]['name'], 'med')
        self.assertEqual(recipe.ingredients[1]['canonical'], 'honey')
        # Still optional: repairing the name must not change its standing.
        self.assertTrue(recipe.ingredients[1]['optional'])

    def test_refuses_an_optional_swap_the_row_never_disclosed(self):
        # The note says nothing about vanilla, and no required entry swapped
        # it. Swapping it here would be a fresh editorial change to someone
        # else's credited recipe.
        recipe = _adapted(ingredients=[
            {'name': 'med', 'canonical': 'honey',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička', 'optional': True},
        ], original_ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička', 'optional': True},
        ])
        out = StringIO()
        call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.ingredients[1]['name'], 'vanilkový extrakt')
        self.assertIn('undisclosed', out.getvalue())
