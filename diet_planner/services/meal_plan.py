"""
Meal Plan Generation Service - Phase 1 of Two-Phase LLM Architecture.
Generates meal plans based on dietary requirements without shop data.
"""
import json
import logging
from typing import Dict, Any, Optional, List

from django.conf import settings

from diet_planner.models import DietaryGoal
from diet_planner.llm_service import GeminiService

logger = logging.getLogger(__name__)


class MealPlanService:
    """
    Service for generating meal plans using Gemini.
    Phase 1: Creates meal plan based solely on dietary requirements.
    Does NOT include pricing - that's handled by Phase 2.
    """

    def __init__(self):
        """Initialize Gemini service."""
        self.llm_service = GeminiService()
        self.model = getattr(settings, 'GEMINI_MODEL', 'gemini-2.0-flash-exp')

    def generate_meal_plan(self, goal: DietaryGoal) -> Dict[str, Any]:
        """
        Generate a meal plan based on dietary goal requirements.

        Args:
            goal: DietaryGoal with user preferences

        Returns:
            Dict containing:
                - 'days': List of day objects with meals
                - 'input_tokens': Token count
                - 'output_tokens': Token count
                - 'cost_usd': API cost
                - 'model': Model used
        """
        prompt = self._build_meal_plan_prompt(goal)
        system_prompt = self._build_system_prompt(goal)

        try:
            import google.generativeai as genai
            
            # Use Gemini API
            gemini_model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system_prompt
            )
            
            response = gemini_model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                },
                request_options={"timeout": 300}  # 5 minutes timeout for meal plan generation
            )

            content = response.text
            usage = response.usage_metadata
            
            input_tokens = usage.prompt_token_count
            output_tokens = usage.candidates_token_count
            total_tokens = usage.total_token_count

            # Calculate cost
            from diet_planner.llm_service import calculate_cost
            cost_usd = calculate_cost(input_tokens, output_tokens, self.model)

            # Parse response
            parsed = json.loads(content)
            days = parsed.get('days', [])

            # Transform old format if needed
            days = self._transform_days_format(days, goal)

            logger.info(
                f"MealPlanService: Generated {len(days)} days, "
                f"tokens: {total_tokens}, cost: ${cost_usd}"
            )

            return {
                'days': days,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'cost_usd': cost_usd,
                'model': self.model,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse meal plan JSON: {e}")
            raise ValueError(f"LLM returned invalid JSON: {e}")
        except Exception as e:
            logger.exception(f"MealPlanService error: {e}")
            raise

    def _build_system_prompt(self, goal: DietaryGoal) -> str:
        """Build system prompt for meal plan generation."""
        language_names = {
            'cs': 'Czech', 'sk': 'Slovak', 'pl': 'Polish',
            'hu': 'Hungarian', 'ro': 'Romanian', 'bg': 'Bulgarian',
            'de': 'German', 'en': 'English',
        }
        target_language = language_names.get(goal.language_code, 'English')

        return f"""You are a nutrition expert creating personalised day-by-day meal plans.
Your responses must be valid JSON only, with no markdown formatting.
All meal names, descriptions, and content must be in {target_language} (code: {goal.language_code}).

Generate a 'days' array where each day has:
- day_number (integer)
- breakfast (single meal object, if requested)
- lunch (single meal object, if requested)
- dinner (single meal object, if requested)
- small_meals (array of meal objects)
- snacks (array of meal objects)

Each meal must include:
- name: Meal name in {target_language}
- description: Brief description in {target_language}
- ingredients: Array of ingredient objects with 'name' and 'quantity' (metric units)
- preparation_time: Minutes as integer
- instructions: Array of step-by-step cooking instructions in {target_language}
- nutritional_info: Object with calories, protein, carbs, fat

DO NOT include prices - the system will calculate them separately.
Focus on ingredients available in local Central European supermarkets."""

    def _build_meal_plan_prompt(self, goal: DietaryGoal) -> str:
        """Build the user prompt for meal plan generation."""
        country_names = dict(DietaryGoal._meta.get_field('country').choices)
        country_name = country_names.get(goal.country, goal.country)

        prompt_data = {
            "task": "generate_meal_plan",
            "user_requirements": {
                "dietary_prompt": goal.prompt,
                "dietary_restrictions": goal.dietary_restrictions or None,
            },
            "location": {
                "country_code": goal.country,
                "country_name": country_name,
                "city": goal.city,
            },
            "localisation": {
                "language_code": goal.language_code,
            },
            "meal_plan_configuration": {
                "num_days": goal.num_days,
                "include_breakfast": goal.breakfast,
                "include_lunch": goal.lunch,
                "include_dinner": goal.dinner,
                "small_meals_per_day": goal.small_meals_per_day,
                "snacks_per_day": goal.snacks_per_day,
            },
            "instructions": [
                f"Generate a {goal.num_days}-day meal plan.",
                f"Include breakfast: {'YES' if goal.breakfast else 'NO'}",
                f"Include lunch: {'YES' if goal.lunch else 'NO'}",
                f"Include dinner: {'YES' if goal.dinner else 'NO'}",
                f"Include {goal.small_meals_per_day} small meal(s) per day",
                f"Include {goal.snacks_per_day} snack(s) per day",
                "Use metric units for all quantities (g, kg, ml, l)",
                "Ensure variety across days",
                "Focus on practical, achievable meals",
                "Consider local cuisine preferences for the country",
            ]
        }

        return json.dumps(prompt_data, indent=2, ensure_ascii=False)

    def _transform_days_format(
        self,
        days_data: List[Dict[str, Any]],
        goal: DietaryGoal
    ) -> List[Dict[str, Any]]:
        """Transform old format (main_courses) to new format (breakfast/lunch/dinner)."""
        if not days_data or not isinstance(days_data, list):
            return []

        transformed_days = []

        wants_breakfast = getattr(goal, 'breakfast', True)
        wants_lunch = getattr(goal, 'lunch', True)
        wants_dinner = getattr(goal, 'dinner', True)

        for day in days_data:
            if not isinstance(day, dict):
                continue

            transformed_day = {
                'day_number': day.get('day_number', len(transformed_days) + 1),
                'small_meals': day.get('small_meals', []),
                'snacks': day.get('snacks', []),
            }

            # If new format exists, use it
            if 'breakfast' in day or 'lunch' in day or 'dinner' in day:
                if wants_breakfast and day.get('breakfast'):
                    transformed_day['breakfast'] = day['breakfast']
                if wants_lunch and day.get('lunch'):
                    transformed_day['lunch'] = day['lunch']
                if wants_dinner and day.get('dinner'):
                    transformed_day['dinner'] = day['dinner']
            # Convert from old main_courses format
            elif 'main_courses' in day and isinstance(day['main_courses'], list):
                main_courses = day['main_courses']
                meal_index = 0
                if wants_breakfast and meal_index < len(main_courses):
                    transformed_day['breakfast'] = main_courses[meal_index]
                    meal_index += 1
                if wants_lunch and meal_index < len(main_courses):
                    transformed_day['lunch'] = main_courses[meal_index]
                    meal_index += 1
                if wants_dinner and meal_index < len(main_courses):
                    transformed_day['dinner'] = main_courses[meal_index]
                    meal_index += 1

            transformed_days.append(transformed_day)

        return transformed_days
