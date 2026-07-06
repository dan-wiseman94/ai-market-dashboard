"""Anthropic Files API proxy."""

from __future__ import annotations

import uuid

from anthropic import Anthropic
from cryptography.fernet import InvalidToken

from apps.ai.providers import client_kwargs
from apps.secrets.models import ProviderConfig


class NoKeyError(RuntimeError):
    pass


def _anthropic_client() -> Anthropic:
    try:
        cfg = ProviderConfig.objects.filter(provider="claude").first()
    except InvalidToken:
        cfg = None  # undecryptable key (key/salt rotation) → treat as not configured
    if cfg is None or not cfg.api_key:
        raise NoKeyError("No Claude API key configured")
    # client_kwargs applies the shared env-configured retry/timeout resilience
    # (AI_PROVIDER_MAX_RETRIES / AI_PROVIDER_TIMEOUT_SECONDS) — uploads are
    # bounded at 5MB (DATA_UPLOAD_MAX_MEMORY_SIZE), well within the timeout.
    return Anthropic(api_key=cfg.api_key, base_url=cfg.base_url or None, **client_kwargs())


def upload_to_anthropic(fileobj, filename: str, mime: str) -> tuple[str, int]:
    """Return (anthropic_file_id, size_bytes)."""
    from apps.core.mocks import is_mock_mode, run_service_scenario

    if is_mock_mode():
        run_service_scenario("files")  # files-upload-fail → raises before any upload
        # Unique per upload — UserFile.anthropic_id is unique=True, so a constant
        # would collide on a second mock upload.
        return f"mock-file-{uuid.uuid4().hex}", int(getattr(fileobj, "size", 0) or 0)

    client = _anthropic_client()
    f = client.beta.files.upload(file=(filename, fileobj, mime))
    return f.id, int(getattr(f, "size_bytes", 0) or 0)


def delete_from_anthropic(anthropic_id: str) -> None:
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return

    client = _anthropic_client()
    client.beta.files.delete(anthropic_id)
