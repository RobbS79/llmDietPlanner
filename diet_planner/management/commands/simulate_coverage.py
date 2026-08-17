"""The user-query farm: demand x phrasing x persona, run against the real
corpus. Read-only — no LLM calls in the default mode, no database writes ever.

This is the report the corpus's real-world coverage is judged by. Rules that
protect its honesty: (1) the default mode builds facets directly from the
query so the number costs nothing and never depends on Gemini being up, with
an opt-in `--extract-facets` mode that exercises the real extractor and
measures its known "Mám X" empty-facet defect; (2) a missing or empty demand
snapshot refuses to print a report at all, rather than a beautiful 100%
coverage over zero terms; (3) the snapshot's own "this is a proxy, not demand
truth" caveat and its age are surfaced in the header, not left buried in a
YAML file nobody reading stdout will ever open; (4) demand coverage is
reported at BOTH the headline cutoff (@20 — the dishes people most want) and
the full `--top-n` cutoff (the long tail), because a single blended number
cannot say which of the two is actually failing.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services import recipe_retrieval as rr
from diet_planner.services.prompt_facets import extract_prompt_facets
from diet_planner.services.user_simulation import (
    PERSONAS, demand_coverage, gate_funnel, generate_queries,
)

_DEFAULT_DEMAND = 'diet_planner/data/demand_index_cz.yaml'
_DEFAULT_TEMPLATES = 'diet_planner/data/prompt_templates_cz.yaml'

#: The headline demand cutoff, reported separately from --top-n (the long
#: tail). See the design doc's DWC@20 vs DWC@200 split — the whole point of
#: the farm is answering "are we failing the dishes people most want, or
#: only the tail", which a single blended number cannot do.
_HEADLINE_TOP_N = 20

#: A snapshot older than this may no longer reflect the market — the sites
#: it was built from get re-ranked over time and dish popularity drifts.
_STALE_AFTER_DAYS = 90


def _load_yaml(path: str):
    """The parsed YAML payload at `path`, or None if the file is
    missing/unreadable — callers decide whether that's fatal."""
    p = Path(path)
    if not p.is_absolute():
        p = Path(settings.BASE_DIR) / path
    try:
        with open(p, encoding='utf-8') as fh:
            return yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return None


def _load_yaml_list(path: str, key: str):
    """The `key` list from a YAML file at `path`, or [] if the file is
    missing/unreadable/lacks the key."""
    payload = _load_yaml(path)
    if not payload:
        return []
    return payload.get(key) or []


