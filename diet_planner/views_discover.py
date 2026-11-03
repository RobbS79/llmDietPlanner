"""First-visit API (spec 2026-11-03): anonymous search, sheet, deals, list."""
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.entitlements import saved_list_allowance
from diet_planner.client_ip import client_ip
from diet_planner.models import CuratedRecipe, SavedShoppingList
from diet_planner.services.discover import discover
from diet_planner.services.discover_cards import recipe_card, recipe_sheet
from diet_planner.services.discover_guard import (
    challenge_needed, result_key, take_llm_slot, verify_challenge,
)
from diet_planner.services.recipe_deals import active_deal_index
from diet_planner.services.shopping_compose import compose_shopping_list
from diet_planner.throttles import ComposeThrottle, DiscoverBurstThrottle, DiscoverDayThrottle

_RESULT_TTL = 60 * 60 * 24
_MAX_LIST_RECIPES = 12


def _ok(data, code=status.HTTP_200_OK):
    return Response({'status': 'success', 'data': data}, status=code)


def _err(code, message, http):
    return Response({'status': 'error', 'code': code, 'error': message}, status=http)


def _ident(request):
    return client_ip(request)


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _published(ids):
    if not isinstance(ids, list):
        return []
    ids = [int(i) for i in ids if str(i).isdigit()][:_MAX_LIST_RECIPES]
    by_id = {r.id: r for r in CuratedRecipe.objects.filter(
        id__in=ids, status=CuratedRecipe.Status.PUBLISHED)}
    return [by_id[i] for i in ids if i in by_id]


class DiscoverView(APIView):
    permission_classes = []
    throttle_classes = [DiscoverBurstThrottle, DiscoverDayThrottle]

    def post(self, request):
        q = str(request.data.get('q', '') or '')[:300]
        page = max(_int(request.data.get('page', 0) or 0, 0), 0)
        ident = _ident(request)
        token = request.data.get('turnstile_token', '')
        if token:
            verify_challenge(token, ident)
        if challenge_needed(ident):
            return _err('CHALLENGE_REQUIRED', 'Potvrď prosím, že nejsi robot.', status.HTTP_403_FORBIDDEN)

        key = result_key(q, page)
        cached = cache.get(key)
        if cached is not None:
            return _ok(cached)

        # An empty recipes list with exact=False (nothing meets the restrictions)
        # is a valid answer and passes through as is.
        result = discover(q, page, llm_allowed=bool(q) and take_llm_slot())
        index, slugs = active_deal_index(), {}
        data = {**result, 'recipes': [recipe_card(r, deal_index=index, slug_cache=slugs)
                                      for r in result['recipes']]}
        cache.set(key, data, _RESULT_TTL)
        return _ok(data)


class DiscoverRecipeView(APIView):
    permission_classes = []
    throttle_classes = [ComposeThrottle]

    def get(self, request, pk: int):
        recipe = get_object_or_404(CuratedRecipe, pk=pk, status=CuratedRecipe.Status.PUBLISHED)
        return _ok(recipe_sheet(recipe, deal_index=active_deal_index(), slug_cache={}))


class DealsThisWeekView(APIView):
    permission_classes = []

    def get(self, request):
        deals = sorted(active_deal_index().values(), key=lambda d: d['valid_until'])
        return _ok({'deals': [{
            'canonical': d['canonical'], 'name': d['display_name'], 'shop': d['shop'],
            'valid_until': d['valid_until'],
        } for d in deals[:12]]})


class ShoppingListComposeView(APIView):
    permission_classes = []
    throttle_classes = [ComposeThrottle]

    def post(self, request):
        recipes = _published(request.data.get('recipe_ids') or [])
        people = _int(request.data.get('people', 2), 2)
        lines = compose_shopping_list(recipes, people=people, deal_index=active_deal_index())
        return _ok({'recipes': [recipe_card(r, deal_index={}, slug_cache={}) for r in recipes],
                    'lines': lines})


class SavedShoppingListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        lists = SavedShoppingList.objects.filter(user=request.user)[:20]
        return _ok({'lists': [{'id': l.id, 'recipe_ids': l.recipe_ids, 'people': l.people,
                               'at_home': l.at_home, 'query': l.query,
                               'created_at': l.created_at.isoformat()} for l in lists],
                    'allowance': saved_list_allowance(request.user)})

    def post(self, request):
        allowance = saved_list_allowance(request.user)
        if not allowance['can_save']:
            return _err('LIST_LIMIT',
                        f"Tento měsíc už máš uložené {allowance['limit']} seznamy. S předplatným bez omezení.",
                        status.HTTP_402_PAYMENT_REQUIRED)
        recipes = _published(request.data.get('recipe_ids') or [])
        if not recipes:
            return _err('EMPTY_LIST', 'Seznam je prázdný.', status.HTTP_400_BAD_REQUEST)
        people = min(max(_int(request.data.get('people', 2) or 2, 2), 1), 6)
        at_home = request.data.get('at_home') or []
        saved = SavedShoppingList.objects.create(
            user=request.user, recipe_ids=[r.id for r in recipes], people=people,
            at_home=[str(k)[:120] for k in (at_home if isinstance(at_home, list) else [])][:200],
            query=str(request.data.get('query', '') or '')[:300])
        return _ok({'id': saved.id}, status.HTTP_201_CREATED)
