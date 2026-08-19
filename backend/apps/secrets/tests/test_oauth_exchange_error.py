import logging
from unittest.mock import patch

import pytest
from django.test import Client


@pytest.mark.django_db
def test_callback_exchange_failure_scrubs_secret_and_logs(caplog):
    """A failed token exchange must not echo credential-bearing query params (httpx
    error strings embed the full request URL) in the 502 body — the raw detail belongs
    in the server log, with the traceback, for diagnosis."""
    import fakeredis

    fake = fakeredis.FakeStrictRedis()
    boom = RuntimeError("POST https://api.schwabapi.com/v1/oauth/token?token=SECRET failed")
    with (
        patch("apps.secrets.schwab_oauth._redis", lambda: fake),
        patch("apps.secrets.views.exchange_code_for_token", side_effect=boom),
        caplog.at_level(logging.WARNING, logger="apps.secrets.views"),
    ):
        from apps.secrets.schwab_oauth import new_oauth_state

        state = new_oauth_state()
        client = Client()
        response = client.get("/api/schwab/callback/", {"code": "abc", "state": state})

    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "oauth_exchange_failed"
    assert "SECRET" not in body["message"]
    assert "token=***" in body["message"]

    warned = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "code exchange failed" in r.getMessage()
    ]
    assert warned, "exchange failure must be logged server-side"
    assert warned[0].exc_info is not None  # traceback (with raw detail) stays in the log
