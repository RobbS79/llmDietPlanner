"""Export published curated recipes so the farm can run against a local mirror.

Read-only: this command never writes to the database it reads. Run it against
prod, load the file locally with `load_curated_corpus`. The output is NOT
committed — it is a few MB of third-party-derived recipe text and it is
regenerable at any time.
"""
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import CuratedRecipe


class Command(BaseCommand):
    help = 'Dump published CuratedRecipe rows to JSON (read-only).'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True, help='Destination .json path')
        parser.add_argument(
            '--status', default=CuratedRecipe.Status.PUBLISHED,
            choices=CuratedRecipe.Status.values)

    def handle(self, *args, **options):
        qs = CuratedRecipe.objects.filter(status=options['status']).order_by('id')
        # Single read: qs.count() followed by qs.iterator() is two separate
        # queries, so a write landing between them could make the printed
        # count disagree with what actually hit the file. serialize() builds
        # the whole JSON string in memory anyway, so materializing the rows
        # here buys no memory cost and closes that window.
        rows = list(qs)
        if not rows:
            # This command exists to move a ~458-row corpus; zero is never a
            # legitimate outcome, only a typo'd --status or the wrong
            # DATABASE_URL. It must fail loudly rather than print SUCCESS,
            # because this file is piped into `load_curated_corpus --flush`,
            # which deletes the local mirror before loading — a silent
            # zero-row dump would wipe the farm's corpus and look like good
            # news.
            raise CommandError(
                f'0 rows for status={options["status"]!r} -- refusing to '
                f'write {options["output"]!r}. Check DATABASE_URL and '
                '--status before retrying.')
        with open(options['output'], 'w', encoding='utf-8') as fh:
            fh.write(serializers.serialize('json', rows))
        self.stdout.write(self.style.SUCCESS(
            f'dumped={len(rows)} -> {options["output"]}'))
