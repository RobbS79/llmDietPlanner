"""
Curation pipeline for the real-recipe corpus (Direction B — recipe grounding).

Turns a single source-URL index entry into a draft `CuratedRecipe`:

    fetch → extract (schema.org/Recipe JSON-LD, else cleaned page text)
          → rewrite into novice-clear Czech (Gemini)
          → map ingredients to canonical/catalog_id (deterministic resolver)
          → clarity/coherence judge (Claude, advisory) → quality_score

Driven by `manage.py build_curated_recipes`. See docs/recipe-grounding-plan.md §4.

Everything here is best-effort and fail-soft: a single bad source must not
break a batch run, so the public entry point returns a result object with an
`error` rather than raising.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from django.conf import settings as django_settings

from diet_planner.llm_service import GeminiService
from diet_planner.models import CuratedRecipe
from diet_planner.services.canonical_lookup import resolve_canonical
from diet_planner.services.ingredient_availability import (
    compute_shopping_difficulty,
    unshoppable_ingredients,
)
from diet_planner.services.nutrition_basis_repair import plan_basis_repair
from diet_planner.services.nutrition_lookups import category_table, piece_weight_table
from diet_planner.services.recipe_plausibility import check_portion_plausibility
from diet_planner.services import recipe_human_judge

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

_VALID_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack", "small_meal"}
_VALID_DIETARY_TAGS = {
    "vegetarian", "vegan", "gluten_free", "dairy_free", "high_protein", "low_carb",
}


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class CurationResult:
    """Outcome of curating one source entry."""
    source_url: str
    ok: bool = False
    recipe: Optional[CuratedRecipe] = None      # unsaved draft, or saved if persisted
    skipped: bool = False                        # already in corpus
    error: Optional[str] = None
    used_jsonld: bool = False
    judge: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fetch + extract
# ---------------------------------------------------------------------------

def fetch_source(url: str, timeout: int = 20) -> Optional[str]:
    """GET the source page HTML. Returns None on any network/HTTP failure."""
    try:
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.warning("recipe_curation: fetch failed for %s: %s", url, exc)
        return None


def _iter_jsonld_objects(html: str):
    """Yield every JSON object found in <script type=application/ld+json>,
    flattening @graph containers and top-level arrays."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if "@graph" in node and isinstance(node["@graph"], list):
                    stack.extend(node["@graph"])
                yield node


def _is_recipe_type(node: Dict[str, Any]) -> bool:
    t = node.get("@type")
    if isinstance(t, str):
        return t.lower() == "recipe"
    if isinstance(t, list):
        return any(isinstance(x, str) and x.lower() == "recipe" for x in t)
    return False


def extract_jsonld_recipe(html: str) -> Optional[Dict[str, Any]]:
    """Return the first schema.org/Recipe JSON-LD object, or None."""
    for node in _iter_jsonld_objects(html):
        if isinstance(node, dict) and _is_recipe_type(node):
            return node
    return None


def cleaned_page_text(html: str, limit: int = 20000) -> str:
    """Readable text fallback when there's no JSON-LD — mirrors the cleanup in
    GeminiService.extract_products_from_html, truncated for token budget."""
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup(["script", "style", "noscript", "meta", "link", "header", "footer", "nav"]):
        junk.decompose()
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = " ".join(c for c in chunks if c)
    return text[:limit]


def _jsonld_lang_hint(node: Optional[Dict[str, Any]]) -> str:
    if not node:
        return ""
    lang = node.get("inLanguage")
    if isinstance(lang, dict):
        lang = lang.get("name") or lang.get("@id")
    return str(lang) if lang else ""


# ---------------------------------------------------------------------------
# Normalize the model output → CuratedRecipe field dict
# ---------------------------------------------------------------------------

def _as_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def map_ingredients(raw_ingredients: Any) -> List[Dict[str, Any]]:
    """Attach `canonical` (CanonicalIngredient.slug) to each ingredient the
    resolver recognises, so the recipe is catalog-mapped by construction.

    `catalog_id` (a store-specific StoreProduct id) is intentionally left unset
    here — it's resolved per-store at pricing time. `canonical` is enough to
    satisfy CuratedRecipe.is_catalog_mapped() and to drive coherent pricing.
    """
    out: List[Dict[str, Any]] = []
    for ing in raw_ingredients or []:
        if not isinstance(ing, dict):
            # Tolerate a bare string ingredient.
            ing = {"name": str(ing)}
        name = str(ing.get("name") or "").strip()
        if not name:
            continue
        item: Dict[str, Any] = {
            "name": name,
            "quantity": ing.get("quantity"),
            "unit": (ing.get("unit") or "").strip() or None,
            "optional": bool(ing.get("optional", False)),
        }
        canonical = resolve_canonical(name)
        if canonical is not None:
            item["canonical"] = canonical.slug
        out.append(item)
    return out


