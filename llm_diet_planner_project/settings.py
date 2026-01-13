# File: llm_diet_planner_project/settings.py
import os
import sys
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# --- 1. SECURITY & ENCRYPTION (MUST BE AT THE TOP) ---
# We load the encryption key immediately to prevent initialization crashes in models.py
SECRET_KEY = config('SECRET_KEY', default='django-insecure-prod-key-must-be-set-in-digital-ocean')
DEBUG = config('DEBUG', default=False, cast=bool)
# FIELD_ENCRYPTION_KEY is required by django-encrypted-model-fields
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='local-testing-key-32-chars-!@#')

# Startup diagnostic logs to stderr for DigitalOcean Runtime Logs
print(f"[STARTUP] FIELD_ENCRYPTION_KEY Present: {bool(FIELD_ENCRYPTION_KEY)}", file=sys.stderr)
print(f"[STARTUP] GOOGLE_CLIENT_ID Loaded: {bool(config('GOOGLE_CLIENT_ID', default=None))}", file=sys.stderr)

# --- 2. GOOGLE OAUTH CONFIGURATION ---
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default=config('VITE_GOOGLE_CLIENT_ID', default=None))
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET', default=None)

# --- 3. APPS ---
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

# --- 4. ALLAUTH & SOCIAL CONFIG ---
SITE_ID = 1
ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'none'
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

# --- 5. STATIC & VITE PRODUCTION ---
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
REACT_BUILD_DIR = os.path.join(BASE_DIR, "frontend", "dist")

STATICFILES_DIRS = []
if os.path.exists(REACT_BUILD_DIR):
    STATICFILES_DIRS.append(REACT_BUILD_DIR)

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
WHITENOISE_INDEX_FILE = True

# --- 6. MIDDLEWARE & DATABASE ---
DATABASES = {'default': dj_database_url.parse(config('DATABASE_URL', default=f'sqlite:///{str(BASE_DIR / "db.sqlite3")}'))}

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

ROOT_URLCONF = "llm_diet_planner_project.urls"
WSGI_APPLICATION = "llm_diet_planner_project.wsgi.application"
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
}
REST_USE_JWT = True

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "llm_diet_planner_project", "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]