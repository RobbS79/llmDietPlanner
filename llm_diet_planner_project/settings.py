# File: llm_diet_planner_project/settings.py
import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# --- 1. SECURITY & ENCRYPTION ---
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY')

# --- 2. HOSTS & PROXY ---
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='', cast=Csv())
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# --- CORS ---
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())
CORS_ALLOW_CREDENTIALS = True

# --- CSRF ---
# Defaults to CORS_ALLOWED_ORIGINS since both want scheme://host form;
# can be overridden via env var if the two lists need to diverge.
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default=','.join(CORS_ALLOWED_ORIGINS),
    cast=Csv(),
)

# --- SECURITY HEADERS ---
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# --- 3. STATIC FILES & WHITENOISE ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
REACT_BUILD_DIR = BASE_DIR / "frontend" / "dist"

STATICFILES_DIRS = []
if REACT_BUILD_DIR.exists():
    STATICFILES_DIRS.append(REACT_BUILD_DIR)

STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
WHITENOISE_INDEX_FILE = True

# --- 4. INSTALLED APPS ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.sitemaps",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # Added for production rotation support
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
    "slack_bot",
]

# --- 5. MIDDLEWARE ---
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "llm_diet_planner_project.middleware.SecurityHeadersMiddleware",
    "corsheaders.middleware.CorsMiddleware", 
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# --- 6. TEMPLATES ---
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "llm_diet_planner_project" / "templates",
            REACT_BUILD_DIR
        ],
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

# --- 7. AUTH & DATABASE ---
SITE_ID = 1
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default=config('VITE_GOOGLE_CLIENT_ID', default=None))
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET', default=None)
FRONTEND_URL = config('FRONTEND_URL', default='')
DATABASES = {'default': dj_database_url.parse(config('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}'))}
ROOT_URLCONF = "llm_diet_planner_project.urls"
WSGI_APPLICATION = "llm_diet_planner_project.wsgi.application"

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
}

# --- PASSWORD VALIDATION ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- AUTHENTICATION HARDENING ---
# Extended lifetimes to account for DigitalOcean latency and long LLM generation wait times
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=24),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

REST_USE_JWT = True
ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_ADAPTER = 'login_app.adapters.CustomSocialAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'login_app.adapters.CustomSocialAccountAdapter'
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
        'APP': {'client_id': GOOGLE_CLIENT_ID, 'secret': GOOGLE_CLIENT_SECRET, 'key': ''}
    }
}

# --- PDF Upload ---
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024  # 15 MB (10 MB PDF + form overhead)

# --- 8. CELERY CONFIGURATION & REDIS STABILITY ---
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Performance Tuning for long-running LLM synthesis
CELERY_TASK_SOFT_TIME_LIMIT = 300  # 5 minutes
CELERY_TASK_TIME_LIMIT = 400
CELERY_WORKER_PREFETCH_MULTIPLIER = 1 # Prevent one worker from hoarding heavy synthesis tasks

# Backward compatibility aliases
BROKER_URL = CELERY_BROKER_URL
RESULT_BACKEND = CELERY_RESULT_BACKEND

# Celery Beat schedule — proactive scraping and freshness lifecycle
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Leaflet stores: scrape Mon + Thu mornings (when leaflets typically change)
    'scrape-lidl-cz': {
        'task': 'diet_planner.tasks.scrape_store_task',
        'schedule': crontab(hour=6, minute=0, day_of_week='mon,thu'),
        'args': ('LIDL_CZ',),
    },
    'scrape-albert-cz': {
        'task': 'diet_planner.tasks.scrape_store_task',
        'schedule': crontab(hour=6, minute=5, day_of_week='mon,thu'),
        'args': ('ALBERT_CZ',),
    },
    'scrape-kaufland-cz': {
        'task': 'diet_planner.tasks.scrape_store_task',
        'schedule': crontab(hour=6, minute=10, day_of_week='mon,thu'),
        'args': ('KAUFLAND_CZ',),
    },
    'scrape-penny-cz': {
        'task': 'diet_planner.tasks.scrape_store_task',
        'schedule': crontab(hour=6, minute=15, day_of_week='mon,thu'),
        'args': ('PENNY_CZ',),
    },
    'scrape-tesco-cz': {
        'task': 'diet_planner.tasks.scrape_store_task',
        'schedule': crontab(hour=6, minute=20, day_of_week='mon,thu'),
        'args': ('TESCO_CZ',),
    },
    'scrape-lidl-sk': {
        'task': 'diet_planner.tasks.scrape_store_task',
        'schedule': crontab(hour=6, minute=25, day_of_week='mon,thu'),
        'args': ('LIDL_SK',),
    },
    'scrape-kaufland-sk': {
        'task': 'diet_planner.tasks.scrape_store_task',
        'schedule': crontab(hour=6, minute=30, day_of_week='mon,thu'),
        'args': ('KAUFLAND_SK',),
    },
    # Online stores: scrape daily (prices change more frequently)
    'scrape-rohlik-daily': {
        'task': 'diet_planner.tasks.scrape_store_task',
        'schedule': crontab(hour=5, minute=0),
        'args': ('ROHLIK',),
    },
    'scrape-lunys-daily': {
        'task': 'diet_planner.tasks.scrape_store_task',
        'schedule': crontab(hour=5, minute=15),
        'args': ('LUNYS',),
    },
    # Freshness lifecycle: transition states every hour
    'update-freshness-states': {
        'task': 'diet_planner.tasks.update_freshness_states_task',
        'schedule': crontab(minute=0),  # top of every hour
    },
    # Archive expired offers weekly
    'archive-expired-offers': {
        'task': 'diet_planner.tasks.archive_expired_offers_task',
        'schedule': crontab(hour=3, minute=0, day_of_week='sun'),
    },
    # Daily health check at 9am UTC
    'scraper-health-check': {
        'task': 'diet_planner.tasks.scraper_health_check_task',
        'schedule': crontab(hour=9, minute=0),
    },
}

