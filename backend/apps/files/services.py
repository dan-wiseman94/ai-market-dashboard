"""Anthropic Files API proxy."""
from __future__ import annotations

from anthropic import Anthropic

from apps.secrets.models import ProviderConfig


class NoKeyError(RuntimeError):
    pass


def _anthropic_client() -> Anthropic:
    cfg = ProviderConfig.objects.filter(provider="claude").first()
    if cfg is None or not cfg.api_key:
        raise NoKeyError("No Claude API key configured")
    return Anthropic(api_key=cfg.api_key, base_url=cfg.base_url or None)


def upload_to_anthropic(fileobj, filename: str, mime: str) -> tuple[str, int]:
    """Return (anthropic_file_id, size_bytes)."""
    client = _anthropic_client()
    f = client.beta.files.upload(file=(filename, fileobj, mime))
    return f.id, int(getattr(f, "size_bytes", 0) or 0)


def delete_from_anthropic(anthropic_id: str) -> None:
    client = _anthropic_client()
    client.beta.files.delete(anthropic_id)
