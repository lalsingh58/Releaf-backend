"""
Django settings for ReLeaf.

All deployment-specific values come from environment variables (optionally
loaded from a local ``.env`` file). See ``.env.example`` for the full list.
"""
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from .env (if present). Real environment variables win.
load_dotenv(BASE_DIR / ".env")


# --------------------------------------------------------------------------- #
# Environment helpers
# --------------------------------------------------------------------------- #
def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key, default):
    return int(os.environ.get(key, default))


def env_float(key, default):
    return float(os.environ.get(key, default))


def env_list(key, default=""):
    return [item.strip() for item in os.environ.get(key, default).split(",") if item.strip()]


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        # Convenience for local development only.
        SECRET_KEY = "django-insecure-dev-only-key-do-not-use-in-production"
    else:
        raise ImproperlyConfigured(
            "The DJANGO_SECRET_KEY environment variable is required when DJANGO_DEBUG is off."
        )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # Local apps
    "apps.core",
    "apps.users",
    "apps.actions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # must be before CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if not DEBUG:
    # Serves admin/static files in production (run `collectstatic` on deploy).
    # In development `runserver` serves them itself.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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


# --------------------------------------------------------------------------- #
# Database: SQLite by default, PostgreSQL via DATABASE_URL
#   DATABASE_URL=postgres://user:password@host:5432/dbname
# --------------------------------------------------------------------------- #
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------- #
# Cache (AQI responses, community impact, DRF throttling)
# Uses Redis when REDIS_URL is set, otherwise per-process local memory.
# --------------------------------------------------------------------------- #
if env("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("REDIS_URL"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "releaf",
        }
    }


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --------------------------------------------------------------------------- #
# Internationalisation
# Streaks are counted per calendar day in TIME_ZONE, so set it to the region
# where most of your users live.
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True


# --------------------------------------------------------------------------- #
# Static & media files
# --------------------------------------------------------------------------- #
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Reject absurdly large uploads early (the validators enforce tighter limits).
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024


# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", DEBUG and not CORS_ALLOWED_ORIGINS)


# --------------------------------------------------------------------------- #
# Django REST Framework
# --------------------------------------------------------------------------- #
_renderers = ["rest_framework.renderers.JSONRenderer"]
if DEBUG:
    _renderers.append("rest_framework.renderers.BrowsableAPIRenderer")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": _renderers,
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", "60/min"),
        "user": env("THROTTLE_USER", "300/min"),
        "auth": env("THROTTLE_AUTH", "10/min"),  # register / login
        "submit": env("THROTTLE_SUBMIT", "30/hour"),  # action submissions
    },
}


# --------------------------------------------------------------------------- #
# JWT (djangorestframework-simplejwt)
# --------------------------------------------------------------------------- #
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 30)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "SIGNING_KEY": SECRET_KEY,
}


# --------------------------------------------------------------------------- #
# ReLeaf: domain settings
# --------------------------------------------------------------------------- #
# Open-Meteo air quality API (free, no API key)
OPEN_METEO_AIR_QUALITY_URL = env(
    "OPEN_METEO_AIR_QUALITY_URL", "https://air-quality-api.open-meteo.com/v1/air-quality"
)
OPEN_METEO_TIMEOUT = env_float("OPEN_METEO_TIMEOUT", 8)  # seconds
AQI_CACHE_SECONDS = env_int("AQI_CACHE_SECONDS", 600)
# US AQI at/above which the app should trigger a green action challenge.
AQI_CHALLENGE_THRESHOLD = env_int("AQI_CHALLENGE_THRESHOLD", 100)

# Points
POINTS_PER_ACTION = {"plant": 50, "water": 20}
# (minimum US AQI, bonus points) checked from highest to lowest; first match wins.
AQI_BONUS_POINTS = [(300, 30), (200, 20), (150, 15), (100, 10)]
MAX_ACTIONS_PER_DAY = env_int("MAX_ACTIONS_PER_DAY", 5)

# Photo proof rules
PROOF_MAX_SIZE_MB = env_float("PROOF_MAX_SIZE_MB", 5)
PROOF_MIN_DIMENSION = env_int("PROOF_MIN_DIMENSION", 200)  # px, shortest side
PROFILE_PICTURE_MAX_SIZE_MB = env_float("PROFILE_PICTURE_MAX_SIZE_MB", 3)
# True  -> proofs that pass basic validation are approved immediately.
# False -> proofs stay "pending" until approved in the Django admin.
PROOF_AUTO_APPROVE = env_bool("PROOF_AUTO_APPROVE", True)
# Dotted path of the proof verifier. Swap in a Google Cloud Vision based one later.
PROOF_VERIFIER = env("PROOF_VERIFIER", "apps.actions.verification.verify_proof_image")

# Rough estimate shown on the community impact endpoint (kg CO2 absorbed / tree / year).
CO2_KG_PER_TREE_PER_YEAR = 21.8
IMPACT_CACHE_SECONDS = env_int("IMPACT_CACHE_SECONDS", 300)


# --------------------------------------------------------------------------- #
# Security (production)
# --------------------------------------------------------------------------- #
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Uncomment when running behind a TLS-terminating proxy (nginx, load balancer):
    # SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
