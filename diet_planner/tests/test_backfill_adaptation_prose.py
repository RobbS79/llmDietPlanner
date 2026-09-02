"""The backfill command: reach, disclosure guard, prose repair, judge gate."""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.substitution_rewrite import RewriteError

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


class ProseRepairTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        judge = mock.patch(
            f'{CMD}.judge_curated_recipe',
            return_value={'ran': True, 'verdict': 'coherent',
                          'high_severity_count': 0})
        judge.start()
        self.addCleanup(judge.stop)

    def test_rewrites_a_title_and_description_the_swap_made_false(self):
        recipe = _adapted()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny',
                                      'Muffiny slazené medem.')) as prose:
            call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Medové muffiny')
        self.assertEqual(recipe.description, 'Muffiny slazené medem.')
        # The reconstructed plan is what the rewriter was handed.
        plan = prose.call_args.args[2]
        self.assertEqual(
            [(c.old_name, c.new_name) for c in plan.changes],
            [('javorový sirup', 'med')])

    def test_leaves_the_slug_alone_even_when_the_name_changes(self):
        recipe = _adapted()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny', 'Muffiny s medem.')):
            call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        self.assertEqual(recipe.slug, 'javorove-muffiny')

    def test_a_clean_row_is_left_completely_alone(self):
        recipe = _adapted(name_cs='Medové muffiny',
                          description='Muffiny slazené medem.')
        before = recipe.updated_at
        out = StringIO()
        with mock.patch(f'{CMD}.rewrite_prose',
                        side_effect=lambda n, d, p: (n, d)):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.updated_at, before)
        self.assertIn('repaired=0', out.getvalue())

    def test_a_rewrite_error_leaves_the_row_untouched(self):
        recipe = _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.rewrite_prose',
                        side_effect=RewriteError('bad shape')):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Javorové muffiny')
        self.assertIn('failed=1', out.getvalue())

    def test_dry_run_writes_nothing(self):
        recipe = _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny', 'Muffiny s medem.')):
            call_command('backfill_adaptation_prose', '--dry-run', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Javorové muffiny')
        self.assertIn('[dry-run]', out.getvalue())
        self.assertIn('repaired=1', out.getvalue())


class JudgeGateTests(TestCase):
    """A rewrite the judge rejects must never reach the row."""

    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        prose = mock.patch(
            f'{CMD}.rewrite_prose',
            return_value=('Medové muffiny', 'Muffiny slazené medem.'))
        prose.start()
        self.addCleanup(prose.stop)

    def test_a_rejected_rewrite_is_discarded(self):
        recipe = _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.judge_curated_recipe',
                        return_value={'ran': True, 'verdict': 'incoherent',
                                      'high_severity_count': 2}):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Javorové muffiny')
        self.assertIn('failed=1', out.getvalue())

    def test_an_unavailable_judge_applies_and_says_so(self):
        recipe = _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.judge_curated_recipe',
                        return_value={'ran': False, 'error': 'no credit'}):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Medové muffiny')
        self.assertIn('unjudged=1', out.getvalue())
        self.assertIn('applying unjudged', out.getvalue())

    def test_skip_judge_never_calls_the_judge(self):
        _adapted()
        with mock.patch(f'{CMD}.judge_curated_recipe') as judge:
            call_command('backfill_adaptation_prose', '--skip-judge',
                         stdout=StringIO())
        judge.assert_not_called()

    def test_the_judge_sees_the_candidate_not_the_stored_row(self):
        recipe = _adapted()
        seen = {}

        def _judge(candidate):
            # Captured DURING the call: the stored row must still hold the old
            # prose at this point, or we are judging something already written.
            seen['candidate_name'] = candidate.name_cs
            seen['stored_name'] = CuratedRecipe.objects.get(
                pk=recipe.pk).name_cs
            return {'ran': True, 'verdict': 'coherent',
                    'high_severity_count': 0}

        with mock.patch(f'{CMD}.judge_curated_recipe', side_effect=_judge):
            call_command('backfill_adaptation_prose', stdout=StringIO())

        self.assertEqual(seen['candidate_name'], 'Medové muffiny')
        self.assertEqual(seen['stored_name'], 'Javorové muffiny')


class NoteAndIdempotenceTests(TestCase):
    """The note stays true to the food, and a second run is a no-op."""

    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        judge = mock.patch(
            f'{CMD}.judge_curated_recipe',
            return_value={'ran': True, 'verdict': 'coherent',
                          'high_severity_count': 0})
        judge.start()
        self.addCleanup(judge.stop)

    def test_the_note_is_left_alone_when_it_already_names_every_swap(self):
        recipe = _adapted()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny', 'Muffiny s medem.')):
            call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        self.assertEqual(recipe.adaptation_note, NOTE)

    def test_a_second_run_writes_nothing(self):
        recipe = _adapted()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny', 'Muffiny s medem.')):
            call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        after_first = recipe.updated_at

        out = StringIO()
        # Second run: the prose no longer leans on anything removed, so the
        # real rewrite_prose returns it untouched without an LLM call.
        with mock.patch(f'{CMD}.rewrite_prose',
                        side_effect=lambda n, d, p: (n, d)):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.updated_at, after_first)
        self.assertIn('repaired=0', out.getvalue())

    def test_an_unusable_snapshot_is_skipped_not_crashed_on(self):
        _adapted(slug='rozbity', original_ingredients=[{'name': 'jen jedna'}])
        out = StringIO()
        call_command('backfill_adaptation_prose', stdout=out)
        self.assertIn('repaired=0', out.getvalue())

    def test_the_note_is_extended_when_it_omits_an_applied_swap(self):
        """The guard's only real case: a note that under-discloses.

        `adaptation_note` truncates at 300 chars, so a row carrying many swaps
        can hold food its note never names. The prose then describes an
        ingredient the disclosure does not account for.
        """
        recipe = _adapted(
            slug='zkraceny-zapis',
            original_ingredients=[
                {'name': 'javorový sirup', 'canonical': 'maple-syrup',
                 'quantity': 2, 'unit': 'lžíce'},
                {'name': 'pekanové ořechy', 'canonical': 'pecans',
                 'quantity': 50, 'unit': 'g'},
            ],
            ingredients=[
                {'name': 'med', 'canonical': 'honey',
                 'quantity': 2, 'unit': 'lžíce'},
                {'name': 'vlašské ořechy', 'canonical': 'walnuts',
                 'quantity': 50, 'unit': 'g'},
            ],
        )
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny',
                                      'Muffiny s medem a vlašskými ořechy.')):
            call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        self.assertIn('javorový sirup → med', recipe.adaptation_note)
        self.assertIn('pekanové ořechy → vlašské ořechy',
                      recipe.adaptation_note)
