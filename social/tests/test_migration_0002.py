from importlib import import_module

from django.apps import apps
from django.test import TestCase

from social.models import SocialPost

migration = import_module('social.migrations.0002_reject_reaction_era_drafts')


class RejectReactionEraDraftsTests(TestCase):
    def test_only_drafts_are_rejected_with_the_reason(self):
        draft = SocialPost.objects.create(kind='recipe', iso_week='2026-W39', scheduled_for='2026-09-23',
                                          status='draft', slack_ts='1.0')
        published = SocialPost.objects.create(kind='deals', iso_week='2026-W39', scheduled_for='2026-09-21',
                                              status='published', facebook_post_id='1_1')
        skipped = SocialPost.objects.create(kind='showcase', iso_week='2026-W38', scheduled_for='2026-09-18',
                                            status='skipped', error='no plan')
        migration.reject_drafts(apps, None)
        for row in (draft, published, skipped):
            row.refresh_from_db()
        self.assertEqual((draft.status, draft.error), ('rejected', migration.REASON))
        self.assertEqual(published.status, 'published')
        self.assertEqual((skipped.status, skipped.error), ('skipped', 'no plan'))
