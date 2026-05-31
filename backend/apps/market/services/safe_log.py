"""Log-safe error summaries for providers that key-auth via the query string.

FRED, Twelve Data, Polygon and Marketaux pass their API key as a request *query
parameter*. A failed ``requests`` call raises an exception whose string form
embeds the full URL — including that key — so logging the bare exception would
leak the credential into the logs (the project forbids logging secrets; see
CLAUDE.md). ``safe_err`` returns a summary that never includes the URL: the
exception type plus, for HTTP errors, the response status code.
"""

from __future__ import annotations


def safe_err(exc: Exception) -> str:
    """Return a log-safe summary of ``exc`` that never echoes the request URL.

    e.g. ``"HTTPError status=429"`` or ``"ConnectionError"``. Use this instead of
    logging a raw ``requests`` exception whenever the API key rides in the URL.
    """
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    if status is not None:
        return f"{type(exc).__name__} status={status}"
    return type(exc).__name__
