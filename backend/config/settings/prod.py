"""Prod settings."""
from .base import *  # noqa: F401,F403
from .base import REPO_ROOT

DEBUG = False

SECURE_SSL_REDIRECT = False  # single-user on localhost; no HTTPS term in container
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Whitenoise serves built frontend
STATICFILES_DIRS = [REPO_ROOT / "frontend" / "dist"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

from apps.core.logging import configure_structlog  # noqa: E402

configure_structlog(dev=False)
