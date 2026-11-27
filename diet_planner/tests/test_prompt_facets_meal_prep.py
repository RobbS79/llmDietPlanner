from django.test import SimpleTestCase

from diet_planner.services import prompt_facets


class MealPrepVocabularyTest(SimpleTestCase):
    def test_prompt_teaches_meal_prep_style(self):
        text = prompt_facets._SYSTEM_PROMPT_TEMPLATE
        self.assertIn('meal_prep', text)
        self.assertIn('krabičk', text)

    def test_meal_prep_style_survives_coercion(self):
        facets = prompt_facets.extract_prompt_facets(
            'krabičky do práce na celý týden', language='cs', cuisine_vocab=[],
            generate=lambda system, user: '{"styles": ["meal_prep"]}')
        self.assertIn('meal_prep', facets.styles)
        self.assertFalse(facets.suspect)
