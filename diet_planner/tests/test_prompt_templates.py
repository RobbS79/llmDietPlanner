"""Reducing real prompts to shareable templates. Nothing personal reaches git."""
from io import StringIO

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import DietaryGoal
from diet_planner.services.prompt_templates import reduce_prompt


class ReducePromptTests(TestCase):
    def test_day_counts_become_a_placeholder(self):
        self.assertEqual(reduce_prompt('jídelníček na 5 dní'),
                         'jídelníček na {n} dní')

    def test_have_x_phrasing_is_preserved_as_a_shape(self):
        """This shape broke facet extraction in prod; the farm must keep it."""
        self.assertEqual(reduce_prompt('Mám kuřecí maso, co uvařit?'),
                         'Mám {ingredient}, co uvařit?')

    def test_an_email_makes_the_prompt_undroppable_into_a_template(self):
        self.assertIsNone(reduce_prompt('napiš mi to na rob@example.com'))

    def test_a_long_free_text_prompt_is_dropped_not_exported(self):
        self.assertIsNone(reduce_prompt(
            'ahoj jmenuji se Petr a bydlím v Brně na Kounicově 12 a chci jíst lépe'))

    def test_empty_prompt_is_dropped(self):
        self.assertIsNone(reduce_prompt(''))

    def test_short_personal_name_becomes_the_free_short_shape(self):
        self.assertEqual(reduce_prompt('Petr Novák'), '{free_short}')

    def test_a_punctuated_question_becomes_the_free_short_shape(self):
        # Dropping punctuated prompts was the wrong default: questions are how
        # people actually phrase real queries, and this module's whole job is
        # to harvest phrasing signal. The catch-all admits punctuation but
        # still only ever emits the fixed {free_short} literal, so safety is
        # untouched.
        self.assertEqual(reduce_prompt('Co mám vařit?'), '{free_short}')


class ExportGoalPromptsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='u', email='u@example.com', password='x')
        self.path = '/tmp/prompt_templates_test.yaml'

    def _goal(self, prompt):
        return DietaryGoal.objects.create(user=self.user, prompt=prompt, num_days=5)

    def test_export_writes_templates_with_counts(self):
        self._goal('jídelníček na 5 dní')
        self._goal('jídelníček na 7 dní')
        self._goal('Mám kuřecí maso, co uvařit?')

        call_command('export_goal_prompts', '--output', self.path, stdout=StringIO())
        payload = yaml.safe_load(open(self.path, encoding='utf-8'))
        by_template = {row['template']: row['observed'] for row in payload['templates']}
        self.assertEqual(by_template['jídelníček na {n} dní'], 2)
        self.assertEqual(by_template['Mám {ingredient}, co uvařit?'], 1)

    def test_unreducible_prompts_never_reach_the_file(self):
        self._goal('ahoj jmenuji se Petr a bydlím v Brně na Kounicově 12')
        call_command('export_goal_prompts', '--output', self.path, stdout=StringIO())
        raw = open(self.path, encoding='utf-8').read()
        self.assertNotIn('Petr', raw)
        self.assertNotIn('Kounicova', raw)
        self.assertNotIn('Kounicově', raw)

    def test_short_personal_prompt_never_reaches_the_file(self):
        self._goal('Petr Novák')  # short enough to hit {free_short}, not the drop path
        call_command('export_goal_prompts', '--output', self.path, stdout=StringIO())
        raw = open(self.path, encoding='utf-8').read()
        self.assertNotIn('Petr', raw)
        self.assertNotIn('Novák', raw)
