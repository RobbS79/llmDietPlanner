"""The user-query farm: demand x phrasing x persona, run against the real
corpus. Read-only — no LLM calls in the default mode, no database writes ever.

This is the report the corpus's real-world coverage is judged by. Two rules
protect its honesty: (1) the default mode builds facets directly from the
query so the number costs nothing and never depends on Gemini being up, with
an opt-in `--extract-facets` mode that exercises the real extractor and
measures its known "Mám X" empty-facet defect; (2) a missing or empty demand
snapshot refuses to print a report at all, rather than a beautiful 100%
coverage over zero terms.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from diet_planner.services import recipe_retrieval as rr
from diet_planner.services.prompt_facets import extract_prompt_facets
from diet_planner.services.user_simulation import (
    PERSONAS, demand_coverage, gate_funnel, generate_queries,
)

_DEFAULT_DEMAND = 'diet_planner/data/demand_index_cz.yaml'
_DEFAULT_TEMPLATES = 'diet_planner/data/prompt_templates_cz.yaml'


def _load_yaml_list(path: str, key: str):
    """The `key` list from a YAML file at `path`, or None if the file is
    missing/unreadable — callers decide whether that's fatal."""
    p = Path(path)
    if not p.is_absolute():
        p = Path(settings.BASE_DIR) / path
    try:
        with open(p, encoding='utf-8') as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return None
    return data.get(key) or []


class Command(BaseCommand):
    help = ('Run the simulated user-query farm against the published corpus. '
            'Read-only: no LLM calls in the default mode, no database writes.')

    def add_arguments(self, parser):
        parser.add_argument('--demand', default=_DEFAULT_DEMAND,
                            help='Path to the demand-index YAML.')
        parser.add_argument('--templates', default=_DEFAULT_TEMPLATES,
                            help='Path to the prompt-templates YAML.')
        parser.add_argument('--queries', type=int, default=200,
                            help='Number of simulated queries to generate.')
        parser.add_argument('--seed', type=int, default=42,
                            help='RNG seed — same seed, same queries.')
        parser.add_argument('--top-n', type=int, default=200,
                            help='How much of the ranked demand to score for coverage.')
        parser.add_argument('--extract-facets', action='store_true',
                            help='Run the real Gemini facet extractor instead of '
                                 'building facets directly from the query. Makes '
                                 'live LLM calls.')

    def handle(self, *args, **options):
        w = self.stdout.write
        demand = _load_yaml_list(options['demand'], 'terms')
        if not demand:
            w(self.style.ERROR(
                f"no demand snapshot found at {options['demand']!r} — refusing "
                f"to print a coverage report over zero terms."))
            return
        templates = _load_yaml_list(options['templates'], 'templates')

        n = options['queries']
        seed = options['seed']
        top_n = options['top_n']
        extract_mode = options['extract_facets']
        mode = 'extract' if extract_mode else 'direct'

        w(f'user-query farm: seed={seed}  queries={n}  mode={mode}')

        queries = generate_queries(demand, templates, PERSONAS, seed=seed, n=n)
        if not queries:
            w(self.style.WARNING('no in-scope demand terms — nothing to simulate.'))
            return

        cuisine_vocab = rr.published_cuisine_vocab() if extract_mode else []

        filled = total = 0
        killer_counts = Counter()
        killer_cross_diet = Counter()
        drop_counts = Counter()
        empty_facets = 0
        extract_calls = 0

        for idx, query in enumerate(queries):
            goal = SimpleNamespace(
                pk=idx, num_days=query.num_days,
                small_meals_per_day=0, snacks_per_day=0,
                breakfast=True, lunch=True, dinner=True,
                dietary_restrictions=query.dietary_restrictions,
            )

            if extract_mode:
                facets = extract_prompt_facets(
                    query.prompt_cs, language='cs', cuisine_vocab=cuisine_vocab)
                extract_calls += 1
                if facets is None or facets.is_empty():
                    empty_facets += 1
            else:
                facets = query.facets

            result = rr.select_recipes_for_plan(goal, facets=facets)
            filled += result['coverage']['filled']
            total += result['coverage']['total']

            required_tags = rr.required_tags_for_goal(goal)
            funnel = gate_funnel(slot=query.slot, required_tags=required_tags,
                                 facets=facets)
            if funnel['killer']:
                killer_counts[funnel['killer']] += 1
                if query.pairing == 'cross-diet':
                    killer_cross_diet[funnel['killer']] += 1
            if funnel['biggest_drop']:
                drop_counts[funnel['biggest_drop']] += 1

        fill_pct = (100.0 * filled / total) if total else 0.0
        w('\n-- slot fill --')
        w(f'  slots filled by curated recipes: {filled}/{total} ({fill_pct:.1f}%)')

        coverage = demand_coverage(demand, top_n=top_n)
        scored = coverage['scored']
        strict_pct = (100.0 * coverage['strict_hits'] / scored) if scored else 0.0
        loose_pct = (100.0 * coverage['loose_hits'] / scored) if scored else 0.0
        w('\n-- demand coverage --')
        w(f'  scored terms (top {top_n}, in-scope): {scored}')
        w(f'  out-of-scope (no meal slot, e.g. desserts/drinks): {coverage["out_of_scope"]}')
        w(f'  strict (we have that dish): {coverage["strict_hits"]}/{scored} ({strict_pct:.1f}%)')
        w(f'  loose (same ingredients at least): {coverage["loose_hits"]}/{scored} ({loose_pct:.1f}%)')

        w('\n-- queries killed, by gate --')
        w('  (cross-diet = a vegan/vegetarian persona asking for an animal-based '
          'dish; it can only ever fail the dietary gate, so counting it as a '
          'corpus gap would overstate the gap)')
        if killer_counts:
            for gate, count in killer_counts.most_common():
                cross = killer_cross_diet.get(gate, 0)
                w(f'  {gate:<10} {count:>4}   (of which {cross} cross-diet)')
        else:
            w('  none — every simulated query found at least one servable recipe.')

        w('\n-- biggest drop, by gate --')
        if drop_counts:
            for gate, count in drop_counts.most_common():
                w(f'  {gate:<10} {count:>4}')
        else:
            w('  none.')

        if extract_mode:
            empty_pct = (100.0 * empty_facets / extract_calls) if extract_calls else 0.0
            w(f'\nempty-facet rate: {empty_facets}/{extract_calls} ({empty_pct:.1f}%)')
            w(self.style.WARNING(
                'NOTE: this is a SOFT LOWER BOUND on the real defect rate — '
                'generated prompts insert dish names without Czech declension '
                '("Mám svíčková" rather than "svíčkovou"), which may cost the '
                'extractor accuracy a real user\'s well-formed prompt would not.'))

        w('\n-- top demand we cannot serve at all --')
        misses = coverage['misses'][:25]
        if misses:
            for term in misses:
                w(f'  {term}')
        else:
            w('  none — every scored term has at least a loose hit.')
