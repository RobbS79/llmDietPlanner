"""Export published curated recipes so the farm can run against a local mirror.

Read-only: this command never writes to the database it reads. Run it against
prod, load the file locally with `load_curated_corpus`. The output is NOT
committed — it is a few MB of third-party-derived recipe text and it is
regenerable at any time.
"""
from django.core import serializers
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe


class Command(BaseCommand):
    help = 'Dump published CuratedRecipe rows to JSON (read-only).'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True, help='Destination .json path')
        parser.add_argument('--status', default=CuratedRecipe.Status.PUBLISHED)

    def handle(self, *args, **options):
        qs = CuratedRecipe.objects.filter(status=options['status']).order_by('id')
        count = qs.count()
        with open(options['output'], 'w', encoding='utf-8') as fh:
            fh.write(serializers.serialize('json', qs.iterator()))
        self.stdout.write(self.style.SUCCESS(
            f'dumped={count} -> {options["output"]}'))
