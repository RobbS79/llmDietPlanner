"""Dictionary coverage for the demand-driven corpus batches 07+08 (2026-09-15).

The 2026-09-15 prod runs (batch 07 re-run after the batch-07 dictionary, and
the first run of docs/curated-recipe-index-batch08.json) rejected 30 recipes at
the availability gate. Every reject was an ingredient line that resolved to no
canonical (UNRATED blocks intake) and every one of them is ordinary Czech
supermarket stock: kachna, kapusta, tavený sýr, škvarky, tvaroh, sardinky,
salám, tvarůžky, krupice... Several sit behind the highest-demand dishes in
the corpus plan (svíčková, pečená kachna, španělský ptáček, znojemská).

This test pins the batch-09 dictionary additions: each rejected line must
resolve to the expected canonical, and that canonical must carry a tier the
intake gate accepts (common or findable), so the fix cannot regress silently.

Deliberately NOT covered (left rejected on purpose):
  - english-muffins is a rated canonical (specialty, owner review) — Vejce
    Benedikt stays out until the owner re-rates it.
  - Maminčina vánoční rybí polévka needs a carp carcass, fish heads, roe and
    mace — a Christmas-eve fishmonger trip, not a supermarket recipe.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CanonicalIngredient
from diet_planner.services.canonical_lookup import clear_cache, resolve_canonical
from diet_planner.services.ingredient_availability import BLOCKING

# (ingredient line as it appeared in the gate error, expected canonical slug)
BATCH09_BLOCKED = [
    # batch 07 re-run leftovers
    ('kuřecí maso s kostí (na vývar)', 'whole-chicken'),
    ('kuřecí maso s kostí', 'whole-chicken'),
    ('listy salátu', 'lettuce'),
    ('tvrdý sýr vcelku', 'cheese'),
    ('šunka vcelku', 'ham'),
    ('vepřová krkovice s kostí v celku', 'pork'),
    # batch 08
    ('červená lahůdková cibulka', 'onion'),
    ('pražský salám', 'salami'),
    ('měkký salám (např. pařížský nebo gothaj)', 'salami'),
    ('měkký salám', 'salami'),
    ('suchý salám', 'salami'),
    ('trvanlivý salám', 'salami'),
    ('gothaj', 'salami'),
    ('hlávkové bílé zelí', 'cabbage'),
    ('bílé hlávkové zelí', 'cabbage'),
    ('kachna', 'duck'),
    ('celá kachna', 'duck'),
    ('masový vývar', 'beef-stock'),
    ('škvarky', 'pork-cracklings'),
    ('vepřové škvarky', 'pork-cracklings'),
    ('netučný tvaroh', 'cottage-cheese'),
    ('nízkotučný tvaroh', 'cottage-cheese'),
    ('tučný tvaroh', 'cottage-cheese'),
    ('uzená krkovice vcelku', 'smoked-meat'),
    ('tuňák v rostlinném oleji (konzerva)', 'tuna-canned'),
    ('tuňák v rostlinném oleji', 'tuna-canned'),
    ('menší květák', 'cauliflower'),
    ('mladá cuketa', 'zucchini'),
    ('změklé máslo', 'butter'),
    ('hrubá krupice', 'semolina'),
    ('dětská krupička', 'semolina'),
    ('krupička', 'semolina'),
    ('tavený sýr', 'processed-cheese'),
    ('hovězí líčka', 'beef-cheeks'),
    ('sýr gervais', 'cream-cheese'),
    ('gervais', 'cream-cheese'),
    ('kapusta', 'savoy-cabbage'),
    ('hlávková kapusta', 'savoy-cabbage'),
    ('hovězí falešná svíčková', 'beef'),
    ('falešná svíčková', 'beef'),
    ('nakládaná kapie', 'pickled-peppers'),
    ('sterilovaná kapie', 'pickled-peppers'),
    ('sardinky v konzervě', 'sardines-canned'),
    ('sardinky v oleji (plechovka)', 'sardines-canned'),
    ('sardinky', 'sardines-canned'),
    ('bambusové výhonky', 'bamboo-shoots'),
    ('sójové výhonky', 'sprouts'),
    ('olomoucké tvarůžky', 'olomouc-cheese'),
    ('tvarůžky', 'olomouc-cheese'),
]

# Existing routes that the new modifier words / aliases must not disturb.
UNCHANGED_ROUTES = [
    ('kapusta kadeřavá', 'kale'),
    ('růžičková kapusta', 'brussels-sprouts'),
    ('bílé víno', 'white-wine'),
    ('jarní cibulka', 'spring-onion'),
    ('mladá cibulka', 'spring-onion'),
    ('paprika kapie', 'bell-pepper'),
    ('sójové klíčky', 'sprouts'),
    ('hovězí zadní', 'beef'),
    ('lučina', 'cream-cheese'),
]


class Batch09DictionaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        clear_cache()

    def test_every_blocked_line_resolves_to_the_expected_canonical(self):
        misses = []
        for line, slug in BATCH09_BLOCKED:
            ci = resolve_canonical(line)
            if ci is None or ci.slug != slug:
                misses.append((line, slug, ci.slug if ci else None))
        self.assertEqual(misses, [], f'unresolved or misrouted lines: {misses}')

    def test_every_target_canonical_passes_the_intake_gate(self):
        slugs = sorted({slug for _, slug in BATCH09_BLOCKED})
        tiers = dict(CanonicalIngredient.objects.filter(slug__in=slugs).values_list('slug', 'availability'))
        blocked = {s: tiers.get(s, 'MISSING') for s in slugs if tiers.get(s) in BLOCKING or s not in tiers}
        self.assertEqual(blocked, {}, f'canonicals the gate would still block: {blocked}')

    def test_existing_routes_are_undisturbed(self):
        misses = []
        for line, slug in UNCHANGED_ROUTES:
            ci = resolve_canonical(line)
            if ci is None or ci.slug != slug:
                misses.append((line, slug, ci.slug if ci else None))
        self.assertEqual(misses, [], f'regressed routes: {misses}')
