"""
Semantic "simulated human" coherence judge (cross-model).

The deterministic checks in `recipe_coherence.py` catch one well-defined
class of bug — an ingredient the recipe says is "already prepared" still
showing up on the shopping list (the *klizka* incident, see
`docs/qa-recipe-shopping-coherence.md`). They are phrase-matchers: precise,
cheap, and blind to anything they don't have a pattern for.

This module adds the layer a regex can't do. It asks a *different model
family* (Gemini writes the plan; Claude grades it — cross-model adversarial
review catches blind spots a model has in its own output) to read the plan,
the individual recipes, and the shopping list the way a real paying customer
would, and answer three human questions:

  1. **Shoppable.** If I buy everything on this list (across whichever
     shops it spans), do I then have what every recipe needs? Is anything
     on the list that no recipe uses? Is anything a recipe needs missing
     from the list?
  2. **Cookable.** Does each recipe actually tell me *how* to make the
     food — real preparation steps, not just a pile of ingredients?
  3. **Humanly sane.** Does it read like sensible food advice a person
     would give? No "eat 1 piece of chocolate bar" non-meals, no absurd
     quantities, no robotic filler.

Design constraints this module honours:

* **Advisory, not blocking (for now).** It returns findings; the caller
  decides what to do with them. Today `MealPlanValidator` surfaces them as
  warnings so we can measure the false-positive rate before promoting any
  of it to a hard checkout gate. See `docs/qa-recipe-shopping-coherence.md`
  §7 for the promotion path.
* **Fail-open.** A judge that errors, times out, is disabled, or has no API
  key must never break plan generation. Every failure path returns a
  verdict with ``ran == False`` and an empty issue list; nothing raises.
* **Gated.** Off unless ``RECIPE_HUMAN_JUDGE_ENABLED`` is true *and* an
  Anthropic API key is configured.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Verdict container
# ---------------------------------------------------------------------------

@dataclass
class JudgeVerdict:
    """Result of one semantic coherence judging pass.

    ``ran`` distinguishes "the judge looked and found nothing" (ran=True,
    issues=[]) from "the judge never ran" (disabled / no key / error).
    Callers treating this as a gate must check ``ran`` before trusting
    ``verdict`` — a verdict of "coherent" with ran=False means *unknown*,
    not *good*.
    """
    ran: bool = False
    verdict: str = "unknown"          # coherent | minor_issues | incoherent | unknown
    shoppable: Optional[bool] = None
    cookable: Optional[bool] = None
    human_sane: Optional[bool] = None
    summary: str = ""
    issues: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""
    error: Optional[str] = None

    @property
    def has_blocking_issues(self) -> bool:
        """True if any issue is high-severity. Not used as a gate today —
        provided for when the validator promotes the judge to a hard check."""
        return any(i.get("severity") == "high" for i in self.issues)

    def as_stats(self) -> Dict[str, Any]:
        return {
            "ran": self.ran,
            "verdict": self.verdict,
            "shoppable": self.shoppable,
            "cookable": self.cookable,
            "human_sane": self.human_sane,
            "issue_count": len(self.issues),
            "high_severity_count": sum(1 for i in self.issues if i.get("severity") == "high"),
            "model": self.model,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Structured-output schema (Anthropic `output_config.format`).
#
# Kept within the structured-outputs limitations: every object sets
# additionalProperties:false and lists all properties as required; no
# string-length / numeric constraints (validated by the model + our own
# light parsing instead).
# ---------------------------------------------------------------------------

_ISSUE_CATEGORIES = (
    "missing_from_shopping_list",   # recipe needs it, shopping list doesn't have it
    "orphan_shopping_item",         # on the list, no recipe uses it
    "not_cookable",                 # recipe lacks usable preparation steps
    "absurd_instruction",           # e.g. "eat 1 piece of chocolate bar"
    "absurd_quantity",              # nonsensical amount for the dish/person
    "not_a_real_meal",              # an item that isn't food a person would cook/eat
    "quantity_drift",               # recipe amount disagrees with shopping-list amount
    "unit_drift",                   # recipe unit disagrees with shopping-list unit
    "language_drift",               # item in the wrong language for the plan
    "other",
)

_VERDICT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["coherent", "minor_issues", "incoherent"]},
        "shoppable": {"type": "boolean"},
        "cookable": {"type": "boolean"},
        "human_sane": {"type": "boolean"},
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string", "enum": list(_ISSUE_CATEGORIES)},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "location": {"type": "string"},
                    "quote": {"type": "string"},
                    "explanation": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": ["category", "severity", "location", "quote", "explanation", "suggested_fix"],
            },
        },
    },
    "required": ["verdict", "shoppable", "cookable", "human_sane", "summary", "issues"],
}


_SYSTEM_PROMPT = """\
You are a meticulous, slightly impatient grocery shopper and home cook who \
has just paid for a meal-plan app. You are reviewing the plan it produced \
for you. You are NOT the model that wrote the plan — your job is to catch the \
ways it fails a real human, the way a paying customer would notice them.

