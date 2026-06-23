"""RecipeDetailView must persist the meal's serving count so per-portion
scaling and pricing use the true denominator (not the model default of 1)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal, DietaryPlan, Recipe


class RecipeCreationServingsTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="chef")
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt="x", num_days=1, country="CZ", currency="CZK",
        )
        # A curated meal already has vetted instructions, so the view skips the
        # LLM regeneration path entirely (is_curated == True).
        self.meal = {
            "name": "Bramborové halušky",
            "servings": 4,
            "source": "curated",
            "description": "",
            "instructions": ["Uvař brambory.", "Zpracuj těsto a vař halušky."],
            "ingredients": [{"name": "brambory", "quantity": 600, "unit": "g"}],
            "nutritional_info": {},
        }
        DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{"day_number": 1, "lunch": self.meal}],
            currency="CZK",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_created_recipe_uses_meal_servings(self):
        url = reverse(
            "diet_planner:recipe-detail",
            kwargs={"meal_identifier": f"{self.goal.id}:1:lunch:0"},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        recipe = Recipe.objects.get(meal_identifier=f"{self.goal.id}:1:lunch:0")
        self.assertEqual(recipe.servings, 4)

    def test_servings_defaults_to_one_when_absent(self):
        # A generated (non-curated) meal carries no servings -> default 1.
        DietaryPlan.objects.filter(dietary_goal=self.goal).update(
            days=[{"day_number": 1, "dinner": {
                "name": "Salát", "source": "curated",
                "instructions": ["Smíchej suroviny dohromady."],
                "ingredients": [{"name": "salát", "quantity": 100, "unit": "g"}],
            }}],
        )
        url = reverse(
            "diet_planner:recipe-detail",
            kwargs={"meal_identifier": f"{self.goal.id}:1:dinner:0"},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        recipe = Recipe.objects.get(meal_identifier=f"{self.goal.id}:1:dinner:0")
        self.assertEqual(recipe.servings, 1)
