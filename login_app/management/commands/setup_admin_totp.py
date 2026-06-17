"""Enroll (or re-enroll) a user's TOTP device for Django-admin MFA.

This is the ONLY enrollment path by design: OTPAdminSite locks the web admin
until a confirmed device exists, and there is no self-service web flow, so an
attacker who guesses the password still cannot get in. The operator runs this
out-of-band in the DigitalOcean App Platform console (prod) or the dev-droplet
container, scans the printed QR / otpauth:// URL into a phone authenticator, and
logs in thereafter with password + rotating code.

    python manage.py setup_admin_totp <username> [--force]

The device row is written to the database (Supabase in prod), so it persists
across redeploys and is shared by every App Platform instance.
"""
import qrcode
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

DEVICE_NAME = "admin-totp"


class Command(BaseCommand):
    help = "Create/confirm a TOTP device for a user and print the enrollment QR + otpauth URL."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username of the (super)user to enroll.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace any existing admin-totp device (invalidates the old secret).",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist.")

        existing = TOTPDevice.objects.filter(user=user, name=DEVICE_NAME).first()
        if existing and not options["force"]:
            device = existing
            self.stdout.write(
                self.style.WARNING(
                    f"User '{username}' already has an '{DEVICE_NAME}' device "
                    f"(id={device.id}). Re-run with --force to regenerate the secret."
                )
            )
        else:
            if existing:
                existing.delete()
            device = TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=True)
            self.stdout.write(
                self.style.SUCCESS(f"Created confirmed TOTP device for '{username}' (id={device.id}).")
            )

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

    def _print_qr(self, url):
        """Render the otpauth URL as an ASCII QR so it can be scanned straight
        from the App Platform console (no file transfer needed)."""
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(out=self.stdout)
