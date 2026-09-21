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
    "channels",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "django_celery_beat",
    "django_structlog",
    "apps.core",
    "apps.secrets",
    "apps.market",
    "apps.profiles",
    "apps.snapshots",
    "apps.threads",
    "apps.ai",
    "apps.analytics",
    "apps.observer",
    "apps.backups",
    "apps.export",
    "apps.thesis",
    "apps.recall",
    "apps.book",
    "apps.strategy",
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

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/2")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
OBSERVER_BEAT_TIMEZONE = env("OBSERVER_BEAT_TIMEZONE", default="UTC")
TRIGGER_TICK_SECONDS = env.int("TRIGGER_TICK_SECONDS", default=10)
# Observer response cache: reuse a recent prior observation when a fire's
# assembled prompt is byte-identical (e.g. a quiet/closed market with mode=diff),
# instead of paying for another AI call. ON by default; a pure cost saving that
# never changes what a fresh prompt produces. Toggle in Settings → Features.
OBSERVER_RESPONSE_CACHE_ENABLED = env.bool("OBSERVER_RESPONSE_CACHE_ENABLED", default=True)
OBSERVER_RESPONSE_CACHE_TTL_SECONDS = env.int("OBSERVER_RESPONSE_CACHE_TTL_SECONDS", default=1800)
# Thesis post-mortem horizons in days; run_due_postmortems schedules an AI replay at each.
THESIS_POSTMORTEM_HORIZONS: list[int] = [7, 30, 90]

# Corporate-action adjustment: stock splits are ALWAYS adjusted in the returns
# math (a split is a non-event for the holder, so an unadjusted return is wrong).
# Dividends are different — adding them back converts price-return to total-return.
# This one stays OFF by default even though every other feature ships ON, because it
# is RETROACTIVE: it restates every post-mortem, Scorecard and Mirror number already
# computed under price-return, so defaulting it on mixes two methodologies inside one
# recorded history. It is fully UI-toggleable behind a confirm step (Settings →
# Features), which is where a deliberate switch to total-return belongs.
# See apps.market.returns.
RETURNS_ADJUST_DIVIDENDS = env.bool("RETURNS_ADJUST_DIVIDENDS", default=False)

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATIC_ROOT = REPO_ROOT / "staticfiles"
STATICFILES_DIRS = (
    [REPO_ROOT / "frontend" / "dist"] if (REPO_ROOT / "frontend" / "dist").exists() else []
)

# Raw-bytes uploads (snapshot client captures): the single knob for the upload cap.
# apps.snapshots.services.screenshot.MAX_BYTES derives from this setting, so the
# view-level size check stays aligned with Django's body-buffer guard and oversized
# PNGs produce a structured 413 rather than Django's bare 400 RequestDataTooBig.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Snapshot image bytes are written here (on the persistent app_data:/data volume)
# instead of into Postgres, keeping pg_dump small. See apps.snapshots.image_store.
SNAPSHOT_IMAGE_DIR = env.str("SNAPSHOT_IMAGE_DIR", default="/data/images")

