# Django Admin MFA & Brute-force Hardening

The Django admin is the highest-value public surface — full read/write access to
the paying-user database. This change adds two independent controls in front of
it **without touching the user-facing allauth/JWT login flow**.

## What it does

1. **TOTP MFA on `/admin/` (django-otp).** The admin login demands a rotating
   6-digit code on top of the password. We swap the default `AdminSite` for
   `OTPAdminSite` in `urls.py` (via `__class__` reassignment, which preserves
   every already-registered model).
2. **Brute-force lockout (django-axes).** Failed logins are rate-limited and
   locked out per `(username, IP)` pair. Lockout state lives in the DB, so it is
   shared across App Platform instances and survives redeploys.
3. **Obscured admin path.** The admin is served at `ADMIN_URL_PATH` (default
   `admin/`) so blind scanners hammering `/admin/` find nothing in prod.

## Enrollment is out-of-band by design

`OTPAdminSite` locks the web admin until a **confirmed** TOTP device exists, and
there is **no self-service web enrollment**. An attacker who guesses the
password still cannot get in.

**Interactive (dev / a working console):**

```bash
python manage.py setup_admin_totp <username>        # create + print QR / otpauth URL
python manage.py setup_admin_totp <username> --force # rotate the secret
```

Scan the printed ASCII QR (or the `otpauth://` URL) into a phone authenticator,
then log in with password + code. The device row persists in the DB (Supabase in
prod).

**Console-free bootstrap (prod).** The DO App Platform console is currently
unusable, so prod enrollment is seeded from a DO SECRET env var instead.
`start.sh` runs this on every boot when `ADMIN_TOTP_SECRET` is set:

```bash
python manage.py setup_admin_totp <username> --secret "$ADMIN_TOTP_SECRET" --quiet
```

`--secret` derives the device key deterministically from a base32 secret, so the
step is idempotent — redeploys keep the same code sequence already in the
operator's authenticator (no rotation, no lockout). Generate the secret once,
set it as the `ADMIN_TOTP_SECRET` DO SECRET, and add the *same* secret to your
authenticator app (manual entry or scan the matching QR). `--quiet` keeps the
secret out of the deploy logs.

## Configuration (env vars)

| Var | Default | Purpose |
|-----|---------|---------|
| `ADMIN_MFA_ENABLED` | `True` | Master switch / emergency escape hatch if the OTP flow ever wedges. |
| `ADMIN_TOTP_SECRET` | (unset) | Base32 TOTP secret. When set, `start.sh` enrolls the admin device from it on boot (console-free). Set as a DO **SECRET**. |
| `ADMIN_URL_PATH` | `admin/` | Secret-ish slug for the admin path in prod. |
| `AXES_ENABLED` | `True` | Master switch for brute-force lockout. |
| `AXES_FAILURE_LIMIT` | `5` | Failed attempts before lockout. |
| `AXES_COOLOFF_HOURS` | `1` | Lockout duration. |
| `AXES_IPWARE_PROXY_COUNT` | `1` | Trusted proxy hops (DO load balancer = 1). Bump if DO adds hops. |

## Implementation notes / gotchas

- **`AUTHENTICATION_BACKENDS` must list `AxesStandaloneBackend` first.** It does
  not authenticate; it short-circuits with a lockout when over the limit, then
  defers to `ModelBackend` (password) and the allauth backend (social).
- **`authenticate()` must be called with `request`.** `AxesStandaloneBackend`
  raises `AxesBackendRequestParameterRequired` otherwise. The JWT login view
  (`login_app/views.py`) passes `request` for exactly this reason — calling it
  without `request` 500s every login.
- **Middleware order:** `OTPMiddleware` after `AuthenticationMiddleware`;
  `AxesMiddleware` last.
- **Real client IP** is read from `X-Forwarded-For` trusting exactly one proxy
  hop, so the header can't be spoofed to forge a source IP.

## Deploy checklist (operational, post-merge)

Set these in the DO dashboard env-var form **before** the deploy that ships MFA,
so the admin is enrolled on the first boot (otherwise `/admin/` locks):

1. `DJANGO_SUPERUSER_PASSWORD` (SECRET) — so `start.sh` bootstraps the superuser
   (prod may currently have none).
2. `ADMIN_TOTP_SECRET` (SECRET) — the base32 secret; add the same secret to your
   authenticator app. `start.sh` enrolls the device from it on boot.
3. `ADMIN_URL_PATH` (optional) — a secret slug for the admin path.

Then:

4. Deploy (push to `prod`). Migrations for `otp_totp`, `otp_static`, `axes` and
   the TOTP enrollment all run automatically via `start.sh`.
5. Confirm admin login at `/<ADMIN_URL_PATH>` requires password + 6-digit code;
   confirm the user-facing `/api/auth/login/` still works.

**Escape hatch:** if anything wedges, set `ADMIN_MFA_ENABLED=False` (dashboard)
and redeploy to fall back to password-only admin.
