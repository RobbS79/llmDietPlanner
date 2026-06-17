"""Reconcile a Stripe subscription into a Django entitlement row.

The operational repair tool for the "paid in Stripe but no service in the app"
gap: when a webhook never arrived (endpoint misconfigured) or the subscription
was created outside checkout (e.g. in the Stripe dashboard, so it carries no
`user_id` metadata), Stripe has an active subscription but Django has no
`Subscription` row, and the generation gate returns 402.

    python manage.py reconcile_subscription <sub_id> [--email X | --user-id N]

It retrieves the live subscription from Stripe, resolves the owning user
(explicit flag first, then the sub's metadata, then an existing customer
mapping), and upserts the entitlement row via the same path the webhooks use.
Idempotent: safe to re-run.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from billing import services


class Command(BaseCommand):
    help = "Provision/refresh a Django entitlement row from a Stripe subscription id."

    def add_arguments(self, parser):
        parser.add_argument("subscription_id", help="Stripe Subscription id (sub_…).")
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--email", help="Bind to the user with this email.")
        group.add_argument("--user-id", type=int, help="Bind to the user with this id.")

    def handle(self, *args, **options):
        sub_id = options["subscription_id"]
        sub_obj = services.retrieve_subscription(sub_id)
        if not sub_obj or not sub_obj.get("id"):
            raise CommandError(f"Stripe returned no subscription for '{sub_id}'.")
        customer_id = sub_obj.get("customer")

        user = self._resolve_user(options, sub_obj, customer_id)
        if user is None:
            raise CommandError(
                f"Could not resolve a user for subscription '{sub_id}'. "
                f"Pass --email or --user-id to bind it explicitly."
            )

        sub = services.upsert_subscription(user, sub_obj, customer_id)
        if sub is None:
            raise CommandError(
                f"Subscription '{sub_id}' has no recognized tier/price; "
                f"check STRIPE_PRICE_STANDARD / STRIPE_PRICE_PREMIUM."
            )

        self.stdout.write(self.style.SUCCESS(
            f"Reconciled {sub.get_tier_display()} subscription for "
            f"{user.username} (id={user.id}): status={sub.status}, "
            f"period_end={sub.current_period_end}, entitled={sub.is_entitled()}."
        ))

    def _resolve_user(self, options, sub_obj, customer_id):
        User = get_user_model()
        if options.get("email"):
            user = User.objects.filter(email__iexact=options["email"]).first()
            if user is None:
                raise CommandError(f"No user with email '{options['email']}'.")
            return user
        if options.get("user_id"):
            user = User.objects.filter(id=options["user_id"]).first()
            if user is None:
                raise CommandError(f"No user with id {options['user_id']}.")
            return user
        # Fall back to the same resolution the webhooks use.
        return services._resolve_user(sub_obj, customer_id)
