# diet_planner/services/meal_locator.py
"""Where a meal lives inside a DietaryPlan, for both plan shapes.

Pool plans (2026-09-29+): ``plan.meals`` is a flat list; every meal carries
``slot`` and ``index`` and the identifier ``<goal>:<slot>:<index>``.

Legacy day-grid plans: ``plan.days`` is a list of day dicts with dict slots
(breakfast/lunch/dinner) and list slots (small_meals/snacks); identifiers are
``<goal>:<day>:<type>:<index>`` (three-part ``<goal>:<day>:<type>`` for old
dict slots).

Every reader/writer of a plan meal — recipe detail, replace, refine, cooked
tracking, research jobs, the stale-cache repair command — goes through here so
the two contracts cannot drift apart again.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Optional

POOL_SLOTS = ('breakfast', 'lunch', 'dinner', 'small_meal', 'snack')
MAIN_SLOTS = ('breakfast', 'lunch', 'dinner')
LIST_KEY_FOR_TYPE = {'small_meal': 'small_meals', 'snack': 'snacks'}


@dataclass(frozen=True)
class MealRef:
    goal_id: int
    slot: str
    index: int
    day_number: Optional[int] = None

    @property
    def is_legacy(self) -> bool:
        return self.day_number is not None

    @property
    def identifier(self) -> str:
        if self.is_legacy:
            return f'{self.goal_id}:{self.day_number}:{self.slot}:{self.index}'
        return pool_identifier(self.goal_id, self.slot, self.index)


def pool_identifier(goal_id: int, slot: str, index: int) -> str:
    return f'{goal_id}:{slot}:{index}'


def parse_meal_identifier(value: str) -> MealRef:
    """Parse either identifier shape. Raises ValueError when malformed."""
    parts = (value or '').split(':')
    if len(parts) < 3:
        raise ValueError('meal identifier needs at least three parts')
    try:
        goal_id = int(parts[0])
    except ValueError:
        raise ValueError('meal identifier must start with the goal id') from None
    if parts[1].isdigit():
        # legacy: goal:day:type[:index]
        slot = parts[2]
        if slot not in POOL_SLOTS or len(parts) > 4:
            raise ValueError(f'unknown legacy slot {slot!r}')
        index = 0
        if len(parts) == 4 and parts[3] != '':
            try:
                index = int(parts[3])
            except ValueError:
                raise ValueError('legacy index must be an integer') from None
        return MealRef(goal_id=goal_id, slot=slot, index=index, day_number=int(parts[1]))
    slot = parts[1]
    if slot not in POOL_SLOTS or len(parts) != 3:
        raise ValueError(f'unknown pool slot {slot!r}')
    try:
        index = int(parts[2])
    except ValueError:
        raise ValueError('pool index must be an integer') from None
    return MealRef(goal_id=goal_id, slot=slot, index=index)


def plan_meals_field(plan: Any) -> str:
    """Which JSON field holds this plan's meals ('meals' or 'days')."""
    return 'meals' if getattr(plan, 'meals', None) is not None else 'days'


def _legacy_day(plan: Any, day_number: int) -> Optional[dict]:
    for day in (getattr(plan, 'days', None) or []):
        if isinstance(day, dict) and day.get('day_number') == day_number:
            return day
    return None


def _pool_position(plan: Any, ref: MealRef) -> Optional[int]:
    for i, meal in enumerate(getattr(plan, 'meals', None) or []):
        if isinstance(meal, dict) and meal.get('slot') == ref.slot and meal.get('index') == ref.index:
            return i
    return None


def locate_meal(plan: Any, ref: MealRef) -> Optional[dict]:
    """The meal dict at `ref`, or None. A legacy ref never matches a pool plan
    and vice versa — the shapes are disjoint on purpose."""
    if ref.is_legacy:
        if getattr(plan, 'meals', None) is not None:
            return None
        day = _legacy_day(plan, ref.day_number)
        if day is None:
            return None
        list_key = LIST_KEY_FOR_TYPE.get(ref.slot)
        if list_key is None:
            meal = day.get(ref.slot)
            return meal if isinstance(meal, dict) else None
        items = day.get(list_key) or []
        if not isinstance(items, list) or not (0 <= ref.index < len(items)):
            return None
        meal = items[ref.index]
        return meal if isinstance(meal, dict) else None
    if getattr(plan, 'meals', None) is None:
        return None
    pos = _pool_position(plan, ref)
    return plan.meals[pos] if pos is not None else None


def set_meal(plan: Any, ref: MealRef, meal: dict) -> bool:
    """Write `meal` at `ref`. Returns False when the position does not exist
    (nothing is appended — a swap can only replace). Pool writes stamp
    slot/index/meal_identifier onto the meal so the invariant holds."""
    if ref.is_legacy:
        if getattr(plan, 'meals', None) is not None:
            return False
        day = _legacy_day(plan, ref.day_number)
        if day is None:
            return False
        list_key = LIST_KEY_FOR_TYPE.get(ref.slot)
        if list_key is None:
            if not isinstance(day.get(ref.slot), dict):
                return False
            day[ref.slot] = meal
            return True
        items = day.get(list_key) or []
        if not (0 <= ref.index < len(items)):
            return False
        items[ref.index] = meal
        day[list_key] = items
        return True
    if getattr(plan, 'meals', None) is None:
        return False
    pos = _pool_position(plan, ref)
    if pos is None:
        return False
    meal['slot'] = ref.slot
    meal['index'] = ref.index
    meal['meal_identifier'] = ref.identifier
    plan.meals[pos] = meal
    return True


def iter_plan_meals(plan: Any) -> Iterator[dict]:
    """Every meal dict in the plan, in display order, whichever shape."""
    meals = getattr(plan, 'meals', None)
    if meals is not None:
        for m in meals:
            if isinstance(m, dict):
                yield m
        return
    for day in (getattr(plan, 'days', None) or []):
        if not isinstance(day, dict):
            continue
        for slot in MAIN_SLOTS:
            m = day.get(slot)
            if isinstance(m, dict):
                yield m
        for list_key in LIST_KEY_FOR_TYPE.values():
            for m in (day.get(list_key) or []):
                if isinstance(m, dict):
                    yield m
