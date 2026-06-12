"""
Re-map the ingredient -> canonical links on existing CuratedRecipe rows.

The curation pipeline maps ingredients to canonical slugs at build time. When
the canonical-ingredient dictionary or the resolver improves (e.g. after
`seed_canonical_ingredients`), already-curated recipes still carry the old,
weaker mapping. This command re-runs the deterministic resolver over each
stored recipe's ingredient names and rewrites the `canonical` links — no
network, no LLM, idempotent.

    python manage.py remap_curated_recipes
    python manage.py remap_curated_recipes --dry-run

See docs/recipe-grounding-plan.md §4 and [[recipe-grounding-b0-pilot]].
"""
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.services.recipe_curation import map_ingredients


class Command(BaseCommand):
    help = "Re-resolve ingredient->canonical links on existing CuratedRecipe rows."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Report the new mapping rate without saving.")

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        # The resolver caches a normalized index; drop it so a freshly-seeded
        # dictionary is reflected.
        clear_cache()

        recipes = CuratedRecipe.objects.all().order_by('id')
        total_ing = mapped_ing = changed = fully = 0

        for r in recipes:
            before = [(i.get('name'), i.get('canonical')) for i in (r.ingredients or [])]
            remapped = map_ingredients(r.ingredients or [])
            after = [(i.get('name'), i.get('canonical')) for i in remapped]

            n = len(remapped)
            m = sum(1 for i in remapped if i.get('canonical') or i.get('catalog_id'))
            total_ing += n
            mapped_ing += m
            non_opt_mapped = all(
                i.get('canonical') or i.get('catalog_id') or i.get('optional')
                for i in remapped
            )
            if remapped and non_opt_mapped:
                fully += 1

            if before != after:
                changed += 1
                if not dry_run:
                    r.ingredients = remapped
                    r.save(update_fields=['ingredients', 'updated_at'])

            self.stdout.write(
                f"[{r.pk}] {r.name_cs[:34]:34} {m}/{n} mapped"
                f"{'  (changed)' if before != after else ''}"
            )

        pct = round(100 * mapped_ing / total_ing) if total_ing else 0
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"{'[dry-run] ' if dry_run else ''}recipes={recipes.count()} "
            f"changed={changed} fully_mapped={fully} "
            f"ingredient_mapping={mapped_ing}/{total_ing} ({pct}%)"
        ))
