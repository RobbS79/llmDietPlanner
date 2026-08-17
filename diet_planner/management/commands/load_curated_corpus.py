"""Load a `dump_curated_corpus` export into the local database.

Drops `created_for_user` on the way in: it points at a prod User row that
does not exist here, and the farm never needs it.
"""
from django.core import serializers
from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection, transaction

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

            # Every row above was inserted with its EXPLICIT prod pk. On
            # Postgres, an explicit-id insert never advances the table's id
            # sequence (only nextval() does) -- so the sequence is left
            # wherever local activity last put it, which can be far behind
            # the pks we just loaded. The next plain `.create()` then asks
            # the sequence for an id that may already be occupied by a row
            # we just loaded, raising IntegrityError. Django's own
            # `loaddata` calls sequence_reset_sql for exactly this reason;
            # do the same here. This is a no-op on sqlite (whose rowid
            # autoincrement self-heals via max(rowid)+1, so
            # sequence_reset_sql returns []), but it IS exercised by this
            # project's unit suite: docker-compose runs tests against a
            # real Postgres, see
            # test_load_resets_the_postgres_sequence in
            # diet_planner/tests/test_corpus_mirror.py, which reproduces the
            # collision and fails without this block. Do not delete this as
            # dead code.
            with connection.cursor() as cursor:
                for sql in connection.ops.sequence_reset_sql(no_style(), [CuratedRecipe]):
                    cursor.execute(sql)

        self.stdout.write(self.style.SUCCESS(f'loaded={loaded}'))
