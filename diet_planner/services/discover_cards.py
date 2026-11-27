# diet_planner/services/discover_cards.py
"""Public payloads for CuratedRecipe on the first-visit landing (spec 2026-11-03).

Per-portion everywhere: base_nutrition is the whole recipe for base_servings.
Unknown nutrition is None so the UI can hide the line. For kcal 0 also
means unknown (no dish has 0 kcal); a macro of 0 is a real value.
"""
from typing import Any, Dict, Optional

from diet_planner.food_categories import guess_category
from diet_planner.food_images import dish_image_url, has_dish_image
from diet_planner.services.ingredient_display import display_ingredient_name
from diet_planner.services.recipe_deals import recipe_deals


def _servings(recipe) -> int:
    return max(int(recipe.base_servings or 1), 1)


def _per_portion(recipe, key: str, *, zero_is_unknown: bool = False) -> Optional[int]:
    value = (recipe.base_nutrition or {}).get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    if value < 0 or (zero_is_unknown and value == 0):
        return None
    return int(round(value / _servings(recipe)))


def image_url(recipe) -> str:
    if has_dish_image(recipe.slug):
        return dish_image_url(recipe.slug)
    return f"/static/food-images/{guess_category(recipe.name_cs, recipe.ingredients or [])}.webp"


def _deals(recipe, deal_index, slug_cache) -> Dict[str, Any]:
    result = recipe_deals(recipe.ingredients or [], index=deal_index, slug_cache=slug_cache)
    names = []
    for deal in result['deals']:
        name = (deal.get('display_name') or deal.get('ingredient') or '').split(' ')[0].lower()
        if name and name not in names:
            names.append(name)
    return {'matched': result['matched'], 'total': result['total'],
            'names': names, 'items': result['deals']}


def recipe_card(recipe, *, deal_index, slug_cache) -> Dict[str, Any]:
    return {
        'id': recipe.id,
        'slug': recipe.slug,
        'name': recipe.name_cs,
        'image_url': image_url(recipe),
        'minutes': recipe.total_time or None,
        'kcal': _per_portion(recipe, 'calories', zero_is_unknown=True),
        'deals': _deals(recipe, deal_index, slug_cache),
    }


def recipe_sheet(recipe, *, deal_index, slug_cache) -> Dict[str, Any]:
    card = recipe_card(recipe, deal_index=deal_index, slug_cache=slug_cache)
    protein, carbs, fat = (_per_portion(recipe, k) for k in ('protein', 'carbs', 'fat'))
    servings = _servings(recipe)
    ingredients = []
    for ing in recipe.ingredients or []:
        if ing.get('optional'):
            continue
        qty = ing.get('quantity')
        ingredients.append({
            'name': display_ingredient_name(ing),
            'canonical': ing.get('canonical') or '',
            'quantity': (qty / servings) if isinstance(qty, (int, float)) else None,
            'unit': ing.get('unit') or '',
        })
    return {
        **card,
        'macros': ({'protein': protein, 'carbs': carbs, 'fat': fat}
                   if None not in (protein, carbs, fat) else None),
        'ingredients': ingredients,
        'steps': list(recipe.instructions or []),
        'source': {'name': recipe.source_name, 'url': recipe.source_url},
    }
