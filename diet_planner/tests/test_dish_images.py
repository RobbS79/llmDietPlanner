"""Serializer image fallback chain: per-dish image beats category stock."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from diet_planner.models import DietaryGoal, Recipe
from diet_planner.serializers import RecipeSerializer


class DishImageFallbackTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.recipe = Recipe.objects.create(
            meal_identifier='g:1:lunch:0', dietary_goal=self.goal,
            name='Kuřecí parmigiana', food_category='kureci', servings=4,
            instructions=['Obalte kuřecí prsa a zapečte je se sýrem a omáčkou.'] * 3,
            ingredients=[{'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g'}],
        )

    def test_dish_image_wins_when_present(self):
        with mock.patch(
            'diet_planner.food_images._dish_image_slugs',
            return_value=frozenset({'kureci-parmigiana'}),
        ):
            data = RecipeSerializer(self.recipe).data
        self.assertEqual(data['image_url'], '/static/food-images/dishes/kureci-parmigiana.webp')

    def test_falls_back_to_category_stock_image(self):
        with mock.patch(
            'diet_planner.food_images._dish_image_slugs',
            return_value=frozenset(),
        ):
            data = RecipeSerializer(self.recipe).data
        self.assertTrue(data['image_url'].startswith('/static/food-images/'))
        self.assertNotIn('/dishes/', data['image_url'])
