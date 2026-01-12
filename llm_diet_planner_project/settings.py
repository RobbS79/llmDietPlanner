# File: llm_diet_planner_project/settings.py
import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# --- SECURITY ---
SECRET_KEY = config('SECRET_KEY', default='django-insecure-prod-key-must-be-set-in-digital-ocean')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,0.0.0.0', cast=Csv())

# --- APPS ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    
    # Third-party (Fundamental Integration)
    "corsheaders", # Resolves ModuleNotFoundError
    "rest_framework",
    "rest_framework.authtoken", # CRITICAL FIX: Fixes ImproperlyConfigured crash
    "rest_framework_simplejwt",
    "encrypted_model_fields",
    
    # Auth Stack
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "dj_rest_auth",
    "dj_rest_auth.registration",
    
    # Local apps
    "diet_planner",
    "login_app",
]

# --- MIDDLEWARE ---
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware", # Production static serving
    "corsheaders.middleware.CorsMiddleware", 
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# --- TEMPLATES ---
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

# --- DATABASE ---
DATABASE_URL = config('DATABASE_URL', default=f'sqlite:///{str(BASE_DIR / "db.sqlite3")}')
DATABASES = {'default': dj_database_url.parse(DATABASE_URL)}

# --- STATIC & VITE PRODUCTION ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
REACT_BUILD_DIR = BASE_DIR / "frontend" / "dist"

# Connect static files to the modern Vite 'dist' output
if os.path.exists(REACT_BUILD_DIR):
    STATICFILES_DIRS = [os.path.join(REACT_BUILD_DIR)]
else:
    STATICFILES_DIRS = []

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# --- AUTH v65+ COMPATIBLE SETTINGS ---
SITE_ID = 1
ACCOUNT_LOGIN_METHODS = {'email'} # Modern alternative to deprecated setting
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_SIGNUP_FIELDS = ['email', 'password1', 'password2']

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
    }
}

# --- REST & JWT ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}
REST_USE_JWT = True

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# --- PRODUCTION SECURITY ---
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CORS_ALLOWED_ORIGINS = ['https://squid-app-6avsy.ondigitalocean.app']
    CSRF_TRUSTED_ORIGINS = ['https://squid-app-6avsy.ondigitalocean.app']
else:
    CORS_ALLOW_ALL_ORIGINS = True
    CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://localhost:5173']

FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='local-testing-key-32-chars-!@#')