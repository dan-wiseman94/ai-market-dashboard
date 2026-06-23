from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.market.tasks import refresh_schwab_token
from apps.secrets.models import ApiCredential


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_refresh_noops_when_not_connected():
    result = refresh_schwab_token.delay().get(timeout=2)
    assert result == {"ok": False, "reason": "not_connected"}


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_refresh_noops_when_fresh():
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A", "refresh_token": "R"},
        expires_at=timezone.now() + timedelta(hours=1),
    )
    result = refresh_schwab_token.delay().get(timeout=2)
    assert result == {"ok": False, "reason": "fresh"}


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_refresh_noops_when_token_undecryptable():
    """A credential encrypted under a now-gone key (secret rotated / salt reset) must
    degrade to a clean no-op, not raise InvalidToken on every beat tick."""
    from cryptography.fernet import Fernet
    from django.db import connection

    cred = ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A", "refresh_token": "R"},
        expires_at=timezone.now() + timedelta(minutes=2),
    )
    # Clobber the column with ciphertext from a foreign key the current Fernet can't read.
    foreign = Fernet(Fernet.generate_key()).encrypt(b'{"refresh_token":"R"}')
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_apicredential SET token = %s WHERE id = %s",
            [foreign, cred.id],
        )

    result = refresh_schwab_token.delay().get(timeout=2)
    assert result == {"ok": False, "reason": "undecryptable"}


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_refresh_degrades_and_marks_reconnect_when_refresh_rejected():
    """An expired/revoked refresh token (Schwab returns 400 invalid_grant) is
    unrecoverable by any automated refresh. The task must not raise an unhandled
    HTTPError every beat tick — degrade to a clean result AND record a cross-process
    auth-error marker so the connection status surfaces "reconnect needed"."""
    import fakeredis
    import httpx

    from apps.core import provider_health

    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A", "refresh_token": "DEAD"},
        expires_at=timezone.now() + timedelta(minutes=2),  # <5 min → triggers refresh
    )
    request = httpx.Request("POST", "https://api.schwabapi.com/v1/oauth/token")
    response = httpx.Response(400, request=request, json={"error": "invalid_grant"})
    fake = fakeredis.FakeStrictRedis()
    with (
        patch(
            "apps.market.tasks.refresh_token",
            side_effect=httpx.HTTPStatusError("400", request=request, response=response),
        ),
        patch("apps.core.provider_health._redis", lambda: fake),
    ):
        result = refresh_schwab_token.delay().get(timeout=2)
        assert result == {"ok": False, "reason": "refresh_rejected"}
        assert provider_health.auth_error("schwab") is not None


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_refresh_triggers_when_near_expiry():
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A", "refresh_token": "OLD"},
        expires_at=timezone.now() + timedelta(minutes=2),  # <5 min
    )
    with (
        patch("apps.market.tasks.refresh_token") as refresh,
        patch("apps.market.tasks.persist_token") as persist,
    ):
        refresh.return_value = {
            "access_token": "NEW",
            "refresh_token": "NEW_R",
            "expires_at": 9999999999,
        }
        result = refresh_schwab_token.delay().get(timeout=2)
    assert result == {"ok": True}
    refresh.assert_called_once_with("OLD")
    persist.assert_called_once()
