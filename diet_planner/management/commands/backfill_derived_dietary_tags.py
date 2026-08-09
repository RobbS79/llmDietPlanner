"""Backfill `DietaryGoal.derived_dietary_tags` for goals generated before the
field existed.

Restrictions typed into the plan prompt ("vegetariánská strava") were honoured
at generation — the LLM reads the prompt — but never persisted, so refine /
replace / swap were blind to them and a vegetarian plan would offer meat swaps.
New plans persist the tags at generation time; this command repairs old ones.

Costs one Gemini flash call per goal, so it is opt-in and bounded by --limit.
Read-only unless --apply is passed.
"""
from django.core.management.base import BaseCommand

from diet_planner.models import DietaryGoal
from diet_planner.services.prompt_facets import extract_prompt_facets
from diet_planner.services.recipe_retrieval import (
    parse_derived_dietary_tags,
    published_cuisine_vocab,
    store_derived_dietary_tags,
)


class Command(BaseCommand):
    help = "Extract prompt-stated dietary restrictions onto existing goals."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=25,
                            help='Maximum goals to process (default 25).')
        parser.add_argument('--goal-id', type=int, default=None,
                            help='Process exactly one goal.')
        parser.add_argument('--apply', action='store_true',
                            help='Write the tags. Without it, only report.')

    def handle(self, *args, **options):
        qs = DietaryGoal.objects.order_by('-id')
        if options['goal_id']:
            qs = qs.filter(id=options['goal_id'])

        vocab = published_cuisine_vocab()
        seen = found = written = 0

        for goal in qs[:options['limit']]:
            # Encrypted field: filtering in SQL is impossible, so skip in Python.
            if parse_derived_dietary_tags(goal.derived_dietary_tags):
                continue
            prompt = (goal.prompt or '').strip()
            if not prompt:
                continue
            seen += 1
            facets = extract_prompt_facets(
                prompt, language=goal.language_code or 'cs', cuisine_vocab=vocab,
            )
            tags = facets.dietary
            if not tags:
                continue
            found += 1
            self.stdout.write(f"goal {goal.id}: {sorted(tags)}  ← {prompt[:70]!r}")
            if options['apply']:
                store_derived_dietary_tags(goal, tags)
                goal.refresh_from_db(fields=['derived_dietary_tags'])
                if parse_derived_dietary_tags(goal.derived_dietary_tags):
                    written += 1

        verb = 'wrote' if options['apply'] else 'would write'
        self.stdout.write(self.style.SUCCESS(
            f"checked {seen} goal(s), {found} carry prompt-stated restrictions, {verb} {written if options['apply'] else found}."
        ))
