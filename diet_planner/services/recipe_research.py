"""
Chat-triggered web recipe acquisition (refine chat v2).

A RecipeResearchJob is created by the refine agent's `research_web` tool and
executed by `research_recipe_task`. Flow: discover candidate source URLs
(Gemini, Google-Search-grounded when the SDK/model supports it) -> run each
through the existing `curate_from_source` pipeline -> save the first success
as a draft owned by the requesting user (origin=chat_web).

Integrity policy (spec 2026-07-27, decision 1):
  * portion plausibility: HARD (curate_from_source enforces it)
  * attribution:          HARD (no fetched source page -> no recipe)
  * dietary tags:         HARD (checked here against the goal/profile)
  * catalog mapping:      SOFT (unmapped ingredients kept, simply unpriced)

Everything is fail-soft: the job ends `ready` or `failed`, never raises out.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable, Dict, List, Optional

from django.conf import settings
from django.utils import timezone

from diet_planner.models import CuratedRecipe, DietaryGoal, RecipeResearchJob
from diet_planner.services.recipe_curation import (
    _save_with_unique_slug,
    curate_from_source,
)
from diet_planner.services.recipe_retrieval import required_tags_for_goal

logger = logging.getLogger(__name__)

DAILY_CAP = 5
MAX_SOURCES = 5

_FAIL_REPLIES = {
    'no_sources': 'Bohužel jsem na webu nenašel žádný vhodný recept. Zkuste to prosím popsat jinak.',
    'all_sources_failed': 'Našel jsem pár receptů, ale žádný se nepodařilo spolehlivě zpracovat. Zkuste to prosím jinak nebo později.',
    'gates_failed': 'Recept jsem našel, ale neodpovídá vašim stravovacím omezením, takže ho nenabídnu.',
    'error': 'Při hledání receptu se něco pokazilo. Zkuste to prosím znovu.',
}


def can_start_research(user) -> bool:
    """True while the user is under DAILY_CAP jobs since local midnight."""
    today = timezone.localdate()
    used = RecipeResearchJob.objects.filter(user=user, created_at__date=today).count()
    return used < DAILY_CAP


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

_DISCOVERY_PROMPT = (
    "Find up to {n} real, currently reachable web pages with a full recipe for: "
    "\"{query}\". Prefer well-known recipe sites with schema.org/Recipe markup; "
    "any language is fine (it will be translated). Return ONLY a JSON array of "
    "objects: [{{\"url\": \"https://...\", \"name\": \"site or creator name\"}}]. "
    "Concrete recipe pages only — no category pages, no search results, no video-only pages."
)


def _default_discovery_generate(prompt: str) -> str:
    """Gemini call for URL discovery. Tries Google-Search grounding; on any SDK
    /model rejection falls back to an ungrounded call. Hallucinated URLs are
    harmless downstream: curate_from_source must successfully fetch and parse a
    page, so a dead link just gets skipped."""
    import google.generativeai as genai

    genai.configure(api_key=getattr(settings, 'GEMINI_API_KEY', None))
    model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash')
    try:
        model = genai.GenerativeModel(model_name, tools='google_search_retrieval')
        resp = model.generate_content(prompt)
        return getattr(resp, 'text', '') or ''
    except Exception as exc:
        logger.info("recipe_research: grounded discovery unavailable (%s), going ungrounded", exc)
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(prompt)
        return getattr(resp, 'text', '') or ''


def discover_recipe_sources(
    query: str,
    *,
    generate: Optional[Callable[[str], str]] = None,
) -> List[Dict[str, str]]:
    """Up to MAX_SOURCES {'url','name'} entries. Never raises; failure -> []."""
    from diet_planner.services.prompt_facets import _strip_code_fence

    gen = generate or _default_discovery_generate
    try:
        raw = gen(_DISCOVERY_PROMPT.format(n=MAX_SOURCES, query=query.strip()))
        data = json.loads(_strip_code_fence(raw))
    except Exception as exc:
        logger.warning("recipe_research: discovery failed for %r: %s", query, exc)
        return []
    out: List[Dict[str, str]] = []
    seen = set()
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        url = str(item.get('url') or '').strip()
        if not re.match(r'^https?://', url) or url in seen:
            continue
        seen.add(url)
        out.append({'url': url, 'name': str(item.get('name') or '').strip()})
        if len(out) >= MAX_SOURCES:
            break
    return out


# ---------------------------------------------------------------------------
# Job runner
# ---------------------------------------------------------------------------

def _slot_of(meal_identifier: str) -> str:
    parts = (meal_identifier or '').split(':')
    return parts[2] if len(parts) > 2 else 'lunch'


def _goal_of(job: RecipeResearchJob) -> Optional[DietaryGoal]:
    parts = (job.meal_identifier or '').split(':')
    try:
        return DietaryGoal.objects.get(id=int(parts[0]), user=job.user)
    except Exception:
        return None


def _finish(job: RecipeResearchJob, *, status: str, fail_reason: str = '',
            recipe: Optional[CuratedRecipe] = None, reply_text: str = '') -> None:
    job.status = status
    job.fail_reason = fail_reason
    job.result_recipe = recipe
    job.reply_text = reply_text or _FAIL_REPLIES.get(fail_reason, '')
    job.save(update_fields=['status', 'fail_reason', 'result_recipe', 'reply_text', 'updated_at'])


def run_research_job(job_id: int) -> Dict[str, str]:
    """Execute one research job end-to-end. Never raises; returns a small
    status dict for the Celery result backend."""
    try:
        job = RecipeResearchJob.objects.get(id=job_id)
    except RecipeResearchJob.DoesNotExist:
        return {'status': 'missing'}
    try:
        return _run(job)
    except Exception as exc:  # noqa: BLE001 — job must end in a terminal state
        logger.exception("recipe_research: job %s crashed: %s", job_id, exc)
        _finish(job, status=RecipeResearchJob.Status.FAILED, fail_reason='error')
        return {'status': 'failed', 'reason': 'error'}


def _run(job: RecipeResearchJob) -> Dict[str, str]:
    slot = _slot_of(job.meal_identifier)
    goal = _goal_of(job)
    required_tags = required_tags_for_goal(goal) if goal else set()

    job.status = RecipeResearchJob.Status.SEARCHING
    job.save(update_fields=['status', 'updated_at'])
    sources = discover_recipe_sources(job.query)
    if not sources:
        _finish(job, status=RecipeResearchJob.Status.FAILED, fail_reason='no_sources')
        return {'status': 'failed', 'reason': 'no_sources'}

    job.status = RecipeResearchJob.Status.CURATING
    job.save(update_fields=['status', 'updated_at'])

    saw_gate_failure = False
    for src in sources:
        result = curate_from_source(
            {'dish_name': job.query, 'source_url': src['url'], 'source_name': src['name']},
            persist=False,
        )
        if result.skipped:
            # Source already in corpus: reuse it if the requester may see it.
            existing = CuratedRecipe.objects.filter(source_url=src['url']).first()
            if existing and (
                existing.status == CuratedRecipe.Status.PUBLISHED
                or existing.created_for_user_id == job.user_id
            ):
                if not required_tags.issubset(set(existing.dietary_tags or [])):
                    saw_gate_failure = True
                    continue
                _finish(
                    job, status=RecipeResearchJob.Status.READY, recipe=existing,
                    reply_text=_ready_reply(existing),
                )
                return {'status': 'ready'}
            continue
        if not result.ok or result.recipe is None:
            continue

        recipe = result.recipe
        # Dietary tags are a HARD gate — accept would reject it anyway; fail
        # here with an honest reason instead of a dead-end card.
        if not required_tags.issubset(set(recipe.dietary_tags or [])):
            saw_gate_failure = True
            continue
        # Guarantee the requested slot so the accept gate can pass.
        if slot not in (recipe.meal_types or []):
            recipe.meal_types = list(recipe.meal_types or []) + [slot]

        recipe.origin = CuratedRecipe.Origin.CHAT_WEB
        recipe.created_for_user = job.user
        try:
            _save_with_unique_slug(recipe)
        except Exception as exc:  # noqa: BLE001
            logger.warning("recipe_research: save failed for %s: %s", src['url'], exc)
            continue
        _finish(
            job, status=RecipeResearchJob.Status.READY, recipe=recipe,
            reply_text=_ready_reply(recipe),
        )
        return {'status': 'ready'}

    reason = 'gates_failed' if saw_gate_failure else 'all_sources_failed'
    _finish(job, status=RecipeResearchJob.Status.FAILED, fail_reason=reason)
    return {'status': 'failed', 'reason': reason}


def _ready_reply(recipe: CuratedRecipe) -> str:
    src = f" (podle {recipe.source_name})" if recipe.source_name else ""
    return f"Našel jsem na webu recept: {recipe.name_cs}{src}. Mrkněte na návrh níže."