You are given three things that MUST agree with each other:
  1. The meal plan: each day's meals, with a name, a description, cooking \
     instructions, and a list of ingredients.
  2. The shopping list: what the app tells the customer to buy (possibly \
     spanning several shops), with quantities and prices.
  3. (Implicitly) the contract between them — there is no database link \
     forcing the plan and the shopping list to match; you must check it.

Judge the plan against three questions, from the customer's chair:

A. SHOPPABLE — "If I go buy exactly what is on this shopping list, will I \
   then have everything each recipe needs?" Flag:
     - an ingredient a recipe needs that is NOT on the shopping list \
       (missing_from_shopping_list) — unless the recipe itself clearly says \
       it is a leftover / already prepared, in which case it is correct to \
       omit it, or the ingredient is marked `"optional": true`, which the \
       customer is free to skip and the list is right to leave off;
     - an item on the shopping list that NO recipe uses (orphan_shopping_item);
     - a quantity or unit on the list that disagrees with the recipe \
       (quantity_drift / unit_drift).

B. COOKABLE — "Does each recipe actually tell me how to MAKE the food?" \
   Flag a recipe that is just an ingredient dump with no usable preparation \
   steps, or steps so vague/garbled the dish cannot be made (not_cookable).

C. HUMANLY SANE — "Does this read like food advice a sensible person would \
   give?" Flag:
     - non-meals or robotic instructions like "eat 1 piece of chocolate \
       bar" presented as a meal (absurd_instruction / not_a_real_meal);
     - quantities no human would use for the dish or the number of eaters \
       (absurd_quantity);
     - items written in the wrong language for the plan (language_drift).

Rules:
  - Only report a REAL problem a customer would notice. Do not invent issues \
    to look thorough. If the plan is fine, say so and return an empty issues \
    list.
  - For every issue, `quote` the exact offending text from the plan or \
    shopping list (in its original language), and write `location` as \
    precisely as you can (e.g. "Day 2 / dinner / 'Beef stew'" or \
    "shopping list: 'klizka'").
  - Write `explanation` and `suggested_fix` in clear English for the \
    engineering team. Quotes stay in the original language.
  - Severity: `high` = the customer is misled or cannot cook/shop the plan \
    (missing core ingredient, non-meal, absurd instruction); `medium` = \
    noticeable but recoverable; `low` = nitpick.
  - `verdict`: "incoherent" if any high-severity issue exists; \
    "minor_issues" if only low/medium; "coherent" if none.
"""


# ---------------------------------------------------------------------------
# Plan serialization — compact, model-readable view of the plan.
# ---------------------------------------------------------------------------

def _ingredient_view(ing: Any) -> Dict[str, Any]:
    if isinstance(ing, dict):
        view = {
            "name": str(ing.get("name") or ing.get("ingredient") or "").strip(),
            "quantity": ing.get("quantity") or ing.get("amount"),
            "unit": ing.get("unit"),
        }
        # Optional items are legitimately absent from a shopping list — a
        # garnish nobody has to buy is not a missing ingredient. Without this
        # flag the judge reads the gap as `missing_from_shopping_list` at high
        # severity, which is a false rejection. Only emitted when true, to
        # keep the payload compact.
        if ing.get("optional"):
            view["optional"] = True
        return view
    return {"name": str(ing or "").strip(), "quantity": None, "unit": None}


def _instructions_view(meal: Dict[str, Any]) -> List[str]:
    steps: List[str] = []
    for step in meal.get("instructions", []) or []:
        if isinstance(step, dict):
            text = str(step.get("text") or step.get("step") or "").strip()
        else:
            text = str(step or "").strip()
        if text:
            steps.append(text)
    return steps


def serialize_plan(meal_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten the plan into a compact list of meals the judge can read."""
    meals: List[Dict[str, Any]] = []
    for day in meal_plan.get("days", []) or []:
        if not isinstance(day, dict):
            continue
        day_number = day.get("day_number")
        for meal_type in ("breakfast", "lunch", "dinner", "small_meals", "snacks"):
            raw = day.get(meal_type)
            if raw is None:
                continue
            meal_list = [raw] if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
            for idx, meal in enumerate(meal_list):
                if not isinstance(meal, dict):
                    continue
                meals.append({
                    "day": day_number,
                    "meal_type": meal_type,
                    "index": idx,
                    "name": meal.get("name", ""),
                    "description": meal.get("description", ""),
                    "instructions": _instructions_view(meal),
                    "ingredients": [_ingredient_view(i) for i in meal.get("ingredients", []) or []],
                    "pre_prepared": [
                        _ingredient_view(i).get("name")
                        for i in meal.get("pre_prepared_ingredients", []) or []
                    ],
                })
    return meals


