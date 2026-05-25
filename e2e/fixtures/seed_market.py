"""Rung 2 — market data: watchlists, OHLC, news, option chains.

Deterministic via ``rng = random.Random(42)``. Spans 30 days x 4 tickers x 7
bars per day at the ``1h`` timeframe. One option-chain snapshot contains an
unusual-options line (volume/oi >= 3.0, iv well above the running mean) to
trip the analytics detector.

Idempotent.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal


def seed_market() -> None:
    from e2e.fixtures.seed_minimal import seed_minimal

    seed_minimal()

    from apps.market.models import (
        NewsItem,
        OHLCBar,
        OptionChainSnapshot,
    )
    from apps.profiles.models import Watchlist, WatchlistSymbol

    for name, syms in (
        ("E2E Core", ["AAPL", "MSFT", "SPY"]),
        ("E2E Tech", ["NVDA", "AMD", "GOOGL", "TSLA"]),
        ("E2E Empty", []),
    ):
        wl, _ = Watchlist.objects.update_or_create(name=name)
        for order, sym in enumerate(syms):
            WatchlistSymbol.objects.update_or_create(
                watchlist=wl, ticker=sym, defaults={"sort_order": order}
            )

    rng = random.Random(42)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    bases = {"AAPL": 175.0, "MSFT": 420.0, "SPY": 500.0, "VIX": 15.0}
    for sym, base in bases.items():
        for day in range(30):
            for hour in range(7):  # roughly 09:30-16:00 ET
                ts = now - timedelta(days=day, hours=hour)
                drift = rng.uniform(-0.02, 0.02)
                o = base * (1 + drift)
                h = o * 1.002
                low = o * 0.998
                c = o * (1 + rng.uniform(-0.005, 0.005))
                OHLCBar.objects.update_or_create(
                    ticker=sym,
                    timeframe="1h",
                    ts=ts,
                    defaults={
                        "open": Decimal(f"{o:.4f}"),
                        "high": Decimal(f"{h:.4f}"),
                        "low": Decimal(f"{low:.4f}"),
                        "close": Decimal(f"{c:.4f}"),
                        "volume": rng.randint(1_000_000, 10_000_000),
                    },
                )

    for i in range(10):
        NewsItem.objects.update_or_create(
            provider="finnhub",
            external_id=f"e2e-{i}",
            defaults={
                "ticker": "AAPL" if i % 2 == 0 else "MSFT",
                "headline": f"E2E news headline {i}",
                "summary": "E2E fixture summary.",
                "url": f"https://example.test/news/{i}",
                "source": "Example",
                "published_at": now - timedelta(hours=i * 3),
            },
        )

    # 14 days of AAPL option-chain snapshots; day 0 contains an unusual-options line.
    # Idempotent via a single bulk reset for the E2E ticker before re-seeding.
    base_iv = 0.28
    OptionChainSnapshot.objects.filter(ticker="AAPL").delete()
    for day in range(14):
        ts = now - timedelta(days=day)
        iv = base_iv + rng.uniform(-0.02, 0.02)
        lines: list[dict] = [
            {"strike": 170, "type": "call", "iv": iv, "volume": 1000, "oi": 500},
            {"strike": 180, "type": "put", "iv": iv + 0.01, "volume": 800, "oi": 600},
        ]
        if day == 0:
            lines.append(
                {
                    "strike": 175,
                    "type": "call",
                    "iv": base_iv + 0.10,
                    "volume": 4000,
                    "oi": 1000,
                }
            )
        snap = OptionChainSnapshot.objects.create(
            ticker="AAPL", expiries=["2026-06-19"], payload={"lines": lines}
        )
        OptionChainSnapshot.objects.filter(pk=snap.pk).update(fetched_at=ts)
