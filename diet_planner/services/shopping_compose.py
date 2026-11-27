"""One shopping list for several picked recipes (spec 2026-11-03).

Merges only like with like (canonical + unit): never invents a unit
conversion. Amounts are rounded the way people shop: whole pieces, tens of
grams, no amount for a spoon of something.
"""
import math
from typing import Any, Dict, List, Optional, Tuple

PEOPLE_MIN, PEOPLE_MAX = 1, 6
_WHOLE = ('ks', 'stroužk', 'stroužek', 'plátk', 'svazek', 'konzerv', 'balen')
_NO_AMOUNT = ('lžíc', 'lžič', 'špetk', 'dle chuti', 'hrst')


def shopping_amount(quantity: Optional[float], unit: str) -> Tuple[Optional[float], str]:
    unit = (unit or '').strip()
    u = unit.lower()
    if quantity is None or quantity <= 0 or any(u.startswith(p) for p in _NO_AMOUNT):
        return None, unit
    if any(u.startswith(p) for p in _WHOLE):
        return math.ceil(quantity - 1e-9), unit
    if u in ('g', 'ml'):
        return max(10, int(round(quantity / 10.0)) * 10), unit
    return round(quantity + 1e-9, 1), unit


def compose_shopping_list(recipes, *, people: int, deal_index: Dict[str, dict]) -> List[Dict[str, Any]]:
    people = min(max(int(people or 2), PEOPLE_MIN), PEOPLE_MAX)
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for recipe in recipes:
        servings = max(int(recipe.base_servings or 1), 1)
        for ing in recipe.ingredients or []:
            if ing.get('optional'):
                continue
            canonical = (ing.get('canonical') or ing.get('name') or '').strip().lower()
            unit = (ing.get('unit') or '').strip()
            key = (canonical, unit.lower())
            line = merged.setdefault(key, {
                'name': ing.get('name') or canonical, 'canonical': canonical, 'unit': unit,
                'raw': 0.0, 'has_qty': False, 'recipes': [], 'deal': deal_index.get(canonical),
            })
            qty = ing.get('quantity')
            if isinstance(qty, (int, float)) and qty > 0:
                line['raw'] += qty / servings * people
                line['has_qty'] = True
            if recipe.id not in line['recipes']:
                line['recipes'].append(recipe.id)
    out = []
    for line in merged.values():
        amount, unit = shopping_amount(line['raw'] if line['has_qty'] else None, line['unit'])
        out.append({'name': line['name'], 'canonical': line['canonical'], 'amount': amount,
                    'unit': unit, 'needed_by': len(line['recipes']), 'recipe_ids': line['recipes'],
                    'deal': line['deal']})
    out.sort(key=lambda l: (l['deal'] is None, l['name'].lower()))
    return out
