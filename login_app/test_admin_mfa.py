"""Tests for admin MFA hardening.

Two surfaces:
  1. `setup_admin_totp` management command — out-of-band TOTP enrollment used
     from the App Platform console (the only way to enroll, by design, so the
     web admin can be locked the moment OTPAdminSite is active).
  2. OTPAdminSite enforcement — an authenticated superuser who has NOT cleared
     a TOTP challenge must not reach the admin.
"""
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from django_otp.plugins.otp_totp.models import TOTPDevice


class SetupAdminTotpCommandTests(TestCase):
    def test_creates_confirmed_totp_device_and_prints_enrollment_url(self):
        user = User.objects.create_superuser("admin", "a@b.com", "pw-strong-123")
        out = StringIO()

        call_command("setup_admin_totp", "admin", stdout=out)

        devices = TOTPDevice.objects.filter(user=user)
        self.assertEqual(devices.count(), 1)
        self.assertTrue(devices.first().confirmed)
        # The scannable enrollment secret must be surfaced to the operator.
        self.assertIn("otpauth://", out.getvalue())

    def test_unknown_user_raises_command_error(self):
        with self.assertRaises(CommandError):
            call_command("setup_admin_totp", "ghost", stdout=StringIO())

    def test_idempotent_without_force(self):
        user = User.objects.create_superuser("admin", "a@b.com", "pw-strong-123")

        call_command("setup_admin_totp", "admin", stdout=StringIO())
        call_command("setup_admin_totp", "admin", stdout=StringIO())

        self.assertEqual(TOTPDevice.objects.filter(user=user).count(), 1)

    def test_force_regenerates_the_device(self):
        user = User.objects.create_superuser("admin", "a@b.com", "pw-strong-123")
        call_command("setup_admin_totp", "admin", stdout=StringIO())
        first_id = TOTPDevice.objects.get(user=user).id

        call_command("setup_admin_totp", "admin", "--force", stdout=StringIO())

        devices = TOTPDevice.objects.filter(user=user)
        self.assertEqual(devices.count(), 1)
        self.assertNotEqual(devices.first().id, first_id)


class AdminMfaEnforcementTests(TestCase):
    def test_unverified_superuser_is_denied_admin_index(self):
        """A logged-in superuser with no satisfied OTP challenge is bounced to
        the admin login by OTPAdminSite — password alone is not enough."""
        user = User.objects.create_superuser("admin", "a@b.com", "pw-strong-123")
        self.client.force_login(user)

        resp = self.client.get(reverse("admin:index"))

        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])