def _normalize_instructions(raw: Any) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for step in raw or []:
        if isinstance(step, dict):
            text = str(step.get("text") or step.get("step") or "").strip()
            if not text:
                continue
            steps.append({
                "text": text,
                "time_min": _as_int(step.get("time_min")),
                "tip": (str(step.get("tip")).strip() or None) if step.get("tip") else None,
            })
        elif step:
            steps.append({"text": str(step).strip(), "time_min": None, "tip": None})
    return steps


def _filter_choices(values: Any, allowed: set) -> List[str]:
    out = []
    for v in values or []:
        s = str(v).strip().lower()
        if s in allowed and s not in out:
            out.append(s)
    return out


def build_recipe_fields(
    curated: Dict[str, Any],
    *,
    source_url: str,
    source_name: str,
    source_author: str = "",
) -> Dict[str, Any]:
    """Map the LLM's curated dict + provenance into CuratedRecipe kwargs."""
    nutrition = curated.get("base_nutrition") or {}
    if not isinstance(nutrition, dict):
        nutrition = {}

    difficulty = str(curated.get("difficulty", "")).strip().lower()
    if difficulty not in {c.value for c in CuratedRecipe.Difficulty}:
        difficulty = CuratedRecipe.Difficulty.EASY

    return {
        "name_cs": str(curated.get("name_cs") or "").strip(),
        "name_en": str(curated.get("name_en") or "").strip(),
        "description": str(curated.get("description") or "").strip(),
        "meal_types": _filter_choices(curated.get("meal_types"), _VALID_MEAL_TYPES),
        "cuisine": str(curated.get("cuisine") or "").strip().lower()[:40],
        "difficulty": difficulty,
        "dietary_tags": _filter_choices(curated.get("dietary_tags"), _VALID_DIETARY_TAGS),
        "ingredients": map_ingredients(curated.get("ingredients")),
        "instructions": _normalize_instructions(curated.get("instructions")),
        "base_servings": max(1, _as_int(curated.get("base_servings")) or 1),
        "base_nutrition": nutrition,
        "prep_time": _as_int(curated.get("prep_time")),
        "cook_time": _as_int(curated.get("cook_time")),
        "source_url": source_url,
        "source_name": source_name,
        "source_author": source_author,
        "license_note": "paraphrased, linked with attribution",
        "status": CuratedRecipe.Status.DRAFT,
    }


def correct_nutrition_basis(fields: Dict[str, Any]) -> Optional[str]:
    """Rewrite `base_nutrition` in place when it holds ONE portion, not the total.

    The curation model writes a per-portion figure into this per-recipe field
    often enough to have corrupted 96 published recipes before anyone noticed
    (repaired 2026-08-25). The prompt now says so explicitly, but a prompt is
    probabilistic and this bug is silent — the recipe looks fine, it just
    understates itself 4x-16x and gets OVER-SERVED by `portions_for_target`.

    So intake re-checks it with the same ingredient evidence the repair command
    uses. Corrects only when the recipe's own ingredients carry the energy to
    prove it; a piece-counted recipe (4 hard-boiled eggs) is left alone, as is
    anything the evidence cannot settle. Returns the reason when it rewrote,
    else None.
    """
    plan = plan_basis_repair(
        fields.get("base_nutrition"),
        fields.get("base_servings"),
        None,  # dish_role is assigned later by retag_dish_roles
        fields.get("ingredients"),
        piece_weights=piece_weight_table(),
        categories=category_table(),
    )
    if plan.action != "repair" or not plan.proposed:
        return None
    fields["base_nutrition"] = plan.proposed
    return plan.reason


# ---------------------------------------------------------------------------
# Clarity / coherence judge (reuse the recipe_human_judge infra)
# ---------------------------------------------------------------------------

