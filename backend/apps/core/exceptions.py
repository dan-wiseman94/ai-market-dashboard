"""DRF exception handling."""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DataError
from django.db.models import ProtectedError, RestrictedError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

log = logging.getLogger(__name__)

# Exceptions that mean "the client sent malformed input that reached the ORM/DB" rather
# than a genuine server fault: a non-integer path id (ValueError "Field 'id' expected a
# number"), a NUL byte hitting a Postgres text column (DataError), etc. Without this they
# escape DRF's default handler as 500s (surfaced by the schemathesis fuzz lane).
_BAD_INPUT = (ValueError, TypeError, DjangoValidationError, DataError)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, ProtectedError | RestrictedError):
        # Delete blocked by a PROTECT/RESTRICT FK (e.g. a profile with snapshots/threads).
        log.warning("delete_conflict_409: %s", exc)
        return Response({"detail": "Cannot delete: still referenced by other objects."}, status=409)
    if isinstance(exc, _BAD_INPUT):
        log.warning("bad_input_400: %s: %s", type(exc).__name__, exc)
        return Response({"detail": "Invalid input."}, status=400)
    return None  # genuinely unhandled — let it surface as a 500
