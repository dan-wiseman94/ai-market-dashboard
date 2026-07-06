"""The Files-API proxy client must apply the shared env-configured resilience
kwargs (AI_PROVIDER_MAX_RETRIES / AI_PROVIDER_TIMEOUT_SECONDS) — it is the one
web-request Anthropic call site, so SDK defaults (600s timeout) would hang an
upload request for 10 minutes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.secrets.models import ProviderConfig


@pytest.mark.django_db
@override_settings(AI_PROVIDER_MAX_RETRIES=3, AI_PROVIDER_TIMEOUT_SECONDS=45.0)
def test_files_client_applies_resilience_kwargs() -> None:
    cfg = ProviderConfig.objects.create(provider="claude")
    cfg.api_key = "sk-ant-test"
    cfg.save()

    captured: dict = {}

    class _FakeAnthropic:
        def __init__(self, **kw):
            captured.update(kw)

    with patch("apps.threads.files_service.Anthropic", _FakeAnthropic):
        from apps.threads.files_service import _anthropic_client

        _anthropic_client()

    assert captured["max_retries"] == 3
    assert captured["timeout"] == 45.0
