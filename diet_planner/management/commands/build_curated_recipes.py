"""
Build the curated real-recipe corpus (Direction B — recipe grounding).

Reads a source-URL index — a JSON array of
``{dish_name, source_url, source_name, source_author?}`` — and for each entry
runs the curation pipeline (fetch → extract schema.org/Recipe JSON-LD or page
text → rewrite into novice-clear Czech via Gemini → map ingredients to the
catalog → advisory clarity/coherence judge) and stores a `draft` CuratedRecipe.

Resumable and idempotent: an entry whose source_url is already in the corpus is
skipped, so re-running only fills gaps. Per-entry failures are logged and the
run continues.

    python manage.py build_curated_recipes --index docs/curated-recipe-index.json
    python manage.py build_curated_recipes --index idx.json --dry-run
    python manage.py build_curated_recipes --index idx.json --limit 30 --sleep 2
    python manage.py build_curated_recipes --index idx.json --no-judge

See docs/recipe-grounding-plan.md §4 and §8 (B0/B1).
"""
import json
import time

from django.core.management.base import BaseCommand, CommandError

from diet_planner.llm_service import GeminiService
from diet_planner.services.recipe_curation import curate_from_source


class Command(BaseCommand):
    help = "Curate real source recipes into draft CuratedRecipe records (recipe grounding)."

    def add_arguments(self, parser):
        parser.add_argument('--index', required=True,
                            help="Path to the source-URL index JSON "
                                 "(array of {dish_name, source_url, source_name}).")
        parser.add_argument('--dry-run', action='store_true',
                            help="Show what would be curated without fetching or calling any LLM.")
        parser.add_argument('--limit', type=int, default=None,
                            help="Curate at most N new entries (cost-bounded runs).")
        parser.add_argument('--sleep', type=float, default=1.0,
                            help="Seconds to sleep between entries (rate-limit guard, default 1.0).")
        parser.add_argument('--no-judge', action='store_true',
                            help="Skip the clarity/coherence judge (faster/cheaper drafts).")

    def handle(self, *args, **options):
        index_path = options['index']
        dry_run = options['dry_run']
        limit = options['limit']
        sleep_s = options['sleep']
        run_judge = not options['no_judge']

        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                index = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise CommandError(f"Could not read index file '{index_path}': {e}")

        if not isinstance(index, list):
            raise CommandError("Index must be a JSON array of recipe entries.")

        # Keep only well-formed entries with a URL.
        entries = [e for e in index if isinstance(e, dict) and (e.get('source_url') or '').strip()]
        self.stdout.write(self.style.NOTICE(
            f"Index '{index_path}': {len(index)} rows, {len(entries)} with a source_url."
        ))

        if limit is not None:
            entries = entries[:limit]
            self.stdout.write(f"Limiting to first {len(entries)} entries.")

        if dry_run:
            for e in entries:
                self.stdout.write(
                    f"[dry-run] would curate: {e.get('dish_name') or '(name from page)'} "
                    f"<- {e.get('source_url')} ({e.get('source_name') or 'source TBD'})"
                )
            self.stdout.write(self.style.SUCCESS(f"[dry-run] {len(entries)} entries."))
            return

        gemini = GeminiService()
        curated = skipped = errors = 0
        judge_flagged = 0

        for i, entry in enumerate(entries, 1):
            label = entry.get('dish_name') or entry.get('source_url')
            result = curate_from_source(entry, gemini=gemini, run_judge=run_judge, persist=True)

            if result.skipped:
                skipped += 1
                self.stdout.write(f"[{i}/{len(entries)}] skip (already in corpus): {label}")
            elif result.ok and result.recipe is not None:
                curated += 1
                r = result.recipe
                src = 'json-ld' if result.used_jsonld else 'page-text'
                mapped = sum(1 for ing in r.ingredients if ing.get('canonical') or ing.get('catalog_id'))
                judge_note = ''
                if result.judge.get('ran'):
                    verdict = result.judge.get('verdict')
                    issue_n = result.judge.get('issue_count', 0)
                    judge_note = f" judge={verdict}({issue_n})"
                    if verdict != 'coherent':
                        judge_flagged += 1
                self.stdout.write(self.style.SUCCESS(
                    f"[{i}/{len(entries)}] curated '{r.name_cs}' "
                    f"(#{r.pk}, {src}, {mapped}/{len(r.ingredients)} mapped, "
                    f"{len(r.instructions)} steps){judge_note}"
                ))
            else:
                errors += 1
                self.stdout.write(self.style.WARNING(
                    f"[{i}/{len(entries)}] FAILED: {label} — {result.error}"
                ))

            if sleep_s and i < len(entries):
                time.sleep(sleep_s)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"Done. curated={curated} skipped={skipped} errors={errors} "
            f"judge_flagged={judge_flagged}"
        ))
        if curated:
            self.stdout.write(
                "New records are status=draft. Review in admin (Curated Recipes), "
                "then promote draft → vetted → published."
            )
