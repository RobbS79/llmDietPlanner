"""
Backfill CuratedRecipe.dish_role via an LLM classification pass.

`meal_types` says WHEN a dish may appear; `dish_role` says whether it can BE
the meal (a Czech oběd is a warm main — side salads, dips and breakfast dishes
must not carry it; see recipe_retrieval._SLOT_ALLOWED_ROLES). This command
tags the whole corpus in batches so the slot-fit gate has data to act on.

Prod usage (DO console):  python manage.py retag_dish_roles [--dry-run]
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe

_VALID_ROLES = {c[0] for c in CuratedRecipe.DishRole.choices}

_SYSTEM_PROMPT = (
    "You classify Czech-market recipes by what they can CARRY in a daily meal "
    "plan. For each recipe return exactly one dish_role:\n"
    "  main — a warm or substantial dish that can be served as a Czech obed "
    "or vecere on its own (includes hearty one-pot soups like gulas, and "
    "composed salads with a full protein portion);\n"
    "  light — breakfast-style or quick-supper dishes: omelettes, scrambled "
    "eggs, toasts, pancakes, porridge, menemen/shakshuka;\n"
    "  soup — brothy or starter soups that accompany a meal rather than "
    "carry it;\n"
    "  side — accompaniments and components: basic/side salads, dips, "
    "spreads, sauces, breads, plain grains or vegetables;\n"
    "  dessert — sweet dishes and baked desserts.\n"
    "Input is a JSON array of recipes. Answer ONLY with a JSON array of "
    '{"slug": ..., "dish_role": ...} covering every input slug. No prose.'
)


def _generate(system_prompt: str, user_text: str) -> str:
    import google.generativeai as genai
    from django.conf import settings

    genai.configure(api_key=getattr(settings, 'GEMINI_API_KEY', None))
    model = genai.GenerativeModel(
        model_name=getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash'),
        system_instruction=system_prompt,
    )
    resp = model.generate_content(
        user_text,
        generation_config=genai.types.GenerationConfig(
            temperature=0.0,
            response_mime_type='application/json',
        ),
    )
    return getattr(resp, 'text', '') or ''


def _describe(recipe: CuratedRecipe) -> dict:
    return {
        'slug': recipe.slug,
        'name': recipe.name_cs,
        'description': recipe.description or '',
        'meal_types': recipe.meal_types or [],
        'ingredients': [i.get('name') for i in (recipe.ingredients or []) if i.get('name')],
        'base_servings': recipe.base_servings,
        'calories_total': (recipe.base_nutrition or {}).get('calories'),
    }


class Command(BaseCommand):
    help = "Classify CuratedRecipe.dish_role (main/light/soup/side/dessert) via LLM."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report, write nothing.')
        parser.add_argument('--force', action='store_true',
                            help='Re-tag recipes that already have a dish_role.')
        parser.add_argument('--batch-size', type=int, default=25)

    def handle(self, *args, **opts):
        qs = CuratedRecipe.objects.order_by('id')
        if not opts['force']:
            qs = qs.filter(dish_role='')
        recipes = list(qs)
        if not recipes:
            self.stdout.write('Nothing to tag.')
            return

        written = skipped = 0
        for start in range(0, len(recipes), opts['batch_size']):
            batch = recipes[start:start + opts['batch_size']]
            payload = json.dumps([_describe(r) for r in batch], ensure_ascii=False)
            try:
                answers = json.loads(_generate(_SYSTEM_PROMPT, payload))
            except Exception as exc:  # noqa: BLE001 — batch failure must not kill the run
                self.stderr.write(f'Batch at #{start} failed: {exc!r}; skipping {len(batch)}.')
                skipped += len(batch)
                continue
            roles = {
                a.get('slug'): str(a.get('dish_role', '')).strip().lower()
                for a in answers if isinstance(a, dict)
            }
            for r in batch:
                role = roles.get(r.slug)
                if role not in _VALID_ROLES:
                    self.stdout.write(f'SKIP {r.slug}: unusable role {role!r}')
                    skipped += 1
                    continue
                self.stdout.write(f'{r.slug}: {r.dish_role or "(empty)"} -> {role}')
                if not opts['dry_run']:
                    r.dish_role = role
                    r.save(update_fields=['dish_role'])
                written += 1

        verb = 'Would write' if opts['dry_run'] else 'Wrote'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {written} role(s), skipped {skipped}, of {len(recipes)} candidate(s).'
        ))
