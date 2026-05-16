"""ScenarioHeaderMiddleware — applied only when ``MOCK_EXTERNAL=true``.

Reads ``X-E2E-Scenario`` from each request, sets the ContextVar, processes the
response, then resets the ContextVar so the next request starts clean.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from apps.core.mocks import reset_scenario, set_scenario


class ScenarioHeaderMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        if not getattr(settings, "MOCK_EXTERNAL", False):
            return self.get_response(request)

        scenario = request.headers.get("X-E2E-Scenario", "default")
        set_scenario(scenario)
        try:
            return self.get_response(request)
        finally:
            reset_scenario()
