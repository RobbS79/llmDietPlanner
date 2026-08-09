from django.test import SimpleTestCase

from diet_planner.services.prompt_facets import (
    ENFORCEABLE_DIETARY_TAGS,
    PromptFacets,
    _coerce_facets,
)


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

    def test_trailing_prose_after_the_json_does_not_kill_the_extraction(self):
        # Prod 2026-08-09: after the gemini-3.5-flash bump every facet call died
        # with json.loads "Extra data" — so cuisines, wanted ingredients, time
        # limits and dietary restrictions were silently empty product-wide, and
        # a vegetarian plan happily offered meat swaps.
        def fake_generate(system_prompt, user_text):
            return (
                '{"dietary": ["vegetarian"], "max_time_minutes": 30}\n\n'
                'Vysvětlení: uživatel uvedl vegetariánskou stravu a limit 30 minut.'
            )

        facets = extract_prompt_facets(
            'vegetariánská strava, max 30 minut',
            language='cs', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertEqual(facets.dietary, {'vegetarian'})
        self.assertEqual(facets.max_time_minutes, 30)

    def test_prose_before_the_json_is_tolerated(self):
        def fake_generate(system_prompt, user_text):
            return 'Jistě, tady je výsledek:\n{"cuisines": ["italian"]}'

        facets = extract_prompt_facets(
            'italská kuchyně', language='cs', cuisine_vocab=self.VOCAB,
            generate=fake_generate,
        )
        self.assertEqual(facets.cuisines, {'italian'})

    def test_contract_object_wins_over_an_unrelated_one(self):
        def fake_generate(system_prompt, user_text):
            return '{"note": "example"}\n{"dietary": ["vegan"]}'

        facets = extract_prompt_facets(
            'veganská strava', language='cs', cuisine_vocab=self.VOCAB,
            generate=fake_generate,
        )
        self.assertEqual(facets.dietary, {'vegan'})

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

    def test_system_prompt_asks_for_the_dietary_key(self):
        # Prod 2026-08-09: the contract listed six keys and `dietary` was not
        # one of them, so the model never emitted it, `_coerce_facets` always
        # read an absent key, and DietaryGoal.derived_dietary_tags (the whole
        # point of 1c022fc) was never written. A vegetarian plan then served
        # meat swap candidates because every gate had nothing to enforce.
        seen = {}

        def fake_generate(system_prompt, user_text):
            seen['system'] = system_prompt
            return '{}'

        extract_prompt_facets(
            'vegetariánská strava', language='cs', cuisine_vocab=self.VOCAB,
            generate=fake_generate,
        )
        self.assertIn('"dietary"', seen['system'])

    def test_system_prompt_offers_exactly_the_enforceable_tags(self):
        # The prompt's vocabulary must be generated FROM the enforceable set,
        # not typed out beside it — a tag the corpus cannot gate on is a
        # restriction we would silently drop.
        seen = {}

        def fake_generate(system_prompt, user_text):
            seen['system'] = system_prompt
            return '{}'

        extract_prompt_facets(
            'bez lepku', language='cs', cuisine_vocab=self.VOCAB,
            generate=fake_generate,
        )
        for tag in ENFORCEABLE_DIETARY_TAGS:
            self.assertIn(tag, seen['system'], msg=f'{tag} missing from contract')

    def test_stated_restriction_becomes_a_dietary_facet(self):
        def fake_generate(system_prompt, user_text):
            return '{"dietary": ["vegetarian"], "cuisines": []}'

        facets = extract_prompt_facets(
            'Chci jíst zdravěji. Vegetariánská strava. Pro 2 osoby.',
            language='cs', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertEqual(facets.dietary, {'vegetarian'})
        self.assertFalse(facets.is_empty())

    def test_generate_exception_returns_empty(self):
        def fake_generate(system_prompt, user_text):
            raise RuntimeError('LLM down')

        facets = extract_prompt_facets(
            'whatever', language='en', cuisine_vocab=self.VOCAB, generate=fake_generate,
        )
        self.assertTrue(facets.is_empty())


class SuspectEmptyFacetsTest(SimpleTestCase):
    """Empty facets from a substantive prompt are an anomaly, not a fact about
    the user (goal 133: 'Mám vejce, těstoviny, tuňáka…' → empty on ~half of
    LLM samples). The extractor must retry once, and if still empty flag the
    result `suspect` so the overlay stops overriding generated meals."""

    VOCAB = ['czech']
    NONTRIVIAL = 'Mám vejce, bezlepkové těstoviny a tuňáka, navař mi z toho.'
    EMPTY = '{"wanted_ingredients": []}'
    GOOD = '{"wanted_ingredients": ["tuňák"]}'

    def test_retries_once_when_nontrivial_prompt_yields_empty(self):
        calls = []

        def gen(system_prompt, user_text):
            calls.append(1)
            return self.EMPTY if len(calls) == 1 else self.GOOD

        facets = extract_prompt_facets(
            self.NONTRIVIAL, language='cs', cuisine_vocab=self.VOCAB, generate=gen)
        self.assertEqual(len(calls), 2)
        self.assertEqual(facets.wanted_ingredients, {'tuňák'})
        self.assertFalse(facets.suspect)

    def test_no_retry_when_first_attempt_has_content(self):
        calls = []

        def gen(system_prompt, user_text):
            calls.append(1)
            return self.GOOD

        facets = extract_prompt_facets(
            self.NONTRIVIAL, language='cs', cuisine_vocab=self.VOCAB, generate=gen)
        self.assertEqual(len(calls), 1)
        self.assertFalse(facets.suspect)

    def test_suspect_when_retry_still_empty(self):
        facets = extract_prompt_facets(
            self.NONTRIVIAL, language='cs', cuisine_vocab=self.VOCAB,
            generate=lambda s, u: self.EMPTY)
        self.assertTrue(facets.is_empty())
        self.assertTrue(facets.suspect)

    def test_trivial_prompt_empty_is_not_suspect(self):
        calls = []

        def gen(system_prompt, user_text):
            calls.append(1)
            return self.EMPTY

        facets = extract_prompt_facets(
            'jídlo', language='cs', cuisine_vocab=self.VOCAB, generate=gen)
        self.assertEqual(len(calls), 1)  # trivial prompt: no retry either
        self.assertFalse(facets.suspect)

    def test_exception_on_nontrivial_prompt_is_suspect(self):
        def gen(system_prompt, user_text):
            raise RuntimeError('LLM down')

        facets = extract_prompt_facets(
            self.NONTRIVIAL, language='cs', cuisine_vocab=self.VOCAB, generate=gen)
        self.assertTrue(facets.is_empty())
        self.assertTrue(facets.suspect)

    def test_system_prompt_counts_inventory_as_wanted(self):
        seen = {}

        def gen(system_prompt, user_text):
            seen['system'] = system_prompt
            return self.GOOD

        extract_prompt_facets(
            self.NONTRIVIAL, language='cs', cuisine_vocab=self.VOCAB, generate=gen)
        self.assertIn('mám', seen['system'].lower())  # inventory rule spelled out
