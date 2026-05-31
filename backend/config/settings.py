import os
import socket
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "change-me-in-production")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "django_celery_beat",
    "apps.jobs.apps.JobsConfig",
    "apps.search.apps.SearchConfig",
    "apps.alerts.apps.AlertsConfig",
    "apps.tracking.apps.TrackingConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "jobs_db"),
        "USER": os.getenv("POSTGRES_USER", "jobs_user"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "jobs_password"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

# Tests use PostgreSQL (pgvector); run via: docker compose exec web python manage.py test

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = os.getenv("INGEST_SCHEDULE_TIMEZONE", "Europe/Istanbul")
CELERY_ENABLE_UTC = False

INGEST_SCHEDULE_HOUR = int(os.getenv("INGEST_SCHEDULE_HOUR", "3"))
INGEST_SCHEDULE_MINUTE = int(os.getenv("INGEST_SCHEDULE_MINUTE", "0"))
ALERT_SCHEDULE_HOUR = int(os.getenv("ALERT_SCHEDULE_HOUR", str(INGEST_SCHEDULE_HOUR + 1 if INGEST_SCHEDULE_HOUR < 23 else 0)))
ALERT_SCHEDULE_MINUTE = int(os.getenv("ALERT_SCHEDULE_MINUTE", "0"))

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "nightly-job-refresh": {
        "task": "apps.jobs.tasks.nightly_job_refresh_task",
        "schedule": crontab(
            hour=INGEST_SCHEDULE_HOUR,
            minute=INGEST_SCHEDULE_MINUTE,
        ),
    },
    "nightly-job-alerts": {
        "task": "apps.alerts.tasks.process_job_alerts_task",
        "schedule": crontab(
            hour=ALERT_SCHEDULE_HOUR,
            minute=ALERT_SCHEDULE_MINUTE,
        ),
    },
}

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers").strip().lower()
EMBEDDING_MODEL_NAME = (
    os.getenv("EMBEDDING_MODEL", "").strip()
    or os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2").strip()
)
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384"))
# When true, embedding failures do not fall back to hash / alternate providers.
EMBEDDING_STRICT_PROVIDER = os.getenv("EMBEDDING_STRICT_PROVIDER", "true").lower() == "true"
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "50"))
EMBEDDING_MAX_JOBS_PER_RUN = int(os.getenv("EMBEDDING_MAX_JOBS_PER_RUN", "100"))
EMBEDDING_SLEEP_SECONDS = float(os.getenv("EMBEDDING_SLEEP_SECONDS", "0.5"))
EMBEDDING_SOURCE_FILTER = os.getenv("EMBEDDING_SOURCE_FILTER", "").strip()
_emb_tech = os.getenv("EMBEDDING_TECH_ONLY", "").strip().lower()
EMBEDDING_TECH_ONLY = (
    True if _emb_tech in {"1", "true", "yes"} else False if _emb_tech in {"0", "false", "no"} else None
)
EMBEDDING_STOP_ON_QUOTA = os.getenv("EMBEDDING_STOP_ON_QUOTA", "true").lower() == "true"

SEMANTIC_SEARCH_CANDIDATE_POOL = int(os.getenv("SEMANTIC_SEARCH_CANDIDATE_POOL", "100"))
SEMANTIC_RERANK_WEIGHT_SEMANTIC = float(os.getenv("SEMANTIC_RERANK_WEIGHT_SEMANTIC", "0.7"))
SEMANTIC_RERANK_WEIGHT_LEXICAL = float(os.getenv("SEMANTIC_RERANK_WEIGHT_LEXICAL", "0.3"))
SEMANTIC_TECH_ONLY = os.getenv("SEMANTIC_TECH_ONLY", "true").lower() == "true"
SEMANTIC_REAL_SOURCES_ONLY = os.getenv("SEMANTIC_REAL_SOURCES_ONLY", "true").lower() == "true"
RANKING_WEIGHT_KEYWORD = float(os.getenv("RANKING_WEIGHT_KEYWORD", "0.5"))
RANKING_WEIGHT_SEMANTIC = float(os.getenv("RANKING_WEIGHT_SEMANTIC", "0.3"))
RANKING_WEIGHT_CLICK = float(os.getenv("RANKING_WEIGHT_CLICK", "0.2"))

# Prefer IPv4 for SMTP (Docker/DigitalOcean often has no IPv6 route).
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _ipv4_getaddrinfo

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@example.com")
ALERT_DEFAULT_EMAIL = os.getenv("ALERT_DEFAULT_EMAIL", "")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").strip()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
BREVO_API_TIMEOUT_SECONDS = int(os.getenv("BREVO_API_TIMEOUT_SECONDS", "30"))
