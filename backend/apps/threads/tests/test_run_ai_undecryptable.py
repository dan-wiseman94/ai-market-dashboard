"""Regression: an undecryptable ProviderConfig key must fail the run cleanly.

If DJANGO_SECRET_KEY or /data/secret.salt changes after a provider key was saved,
the stored ciphertext can no longer be decrypted. The decryption happens lazily in
`EncryptedJSONField.from_db_value` during the ORM fetch, so `ProviderConfig.objects.get(...)`
raises `InvalidToken` deep inside `_resolve_run_config`. Before this fix that crashed the
Celery task with no user-visible feedback — the UI just hung after capturing a snapshot.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message


def _corrupt_stored_key(provider: str) -> None:
    """Overwrite the encrypted api_key column with bytes that aren't valid Fernet
    ciphertext, bypassing the field's encrypt-on-write path. Mirrors a real
    key/salt rotation, with no mocks. Table/column are literal (stable Meta names)
    so the raw SQL stays free of string interpolation; the asserts fail loudly if
    either is ever renamed."""
    assert ProviderConfig._meta.db_table == "secrets_providerconfig"
    assert ProviderConfig._meta.get_field("_api_key").column == "api_key"
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_providerconfig SET api_key = %s WHERE provider = %s",
            [b"not-valid-fernet-ciphertext", provider],
        )


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_undecryptable_provider_key_fails_run_gracefully():
    ProviderConfig.objects.create(provider="claude", default_model="claude-sonnet-4-6")
    _corrupt_stored_key("claude")

    p = TradingProfile.objects.create(
        name="P", style="x", default_provider="claude", default_model="claude-sonnet-4-6"
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    # Must NOT raise InvalidToken — returns a failure result like the no-key path.
    result = run_ai_on_message.delay(
        thread_id=t.id,
        user_message_id=u.id,
        override={"provider": "claude", "model": "claude-sonnet-4-6"},
    ).get(timeout=5)

    assert result["ok"] is False
    failed = Message.objects.filter(thread=t, role="assistant", status="failed").first()
    assert failed is not None, "expected a failed assistant message"
    # Actionable, decrypt-specific guidance pointing the user at Settings.
    assert "decrypt" in failed.error.lower()
    assert "settings" in failed.error.lower()
