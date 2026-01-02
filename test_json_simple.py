#!/usr/bin/env python
"""
Simple script to generate example LLM JSON prompt structure without database.
This shows what the JSON structure looks like.
"""
import json

# Example JSON structure that would be generated
example_json = {
    "task": "generate_personalised_diet_plan",
    "user_requirements": {
        "dietary_prompt": "I want to lose 5kg in 2 months while maintaining muscle mass",
        "dietary_restrictions": "No gluten, lactose intolerant"
    },
    "location": {
        "country_code": "CZ",
        "country_name": "Czech Republic",
        "city": "Prague"
    },
    "localisation": {
        "currency": "CZK",
        "language_code": "cs"
    },
    "instructions": {
        "output_format": "json",
        "required_outputs": [
            "meal_ideas",
            "shopping_list"
        ],
        "meal_ideas_requirements": {
            "include": [
                "name",
                "description",
                "ingredients",
                "preparation_time",
                "nutritional_info"
            ],
            "nutritional_info_should_include": [
                "calories",
                "protein",
                "carbs",
                "fat"
            ]
        },
        "shopping_list_requirements": {
            "include": [
                "ingredient",
                "quantity",
                "unit",
                "notes"
            ],
            "notes": "Quantities are optional but recommended. Use metric units (g, kg, ml, l)."
        },
        "context_notes": [
            "Ingredients should be available in local supermarkets (Lidl, Biedronka, Kaufland, etc.)",
            "Consider local cuisine preferences for the specified country",
            "Prices will be calculated separately by the system - do not include prices",
            "Focus on creating practical, achievable meal plans"
        ]
    }
}

print("=" * 80)
print("EXAMPLE LLM PROMPT JSON STRUCTURE")
print("=" * 80)
print(json.dumps(example_json, indent=2, ensure_ascii=False))
print("=" * 80)

# Save to file
output_file = 'example_llm_prompt.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(example_json, f, indent=2, ensure_ascii=False)
print("\nSaved to: {}".format(output_file))
print("\nThis is the structure that will be sent to the LLM when processing a dietary goal.")

