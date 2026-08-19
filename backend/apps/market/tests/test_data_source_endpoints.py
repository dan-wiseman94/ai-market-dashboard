"""Read endpoints for the new data dimensions: macro / filings / insider / treasury."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_macro_endpoint(api):
    fixture = {"DGS10": {"label": "10Y yield", "value": 4.2, "date": "2026-05-30"}}
    with patch("apps.market.views.fetch_macro", return_value=fixture) as m:
        r = api.get("/api/market/macro/")
    assert r.status_code == 200
    assert r.json()["DGS10"]["value"] == 4.2
    m.assert_called_once_with(None)


@pytest.mark.django_db
def test_macro_endpoint_series_filter(api):
    with patch("apps.market.views.fetch_macro", return_value={}) as m:
        api.get("/api/market/macro/?series=cpiaucsl,dgs10")
    m.assert_called_once_with(["CPIAUCSL", "DGS10"])


@pytest.mark.django_db
def test_filings_endpoint_keyed_by_ticker(api):
    with patch("apps.market.views.fetch_filings", return_value=[{"form": "10-K", "url": "u"}]) as m:
        r = api.get("/api/market/filings/?tickers=AAPL,MSFT")
    assert r.status_code == 200
    body = r.json()
    assert body["AAPL"][0]["form"] == "10-K"
    assert "MSFT" in body
    assert m.call_count == 2


@pytest.mark.django_db
def test_filings_missing_tickers_400(api):
    r = api.get("/api/market/filings/")
    assert r.status_code == 400
    assert r.json()["code"] == "missing_tickers"


@pytest.mark.django_db
def test_insider_endpoint(api):
    with patch("apps.market.views.fetch_insider", return_value=[{"accession": "x"}]):
        r = api.get("/api/market/insider/?tickers=AAPL")
    assert r.status_code == 200
    assert r.json()["AAPL"][0]["accession"] == "x"


@pytest.mark.django_db
def test_insider_missing_tickers_400(api):
    r = api.get("/api/market/insider/")
    assert r.status_code == 400


@pytest.mark.django_db
def test_treasury_endpoint(api):
    with patch("apps.market.views.fetch_treasury", return_value={"rates": {"x": 1.0}, "debt": {}}):
        r = api.get("/api/market/treasury/")
    assert r.status_code == 200
    assert r.json()["rates"]["x"] == 1.0
