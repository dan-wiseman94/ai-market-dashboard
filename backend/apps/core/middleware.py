"""Core request middleware."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse


def _has_nul(value: Any) -> bool:
    """True if a decoded JSON value contains a NUL char anywhere."""
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(k) or _has_nul(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_nul(item) for item in value)
    return False


class RejectNullBytesMiddleware:
    """Reject requests carrying NUL (0x00) bytes with a 400 instead of a 500.

    PostgreSQL text columns cannot store NUL bytes; Django passes user input straight
    to the driver, so a NUL in a path param, query string, header (e.g. a fuzzed
    Authorization header hitting DRF's default BasicAuthentication → a User lookup), or
    JSON body raises ``DataError`` deep in a query and surfaces as a 500. NUL has no
    legitimate use in this API's text, so a 400 is correct. Caught by the schemathesis
    fuzz lane.

    JSON bodies are parsed and checked recursively — a fuzzer sends NUL as the escaped
    ``\\u0000``, which only becomes a real NUL char after JSON decoding. Binary uploads
    (snapshot PNGs legitimately contain NUL) use non-JSON content types and are skipped.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if "\x00" in request.path_info or "\x00" in request.META.get("QUERY_STRING", ""):
            return self._bad_request()

        for key, value in request.META.items():
            if key.startswith("HTTP_") and isinstance(value, str) and "\x00" in value:
                return self._bad_request()

        if request.META.get("CONTENT_TYPE", "").startswith("application/json"):
            try:
                body = request.body
            except Exception:  # body already consumed / streaming — let the view handle it
                body = b""
            if body:
                try:
                    parsed = json.loads(body)
                except ValueError:
                    parsed = None  # malformed JSON — the view's parser returns its own 400
                if parsed is not None and _has_nul(parsed):
                    return self._bad_request()

        return self.get_response(request)

    @staticmethod
    def _bad_request() -> JsonResponse:
        return JsonResponse({"detail": "Null bytes are not allowed."}, status=400)
