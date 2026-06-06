"""Pairwise daily-return correlation clustering over stored OHLCBar history.
Tickers with insufficient overlapping history are dropped (honest coverage)."""

from __future__ import annotations

from typing import Any

from apps.book import constants as C
from apps.market.models import OHLCBar


def _daily_returns(ticker: str, window: int) -> list[float]:
    closes = [
        float(c)
        for c in reversed(
            list(
                OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d")
                .order_by("-ts")
                .values_list("close", flat=True)[: window + 1]
            )
        )
    ]
    return [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes)) if closes[i - 1]]


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < C.CORR_MIN_BARS:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    return cov / (va**0.5 * vb**0.5)


def correlation_clusters(tickers: list[str]) -> list[dict]:
    rets = {t: _daily_returns(t, C.CORR_WINDOW) for t in {x.upper() for x in tickers}}
    rets = {t: r for t, r in rets.items() if len(r) >= C.CORR_MIN_BARS}
    names = sorted(rets)
    parent = {t: t for t in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pair_corr: dict[tuple[str, str], float] = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            c = _pearson(rets[names[i]], rets[names[j]])
            if c is not None and c >= C.CORR_THRESHOLD:
                pair_corr[(names[i], names[j])] = c
                parent[find(names[i])] = find(names[j])

    groups: dict[str, list[str]] = {}
    for t in names:
        groups.setdefault(find(t), []).append(t)

    out: list[dict[str, Any]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        cs = [v for (x, y), v in pair_corr.items() if x in members and y in members]
        out.append({"members": sorted(members), "avg_corr": (sum(cs) / len(cs)) if cs else None})
    out.sort(key=lambda g: len(g["members"]), reverse=True)
    return out