def judge_curated_recipe(recipe: CuratedRecipe) -> Dict[str, Any]:
    """Score one curated recipe by wrapping it as a one-meal plan and running
    the cross-model coherence judge. Advisory only; fail-open (returns
    {ran: False} if the judge is disabled or errors)."""
    pseudo_plan = {
        "days": [{
            "day_number": 1,
            "lunch": {
                "name": recipe.name_cs,
                "description": recipe.description,
                "instructions": recipe.instructions,
                "ingredients": recipe.ingredients,
            },
        }],
    }
    # The recipe's own ingredients ARE its shopping list — a coherent recipe
    # must be fully shoppable from exactly them.
    shopping_list = [
        {"ingredient": ing.get("name"), "quantity": ing.get("quantity"), "unit": ing.get("unit")}
        for ing in (recipe.ingredients or [])
        if isinstance(ing, dict) and not ing.get("optional")
    ]
    verdict = recipe_human_judge.judge_plan_coherence(
        pseudo_plan, shopping_list, language="Czech",
    )
    stats = verdict.as_stats()
    stats["summary"] = verdict.summary
    stats["issues"] = verdict.issues
    return stats


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def curate_from_source(
    entry: Dict[str, str],
    *,
    gemini: Optional[GeminiService] = None,
    run_judge: bool = True,
    persist: bool = True,
    enforce_plausibility: bool = True,
    enforce_availability: bool = True,
) -> CurationResult:
    """Run the full pipeline for one `{dish_name, source_url, source_name}` entry.

    Idempotent: an entry whose `source_url` already exists in the corpus is
    skipped (result.skipped=True). Returns a CurationResult; never raises.
    """
    url = (entry.get("source_url") or "").strip()
    source_name = (entry.get("source_name") or "").strip()
    dish_name = (entry.get("dish_name") or entry.get("name") or "").strip()
    author = (entry.get("source_author") or "").strip()
    result = CurationResult(source_url=url)

    if not url:
        result.error = "missing source_url"
        return result

    if CuratedRecipe.objects.filter(source_url=url).exists():
        result.skipped = True
        result.ok = True
        return result

    html = fetch_source(url)
    if not html:
        result.error = "fetch failed"
        return result

    jsonld = extract_jsonld_recipe(html)
    if jsonld:
        source_material = json.dumps(jsonld, ensure_ascii=False)[:50000]
        result.used_jsonld = True
        lang_hint = _jsonld_lang_hint(jsonld)
        if not dish_name:
            dish_name = str(jsonld.get("name") or "").strip()
    else:
        source_material = cleaned_page_text(html)
        lang_hint = ""

    if not source_material.strip():
        result.error = "no extractable content"
        return result

    gemini = gemini or GeminiService()
    curated = gemini.curate_recipe_to_czech(
        source_title=dish_name or "recipe",
        source_material=source_material,
        source_url=url,
        source_lang_hint=lang_hint,
    )
    if not curated or not str(curated.get("name_cs") or "").strip():
        result.error = "LLM curation returned nothing usable"
        return result

    fields = build_recipe_fields(
        curated, source_url=url, source_name=source_name or _domain_of(url),
        source_author=author,
    )
    if not fields["instructions"]:
        result.error = "no instructions after curation"
        return result

    corrected = correct_nutrition_basis(fields)
    if corrected:
        logger.info(
            "recipe_curation: base_nutrition held one portion, corrected to the "
            "whole recipe for %s (%s)", url, corrected,
        )

    if enforce_plausibility:
        plausibility = check_portion_plausibility(
            fields["ingredients"], fields["base_servings"]
        )
        if not plausibility.ok:
            result.error = "implausible portion: " + "; ".join(plausibility.reasons)
            return result

    if enforce_availability and getattr(
        django_settings, 'AVAILABILITY_GATE_ENABLED', False,
    ):
        # Reads ingredient tiers directly, NOT the recipe rollup: the rollup
        # softens 'unrated' to 'findable', which is right for ranking and
        # wrong for intake.
        blocked = unshoppable_ingredients(fields["ingredients"])
        if blocked:
            result.error = "unshoppable ingredients: " + ", ".join(blocked)
            return result

    recipe = CuratedRecipe(**fields)

    # A freshly curated recipe must never be left "not yet computed".
    recipe.shopping_difficulty, recipe.shopping_blockers = compute_shopping_difficulty(recipe)

    if run_judge:
        # Judge needs the ingredient/instruction JSON; the in-memory instance
        # already has it, no save required to score.
        try:
            result.judge = judge_curated_recipe(recipe)
            recipe.quality_score = result.judge
        except Exception as exc:  # never let judging block curation
            logger.warning("recipe_curation: judge failed for %s: %s", url, exc)

    if persist:
        try:
            _save_with_unique_slug(recipe)
        except Exception as exc:  # honour "never raises"
            logger.warning("recipe_curation: save failed for %s: %s", url, exc)
            result.error = f"save failed: {exc}"
            return result

    result.recipe = recipe
    result.ok = True
    return result


def _save_with_unique_slug(recipe: CuratedRecipe) -> None:
    """Save, disambiguating the auto-generated slug on collision.

    CuratedRecipe.save() derives slug from name_cs without dedup, so two dishes
    with the same Czech name would collide on the unique constraint. Suffix and
    retry a few times rather than let one collision abort a batch run.
    """
    from django.db import IntegrityError
    from django.utils.text import slugify

    base = recipe.slug or slugify(recipe.name_cs)[:255]
    for attempt in range(6):
        recipe.slug = base if attempt == 0 else f"{base[:248]}-{attempt + 1}"
        try:
            recipe.save()
            return
        except IntegrityError:
            recipe.pk = None  # ensure the retry is an INSERT, not a doomed UPDATE
    # Last resort: let the final attempt's error propagate to the caller.
    recipe.slug = f"{base[:240]}-{recipe.source_url[-8:]}"
    recipe.save()


def _domain_of(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else (url or "")
