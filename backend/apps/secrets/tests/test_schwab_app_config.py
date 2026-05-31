"""Schwab app credentials (client_id + secret) configured via the UI, encrypted at rest."""

import json

import pytest
from django.test import Client, override_settings

from apps.secrets.models import SchwabAppConfig
from apps.secrets.schwab_oauth import (
    SchwabNotConfigured,
    build_authorize_url,
    schwab_app_credentials,
)

AUTHORIZE_SETTINGS = {
    "SCHWAB_AUTHORIZE_URL": "https://api.schwabapi.com/v1/oauth/authorize",
    "SCHWAB_CALLBACK_URL": "https://127.0.0.1:8000/api/schwab/callback",
}


@pytest.mark.django_db
def test_load_is_singleton_and_roundtrips_encrypted_values():
    cfg = SchwabAppConfig.load()
    cfg.client_id = "APPKEY"
    cfg.client_secret = "SECRET"
    cfg.save()

    again = SchwabAppConfig.load()
    assert again.pk == cfg.pk == 1
    assert again.client_id == "APPKEY"
    assert again.client_secret == "SECRET"


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="ENVID", SCHWAB_CLIENT_SECRET="ENVSEC")
def test_credentials_prefer_db_over_env():
    cfg = SchwabAppConfig.load()
    cfg.client_id = "DBID"
    cfg.client_secret = "DBSEC"
    cfg.save()
    assert schwab_app_credentials() == ("DBID", "DBSEC")


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="ENVID", SCHWAB_CLIENT_SECRET="ENVSEC")
def test_credentials_fall_back_to_env_when_db_blank():
    assert schwab_app_credentials() == ("ENVID", "ENVSEC")


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="", SCHWAB_CLIENT_SECRET="", **AUTHORIZE_SETTINGS)
def test_build_authorize_url_uses_db_credentials():
    cfg = SchwabAppConfig.load()
    cfg.client_id = "DBID"
    cfg.save()
    assert "client_id=DBID" in build_authorize_url()


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="", SCHWAB_CLIENT_SECRET="")
def test_build_authorize_url_raises_when_unconfigured():
    with pytest.raises(SchwabNotConfigured):
        build_authorize_url()


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="", SCHWAB_CLIENT_SECRET="")
def test_app_config_get_reports_unconfigured():
    response = Client().get("/api/schwab/app-config/")
    assert response.status_code == 200
    assert response.json() == {
        "client_id": "",
        "client_secret_present": False,
        "configured": False,
    }


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="", SCHWAB_CLIENT_SECRET="")
def test_app_config_patch_saves_and_does_not_echo_secret():
    response = Client().patch(
        "/api/schwab/app-config/",
        data=json.dumps({"client_id": "APPKEY", "client_secret_write": "SECRET"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"client_id": "APPKEY", "client_secret_present": True, "configured": True}
    assert "client_secret" not in body and "client_secret_write" not in body
    cfg = SchwabAppConfig.load()
    assert cfg.client_secret == "SECRET"  # persisted, write-only


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="", SCHWAB_CLIENT_SECRET="")
def test_app_config_patch_blank_secret_leaves_existing():
    cfg = SchwabAppConfig.load()
    cfg.client_secret = "OLD"
    cfg.save()
    Client().patch(
        "/api/schwab/app-config/",
        data=json.dumps({"client_id": "NEWID"}),
        content_type="application/json",
    )
    refreshed = SchwabAppConfig.load()
    assert refreshed.client_id == "NEWID"
    assert refreshed.client_secret == "OLD"  # unchanged when secret omitted
