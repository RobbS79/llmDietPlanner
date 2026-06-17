"""
Tests that DietaryGoalDetailSerializer surfaces the user's (decrypted) prompt
so the plan page can show people what they actually asked for.

The prompt is stored encrypted at rest (EncryptedTextField); the serializer
reads through it and exposes the plaintext to the goal's owner. This keeps
encryption-at-rest intact while making request-vs-result visible to the user.
"""
from django.test import TestCase
from django.contrib.auth.models import User

from diet_planner.models import DietaryGoal
from diet_planner.serializers import DietaryGoalDetailSerializer


class GoalDetailSerializerPromptTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('promptuser', password='test')
        self.goal = DietaryGoal.objects.create(
            user=self.user,
            prompt='High-protein vegetarian, Indian flavours, 7 days',
            dietary_restrictions='No peanuts',
            country='CZ',
            city='Prague',
            num_days=7,
        )

    def test_prompt_is_exposed_decrypted(self):
        data = DietaryGoalDetailSerializer(self.goal).data
        self.assertIn('prompt', data)
        self.assertEqual(
            data['prompt'],
            'High-protein vegetarian, Indian flavours, 7 days',
        )

    def test_dietary_restrictions_is_exposed_decrypted(self):
        data = DietaryGoalDetailSerializer(self.goal).data
        self.assertIn('dietary_restrictions', data)
        self.assertEqual(data['dietary_restrictions'], 'No peanuts')

    def test_prompt_is_read_only(self):
        serializer = DietaryGoalDetailSerializer()
        self.assertIn('prompt', serializer.Meta.read_only_fields)
        self.assertIn('dietary_restrictions', serializer.Meta.read_only_fields)
