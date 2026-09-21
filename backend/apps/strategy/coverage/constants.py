"""Coverage subdomain knobs."""

from __future__ import annotations

from django.conf import settings

# Whether an observer fire may open the FIRST house view on a ticker. With it off, a
# note only ever exists for names opened by hand, so the revision loop never starts
# on its own and a newly watched ticker stays uncovered forever. Override with
# ``COVERAGE_AUTO_CREATE_ENABLED`` in settings.
AUTO_CREATE_SETTING = "COVERAGE_AUTO_CREATE_ENABLED"
AUTO_CREATE_DEFAULT = True


def auto_create_enabled() -> bool:
    """Resolved auto-create switch: the Django setting, else :data:`AUTO_CREATE_DEFAULT`."""
    return bool(getattr(settings, AUTO_CREATE_SETTING, AUTO_CREATE_DEFAULT))
