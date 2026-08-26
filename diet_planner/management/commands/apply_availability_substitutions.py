"""Rewrite unshoppable recipes into Czech-shoppable ones.

All-or-nothing per recipe: the ingredient rewrite, the instruction rewrite and
the coherence judge must all succeed, or the recipe is left exactly as its
author wrote it. We are editing credited third-party recipes, so
`original_ingredients` keeps the original and `adaptation_note` discloses the
change on the recipe page.

See docs/superpowers/specs/2026-08-11-ingredient-obtainability-design.md §6
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability
from diet_planner.services.ingredient_availability import (
    availability_index,
    compute_shopping_difficulty,
)
from diet_planner.services.ingredient_substitution import (
    apply_changes_to_ingredients,
    plan_substitutions,
    substitution_table,
)
from diet_planner.services.recipe_curation import judge_curated_recipe
from diet_planner.services.substitution_rewrite import (
    RewriteError, reset_usage, rewrite_instructions, rewrite_prose,
    usage_snapshot,
)

_NOTE_PREFIX = 'Upraveno pro dostupnost v českých obchodech: '

#: adaptation_note's max_length. Truncating here rather than letting the DB
#: raise mid-batch.
_NOTE_MAX = CuratedRecipe._meta.get_field('adaptation_note').max_length


def _judge_rejected(verdict: dict) -> bool:
    """Did the judge actively reject this rewrite?

    `judge_curated_recipe` returns `JudgeVerdict.as_stats()`, which has no
    boolean pass/fail — it reports `ran`, a four-value `verdict`, and issue
    counts. Per JudgeVerdict's own docstring, a verdict is only meaningful
    when `ran` is True; ran=False means UNKNOWN, and unknown is not rejection.
    'minor_issues' passes, but a high-severity issue never does.
    """
    if not verdict.get('ran'):
        return False
    if verdict.get('verdict') == 'incoherent':
        return True
    return bool(verdict.get('high_severity_count'))


class Command(BaseCommand):
    help = 'Substitute hard-to-buy ingredients in curated recipes.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--slug', default=None, help='Adapt one recipe only')
        parser.add_argument(
            '--skip-judge', action='store_true',
            help='Skip the coherence judge (for offline reruns; not for prod)')
        parser.add_argument(
            '--tier', choices=['all', 'specialty'], default='all',
            help=("'specialty' edits only recipes whose rescue lifts a "
                  "SPECIALTY blocker — the tier retrieval gates on. 'all' "
                  "(default) also improves findable recipes."))

    def handle(self, *args, **options):
        reset_usage()
        table = substitution_table()
        if not table:
            self.stdout.write(self.style.WARNING(
                'no availability substitutions loaded — '
                'run load_availability_substitutions first'))
            return

        index = availability_index()
        qs = CuratedRecipe.objects.exclude(
            shopping_difficulty=Availability.COMMON,
        ).filter(adaptation_note='').order_by('id')
        if options['slug']:
            qs = qs.filter(slug=options['slug'])

        adapted = skipped = failed = unjudged = 0

        for recipe in qs.iterator():
            if options['limit'] is not None and adapted >= options['limit']:
                break

            plan = plan_substitutions(recipe, table, index=index)
            if not plan.saveable:
                skipped += 1
                if plan.blocking:
                    self.stdout.write(
                        f'  skip {recipe.slug}: specialty, no swap — '
                        f'{", ".join(plan.blocking)}')
                continue

            # --tier=specialty: only edit a recipe when the rescue clears a
            # gated ingredient. A findable-only rewrite is a real improvement
            # but it touches an attributed recipe for a rank nudge, so it is
            # opt-in rather than something a bare run does.
            if options['tier'] == 'specialty' and not any(
                    index.get(c.old_slug) == Availability.SPECIALTY
                    for c in plan.changes):
                skipped += 1
                continue

            self.stdout.write(f'{recipe.slug}: {plan.summary()}')

            new_ingredients = apply_changes_to_ingredients(recipe.ingredients, plan)
            try:
                new_instructions = rewrite_instructions(recipe.instructions, plan)
                # The prose around the steps makes claims too: a title still
                # promising the removed ingredient is the first thing a reader
                # sees. Same fail-closed contract as the steps.
                new_name, new_description = rewrite_prose(
                    recipe.name_cs, recipe.description, plan)
            except RewriteError as exc:
                failed += 1
                self.stdout.write(self.style.WARNING(f'  rewrite failed: {exc}'))
                continue

            if options['dry_run']:
                for change in plan.changes:
                    self.stdout.write(
                        f'    - {change.old_name} {change.new_quantity}'
                        f' {change.new_unit} -> {change.new_name}')
                adapted += 1
                continue

            # Judge the CANDIDATE, not the stored row: build an unsaved copy.
            candidate = CuratedRecipe(
                id=recipe.id, slug=recipe.slug, name_cs=new_name,
                description=new_description,
                ingredients=new_ingredients, instructions=new_instructions,
                base_servings=recipe.base_servings,
            )
            if not options['skip_judge']:
                verdict = judge_curated_recipe(candidate)
                if _judge_rejected(verdict):
                    failed += 1
                    self.stdout.write(self.style.WARNING(
                        f"  judge rejected the rewrite — discarded "
                        f"(verdict={verdict.get('verdict')}, "
                        f"high={verdict.get('high_severity_count')})"))
                    continue
                if not verdict.get('ran'):
                    # Applying unjudged is a decision, not a detail: say it.
                    unjudged += 1
                    self.stdout.write(self.style.WARNING(
                        f"  judge did not run ({verdict.get('error') or 'disabled'})"
                        f" — applying unjudged"))

            with transaction.atomic():
                if not recipe.original_ingredients:
                    recipe.original_ingredients = recipe.ingredients
                recipe.ingredients = new_ingredients
                recipe.instructions = new_instructions
                # slug is deliberately NOT regenerated: the URL is public.
                recipe.name_cs = new_name
                recipe.description = new_description
                recipe.adaptation_note = (_NOTE_PREFIX + plan.summary())[:_NOTE_MAX]
                tier, blockers = compute_shopping_difficulty(recipe, index=index)
                recipe.shopping_difficulty = tier
                recipe.shopping_blockers = blockers
                recipe.save(update_fields=[
                    'ingredients', 'instructions', 'name_cs', 'description',
                    'adaptation_note', 'original_ingredients',
                    'shopping_difficulty', 'shopping_blockers', 'updated_at',
                ])
            adapted += 1

        prefix = '[dry-run] ' if options['dry_run'] else ''
        summary = f'{prefix}adapted={adapted} skipped={skipped} failed={failed}'
        if unjudged:
            summary += f' unjudged={unjudged}'
        self.stdout.write(self.style.SUCCESS(summary))

        # The bill. Printed even on a dry run, because a dry run spends the
        # same tokens as a real one — the rewrite happens before the dry-run
        # branch by design.
        usage = usage_snapshot()
        model = getattr(settings, 'GEMINI_MODEL', '(unset)')
        line = (f'{prefix}llm model={model} calls={usage["calls"]} '
                f'prompt_tokens={usage["prompt_tokens"]} '
                f'output_tokens={usage["output_tokens"]} '
                f'total_tokens={usage["total_tokens"]}')
        if usage['unmetered_calls']:
            line += f' unmetered_calls={usage["unmetered_calls"]}'
        self.stdout.write(line)
