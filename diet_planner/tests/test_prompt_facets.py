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
            },
        )


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

    def test_generate_exception_returns_empty(self):
        def fake_generate(system_prompt, user_text):
            raise RuntimeError('LLM down')

        facets = extract_prompt_facets(
            'whatever', language='en', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertTrue(facets.is_empty())
