"""Deciding whether an unshoppable recipe can be rewritten into a shoppable one.

Pure: no LLM, no writes. The command in
`management/commands/apply_availability_substitutions.py` owns the side
effects; everything here is a function of (recipe, table).

See docs/superpowers/specs/2026-08-11-ingredient-obtainability-design.md §6
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from diet_planner.models.catalog import Availability, IngredientSubstitute
from diet_planner.services.ingredient_availability import (
    _entry_availability,
    availability_index,
)

#: Swaps that would quietly break a dietary promise the recipe makes. The
#: substitute is fine in general; it is not fine in a recipe carrying this tag.
#: Without this, the spec's own `tamari -> sójová omáčka` row would strip the
#: gluten-free guarantee off a recipe advertised as gluten_free — and those
#: tags are hard-enforced everywhere else in the product.
_TAG_INCOMPATIBLE = {
    'gluten_free': {'soy-sauce', 'wheat-flour', 'oats', 'oat-flour', 'barley',
                    'couscous'},
    'vegan': {'honey', 'butter', 'yogurt', 'milk', 'eggs'},
    'dairy_free': {'butter', 'yogurt', 'milk', 'cream'},
}


@dataclass(frozen=True)
class SubstitutionRule:
    old_slug: str
    new_slug: str
    new_name: str
    conversion_factor: float
    new_unit: str
    quality_score: float


@dataclass(frozen=True)
class IngredientChange:
    index: int
    old_name: str
    old_slug: str
    new_name: str
    new_canonical: str
    new_quantity: Optional[float]
    new_unit: str


@dataclass
class SubstitutionPlan:
    saveable: bool = False
    changes: List[IngredientChange] = field(default_factory=list)
    uncovered: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """The adaptation_note body: 'tamari → sójová omáčka, ...'."""
        return ', '.join(f'{c.old_name} → {c.new_name}' for c in self.changes)


def substitution_table() -> Dict[str, SubstitutionRule]:
    """slug -> best availability swap. Highest quality_score wins a tie."""
    rows = (
        IngredientSubstitute.objects
        .filter(purpose=IngredientSubstitute.Purpose.AVAILABILITY)
        .select_related('ingredient', 'substitute')
        .order_by('-quality_score')
    )
    table: Dict[str, SubstitutionRule] = {}
    for row in rows:
        if row.ingredient.slug in table:
            continue  # already have a better-scoring swap
        table[row.ingredient.slug] = SubstitutionRule(
            old_slug=row.ingredient.slug,
            new_slug=row.substitute.slug,
            new_name=row.substitute.name_cs or row.substitute.name,
            conversion_factor=float(row.conversion_factor),
            new_unit=row.substitute_unit or '',
            quality_score=float(row.quality_score),
        )
    return table


def _breaks_dietary_promise(recipe, rule: SubstitutionRule) -> bool:
    for tag in (recipe.dietary_tags or []):
        if rule.new_slug in _TAG_INCOMPATIBLE.get(tag, ()):
            return True
    return False


def plan_substitutions(
    recipe,
    table: Dict[str, SubstitutionRule],
    index: Optional[Dict[str, str]] = None,
) -> SubstitutionPlan:
    """What it would take to make `recipe` shoppable.

    `saveable` is True only when EVERY blocker is covered. Partial coverage is
    worthless: a recipe with one remaining unbuyable ingredient still fails the
    one-stop bar, and we would have rewritten a sourced recipe for nothing.
    """
    if index is None:
        index = availability_index()

    plan = SubstitutionPlan()

    for position, ing in enumerate(recipe.ingredients or []):
        # Generated (non-corpus) meals carry bare strings rather than dicts;
        # those have no canonical to rate, so they are skipped, not crashed on.
        if not isinstance(ing, dict) or ing.get('optional'):
            continue

        availability, key = _entry_availability(ing, index)
        if availability == Availability.COMMON:
            continue

        rule = table.get(key)
        if rule is None or _breaks_dietary_promise(recipe, rule):
            plan.uncovered.append(key)
            continue

        quantity = ing.get('quantity')
        try:
            new_quantity = (
                round(float(quantity) * rule.conversion_factor, 3)
                if quantity is not None else None
            )
        except (TypeError, ValueError):
            new_quantity = None

        plan.changes.append(IngredientChange(
            index=position,
            old_name=(ing.get('name') or '').strip(),
            old_slug=key,
            new_name=rule.new_name,
            new_canonical=rule.new_slug,
            new_quantity=new_quantity,
            new_unit=rule.new_unit or (ing.get('unit') or ''),
        ))

    plan.uncovered = sorted(set(plan.uncovered))
    plan.saveable = bool(plan.changes) and not plan.uncovered
    if not plan.saveable:
        plan.changes = []
    return plan


def apply_changes_to_ingredients(ingredients, plan: SubstitutionPlan) -> List[dict]:
    """A NEW ingredients list with the plan applied. Does not mutate the input.

    The caller snapshots the author's original into
    `CuratedRecipe.original_ingredients`, so aliasing the dicts here would
    quietly corrupt the very record that proves what we changed.
    """
    out = [dict(ing) if isinstance(ing, dict) else ing for ing in (ingredients or [])]
    for change in plan.changes:
        entry = out[change.index]
        entry['name'] = change.new_name
        entry['canonical'] = change.new_canonical
        if change.new_quantity is not None:
            entry['quantity'] = change.new_quantity
        if change.new_unit:
            entry['unit'] = change.new_unit
        # Points at a StoreProduct for the ingredient we just replaced.
        entry.pop('catalog_id', None)
    return out
