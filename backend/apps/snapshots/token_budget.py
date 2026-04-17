"""Token estimation + pruning for payload sections."""
from __future__ import annotations

import tiktoken


_ENC = tiktoken.get_encoding("cl100k_base")

_PRUNE_ORDER = ["chain", "news", "ohlc", "breadth", "quotes", "positions"]


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENC.encode(text))


def prune_to_budget(
    sections: dict[str, str],
    *,
    max_tokens: int,
) -> tuple[dict[str, str], list[str]]:
    kept = dict(sections)
    pruned: list[str] = []

    def total() -> int:
        return sum(estimate_tokens(v) for v in kept.values())

    for kind in _PRUNE_ORDER:
        if total() <= max_tokens:
            break
        if kind in kept:
            del kept[kind]
            pruned.append(kind)

    return kept, pruned
