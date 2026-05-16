"""Provider-aware token estimator.

Claude uses a different tokenizer than GPT. Calling tiktoken.cl100k_base on
Claude text miscounts by ~15-25%. This module routes by provider:
- claude: Anthropic SDK count_tokens endpoint (network call; cached)
- openai / local / unknown: tiktoken.cl100k_base (local, fast)
"""

from __future__ import annotations

import logging
from functools import lru_cache

import tiktoken

log = logging.getLogger(__name__)

_ENC = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str, *, provider: str, model: str) -> int:
    if not text:
        return 0
    if provider == "claude":
        try:
            return _claude_count_tokens(text, model)
        except Exception as exc:
            log.warning("Claude count_tokens failed (%s); falling back to tiktoken", exc)
            return len(_ENC.encode(text))
    return len(_ENC.encode(text))


@lru_cache(maxsize=1024)
def _claude_count_tokens(text: str, model: str) -> int:
    """Call Anthropic count_tokens. Cached so repeated identical chunks (e.g.,
    the trading-style prompt across many snapshots) don't hit the network twice.
    """
    from anthropic import Anthropic

    from apps.secrets.models import ProviderConfig

    cfg = ProviderConfig.objects.filter(provider="claude").first()
    if cfg is None or not cfg.api_key:
        return len(_ENC.encode(text))

    client = Anthropic(api_key=cfg.api_key)
    resp = client.messages.count_tokens(
        model=model,
        messages=[{"role": "user", "content": text}],
    )
    return int(resp.input_tokens)
