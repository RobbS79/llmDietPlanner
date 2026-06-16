# Restriction Enforcement & Shopping-List Parity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop dietary restrictions from leaking into recipes, and make the shopping list always match the recipe ingredients on both LLM generation paths.

**Architecture:** One new module `diet_planner/services/restrictions.py` owns restriction parsing, validation, deterministic swaps, and repair-loop orchestration. Two existing LLM entry points (`generate_meal_plan_only`, `generate_catalog_constrained_plan`) gain a hard-rule system-prompt block driven by `ResolvedRestrictions`. The legacy task path adopts the deterministic `aggregate_ingredients_from_meals` aggregator (already used by the catalog path) and the shopping-list LLM call is fed the aggregated list instead of a truncated days summary.

**Tech Stack:** Python 3.11, Django, Celery, Gemini SDK. Tests use Django's `TestCase` + `unittest.mock`.

**Reference spec:** `docs/superpowers/specs/2026-06-13-restriction-enforcement-and-shopping-list-parity-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `diet_planner/services/restrictions.py` | Create | `ResolvedRestrictions`, `RestrictionResolver`, validator, `Violation`, `DETERMINISTIC_SWAPS`, `try_deterministic_swap`, `COMPLIANCE_MODIFIERS`, `repair_meals_with_violations` |
| `diet_planner/services/catalog.py` | Edit (~line 112–138, 253–279) | `CatalogService.build_catalog_for_prompt` accepts `exclusions`; `_filter_by_dietary_restrictions` reads `exclusions.exclusion_keywords` |
| `diet_planner/llm_service.py` | Edit | New `_build_meal_system_prompt` helper; `generate_meal_plan_only` and `generate_catalog_constrained_plan` accept `exclusions`; new `regenerate_meal`; `generate_shopping_list_with_prices` takes aggregated list |
| `diet_planner/tasks.py` | Edit (~line 1449–1493, 2049–2160) | Both task paths run resolver → generation → validator+repair → aggregator → shopping list |
| `diet_planner/tests/test_restrictions.py` | Create | Unit tests for the new module (no DB needed for most) |
| `diet_planner/tests/test_llm_service_restrictions.py` | Create | Mocked-Gemini tests for system prompt + `regenerate_meal` + shopping-list signature |
| `diet_planner/tests/test_tasks_restriction_enforcement.py` | Create | End-to-end (still mocked-Gemini) tests for both task paths including plan-#110 reproduction |

---

## Task 1: `restrictions.py` skeleton + `ResolvedRestrictions` + `RestrictionResolver.resolve` (structured field)

**Files:**
- Create: `diet_planner/services/restrictions.py`
- Create: `diet_planner/tests/test_restrictions.py`

- [ ] **Step 1: Write the failing test**

`diet_planner/tests/test_restrictions.py`:

```python
"""Unit tests for diet_planner.services.restrictions."""
from unittest.mock import MagicMock

import pytest

from diet_planner.services.restrictions import (
    ResolvedRestrictions,
    RestrictionResolver,
)


def _goal(prompt: str = "", dietary_restrictions: str = ""):
    g = MagicMock()
    g.prompt = prompt
    g.dietary_restrictions = dietary_restrictions
    return g


