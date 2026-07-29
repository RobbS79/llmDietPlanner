from django.test import SimpleTestCase

from diet_planner.services.prompt_facets import PromptFacets, _coerce_facets


class CoerceFacetsTest(SimpleTestCase):
    VOCAB = ['czech', 'italian', 'asian']

    def test_normalizes_and_filters_cuisine_to_vocab(self):
        facets = _coerce_facets(
            {'cuisines': ['Italian', 'klingon'], 'wanted_ingredients': ['Chicken']},
            cuisine_vocab=self.VOCAB,
        )
        self.assertEqual(facets.cuisines, {'italian'})          # klingon dropped
        self.assertEqual(facets.wanted_ingredients, {'chicken'})  # lowercased

    def test_missing_keys_yield_empty_sets(self):
        facets = _coerce_facets({}, cuisine_vocab=self.VOCAB)
        self.assertTrue(facets.is_empty())

    def test_non_list_values_are_ignored(self):
        facets = _coerce_facets(
            {'cuisines': 'italian', 'avoided_ingredients': None, 'styles': ['quick']},
            cuisine_vocab=self.VOCAB,
        )
        self.assertEqual(facets.cuisines, set())     # string, not list -> ignored
        self.assertEqual(facets.avoided_ingredients, set())
        self.assertEqual(facets.styles, {'quick'})

    def test_to_debug_is_sorted_lists(self):
        facets = _coerce_facets(
            {'emphases': ['high_protein'], 'cuisines': ['asian', 'italian']},
            cuisine_vocab=self.VOCAB,
        )
        self.assertEqual(
            facets.to_debug(),
            {
                'cuisines': ['asian', 'italian'],
                'wanted_ingredients': [],
                'avoided_ingredients': [],
                'styles': [],
                'emphases': ['high_protein'],
                'dietary': [],
                'max_time_minutes': None,
            },
        )

    def test_max_time_minutes_parsed(self):
        facets = _coerce_facets({'max_time_minutes': 30}, cuisine_vocab=self.VOCAB)
        self.assertEqual(facets.max_time_minutes, 30)
        self.assertFalse(facets.is_empty())  # a time limit alone is a real constraint

    def test_max_time_minutes_numeric_string_parsed(self):
        facets = _coerce_facets({'max_time_minutes': '30'}, cuisine_vocab=self.VOCAB)
        self.assertEqual(facets.max_time_minutes, 30)

    def test_max_time_minutes_invalid_or_nonpositive_is_none(self):
        for bad in (None, 'soon', -5, 0, []):
            facets = _coerce_facets({'max_time_minutes': bad}, cuisine_vocab=self.VOCAB)
            self.assertIsNone(facets.max_time_minutes, msg=repr(bad))


from diet_planner.services.prompt_facets import extract_prompt_facets


class ExtractPromptFacetsTest(SimpleTestCase):
    VOCAB = ['czech', 'italian', 'asian']

    def test_parses_json_and_maps_vocab(self):
        def fake_generate(system_prompt, user_text):
            return '{"cuisines": ["italian"], "wanted_ingredients": ["chicken"], "emphases": ["high_protein"]}'

        facets = extract_prompt_facets(
            'rychlé italské večeře s kuřecím, hodně bílkovin',
            language='cs', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertEqual(facets.cuisines, {'italian'})
        self.assertEqual(facets.wanted_ingredients, {'chicken'})
        self.assertEqual(facets.emphases, {'high_protein'})

    def test_strips_markdown_code_fence(self):
        def fake_generate(system_prompt, user_text):
            return '```json\n{"cuisines": ["asian"]}\n```'

        facets = extract_prompt_facets(
            'asian food', language='en', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertEqual(facets.cuisines, {'asian'})

    def test_empty_prompt_returns_empty_without_calling_llm(self):
        calls = []

        def fake_generate(system_prompt, user_text):
            calls.append(1)
            return '{}'

        facets = extract_prompt_facets(
            '   ', language='cs', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertTrue(facets.is_empty())
        self.assertEqual(calls, [])  # short-circuited, no LLM call

    def test_garbage_output_returns_empty(self):
        def fake_generate(system_prompt, user_text):
            return 'not json at all'

        facets = extract_prompt_facets(
            'whatever', language='en', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertTrue(facets.is_empty())

    def test_max_time_minutes_extracted(self):
        def fake_generate(system_prompt, user_text):
            return '{"max_time_minutes": 30, "styles": ["quick"]}'

        facets = extract_prompt_facets(
            'Max 30 minut na vaření', language='cs', cuisine_vocab=self.VOCAB,
            generate=fake_generate,
        )
        self.assertEqual(facets.max_time_minutes, 30)

    def test_system_prompt_mentions_time_limit_key(self):
        seen = {}

        def fake_generate(system_prompt, user_text):
            seen['system'] = system_prompt
            return '{}'

        extract_prompt_facets(
            'cokoliv', language='cs', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertIn('max_time_minutes', seen['system'])

    def test_generate_exception_returns_empty(self):
        def fake_generate(system_prompt, user_text):
            raise RuntimeError('LLM down')

        facets = extract_prompt_facets(
            'whatever', language='en', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertTrue(facets.is_empty())