# No throttling by design — single-user, 127.0.0.1-bound, AllowAny app (security model
# is network isolation, not auth; see CLAUDE.md). Mirrors the csrf-exempt /
# insecure-websocket rules already excluded in .github/workflows/semgrep.yml.
REST_FRAMEWORK = {  # nosemgrep
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # No auth by design (network isolation is the security model) — DRF's default
    # Session/Basic classes otherwise advertise a basicAuth scheme in the OpenAPI
    # schema for auth the API doesn't actually perform.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
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
    # A choice set reached by more than one serializer — or whose field name is
    # shared with a different choice set elsewhere — otherwise gets a hash-suffixed
    # component name (KindC68Enum, Status95aEnum, …). Those hashes churn whenever an
    # unrelated enum is added, and every churn rewrites frontend/src/api/schema.d.ts,
    # so pin each one by hand. Keyed by the choice set, not the field: two fields
    # with identical (value, label) pairs share one name by design.
    "ENUM_NAME_OVERRIDES": {
        # Thread.kind is shared by ThreadSerializer + ThreadListSerializer.
        "ThreadKindEnum": "apps.threads.models.Thread.KIND_CHOICES",
        # bullish/bearish/neutral: DirectionalCall's set, reached by Thesis.direction
        # and AIPrediction.direction. Collides on "direction" with Position's
        # long/short.
        "DirectionalCallEnum": "apps.core.model_bases.DIRECTION_CHOICES",
        # manual/scheduled: BackupRecord.kind and EvalRun.source are the same set
        # under two field names, so they must share one component name.
        "ManualOrScheduledEnum": "apps.analytics.models.EvalRun.SOURCE",
        # Snapshot's own two — both field names collide with other models'.
        "SnapshotStatusEnum": "apps.snapshots.models.Snapshot.STATUS_CHOICES",
        "SnapshotSourceEnum": "apps.snapshots.models.Snapshot.SOURCE_CHOICES",
        # AIPrediction.status is now reached by the ledger-stats filter echo too.
        "AIPredictionStatusEnum": "apps.observer.models.AIPrediction.STATUSES",
    },
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

SCHWAB_CLIENT_ID = env("SCHWAB_CLIENT_ID", default="")
SCHWAB_CLIENT_SECRET = env("SCHWAB_CLIENT_SECRET", default="")
SCHWAB_CALLBACK_URL = env(
    "SCHWAB_CALLBACK_URL", default="https://127.0.0.1:8000/api/schwab/callback"
)
SCHWAB_AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"  # noqa: S105 (URL, not a secret)

# Env fallback for free data-source API keys (same DB-first/env-fallback contract as the
# SCHWAB_CLIENT_ID pair above; merge is per-field in apps.secrets.credentials.decrypt_token).
# Keys saved through Settings → Connections live in Postgres encrypted with the /data Fernet
# salt — `docker compose down -v` destroys both, while .env survives any stack rebuild.
DATA_SOURCE_ENV_KEYS = {
    "alpaca": {
        "api_key": env("ALPACA_API_KEY", default=""),
        "api_secret": env("ALPACA_API_SECRET", default=""),
    },
    "finnhub": {"api_key": env("FINNHUB_API_KEY", default="")},
    "tiingo": {"api_key": env("TIINGO_API_KEY", default="")},
    "twelvedata": {"api_key": env("TWELVEDATA_API_KEY", default="")},
    "polygon": {"api_key": env("POLYGON_API_KEY", default="")},
    "tradier": {"api_key": env("TRADIER_API_KEY", default="")},
    "fred": {"api_key": env("FRED_API_KEY", default="")},
    "marketaux": {"api_key": env("MARKETAUX_API_KEY", default="")},
}

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
# the run once on a secondary provider. ON by default; never retries mid-stream
# (after a token has streamed). The secondary uses its ProviderConfig.default_model.
# An empty AI_FAILOVER_PROVIDER means "no secondary configured" — the retry is then
# inert, so this is safe to arm before a second provider exists.
AI_FAILOVER_ENABLED = env.bool("AI_FAILOVER_ENABLED", default=True)
AI_FAILOVER_PROVIDER = env.str("AI_FAILOVER_PROVIDER", default="")

# Autonomous investigation: a trigger/observer fire can run a BOUNDED
# tool-using investigation instead of a single observation. Max tool rounds per
# run, then one tool-less concluding turn. The autonomous daily cap is a separate,
# lower ceiling that GATES autonomous runs against total provider spend today
# (0.0 = no separate gate; the provider's own daily cap still applies).
AI_INVESTIGATION_MAX_ITERATIONS = env.int("AI_INVESTIGATION_MAX_ITERATIONS", default=8)
# 0.0 disables the separate autonomous gate entirely (only the provider's own daily
# cap then applies), so a real ceiling is the safer default for background spend.
AI_AUTONOMOUS_DAILY_CAP_USD = env.float("AI_AUTONOMOUS_DAILY_CAP_USD", default=5.0)

# Chat tool-loop ceiling: max tool rounds an ordinary (non-investigation) chat run may
# take before the provider must answer. Bounds a pathological tool loop's spend.
AI_CHAT_MAX_TOOL_ITERATIONS = env.int("AI_CHAT_MAX_TOOL_ITERATIONS", default=12)

# Offline eval harness — scheduled run. ON by default; bounded (25 rows / 30d horizon)
# and cost-cap pre-flighted. It calls the REAL model and run_structured has no
# MOCK_EXTERNAL short-circuit, so the beat entrypoint refuses under MOCK_EXTERNAL.
AIEVAL_SCHEDULED_ENABLED = env.bool("AIEVAL_SCHEDULED_ENABLED", default=True)

# Calibration-drift sentinel — daily notify when a model's calibration_error drifts.
# ON by default; reads EvalRuns only, no AI $. Notifies at most once per episode.
CALIBRATION_DRIFT_SENTINEL_ENABLED = env.bool("CALIBRATION_DRIFT_SENTINEL_ENABLED", default=True)

# Opt-in shared-token auth for the MCP-out server (/api/mcp/). Empty (default) keeps
# the app's 127.0.0.1/AllowAny posture; set it (and send `Authorization: Bearer <token>`)
# before exposing the MCP endpoint to external agents beyond localhost.
MCP_AUTH_TOKEN = env.str("MCP_AUTH_TOKEN", default="")

# TradingView's official MCP server. The client only ever talks to this URL (the OAuth
# metadata URLs derive from it), so no user input reaches a request URL. The callback
# must be reachable by the browser after consent — in dev that's the Caddy tls-proxy.
TRADINGVIEW_MCP_URL = env.str("TRADINGVIEW_MCP_URL", default="https://mcp.tradingview.com/mcp")
TRADINGVIEW_CALLBACK_URL = env.str(
    "TRADINGVIEW_CALLBACK_URL",
    default="https://127.0.0.1:8000/api/schwab/data-sources/tradingview/callback/",
)
# Expose the read-only tv_* TradingView tools to the in-app AI. Env default behind the
# SystemSettings.tradingview_tools_enabled UI override. ON by default; exposure also
# requires a connected TradingView, so this is inert until the user connects one.
TRADINGVIEW_TOOLS_ENABLED = env.bool("TRADINGVIEW_TOOLS_ENABLED", default=True)

# Calibration-weighted routing: when ON, the provider/model FALLBACK (no per-send
# override, no profile pin) picks the best-MEASURED enabled model from the eval
# harness instead of the first ProviderConfig by id. Per-send overrides and profile
# pins still win. ON by default; the min decisive-call floor + recency window below
# mean a stale or thin eval never pins routing, so it degrades to the plain fallback.
AI_CALIBRATION_ROUTING_ENABLED = env.bool("AI_CALIBRATION_ROUTING_ENABLED", default=True)

# Anomaly-sweep / Desk: when ON, the beat-scheduled sweep scans watched tickers for
# anomalies and auto-originates DeskEntry investigations. ON by default; autonomous
# spend is bounded by the cost caps inside investigate(), and the beat entrypoint
# refuses under MOCK_EXTERNAL so CI never bills it.
ANOMALY_SWEEP_ENABLED = env.bool("ANOMALY_SWEEP_ENABLED", default=True)

# AI prose on top of the deterministic daily regime/book readings. The numbers are
# computed either way; off drops only the paragraph (and its per-run model spend).
REGIME_NARRATIVE_ENABLED = env.bool("REGIME_NARRATIVE_ENABLED", default=True)
BOOK_NARRATIVE_ENABLED = env.bool("BOOK_NARRATIVE_ENABLED", default=True)
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
# Append-only strategy/book time-series — generous windows; the latest row of each is
# always recent (regime refreshes every ~30 min in market hours), so old rows are pure
# history. WarRoomRun / CoverageRevision / AIRun / TriggerFiring / EvalRun are kept
# (load-bearing audit/cost trails) and intentionally NOT pruned.
AI_RETENTION_REGIME_DAYS = env.int("AI_RETENTION_REGIME_DAYS", default=180)
AI_RETENTION_DESK_DAYS = env.int("AI_RETENTION_DESK_DAYS", default=180)
AI_RETENTION_BOOK_DAYS = env.int("AI_RETENTION_BOOK_DAYS", default=365)

# Restore-from-backup as a UI action (apps.backups): a restore overwrites the live
# database with a dump, so it is the one destructive button in the app. ON by
# default — a single-user desktop dashboard should be able to undo itself — and
# switchable off from Settings → Features for anyone who wants `make restore` to be
# the only path.
RESTORE_FROM_UI_ENABLED = env.bool("RESTORE_FROM_UI_ENABLED", default=True)

# Logging: handled by apps.core.logging.configure_structlog, called from dev/prod settings.
# We intentionally leave LOGGING at Django's default and reconfigure structlog imperatively.

# Error visibility (opt-in): initializes ONLY when SENTRY_DSN is set. An empty DSN
# (the default) is a complete no-op — nothing is imported-and-run that phones home,
# nothing transmits. Captures the warn-and-continue / _safe() swallow points (see
# apps.analytics.dashboard, apps.thesis.services.postmortem) so silent degradation is visible
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
