"""Data-source credential API: /api/schwab/data-sources/."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.secrets.models import ApiCredential


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_list_reports_status(api):
    ApiCredential.objects.create(provider="alpaca", token={"api_key": "k", "api_secret": "s"})
    r = api.get("/api/schwab/data-sources/")
    assert r.status_code == 200
    by_provider = {d["provider"]: d for d in r.json()["data_sources"]}
    assert by_provider["alpaca"]["status"]["configured"] is True
    assert by_provider["alpaca"]["status"]["fields_present"] == ["api_key", "api_secret"]
    assert by_provider["fred"]["status"]["configured"] is False
    # keyless sources are always available
    assert by_provider["edgar"]["auth"] == "none"
    assert by_provider["edgar"]["status"]["configured"] is True


@pytest.mark.django_db
def test_list_never_exposes_secret(api):
    ApiCredential.objects.create(provider="fred", token={"api_key": "SUPERSECRET"})
    r = api.get("/api/schwab/data-sources/")
    assert "SUPERSECRET" not in r.content.decode()


@pytest.mark.django_db
def test_put_saves_key(api):
    r = api.put("/api/schwab/data-sources/fred/", data={"api_key_write": "abc123"}, format="json")
    assert r.status_code == 200
    assert r.json()["configured"] is True
    assert ApiCredential.objects.get(provider="fred").token["api_key"] == "abc123"


@pytest.mark.django_db
def test_put_partial_update_preserves_secret(api):
    ApiCredential.objects.create(provider="alpaca", token={"api_key": "old", "api_secret": "sec"})
    # Rotate only the key; a blank/absent secret leaves the stored one untouched.
    r = api.put("/api/schwab/data-sources/alpaca/", data={"api_key_write": "new"}, format="json")
    assert r.status_code == 200
    cred = ApiCredential.objects.get(provider="alpaca")
    assert cred.token["api_key"] == "new"
    assert cred.token["api_secret"] == "sec"


@pytest.mark.django_db
def test_put_missing_key_400(api):
    r = api.put("/api/schwab/data-sources/fred/", data={}, format="json")
    assert r.status_code == 400
    assert r.json()["code"] == "missing_key"


@pytest.mark.django_db
def test_delete_clears_key(api):
    ApiCredential.objects.create(provider="fred", token={"api_key": "k"})
    r = api.delete("/api/schwab/data-sources/fred/")
    assert r.status_code == 200
    assert r.json()["configured"] is False
    assert not ApiCredential.objects.filter(provider="fred").exists()


@pytest.mark.django_db
def test_put_keyless_source_rejected(api):
    r = api.put("/api/schwab/data-sources/edgar/", data={"api_key_write": "x"}, format="json")
    assert r.status_code == 400
    assert r.json()["code"] == "not_key_managed"


@pytest.mark.django_db
def test_unknown_provider_404(api):
    r = api.put("/api/schwab/data-sources/nope/", data={"api_key_write": "x"}, format="json")
    assert r.status_code == 404


# --- "Test key" endpoint + probe -------------------------------------------


@pytest.mark.django_db
def test_test_endpoint_returns_probe_result(api):
    with patch(
        "apps.secrets.views.test_credential", return_value={"ok": True, "message": "Key works."}
    ) as m:
        r = api.post("/api/schwab/data-sources/fred/test/")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "message": "Key works."}
    m.assert_called_once_with("fred")


@pytest.mark.django_db
def test_test_endpoint_keyless_400(api):
    r = api.post("/api/schwab/data-sources/edgar/test/")
    assert r.status_code == 400
    assert r.json()["code"] == "not_key_managed"


@pytest.mark.django_db
def test_test_endpoint_unknown_404(api):
    r = api.post("/api/schwab/data-sources/nope/test/")
    assert r.status_code == 404


@pytest.mark.django_db
def test_test_credential_mock_mode_short_circuits():
    from apps.secrets.data_source_test import test_credential

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        assert test_credential("fred")["ok"] is True


@pytest.mark.django_db
def test_test_credential_no_cred_saved():
    from apps.secrets.data_source_test import test_credential

    with patch("apps.core.mocks.is_mock_mode", return_value=False):
        result = test_credential("fred")
    assert result["ok"] is False
    assert "No credential" in result["message"]


@pytest.mark.django_db
def test_test_credential_classifies_status_codes():
    from apps.secrets import data_source_test as mod

    ApiCredential.objects.create(provider="fred", token={"api_key": "k"})
    ApiCredential.objects.create(provider="finnhub", token={"api_key": "k"})
    with patch("apps.core.mocks.is_mock_mode", return_value=False):
        with patch.dict(mod._PROBES, {"fred": lambda _t: SimpleNamespace(status_code=401)}):
            rejected = mod.test_credential("fred")
        with patch.dict(mod._PROBES, {"finnhub": lambda _t: SimpleNamespace(status_code=200)}):
            ok = mod.test_credential("finnhub")
    assert rejected["ok"] is False
    assert "rejected" in rejected["message"].lower()
    assert ok["ok"] is True
