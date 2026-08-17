"""Load a `dump_curated_corpus` export into the local database.

Drops `created_for_user` on the way in: it points at a prod User row that
does not exist here, and the farm never needs it.
"""
from django.core import serializers
from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import CuratedRecipe


class Command(BaseCommand):
    help = 'Load curated recipes from a dump_curated_corpus JSON file.'

    def add_arguments(self, parser):
        parser.add_argument('--input', required=True, help='Path to the .json export')
        parser.add_argument(
            '--flush', action='store_true',
            help='Delete existing CuratedRecipe rows first (exact mirror)')

    def handle(self, *args, **options):
        with open(options['input'], encoding='utf-8') as fh:
            payload = fh.read()

        loaded = 0
        with transaction.atomic():
            if options['flush']:
                CuratedRecipe.objects.all().delete()
            for wrapper in serializers.deserialize('json', payload):
                wrapper.object.created_for_user = None
                wrapper.save()
                loaded += 1

        self.stdout.write(self.style.SUCCESS(f'loaded={loaded}'))