# Freshness TTL config per store type (hours)
FRESHNESS_CONFIG = {
    # Leaflet-based stores (weekly leaflets)
    'LIDL_CZ':     {'fresh_hours': 72, 'stale_hours': 120, 'expire_hours': 168},
    'LIDL_SK':     {'fresh_hours': 72, 'stale_hours': 120, 'expire_hours': 168},
    'ALBERT_CZ':   {'fresh_hours': 72, 'stale_hours': 120, 'expire_hours': 168},
    'KAUFLAND_CZ': {'fresh_hours': 72, 'stale_hours': 120, 'expire_hours': 168},
    'KAUFLAND_SK': {'fresh_hours': 72, 'stale_hours': 120, 'expire_hours': 168},
    'PENNY_CZ':    {'fresh_hours': 72, 'stale_hours': 120, 'expire_hours': 168},
    'TESCO_CZ':    {'fresh_hours': 72, 'stale_hours': 120, 'expire_hours': 168},
    # Online stores (prices change daily)
    'ROHLIK':      {'fresh_hours': 12, 'stale_hours': 24, 'expire_hours': 48},
    'LUNYS':       {'fresh_hours': 12, 'stale_hours': 24, 'expire_hours': 48},
    'KOSIK_CZ':    {'fresh_hours': 12, 'stale_hours': 24, 'expire_hours': 48},
}

# Feature flag for catalog-constrained generation
CATALOG_CONSTRAINED_GENERATION = config('CATALOG_CONSTRAINED_GENERATION', default=True, cast=bool)

# --- 9. GEMINI AI CONFIGURATION ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', config('GEMINI_API_KEY', default=None))
GEMINI_MODEL = config('GEMINI_MODEL', default='gemini-2.5-flash')
GEMINI_MAX_OUTPUT_TOKENS = int(config('GEMINI_MAX_OUTPUT_TOKENS', default=65536))
GEMINI_IMAGE_MODEL = config('GEMINI_IMAGE_MODEL', default='gemini-2.5-flash-image')

if not GEMINI_API_KEY:
    import logging as _log
    _log.getLogger(__name__).warning("GEMINI_API_KEY is not set")

# --- 9b. ANTHROPIC / CLAUDE (cross-model coherence judge) ---
# Gemini writes the meal plan; Claude grades it. Used by the semantic
# "simulated human" coherence judge (diet_planner/services/recipe_human_judge.py)
# to catch recipe/shopping-list incoherence a regex can't. Advisory and
# fail-open: when the flag is off or no key is set, the judge never runs and
# nothing else changes. See docs/qa-recipe-shopping-coherence.md.
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', config('ANTHROPIC_API_KEY', default=None))
RECIPE_HUMAN_JUDGE_ENABLED = config('RECIPE_HUMAN_JUDGE_ENABLED', default=False, cast=bool)
RECIPE_HUMAN_JUDGE_MODEL = config('RECIPE_HUMAN_JUDGE_MODEL', default='claude-opus-4-8')

# --- 10. EMAIL BACKEND ---
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@dietplanner.app')

# --- 11. LOGGING ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'diet_planner': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'login_app': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'shopifyin': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}