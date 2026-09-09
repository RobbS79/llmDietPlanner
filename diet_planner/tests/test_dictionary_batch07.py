"""Dictionary coverage for the demand-driven corpus batch 07 (2026-09-09).

The first run of docs/curated-recipe-index-batch07.json on prod rejected 31 of
48 recipes at the availability gate because these ingredient lines did not
resolve to any canonical ingredient (an unresolved line is UNRATED, and UNRATED
blocks intake). Every one of them is an ordinary Czech supermarket item. This
test pins the dictionary additions that let the batch through: each line must
resolve, and the canonical it resolves to must carry a tier the intake gate
accepts (common or findable), so the fix cannot regress silently.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CanonicalIngredient
from diet_planner.services.canonical_lookup import clear_cache, resolve_canonical
from diet_planner.services.ingredient_availability import BLOCKING

# (ingredient line as it appeared in the batch-07 gate error, expected canonical slug)
BATCH07_BLOCKED = [
    ('pancetta', 'pancetta'),
    ('sýr pecorino', 'pecorino'),
    ('kapří filet', 'carp'),
    ('toastový chléb', 'bread-loaf'),
    ('čínské nudle', 'chinese-noodles'),
    ('pláty na lasagne', 'lasagne-sheets'),
    ('badyán', 'star-anise'),
    ('hovězí morkové kosti', 'beef-marrow-bones'),
    ('široké rýžové nudle', 'rice-noodles'),
    ('pikantní klobása', 'sausage'),
    ('uzené maso', 'smoked-meat'),
    ('moravské uzené maso', 'smoked-meat'),
    ('uzené maso (např. uzené ramínko nebo krkovice)', 'smoked-meat'),
    ('burgerové bulky', 'burger-buns'),
    ('listový salát', 'lettuce'),
    ('koření na americké brambory', 'potato-seasoning'),
    ('polotvrdý sýr v celku', 'cheese'),
    ('brambory vařené ve slupce', 'potatoes'),
    ('bryndza', 'bryndza'),
    ('celozrnný kuskus', 'couscous'),
    ('kuskus', 'couscous'),
    ('konzervovaná kukuřice', 'corn'),
    ('konzervované červené fazole', 'beans'),
    ('koření na gyros', 'gyros-seasoning'),
    ('sýr typu parmezán', 'parmesan'),
    ('parmazán v bloku', 'parmesan'),
    ('bulgur', 'bulgur'),
    ('barevné těstoviny', 'pasta'),
    ('dušená šunka v celku', 'ham'),
    ('polotmavé pivo', 'beer'),
    ('tuňák ve vlastní šťávě', 'tuna-canned'),
    ('sójové klíčky', 'sprouts'),
    ('sušený hrách', 'dried-peas'),
    ('žlutý loupaný hrách', 'dried-peas'),
    ('hrách', 'dried-peas'),
    ('vepřové koleno přední', 'pork-knuckle'),
    ('vepřové koleno', 'pork-knuckle'),
    ('hovězí maso s kostí', 'beef'),
    ('syrové hovězí dršťky', 'tripe'),
    ('kořen petržele', 'parsley-root'),
    ('vepřová játra', 'pork-liver'),
    ('drůbeží játra', 'chicken-liver'),
    ('kuřecí játra', 'chicken-liver'),
    ('bílá bageta', 'bread-loaf'),
    ('sardelové filety', 'anchovies'),
    ('pomazánkové máslo', 'spread-butter'),
    ('vepřová krkovice s kostí vcelku', 'pork'),
    ('kapr', 'carp'),
]


class Batch07DictionaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        clear_cache()

    def test_every_blocked_line_resolves_to_the_expected_canonical(self):
        misses = []
        for line, slug in BATCH07_BLOCKED:
            ci = resolve_canonical(line)
            if ci is None or ci.slug != slug:
                misses.append((line, slug, ci.slug if ci else None))
        self.assertEqual(misses, [], f'unresolved or misrouted lines: {misses}')

    def test_every_target_canonical_passes_the_intake_gate(self):
        slugs = sorted({slug for _, slug in BATCH07_BLOCKED})
        tiers = dict(CanonicalIngredient.objects.filter(slug__in=slugs).values_list('slug', 'availability'))
        blocked = {s: tiers.get(s, 'MISSING') for s in slugs if tiers.get(s) in BLOCKING or s not in tiers}
        self.assertEqual(blocked, {}, f'canonicals the gate would still block: {blocked}')
