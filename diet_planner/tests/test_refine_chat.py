"""Refine-chat service: conversation -> (PromptFacets, Czech follow-up question).

Never raises: any LLM/parse failure yields (empty facets, None) so the caller
degrades to an unsteered pick.
Spec: docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
"""
from django.test import SimpleTestCase

from diet_planner.services.refine_chat import (
    MAX_TOTAL_MESSAGES,
    MAX_USER_MESSAGES,
    clamp_messages,
    refine_conversation,
)


def msgs(*pairs):
    return [{'role': r, 'text': t} for r, t in pairs]


class ClampMessagesTest(SimpleTestCase):
    def test_drops_malformed_entries_and_trims_text(self):
        raw = [
            {'role': 'user', 'text': 'a' * 900},
            {'role': 'bogus', 'text': 'x'},
            'not-a-dict',
            {'role': 'assistant', 'text': '   '},
            {'role': 'assistant', 'text': 'ok'},
        ]
        clean = clamp_messages(raw)
        self.assertEqual([m['role'] for m in clean], ['user', 'assistant'])
        self.assertEqual(len(clean[0]['text']), 500)

    def test_caps_total_and_user_message_counts(self):
        # 20 user messages -> at most MAX_TOTAL_MESSAGES entries and at most
        # MAX_USER_MESSAGES user entries, keeping the NEWEST ones.
        raw = msgs(*[('user', f'm{i}') for i in range(20)])
        clean = clamp_messages(raw)
        self.assertLessEqual(len(clean), MAX_TOTAL_MESSAGES)
        self.assertLessEqual(sum(1 for m in clean if m['role'] == 'user'), MAX_USER_MESSAGES)
        self.assertEqual(clean[-1]['text'], 'm19')

    def test_non_list_becomes_empty(self):
        self.assertEqual(clamp_messages(None), [])
        self.assertEqual(clamp_messages('hi'), [])


class RefineConversationTest(SimpleTestCase):
    def test_happy_path_returns_facets_and_question(self):
        def fake_gen(system_prompt, user_text):
            # The transcript must reach the LLM (both turns).
            assert 'něco lehčího' in user_text and 'assistant' in user_text
            return ('{"cuisines": ["czech"], "wanted_ingredients": ["kuřecí"],'
                     ' "avoided_ingredients": [], "styles": ["light"], "emphases": [],'
                     ' "question": "Chcete to spíš rychlé?"}')

        facets, question = refine_conversation(
            msgs(('user', 'něco lehčího'), ('assistant', 'Co třeba salát?')),
            language='cs', cuisine_vocab=['czech', 'italian'], generate=fake_gen,
        )
        self.assertEqual(facets.wanted_ingredients, {'kuřecí'})
        self.assertEqual(facets.cuisines, {'czech'})
        self.assertEqual(question, 'Chcete to spíš rychlé?')

    def test_cuisines_outside_vocab_are_dropped(self):
        def fake_gen(sp, ut):
            return '{"cuisines": ["martian"], "question": null}'
        facets, question = refine_conversation(
            msgs(('user', 'cokoli')), language='cs', cuisine_vocab=['czech'], generate=fake_gen,
        )
        self.assertEqual(facets.cuisines, set())
        self.assertIsNone(question)

    def test_null_or_blank_question_becomes_none(self):
        def fake_gen(sp, ut):
            return '{"wanted_ingredients": ["tofu"], "question": "   "}'
        facets, question = refine_conversation(
            msgs(('user', 'tofu')), language='cs', cuisine_vocab=[], generate=fake_gen,
        )
        self.assertEqual(facets.wanted_ingredients, {'tofu'})
        self.assertIsNone(question)

    def test_malformed_json_yields_empty_facets_and_no_question(self):
        facets, question = refine_conversation(
            msgs(('user', 'ahoj')), language='cs', cuisine_vocab=[],
            generate=lambda sp, ut: 'not json at all',
        )
        self.assertTrue(facets.is_empty())
        self.assertIsNone(question)

    def test_generate_exception_yields_empty_facets_and_no_question(self):
        def boom(sp, ut):
            raise RuntimeError('LLM down')
        facets, question = refine_conversation(
            msgs(('user', 'ahoj')), language='cs', cuisine_vocab=[], generate=boom,
        )
        self.assertTrue(facets.is_empty())
        self.assertIsNone(question)

    def test_dietary_restrictions_stated_in_chat_are_extracted(self):
        def fake_gen(sp, ut):
            return '{"dietary": ["gluten_free", "bogus_diet"], "question": null}'
        facets, question = refine_conversation(
            msgs(('user', 'nejím lepek')), language='cs', cuisine_vocab=[], generate=fake_gen,
        )
        self.assertEqual(facets.dietary, {'gluten_free'})
        self.assertFalse(facets.is_empty())

    def test_repeated_question_is_suppressed(self):
        # The LLM re-asking a question already visible in the transcript is
        # dropped to None — never show the user the same question twice.
        q = 'Máte chuť na maso, nebo byste raději bezmasé jídlo?'
        def fake_gen(sp, ut):
            return '{"wanted_ingredients": ["kuřecí"], "question": "%s"}' % q
        facets, question = refine_conversation(
            msgs(
                ('user', 'něco dobrého'),
                ('assistant', f'Co třeba: Kulajda? {q}'),
                ('user', 'něco s kuřecím'),
            ),
            language='cs', cuisine_vocab=[], generate=fake_gen,
        )
        self.assertEqual(facets.wanted_ingredients, {'kuřecí'})
        self.assertIsNone(question)

    def test_fresh_question_is_kept(self):
        def fake_gen(sp, ut):
            return '{"question": "Chcete to spíš rychlé?"}'
        facets, question = refine_conversation(
            msgs(
                ('user', 'něco dobrého'),
                ('assistant', 'Co třeba: Kulajda? Máte chuť na maso, nebo bezmasé?'),
                ('user', 'jiné'),
            ),
            language='cs', cuisine_vocab=[], generate=fake_gen,
        )
        self.assertEqual(question, 'Chcete to spíš rychlé?')

    def test_no_user_messages_makes_no_llm_call(self):
        calls = []
        def spy(sp, ut):
            calls.append(1)
            return '{}'
        facets, question = refine_conversation(
            msgs(('assistant', 'Co třeba?')), language='cs', cuisine_vocab=[], generate=spy,
        )
        self.assertTrue(facets.is_empty())
        self.assertIsNone(question)
        self.assertEqual(calls, [])
