"""
Django settings for llm_diet_planner_project project.
"""

from pathlib import Path
from decouple import config, Csv
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-prod-key')
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,.ondigitalocean.app', cast=Csv())

# Google OAuth Configuration
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default='')
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET', default='')
GOOGLE_REDIRECT_URI = config('GOOGLE_REDIRECT_URI', default='')

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "encrypted_model_fields",
    "diet_planner",
    "login_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware", # Must be immediately after SecurityMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "llm_diet_planner_project.urls"

WSGI_APPLICATION = "llm_diet_planner_project.wsgi.application"

# Database
DATABASE_URL = config('DATABASE_URL', default=f'sqlite:///{str(BASE_DIR / "db.sqlite3")}')
DATABASES = {'default': dj_database_url.parse(DATABASE_URL)}

# Static Files & WhiteNoise (The Color Fix)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Tell Django where to find the React assets BEFORE collecting
REACT_BUILD_DIR = BASE_DIR / "frontend" / "build"
STATICFILES_DIRS = [
    # Include the main build static folder (css, js, media)
    os.path.join(REACT_BUILD_DIR, "static"),
]

# Use WhiteNoise for efficient storage and serving
if not DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://*.ondigitalocean.app',
    cast=Csv()
)

# Email & Encryption Keys (Ensuring persistence)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='dummy-key-for-dev')

# Celery
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://127.0.0.1:6379/0')