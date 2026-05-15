# backend/apps/core/tests/test_spa_fallback.py
"""Prod SPA fallback: / serves index.html, /api/* still 404s, /static/* unaffected."""

from __future__ import annotations

import pytest
from django.test import Client, override_settings


@pytest.mark.django_db
@override_settings(DEBUG=False, ALLOWED_HOSTS=["*"])
def test_root_serves_spa_shell() -> None:
    client = Client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/html")
    assert b"<!doctype html>" in resp.content.lower() or b"<!DOCTYPE html>" in resp.content


@pytest.mark.django_db
@override_settings(DEBUG=False, ALLOWED_HOSTS=["*"])
def test_deep_link_serves_spa_shell() -> None:
    client = Client()
    resp = client.get("/triggers/42")
    assert resp.status_code == 200
    assert b"<!doctype html>" in resp.content.lower() or b"<!DOCTYPE html>" in resp.content


@pytest.mark.django_db
@override_settings(DEBUG=False, ALLOWED_HOSTS=["*"])
def test_unknown_api_still_404() -> None:
    client = Client()
    resp = client.get("/api/nonexistent-endpoint/")
    assert resp.status_code == 404
    # Not the SPA shell — SPA index.html contains "ai-dash"; Django's 404 does not.
    assert b"ai-dash" not in resp.content


@pytest.mark.django_db
@override_settings(DEBUG=False, ALLOWED_HOSTS=["*"])
def test_static_prefix_not_intercepted_by_spa_fallback() -> None:
    """/static/nonexistent.css must 404 via Whitenoise, not return the SPA shell."""
    client = Client()
    resp = client.get("/static/nonexistent-css-file.css")
    # Whitenoise returns 404 for missing static files in production; the SPA fallback
    # must NOT catch /static/* per our re_path negative lookahead.
    assert resp.status_code == 404
    assert b"ai-dash" not in resp.content
