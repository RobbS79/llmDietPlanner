"""
Walk all public recipes and re-generate the instructions when they're
below the substantive-content threshold ("eat a piece of chocolate" -> a
proper 4-8 step guide with nutritional context).

Resumable and idempotent: re-running after success only touches recipes
that are still below the threshold.

    python manage.py enrich_thin_recipes
    python manage.py enrich_thin_recipes --dry-run
    python manage.py enrich_thin_recipes --limit 20 --sleep 2
    python manage.py enrich_thin_recipes --threshold 40
"""
import logging
import time

from django.core.management.base import BaseCommand

from diet_planner.models import Recipe
from diet_planner.llm_service import GeminiService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Re-generate instructions on recipes whose current text is too thin to publish."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Report what would change without calling the LLM.")
        parser.add_argument('--limit', type=int, default=None,
                            help="Process at most N recipes (useful for cost-bounded runs).")
        parser.add_argument('--threshold', type=int, default=Recipe.PUBLISH_MIN_WORDS,
                            help=f"Min word count to consider a recipe substantive "
                                 f"(default {Recipe.PUBLISH_MIN_WORDS}).")
        parser.add_argument('--sleep', type=float, default=0.0,
                            help="Seconds to sleep between LLM calls (rate-limit guard).")

    def handle(self, *args, **options):
        threshold = options['threshold']
        dry_run = options['dry_run']
        limit = options['limit']
        sleep_s = options['sleep']

        qs = Recipe.objects.all().order_by('id')
        thin = [r for r in qs if Recipe.count_instruction_words(r.instructions) < threshold]
        self.stdout.write(self.style.NOTICE(
            f"Scanned {qs.count()} recipes — {len(thin)} below threshold of {threshold} words."
        ))

        if limit is not None:
            thin = thin[:limit]
            self.stdout.write(f"Processing first {len(thin)} (limit={limit}).")

        if dry_run:
            for r in thin:
                wc = Recipe.count_instruction_words(r.instructions)
                self.stdout.write(f"[dry-run] would enrich #{r.id} '{r.name}' "
                                  f"(currently {wc} words, is_public={r.is_public})")
            return

        if not thin:
            self.stdout.write(self.style.SUCCESS("Nothing to do — every recipe is substantive."))
            return

        llm = GeminiService()
        enriched = 0
        still_thin = 0
        errors = 0

        for r in thin:
            before_wc = Recipe.count_instruction_words(r.instructions)
            ingredient_names = [
                ing.get('name', str(ing)) if isinstance(ing, dict) else str(ing)
                for ing in (r.ingredients or [])
            ]
            try:
                new_instructions = llm.expand_thin_recipe_instructions(
                    meal_name=r.name,
                    ingredients=ingredient_names,
                    thin_instructions=r.instructions or [],
                    description=r.description or '',
                    language_code=r.dietary_goal.language_code,
                )
            except Exception as e:
                logger.exception(f"LLM expansion failed for recipe #{r.id}: {e}")
                errors += 1
                if sleep_s:
                    time.sleep(sleep_s)
                continue

            after_wc = Recipe.count_instruction_words(new_instructions)
            if after_wc > before_wc:
                r.instructions = new_instructions
                r.save()  # auto-promotes to is_public=True if substantive
                status = 'PUBLIC' if r.is_public else 'still private'
                self.stdout.write(self.style.SUCCESS(
                    f"#{r.id} '{r.name}': {before_wc} → {after_wc} words ({status})"
                ))
                enriched += 1
                if not r.is_public:
                    still_thin += 1
            else:
                # Expansion failed — explicitly demote so this thin recipe
                # stops appearing in /recepty/. save() never auto-demotes,
                # so we have to flip it here.
                if r.is_public:
                    r.is_public = False
                    r.save(update_fields=['is_public', 'updated_at'])
                self.stdout.write(self.style.WARNING(
                    f"#{r.id} '{r.name}': expansion did not improve "
                    f"({before_wc} → {after_wc}), demoted to private"
                ))
                still_thin += 1

            if sleep_s:
                time.sleep(sleep_s)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"Done. enriched={enriched} still_thin={still_thin} errors={errors}"
        ))
