"""SocialPost is the shared contract between the generator job (writes) and
the publisher job (reads); the database is the only storage the two
containers share."""
from django.db import models


CHANNELS_BY_KIND = {
    'deals': ['facebook'],
    'recipe': ['facebook', 'pinterest'],
    'showcase': ['facebook'],
}


class SocialPost(models.Model):
    class Kind(models.TextChoices):
        DEALS = 'deals', 'Weekly deals roundup'
        RECIPE = 'recipe', 'Recipe card'
        SHOWCASE = 'showcase', 'Plan showcase'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft (awaiting ✅)'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        PUBLISHED = 'published', 'Published'
        FAILED = 'failed', 'Failed'
        SKIPPED = 'skipped', 'Skipped (no facts)'

    kind = models.CharField(max_length=16, choices=Kind.choices)
    iso_week = models.CharField(max_length=8, help_text='e.g. 2026-W37')
    scheduled_for = models.DateField()
    channels = models.JSONField(default=list, blank=True)
    facts = models.JSONField(default=dict, blank=True)
    caption = models.TextField(blank=True, default='')
    group_variant = models.TextField(blank=True, default='')
    image = models.BinaryField(blank=True, null=True, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    slack_channel = models.CharField(max_length=32, blank=True, default='')
    slack_ts = models.CharField(max_length=32, blank=True, default='')
    approved_by = models.CharField(max_length=32, blank=True, default='')
    facebook_post_id = models.CharField(max_length=64, blank=True, default='')
    pinterest_pin_id = models.CharField(max_length=64, blank=True, default='')
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['kind', 'iso_week'], name='social_post_kind_week'),
        ]
        ordering = ['-scheduled_for', 'kind']

    def save(self, *args, **kwargs):
        if not self.channels:
            channels = CHANNELS_BY_KIND.get(self.kind)
            if channels is None:
                raise ValueError(f'unknown kind {self.kind!r}')
            self.channels = list(channels)
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {'channels'}
        super().save(*args, **kwargs)

    @property
    def utm_campaign(self) -> str:
        return f'auto-{self.kind}-{self.iso_week}'

    @property
    def image_bytes(self) -> bytes:
        """psycopg2 returns bytea as memoryview; sqlite returns bytes."""
        return bytes(self.image) if self.image else b''

    def external_id(self, channel: str) -> str:
        ids = {'facebook': self.facebook_post_id, 'pinterest': self.pinterest_pin_id}
        if channel not in ids:
            raise ValueError(channel)
        return ids[channel]

    def set_external_id(self, channel: str, value: str) -> None:
        if channel == 'facebook':
            self.facebook_post_id = value
        elif channel == 'pinterest':
            self.pinterest_pin_id = value
        else:
            raise ValueError(channel)

    def pending_channels(self) -> list:
        return [c for c in self.channels if not self.external_id(c)]

    def __str__(self) -> str:
        return f'{self.kind} {self.iso_week} [{self.status}]'
