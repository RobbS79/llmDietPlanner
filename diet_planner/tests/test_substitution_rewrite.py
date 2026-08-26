"""The LLM instruction rewrite: bounded, fail-closed, no silent regeneration."""
import json

from django.test import TestCase

from diet_planner.services.ingredient_substitution import IngredientChange, SubstitutionPlan


def _plan():
    return SubstitutionPlan(saveable=True, changes=[IngredientChange(
        index=0, old_name='vanilkový extrakt', old_slug='vanilla-extract',
        new_name='vanilkové aroma', new_canonical='vanilla-aroma',
        new_quantity=1.0, new_unit='ml')])


def _maple_plan():
    return SubstitutionPlan(saveable=True, changes=[IngredientChange(
        index=0, old_name='javorový sirup', old_slug='maple-syrup',
        new_name='med', new_canonical='honey',
        new_quantity=60.0, new_unit='ml')])


class RewriteInstructionsTests(TestCase):
    def test_only_affected_steps_are_sent_to_the_llm(self):
        from diet_planner.services.substitution_rewrite import rewrite_instructions
        steps = [
            {'text': 'Smíchejte mouku a cukr.', 'time_min': 2},
            {'text': 'Přidejte vanilkový extrakt.', 'time_min': 1},
        ]
        seen = {}

        def fake_generate(prompt):
            seen['prompt'] = prompt
            return json.dumps({'steps': [
                {'text': 'Přidejte vanilkové aroma.', 'time_min': 1}]})

        out = rewrite_instructions(steps, _plan(), generate=fake_generate)
        self.assertEqual(out[0]['text'], 'Smíchejte mouku a cukr.')
        self.assertEqual(out[1]['text'], 'Přidejte vanilkové aroma.')
        self.assertIn('vanilkový extrakt', seen['prompt'])
        self.assertNotIn('Smíchejte mouku a cukr', seen['prompt'],
                         "unaffected step must not be sent for regeneration")

    def test_no_affected_step_skips_the_llm_entirely(self):
        from diet_planner.services.substitution_rewrite import rewrite_instructions
        steps = [{'text': 'Smíchejte mouku a cukr.', 'time_min': 2}]

        def explode(prompt):
            raise AssertionError('LLM must not be called')

        out = rewrite_instructions(steps, _plan(), generate=explode)
        self.assertEqual(out, steps)

    def test_step_count_mismatch_fails_closed(self):
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_instructions,
        )
        steps = [{'text': 'Přidejte vanilkový extrakt.', 'time_min': 1}]

        def bad_generate(prompt):
            return json.dumps({'steps': [{'text': 'a'}, {'text': 'b'}]})

        with self.assertRaises(RewriteError):
            rewrite_instructions(steps, _plan(), generate=bad_generate)

    def test_llm_error_fails_closed(self):
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_instructions,
        )
        steps = [{'text': 'Přidejte vanilkový extrakt.', 'time_min': 1}]

        def bad_generate(prompt):
            raise RuntimeError('gemini 503')

        with self.assertRaises(RewriteError):
            rewrite_instructions(steps, _plan(), generate=bad_generate)

    def test_old_ingredient_left_in_output_fails_closed(self):
        """The whole point is removing the name — a passthrough is a failure."""
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_instructions,
        )
        steps = [{'text': 'Přidejte vanilkový extrakt.', 'time_min': 1}]

        def lazy_generate(prompt):
            return json.dumps({'steps': [{'text': 'Přidejte vanilkový extrakt.'}]})

        with self.assertRaises(RewriteError):
            rewrite_instructions(steps, _plan(), generate=lazy_generate)

    def test_preserves_tip_and_time_when_llm_omits_them(self):
        from diet_planner.services.substitution_rewrite import rewrite_instructions
        steps = [{'text': 'Přidejte vanilkový extrakt.', 'time_min': 3, 'tip': 'Nemíchejte moc.'}]

        def terse_generate(prompt):
            return json.dumps({'steps': [{'text': 'Přidejte vanilkové aroma.'}]})

        out = rewrite_instructions(steps, _plan(), generate=terse_generate)
        self.assertEqual(out[0]['time_min'], 3)
        self.assertEqual(out[0]['tip'], 'Nemíchejte moc.')


class SharedHeadNounTests(TestCase):
    """avocado-oil -> rapeseed-oil keeps the noun 'olej' and changes only the
    adjective. Matching on any single word stem cannot tell those two apart."""

    def _oil_plan(self):
        return SubstitutionPlan(saveable=True, changes=[IngredientChange(
            index=0, old_name='avokádový olej', old_slug='avocado-oil',
            new_name='řepkový olej', new_canonical='rapeseed-oil',
            new_quantity=15.0, new_unit='ml')])

    def test_unchanged_adjective_fails_closed(self):
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_instructions,
        )
        steps = [{'text': 'Rozehřejte avokádový olej na pánvi.', 'time_min': 2}]

        def lazy_generate(prompt):
            return json.dumps({'steps': [
                {'text': 'Rozehřejte avokádový olej na pánvi.'}]})

        with self.assertRaises(RewriteError):
            rewrite_instructions(steps, self._oil_plan(), generate=lazy_generate)

    def test_swapped_adjective_is_accepted(self):
        from diet_planner.services.substitution_rewrite import rewrite_instructions
        steps = [{'text': 'Rozehřejte avokádový olej na pánvi.', 'time_min': 2}]

        def good_generate(prompt):
            return json.dumps({'steps': [
                {'text': 'Rozehřejte řepkový olej na pánvi.'}]})

        out = rewrite_instructions(steps, self._oil_plan(), generate=good_generate)
        self.assertEqual(out[0]['text'], 'Rozehřejte řepkový olej na pánvi.')