def serialize_shopping_list(shopping_list: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in shopping_list or []:
        if not isinstance(item, dict):
            continue
        out.append({
            "name": item.get("ingredient") or item.get("name") or item.get("matched_product_name") or "",
            "quantity": item.get("quantity") or item.get("amount"),
            "unit": item.get("unit"),
            "price": item.get("price"),
            "store": item.get("store") or item.get("store_name") or item.get("shop"),
        })
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    return bool(
        getattr(settings, "RECIPE_HUMAN_JUDGE_ENABLED", False)
        and getattr(settings, "ANTHROPIC_API_KEY", None)
    )


def judge_plan_coherence(
    meal_plan: Dict[str, Any],
    shopping_list: Optional[List[Dict[str, Any]]],
    *,
    language: Optional[str] = None,
    model: Optional[str] = None,
) -> JudgeVerdict:
    """Run the semantic coherence judge. Never raises — fails open.

    Returns a :class:`JudgeVerdict`. When the judge is disabled, has no key,
    or errors, ``ran`` is False and ``issues`` is empty.
    """
    if not is_enabled():
        return JudgeVerdict(ran=False, verdict="unknown", error="disabled")

    model = model or getattr(settings, "RECIPE_HUMAN_JUDGE_MODEL", "claude-sonnet-4-6")
    effort = getattr(settings, "RECIPE_HUMAN_JUDGE_EFFORT", "low")

    try:
        import json

        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        plan_view = serialize_plan(meal_plan)
        list_view = serialize_shopping_list(shopping_list)
        lang = language or "the language the plan is written in"

        user_payload = {
            "plan_language": lang,
            "meals": plan_view,
            "shopping_list": list_view,
        }
        user_message = (
            "Review this meal plan and shopping list as a paying customer. "
            f"The plan is written in {lang}; quote offending text in its "
            "original language but write your explanations in English.\n\n"
            "```json\n" + json.dumps(user_payload, ensure_ascii=False, indent=2) + "\n```"
        )

        response = client.messages.create(
            model=model,
            max_tokens=8000,
            system=_SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": _VERDICT_SCHEMA},
            },
            messages=[{"role": "user", "content": user_message}],
        )

        if response.stop_reason == "refusal":
            logger.warning("recipe_human_judge: model refused the request")
            return JudgeVerdict(ran=False, verdict="unknown", model=model, error="refusal")

        text = next((b.text for b in response.content if b.type == "text"), "")
        data = json.loads(text)

        verdict = JudgeVerdict(
            ran=True,
            verdict=str(data.get("verdict", "unknown")),
            shoppable=data.get("shoppable"),
            cookable=data.get("cookable"),
            human_sane=data.get("human_sane"),
            summary=str(data.get("summary", "")),
            issues=[i for i in (data.get("issues") or []) if isinstance(i, dict)],
            model=model,
        )
        logger.info(
            "recipe_human_judge: verdict=%s issues=%d (shoppable=%s cookable=%s sane=%s)",
            verdict.verdict, len(verdict.issues),
            verdict.shoppable, verdict.cookable, verdict.human_sane,
        )
        return verdict

    except ImportError as exc:
        logger.warning("recipe_human_judge: anthropic SDK not installed (%s)", exc)
        return JudgeVerdict(ran=False, verdict="unknown", model=model, error="anthropic_not_installed")
    except Exception as exc:  # fail-open: never break plan generation
        logger.warning("recipe_human_judge: judging failed, continuing without it: %s", exc)
        return JudgeVerdict(ran=False, verdict="unknown", model=model, error=str(exc))
