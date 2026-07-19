"""Generate per-dish images for the public recipe showcase.

Wave 1 of replacing category stock images: one image per distinct public
Recipe slug, prompted from the actual dish (name + main ingredients), so
"bramborové halušky" stops being illustrated by roasted potatoes. Output goes
to frontend/public/food-images/dishes/<slug>.webp — commit the results; they
ship with the frontend build exactly like the category images.

    python manage.py generate_recipe_images --dry-run
    python manage.py generate_recipe_images
    python manage.py generate_recipe_images --slug kureci-parmigiana --overwrite
"""
import os

import google.generativeai as genai
from django.conf import settings
from django.core.management.base import BaseCommand

from diet_planner.food_images import encode_webp
from diet_planner.models import Recipe

# Same style block as generate_food_images so dish and category images read
# as one photo set.
STYLE = (
    'Top-down 45-degree angle, dark moody background, soft directional lighting, '
    'shallow depth of field, on a dark ceramic plate. '
    'Photorealistic, appetizing, editorial food photography style. '
    'No text, no watermarks, no people.'
)

MAX_PROMPT_INGREDIENTS = 6


def build_prompt(recipe) -> str:
    ingredients = [
        ing.get('name') for ing in (recipe.ingredients or [])
        if isinstance(ing, dict) and ing.get('name') and not ing.get('optional')
    ][:MAX_PROMPT_INGREDIENTS]
    parts = [f'Generate a professional food photograph of the finished Czech dish "{recipe.name}"']
    if ingredients:
        parts.append(f'made with {", ".join(ingredients)}')
    if recipe.description:
        parts.append(f'({recipe.description[:160]})')
    return f'{" ".join(parts)}. The photo must show this exact prepared dish. {STYLE}'


class Command(BaseCommand):
    help = 'Generate per-dish images for public recipes into frontend/public/food-images/dishes/'

    def add_arguments(self, parser):
        parser.add_argument('--slug', type=str, help='Generate only this recipe slug')
        parser.add_argument('--limit', type=int, help='Stop after N generated images')
        parser.add_argument('--dry-run', action='store_true', help='Print prompts without generating')
        parser.add_argument('--overwrite', action='store_true', help='Overwrite existing images')

    def handle(self, *args, **options):
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            self.stderr.write(self.style.ERROR('GEMINI_API_KEY not set'))
            return

        output_dir = os.path.join(settings.BASE_DIR, 'frontend', 'public', 'food-images', 'dishes')
        os.makedirs(output_dir, exist_ok=True)

        # Newest row per slug — duplicate public rows share a slug and thus a file.
        recipes_by_slug = {}
        qs = Recipe.objects.filter(is_public=True).exclude(slug='').order_by('created_at')
        if options['slug']:
            qs = qs.filter(slug=options['slug'])
        for recipe in qs:
            recipes_by_slug[recipe.slug] = recipe
        if not recipes_by_slug:
            self.stderr.write(self.style.ERROR('No matching public recipes'))
            return

        genai.configure(api_key=api_key)
        model_name = getattr(settings, 'GEMINI_IMAGE_MODEL', 'gemini-2.0-flash-preview-image-generation')
        model = genai.GenerativeModel(model_name)

        self.stdout.write(f'Generating up to {len(recipes_by_slug)} dish images with {model_name}...')
        self.stdout.write(f'Output: {output_dir}\n')

        generated = 0
        skipped = 0
        failed = 0

        for slug, recipe in sorted(recipes_by_slug.items()):
            filepath = os.path.join(output_dir, f'{slug}.webp')

            if os.path.exists(filepath) and not options['overwrite']:
                self.stdout.write(f'  [{slug}] exists, skipping (use --overwrite)')
                skipped += 1
                continue
            if options['limit'] and generated >= options['limit']:
                self.stdout.write('  --limit reached, stopping')
                break

            prompt = build_prompt(recipe)
            self.stdout.write(f'  [{slug}] {recipe.name}... ', ending='')

            if options['dry_run']:
                self.stdout.write(self.style.WARNING(f'dry run — prompt: "{prompt[:100]}..."'))
                continue

            try:
                response = model.generate_content(
                    prompt,
                    generation_config={
                        'response_modalities': ['IMAGE', 'TEXT'],
                        'temperature': 0.8,
                    },
                    request_options={'timeout': 120},
                )

                image_data = None
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data.mime_type.startswith('image/'):
                        image_data = part.inline_data.data
                        break

                if not image_data:
                    self.stdout.write(self.style.WARNING('no image in response'))
                    failed += 1
                    continue

                size_kb = encode_webp(image_data, filepath) / 1024
                self.stdout.write(self.style.SUCCESS(f'saved ({size_kb:.0f} KB)'))
                generated += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'error: {e}'))
                failed += 1

        self.stdout.write(f'\nDone. Generated: {generated}, Skipped: {skipped}, Failed: {failed}')
        if generated:
            self.stdout.write('Commit the new files under frontend/public/food-images/dishes/.')
