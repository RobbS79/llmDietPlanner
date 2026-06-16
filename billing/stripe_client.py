"""
Central Stripe SDK configuration.

Import `stripe` from here (not the package directly) so the API key and pinned
API version are guaranteed to be set. Keys come from settings/env — never
hardcoded. See docs/stripe-billing-plan.md §7 and the security best-practices
skill (prefer a restricted key `rk_` in production).
"""
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

# Pin the API version so object shapes don't shift under us on Stripe upgrades.
_api_version = getattr(settings, 'STRIPE_API_VERSION', '') or ''
if _api_version:
    stripe.api_version = _api_version


def is_configured() -> bool:
    """True when a secret key is present (lets endpoints fail clean in dev)."""
    return bool(settings.STRIPE_SECRET_KEY)


__all__ = ['stripe', 'is_configured']
