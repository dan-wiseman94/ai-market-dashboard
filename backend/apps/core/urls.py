"""Core app URL routes."""

from __future__ import annotations

import os

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("ready/", views.ready, name="ready"),
    path("errors/", views.ErrorEventListView.as_view(), name="error-list"),
    path("errors/<int:pk>/resolve/", views.ErrorEventResolveView.as_view(), name="error-resolve"),
]

if os.environ.get("MOCK_EXTERNAL", "").lower() in ("1", "true", "yes"):
    urlpatterns += [
        path("_scenario_probe/", views.scenario_probe, name="scenario-probe"),
        path("_mock_ping_claude/", views.mock_ping_claude, name="mock-ping-claude"),
    ]
