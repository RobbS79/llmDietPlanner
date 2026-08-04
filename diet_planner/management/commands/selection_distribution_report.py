"""Measure how plan-selection serves distribute across the published corpus.

Simulates plan generation for a fixed persona set (facets built directly, no
LLM calls, no DB writes) and reports concentration metrics. This is the
before/after harness for serving-distribution changes: run it on two code
states against the same corpus and compare.
"""
import inspect
from collections import Counter
from types import SimpleNamespace

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services import recipe_retrieval as rr
from diet_planner.services.prompt_facets import PromptFacets

# (name, dietary_restrictions free text, PromptFacets kwargs) — mirrors the
# five market personas plus common real prompts seen in prod goals.
PERSONAS = [
    ('no-preferences', '', {}),
    ('meat-lover', '', {'wanted_ingredients': {'maso'}}),
    ('fish-and-rice', '', {'wanted_ingredients': {'ryba', 'rýže'}}),
    ('quick-chicken', '', {'wanted_ingredients': {'kuřecí'}, 'max_time_minutes': 30}),
    ('vegetarian', 'vegetariánská strava', {}),
    ('gf-meat', 'bez lepku', {'wanted_ingredients': {'maso'}}),
    ('protein-veg', '', {'wanted_ingredients': {'zelenina'}, 'emphases': {'high_protein'}}),
    ('pasta', '', {'wanted_ingredients': {'těstoviny'}}),
]


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--regens', type=int, default=5,
                            help='Plans generated per persona (regeneration count)')
        parser.add_argument('--days', type=int, default=5)

    def handle(self, *args, **options):
        regens, days = options['regens'], options['days']
        pool = CuratedRecipe.objects.filter(status=CuratedRecipe.Status.PUBLISHED)
        pool_count = pool.count()

        select_params = inspect.signature(rr.select_recipes_for_plan).parameters
        serves = Counter()
        day1_lunch = {}  # persona -> [recipe id per regen]
        filled = total = 0

        for p_idx, (name, restrictions, facet_kwargs) in enumerate(PERSONAS):
            facets = PromptFacets(**facet_kwargs) if facet_kwargs else None
            seen_ids = set()  # this persona's serve history across regens
            for regen in range(regens):
                goal = SimpleNamespace(
                    pk=p_idx * 1000 + regen, num_days=days,
                    small_meals_per_day=0, snacks_per_day=0,
                    breakfast=True, lunch=True, dinner=True,
                    dietary_restrictions=restrictions,
                )
                kwargs = {'facets': facets}
                if 'recently_served_ids' in select_params:
                    kwargs['recently_served_ids'] = set(seen_ids)
                result = rr.select_recipes_for_plan(goal, **kwargs)
                for day in result['days']:
                    for slot_key, recipe in day['slots'].items():
                        serves[recipe.id] += 1
                        seen_ids.add(recipe.id)
                        if day['day_number'] == 1 and slot_key == 'lunch':
                            day1_lunch.setdefault(name, []).append(recipe.id)
                filled += result['coverage']['filled']
                total += result['coverage']['total']

        total_serves = sum(serves.values())
        distinct = len(serves)
        never = pool_count - distinct
        top15 = sum(c for _, c in serves.most_common(15))
        top15_share = (100.0 * top15 / total_serves) if total_serves else 0.0
        never_pct = (100.0 * never / pool_count) if pool_count else 0.0

        repeat_rates = []
        for ids in day1_lunch.values():
            if len(ids) > 1:
                repeat_rates.append((len(ids) - len(set(ids))) / (len(ids) - 1))
        repeat = sum(repeat_rates) / len(repeat_rates) if repeat_rates else 0.0

        w = self.stdout.write
        w(f'published pool: {pool_count}')
        w(f'slots: {filled}/{total} filled by curated recipes')
        w(f'total serves: {total_serves}')
        w(f'distinct recipes served: {distinct}')
        w(f'never-served: {never} ({never_pct:.1f}% of pool)')
        w(f'top-15 share: {top15_share:.1f}% of serves')
        w(f'day1-lunch repeat rate: {repeat:.2f} (1.00 = same dish every regeneration)')
