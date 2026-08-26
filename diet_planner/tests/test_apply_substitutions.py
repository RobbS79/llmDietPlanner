"""The substitution command: dry-run, judge gate, snapshot, rollup refresh."""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(**kw):
    defaults = dict(
        slug='vanilkovy-kolac', name_cs='Vanilkový koláč',
        meal_types=['snack'], base_servings=4,
        source_url='https://example.com/r', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
        ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
        ],
        instructions=[{'text': 'Přidejte vanilkový extrakt.', 'time_min': 1}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class ApplySubstitutionsTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        # These tests are about the ingredient swap, not the prose. Hold name
        # and description still class-wide: unpatched, the command's prose
        # rewrite reaches for a live LLM and the RewriteError skips the recipe,
        # so every swap assertion below would fail for an unrelated reason.
        # ProseIsAdaptedTests covers the prose path properly.
        prose = mock.patch(
            'diet_planner.management.commands.apply_availability_substitutions'
            '.rewrite_prose',
            side_effect=lambda name, description, plan: (name, description))
        prose.start()
        self.addCleanup(prose.stop)

    def _patched(self, verdict=None):
        """judge_curated_recipe returns JudgeVerdict.as_stats() — there is no
        'passed' key, so the gate reads `ran` + `verdict` + high severity."""
        if verdict is None:
            verdict = {'ran': True, 'verdict': 'coherent', 'high_severity_count': 0}
        return (
            mock.patch(
                'diet_planner.management.commands.apply_availability_substitutions'
                '.rewrite_instructions',
                return_value=[{'text': 'Přidejte vanilkové aroma.', 'time_min': 1}]),
            mock.patch(
                'diet_planner.management.commands.apply_availability_substitutions'
                '.judge_curated_recipe',
                return_value=verdict),
        )

    def test_dry_run_writes_nothing(self):
        r = _recipe()
        rewrite, judge = self._patched()
        out = StringIO()
        with rewrite, judge:
            call_command('apply_availability_substitutions', '--dry-run', stdout=out)
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-extract')
        self.assertEqual(r.adaptation_note, '')
        self.assertIn('vanilkový extrakt', out.getvalue())

    def test_applies_and_snapshots(self):
        r = _recipe()
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-aroma')
        self.assertEqual(r.ingredients[0]['name'], 'vanilkové aroma')
        self.assertEqual(r.instructions[0]['text'], 'Přidejte vanilkové aroma.')
        self.assertIn('vanilkový extrakt', r.adaptation_note)
        self.assertEqual(
            r.original_ingredients[0]['canonical'], 'vanilla-extract',
            "the source author's original must be preserved")

    def test_rollup_is_recomputed(self):
        r = _recipe()
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, 'common')
        self.assertEqual(r.shopping_blockers, [])

    def test_judge_rejection_discards_the_whole_rewrite(self):
        r = _recipe()
        rewrite, judge = self._patched(
            verdict={'ran': True, 'verdict': 'incoherent', 'high_severity_count': 0})
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-extract')
        self.assertEqual(r.instructions[0]['text'], 'Přidejte vanilkový extrakt.')
        self.assertEqual(r.adaptation_note, '')

    def test_high_severity_issue_discards_the_whole_rewrite(self):
        """'minor_issues' with a high-severity issue is still a rejection."""
        r = _recipe()
        rewrite, judge = self._patched(
            verdict={'ran': True, 'verdict': 'minor_issues', 'high_severity_count': 1})
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-extract')
        self.assertEqual(r.adaptation_note, '')

    def test_judge_that_did_not_run_fails_open_but_says_so(self):
        """ran=False means UNKNOWN, not good. We still apply — the judge is
        advisory here as everywhere — but the operator must see it in the batch
        output, or a whole prod run could pass unjudged and look clean."""
        r = _recipe()
        rewrite, judge = self._patched(
            verdict={'ran': False, 'verdict': 'unknown', 'error': 'no api key'})
        out = StringIO()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=out)
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-aroma')
        self.assertIn('judge did not run', out.getvalue())

    def test_rewrite_error_discards_the_whole_rewrite(self):
        from diet_planner.services.substitution_rewrite import RewriteError
        r = _recipe()
        with mock.patch(
            'diet_planner.management.commands.apply_availability_substitutions'
            '.rewrite_instructions', side_effect=RewriteError('bad shape'),
        ):
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-extract')
        self.assertEqual(r.adaptation_note, '')

    def test_uncovered_recipe_is_left_alone(self):
        r = _recipe(slug='tahini-dressing', ingredients=[
            {'name': 'tahini', 'canonical': 'tahini', 'quantity': 30, 'unit': 'g'}],
            instructions=[{'text': 'Rozmíchejte tahini.'}])
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'tahini')

    def test_tier_specialty_only_touches_gated_recipes(self):
        """Staging control for the prod run: `findable` recipes are servable
        today, so a first pass should edit only what retrieval gates out."""
        gated = _recipe(slug='vanilkovy-kolac')
        findable = _recipe(
            slug='javorove-lividance',
            ingredients=[{'name': 'javorový sirup', 'canonical': 'maple-syrup',
                          'quantity': 50, 'unit': 'ml'}],
            instructions=[{'text': 'Polijte javorovým sirupem.'}])
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', '--tier=specialty',
                         stdout=StringIO())
        gated.refresh_from_db()
        findable.refresh_from_db()
        self.assertEqual(gated.ingredients[0]['canonical'], 'vanilla-aroma')
        self.assertEqual(findable.ingredients[0]['canonical'], 'maple-syrup')

    def test_skip_names_the_specialty_item_that_blocked_it(self):
        """The skip line must name the fatal item, not every findable one, or
        the operator reads the run as blocked by things that cost nothing."""
        _recipe(slug='sushi-miska', ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'list'},
            {'name': 'tahini', 'canonical': 'tahini', 'quantity': 30, 'unit': 'g'},
        ], instructions=[{'text': 'Zabalte do nori.'}])
        rewrite, judge = self._patched()
        out = StringIO()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=out)
        line = [ln for ln in out.getvalue().splitlines() if 'skip' in ln]
        self.assertTrue(line, 'no skip line was printed')
        self.assertIn('nori', line[0])
        self.assertNotIn('tahini', line[0])

    def test_limit_bounds_the_batch(self):
        for n in range(3):
            _recipe(slug=f'kolac-{n}')
        rewrite, judge = self._patched()
        out = StringIO()
        with rewrite, judge:
            call_command('apply_availability_substitutions', '--limit=2', stdout=out)
        changed = CuratedRecipe.objects.exclude(adaptation_note='').count()
        self.assertEqual(changed, 2)

    def test_already_adapted_recipe_is_not_reprocessed(self):
        r = _recipe(adaptation_note='Upraveno pro dostupnost: x → y')
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.adaptation_note, 'Upraveno pro dostupnost: x → y')

    def test_slug_targets_one_recipe(self):
        target = _recipe(slug='kolac-a')
        other = _recipe(slug='kolac-b')
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', '--slug=kolac-a',
                         stdout=StringIO())
        target.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(target.ingredients[0]['canonical'], 'vanilla-aroma')
        self.assertEqual(other.ingredients[0]['canonical'], 'vanilla-extract')


class UnpublishUnshoppableTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())

    def test_specialty_published_becomes_draft(self):
        r = _recipe(slug='sushi-miska', ingredients=[
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'ks'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, 'specialty')

        out = StringIO()
        call_command('unpublish_unshoppable', stdout=out)
        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.DRAFT)
        self.assertIn('sushi-miska', out.getvalue())

    def test_findable_recipe_stays_published(self):
        """Only specialty is demoted; findable is a bigger-shop trip, not a wall."""
        r = _recipe(slug='findable-dish', ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 30, 'unit': 'ml'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        call_command('unpublish_unshoppable', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.PUBLISHED)

    def test_nothing_is_deleted(self):
        _recipe(slug='sushi-miska', ingredients=[
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'ks'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        call_command('unpublish_unshoppable', stdout=StringIO())
        self.assertTrue(CuratedRecipe.objects.filter(slug='sushi-miska').exists())

    def test_dry_run_writes_nothing(self):
        r = _recipe(slug='sushi-miska', ingredients=[
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'ks'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        call_command('unpublish_unshoppable', '--dry-run', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.PUBLISHED)

    def test_blockers_are_reported_so_the_demotion_is_reviewable(self):
        """Draft, never delete — the printed reason is how a later table finds
        these again."""
        _recipe(slug='sushi-miska', ingredients=[
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'ks'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        out = StringIO()
        call_command('unpublish_unshoppable', stdout=out)
        self.assertIn('nori', out.getvalue())

    def test_already_draft_specialty_is_not_recounted(self):
        _recipe(slug='sushi-draft', status=CuratedRecipe.Status.DRAFT, ingredients=[
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'ks'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        out = StringIO()
        call_command('unpublish_unshoppable', stdout=out)
        self.assertIn('demoted=0', out.getvalue())


class ProseIsAdaptedTests(TestCase):
    """The command rewrote ingredients and steps but left the prose claiming
    the old ingredient — 10 published recipes on prod said so, 2 in the title.
    """

    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())

    def _patched(self, prose=('Koláč s aroma', 'Koláč s vanilkovým aroma.')):
        return (
            mock.patch(
                'diet_planner.management.commands.apply_availability_substitutions'
                '.rewrite_instructions',
                return_value=[{'text': 'Přidejte vanilkové aroma.', 'time_min': 1}]),
            mock.patch(
                'diet_planner.management.commands.apply_availability_substitutions'
                '.rewrite_prose', return_value=prose),
            mock.patch(
                'diet_planner.management.commands.apply_availability_substitutions'
                '.judge_curated_recipe',
                return_value={'ran': True, 'verdict': 'coherent',
                              'high_severity_count': 0}),
        )

    def test_name_and_description_are_saved(self):
        r = _recipe(name_cs='Koláč s vanilkovým extraktem',
                    description='Koláč s vanilkovým extraktem.')
        rewrite, prose, judge = self._patched()
        with rewrite, prose, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.name_cs, 'Koláč s aroma')
        self.assertEqual(r.description, 'Koláč s vanilkovým aroma.')

    def test_slug_never_changes(self):
        """URLs are public; the title is what the reader sees."""
        r = _recipe(name_cs='Koláč s vanilkovým extraktem',
                    description='Koláč s vanilkovým extraktem.')
        rewrite, prose, judge = self._patched()
        with rewrite, prose, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.slug, 'vanilkovy-kolac')

    def test_prose_rewrite_failure_discards_the_whole_adaptation(self):
        """Half-adapted is worse than unadapted — same contract as steps."""
        from diet_planner.services.substitution_rewrite import RewriteError
        r = _recipe(name_cs='Koláč s vanilkovým extraktem',
                    description='Koláč s vanilkovým extraktem.')
        rewrite, _prose, judge = self._patched()
        boom = mock.patch(
            'diet_planner.management.commands.apply_availability_substitutions'
            '.rewrite_prose', side_effect=RewriteError('nope'))
        with rewrite, boom, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.adaptation_note, '')
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-extract')
        self.assertEqual(r.name_cs, 'Koláč s vanilkovým extraktem')

    def test_judge_sees_the_rewritten_prose(self):
        """The judge must score what we intend to save, not the stale title."""
        r = _recipe(name_cs='Koláč s vanilkovým extraktem',
                    description='Koláč s vanilkovým extraktem.')
        seen = {}

        def capture(candidate):
            seen['name'] = candidate.name_cs
            seen['description'] = candidate.description
            return {'ran': True, 'verdict': 'coherent', 'high_severity_count': 0}

        rewrite, prose, _judge = self._patched()
        with rewrite, prose, mock.patch(
            'diet_planner.management.commands.apply_availability_substitutions'
            '.judge_curated_recipe', side_effect=capture,
        ):
            call_command('apply_availability_substitutions', stdout=StringIO())
        self.assertEqual(seen['name'], 'Koláč s aroma')
        self.assertEqual(seen['description'], 'Koláč s vanilkovým aroma.')
