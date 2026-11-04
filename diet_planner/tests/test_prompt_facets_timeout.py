import sys
import types
from unittest import mock

from django.test import SimpleTestCase

from diet_planner.services import prompt_facets


class DefaultGenerateTimeoutTest(SimpleTestCase):
    def test_generate_content_gets_a_request_timeout(self):
        import google.generativeai as genai
        model = mock.Mock()
        model.generate_content.return_value = types.SimpleNamespace(text='{}')
        with mock.patch.object(genai, 'configure'), \
             mock.patch.object(genai, 'GenerativeModel', return_value=model):
            self.assertEqual(prompt_facets._default_generate('sys', 'user'), '{}')
        self.assertEqual(model.generate_content.call_args.kwargs['request_options'], {'timeout': 10})
        self.assertIn('google.generativeai', sys.modules)
