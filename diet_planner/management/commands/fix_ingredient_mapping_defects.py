"""Repair three canonical-ingredient mapping defects found while rating
ingredient availability (spec 2026-08-11-ingredient-obtainability-design).

1. `vanilla-extract` conflated two different products: 37 corpus rows really
   say "vanilkový extrakt", but 10 say "vanilkový cukr" — a distinct, ordinary
   supermarket item — and the alias "vanilkový cukr" pointed at the extract.
   Also un-inverts the alias "vanilkový extrakt", which pointed at `vanilla`
   (dormant, because resolve_canonical matches canonical names before aliases,
   but a landmine the moment name_cs changes).

2. `kale.name_cs` was "kapusta" — savoy cabbage, a different and completely
   ordinary vegetable. The raw ingredient names confirm the recipes mean
   kadeřávek. Anything resolving the bare word "kapusta" landed on kale.

3. `green-curry-paste.name_cs` was the generic "kari pasta", and it owned the
   aliases for *červená* paste too — green and red are not interchangeable.

Default is a dry run; pass --apply to write.

Idempotent: re-running after --apply reports zero changes.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models.catalog import CanonicalIngredient, IngredientAlias
from diet_planner.models.curated import CuratedRecipe
from diet_planner.services.canonical_lookup import clear_cache, fold_diacritics


def _folded(text: str) -> str:
    return fold_diacritics((text or "").strip().lower())


class Command(BaseCommand):
    help = "Repair the vanilla / kale / curry-paste canonical mapping defects."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write the repairs (default: dry-run).')

    def handle(self, *args, **options):
        apply = options['apply']
        self.changes: list[str] = []

        with transaction.atomic():
            self._fix_vanilla()
            self._fix_kale()
            self._fix_curry_paste()

            if not self.changes:
                self.stdout.write(self.style.SUCCESS(
                    "Nothing to do — all three defects already repaired."))
                return

            for line in self.changes:
                self.stdout.write("  " + line)
            self.stdout.write("")

            if not apply:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(
                    f"DRY RUN — {len(self.changes)} change(s) rolled back. "
                    "Re-run with --apply to write."))
                return

        clear_cache()
        self.stdout.write(self.style.SUCCESS(
            f"Applied {len(self.changes)} change(s)."))
        self.stdout.write(self.style.WARNING(
            "NOTE: resolve_canonical caches its name index per process "
            "(@lru_cache). Running web/worker processes keep the OLD index "
            "until they restart."))

    # --- helpers ----------------------------------------------------------

    def _canonical(self, slug: str, **defaults) -> CanonicalIngredient:
        ci = CanonicalIngredient.objects.filter(slug=slug).first()
        if ci:
            return ci
        ci = CanonicalIngredient(slug=slug, **defaults)
        ci.save()
        self.changes.append(f"CREATE canonical {slug} (name_cs={ci.name_cs!r})")
        return ci

    def _rename(self, ci: CanonicalIngredient, name_cs: str) -> None:
        if ci.name_cs == name_cs:
            return
        self.changes.append(
            f"RENAME {ci.slug}.name_cs {ci.name_cs!r} -> {name_cs!r}")
        ci.name_cs = name_cs
        ci.save(update_fields=['name_cs', 'updated_at'])

    def _repoint(self, alias_text: str, target: CanonicalIngredient) -> None:
        """Move an alias to `target`, creating it if absent."""
        al = IngredientAlias.objects.filter(alias__iexact=alias_text).first()
        if al is None:
            IngredientAlias.objects.create(
                canonical_ingredient=target, alias=alias_text, language_code='cs')
            self.changes.append(f"ADD alias {alias_text!r} -> {target.slug}")
            return
        if al.canonical_ingredient_id == target.id:
            return
        self.changes.append(
            f"REPOINT alias {alias_text!r}: "
            f"{al.canonical_ingredient.slug} -> {target.slug}")
        al.canonical_ingredient = target
        al.save(update_fields=['canonical_ingredient'])

    def _remap_corpus(self, from_slug: str, to_slug: str, match) -> None:
        """Move recipe ingredient rows from one canonical to another.

        `match(folded_name) -> bool` decides which rows move. Walks every
        status, not just published, so drafts are correct when promoted.
        """
        moved = 0
        for r in CuratedRecipe.objects.all().only('id', 'slug', 'ingredients'):
            dirty = False
            for ing in r.ingredients or []:
                if not isinstance(ing, dict) or ing.get('canonical') != from_slug:
                    continue
                if not match(_folded(ing.get('name'))):
                    continue
                ing['canonical'] = to_slug
                # catalog_id pointed at a StoreProduct for the OLD ingredient.
                ing.pop('catalog_id', None)
                dirty = True
            if dirty:
                r.save(update_fields=['ingredients', 'updated_at'])
                moved += 1
        if moved:
            self.changes.append(
                f"REMAP {moved} recipe(s): ingredient {from_slug} -> {to_slug}")

    # --- the three defects ------------------------------------------------

    def _fix_vanilla(self) -> None:
        sugar = self._canonical(
            'vanilla-sugar',
            name='vanilla sugar', name_cs='vanilkový cukr',
            category=CanonicalIngredient.Category.BAKING,
            default_unit='g', typical_unit='ks',
            avg_piece_weight_g=8,          # the standard CZ 8 g sáček
            typical_package_sizes=[8],
        )
        extract = CanonicalIngredient.objects.get(slug='vanilla-extract')

        self._repoint('vanilkový cukr', sugar)
        self._repoint('cukr vanilkový', sugar)
        # Was pointing at `vanilla`; shadowed today, wrong regardless.
        self._repoint('vanilkový extrakt', extract)

        self._remap_corpus(
            'vanilla-extract', 'vanilla-sugar',
            lambda n: 'vanilk' in n and 'cukr' in n,
        )

    def _fix_kale(self) -> None:
        kale = CanonicalIngredient.objects.get(slug='kale')
        self._rename(kale, 'kadeřávek')
        # Four corpus rows use this word order; only the reverse was aliased.
        self._repoint('kadeřavá kapusta', kale)

    def _fix_curry_paste(self) -> None:
        green = CanonicalIngredient.objects.get(slug='green-curry-paste')
        self._rename(green, 'zelená kari pasta')

        red = self._canonical(
            'red-curry-paste',
            name='red curry paste', name_cs='červená kari pasta',
            category=CanonicalIngredient.Category.CONDIMENTS,
            default_unit='g',
        )
        self._repoint('červená kari pasta', red)
        self._repoint('thajská červená kari pasta', red)

        self._remap_corpus(
            'green-curry-paste', 'red-curry-paste',
            lambda n: 'cerven' in n,
        )