class StringStepTests(TestCase):
    def test_plain_string_steps_are_handled(self):
        """Older corpus rows store instructions as bare strings."""
        from diet_planner.services.substitution_rewrite import rewrite_instructions
        steps = ['Přidejte vanilkový extrakt.']

        def fake_generate(prompt):
            return json.dumps({'steps': [{'text': 'Přidejte vanilkové aroma.'}]})

        out = rewrite_instructions(steps, _plan(), generate=fake_generate)
        self.assertEqual(out[0]['text'], 'Přidejte vanilkové aroma.')


class UsageAccountingTests(TestCase):
    """What the substitution run costs. An unknown cost must never read as
    zero cost, so unmetered calls are counted separately rather than folded
    into the token totals."""

    def setUp(self):
        from diet_planner.services.substitution_rewrite import reset_usage
        reset_usage()

    def test_reset_zeroes_every_counter(self):
        from diet_planner.services.substitution_rewrite import usage_snapshot
        self.assertEqual(
            usage_snapshot(),
            {'calls': 0, 'unmetered_calls': 0, 'prompt_tokens': 0,
             'output_tokens': 0, 'total_tokens': 0})

    def test_every_llm_attempt_is_counted(self):
        from diet_planner.services.substitution_rewrite import (
            rewrite_instructions, usage_snapshot)
        steps = [{'text': 'Přidejte vanilkový extrakt.'}]
        rewrite_instructions(steps, _plan(), generate=lambda p: json.dumps(
            {'steps': [{'text': 'Přidejte vanilkové aroma.'}]}))
        self.assertEqual(usage_snapshot()['calls'], 1)

    def test_skipped_llm_is_not_counted(self):
        """No affected step means no call, so it must not inflate the bill."""
        from diet_planner.services.substitution_rewrite import (
            rewrite_instructions, usage_snapshot)
        rewrite_instructions([{'text': 'Smíchejte mouku a cukr.'}], _plan(),
                             generate=lambda p: self.fail('must not be called'))
        self.assertEqual(usage_snapshot()['calls'], 0)

    def test_a_failed_rewrite_still_costs_and_is_counted(self):
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_instructions, usage_snapshot)
        with self.assertRaises(RewriteError):
            rewrite_instructions([{'text': 'Přidejte vanilkový extrakt.'}],
                                 _plan(), generate=lambda p: 'not json')
        self.assertEqual(usage_snapshot()['calls'], 1,
                         'tokens were spent even though the rewrite was discarded')

    def test_record_usage_accumulates_token_counts(self):
        from diet_planner.services.substitution_rewrite import (
            record_usage, usage_snapshot)

        class _Meta:
            prompt_token_count = 300
            candidates_token_count = 120
            total_token_count = 420

        class _Resp:
            usage_metadata = _Meta()

        record_usage(_Resp())
        record_usage(_Resp())
        snap = usage_snapshot()
        self.assertEqual(snap['prompt_tokens'], 600)
        self.assertEqual(snap['output_tokens'], 240)
        self.assertEqual(snap['total_tokens'], 840)
        self.assertEqual(snap['unmetered_calls'], 0)

    def test_missing_metadata_counts_as_unmetered_not_free(self):
        from diet_planner.services.substitution_rewrite import (
            record_usage, usage_snapshot)

        class _Resp:
            usage_metadata = None

        record_usage(_Resp())
        snap = usage_snapshot()
        self.assertEqual(snap['total_tokens'], 0)
        self.assertEqual(snap['unmetered_calls'], 1,
                         'a call with no usage metadata must be visible, not silent')


