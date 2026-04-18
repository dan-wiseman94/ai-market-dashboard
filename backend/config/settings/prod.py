"""Prod settings."""
from .base import *
from .base import REPO_ROOT, env

DEBUG = False

# Prod: SPA served by Whitenoise from index.html; render route uses hash routing.
RENDER_BASE_URL = env("RENDER_BASE_URL", default="http://web:8000/static/index.html")

# Single-user on localhost; no HTTPS termination in container.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Whitenoise serves built frontend (dist is baked into the prod image).
STATICFILES_DIRS = [REPO_ROOT / "frontend" / "dist"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

from apps.core.logging import configure_structlog  # noqa: E402

configure_structlog(dev=False)
