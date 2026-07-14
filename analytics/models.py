from django.conf import settings
from django.db import models


class MarketingAttribution(models.Model):
    """First-party attribution + consent record, one row per user.

    Populated at signup from the client-captured UTM/fbclid/consent payload,
    so we can answer "which campaign -> paid" in our own DB independent of Meta,
    and so webhook-time CAPI events can honor consent (no browser present then).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="marketing_attribution",
    )
    utm_source = models.CharField(max_length=255, blank=True, default="")
    utm_medium = models.CharField(max_length=255, blank=True, default="")
    utm_campaign = models.CharField(max_length=255, blank=True, default="")
    utm_content = models.CharField(max_length=255, blank=True, default="")
    utm_term = models.CharField(max_length=255, blank=True, default="")
    fbclid = models.CharField(max_length=512, blank=True, default="")
    fbp = models.CharField(max_length=255, blank=True, default="")
    fbc = models.CharField(max_length=512, blank=True, default="")
    landing_at = models.DateTimeField(null=True, blank=True)

    marketing_consent = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_version = models.CharField(max_length=20, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Attribution(user={self.user_id}, consent={self.marketing_consent})"