def _snapshot_age_days(generated_at) -> float:
    """Age in days of an ISO-8601 `generated_at` timestamp. Raises
    ValueError/TypeError on anything unparseable — callers must catch."""
    stamp = datetime.fromisoformat(str(generated_at))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds() / 86400


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
                            help='How much of the ranked demand to score for '
                                 'the long-tail coverage cut (headline @20 is '
                                 'always also reported).')
        parser.add_argument('--extract-facets', action='store_true',
                            help='Run the real Gemini facet extractor instead of '
                                 'building facets directly from the query. Makes '
                                 'live LLM calls.')

    def handle(self, *args, **options):
        w = self.stdout.write
        demand_payload = _load_yaml(options['demand'])
        demand = (demand_payload or {}).get('terms') or []
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

        corpus_size = len(rr.published_pool(CuratedRecipe.Status.PUBLISHED))
        w(f'user-query farm: seed={seed}  queries={n}  mode={mode}  '
          f'corpus={corpus_size} published recipes')
        if corpus_size == 0:
            w(self.style.ERROR(
                '  WARNING: the published corpus is EMPTY. Every number below is '
                'MEANINGLESS — there is nothing to measure. Populate the corpus '
                '(see load_curated_corpus) before trusting this report.'))

        # The snapshot's own caveat, read from the YAML rather than
        # hardcoded — editing the note in the snapshot updates the report.
        note = demand_payload.get('note')
        if note:
            w(f'  snapshot note: {note}')

        # Staleness: a six-month-old snapshot reads identically to one built
        # this morning unless its age is surfaced somewhere. The committed
        # snapshot predates this field, so a missing/unparseable value must
        # degrade gracefully rather than crash.
        generated_at = demand_payload.get('generated_at')
        if generated_at is None:
            w('  snapshot age unknown, rebuild with --refresh')
        else:
            try:
                age_days = _snapshot_age_days(generated_at)
            except (ValueError, TypeError):
                w('  snapshot age unknown, rebuild with --refresh')
            else:
                w(f'  snapshot age: {age_days:.0f} days (generated {generated_at})')
                if age_days > _STALE_AFTER_DAYS:
                    w(self.style.WARNING(
                        f'  WARNING: snapshot is older than {_STALE_AFTER_DAYS} '
                        f'days — demand data may no longer reflect the market.'))

        if n <= 0:
            w(self.style.WARNING(
                f'  --queries={n}: no queries requested — the flag, not the '
                f'demand data, is why nothing is simulated below; demand '
                f'coverage does not depend on generated queries and is still '
                f'reported.'))
            queries = []
        else:
            queries = generate_queries(demand, templates, PERSONAS, seed=seed, n=n)
            if not queries:
                w(self.style.WARNING(
                    'no in-scope demand terms in this snapshot — nothing to '
                    'simulate; demand coverage does not depend on generated '
                    'queries and is still reported.'))

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

        # DWC@20 (headline demand) reported separately from DWC@top-n (the
        # long tail) — a single blended number cannot say whether gaps are
        # in the dishes people most want or only in the tail.
        headline_coverage = demand_coverage(demand, top_n=_HEADLINE_TOP_N)
        full_coverage = demand_coverage(demand, top_n=top_n)

        w('\n-- demand coverage --')
        # A property of the whole snapshot, not of either cutoff below (both
        # cutoffs slice the same in-scope-ranked list, so this number would
        # otherwise print identically, and confusingly, inside each block).
        w(f'  out-of-scope in this snapshot (no meal slot, e.g. desserts/'
          f'drinks — whole snapshot, not this cutoff): {full_coverage["out_of_scope"]}')
        for label, coverage in (
            (f'@{_HEADLINE_TOP_N} (headline demand)', headline_coverage),
            (f'@{top_n} (full)', full_coverage),
        ):
            scored = coverage['scored']
            strict_pct = (100.0 * coverage['strict_hits'] / scored) if scored else 0.0
            loose_pct = (100.0 * coverage['loose_hits'] / scored) if scored else 0.0
            w(f'  {label}:')
            w(f'    scored terms (in-scope, ranked across sources): {scored}')
            w(f'    strict (we have that dish): {coverage["strict_hits"]}/{scored} '
              f'({strict_pct:.1f}%)')
            w(f'    loose (same ingredients at least): {coverage["loose_hits"]}/'
              f'{scored} ({loose_pct:.1f}%)')

        w('\n-- queries killed, by gate --')
        w('  (cross-diet = a vegan/vegetarian persona asking for an animal-based '
          'dish; it can only ever fail the dietary gate, so counting it as a '
          'corpus gap would overstate the gap)')
        if killer_counts:
            for gate, count in killer_counts.most_common():
                cross = killer_cross_diet.get(gate, 0)
                w(f'  {gate:<10} {count:>4}   (of which {cross} cross-diet)')
        elif filled > 0:
            # Derived from real fill counts, not merely the absence of a
            # named killer — an empty corpus has no killer either (nothing to
            # measure), and that must never read as this success claim.
            w('  none — every simulated query found at least one servable recipe.')
        else:
            w(self.style.WARNING(
                '  no gate recorded a kill, but nothing was filled either — this '
                'reading is not trustworthy (see the corpus-size warning above, '
                'or the --queries=0 note, if either applies).'))

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
        misses = full_coverage['misses'][:25]
        if misses:
            for term in misses:
                w(f'  {term}')
        else:
            w('  none — every scored term has at least a loose hit.')
