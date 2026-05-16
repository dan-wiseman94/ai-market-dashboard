"""Token estimation + pruning for payload sections."""

from __future__ import annotations

from apps.ai.token_counter import estimate_tokens as _estimate

_PRUNE_ORDER = ["chain", "news", "ohlc", "breadth", "quotes", "positions"]


def estimate_tokens(text: str, *, provider: str = "openai", model: str = "") -> int:
    """Provider-aware estimate. Defaults preserve the old tiktoken behavior."""
    return _estimate(text, provider=provider, model=model)


def prune_to_budget(
    sections: dict[str, str],
    *,
    max_tokens: int,
    provider: str = "openai",
    model: str = "",
) -> tuple[dict[str, str], list[str]]:
    kept = dict(sections)
    pruned: list[str] = []
    sizes = {k: _estimate(v, provider=provider, model=model) for k, v in kept.items()}
    total = sum(sizes.values())

    for kind in _PRUNE_ORDER:
        if total <= max_tokens:
            break
        if kind in kept:
            del kept[kind]
            total -= sizes[kind]
            pruned.append(kind)

    return kept, pruned
