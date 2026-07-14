"""Idempotently provision the QA verification user for /qa-prod.

SECURITY (incident 2026-06-02-dbminer): the QA password must NEVER be committed.
It is supplied only via DO SECRET env vars (QA_TEST_USERNAME / QA_TEST_PASSWORD,
optional QA_TEST_EMAIL). If either credential is absent the command no-ops, and
the authed portion of /qa-prod is skipped (public-only run).

Wired into start.sh so every deploy keeps the account in sync. Idempotent:
creates the user if absent, otherwise resets its password (mirrors the superuser
bootstrap). The account is a plain, non-staff, non-superuser user.
"""
import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Idempotently provision the QA verification user from env secrets."

    def handle(self, *args, **options):
        username = os.environ.get("QA_TEST_USERNAME", "").strip()
        password = os.environ.get("QA_TEST_PASSWORD", "")
        email = os.environ.get("QA_TEST_EMAIL", "").strip()

        if not username or not password:
            self.stdout.write(
                "QA_TEST_USERNAME/QA_TEST_PASSWORD not set — skipping QA account seed."
            )
            return

        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email, "is_active": True}
        )
        user.email = email or user.email
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        user.save()

        self.stdout.write(
            "QA account created." if created else "QA account password reset."
        )
