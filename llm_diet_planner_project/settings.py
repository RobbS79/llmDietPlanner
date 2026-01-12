# File: llm_diet_planner_project/settings.py
from pathlib import Path
from decouple import config, Csv
import os
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

# Security
SECRET_KEY = config('SECRET_KEY', default='django-insecure-key-ensure-this-is-set-in-digital-ocean')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,0.0.0.0', cast=Csv())

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    
    # Third-party
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "encrypted_model_fields",
    
    # Auth Stack
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "dj_rest_auth",
    "dj_rest_auth.registration",
    'rest_framework.authtoken',
    
    # Local apps
    "diet_planner",
    "login_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware", # Correctly placed before CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# --- CRITICAL FIX: RE-ADDED TEMPLATES CONFIGURATION ---
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "llm_diet_planner_project" / "templates"],
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

ROOT_URLCONF = "llm_diet_planner_project.urls"
WSGI_APPLICATION = "llm_diet_planner_project.wsgi.application"

# Database
import dj_database_url
DATABASE_URL = config('DATABASE_URL', default=f'sqlite:///{str(BASE_DIR / "db.sqlite3")}')
DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL)
}

# Static & Vite Production Integration
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
REACT_BUILD_DIR = BASE_DIR / "frontend" / "dist"

STATICFILES_DIRS = [
    os.path.join(REACT_BUILD_DIR),
]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# --- ALLAUTH UPDATED SETTINGS (Fixed Deprecations) ---
SITE_ID = 1
ACCOUNT_LOGIN_METHODS = {'email'} # Replaces ACCOUNT_AUTHENTICATION_METHOD
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'none'
# Using default SIGNUP_FIELDS to resolve warnings

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
    }
}

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}
REST_USE_JWT = True

# JWT Config
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Production Proxies
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

CORS_ALLOW_ALL_ORIGINS = DEBUG
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='https://squid-app-6avsy.ondigitalocean.app', cast=Csv())
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='')