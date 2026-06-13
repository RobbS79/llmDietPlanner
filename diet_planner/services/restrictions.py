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


# Same shape as recipe_retrieval._DIETARY_KEYWORDS but consolidated here so
# the catalog filter, the validator, and recipe retrieval can't drift apart.
# Substring match, case-folded, Czech + English.
_TAG_KEYWORDS: dict[str, str] = {
    "vegan": "vegan", "vegán": "vegan", "rostlinn": "vegan",
    "vegetari": "vegetarian", "bezmas": "vegetarian",
    "gluten": "gluten_free", "lepk": "gluten_free", "bezlepk": "gluten_free",
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


# Per-tag prefixes that mark an otherwise-forbidden token as legitimate.
# Substring match, case-folded. Order doesn't matter; presence does.
COMPLIANCE_MODIFIERS: dict[str, tuple[str, ...]] = {
    "gluten_free":  ("bezlepk", "gluten-free", "gluten free", " gf "),
    "lactose_free": ("bezlaktóz", "lactose-free", "lactose free"),
    "dairy_free":   ("bez mlék", "dairy-free", "dairy free"),
    "vegan":        ("veganské", "veganská", "veganský", "vegan"),
    "vegetarian":   ("vegetariánsk",),
}


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
