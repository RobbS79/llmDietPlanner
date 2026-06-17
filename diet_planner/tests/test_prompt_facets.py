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
