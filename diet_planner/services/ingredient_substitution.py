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
    #: Every non-common ingredient we have no usable swap for, both tiers.
    #: Reported, not all fatal.
    uncovered: List[str] = field(default_factory=list)
    #: The subset of `uncovered` that is `specialty` — the only tier retrieval
    #: actually gates on, and therefore the only one that can sink a plan.
    blocking: List[str] = field(default_factory=list)
    #: Swaps on `optional` entries. Kept apart from `changes` because optional
    #: items must never enter the gating calculus — they cannot sink a plan and
    #: are not a reason to start one. They ride along on a real rescue so an
    #: adapted recipe stops listing the ingredient it says it replaced.
    optional_changes: List[IngredientChange] = field(default_factory=list)

    def summary(self) -> str:
        """The adaptation_note body: 'tamari → sójová omáčka, ...'.

        Optional swaps are disclosed too — the note is what the reader is told
        we changed, and what a later audit reads back.
        """
        return ', '.join(
            f'{c.old_name} → {c.new_name}'
            for c in list(self.changes) + list(self.optional_changes))


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

    `saveable` is True when every SPECIALTY blocker is covered and at least one
    swap results. Specialty is the bar because it is what
    `eligible_recipes_for_slot` hard-gates on: a recipe carrying one is invisible
    to every user, so rescuing it is what buys anything. A leftover `findable`
    item ("large store or Rohlík only") costs the recipe a ranking penalty, not
    its existence — refusing the rescue over one would keep the recipe gated out
    for no gain. Those are still reported in `uncovered`.

    Demanding full coverage of both tiers was the original rule and it recovered
    nothing: measured against the prod corpus on 2026-08-18, 0 of 252 eligible
    recipes cleared it, 149 of them missing by exactly one findable item.
    """
    if index is None:
        index = availability_index()

    plan = SubstitutionPlan()

    for position, ing in enumerate(recipe.ingredients or []):
        # Generated (non-corpus) meals carry bare strings rather than dicts;
        # those have no canonical to rate, so they are skipped, not crashed on.
        if not isinstance(ing, dict):
            continue
        optional = bool(ing.get('optional'))

        availability, key = _entry_availability(ing, index)
        if availability == Availability.COMMON:
            continue

        rule = table.get(key)
        if rule is None or _breaks_dietary_promise(recipe, rule):
            # An optional entry we cannot swap is not a shopping problem: the
            # cook simply leaves it out. Reporting it would let a garnish gate
            # the whole recipe out of retrieval.
            if not optional:
                plan.uncovered.append(key)
                if availability == Availability.SPECIALTY:
                    plan.blocking.append(key)
            continue

        quantity = ing.get('quantity')
        try:
            new_quantity = (
                round(float(quantity) * rule.conversion_factor, 3)
                if quantity is not None else None
            )
        except (TypeError, ValueError):
            new_quantity = None

        target = plan.optional_changes if optional else plan.changes
        target.append(IngredientChange(
            index=position,
            old_name=(ing.get('name') or '').strip(),
            old_slug=key,
            new_name=rule.new_name,
            new_canonical=rule.new_slug,
            new_quantity=new_quantity,
            new_unit=rule.new_unit or (ing.get('unit') or ''),
        ))

    plan.uncovered = sorted(set(plan.uncovered))
    plan.blocking = sorted(set(plan.blocking))
    # `changes` alone decides saveability: an optional-only plan would
    # rewrite a credited recipe for a garnish and rescue nothing.
    plan.saveable = bool(plan.changes) and not plan.blocking
    if not plan.saveable:
        plan.changes = []
        plan.optional_changes = []
    return plan


def apply_changes_to_ingredients(ingredients, plan: SubstitutionPlan) -> List[dict]:
    """A NEW ingredients list with the plan applied. Does not mutate the input.

    The caller snapshots the author's original into
    `CuratedRecipe.original_ingredients`, so aliasing the dicts here would
    quietly corrupt the very record that proves what we changed.
    """
    out = [dict(ing) if isinstance(ing, dict) else ing for ing in (ingredients or [])]
    for change in list(plan.changes) + list(plan.optional_changes):
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
