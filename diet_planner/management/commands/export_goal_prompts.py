"""Export real goal prompts as scrubbed phrasing templates.

Writes shapes and counts only — see services/prompt_templates for why.
"""
from collections import Counter
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from diet_planner.models import DietaryGoal
from diet_planner.services.prompt_templates import reduce_prompt

DEFAULT_PATH = (Path(settings.BASE_DIR) / 'diet_planner' / 'data'
                / 'prompt_templates_cz.yaml')


class Command(BaseCommand):
    help = 'Reduce real DietaryGoal prompts to committed phrasing templates.'

    def add_arguments(self, parser):
        parser.add_argument('--output', default=str(DEFAULT_PATH))

    def handle(self, *args, **options):
        counts = Counter()
        seen = dropped = 0
        for goal in DietaryGoal.objects.all().iterator():
            seen += 1
            template = reduce_prompt(goal.prompt or '')
            if template is None:
                dropped += 1
                continue
            counts[template] += 1

        payload = {
            'note': ('Shapes only. Prompts that do not reduce to a known '
                     'template are dropped, never exported.'),
            'templates': [
                {'template': template, 'observed': n}
                for template, n in counts.most_common()
            ],
        }
        Path(options['output']).write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
            encoding='utf-8')

        self.stdout.write(self.style.SUCCESS(
            f'goals={seen} templates={len(counts)} dropped={dropped}'))
