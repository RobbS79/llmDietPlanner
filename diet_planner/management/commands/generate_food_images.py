import os
import google.generativeai as genai
from django.conf import settings
from django.core.management.base import BaseCommand

from diet_planner.food_categories import FOOD_CATEGORIES
from diet_planner.food_images import encode_webp


class Command(BaseCommand):
    help = 'Generate stock food images using Gemini and save to frontend/public/food-images/'

    def add_arguments(self, parser):
        parser.add_argument('--category', type=str, help='Generate only this category slug')
        parser.add_argument('--dry-run', action='store_true', help='Print prompts without generating')
        parser.add_argument('--overwrite', action='store_true', help='Overwrite existing images')

    def handle(self, *args, **options):
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            self.stderr.write(self.style.ERROR('GEMINI_API_KEY not set'))
            return

        output_dir = os.path.join(settings.BASE_DIR, 'frontend', 'public', 'food-images')
        os.makedirs(output_dir, exist_ok=True)

        genai.configure(api_key=api_key)
        model_name = getattr(settings, 'GEMINI_IMAGE_MODEL', 'gemini-2.0-flash-preview-image-generation')
        model = genai.GenerativeModel(model_name)

        categories = FOOD_CATEGORIES
        if options['category']:
            slug = options['category']
            if slug not in categories:
                self.stderr.write(self.style.ERROR(f'Unknown category: {slug}'))
                return
            categories = {slug: categories[slug]}

        self.stdout.write(f'Generating {len(categories)} food images with {model_name}...')
        self.stdout.write(f'Output: {output_dir}\n')

        generated = 0
        skipped = 0

        for slug, cat in categories.items():
            filepath = os.path.join(output_dir, f'{slug}.webp')

            if os.path.exists(filepath) and not options['overwrite']:
                self.stdout.write(f'  [{slug}] exists, skipping (use --overwrite)')
                skipped += 1
                continue

            self.stdout.write(f'  [{slug}] {cat["name"]}... ', ending='')

            if options['dry_run']:
                self.stdout.write(self.style.WARNING(f'dry run — prompt: "{cat["prompt"][:80]}..."'))
                continue

            prompt = (
                f'Generate a professional food photograph: {cat["prompt"]}. '
                f'Top-down 45-degree angle, dark moody background, soft directional lighting, '
                f'shallow depth of field, on a dark ceramic plate. '
                f'Photorealistic, appetizing, editorial food photography style. '
                f'No text, no watermarks, no people.'
            )

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
                    continue

                size_kb = encode_webp(image_data, filepath) / 1024
                self.stdout.write(self.style.SUCCESS(f'saved ({size_kb:.0f} KB)'))
                generated += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'error: {e}'))

        self.stdout.write(f'\nDone. Generated: {generated}, Skipped: {skipped}')