class TestRestrictionResolverStructured:
    def test_empty_goal_yields_empty_restrictions(self):
        result = RestrictionResolver().resolve(_goal())
        assert result == ResolvedRestrictions(
            tags=frozenset(),
            exclusion_keywords=frozenset(),
            freeform_allergens=frozenset(),
        )

    def test_structured_field_gluten_free(self):
        result = RestrictionResolver().resolve(
            _goal(dietary_restrictions="gluten_free")
        )
        assert "gluten_free" in result.tags
        # DIETARY_EXCLUSIONS['gluten_free'] keywords must all be present
        assert "mouka" in result.exclusion_keywords
        assert "flour" in result.exclusion_keywords
        assert "pšenič" in result.exclusion_keywords

    def test_structured_field_multiple_tags(self):
        result = RestrictionResolver().resolve(
            _goal(dietary_restrictions="vegan, gluten_free")
        )
        assert result.tags == frozenset({"vegan", "gluten_free"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest diet_planner/tests/test_restrictions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'diet_planner.services.restrictions'`

- [ ] **Step 3: Write minimal implementation**

`diet_planner/services/restrictions.py`:

```python
"""Dietary restriction resolution, validation, and repair.

Single source of truth for everything restriction-related. Used by:
- CatalogService to filter the product catalog
- GeminiService to inject restriction rules into meal-plan prompts
- The post-generation validator that rejects/repairs violating meals
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from diet_planner.services.catalog import DIETARY_EXCLUSIONS

if TYPE_CHECKING:
    from diet_planner.models import DietaryGoal


@dataclass(frozen=True)
class ResolvedRestrictions:
    """Normalized dietary restrictions for one DietaryGoal.

    `tags` are the canonical restriction names (e.g. 'gluten_free').
    `exclusion_keywords` is the union of DIETARY_EXCLUSIONS for those tags
    plus any freeform allergens, all lowercased, ready for substring match.
    `freeform_allergens` is the set of allergen tokens parsed from prose
    (kept separate so callers can render them distinctly in prompts).
    """

    tags: frozenset[str]
    exclusion_keywords: frozenset[str]
    freeform_allergens: frozenset[str]


class RestrictionResolver:
    """Resolve a DietaryGoal into a normalized ResolvedRestrictions value."""

    def resolve(self, goal: "DietaryGoal") -> ResolvedRestrictions:
        tags: set[str] = set()

        structured = (getattr(goal, "dietary_restrictions", "") or "").lower()
        for tag in DIETARY_EXCLUSIONS.keys():
            if tag in structured:
                tags.add(tag)

        exclusion_keywords: set[str] = set()
        for tag in tags:
            exclusion_keywords.update(
                kw.lower() for kw in DIETARY_EXCLUSIONS[tag]
            )

        return ResolvedRestrictions(
            tags=frozenset(tags),
            exclusion_keywords=frozenset(exclusion_keywords),
            freeform_allergens=frozenset(),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest diet_planner/tests/test_restrictions.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/restrictions.py diet_planner/tests/test_restrictions.py
git commit -m "feat(restrictions): add RestrictionResolver with structured-field parsing"
```

---

## Task 2: `RestrictionResolver` — freeform prompt parsing (Czech + English)

**Files:**
- Modify: `diet_planner/services/restrictions.py`
- Modify: `diet_planner/tests/test_restrictions.py`

- [ ] **Step 1: Write the failing test**

Append to `test_restrictions.py`:

```python
class TestRestrictionResolverFreeform:
    def test_prompt_only_czech_gluten_free(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="Chci bezlepkový jídelníček, mám celiakii.")
        )
        assert "gluten_free" in result.tags
        assert "mouka" in result.exclusion_keywords

    def test_prompt_only_english_vegan(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="Make me a vegan meal plan please")
        )
        assert "vegan" in result.tags

    def test_prompt_and_structured_field_union(self):
        result = RestrictionResolver().resolve(
            _goal(
                prompt="bez lepku",
                dietary_restrictions="vegan",
            )
        )
        assert result.tags == frozenset({"vegan", "gluten_free"})

    def test_freeform_allergen_peanut(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="Alergie na arašídy a sezam.")
        )
        assert "peanut" in result.freeform_allergens
        assert "sesame" in result.freeform_allergens
        # Allergens also flow into exclusion_keywords for the validator
        assert "arašíd" in result.exclusion_keywords
        assert "sezam" in result.exclusion_keywords

    def test_freeform_allergen_english(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="I'm allergic to soy and shellfish.")
        )
        assert "soy" in result.freeform_allergens
        assert "shellfish" in result.freeform_allergens

    def test_unknown_word_is_ignored(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="Allergic to xylophone")
        )
        assert result.freeform_allergens == frozenset()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest diet_planner/tests/test_restrictions.py::TestRestrictionResolverFreeform -v`
Expected: FAIL — tags not picked up from prompt and `freeform_allergens` always empty.

- [ ] **Step 3: Write minimal implementation**

In `diet_planner/services/restrictions.py`, add module-level constants and extend `resolve`:

```python
# Same shape as recipe_retrieval._DIETARY_KEYWORDS but consolidated here so
# the catalog filter, the validator, and recipe retrieval can't drift apart.
# Substring match, case-folded, Czech + English.
_TAG_KEYWORDS: dict[str, str] = {
    "vegan": "vegan", "vegán": "vegan", "rostlinn": "vegan",
    "vegetari": "vegetarian", "bezmas": "vegetarian",
    "gluten": "gluten_free", "lepek": "gluten_free", "bezlepk": "gluten_free",
    "celiak": "gluten_free",
    "lakt": "lactose_free", "lactose": "lactose_free",
    "dairy": "lactose_free", "bez mlék": "lactose_free", "mléčn": "lactose_free",
}

# Fixed allergen vocabulary. Each entry maps a recognised phrasing fragment
# to (canonical_allergen, ingredient_keywords_to_block). We deliberately keep
# this small and explicit — this is NOT a general NLU.
_ALLERGEN_VOCAB: dict[str, tuple[str, tuple[str, ...]]] = {
    # peanuts
    "arašíd":   ("peanut", ("arašíd", "peanut")),
    "burský":   ("peanut", ("arašíd", "peanut")),
    "peanut":   ("peanut", ("arašíd", "peanut")),
    # tree nuts
    "ořech":    ("nuts", ("ořech", "nut", "mandle", "almond", "kešu", "cashew")),
    "nut":      ("nuts", ("ořech", "nut", "mandle", "almond", "kešu", "cashew")),
    "mandle":   ("nuts", ("ořech", "nut", "mandle", "almond")),
    "almond":   ("nuts", ("ořech", "nut", "mandle", "almond")),
    # soy
    "sója":     ("soy", ("sója", "soja", "soy", "tofu")),
    "soja":     ("soy", ("sója", "soja", "soy", "tofu")),
    "soy":      ("soy", ("sója", "soja", "soy", "tofu")),
    # sesame
    "sezam":    ("sesame", ("sezam", "sesame", "tahini")),
    "sesame":   ("sesame", ("sezam", "sesame", "tahini")),
    # eggs (separate from dairy/lactose)
    "vejce":    ("egg", ("vejce", "vajíčk", "egg")),
    "vajíčk":   ("egg", ("vejce", "vajíčk", "egg")),
    "egg":      ("egg", ("vejce", "vajíčk", "egg")),
    # shellfish / fish
    "krevet":   ("shellfish", ("krevet", "shrimp", "garnát", "humra", "lobster")),
    "shellfish":("shellfish", ("krevet", "shrimp", "garnát", "humra", "lobster")),
    "shrimp":   ("shellfish", ("krevet", "shrimp", "garnát", "humra", "lobster")),
    # fish
    "ryb":      ("fish", ("ryb", "fish", "losos", "salmon", "tuňák", "tuna")),
    "fish":     ("fish", ("ryb", "fish", "losos", "salmon", "tuňák", "tuna")),
}

# Phrase patterns that announce an allergy/avoidance. Tokens following these
# (in the same sentence) are checked against _ALLERGEN_VOCAB.
_ALLERGY_TRIGGERS: tuple[str, ...] = (
    "alergi",          # "alergie na X", "alergický na X"
    "intoleran",       # "intolerance na X"
    "bez ",            # "bez ořechů" — only when followed by allergen vocab
    "allergic",        # "allergic to X"
    "allergy",         # "X allergy"
    "intolerant",      # "intolerant to X"
    "-free",           # "soy-free" (suffix trigger handled separately)
)
```

Add a helper method and extend `resolve`:

```python
class RestrictionResolver:
    def resolve(self, goal: "DietaryGoal") -> ResolvedRestrictions:
        tags: set[str] = set()

        structured = (getattr(goal, "dietary_restrictions", "") or "").lower()
        prompt = (getattr(goal, "prompt", "") or "").lower()
        combined_for_tags = f"{structured} {prompt}"

        for needle, tag in _TAG_KEYWORDS.items():
            if needle in combined_for_tags:
                tags.add(tag)
        for tag in DIETARY_EXCLUSIONS.keys():
            if tag in structured:
                tags.add(tag)

        allergens, allergen_keywords = self._parse_freeform_allergens(prompt)

        exclusion_keywords: set[str] = set()
        for tag in tags:
            exclusion_keywords.update(
                kw.lower() for kw in DIETARY_EXCLUSIONS[tag]
            )
        exclusion_keywords.update(allergen_keywords)

        return ResolvedRestrictions(
            tags=frozenset(tags),
            exclusion_keywords=frozenset(exclusion_keywords),
            freeform_allergens=frozenset(allergens),
        )

    @staticmethod
    def _parse_freeform_allergens(text: str) -> tuple[set[str], set[str]]:
        """Return (canonical_allergens, ingredient_keywords) for prompt prose.

        Only words mentioned NEAR an allergy/avoidance trigger word are
        considered — bare 'eggs' in a recipe-style prompt is not an allergy.
        """
        if not text:
            return set(), set()

        allergens: set[str] = set()
        keywords: set[str] = set()

        # 1. Sentence-level proximity: split on sentence-ish boundaries.
        for chunk in _split_sentences(text):
            if not any(trig in chunk for trig in _ALLERGY_TRIGGERS):
                continue
            for needle, (canonical, kws) in _ALLERGEN_VOCAB.items():
                if needle in chunk:
                    allergens.add(canonical)
                    keywords.update(kws)

        # 2. "<X>-free" suffix anywhere.
        for needle, (canonical, kws) in _ALLERGEN_VOCAB.items():
            if f"{needle}-free" in text or f"{needle} free" in text:
                allergens.add(canonical)
                keywords.update(kws)

        return allergens, keywords


def _split_sentences(text: str) -> list[str]:
    """Cheap sentence-ish splitter. Good enough for prose; not a real NLP."""
    out: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in ".!?;\n":
            out.append("".join(buf))
            buf = []
    if buf:
        out.append("".join(buf))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest diet_planner/tests/test_restrictions.py -v`
Expected: PASS — all tests green.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/restrictions.py diet_planner/tests/test_restrictions.py
git commit -m "feat(restrictions): freeform prompt + allergen parsing (Czech + English)"
```

---

## Task 3: `Violation` + `validate_meal_against_exclusions` (with compliance-modifier suppression)

**Files:**
- Modify: `diet_planner/services/restrictions.py`
- Modify: `diet_planner/tests/test_restrictions.py`

- [ ] **Step 1: Write the failing test**

Append to `test_restrictions.py`:

```python
from diet_planner.services.restrictions import (
    COMPLIANCE_MODIFIERS,
    Violation,
    validate_meal_against_exclusions,
)


def _meal(name="Test meal", ingredients=None, instructions=None):
    return {
        "name": name,
        "ingredients": ingredients or [],
        "instructions": instructions or [],
    }


class TestValidator:
    def test_compliant_meal_has_no_violations(self):
        meal = _meal(
            ingredients=[{"name": "kuřecí prsa", "quantity": 200, "unit": "g"}],
            instructions=["Osol kuře a opeč."],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouka", "flour"}))
        assert violations == []

    def test_flour_in_ingredients_is_flagged(self):
        meal = _meal(
            ingredients=[{"name": "pšeničná mouka", "quantity": 100, "unit": "g"}],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouka"}))
        assert len(violations) == 1
        assert violations[0].matched_keyword == "mouka"
        assert violations[0].matched_in == "ingredients"

    def test_flour_in_instructions_is_flagged(self):
        meal = _meal(
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s moukou."],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouk"}))
        assert len(violations) == 1
        assert violations[0].matched_in == "instructions"

    def test_compliance_modifier_suppresses_match(self):
        # 'bezlepková mouka' contains 'mouka' but the bezlepk- modifier
        # legitimises it — no violation.
        meal = _meal(
            ingredients=[{"name": "bezlepková mouka", "quantity": 100, "unit": "g"}],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouka"}))
        assert violations == []

    def test_compliance_modifier_only_suppresses_for_modified_token(self):
        # 'bezlepková mouka, obyčejná mouka' — second one MUST still flag.
        meal = _meal(
            ingredients=[
                {"name": "bezlepková mouka", "quantity": 100, "unit": "g"},
                {"name": "obyčejná mouka", "quantity": 100, "unit": "g"},
            ],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouka"}))
        assert len(violations) == 1
        assert violations[0].ingredient_name == "obyčejná mouka"

    def test_compliance_modifiers_constant_exists(self):
        # Smoke test: every supported tag has a modifier list.
        for tag in ("gluten_free", "lactose_free", "vegan"):
            assert tag in COMPLIANCE_MODIFIERS
            assert len(COMPLIANCE_MODIFIERS[tag]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest diet_planner/tests/test_restrictions.py::TestValidator -v`
Expected: FAIL — `ImportError: cannot import name 'Violation'` (and friends).

- [ ] **Step 3: Write minimal implementation**

Add to `diet_planner/services/restrictions.py`:

```python
# Per-tag prefixes that mark an otherwise-forbidden token as legitimate.
# Substring match, case-folded. Order doesn't matter; presence does.
COMPLIANCE_MODIFIERS: dict[str, tuple[str, ...]] = {
    "gluten_free":  ("bezlepk", "gluten-free", "gluten free", " gf "),
    "lactose_free": ("bezlaktóz", "lactose-free", "lactose free"),
    "dairy_free":   ("bez mlék", "dairy-free", "dairy free"),
    "vegan":        ("veganské", "veganská", "veganský", "vegan"),
    "vegetarian":   ("vegetariánsk",),
}

# Tags that have COMPLIANCE_MODIFIERS — used by the validator. Other tags
# (egg/peanut allergies, etc.) get no modifier — there's no compliant
# variant of "egg" for an egg allergy.
_TAGS_WITH_MODIFIERS = frozenset(COMPLIANCE_MODIFIERS.keys())


@dataclass(frozen=True)
class Violation:
    meal_key: str             # 'day_2.lunch' set by caller; '' from validator
    matched_keyword: str
    matched_in: str           # 'ingredients' | 'instructions'
    ingredient_name: str | None
    source_text: str          # the offending string for debug


def validate_meal_against_exclusions(
    meal: dict,
    exclusion_keywords: frozenset[str],
    *,
    meal_key: str = "",
) -> list[Violation]:
    """Scan a meal dict for any forbidden keyword.

    A keyword is suppressed if the string under inspection contains a
    compliance modifier for ANY supported tag at any position before the
    keyword. Substring match, case-folded.
    """
    if not exclusion_keywords:
        return []

    violations: list[Violation] = []

    for ing in meal.get("ingredients", []) or []:
        name = (ing.get("name") if isinstance(ing, dict) else "") or ""
        text = name.lower()
        for kw in exclusion_keywords:
            if kw not in text:
                continue
            if _is_compliance_modified(text, kw):
                continue
            violations.append(
                Violation(
                    meal_key=meal_key,
                    matched_keyword=kw,
                    matched_in="ingredients",
                    ingredient_name=name,
                    source_text=name,
                )
            )

    for line in meal.get("instructions", []) or []:
        if not isinstance(line, str):
            continue
        text = line.lower()
        for kw in exclusion_keywords:
            if kw not in text:
                continue
            if _is_compliance_modified(text, kw):
                continue
            violations.append(
                Violation(
                    meal_key=meal_key,
                    matched_keyword=kw,
                    matched_in="instructions",
                    ingredient_name=None,
                    source_text=line,
                )
            )

    return violations


def _is_compliance_modified(text_lower: str, keyword: str) -> bool:
    """True iff some compliance modifier appears in `text_lower` before
    `keyword`. Uses the first occurrence of `keyword`."""
    kw_pos = text_lower.find(keyword)
    if kw_pos < 0:
        return False
    head = text_lower[:kw_pos]
    for mods in COMPLIANCE_MODIFIERS.values():
        for m in mods:
            if m in head:
                return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest diet_planner/tests/test_restrictions.py::TestValidator -v`
Expected: PASS — all 6 tests green.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/restrictions.py diet_planner/tests/test_restrictions.py
git commit -m "feat(restrictions): meal validator with compliance-modifier suppression"
```

---

## Task 4: `DETERMINISTIC_SWAPS` + `try_deterministic_swap` + anti-rot test

**Files:**
- Modify: `diet_planner/services/restrictions.py`
- Modify: `diet_planner/tests/test_restrictions.py`

- [ ] **Step 1: Write the failing test**

Append to `test_restrictions.py`:

```python
from diet_planner.services.restrictions import (
    DETERMINISTIC_SWAPS,
    try_deterministic_swap,
)


class TestDeterministicSwap:
    def test_gluten_free_flour_swap(self):
        meal = _meal(
            ingredients=[{"name": "pšeničná mouka", "quantity": 100, "unit": "g"}],
        )
        violation = Violation(
            meal_key="day_1.lunch",
            matched_keyword="mouka",
            matched_in="ingredients",
            ingredient_name="pšeničná mouka",
            source_text="pšeničná mouka",
        )
        swapped = try_deterministic_swap(
            meal, violation, tags=frozenset({"gluten_free"})
        )
        assert swapped is not None
        names = [i["name"] for i in swapped["ingredients"]]
        assert names == ["bezlepková mouka"]

    def test_vegan_meat_violation_has_no_swap(self):
        meal = _meal(
            ingredients=[{"name": "kuřecí prsa", "quantity": 200, "unit": "g"}],
        )
        violation = Violation(
            meal_key="day_1.dinner",
            matched_keyword="kuřecí",
            matched_in="ingredients",
            ingredient_name="kuřecí prsa",
            source_text="kuřecí prsa",
        )
        swapped = try_deterministic_swap(
            meal, violation, tags=frozenset({"vegan"})
        )
        assert swapped is None  # no swap exists — caller must re-prompt

    def test_instructions_violation_has_no_swap(self):
        # Swaps only fix ingredients[]; instruction-only violations always
        # require re-prompt.
        meal = _meal(
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s pšeničnou moukou."],
        )
        violation = Violation(
            meal_key="day_1.lunch",
            matched_keyword="mouka",
            matched_in="instructions",
            ingredient_name=None,
            source_text="Smíchej s pšeničnou moukou.",
        )
        swapped = try_deterministic_swap(
            meal, violation, tags=frozenset({"gluten_free"})
        )
        assert swapped is None

    def test_anti_rot_every_swap_target_validates_clean(self):
        """Swap targets must NOT trigger the validator for their own tag.

        Catches both 'we forgot the compliance modifier' and 'we swapped
        flour → wheat flour'. If this test fails, the swap is bogus.
        """
        for tag, mapping in DETERMINISTIC_SWAPS.items():
            exclusion = frozenset(
                kw.lower() for kw in
                __import__("diet_planner.services.catalog", fromlist=["DIETARY_EXCLUSIONS"]).DIETARY_EXCLUSIONS[tag]
            )
            for source, target in mapping.items():
                meal = _meal(ingredients=[{"name": target, "quantity": 1, "unit": "g"}])
                violations = validate_meal_against_exclusions(meal, exclusion)
                assert violations == [], (
                    f"Swap target {target!r} (from {source!r} for tag {tag!r}) "
                    f"itself triggers the validator: {violations}"
                )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest diet_planner/tests/test_restrictions.py::TestDeterministicSwap -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Add to `diet_planner/services/restrictions.py`:

```python
# Map of (tag -> {forbidden_keyword -> compliant_replacement_phrase}).
# Replacement phrases MUST include a COMPLIANCE_MODIFIERS[tag] prefix so the
# validator does not re-flag them — the anti-rot test enforces this.
DETERMINISTIC_SWAPS: dict[str, dict[str, str]] = {
    "gluten_free": {
        "mouka":      "bezlepková mouka",
        "těstoviny":  "bezlepkové těstoviny",
        "chléb":      "bezlepkový chléb",
        "rohlík":     "bezlepkový rohlík",
        "houska":     "bezlepková houska",
        "pečivo":     "bezlepkové pečivo",
        "flour":      "gluten-free flour",
        "pasta":      "gluten-free pasta",
        "bread":      "gluten-free bread",
        "roll":       "gluten-free roll",
    },
    "lactose_free": {
        "mléko":      "bezlaktózové mléko",
        "smetana":    "bezlaktózová smetana",
        "jogurt":     "bezlaktózový jogurt",
        "tvaroh":     "bezlaktózový tvaroh",
        "milk":       "lactose-free milk",
        "cream":      "lactose-free cream",
        "yogurt":     "lactose-free yogurt",
    },
    # vegan / vegetarian: no clean 1:1 swap (chicken → ??). Re-prompt path.
}


def try_deterministic_swap(
    meal: dict,
    violation: Violation,
    *,
    tags: frozenset[str],
) -> dict | None:
    """Return a patched meal if a clean 1:1 swap applies, else None.

    Only works for `ingredients[]` violations. Instruction violations
    always go through the LLM re-prompt path — we won't rewrite prose.
    """
    if violation.matched_in != "ingredients":
        return None
    if violation.ingredient_name is None:
        return None

    for tag in tags:
        mapping = DETERMINISTIC_SWAPS.get(tag)
        if not mapping:
            continue
        replacement = mapping.get(violation.matched_keyword)
        if not replacement:
            continue
        patched = dict(meal)
        patched["ingredients"] = [
            ({**ing, "name": replacement}
             if isinstance(ing, dict) and ing.get("name") == violation.ingredient_name
             else ing)
            for ing in (meal.get("ingredients") or [])
        ]
        return patched

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest diet_planner/tests/test_restrictions.py::TestDeterministicSwap -v`
Expected: PASS — 4 tests green, including anti-rot.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/restrictions.py diet_planner/tests/test_restrictions.py
git commit -m "feat(restrictions): deterministic 1:1 swap map + anti-rot guarantee"
```

---

## Task 5: Refactor `CatalogService` to consume `ResolvedRestrictions`

**Files:**
- Modify: `diet_planner/services/catalog.py` (lines ~112–155, ~253–279)
- Create: `diet_planner/tests/test_catalog_restrictions.py`

- [ ] **Step 1: Write the failing test**

`diet_planner/tests/test_catalog_restrictions.py`:

```python
"""CatalogService now consumes ResolvedRestrictions instead of reading
goal.dietary_restrictions directly."""
from unittest.mock import MagicMock

from diet_planner.services.catalog import CatalogService
from diet_planner.services.restrictions import ResolvedRestrictions


def _goal():
    g = MagicMock()
    g.id = 1
    g.shop = "rohlik"
    g.dietary_restrictions = ""  # intentionally empty
    g.prompt = "bezlepkový týden"
    return g


class TestCatalogConsumesResolvedRestrictions:
    def test_filter_uses_exclusions_argument_not_goal_field(self, monkeypatch):
        # Stub _load_products so we don't need the DB
        flour = {"name": "pšeničná mouka", "display_name": "Hladká mouka"}
        chicken = {"name": "kuřecí prsa", "display_name": "Kuřecí prso"}
        rice = {"name": "rýže", "display_name": "Basmati rýže"}
        monkeypatch.setattr(
            CatalogService,
            "_load_products",
            lambda self, goal: [flour, chicken, rice],
        )
        monkeypatch.setattr(
            CatalogService,
            "_get_pantry_staples",
            lambda self, goal: [],
        )

        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "flour"}),
            freeform_allergens=frozenset(),
        )
        result = CatalogService().build_catalog_for_prompt(
            _goal(), exclusions=exclusions
        )

        flat = [
            p for items in result["products_by_category"].values() for p in items
        ]
        names = [p["name"] for p in flat]
        assert "kuřecí prsa" in names
        assert "rýže" in names
        assert "pšeničná mouka" not in names  # filtered out

    def test_no_exclusions_returns_unfiltered(self, monkeypatch):
        flour = {"name": "pšeničná mouka", "display_name": "Hladká mouka"}
        monkeypatch.setattr(CatalogService, "_load_products", lambda self, goal: [flour])
        monkeypatch.setattr(CatalogService, "_get_pantry_staples", lambda self, goal: [])

        result = CatalogService().build_catalog_for_prompt(_goal(), exclusions=None)
        flat = [p for items in result["products_by_category"].values() for p in items]
        assert any(p["name"] == "pšeničná mouka" for p in flat)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest diet_planner/tests/test_catalog_restrictions.py -v`
Expected: FAIL — `build_catalog_for_prompt` does not accept `exclusions`.

- [ ] **Step 3: Modify `CatalogService.build_catalog_for_prompt`**

Open `diet_planner/services/catalog.py`. Replace the signature and the call to `_filter_by_dietary_restrictions`:

```python
def build_catalog_for_prompt(
    self,
    goal: DietaryGoal,
    max_products: int = 500,
    exclusions: "ResolvedRestrictions | None" = None,
) -> Dict[str, Any]:
    """
    Build a catalog suitable for injecting into the LLM prompt.

    `exclusions` is the resolved restriction set. If None, no dietary
    filter is applied. Callers should pass the result of
    RestrictionResolver().resolve(goal) — see services/restrictions.py.
    """
    products = self._load_products(goal)
    products = self._filter_by_exclusions(products, exclusions)
    categorized = self._categorize(products)
    limited = self._limit_products(categorized, max_products)
    # ... unchanged tail ...
```

Replace `_filter_by_dietary_restrictions` with a new method that consumes the resolved set:

```python
def _filter_by_exclusions(
    self,
    products: List[Dict[str, Any]],
    exclusions: "ResolvedRestrictions | None",
) -> List[Dict[str, Any]]:
    if exclusions is None or not exclusions.exclusion_keywords:
        return products

    exclude_keywords = exclusions.exclusion_keywords
    filtered = []
    for p in products:
        name_lower = p["name"].lower()
        display_lower = (p.get("display_name") or "").lower()
        combined = f"{name_lower} {display_lower}"
        if not any(kw in combined for kw in exclude_keywords):
            filtered.append(p)

    logger.info(
        f"Dietary filter: {len(products)} -> {len(filtered)} products "
        f"(excluded {len(exclude_keywords)} keywords)"
    )
    return filtered
```

Add the lazy import at the top of `catalog.py` (TYPE_CHECKING is fine):

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from diet_planner.services.restrictions import ResolvedRestrictions
```

Delete the old `_filter_by_dietary_restrictions` method.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest diet_planner/tests/test_catalog_restrictions.py -v`
Expected: PASS — 2 tests green.

Also run the existing catalog test file to ensure no regression:
Run: `pytest diet_planner/tests/test_catalog_constrained.py -v`
Expected: PASS (any failures should be fixed by passing `exclusions=None`).

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/catalog.py diet_planner/tests/test_catalog_restrictions.py
git commit -m "refactor(catalog): build_catalog_for_prompt consumes ResolvedRestrictions"
```

---

## Task 6: `_build_meal_system_prompt` helper extracted from existing prompts

**Files:**
- Modify: `diet_planner/llm_service.py` (~line 350–399 and ~1476–1521)
- Create: `diet_planner/tests/test_llm_service_restrictions.py`

- [ ] **Step 1: Write the failing test**

`diet_planner/tests/test_llm_service_restrictions.py`:

```python
"""System-prompt construction tests for the meal-plan LLM calls."""
from unittest.mock import MagicMock

from diet_planner.llm_service import GeminiService
from diet_planner.services.restrictions import ResolvedRestrictions


def _goal(**overrides):
    g = MagicMock()
    g.language_code = "cs"
    g.country = "CZ"
    g.num_days = 7
    g.shop = "rohlik"
    for k, v in overrides.items():
        setattr(g, k, v)
    return g


class TestBuildMealSystemPrompt:
    def test_no_exclusions_omits_restriction_block(self):
        svc = GeminiService()
        prompt = svc._build_meal_system_prompt(
            goal=_goal(), exclusions=None, shop_url="https://x.example",
        )
        assert "DIETARY RESTRICTIONS" not in prompt

    def test_gluten_free_adds_hard_rule_block_with_keywords(self):
        svc = GeminiService()
        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "flour", "wheat"}),
            freeform_allergens=frozenset(),
        )
        prompt = svc._build_meal_system_prompt(
            goal=_goal(), exclusions=exclusions, shop_url="https://x.example",
        )
        assert "DIETARY RESTRICTIONS" in prompt
        assert "gluten_free" in prompt
        # all keywords surfaced for the model
        assert "mouka" in prompt
        assert "flour" in prompt
        assert "wheat" in prompt

    def test_freeform_allergens_appear_in_block(self):
        svc = GeminiService()
        exclusions = ResolvedRestrictions(
            tags=frozenset(),
            exclusion_keywords=frozenset({"arašíd", "peanut"}),
            freeform_allergens=frozenset({"peanut"}),
        )
        prompt = svc._build_meal_system_prompt(
            goal=_goal(), exclusions=exclusions, shop_url="https://x.example",
        )
        assert "ALLERG" in prompt.upper()
        assert "peanut" in prompt

    def test_single_meal_mode_changes_output_schema_hint(self):
        svc = GeminiService()
        prompt = svc._build_meal_system_prompt(
            goal=_goal(), exclusions=None, shop_url="https://x.example",
            single_meal=True,
        )
        # In single-meal mode we expect a single meal object, not a days array
        assert "days" not in prompt.lower() or "single meal" in prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest diet_planner/tests/test_llm_service_restrictions.py::TestBuildMealSystemPrompt -v`
Expected: FAIL — `AttributeError: 'GeminiService' object has no attribute '_build_meal_system_prompt'`.

- [ ] **Step 3: Add the helper method to `GeminiService`**

In `diet_planner/llm_service.py`, add this method to the `GeminiService` class (near the existing `generate_meal_plan_only`):

```python
def _build_meal_system_prompt(
    self,
    *,
    goal: Any,
    exclusions: "Optional[ResolvedRestrictions]",
    shop_url: Optional[str] = None,
    catalog_text: Optional[str] = None,
    single_meal: bool = False,
) -> str:
    """Build the system prompt for meal generation.

    Shared by generate_meal_plan_only (URL browsing), generate_catalog_
    constrained_plan (catalog text), and regenerate_meal (single-meal
    repair). The restriction block is injected when exclusions is non-
    empty; this is the ONE place the rule lives.
    """
    language_names = {
        "cs": "Czech", "sk": "Slovak", "pl": "Polish",
        "hu": "Hungarian", "ro": "Romanian", "bg": "Bulgarian",
        "de": "German", "en": "English",
    }
    target_language = language_names.get(
        getattr(goal, "language_code", "en") or "en", "English"
    )
    num_days = getattr(goal, "num_days", 7)

    restriction_block = self._format_restriction_block(exclusions)

    if single_meal:
        schema_hint = (
            "OUTPUT: a SINGLE meal JSON object with keys "
            "name, description, food_category, preparation_time, "
            "ingredients[], instructions[], nutritional_info."
        )
        scope_line = "TASK: produce ONE replacement meal honoring all rules."
    else:
        schema_hint = (
            'OUTPUT: {"days": [{"day_number": 1, "breakfast": {...}, '
            '"lunch": {...}, "dinner": {...}, "small_meals": [...], '
            '"snacks": [...]}, ...]}'
        )
        scope_line = f"TASK: generate a {num_days}-day meal plan."

    source_line = (
        f"Browse {shop_url} for context but don't list prices."
        if shop_url
        else f"Use ONLY the AVAILABLE PRODUCTS list below.\n\n{catalog_text or ''}"
    )

    return (
        f"You are a nutrition expert creating meal plans.\n\n"
        f"RESPONSE FORMAT: Valid JSON only, no markdown, all text in {target_language}.\n\n"
        f"{scope_line}\n"
        f"{schema_hint}\n\n"
        f"{source_line}\n\n"
        f"{restriction_block}"
        f"CRITICAL RULES:\n"
        f"- Keep instructions VERY BRIEF: 3 steps maximum per meal\n"
        f"- Keep descriptions to 1 sentence\n"
        f"\n"
        f"INGREDIENT CONSISTENCY (production-critical, do not violate):\n"
        f"- ingredients[] MUST list ONLY raw items the user has to buy fresh\n"
        f"  at the store for THIS meal.\n"
        f"- A meal that reuses a leftover from another day MUST exclude that\n"
        f"  leftover from ingredients[]."
    )


@staticmethod
def _format_restriction_block(
    exclusions: "Optional[ResolvedRestrictions]",
) -> str:
    if exclusions is None or not exclusions.exclusion_keywords:
        return ""
    tags_str = ", ".join(sorted(exclusions.tags)) or "(none)"
    allergens_line = ""
    if exclusions.freeform_allergens:
        allergens_line = (
            "- The user has reported ALLERGIES to: "
            f"{', '.join(sorted(exclusions.freeform_allergens))}.\n"
        )
    kw_str = ", ".join(sorted(exclusions.exclusion_keywords))
    return (
        "DIETARY RESTRICTIONS (non-negotiable, hard rule):\n"
        f"- The user requires: {tags_str}.\n"
        f"{allergens_line}"
        f"- The following ingredient keywords are FORBIDDEN in ingredients[]\n"
        f"  AND instructions[] for ALL meals: {kw_str}.\n"
        "- If a traditional recipe would require a forbidden ingredient,\n"
        "  substitute a compliant alternative (e.g. bezlepková mouka instead\n"
        "  of mouka). Generated meals containing any forbidden keyword will\n"
        "  be REJECTED.\n\n"
    )
```

Add the import at the top of the file (or under TYPE_CHECKING if a circular import bites):

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from diet_planner.services.restrictions import ResolvedRestrictions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest diet_planner/tests/test_llm_service_restrictions.py::TestBuildMealSystemPrompt -v`
Expected: PASS — 4 tests green.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/llm_service.py diet_planner/tests/test_llm_service_restrictions.py
git commit -m "feat(llm_service): _build_meal_system_prompt helper with restriction block"
```

---

## Task 7: Wire `exclusions` into `generate_meal_plan_only` and `generate_catalog_constrained_plan`

**Files:**
- Modify: `diet_planner/llm_service.py`
- Modify: `diet_planner/tests/test_llm_service_restrictions.py`

- [ ] **Step 1: Write the failing test**

Append to `test_llm_service_restrictions.py`:

```python
class TestGenerateMealPlanOnlyUsesExclusions:
    def test_passes_restriction_block_via_system_instruction(self, monkeypatch):
        svc = GeminiService()
        captured = {}

        class FakeModel:
            def __init__(self, model_name, system_instruction):
                captured["system_instruction"] = system_instruction
            def generate_content(self, *a, **kw):
                resp = MagicMock()
                resp.candidates = [MagicMock(finish_reason=MagicMock(name="OK"))]
                resp.text = '{"days": []}'
                resp.usage_metadata = MagicMock(
                    prompt_token_count=1, candidates_token_count=1
                )
                return resp

        import diet_planner.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.genai, "GenerativeModel", FakeModel)

        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "flour"}),
            freeform_allergens=frozenset(),
        )
        svc.generate_meal_plan_only(
            user_prompt="bezlepkový týden",
            shop_url="https://x.example",
            goal=_goal(),
            exclusions=exclusions,
        )
        assert "DIETARY RESTRICTIONS" in captured["system_instruction"]
        assert "mouka" in captured["system_instruction"]


class TestGenerateCatalogConstrainedPlanUsesExclusions:
    def test_passes_restriction_block_via_system_instruction(self, monkeypatch):
        svc = GeminiService()
        captured = {}

        class FakeModel:
            def __init__(self, model_name, system_instruction):
                captured["system_instruction"] = system_instruction
            def generate_content(self, *a, **kw):
                resp = MagicMock()
                resp.candidates = [MagicMock(finish_reason=MagicMock(name="OK"))]
                resp.text = '{"days": []}'
                resp.usage_metadata = MagicMock(
                    prompt_token_count=1, candidates_token_count=1
                )
                return resp

        import diet_planner.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.genai, "GenerativeModel", FakeModel)

        exclusions = ResolvedRestrictions(
            tags=frozenset({"vegan"}),
            exclusion_keywords=frozenset({"kuřecí", "chicken"}),
            freeform_allergens=frozenset(),
        )
        svc.generate_catalog_constrained_plan(
            user_prompt="vegan",
            catalog_text="#1 rice\n#2 beans",
            goal=_goal(),
            exclusions=exclusions,
        )
        assert "DIETARY RESTRICTIONS" in captured["system_instruction"]
        assert "kuřecí" in captured["system_instruction"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest diet_planner/tests/test_llm_service_restrictions.py -k Uses -v`
Expected: FAIL — `unexpected keyword argument 'exclusions'`.

- [ ] **Step 3: Update both methods**

In `diet_planner/llm_service.py`:

```python
def generate_meal_plan_only(
    self,
    user_prompt: str,
    shop_url: str,
    goal: Any,
    model: Optional[str] = None,
    exclusions: "Optional[ResolvedRestrictions]" = None,
) -> Dict[str, Any]:
    model = model or self.default_model
    system_prompt = self._build_meal_system_prompt(
        goal=goal, exclusions=exclusions, shop_url=shop_url, single_meal=False,
    )
    full_prompt = (
        f"{user_prompt}\n\n"
        f"Create meal plan with recipes from {shop_url}.\n"
        f"Keep all text concise - 3 steps max per recipe, 1 sentence descriptions."
    )
    # ... existing Gemini call + parse + return unchanged ...
```

Likewise replace the inline `system_prompt = f"""..."""` in
`generate_catalog_constrained_plan` with:

```python
def generate_catalog_constrained_plan(
    self,
    user_prompt: str,
    catalog_text: str,
    goal: Any,
    model: Optional[str] = None,
    exclusions: "Optional[ResolvedRestrictions]" = None,
) -> Dict[str, Any]:
    model = model or self.default_model
    system_prompt = self._build_meal_system_prompt(
        goal=goal, exclusions=exclusions, catalog_text=catalog_text, single_meal=False,
    )
    # ... existing full_prompt + Gemini call + parse + return unchanged ...
```

Delete the now-dead inline system-prompt strings from both methods (keep the remaining body intact: model construction, generate_content call, parsing).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest diet_planner/tests/test_llm_service_restrictions.py -v`
Expected: PASS — all tests in the file green.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/llm_service.py diet_planner/tests/test_llm_service_restrictions.py
git commit -m "feat(llm_service): wire exclusions kwarg into both meal-plan methods"
```

---

## Task 8: `regenerate_meal` (single-meal surgical re-prompt)

**Files:**
- Modify: `diet_planner/llm_service.py`
- Modify: `diet_planner/tests/test_llm_service_restrictions.py`

- [ ] **Step 1: Write the failing test**

Append to `test_llm_service_restrictions.py`:

```python
class TestRegenerateMeal:
    def test_returns_single_meal_dict(self, monkeypatch):
        svc = GeminiService()

        class FakeModel:
            def __init__(self, model_name, system_instruction):
                self.system_instruction = system_instruction
            def generate_content(self, *a, **kw):
                resp = MagicMock()
                resp.candidates = [MagicMock(finish_reason=MagicMock(name="OK"))]
                resp.text = (
                    '{"name": "GF Risotto", "description": "Compliant.",'
                    '"food_category": "lunch_main_dish", "preparation_time": 20,'
                    '"ingredients": [{"name": "rýže", "quantity": 100, "unit": "g"}],'
                    '"instructions": ["Vař rýži."],'
                    '"nutritional_info": {"calories": 350}}'
                )
                resp.usage_metadata = MagicMock(
                    prompt_token_count=1, candidates_token_count=1
                )
                return resp

        import diet_planner.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.genai, "GenerativeModel", FakeModel)

        original = {
            "name": "Wheat-based lunch",
            "ingredients": [{"name": "mouka", "quantity": 100, "unit": "g"}],
            "instructions": ["mix flour"],
            "food_category": "lunch_main_dish",
        }
        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "flour"}),
            freeform_allergens=frozenset(),
        )
        result = svc.regenerate_meal(
            original_meal=original, goal=_goal(), exclusions=exclusions,
        )
        # Must be a SINGLE meal dict, not a days envelope
        assert "days" not in result
        assert result["name"] == "GF Risotto"
        assert all(i["name"] != "mouka" for i in result["ingredients"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest diet_planner/tests/test_llm_service_restrictions.py::TestRegenerateMeal -v`
Expected: FAIL — `AttributeError: 'GeminiService' object has no attribute 'regenerate_meal'`.

- [ ] **Step 3: Add the method**

In `diet_planner/llm_service.py`:

```python
def regenerate_meal(
    self,
    original_meal: Dict[str, Any],
    goal: Any,
    exclusions: "ResolvedRestrictions",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Re-prompt Gemini for ONE replacement meal that honors restrictions.

    Returns a single meal dict (not wrapped in a days array). Used by the
    repair loop when the validator finds a forbidden ingredient.
    """
    model = model or self.default_model
    system_prompt = self._build_meal_system_prompt(
        goal=goal, exclusions=exclusions, shop_url=None, single_meal=True,
    )
    meal_brief = (
        f"Slot: {original_meal.get('food_category', 'meal')}\n"
        f"Replace this meal because it violated restrictions:\n"
        f"  name: {original_meal.get('name', '?')}\n"
        f"  ingredients: "
        f"{[i.get('name') for i in (original_meal.get('ingredients') or []) if isinstance(i, dict)]}\n"
        f"Produce a compliant replacement for the same slot."
    )
    gemini_model = genai.GenerativeModel(
        model_name=model, system_instruction=system_prompt
    )
    response = gemini_model.generate_content(
        meal_brief,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.7,
            "max_output_tokens": getattr(
                settings, "GEMINI_MAX_OUTPUT_TOKENS", 65536
            ),
        },
        request_options={"timeout": 120},
    )
    return json.loads(response.text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest diet_planner/tests/test_llm_service_restrictions.py::TestRegenerateMeal -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/llm_service.py diet_planner/tests/test_llm_service_restrictions.py
git commit -m "feat(llm_service): regenerate_meal for surgical single-meal repair"
```

---

## Task 9: `generate_shopping_list_with_prices` consumes aggregated list, no truncation

**Files:**
- Modify: `diet_planner/llm_service.py` (~line 453–562)
- Modify: `diet_planner/tests/test_llm_service_restrictions.py`

- [ ] **Step 1: Write the failing test**

Append to `test_llm_service_restrictions.py`:

```python
class TestShoppingListUsesAggregatedList:
    def test_user_prompt_lists_every_aggregated_item(self, monkeypatch):
        svc = GeminiService()
        captured = {}

        class FakeModel:
            def __init__(self, model_name, system_instruction):
                captured["system_instruction"] = system_instruction
            def generate_content(self, prompt, *a, **kw):
                captured["prompt"] = prompt
                resp = MagicMock()
                resp.candidates = [MagicMock(finish_reason=MagicMock(name="OK"))]
                resp.text = '{"shopping_list": [], "total_cost": 0}'
                resp.usage_metadata = MagicMock(
                    prompt_token_count=1, candidates_token_count=1
                )
                return resp

        import diet_planner.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.genai, "GenerativeModel", FakeModel)

        aggregated = [
            {"ingredient": "rýže", "quantity": 200, "unit": "g"},
            {"ingredient": "kuřecí prsa", "quantity": 800, "unit": "g"},
            # 40 more items to ensure no [:5000] truncation drops them
            *[
                {"ingredient": f"item_{i}", "quantity": 10, "unit": "g"}
                for i in range(40)
            ],
        ]
        svc.generate_shopping_list_with_prices(
            aggregated_items=aggregated,
            shop_url="https://x.example",
            goal=_goal(),
        )
        # Every aggregated item must appear verbatim in the user prompt
        for item in aggregated:
            assert item["ingredient"] in captured["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest diet_planner/tests/test_llm_service_restrictions.py::TestShoppingListUsesAggregatedList -v`
Expected: FAIL — `unexpected keyword argument 'aggregated_items'`.

- [ ] **Step 3: Change the signature**

In `diet_planner/llm_service.py`, replace the body of `generate_shopping_list_with_prices`. New signature and body:

```python
def generate_shopping_list_with_prices(
    self,
    aggregated_items: List[Dict[str, Any]],
    shop_url: str,
    goal: Any,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Price-match a pre-aggregated shopping list against a shop catalog.

    The aggregated list is the SOURCE OF TRUTH — Gemini must price every
    item and may not drop or add anything. Parity with recipe ingredients
    is guaranteed by the caller, not by Gemini.
    """
    model = model or self.default_model

    language_names = {
        "cs": "Czech", "sk": "Slovak", "pl": "Polish",
        "hu": "Hungarian", "ro": "Romanian", "bg": "Bulgarian",
        "de": "German", "en": "English",
    }
    target_language = language_names.get(
        getattr(goal, "language_code", "en") or "en", "English"
    )
    currency_map = {"CZ": "CZK", "SK": "EUR", "PL": "PLN", "HU": "HUF"}
    currency = currency_map.get(getattr(goal, "country", "CZ"), "CZK")

    system_prompt = (
        f"You are a shopping assistant. Price each item below from {shop_url}.\n\n"
        f"RESPONSE FORMAT: Valid JSON only, all text in {target_language}\n\n"
        "OUTPUT:\n"
        '{\n  "shopping_list": [\n'
        '    {\n'
        '      "ingredient": "name",\n'
        '      "quantity": 500,\n'
        '      "unit": "g",\n'
        '      "matched_product_name": "actual product",\n'
        '      "price": 89.90,\n'
        '      "price_total": 89.90,\n'
        f'      "currency": "{currency}",\n'
        '      "package_size": 500,\n'
        '      "product_unit": "g",\n'
        '      "price_type": "REGULAR",\n'
        '      "estimated": false\n'
        '    }\n  ],\n  "total_cost": 2345.67\n}\n\n'
        "RULES:\n"
        f"1. Browse {shop_url} for ACTUAL prices\n"
        "2. Convert weights to pieces when needed (200g avocado -> 2 pieces)\n"
        "3. Round UP to purchasable packages (300ml oil -> 500ml bottle)\n"
        "4. Mark estimated: true only if product not found\n"
        "5. EVERY input item must appear in shopping_list — do not drop any."
    )

    items_block = "\n".join(
        f"- {it.get('ingredient', '')}: {it.get('quantity', '')} {it.get('unit', '')}"
        for it in aggregated_items
    )
    prompt = (
        f"Price every item below from {shop_url}.\n"
        f"Input items ({len(aggregated_items)} total):\n{items_block}\n\n"
        f"Return shopping_list with one entry per input item."
    )

    gemini_model = genai.GenerativeModel(
        model_name=model, system_instruction=system_prompt
    )
    max_tokens = getattr(settings, "GEMINI_MAX_OUTPUT_TOKENS", 65536)
    response = gemini_model.generate_content(
        prompt,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.3,
            "max_output_tokens": max_tokens,
        },
        request_options={"timeout": 300},
    )
    if response.candidates and hasattr(response.candidates[0], "finish_reason"):
        finish = response.candidates[0].finish_reason
        if finish.name == "MAX_TOKENS":
            raise ValueError(f"Shopping list response truncated at {max_tokens} tokens")
    parsed = json.loads(response.text)
    usage = response.usage_metadata
    return {
        "response": parsed,
        "input_tokens": getattr(usage, "prompt_token_count", 0),
        "output_tokens": getattr(usage, "candidates_token_count", 0),
        "cost_usd": 0.0,
    }
```

Also update the only existing caller `generate_complete_plan_with_shopping_list` (`llm_service.py:563`) to pass an aggregated list — this gets done in Task 11 alongside the legacy task wiring. For now, leave that caller's old call broken; the test we just added covers the new shape.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest diet_planner/tests/test_llm_service_restrictions.py::TestShoppingListUsesAggregatedList -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/llm_service.py diet_planner/tests/test_llm_service_restrictions.py
git commit -m "feat(llm_service): shopping list takes aggregated items, no truncation"
```

---

## Task 10: Repair loop — `repair_meals_with_violations`

**Files:**
- Modify: `diet_planner/services/restrictions.py`
- Modify: `diet_planner/tests/test_restrictions.py`

- [ ] **Step 1: Write the failing test**

Append to `test_restrictions.py`:

```python
from diet_planner.services.restrictions import (
    RepairBudgetExhausted,
    RepairOutcome,
    repair_meals_with_violations,
)


class _FakeLLM:
    """Stub for GeminiService.regenerate_meal. Each script entry is the dict
    returned by the next call."""

    def __init__(self, scripted: list[dict]):
        self._scripted = list(scripted)
        self.calls = 0

    def regenerate_meal(self, *, original_meal, goal, exclusions, **_):
        self.calls += 1
        return self._scripted.pop(0)


class TestRepairLoop:
    def _exclusions(self):
        return ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka"}),
            freeform_allergens=frozenset(),
        )

    def test_no_violations_returns_days_unchanged(self):
        days = [{
            "day_number": 1,
            "breakfast": _meal(ingredients=[{"name": "rýže", "quantity": 100, "unit": "g"}]),
        }]
        outcome = repair_meals_with_violations(
            days=days, goal=MagicMock(),
            exclusions=self._exclusions(), llm=_FakeLLM([]),
        )
        assert outcome.days == days
        assert outcome.reprompts == 0

    def test_swap_applied_no_llm_call(self):
        days = [{
            "day_number": 1,
            "lunch": _meal(ingredients=[{"name": "pšeničná mouka", "quantity": 100, "unit": "g"}]),
        }]
        llm = _FakeLLM([])
        outcome = repair_meals_with_violations(
            days=days, goal=MagicMock(),
            exclusions=self._exclusions(), llm=llm,
        )
        assert llm.calls == 0
        assert outcome.days[0]["lunch"]["ingredients"][0]["name"] == "bezlepková mouka"

    def test_reprompt_for_unmapped_violation(self):
        # Instruction-only violation isn't swappable -> must re-prompt
        days = [{
            "day_number": 1,
            "lunch": _meal(
                ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
                instructions=["Smíchej s moukou."],
            ),
        }]
        compliant_replacement = _meal(
            name="GF lunch",
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s bezlepkovou moukou."],
        )
        llm = _FakeLLM([compliant_replacement])
        outcome = repair_meals_with_violations(
            days=days, goal=MagicMock(),
            exclusions=self._exclusions(), llm=llm,
        )
        assert llm.calls == 1
        assert outcome.days[0]["lunch"]["name"] == "GF lunch"

    def test_two_failed_reprompts_then_failure(self):
        days = [{
            "day_number": 1,
            "lunch": _meal(
                ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
                instructions=["Smíchej s moukou."],
            ),
        }]
        # Both replacements still contain 'moukou' in instructions
        still_bad = _meal(
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s moukou."],
        )
        llm = _FakeLLM([still_bad, still_bad])
        with pytest.raises(RepairBudgetExhausted):
            repair_meals_with_violations(
                days=days, goal=MagicMock(),
                exclusions=self._exclusions(), llm=llm,
                max_reprompts_per_meal=2, max_reprompts_per_plan=6,
            )
        assert llm.calls == 2

    def test_per_plan_budget_caps_calls(self):
        days = [
            {
                "day_number": d,
                "lunch": _meal(
                    ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
                    instructions=["Smíchej s moukou."],
                ),
            }
            for d in range(1, 8)  # 7 days, 7 violations
        ]
        still_bad = _meal(
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s moukou."],
        )
        llm = _FakeLLM([still_bad] * 20)
        with pytest.raises(RepairBudgetExhausted):
            repair_meals_with_violations(
                days=days, goal=MagicMock(),
                exclusions=self._exclusions(), llm=llm,
                max_reprompts_per_meal=2, max_reprompts_per_plan=6,
            )
        assert llm.calls == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest diet_planner/tests/test_restrictions.py::TestRepairLoop -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement the repair loop**

Append to `diet_planner/services/restrictions.py`:

```python
import logging

logger = logging.getLogger(__name__)


@dataclass
class RepairOutcome:
    days: list[dict]
    reprompts: int
    swaps: int


class RepairBudgetExhausted(Exception):
    """Raised when a meal can't be repaired within the configured budget."""

    def __init__(self, message: str, *, meal_key: str, violations: list[Violation]):
        super().__init__(message)
        self.meal_key = meal_key
        self.violations = violations


_SLOT_KEYS = ("breakfast", "lunch", "dinner")
_SLOT_LIST_KEYS = ("small_meals", "snacks")


def _iter_meals(days: list[dict]):
    """Yield (day_index, slot_key, list_index_or_None, meal_dict)."""
    for d_idx, day in enumerate(days):
        for slot in _SLOT_KEYS:
            meal = day.get(slot)
            if isinstance(meal, dict):
                yield d_idx, slot, None, meal
        for slot in _SLOT_LIST_KEYS:
            arr = day.get(slot) or []
            if isinstance(arr, list):
                for i, m in enumerate(arr):
                    if isinstance(m, dict):
                        yield d_idx, slot, i, m


def _replace_meal(day: dict, slot: str, list_idx: int | None, new_meal: dict) -> None:
    if list_idx is None:
        day[slot] = new_meal
    else:
        day[slot][list_idx] = new_meal


def repair_meals_with_violations(
    *,
    days: list[dict],
    goal,
    exclusions: ResolvedRestrictions,
    llm,
    max_reprompts_per_meal: int = 2,
    max_reprompts_per_plan: int = 6,
) -> RepairOutcome:
    """Walk every meal; swap or re-prompt anything that violates exclusions.

    Raises RepairBudgetExhausted if the per-meal cap (default 2) or the
    per-plan cap (default 6) is hit while violations remain. Caller is
    expected to mark the DietaryGoal as FAILED in that case.
    """
    if not exclusions.exclusion_keywords:
        return RepairOutcome(days=days, reprompts=0, swaps=0)

    total_reprompts = 0
    total_swaps = 0

    for d_idx, slot, list_idx, meal in _iter_meals(days):
        meal_key = f"day_{days[d_idx].get('day_number', d_idx + 1)}.{slot}"
        if list_idx is not None:
            meal_key += f"[{list_idx}]"
        current = meal
        attempts = 0

        while True:
            violations = validate_meal_against_exclusions(
                current, exclusions.exclusion_keywords, meal_key=meal_key,
            )
            if not violations:
                _replace_meal(days[d_idx], slot, list_idx, current)
                break

            # Try deterministic swap for the FIRST violation we can fix
            patched = None
            for v in violations:
                patched = try_deterministic_swap(
                    current, v, tags=exclusions.tags,
                )
                if patched is not None:
                    total_swaps += 1
                    current = patched
                    break

            if patched is not None:
                # Loop again: validator will tell us if more violations remain
                continue

            # No swap available -> re-prompt
            if attempts >= max_reprompts_per_meal:
                raise RepairBudgetExhausted(
                    f"Meal {meal_key}: still violating after "
                    f"{attempts} re-prompts",
                    meal_key=meal_key, violations=violations,
                )
            if total_reprompts >= max_reprompts_per_plan:
                raise RepairBudgetExhausted(
                    f"Plan re-prompt budget exhausted "
                    f"({max_reprompts_per_plan}) at meal {meal_key}",
                    meal_key=meal_key, violations=violations,
                )
            logger.info(
                "restriction-repair: re-prompting %s (attempt %d) for %d violations",
                meal_key, attempts + 1, len(violations),
            )
            current = llm.regenerate_meal(
                original_meal=current, goal=goal, exclusions=exclusions,
            )
            attempts += 1
            total_reprompts += 1

    return RepairOutcome(days=days, reprompts=total_reprompts, swaps=total_swaps)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest diet_planner/tests/test_restrictions.py::TestRepairLoop -v`
Expected: PASS — 5 tests green.

Also run the full module test file to ensure nothing regressed:
Run: `pytest diet_planner/tests/test_restrictions.py -v`
Expected: PASS — all tests green.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/restrictions.py diet_planner/tests/test_restrictions.py
git commit -m "feat(restrictions): repair loop with swap + re-prompt + budget caps"
```

---

## Task 11: Wire into `process_dietary_goal_task` (legacy / fallback path)

**Files:**
- Modify: `diet_planner/llm_service.py` (`generate_complete_plan_with_shopping_list`)
- Modify: `diet_planner/tasks.py` (`process_dietary_goal_task`)
- Create: `diet_planner/tests/test_tasks_restriction_enforcement.py`

- [ ] **Step 1: Write the failing test**

`diet_planner/tests/test_tasks_restriction_enforcement.py`:

```python
"""End-to-end-ish tests for the two Celery task paths.

Gemini is mocked. The DB layer is patched where needed. These tests
verify that the resolver, validator, repair loop, deterministic
aggregator, and aggregated-list shopping call are all stitched
together correctly for both paths.
"""
from unittest.mock import MagicMock, patch

import pytest

from diet_planner.services.restrictions import ResolvedRestrictions


@pytest.mark.django_db
class TestLegacyPathReplicatesPlan110Scenario:
    def test_gluten_free_prompt_no_flour_anywhere(self, monkeypatch):
        from diet_planner.models import DietaryGoal
        from diet_planner.tasks import process_dietary_goal_task

        goal = DietaryGoal.objects.create(
            prompt="bezlepkový týden",
            dietary_restrictions="",  # ONLY in freeform — the plan-#110 case
            num_days=2,
            country="CZ",
            language_code="cs",
            status=DietaryGoal.StatusChoices.PENDING,
        )

        # First call returns days with flour; the repair loop re-prompts and
        # gets a compliant replacement.
        bad_meal = {
            "name": "Wheat lunch", "description": "x",
            "food_category": "lunch_main_dish", "preparation_time": 15,
            "ingredients": [{"name": "pšeničná mouka", "quantity": 100, "unit": "g"}],
            "instructions": ["mix flour"],
            "nutritional_info": {"calories": 350},
        }
        bad_days = [
            {"day_number": 1, "breakfast": bad_meal, "lunch": bad_meal,
             "dinner": bad_meal, "small_meals": [], "snacks": []},
            {"day_number": 2, "breakfast": bad_meal, "lunch": bad_meal,
             "dinner": bad_meal, "small_meals": [], "snacks": []},
        ]

        # Note: swap handles "mouka" deterministically — no LLM call needed
        # for the ingredients[]. But "mix flour" in instructions IS a
        # violation; the swap can't fix instructions, so re-prompt is used.
        good_meal = {
            "name": "GF lunch", "description": "x",
            "food_category": "lunch_main_dish", "preparation_time": 15,
            "ingredients": [{"name": "rýže", "quantity": 100, "unit": "g"}],
            "instructions": ["Cook rice."],
            "nutritional_info": {"calories": 350},
        }

        with patch("diet_planner.tasks.GeminiService") as MockSvc:
            svc = MockSvc.return_value
            svc.generate_complete_plan_with_shopping_list.return_value = {
                "response": {"days": bad_days, "shopping_list": [], "total_cost": 0},
                "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0,
            }
            svc.regenerate_meal.return_value = good_meal
            svc.generate_shopping_list_with_prices.return_value = {
                "response": {"shopping_list": [
                    {"ingredient": "rýže", "quantity": 200, "unit": "g",
                     "matched_product_name": "Basmati", "price": 50,
                     "price_total": 50, "currency": "CZK",
                     "package_size": 200, "product_unit": "g",
                     "price_type": "REGULAR", "estimated": False},
                ], "total_cost": 50},
                "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0,
            }
            process_dietary_goal_task(goal.id)

        goal.refresh_from_db()
        # Plan must have completed (or remained processing if still going) -
        # crucially NOT failed because of restriction violation.
        assert goal.status != DietaryGoal.StatusChoices.FAILED

        # Pull the latest plan and check no recipe contains 'mouka' or 'flour'
        plan = goal.dietary_plans.latest("created_at")
        for day in plan.days or []:
            for slot in ("breakfast", "lunch", "dinner"):
                meal = day.get(slot)
                if isinstance(meal, dict):
                    blob = (meal.get("name", "") + " " +
                            " ".join(str(i.get("name", "")) for i in (meal.get("ingredients") or []) if isinstance(i, dict)) + " " +
                            " ".join(meal.get("instructions") or [])).lower()
                    assert "mouka" not in blob or "bezlepk" in blob
                    assert "flour" not in blob or "gluten-free" in blob

        # Shopping list parity: every recipe ingredient must appear
        # (the aggregated list is the SOURCE OF TRUTH)
        shopping_names = {item["ingredient"].lower() for item in plan.shopping_list or []}
        for day in plan.days or []:
            for slot in ("breakfast", "lunch", "dinner"):
                meal = day.get(slot)
                if isinstance(meal, dict):
                    for ing in meal.get("ingredients") or []:
                        if isinstance(ing, dict):
                            assert ing["name"].lower() in shopping_names


@pytest.mark.django_db
class TestLegacyPathFailsOnExhaustedBudget:
    def test_persistent_violation_marks_goal_failed(self, monkeypatch):
        from diet_planner.models import DietaryGoal
        from diet_planner.tasks import process_dietary_goal_task

        goal = DietaryGoal.objects.create(
            prompt="bezlepkový týden",
            dietary_restrictions="",
            num_days=1,
            country="CZ",
            language_code="cs",
            status=DietaryGoal.StatusChoices.PENDING,
        )
        bad_meal = {
            "name": "Flour soup", "description": "x",
            "food_category": "lunch_main_dish", "preparation_time": 10,
            "ingredients": [{"name": "máslo", "quantity": 10, "unit": "g"}],
            "instructions": ["Mix with flour."],  # instruction-only -> no swap
            "nutritional_info": {},
        }
        bad_days = [
            {"day_number": 1, "breakfast": bad_meal, "lunch": bad_meal,
             "dinner": bad_meal, "small_meals": [], "snacks": []},
        ]
        with patch("diet_planner.tasks.GeminiService") as MockSvc:
            svc = MockSvc.return_value
            svc.generate_complete_plan_with_shopping_list.return_value = {
                "response": {"days": bad_days, "shopping_list": [], "total_cost": 0},
                "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0,
            }
            # All re-prompts return the same bad meal -> budget exhausts
            svc.regenerate_meal.return_value = bad_meal
            process_dietary_goal_task(goal.id)

        goal.refresh_from_db()
        assert goal.status == DietaryGoal.StatusChoices.FAILED
        assert "restriction" in (goal.error_message or "").lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest diet_planner/tests/test_tasks_restriction_enforcement.py::TestLegacyPathReplicatesPlan110Scenario -v`
Expected: FAIL — flour still appears, or shopping list misses items.

- [ ] **Step 3: Wire the resolver + repair + aggregator into the legacy task**

In `diet_planner/llm_service.py`, update `generate_complete_plan_with_shopping_list` to accept `exclusions` and stop calling the shopping-list LLM internally — pricing now happens at task level over the aggregated list:

```python
def generate_complete_plan_with_shopping_list(
    self,
    user_prompt: str,
    shop_url: str,
    goal: Any,
    model: Optional[str] = None,
    exclusions: "Optional[ResolvedRestrictions]" = None,
) -> Dict[str, Any]:
    """Step 1 only: produce the meal plan. Shopping list is produced by
    the caller after deterministic aggregation. This method retains its
    name for callers but no longer fans out the second LLM call."""
    meal_plan_result = self.generate_meal_plan_only(
        user_prompt, shop_url, goal, model, exclusions=exclusions,
    )
    return meal_plan_result
```

In `diet_planner/tasks.py`, replace the body of `process_dietary_goal_task` around lines 1483–1497 with the new flow. Show the diff for clarity:

```python
# Before:
#     llm_result = llm_service.generate_complete_plan_with_shopping_list(
#         user_prompt=user_prompt, shop_url=shop_url, goal=goal,
#     )
#     llm_response = llm_result['response']
#     days = llm_response.get('days', [])
#     shopping_list_from_llm = llm_response.get('shopping_list', [])
#     total_cost_from_llm = llm_response.get('total_cost')

# After:
from diet_planner.services.restrictions import (
    RepairBudgetExhausted,
    RestrictionResolver,
    repair_meals_with_violations,
)

# 1. Resolve restrictions ONCE
exclusions = RestrictionResolver().resolve(goal)
logger.info(
    f"{log_prefix} Restrictions resolved: tags={set(exclusions.tags)}, "
    f"{len(exclusions.exclusion_keywords)} keywords, "
    f"allergens={set(exclusions.freeform_allergens)}"
)

# 2. Meal-plan-only LLM call (Gemini #1)
llm_result = llm_service.generate_complete_plan_with_shopping_list(
    user_prompt=user_prompt, shop_url=shop_url, goal=goal,
    exclusions=exclusions,
)
llm_response = llm_result["response"]
days = llm_response.get("days", [])

# 3. Validator + repair loop
try:
    outcome = repair_meals_with_violations(
        days=days, goal=goal, exclusions=exclusions, llm=llm_service,
    )
    days = outcome.days
    logger.info(
        f"{log_prefix} Repair: {outcome.swaps} swaps, "
        f"{outcome.reprompts} re-prompts"
    )
except RepairBudgetExhausted as exc:
    goal.status = DietaryGoal.StatusChoices.FAILED
    goal.error_message = (
        f"Could not produce a plan honoring the dietary restriction "
        f"(meal {exc.meal_key}). Please try again or adjust the prompt."
    )
    goal.save(update_fields=["status", "error_message"])
    logger.error(f"{log_prefix} Restriction repair exhausted: {exc}")
    return {"status": "failed", "error": str(exc)}

# 4. Deterministic aggregation (replaces the LLM-driven shopping list)
shopping_items = aggregate_ingredients_from_meals(
    days, context_id=context_id, goal_id=goal_id,
)

# 5. Pricing via the existing LLM shopping-list call, now fed the
#    aggregated list (no [:5000] truncation)
pricing_result = llm_service.generate_shopping_list_with_prices(
    aggregated_items=shopping_items, shop_url=shop_url, goal=goal,
)
priced = pricing_result["response"]
shopping_list_from_llm = priced.get("shopping_list", [])
total_cost_from_llm = priced.get("total_cost")
```

The rest of `process_dietary_goal_task` (transform, validate_shopping_item, persist) stays unchanged — it already iterates `shopping_list_from_llm`.

- [ ] **Step 4: Run the tests**

Run: `pytest diet_planner/tests/test_tasks_restriction_enforcement.py -v`
Expected: PASS — both classes green.

Also run the existing test suite for tasks to ensure no regression:
Run: `pytest diet_planner/tests/ -v --ignore=diet_planner/tests/test_tasks_restriction_enforcement.py -x`
Expected: PASS (or pre-existing failures only — fix any new failures).

- [ ] **Step 5: Commit**

```bash
git add diet_planner/llm_service.py diet_planner/tasks.py diet_planner/tests/test_tasks_restriction_enforcement.py
git commit -m "feat(tasks): wire restriction enforcement + aggregator into legacy path"
```

---

## Task 12: Wire into `process_dietary_goal_catalog_task` (catalog / v2 path)

**Files:**
- Modify: `diet_planner/tasks.py` (`process_dietary_goal_catalog_task`)
- Modify: `diet_planner/tests/test_tasks_restriction_enforcement.py`

- [ ] **Step 1: Write the failing test**

Append to `test_tasks_restriction_enforcement.py`:

```python
@pytest.mark.django_db
class TestCatalogPathEnforcesRestrictions:
    def test_catalog_filter_uses_resolved_exclusions_from_prompt(self, monkeypatch):
        from diet_planner.models import DietaryGoal
        from diet_planner.tasks import process_dietary_goal_catalog_task

        goal = DietaryGoal.objects.create(
            prompt="bezlepkový týden",
            dietary_restrictions="",  # plan-#110 case: prompt-only
            num_days=1,
            country="CZ",
            language_code="cs",
            status=DietaryGoal.StatusChoices.PENDING,
            shop="rohlik",
        )

        captured = {}

        def fake_build_catalog(self, goal_arg, max_products=500, exclusions=None):
            captured["exclusions"] = exclusions
            # Return a catalog big enough to NOT trigger the legacy fallback
            return {
                "products_by_category": {"grains": [{"name": "rýže"}] * 15},
                "total_products": 15,
                "pantry_staples": [],
                "store_name": "Rohlik",
                "catalog_limited": False,
            }

        with patch("diet_planner.services.catalog.CatalogService.build_catalog_for_prompt", fake_build_catalog), \
             patch("diet_planner.tasks.GeminiService") as MockSvc, \
             patch("diet_planner.tasks.PriceResolver") as MockResolver:
            svc = MockSvc.return_value
            good_meal = {
                "name": "GF Risotto", "description": "x",
                "food_category": "lunch_main_dish", "preparation_time": 15,
                "ingredients": [{"name": "rýže", "quantity": 100, "unit": "g",
                                 "catalog_id": 1}],
                "instructions": ["Vař rýži."],
                "nutritional_info": {},
            }
            svc.generate_catalog_constrained_plan.return_value = {
                "response": {"days": [
                    {"day_number": 1, "breakfast": good_meal,
                     "lunch": good_meal, "dinner": good_meal,
                     "small_meals": [], "snacks": []},
                ]},
                "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0,
            }
            MockResolver.return_value.resolve_shopping_list.return_value = [{
                "ingredient": "rýže", "quantity": 100, "unit": "g",
                "price_total": 50, "currency": "CZK", "matched_product_name": "Basmati",
            }]
            process_dietary_goal_catalog_task(goal.id)

        # Catalog filter MUST have received resolved exclusions even though
        # dietary_restrictions field is empty
        assert captured["exclusions"] is not None
        assert "gluten_free" in captured["exclusions"].tags
        # generate_catalog_constrained_plan MUST have been called WITH exclusions
        kwargs = svc.generate_catalog_constrained_plan.call_args.kwargs
        assert kwargs.get("exclusions") is not None
        assert "gluten_free" in kwargs["exclusions"].tags

        goal.refresh_from_db()
        assert goal.status != DietaryGoal.StatusChoices.FAILED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest diet_planner/tests/test_tasks_restriction_enforcement.py::TestCatalogPathEnforcesRestrictions -v`
Expected: FAIL — `captured["exclusions"]` is None.

- [ ] **Step 3: Wire the catalog task**

In `diet_planner/tasks.py`, near `process_dietary_goal_catalog_task` (~line 2049), insert the resolver before `CatalogService` and pass exclusions through; insert the repair loop after generation.

Show the new block (replaces existing Phase-1 catalog build and Phase-2 LLM call lines):

```python
from diet_planner.services.restrictions import (
    RepairBudgetExhausted,
    RestrictionResolver,
    repair_meals_with_violations,
)

# Phase 0: resolve restrictions
exclusions = RestrictionResolver().resolve(goal)
logger.info(
    f"{log_prefix} Restrictions resolved: tags={set(exclusions.tags)}, "
    f"{len(exclusions.exclusion_keywords)} keywords"
)

# Phase 1: build catalog (now filtered by the resolved set)
catalog = CatalogService().build_catalog_for_prompt(
    goal, exclusions=exclusions,
)

# Existing small-catalog fallback (unchanged):
if catalog["total_products"] < 10:
    logger.warning(
        f"{log_prefix} Catalog too sparse "
        f"({catalog['total_products']} products), falling back to legacy"
    )
    return process_dietary_goal_task(goal_id)

# ... existing catalog_text construction unchanged ...

# Phase 2: generation
llm_service = GeminiService()
user_prompt = _build_protocol_prompt(goal)
llm_result = llm_service.generate_catalog_constrained_plan(
    user_prompt=user_prompt,
    catalog_text=catalog_text,
    goal=goal,
    exclusions=exclusions,
)
days = llm_result["response"].get("days", [])

# Phase 2.5: validator + repair (NEW)
try:
    outcome = repair_meals_with_violations(
        days=days, goal=goal, exclusions=exclusions, llm=llm_service,
    )
    days = outcome.days
    logger.info(
        f"{log_prefix} Repair: {outcome.swaps} swaps, "
        f"{outcome.reprompts} re-prompts"
    )
except RepairBudgetExhausted as exc:
    goal.status = DietaryGoal.StatusChoices.FAILED
    goal.error_message = (
        f"Could not produce a plan honoring the dietary restriction "
        f"(meal {exc.meal_key}). Please try again or adjust the prompt."
    )
    goal.save(update_fields=["status", "error_message"])
    return {"status": "failed", "error": str(exc)}

# Phases 3 & 4 (aggregate + PriceResolver) are unchanged.
```

The recipe-grounding overlay (`overlay_curated_recipes`) keeps its existing position before aggregation. That's fine — curated recipes are already restriction-compliant for their tags, and any survivor will pass the validator on the next plan generation if the user re-runs.

- [ ] **Step 4: Run the tests**

Run: `pytest diet_planner/tests/test_tasks_restriction_enforcement.py -v`
Expected: PASS — all three classes green.

Run the catalog-task regression suite:
Run: `pytest diet_planner/tests/test_catalog_constrained.py -v`
Expected: PASS (fix any callers of `build_catalog_for_prompt` that needed `exclusions=None`).

- [ ] **Step 5: Commit**

```bash
git add diet_planner/tasks.py diet_planner/tests/test_tasks_restriction_enforcement.py
git commit -m "feat(tasks): wire restriction enforcement into catalog/v2 path"
```

---

## Task 13: Full-suite sanity sweep + plan-#110 regression assertion

**Files:**
- No new files. Run the full test suite end-to-end and tie up loose ends.

- [ ] **Step 1: Run the entire diet_planner test suite**

Run: `pytest diet_planner/tests/ -v`
Expected: PASS, including the three new files:
- `test_restrictions.py` — ~20 tests
- `test_llm_service_restrictions.py` — ~7 tests
- `test_tasks_restriction_enforcement.py` — 3 tests
- All pre-existing tests still green.

If any pre-existing test now fails because a caller of `build_catalog_for_prompt` didn't pass `exclusions`, update that caller to pass `exclusions=None` (back-compat) or `RestrictionResolver().resolve(goal)` if it's a production caller.

- [ ] **Step 2: Run the project lint/format checks (if configured)**

Run: `pre-commit run --all-files`
Expected: PASS or auto-format the affected files.

If pre-commit isn't configured for this repo, skip this step.

- [ ] **Step 3: Commit any cleanup**

```bash
git add -u
git commit -m "chore(restrictions): final lint + back-compat tidy"
```

(Skip if the diff is empty.)

- [ ] **Step 4: Verify the branch state**

Run: `git log --oneline feature/stripe-billing..HEAD`
Expected: 12 or 13 commits, all on `feature/restriction-enforcement`, no merge commits.

Run: `git diff --stat feature/stripe-billing..HEAD`
Expected: file changes confined to:
- `diet_planner/services/restrictions.py` (new)
- `diet_planner/services/catalog.py`
- `diet_planner/llm_service.py`
- `diet_planner/tasks.py`
- `diet_planner/tests/test_restrictions.py` (new)
- `diet_planner/tests/test_llm_service_restrictions.py` (new)
- `diet_planner/tests/test_tasks_restriction_enforcement.py` (new)
- `docs/superpowers/specs/2026-06-13-restriction-enforcement-and-shopping-list-parity-design.md` (existing)
- `docs/superpowers/plans/2026-06-13-restriction-enforcement-and-shopping-list-parity.md` (this plan)

No changes outside `diet_planner/` or `docs/`.

---

## Self-Review (do NOT include in plan file; this is the author's check)

1. **Spec §1a–1c root causes:** Tasks 7, 11, 12 fix the allergen leak on both LLM paths. ✓
2. **Spec §1b shopping-list truncation:** Task 9 removes `[:5000]` truncation; Task 11 feeds the aggregated list. ✓
3. **Spec §2.1 RestrictionResolver + freeform allergens:** Tasks 1–2. ✓
4. **Spec §2.1 DETERMINISTIC_SWAPS + anti-rot test:** Task 4. ✓
5. **Spec §2.1 validate_meal_against_exclusions + compliance modifiers:** Task 3. ✓
6. **Spec §2.2 _build_meal_system_prompt shared helper:** Task 6. ✓
7. **Spec §2.2 regenerate_meal:** Task 8. ✓
8. **Spec §2.2 generate_shopping_list_with_prices signature change:** Task 9. ✓
9. **Spec §2.3 task-path reordering for both paths:** Tasks 11 + 12. ✓
10. **Spec §3 repair loop, 2/meal and 6/plan caps, FAILED on exhaustion:** Tasks 10, 11, 12. ✓
11. **Spec §5 testing plan:** unit tests in each task; reproduction test in Task 11; anti-rot test in Task 4. ✓
12. **Spec §6 Czech morphology:** documented limitation — we use substring matching + compliance modifiers; no separate task because no code change is needed. ✓
13. **Spec §7 non-goals:** PriceResolver migration for legacy path is explicitly NOT done (Task 11 still uses LLM pricing, just over the aggregated list). ✓
