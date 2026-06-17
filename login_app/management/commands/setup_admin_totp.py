"""Enroll (or re-enroll) a user's TOTP device for Django-admin MFA.

This is the ONLY enrollment path by design: OTPAdminSite locks the web admin
until a confirmed device exists, and there is no self-service web flow, so an
attacker who guesses the password still cannot get in.

Two ways to run it:

  1. Interactive (dev / a working console):
        python manage.py setup_admin_totp <username> [--force]
     A random secret is generated; the printed QR / otpauth:// URL is scanned
     into a phone authenticator.

  2. Console-free bootstrap (prod, where the DO App Platform console is
     unusable): provide the secret out-of-band via a DO SECRET env var, and
     `start.sh` runs this on every boot:
        python manage.py setup_admin_totp <username> --secret "$ADMIN_TOTP_SECRET" --quiet
     `--secret` makes enrollment DETERMINISTIC and idempotent — the device key
     is derived from the supplied base32 secret, so re-running on every redeploy
     keeps the same code sequence the operator already has in their authenticator
     (no --force / no lockout). The operator sets the same base32 secret in their
     authenticator app once.

The device row is written to the database (Supabase in prod), so it persists
across redeploys and is shared by every App Platform instance.
"""
import base64
import binascii

import qrcode
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

DEVICE_NAME = "admin-totp"


def _base32_to_hex_key(secret: str) -> str:
    """Convert an operator-supplied base32 TOTP secret (the format an
    authenticator app expects) into the hex key TOTPDevice.key stores."""
    cleaned = secret.strip().replace(" ", "").upper()
    # Authenticator secrets are often shown unpadded; b32decode wants padding.
    cleaned += "=" * (-len(cleaned) % 8)
    try:
        raw = base64.b32decode(cleaned, casefold=True)
    except (binascii.Error, ValueError) as exc:
        raise CommandError(f"ADMIN_TOTP_SECRET is not valid base32: {exc}")
    if not raw:
        raise CommandError("ADMIN_TOTP_SECRET decoded to empty bytes.")
    return binascii.hexlify(raw).decode()


class Command(BaseCommand):
    help = "Create/confirm a TOTP device for a user and print the enrollment QR + otpauth URL."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username of the (super)user to enroll.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace any existing admin-totp device (invalidates the old secret).",
        )
        parser.add_argument(
            "--secret",
            default=None,
            help=(
                "Base32 TOTP secret to seed the device key from (deterministic, "
                "idempotent enrollment for console-free prod bootstrap)."
            ),
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress the QR / otpauth URL output (used at boot to avoid logging the secret).",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist.")

        seed_key = _base32_to_hex_key(options["secret"]) if options["secret"] else None
        existing = TOTPDevice.objects.filter(user=user, name=DEVICE_NAME).first()

        if seed_key is not None:
            # Deterministic mode: ensure exactly one confirmed device whose key
            # matches the supplied secret. Idempotent across redeploys.
            if existing and existing.key == seed_key and existing.confirmed:
                device = existing
                self._note(options, self.style.SUCCESS(
                    f"Admin TOTP device for '{username}' already matches the supplied secret (id={device.id})."))
            else:
                if existing:
                    existing.delete()
                device = TOTPDevice.objects.create(
                    user=user, name=DEVICE_NAME, key=seed_key, confirmed=True)
                self._note(options, self.style.SUCCESS(
                    f"Enrolled admin TOTP device for '{username}' from supplied secret (id={device.id})."))
        elif existing and not options["force"]:
            device = existing
            self._note(options, self.style.WARNING(
                f"User '{username}' already has an '{DEVICE_NAME}' device "
                f"(id={device.id}). Re-run with --force to regenerate the secret."))
        else:
            if existing:
                existing.delete()
            device = TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=True)
            self._note(options, self.style.SUCCESS(
                f"Created confirmed TOTP device for '{username}' (id={device.id})."))

        if options["quiet"]:
            return

        url = device.config_url
        self._print_qr(url)
        self.stdout.write("")
        self.stdout.write("Scan the QR above, or enter this URL manually in your authenticator app:")
        self.stdout.write(url)
        self.stdout.write("")
        self.stdout.write(
            self.style.NOTICE(
                "Then log in to the admin with your password + the 6-digit code. "
                "Keep this URL secret; anyone with it can generate your codes."
            )
        )

    def _note(self, options, message):
        """Write a status line unless --quiet (boot logs stay clean)."""
        if not options["quiet"]:
            self.stdout.write(message)

    def _print_qr(self, url):
        """Render the otpauth URL as an ASCII QR so it can be scanned straight
        from the App Platform console (no file transfer needed)."""
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(out=self.stdout)
