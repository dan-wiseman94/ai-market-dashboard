"""Prod settings."""
import os

from .base import *
from .base import REPO_ROOT

DEBUG = False

# Prod: SPA served by Whitenoise from index.html; render route uses hash routing.
RENDER_BASE_URL = os.environ.get("RENDER_BASE_URL", "http://web:8000/static/index.html")

SECURE_SSL_REDIRECT = False  # single-user on localhost; no HTTPS term in container
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Whitenoise serves built frontend
STATICFILES_DIRS = [REPO_ROOT / "frontend" / "dist"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

from apps.core.logging import configure_structlog  # noqa: E402

configure_structlog(dev=False)
