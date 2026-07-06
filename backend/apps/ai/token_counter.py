"""Provider-aware token estimator.

Claude uses a different tokenizer than GPT. Calling tiktoken.cl100k_base on
Claude text miscounts by ~15-25%. This module routes by provider:
- claude: Anthropic SDK count_tokens endpoint (network call; result cached)
- openai / local / unknown: tiktoken.cl100k_base (local, fast)
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict

import tiktoken

log = logging.getLogger(__name__)

_ENC = tiktoken.get_encoding("cl100k_base")

# LRU of count results keyed by (sha256(text), model) — never the text itself.
# Inputs are full serialized snapshot sections (up to 150k+ tokens per the
# catalog budgets); keying on the raw strings would pin up to 1024 of them in
# long-lived worker/web processes. The count is the only thing worth keeping.
_COUNT_CACHE: OrderedDict[tuple[str, str], int] = OrderedDict()
_COUNT_CACHE_MAX = 1024
_COUNT_CACHE_LOCK = threading.Lock()


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


def _claude_count_tokens(text: str, model: str) -> int:
    """Anthropic count_tokens with a hash-keyed LRU so a repeated identical
    chunk doesn't hit the network twice. The network call runs outside the
    cache lock — only the (hash, count) bookkeeping is locked."""
    key = (hashlib.sha256(text.encode()).hexdigest(), model)
    with _COUNT_CACHE_LOCK:
        if key in _COUNT_CACHE:
            _COUNT_CACHE.move_to_end(key)
            return _COUNT_CACHE[key]

    count = _claude_count_tokens_api(text, model)

    with _COUNT_CACHE_LOCK:
        _COUNT_CACHE[key] = count
        _COUNT_CACHE.move_to_end(key)
        while len(_COUNT_CACHE) > _COUNT_CACHE_MAX:
            _COUNT_CACHE.popitem(last=False)
    return count


def _claude_count_tokens_api(text: str, model: str) -> int:
    """Uncached: call Anthropic count_tokens (tiktoken when no usable key)."""
    from anthropic import Anthropic

    from apps.ai.providers._config import client_kwargs
    from apps.secrets.models import ProviderConfig

    cfg = ProviderConfig.objects.filter(provider="claude").first()
    if cfg is None or not cfg.api_key:
        return len(_ENC.encode(text))

    client = Anthropic(api_key=cfg.api_key, **client_kwargs())
    resp = client.messages.count_tokens(
        model=model,
        messages=[{"role": "user", "content": text}],
    )
    return int(resp.input_tokens)
