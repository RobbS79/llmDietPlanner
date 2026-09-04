from django.db import IntegrityError, transaction
from django.test import TestCase

from social.models import CHANNELS_BY_KIND, SocialPost


class SocialPostTests(TestCase):
    def test_kind_and_week_are_unique_together(self):
        SocialPost.objects.create(kind=SocialPost.Kind.DEALS, iso_week='2026-W37',
                                  scheduled_for='2026-09-07')
        with self.assertRaises(IntegrityError), transaction.atomic():
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

    def test_set_external_id_sets_facebook_and_pinterest(self):
        post = SocialPost.objects.create(kind=SocialPost.Kind.RECIPE, iso_week='2026-W38',
                                         scheduled_for='2026-09-16')
        post.set_external_id('facebook', '111_222')
        post.set_external_id('pinterest', 'pin-333')
        self.assertEqual(post.facebook_post_id, '111_222')
        self.assertEqual(post.pinterest_pin_id, 'pin-333')

    def test_set_external_id_rejects_unknown_channel(self):
        post = SocialPost.objects.create(kind=SocialPost.Kind.RECIPE, iso_week='2026-W38',
                                         scheduled_for='2026-09-16')
        with self.assertRaises(ValueError):
            post.set_external_id('tiktok', 'abc')

    def test_external_id_rejects_unknown_channel(self):
        post = SocialPost.objects.create(kind=SocialPost.Kind.RECIPE, iso_week='2026-W38',
                                         scheduled_for='2026-09-16')
        with self.assertRaises(ValueError):
            post.external_id('tiktok')

    def test_image_bytes_round_trips_and_defaults_empty(self):
        post = SocialPost.objects.create(kind=SocialPost.Kind.SHOWCASE, iso_week='2026-W38',
                                         scheduled_for='2026-09-18')
        self.assertEqual(post.image_bytes, b'')
        post.image = b'\x89PNG'
        post.save(update_fields=['image'])
        post.refresh_from_db()
        self.assertEqual(post.image_bytes, b'\x89PNG')

    def test_save_rejects_unknown_kind(self):
        post = SocialPost(kind='', iso_week='2026-W38', scheduled_for='2026-09-18')
        with self.assertRaises(ValueError):
            post.save()

    def test_save_with_update_fields_still_persists_derived_channels(self):
        # Simulates a row whose `channels` was somehow left empty (e.g. a
        # legacy row predating this field) getting resaved with an unrelated
        # field in update_fields: the derived channels must not be silently
        # dropped from the UPDATE statement.
        post = SocialPost.objects.create(kind=SocialPost.Kind.DEALS, iso_week='2026-W39',
                                         scheduled_for='2026-09-21')
        SocialPost.objects.filter(pk=post.pk).update(channels=[])
        post.channels = []
        post.status = SocialPost.Status.APPROVED
        post.save(update_fields=['status'])
        post.refresh_from_db()
        self.assertEqual(post.channels, CHANNELS_BY_KIND['deals'])
