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
    "drf_spectacular",
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
    "apps.predictions",
    "apps.lessons",
    "apps.coverage",
    "apps.regime",
    "apps.book",
    "apps.warroom",
    "apps.desk",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RejectNullBytesMiddleware",
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
# Observer response cache (C2): reuse a recent prior observation when a fire's
# assembled prompt is byte-identical (e.g. a quiet/closed market with mode=diff),
# instead of paying for another AI call. OFF by default; opt-in cost lever.
OBSERVER_RESPONSE_CACHE_ENABLED = env.bool("OBSERVER_RESPONSE_CACHE_ENABLED", default=False)
OBSERVER_RESPONSE_CACHE_TTL_SECONDS = env.int("OBSERVER_RESPONSE_CACHE_TTL_SECONDS", default=1800)
# M11 — Thesis post-mortem horizons in days. Phase 2 will schedule AI replays at each.
THESIS_POSTMORTEM_HORIZONS: list[int] = [7, 30, 90]

# Corporate-action adjustment (C3): stock splits are ALWAYS adjusted in the returns
# math (a split is a non-event for the holder, so an unadjusted return is wrong).
# Dividends are different — adding them back converts price-return to total-return,
# a semantic change — so they're opt-in here. OFF by default; see apps.market.returns.
RETURNS_ADJUST_DIVIDENDS = env.bool("RETURNS_ADJUST_DIVIDENDS", default=False)

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

# Snapshot image bytes are written here (on the persistent app_data:/data volume)
# instead of into Postgres, keeping pg_dump small (C7). See apps.snapshots.image_store.
SNAPSHOT_IMAGE_DIR = env.str("SNAPSHOT_IMAGE_DIR", default="/data/images")

# DRF
# No throttling by design — single-user, 127.0.0.1-bound, AllowAny app (security model
# is network isolation, not auth; see CLAUDE.md). Mirrors the csrf-exempt /
# insecure-websocket rules already excluded in .github/workflows/semgrep.yml.
REST_FRAMEWORK = {  # nosemgrep
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Map malformed-client-input exceptions (non-integer path ids, NUL bytes, etc.) that
    # reach the ORM to 400 instead of letting them escape as 500s. See apps.core.exceptions.
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Ledger API",
    "DESCRIPTION": "Single-user AI trading dashboard — internal API.",
    "VERSION": "0.4.0",
    "SERVE_INCLUDE_SCHEMA": False,
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

# SEC EDGAR requires a descriptive User-Agent ("name email") on every request; this is
# the keyless identifier the edgar service sends. Override with a real contact in prod.
SEC_EDGAR_USER_AGENT = env(
    "SEC_EDGAR_USER_AGENT", default="ai-dashboard research contact@example.com"
)

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

# Autonomous investigation (M14 F1): a trigger/observer fire can run a BOUNDED
# tool-using investigation instead of a single observation. Max tool rounds per
# run, then one tool-less concluding turn. The autonomous daily cap is a separate,
# lower ceiling that GATES autonomous runs against total provider spend today
# (0.0 = no separate gate; the provider's own daily cap still applies).
AI_INVESTIGATION_MAX_ITERATIONS = env.int("AI_INVESTIGATION_MAX_ITERATIONS", default=8)
AI_AUTONOMOUS_DAILY_CAP_USD = env.float("AI_AUTONOMOUS_DAILY_CAP_USD", default=0.0)

# Offline eval harness — scheduled run. OFF by default: it calls the REAL model
# ($) and run_structured has no MOCK_EXTERNAL short-circuit. Enable deliberately.
AIEVAL_SCHEDULED_ENABLED = env.bool("AIEVAL_SCHEDULED_ENABLED", default=False)

# Calibration-weighted routing (M14 F2/F6, opt-in): when ON, the provider/model
# FALLBACK (no per-send override, no profile pin) picks the best-MEASURED enabled
# model from the eval harness instead of the first ProviderConfig by id. Per-send
# overrides and profile pins still win. Gated by a min decisive-call floor + a
# recency window so a stale or thin eval never pins routing.
AI_CALIBRATION_ROUTING_ENABLED = env.bool("AI_CALIBRATION_ROUTING_ENABLED", default=False)

# Anomaly-sweep / Desk (M15 F4, opt-in): when ON, the beat-scheduled sweep
# scans watched tickers for anomalies and auto-originates DeskEntry investigations.
ANOMALY_SWEEP_ENABLED = env.bool("ANOMALY_SWEEP_ENABLED", default=False)
AUTONOMY_AUTO_EXECUTE = env.bool("AUTONOMY_AUTO_EXECUTE", default=False)
AI_CALIBRATION_ROUTING_MIN_SCORED = env.int("AI_CALIBRATION_ROUTING_MIN_SCORED", default=5)
AI_CALIBRATION_ROUTING_MAX_AGE_DAYS = env.int("AI_CALIBRATION_ROUTING_MAX_AGE_DAYS", default=30)
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

# Error visibility (opt-in): initializes ONLY when SENTRY_DSN is set. An empty DSN
# (the default) is a complete no-op — nothing is imported-and-run that phones home,
# nothing transmits. Captures the warn-and-continue / _safe() swallow points (see
# apps.dashboard, apps.thesis.services.postmortem) so silent degradation is visible
# once a DSN is configured. sentry_sdk.capture_exception() at those sites is itself a
# no-op while uninitialized.
SENTRY_DSN = env.str("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        send_default_pii=False,
        environment=env.str("SENTRY_ENVIRONMENT", default="dev"),
    )
