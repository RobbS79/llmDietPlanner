"""Bare-key collisions in the normalized lookup index (found 2026-09-15).

"rajčata" (tomatoes), "sušená rajčata" (sun-dried) and "konzervovaná rajčata"
(canned) all reduce to the normalized key "rajčata" once the modifier words are
stripped. The index used to keep whichever row happened to be inserted first,
so on prod "čerstvá rajčata", "zralá rajčata" and every "krájená rajčata v
plechovce" line resolved to sun-dried tomatoes — 18 recipes, 13 published.

Rule pinned here: a key that lost no words (the entry's own text IS the key)
beats a key produced by stripping, whatever the insertion order; and the
common canned phrasings route to the canned canonical through aliases.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CanonicalIngredient
from diet_planner.services.canonical_lookup import clear_cache, resolve_canonical


class BareKeyPriorityTests(TestCase):
    """Insertion order must not decide who owns a bare key."""

    def setUp(self):
        clear_cache()
        # Deliberately insert the stripped-key entry FIRST.
        CanonicalIngredient.objects.create(name='sun-dried tomatoes', name_cs='sušená rajčata', slug='sun-dried-tomatoes', category='canned')
        CanonicalIngredient.objects.create(name='tomatoes', name_cs='rajčata', slug='tomatoes', category='vegetables')
        clear_cache()

    def tearDown(self):
        clear_cache()

    def test_fresh_lines_resolve_to_the_bare_entry(self):
        for line in ('čerstvá rajčata', 'zralá rajčata', 'rajčata (malá), nakrájená na klínky', 'čerstvá rajčata, nasekaná'):
            ci = resolve_canonical(line)
            self.assertIsNotNone(ci, line)
            self.assertEqual(ci.slug, 'tomatoes', line)

    def test_sun_dried_still_resolves(self):
        self.assertEqual(resolve_canonical('sušená rajčata').slug, 'sun-dried-tomatoes')

    def test_canned_marker_falls_back_to_the_base_product(self):
        # No canned tomato variant in this minimal dictionary -> the canned
        # line must still resolve to plain tomatoes rather than to nothing.
        self.assertEqual(resolve_canonical('rajčata z konzervy').slug, 'tomatoes')
        self.assertEqual(resolve_canonical('krájená rajčata v plechovce, s vlastní šťávou').slug, 'tomatoes')


class CannedTomatoRoutingTests(TestCase):
    """Every canned phrasing seen on prod must reach the canned canonical."""

    @classmethod
    def setUpTestData(cls):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        clear_cache()

    LINES = [
        ('drcená rajčata v plechovce', 'chopped-tomatoes-canned'),
        ('drcená rajčata z konzervy', 'chopped-tomatoes-canned'),
        ('drcená rajčata v konzervě', 'chopped-tomatoes-canned'),
        ('krájená rajčata v konzervě, s vlastní šťávou', 'chopped-tomatoes-canned'),
        ('krájená rajčata z konzervy', 'chopped-tomatoes-canned'),
        ('krájená rajčata v plechovce', 'chopped-tomatoes-canned'),
        ('rajčata krájená v plechovce', 'chopped-tomatoes-canned'),
        ('rajčata krájená z konzervy', 'chopped-tomatoes-canned'),
        ('rajčata, krájená, konzervovaná', 'chopped-tomatoes-canned'),
        ('rajčata krájená, z plechovky (fire roasted)', 'chopped-tomatoes-canned'),
        ('krájená rajčata pečená na ohni (z plechovky)', 'chopped-tomatoes-canned'),
        ('pečená rajčata v plechovce, dobře scezená', 'chopped-tomatoes-canned'),
        ('rajčata drcená nebo krájená', 'tomatoes'),
        ('čerstvá rajčata', 'tomatoes'),
        ('zralá rajčata', 'tomatoes'),
        ('rajčata (malá), nakrájená na klínky', 'tomatoes'),
        ('sušená rajčata v oleji', 'sun-dried-tomatoes'),
        ('sušená rajčata', 'sun-dried-tomatoes'),
        # canned marker routes to the canned variant when the dictionary has one
        ('cizrna z konzervy', 'chickpeas-canned'),
        ('kukuřice z konzervy', 'corn'),
        ('tuňák v konzervě', 'tuna-canned'),
        # peeled / crushed tomatoes are a can, not produce (remap audit 2026-09-15)
        ('loupaná rajčata z konzervy', 'chopped-tomatoes-canned'),
        ('rajčata loupaná celá v plechovce', 'chopped-tomatoes-canned'),
        ('loupaná rajčata', 'chopped-tomatoes-canned'),
        ('drcená rajčata', 'chopped-tomatoes-canned'),
        # two published recipes lost these lines in the 2026-09-15 remap
        ('hřebíčky', 'cloves'),
        ('nálev z oliv', 'olives'),
    ]

    def test_every_line_routes_as_expected(self):
        misses = []
        for line, slug in self.LINES:
            ci = resolve_canonical(line)
            if ci is None or ci.slug != slug:
                misses.append((line, slug, ci.slug if ci else None))
        self.assertEqual(misses, [], f'misrouted: {misses}')
