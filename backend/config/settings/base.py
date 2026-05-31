"""Base settings — shared between dev and prod."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # ai-dashboard/backend
REPO_ROOT = BASE_DIR.parent  # ai-dashboard

env = environ.Env()
environ.Env.read_env(REPO_ROOT / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # 3rd party
    "channels",
    "rest_framework",
    "corsheaders",
    "django_celery_beat",
    "django_structlog",
    # local
    "apps.core",
    "apps.secrets",
    "apps.market",
    "apps.profiles",
    "apps.snapshots",
    "apps.threads",
    "apps.triggers",
    "apps.ai",
    "apps.analytics",
    "apps.costs",
    "apps.observer",
    "apps.backups",
    "apps.export",
    "apps.files",
    "apps.thesis",
    "apps.briefing",
    "apps.recall",
    "apps.dashboard",
    "apps.aieval",
    "apps.portfolio",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_structlog.middlewares.RequestMiddleware",
]

# E2E scenario engine — only loaded when MOCK_EXTERNAL is on, never in prod.
MOCK_EXTERNAL = env.bool("MOCK_EXTERNAL", default=False)
if MOCK_EXTERNAL:
    MIDDLEWARE = [*MIDDLEWARE, "apps.core.mocks.middleware.ScenarioHeaderMiddleware"]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [REPO_ROOT / "frontend" / "dist"],
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="db"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
    }
}

# Redis / Channels
REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    },
}

# Encryption (apps.secrets): salt path for Fernet key derivation.
# The 32-byte random salt is generated on first access if missing.
# Losing this file permanently destroys stored credentials.
_ENCRYPTION_SALT_PATH = env.str("ENCRYPTION_SALT_PATH", default="/data/secret.salt")

# Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/2")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
OBSERVER_BEAT_TIMEZONE = env("OBSERVER_BEAT_TIMEZONE", default="UTC")
TRIGGER_TICK_SECONDS = env.int("TRIGGER_TICK_SECONDS", default=10)
# M11 — Thesis post-mortem horizons in days. Phase 2 will schedule AI replays at each.
THESIS_POSTMORTEM_HORIZONS: list[int] = [7, 30, 90]

# Auth / i18n / etc
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Static / media
STATIC_URL = "/static/"
STATIC_ROOT = REPO_ROOT / "staticfiles"
STATICFILES_DIRS = (
    [REPO_ROOT / "frontend" / "dist"] if (REPO_ROOT / "frontend" / "dist").exists() else []
)

# Raw-bytes uploads (snapshot client captures): align Django's body-buffer cap with
# apps.snapshots.services_image.MAX_BYTES so oversized PNGs produce a structured 413
# response from the view rather than Django's bare 400 RequestDataTooBig.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB

# DRF
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

# CORS (dev only — prod serves frontend same-origin)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ALLOW_CREDENTIALS = True

# Playwright server-side chart render base URL.
# Dev: hits the live Vite dev server (history-mode /render/chart route).
# Prod: hits the Whitenoise-served SPA bundle via hash routing.
RENDER_BASE_URL = env("RENDER_BASE_URL", default="http://frontend:5173")

# Schwab OAuth
SCHWAB_CLIENT_ID = env("SCHWAB_CLIENT_ID", default="")
SCHWAB_CLIENT_SECRET = env("SCHWAB_CLIENT_SECRET", default="")
SCHWAB_CALLBACK_URL = env(
    "SCHWAB_CALLBACK_URL", default="https://127.0.0.1:8000/api/schwab/callback"
)
SCHWAB_AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"

# Where the Schwab OAuth callback sends the browser after a successful connect.
# Dev: the Vite SPA on :5173 (the callback itself arrives via the tls-proxy on :8000).
# Prod: empty → same-origin relative redirect (SPA is served by web on :8000).
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="")

# AI provider resilience: bounded SDK retry (exponential backoff on 429/5xx) + read timeout.
AI_PROVIDER_MAX_RETRIES = env.int("AI_PROVIDER_MAX_RETRIES", default=2)
AI_PROVIDER_TIMEOUT_SECONDS = env.float("AI_PROVIDER_TIMEOUT_SECONDS", default=60.0)

# Cross-provider failover: if the primary errors BEFORE emitting any token, retry
# the run once on a secondary provider. OFF by default; never retries mid-stream
# (after a token has streamed). The secondary uses its ProviderConfig.default_model.
AI_FAILOVER_ENABLED = env.bool("AI_FAILOVER_ENABLED", default=False)
AI_FAILOVER_PROVIDER = env.str("AI_FAILOVER_PROVIDER", default="")

# Offline eval harness — scheduled run. OFF by default: it calls the REAL model
# ($) and run_structured has no MOCK_EXTERNAL short-circuit. Enable deliberately.
AIEVAL_SCHEDULED_ENABLED = env.bool("AIEVAL_SCHEDULED_ENABLED", default=False)
AIEVAL_SCHEDULED_MODEL = env.str("AIEVAL_SCHEDULED_MODEL", default="claude-sonnet-4-6")
AIEVAL_SCHEDULED_HORIZON = env.int("AIEVAL_SCHEDULED_HORIZON", default=30)
AIEVAL_SCHEDULED_LIMIT = env.int("AIEVAL_SCHEDULED_LIMIT", default=25)

# Retention windows for the daily prune_retention beat task (core.prune_retention).
# Generous defaults — these are standalone time-series / ephemera tables only.
# Load-bearing tables (Snapshot, Message, Thesis, AIRun, PostMortem, …) are NEVER pruned.
AI_RETENTION_OHLC_DAYS = env.int("AI_RETENTION_OHLC_DAYS", default=400)
AI_RETENTION_CHAIN_DAYS = env.int("AI_RETENTION_CHAIN_DAYS", default=120)
AI_RETENTION_NOTIFICATION_DAYS = env.int("AI_RETENTION_NOTIFICATION_DAYS", default=90)
AI_RETENTION_ERROR_DAYS = env.int("AI_RETENTION_ERROR_DAYS", default=90)

# Logging: handled by apps.core.logging.configure_structlog, called from dev/prod settings.
# We intentionally leave LOGGING at Django's default and reconfigure structlog imperatively.
