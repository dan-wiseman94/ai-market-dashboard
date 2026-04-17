from unittest.mock import patch

import pytest
from django.utils import timezone
from datetime import timedelta
from django.test import override_settings

from apps.secrets.models import ApiCredential
from apps.market.tasks import refresh_schwab_token


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
def test_refresh_triggers_when_near_expiry():
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A", "refresh_token": "OLD"},
        expires_at=timezone.now() + timedelta(minutes=2),  # <5 min
    )
    with patch("apps.market.tasks.refresh_token") as refresh, \
         patch("apps.market.tasks.persist_token") as persist:
        refresh.return_value = {"access_token": "NEW", "refresh_token": "NEW_R", "expires_at": 9999999999}
        result = refresh_schwab_token.delay().get(timeout=2)
    assert result == {"ok": True}
    refresh.assert_called_once_with("OLD")
    persist.assert_called_once()
