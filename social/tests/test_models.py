from django.db import IntegrityError
from django.test import TestCase

from social.models import CHANNELS_BY_KIND, SocialPost


class SocialPostTests(TestCase):
    def test_kind_and_week_are_unique_together(self):
        SocialPost.objects.create(kind=SocialPost.Kind.DEALS, iso_week='2026-W37',
                                  scheduled_for='2026-09-07')
        with self.assertRaises(IntegrityError):
            SocialPost.objects.create(kind=SocialPost.Kind.DEALS, iso_week='2026-W37',
                                      scheduled_for='2026-09-07')

    def test_channels_default_from_kind(self):
        post = SocialPost.objects.create(kind=SocialPost.Kind.RECIPE, iso_week='2026-W37',
                                         scheduled_for='2026-09-09')
        self.assertEqual(post.channels, ['facebook', 'pinterest'])
        self.assertEqual(CHANNELS_BY_KIND['deals'], ['facebook'])

    def test_pending_channels_skips_published_ones(self):
        post = SocialPost.objects.create(kind=SocialPost.Kind.RECIPE, iso_week='2026-W37',
                                         scheduled_for='2026-09-09',
                                         facebook_post_id='123_456')
        self.assertEqual(post.pending_channels(), ['pinterest'])

    def test_utm_campaign_is_derived(self):
        post = SocialPost.objects.create(kind=SocialPost.Kind.SHOWCASE, iso_week='2026-W37',
                                         scheduled_for='2026-09-11')
        self.assertEqual(post.utm_campaign, 'auto-showcase-2026-W37')
