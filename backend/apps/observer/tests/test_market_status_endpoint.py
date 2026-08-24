from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_market_status_endpoint_returns_expected_shape(api):
    fake = {"is_open": True, "next_open": None, "next_close": None}
    with patch("apps.observer.views.market_status", return_value=fake):
        resp = api.get("/api/observer/market-status/")
    assert resp.status_code == 200
    body = resp.json()
    assert "is_open" in body
    assert "next_open" in body
    assert "next_close" in body
