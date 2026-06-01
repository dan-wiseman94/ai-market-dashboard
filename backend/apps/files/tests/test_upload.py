"""POST /api/files/ uploads to Anthropic via the Files API and persists a UserFile row."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.secrets.models import ProviderConfig


@pytest.fixture
def claude_cfg(db):
    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


def test_upload_proxies_to_anthropic_and_persists_row(db, claude_cfg) -> None:
    from apps.files.models import UserFile

    fake_file = MagicMock(id="file_abc", size_bytes=1024)
    upload = SimpleUploadedFile("10k.pdf", b"%PDF-1.7\n...", content_type="application/pdf")
    with patch("apps.files.services._anthropic_client") as ac:
        ac.return_value.beta.files.upload.return_value = fake_file
        client = APIClient()
        resp = client.post(
            "/api/files/",
            data={"file": upload, "kind": "filing", "ticker": "AAPL"},
            format="multipart",
        )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["anthropic_id"] == "file_abc"
    assert body["kind"] == "filing"
    assert body["ticker"] == "AAPL"
    assert body["size"] == 1024
    assert UserFile.objects.count() == 1


def test_upload_without_provider_key_400(db) -> None:
    upload = SimpleUploadedFile("x.txt", b"hi", content_type="text/plain")
    client = APIClient()
    resp = client.post(
        "/api/files/",
        data={"file": upload},
        format="multipart",
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "no_key"


def test_upload_with_undecryptable_key_400(db) -> None:
    """An undecryptable Claude key (key/salt rotation) must surface as a clean no_key
    400, not a 500 from InvalidToken leaking out of the client builder."""
    from django.db import connection

    ProviderConfig.objects.create(provider="claude", enabled=True)
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_providerconfig SET api_key = %s WHERE provider = %s",
            [b"not-valid-fernet", "claude"],
        )
    upload = SimpleUploadedFile("x.txt", b"hi", content_type="text/plain")
    client = APIClient()
    resp = client.post("/api/files/", data={"file": upload}, format="multipart")
    assert resp.status_code == 400, resp.content
    assert resp.json()["code"] == "no_key"


def test_list_returns_rows_filtered_by_kind(db, claude_cfg) -> None:
    from apps.files.models import UserFile

    UserFile.objects.create(
        anthropic_id="f1",
        kind="filing",
        ticker="AAPL",
        mime="application/pdf",
        size=100,
    )
    UserFile.objects.create(
        anthropic_id="f2",
        kind="transcript",
        ticker="AAPL",
        mime="text/plain",
        size=200,
    )
    client = APIClient()
    resp = client.get("/api/files/?kind=filing")
    assert resp.status_code == 200
    rows = resp.json()["results"]
    assert len(rows) == 1
    assert rows[0]["anthropic_id"] == "f1"


def test_delete_removes_row_and_calls_api(db, claude_cfg) -> None:
    from apps.files.models import UserFile

    f = UserFile.objects.create(
        anthropic_id="f1",
        kind="filing",
        ticker="AAPL",
        mime="application/pdf",
        size=100,
    )
    with patch("apps.files.services._anthropic_client") as ac:
        client = APIClient()
        resp = client.delete(f"/api/files/{f.id}/")
    assert resp.status_code == 204
    assert UserFile.objects.count() == 0
    ac.return_value.beta.files.delete.assert_called_once_with("f1")
