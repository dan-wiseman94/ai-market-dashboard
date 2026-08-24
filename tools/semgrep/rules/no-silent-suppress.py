# Test fixture for no-silent-suppress. Run: semgrep --test --config <dir>
import contextlib
import logging
from contextlib import suppress

log = logging.getLogger(__name__)


def _fixture(refresh_quotes):
    # ruleid: no-silent-suppress
    with contextlib.suppress(Exception):
        refresh_quotes()
    # ruleid: no-silent-suppress
    with suppress(Exception):
        refresh_quotes()
    # ruleid: no-silent-suppress
    with contextlib.suppress(BaseException):
        refresh_quotes()
    # ruleid: no-silent-suppress
    with suppress(BaseException):
        refresh_quotes()
    # ok: no-silent-suppress
    with contextlib.suppress(ValueError, TypeError):
        refresh_quotes()
    # ok: no-silent-suppress
    with suppress(FileNotFoundError):
        refresh_quotes()
    # ok: no-silent-suppress
    try:
        refresh_quotes()
    except Exception:
        log.warning("quote refresh failed", exc_info=True)
