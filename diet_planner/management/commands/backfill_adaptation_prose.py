"""Repair the prose the availability rescue left stale.

`apply_availability_substitutions` filters `.filter(adaptation_note='')`, so
every row it has already touched is beyond its reach — and until PR #80 it
rewrote neither the prose nor the `optional` ingredient entries. This command is
the complement: it finishes rewrites the corpus has already disclosed, and it
introduces no swap the recipe does not already claim.

Nothing here rescues a recipe. The gating was settled when the row was adapted.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import CuratedRecipe
from diet_planner.services.ingredient_availability import (
    availability_index, compute_shopping_difficulty,
)
from diet_planner.services.ingredient_substitution import (
    SubstitutionPlan, apply_changes_to_ingredients, diff_applied_changes,
    disclosed_swaps, plan_substitutions, substitution_table,
)
from diet_planner.services.recipe_curation import judge_curated_recipe
from diet_planner.services.substitution_rewrite import (
    RewriteError, reset_usage, rewrite_prose, usage_snapshot,
)

_NOTE_PREFIX = 'Upraveno pro dostupnost v českých obchodech: '
_NOTE_MAX = CuratedRecipe._meta.get_field('adaptation_note').max_length


def _judge_rejected(verdict: dict) -> bool:
    """Did the judge actively reject this rewrite?

    `judge_curated_recipe` returns `JudgeVerdict.as_stats()`, which has no
    'passed' key — the same shape the rescue command reads.
    """
    if not verdict.get('ran'):
        return False
    return (verdict.get('verdict') != 'coherent'
            or bool(verdict.get('high_severity_count')))


class Command(BaseCommand):
    help = 'Repair stale prose and optional ingredient lines on adapted recipes'

    def add_arguments(self, parser):
        parser.add_argument('--slug', help='Restrict to one recipe')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--skip-judge', action='store_true',
            help='Skip the coherence judge (for offline reruns; not for prod)')

    def handle(self, *args, **options):
        reset_usage()
        repaired = skipped = failed = unjudged = 0

        qs = CuratedRecipe.objects.exclude(adaptation_note='').order_by('id')
        if options['slug']:
            qs = qs.filter(slug=options['slug'])

        table = substitution_table()
        if not table:
            self.stdout.write(self.style.WARNING(
                'no availability substitutions loaded — '
                'run load_availability_substitutions first'))
            return
        index = availability_index()

        for recipe in qs.iterator():
            if options['limit'] is not None and repaired >= options['limit']:
                break

            applied = diff_applied_changes(
                recipe.original_ingredients, recipe.ingredients)
            if not applied:
                # No usable snapshot, or nothing was ever swapped: there is no
                # disclosure to finish and no change list to describe.
                skipped += 1
                continue

            disclosed = disclosed_swaps(recipe.adaptation_note, applied)

            # Step 1 — optional entries the rescue skipped. `gate=False`
            # because `saveable` guards against *introducing* a change, and
            # the disclosure filter below means we introduce none.
            plan = plan_substitutions(recipe, table, index=index, gate=False)
            optional = [
                c for c in plan.optional_changes
                if (c.old_name.strip().lower(),
                    c.new_name.strip().lower()) in disclosed
            ]
            for change in plan.optional_changes:
                if change not in optional:
                    self.stdout.write(
                        f'  {recipe.slug}: leaving undisclosed optional swap '
                        f'{change.old_name} → {change.new_name}')

            new_ingredients = recipe.ingredients
            if optional:
                new_ingredients = apply_changes_to_ingredients(
                    recipe.ingredients,
                    SubstitutionPlan(changes=[], optional_changes=optional))
                # The prose must describe the list as it now stands.
                applied = diff_applied_changes(
                    recipe.original_ingredients, new_ingredients)

            # Step 2 — the prose. The change list is the diff, so the rewrite
            # describes the list as it actually stands, not as today's table
            # would have swapped it.
            plan_for_prose = SubstitutionPlan(changes=applied)
            try:
                new_name, new_description = rewrite_prose(
                    recipe.name_cs, recipe.description, plan_for_prose)
            except RewriteError as exc:
                failed += 1
                self.stdout.write(self.style.WARNING(
                    f'  {recipe.slug}: prose rewrite failed: {exc}'))
                continue

            prose_changed = (new_name != recipe.name_cs
                             or new_description != recipe.description)
            if new_ingredients == recipe.ingredients and not prose_changed:
                skipped += 1
                continue

            self.stdout.write(f'{recipe.slug}: {plan_for_prose.summary()}')
            if prose_changed:
                self.stdout.write(f'    {recipe.name_cs!r} -> {new_name!r}')

            if options['dry_run']:
                repaired += 1
                continue

            # Judge the CANDIDATE, not the stored row: build an unsaved copy.
            candidate = CuratedRecipe(
                id=recipe.id, slug=recipe.slug, name_cs=new_name,
                description=new_description,
                ingredients=new_ingredients, instructions=recipe.instructions,
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

            # Every applied swap should already be named in the note — the
            # disclosure filter guarantees it for the optional entries we add.
            # It is not guaranteed for what the rescue itself applied: the note
            # truncates at 300 chars, so a row can carry food its note never
            # names. Extend it rather than let the prose describe an
            # undisclosed swap.
            note = recipe.adaptation_note
            named = disclosed_swaps(note, [])
            missing = [c for c in applied
                       if (c.old_name.strip().lower(),
                           c.new_name.strip().lower()) not in named]
            if missing:
                extra = SubstitutionPlan(changes=missing).summary()
                note = (f'{note}, {extra}' if note else _NOTE_PREFIX + extra)
                note = note[:_NOTE_MAX]
                self.stdout.write(f'    note extended: {extra}')

            with transaction.atomic():
                recipe.ingredients = new_ingredients
                # slug is deliberately NOT regenerated: the URL is public.
                recipe.name_cs = new_name
                recipe.description = new_description
                recipe.adaptation_note = note
                tier, blockers = compute_shopping_difficulty(recipe, index=index)
                recipe.shopping_difficulty = tier
                recipe.shopping_blockers = blockers
                recipe.save(update_fields=[
                    'ingredients', 'name_cs', 'description', 'adaptation_note',
                    'shopping_difficulty', 'shopping_blockers', 'updated_at',
                ])
            repaired += 1

        prefix = '[dry-run] ' if options['dry_run'] else ''
        summary = f'{prefix}repaired={repaired} skipped={skipped} failed={failed}'
        if unjudged:
            summary += f' unjudged={unjudged}'
        self.stdout.write(self.style.SUCCESS(summary))

        # The run spends real tokens; report the bill rather than let it pass
        # silently. `unmetered` is kept separate so an unknown cost can never
        # read as a zero cost.
        usage = usage_snapshot()
        self.stdout.write(
            f"  llm: calls={usage['calls']} "
            f"unmetered={usage['unmetered_calls']} "
            f"tokens={usage['total_tokens']}")
