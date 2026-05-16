"""Dev settings — debug on, permissive hosts."""

from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Pretty log output in dev
from apps.core.logging import configure_structlog  # noqa: E402

configure_structlog(dev=True)
