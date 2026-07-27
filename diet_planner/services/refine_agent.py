"""
Refine chat v2: agentic tool loop (spec 2026-07-27).

`run_refine_turn` drives one preview turn: Gemini (function calling) converses
about the CURRENT recipe and may call:

  * search_corpus  — top-5 pre-gated corpus candidates. Eligibility (slot,
    dietary, mapping) is computed IN CODE; the model only chooses among what
    the gate returns and can never fabricate a card (candidate ids are
    validated against the tool's own results).
  * research_web   — creates a RecipeResearchJob + enqueues the Celery task;
    the chat polls it separately.

The caller (RecipeRefineView) treats ANY exception here as "fall back to the
v1 facet path", so this module may raise freely on unexpected states.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Set

from django.conf import settings

from diet_planner.models import CuratedRecipe, RecipeResearchJob
from diet_planner.services import recipe_research
from diet_planner.services.recipe_retrieval import (
    eligible_recipes_for_slot,
    score_recipe,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
TOP_N = 5

_FALLBACK_REPLY = 'Omlouvám se, teď mi to nemyslí. Zkuste to prosím ještě jednou.'

_SYSTEM_PROMPT = (
    "Jsi přátelský kuchařský asistent služby Vařto. Pomáháš uživateli vybrat "
    "náhradu za JEDNO jídlo v jeho jídelníčku. Odpovídáš VŽDY česky, stručně "
    "(1–3 věty), přirozeně a konkrétně.\n"
    "Pravidla:\n"
    "1. Jídla smíš nabízet POUZE z výsledků nástroje search_corpus. Nikdy si "
    "recept nevymýšlej.\n"
    "2. Když v databázi nic vhodného není, nebo chce uživatel něco speciálního, "
    "zavolej research_web — a řekni uživateli, že hledáš na internetu (najde se "
    "to na pozadí, výsledek přijde do chatu).\n"
    "3. Nikdy nezmiňuj ceny ani dostupnost surovin.\n"
    "4. Nikdy netvrď, že něco hledáš nebo budeš hledat na internetu, pokud jsi "
    "v TOMTO tahu skutečně nezavolal nástroj research_web. Slíbené hledání, "
    "které neproběhne, je pro uživatele slepá ulička.\n"
    "5. Respektuj uvedená stravovací omezení uživatele i v konverzaci.\n"
    "Poslední zpráva každého tahu MUSÍ být POUZE tento JSON objekt a nic víc — "
    "žádný text před ním ani za ním: "
    '{"reply": "<tvá česká odpověď>", "candidate_id": <číselné id z posledního '
    "search_corpus, jinak null>}. Celá tvá odpověď uživateli patří do pole "
    '"reply".'
)

_SEARCH_CORPUS_DECL = {
    'name': 'search_corpus',
    'description': (
        'Search the curated recipe database for the current meal slot. Returns '
        'up to 5 eligible candidates. Dietary restrictions are enforced '
        'automatically; do not pass them.'
    ),
    'parameters': {
        'type': 'object',
        'properties': {
            'cuisines': {'type': 'array', 'items': {'type': 'string'},
                         'description': 'lowercase cuisine slugs'},
            'wanted_ingredients': {'type': 'array', 'items': {'type': 'string'}},
            'avoided_ingredients': {'type': 'array', 'items': {'type': 'string'}},
            'styles': {'type': 'array', 'items': {'type': 'string'},
                       'description': 'e.g. quick, comfort, light'},
            'emphases': {'type': 'array', 'items': {'type': 'string'},
                         'description': 'high_protein, low_carb, low_calorie, budget'},
        },
    },
}

_RESEARCH_WEB_DECL = {
    'name': 'research_web',
    'description': (
        'Start a background web search for a brand-new recipe not in the '
        'database. Use when the corpus cannot satisfy the request or the user '
        'asks for something special. Returns a job id; the result arrives in '
        'the chat later.'
    ),
    'parameters': {
        'type': 'object',
        'properties': {
            'query': {'type': 'string',
                      'description': 'what to search for, in Czech or English'},
        },
        'required': ['query'],
    },
}


@dataclass
class AgentTurn:
    reply_text: str
    candidate: Optional[CuratedRecipe] = None
    research_job_id: Optional[int] = None


class GeminiAgentSession:
    """Thin wrapper over google-generativeai chat + function calling. All SDK
    types stay inside this class so the loop is testable with a fake."""

    def __init__(self, system_prompt: str):
        import google.generativeai as genai

        genai.configure(api_key=getattr(settings, 'GEMINI_API_KEY', None))
        self._genai = genai
        model = genai.GenerativeModel(
            model_name=getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash'),
            system_instruction=system_prompt,
            tools=[{'function_declarations': [_SEARCH_CORPUS_DECL, _RESEARCH_WEB_DECL]}],
        )
        self._chat = model.start_chat()

    def send_text(self, text: str) -> Dict:
        return self._parse(self._chat.send_message(text))

    def send_tool_result(self, name: str, payload: Dict) -> Dict:
        part = self._genai.protos.Part(
            function_response=self._genai.protos.FunctionResponse(
                name=name, response={'result': payload},
            )
        )
        return self._parse(self._chat.send_message(part))

    @staticmethod
    def _parse(resp) -> Dict:
        try:
            parts = resp.candidates[0].content.parts
        except (AttributeError, IndexError):
            return {'tool_call': None, 'text': ''}
        for part in parts:
            fc = getattr(part, 'function_call', None)
            if fc is not None and getattr(fc, 'name', ''):
                return {'tool_call': {'name': fc.name, 'args': dict(fc.args or {})},
                        'text': None}
        try:
            text = resp.text or ''
        except Exception:
            text = ''
        return {'tool_call': None, 'text': text}


def _context_message(
    *, meal_type: str, current_meal: Dict, required_tags: Set[str],
    used_cuisines: Sequence[str], messages: List[Dict],
) -> str:
    transcript = '\n'.join(f"{m['role']}: {m['text']}" for m in messages)
    return (
        f"Slot: {meal_type}\n"
        f"Aktuální jídlo: {current_meal.get('name') or '(neznámé)'} — "
        f"{current_meal.get('description') or ''}\n"
        f"Stravovací omezení (vynucená systémem): "
        f"{', '.join(sorted(required_tags)) or 'žádná'}\n"
        f"Kuchyně už použité v plánu: {', '.join(used_cuisines) or 'žádné'}\n"
        f"Konverzace:\n{transcript}"
    )


def _tool_search_corpus(
    args: Dict, *, meal_type: str, required_tags: Set[str],
    pool: List[CuratedRecipe], exclude_ids: Set[int],
    used_recipe_ids: Set[int], used_cuisines: Sequence[str],
) -> Dict:
    """Execute search_corpus: hard gate in code, model-supplied soft criteria."""
    from diet_planner.services.prompt_facets import PromptFacets

    def _set(key):
        v = args.get(key)
        return {str(x).strip().lower() for x in v if str(x).strip()} if isinstance(v, (list, tuple)) else set()

    facets = PromptFacets(
        cuisines=_set('cuisines'),
        wanted_ingredients=_set('wanted_ingredients'),
        avoided_ingredients=_set('avoided_ingredients'),
        styles=_set('styles'),
        emphases=_set('emphases'),
    )
    active = None if facets.is_empty() else facets
    candidates = eligible_recipes_for_slot(
        meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=active,
    )
    if not candidates and active is not None:
        # Soft criteria too narrow — retry unsteered so the model can say so
        # honestly and still offer the best available dish.
        candidates = eligible_recipes_for_slot(
            meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=None,
        )
    ranked = sorted(
        candidates,
        key=lambda r: score_recipe(
            r, used_recipe_ids=used_recipe_ids, used_cuisines=used_cuisines, facets=active,
        ),
        reverse=True,
    )[:TOP_N]
    return {
        'candidates': [
            {
                'id': r.id,
                'name': r.name_cs,
                'description': r.description,
                'total_time': r.total_time or None,
                'calories': (r.base_nutrition or {}).get('calories'),
                'cuisine': r.cuisine,
                'dietary_tags': r.dietary_tags or [],
            }
            for r in ranked
        ],
    }


def _tool_research_web(args: Dict, *, user, meal_identifier: str):
    """Execute research_web: cap check + job creation + enqueue. Returns
    (payload_for_model, job_id_or_None)."""
    query = str(args.get('query') or '').strip()[:300]
    if not query:
        return {'error': 'empty_query'}, None
    if not recipe_research.can_start_research(user):
        return {'error': 'cap_reached',
                'detail': 'Denní limit hledání na webu je vyčerpán (5/den).'}, None
    job = RecipeResearchJob.objects.create(
        user=user, meal_identifier=meal_identifier, query=query,
    )
    from diet_planner.tasks import research_recipe_task
    try:
        research_recipe_task.delay(job.id)
    except Exception:  # broker down — run inline as a last resort
        logger.warning("refine_agent: broker unavailable, running research inline")
        recipe_research.run_research_job(job.id)
    return {'job_id': job.id, 'status': 'queued'}, job.id


def _coerce_candidate_id(cid) -> Optional[int]:
    """Model emits ints AND quoted ints ("18944" — seen in prod QA 2026-07-27)."""
    if isinstance(cid, bool):
        return None
    if isinstance(cid, int):
        return cid
    if isinstance(cid, str) and cid.strip().isdigit():
        return int(cid.strip())
    return None


def _extract_contract(text: str) -> Optional[Dict]:
    """Find the LAST parseable JSON object with a string "reply" anywhere in the
    text. Gemini routinely prefixes the contract with prose (prod QA
    2026-07-27: 5/6 turns) — the prose is a paraphrase of the reply, so only
    the JSON is surfaced and nothing leaks into the chat bubble."""
    decoder = json.JSONDecoder()
    found = None
    idx = text.find('{')
    while idx != -1:
        try:
            data, _ = decoder.raw_decode(text, idx)
            if isinstance(data, dict) and isinstance(data.get('reply'), str):
                found = data
        except ValueError:
            pass
        idx = text.find('{', idx + 1)
    return found


def _parse_final(text: str) -> Dict:
    """Final-message contract: JSON {reply, candidate_id}, possibly wrapped in
    code fences or prose. A reply with no JSON degrades to plain text."""
    from diet_planner.services.prompt_facets import _strip_code_fence
    data = _extract_contract(_strip_code_fence(text or ''))
    if data is not None:
        return {'reply': data['reply'].strip(),
                'candidate_id': _coerce_candidate_id(data.get('candidate_id'))}
    return {'reply': (text or '').strip(), 'candidate_id': None}


def run_refine_turn(
    *,
    user,
    meal_identifier: str,
    meal_type: str,
    current_meal: Dict,
    required_tags: Set[str],
    pool: List[CuratedRecipe],
    exclude_ids: Set[int],
    used_recipe_ids: Set[int],
    used_cuisines: Sequence[str],
    messages: List[Dict],
    session_factory: Optional[Callable[[str], object]] = None,
) -> AgentTurn:
    """One preview turn of the v2 agent. May raise — the caller falls back to
    the v1 facet path on any exception."""
    factory = session_factory or GeminiAgentSession
    session = factory(_SYSTEM_PROMPT)

    offered_ids: Set[int] = set()
    research_job_id: Optional[int] = None

    out = session.send_text(_context_message(
        meal_type=meal_type, current_meal=current_meal, required_tags=required_tags,
        used_cuisines=used_cuisines, messages=messages,
    ))
    for _ in range(MAX_TOOL_ROUNDS):
        call = out.get('tool_call')
        if not call:
            break
        name, args = call.get('name'), call.get('args') or {}
        if name == 'search_corpus':
            payload = _tool_search_corpus(
                args, meal_type=meal_type, required_tags=required_tags, pool=pool,
                exclude_ids=exclude_ids, used_recipe_ids=used_recipe_ids,
                used_cuisines=used_cuisines,
            )
            offered_ids = {c['id'] for c in payload['candidates']}
            out = session.send_tool_result(name, payload)
        elif name == 'research_web':
            payload, job_id = _tool_research_web(
                args, user=user, meal_identifier=meal_identifier,
            )
            if job_id is not None:
                research_job_id = job_id
            out = session.send_tool_result(name, payload)
        else:
            out = session.send_tool_result(name or 'unknown', {'error': 'unknown_tool'})

    final = _parse_final(out.get('text') or '')
    reply = final['reply'] or _FALLBACK_REPLY

    candidate = None
    cid = final['candidate_id']
    if cid is not None and cid in offered_ids:
        candidate = next((r for r in pool if r.id == cid), None)

    return AgentTurn(reply_text=reply, candidate=candidate,
                     research_job_id=research_job_id)
