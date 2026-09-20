"""TradingView connection endpoints under /api/schwab/data-sources/tradingview/."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.secrets.models import ApiCredential
from apps.secrets.tradingview_oauth import TradingViewOAuthError

BASE = "/api/schwab/data-sources/tradingview"
FLOW = {"client_id": "cid", "client_secret": "", "code_verifier": "v"}
TOKEN = {"access_token": "A", "refresh_token": "R", "expires_at": 9999999999, "client_id": "cid"}


@pytest.mark.django_db
def test_authorize_returns_url(api):
    with patch(
        "apps.secrets.views.tv_build_authorize_url", return_value="https://tv/authorize?x=1"
    ):
        r = api.get(f"{BASE}/authorize/")
    assert r.status_code == 200
    assert r.json() == {"url": "https://tv/authorize?x=1"}


@pytest.mark.django_db
def test_authorize_registration_failure_is_502_with_safe_message(api):
    with patch(
        "apps.secrets.views.tv_build_authorize_url",
        side_effect=TradingViewOAuthError(
            "TradingView rejected the client registration (HTTP 400): loopback not allowed"
        ),
    ):
        r = api.get(f"{BASE}/authorize/")
    assert r.status_code == 502
    assert r.json()["code"] == "tradingview_registration_failed"
    assert "loopback not allowed" in r.json()["message"]


@pytest.mark.django_db
@override_settings(FRONTEND_BASE_URL="http://localhost:5173")
def test_callback_denied_redirects_with_denied_flag(api):
    r = api.get(f"{BASE}/callback/?error=access_denied&state=s")
    assert r.status_code == 302
    assert r["Location"] == "http://localhost:5173/settings?tradingview=denied"


@pytest.mark.django_db
def test_callback_missing_code_400(api):
    r = api.get(f"{BASE}/callback/?state=s")
    assert r.status_code == 400
    assert r.json()["code"] == "missing_code"


@pytest.mark.django_db
def test_callback_invalid_state_400_and_no_exchange(api):
    with (
        patch("apps.secrets.views.tv_consume_oauth_state", return_value=None),
        patch("apps.secrets.views.tv_exchange_code") as ex,
    ):
        r = api.get(f"{BASE}/callback/?code=C&state=bad")
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_state"
    ex.assert_not_called()


@pytest.mark.django_db
def test_callback_exchange_failure_502(api):
    with (
        patch("apps.secrets.views.tv_consume_oauth_state", return_value=FLOW),
        patch("apps.secrets.views.tv_exchange_code", side_effect=TradingViewOAuthError("down")),
    ):
        r = api.get(f"{BASE}/callback/?code=C&state=ok")
    assert r.status_code == 502
    assert r.json()["code"] == "oauth_exchange_failed"


@pytest.mark.django_db
@override_settings(FRONTEND_BASE_URL="http://localhost:5173")
def test_callback_success_persists_and_redirects(api):
    with (
        patch("apps.secrets.views.tv_consume_oauth_state", return_value=FLOW),
        patch("apps.secrets.views.tv_exchange_code", return_value=dict(TOKEN)) as ex,
    ):
        r = api.get(f"{BASE}/callback/?code=C&state=ok")
    ex.assert_called_once_with("C", FLOW)
    assert r.status_code == 302
    assert r["Location"] == "http://localhost:5173/settings?tradingview=connected"
    assert ApiCredential.objects.get(provider="tradingview").token["access_token"] == "A"


@pytest.mark.django_db
def test_callback_under_mock_skips_state_check(api):
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        r = api.get(f"{BASE}/callback/?code=MOCK_OAUTH&state=mock")
    assert r.status_code == 302
    assert ApiCredential.objects.filter(provider="tradingview").exists()


@pytest.mark.django_db
def test_test_endpoint_delegates_to_probe(api):
    with patch(
        "apps.secrets.views.tv_probe",
        return_value={"ok": True, "message": "Connected — 3 tools available."},
    ):
        r = api.post(f"{BASE}/test/")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.django_db
def test_schwab_test_endpoint_still_not_key_managed(api):
    r = api.post("/api/schwab/data-sources/schwab/test/")
    assert r.status_code == 400
    assert r.json()["code"] == "not_key_managed"


@pytest.mark.django_db
def test_delete_disconnects(api):
    ApiCredential.objects.create(provider="tradingview", token=dict(TOKEN))
    with patch(
        "apps.secrets.views.tv_revoke_and_disconnect",
        side_effect=lambda: ApiCredential.objects.filter(provider="tradingview").delete(),
    ) as rev:
        r = api.delete(f"{BASE}/")
    rev.assert_called_once()
    assert r.status_code == 200
    assert r.json()["configured"] is False


@pytest.mark.django_db
def test_schwab_delete_still_rejected(api):
    r = api.delete("/api/schwab/data-sources/schwab/")
    assert r.status_code == 400
