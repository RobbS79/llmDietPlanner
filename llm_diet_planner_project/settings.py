"""
Django settings for llm_diet_planner_project project.
Final refactor for production stability, styling, and Google OAuth.
"""

from pathlib import Path
from decouple import config, Csv
import os
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-prod-key-for-initial-setup')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,.ondigitalocean.app', cast=Csv())

# --- GOOGLE OAUTH CONFIGURATION ---
# DigitalOcean expects these variables. Ensure they match your Dashboard keys.
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default='')
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET', default='')
GOOGLE_REDIRECT_URI = config('GOOGLE_REDIRECT_URI', default='')

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    "rest_framework_simplejwt",
    "encrypted_model_fields",
    "whitenoise.runserver_nostatic",
    # Local apps
    "diet_planner",
    "login_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Correct position for WhiteNoise
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "llm_diet_planner_project.urls"

# FIX: Configuration for Admin Application (Resolves admin.E403)
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

WSGI_APPLICATION = "llm_diet_planner_project.wsgi.application"

# Database Configuration
DATABASE_URL = config('DATABASE_URL', default=f'sqlite:///{str(BASE_DIR / "db.sqlite3")}')
DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL)
}

# Static Files & WhiteNoise (Ensures the "dark blue" theme loads correctly)
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# React build directory integration
REACT_APP_DIR = os.path.join(BASE_DIR, "frontend")
REACT_BUILD_DIR = os.path.join(REACT_APP_DIR, "build")

# Crucial: Tell Django where the built assets live before they are collected
STATICFILES_DIRS = [
    # Include the main build static folder (contains bundled css, js, media)
    os.path.join(REACT_BUILD_DIR, "static"),
]

# Use WhiteNoise's optimized storage for production
if not DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# CSRF & Security Configuration
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://*.ondigitalocean.app',
    cast=Csv()
)

if not DEBUG:
    SECURE_SSL_REDIRECT = False  # DigitalOcean handles SSL termination
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# JWT Settings
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
}

# Encryption Key for sensitive fields (GDPR)
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='key-for-migrations-only-replace-in-prod')

# Celery Configuration
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_TIMEZONE = "UTC"