class RewriteProseTests(TestCase):
    """Name and description must not keep advertising a swapped-out ingredient.

    Found on prod 2026-08-25: 10 adapted recipes still promised the removed
    item in their description and 2 in their title — 'Ovesná kaše s javorovým
    sirupem a skořicí' contained no maple syrup at all.
    """

    def test_description_naming_the_old_ingredient_is_rewritten(self):
        from diet_planner.services.substitution_rewrite import rewrite_prose

        def fake_generate(prompt):
            return json.dumps({
                'name': 'Banánový chléb',
                'description': 'Vláčný banánový chléb oslazený pouze medem.',
            })

        name, description = rewrite_prose(
            'Banánový chléb',
            'Vláčný banánový chléb oslazený pouze javorovým sirupem.',
            _maple_plan(), generate=fake_generate)

        self.assertEqual(description,
                         'Vláčný banánový chléb oslazený pouze medem.')
        self.assertEqual(name, 'Banánový chléb')

    def test_name_naming_the_old_ingredient_is_rewritten(self):
        from diet_planner.services.substitution_rewrite import rewrite_prose

        def fake_generate(prompt):
            return json.dumps({
                'name': 'Ovesná kaše s medem a skořicí',
                'description': 'Krémová ovesná kaše.',
            })

        name, _ = rewrite_prose(
            'Ovesná kaše s javorovým sirupem a skořicí',
            'Krémová ovesná kaše.', _maple_plan(), generate=fake_generate)

        self.assertEqual(name, 'Ovesná kaše s medem a skořicí')

    def test_prose_that_never_mentions_the_swap_skips_the_llm(self):
        from diet_planner.services.substitution_rewrite import rewrite_prose

        def explode(prompt):
            raise AssertionError('LLM must not be called')

        name, description = rewrite_prose(
            'Banánový chléb', 'Vláčný a sladký banánový chléb.',
            _maple_plan(), generate=explode)

        self.assertEqual(name, 'Banánový chléb')
        self.assertEqual(description, 'Vláčný a sladký banánový chléb.')

    def test_result_still_naming_the_old_ingredient_fails_closed(self):
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_prose,
        )

        def lazy_generate(prompt):
            # The model echoed the input back unchanged.
            return json.dumps({
                'name': 'Banánový chléb',
                'description': 'Oslazený pouze javorovým sirupem.',
            })

        with self.assertRaises(RewriteError):
            rewrite_prose('Banánový chléb',
                          'Oslazený pouze javorovým sirupem.',
                          _maple_plan(), generate=lazy_generate)

    def test_malformed_llm_response_fails_closed(self):
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_prose,
        )

        def bad_generate(prompt):
            return json.dumps({'description': 'chybí jméno'})

        with self.assertRaises(RewriteError):
            rewrite_prose('Banánový chléb',
                          'Oslazený pouze javorovým sirupem.',
                          _maple_plan(), generate=bad_generate)

    def test_prose_keeping_the_surviving_word_is_left_alone(self):
        """'Vanilkový koláč' is still vanilla after extrakt -> aroma.

        Only a word the swap actually REMOVES should trigger a rewrite;
        otherwise every vanilla recipe gets its title regenerated for nothing.
        """
        from diet_planner.services.substitution_rewrite import rewrite_prose

        def explode(prompt):
            raise AssertionError('LLM must not be called')

        name, description = rewrite_prose(
            'Vanilkový koláč', 'Sladký vanilkový koláč.',
            _plan(), generate=explode)

        self.assertEqual(name, 'Vanilkový koláč')
        self.assertEqual(description, 'Sladký vanilkový koláč.')

    def test_title_naming_only_part_of_the_removed_item_is_rewritten(self):
        """'Javorové banánové muffiny' never says 'sirup', but the maple is
        gone — requiring every word of the phrase would miss it."""
        from diet_planner.services.substitution_rewrite import rewrite_prose
        called = {}

        def fake_generate(prompt):
            called['yes'] = True
            return json.dumps({'name': 'Banánové muffiny s medem',
                               'description': 'Vláčné banánové muffiny.'})

        name, _ = rewrite_prose('Javorové banánové muffiny',
                                'Vláčné banánové muffiny.',
                                _maple_plan(), generate=fake_generate)

        self.assertTrue(called.get('yes'), 'stale title must be rewritten')
        self.assertEqual(name, 'Banánové muffiny s medem')

    def test_short_filler_word_in_the_old_name_never_triggers_alone(self):
        """'pico de gallo' -> 'salsa' drops the word 'de', which is a substring
        of half the Czech language ('dezert', 'deset', 'medailonky'). A stem
        that short cannot identify the ingredient, so it must not put a title
        in front of the model — while the real name still must."""
        from diet_planner.services.substitution_rewrite import rewrite_prose
        plan = SubstitutionPlan(saveable=True, changes=[IngredientChange(
            index=0, old_name='pico de gallo', old_slug='pico-de-gallo',
            new_name='salsa', new_canonical='salsa',
            new_quantity=100.0, new_unit='g')])

        def explode(prompt):
            raise AssertionError('LLM must not be called')

        name, description = rewrite_prose(
            'Domácí dezert', 'Lehký domácí dezert.', plan, generate=explode)
        self.assertEqual(name, 'Domácí dezert')
        self.assertEqual(description, 'Lehký domácí dezert.')

        called = {}

        def fake_generate(prompt):
            called['yes'] = True
            return json.dumps({'name': 'Tacos se salsou',
                               'description': 'Tacos se salsou.'})

        name, _ = rewrite_prose('Tacos s pico de gallo', 'Tacos.',
                                plan, generate=fake_generate)
        self.assertTrue(called.get('yes'), 'a real mention must still rewrite')
        self.assertEqual(name, 'Tacos se salsou')
