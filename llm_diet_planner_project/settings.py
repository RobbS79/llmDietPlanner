# File: llm_diet_planner_project/settings.py
"""
Django settings for llm_diet_planner_project.
Ensures Google credentials are loaded from both legacy and Vite-shared keys.
"""
import os
import sys
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# --- SECURITY ---
SECRET_KEY = config('SECRET_KEY', default='django-insecure-prod-key-must-be-set-in-digital-ocean')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='.ondigitalocean.app,localhost,127.0.0.1', cast=Csv())

# --- GOOGLE OAUTH CONFIGURATION ---
# Try multiple possible environment variable names to be safe
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default=config('VITE_GOOGLE_CLIENT_ID', default=None))
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET', default=None)

# LOG CONFIG STATUS (DURING STARTUP)
print(f"\n[STARTUP DEBUG] Google Client ID Present: {bool(GOOGLE_CLIENT_ID)}", file=sys.stderr)
if GOOGLE_CLIENT_ID:
    print(f"[STARTUP DEBUG] Google Client ID starts with: {GOOGLE_CLIENT_ID[:10]}...", file=sys.stderr)
print(f"[STARTUP DEBUG] Google Client Secret Present: {bool(GOOGLE_CLIENT_SECRET)}", file=sys.stderr)

# --- APPS ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt",
    "encrypted_model_fields",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "dj_rest_auth",
    "dj_rest_auth.registration",
    "diet_planner",
    "login_app",
    "shopifyin",
]

# --- ALLAUTH CONFIG (0.65+) ---
SITE_ID = 1
ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_SIGNUP_FIELDS = ['email'] 

ACCOUNT_ADAPTER = 'login_app.adapters.CustomSocialAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'login_app.adapters.CustomSocialAccountAdapter'

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
        'APP': {
            'client_id': GOOGLE_CLIENT_ID,
            'secret': GOOGLE_CLIENT_SECRET,
            'key': ''
        }
    }
}

# --- REMAINING STANDARD SETTINGS ---
DATABASES = {'default': dj_database_url.parse(config('DATABASE_URL', default=f'sqlite:///{str(BASE_DIR / "db.sqlite3")}'))}
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
}
REST_USE_JWT = True
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware", 
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]