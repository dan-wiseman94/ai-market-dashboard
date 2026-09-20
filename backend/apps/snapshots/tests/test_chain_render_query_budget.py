"""N+1 regression gate for the chain render's unusual-activity lookup.

_render_chain(..., captured_at=...) calls apps.analytics.services.unusual_options,
which issues a fixed 2 queries (latest chain snapshot + 30d history) regardless of
how many contracts are on the chain. A budget of 3 leaves small headroom while
still catching a per-contract or per-expiry N+1 (which would blow well past it).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.market.models import OptionChainSnapshot
from apps.snapshots.serializer import _render_chain

_PAYLOAD = {
    "underlying_last": "100.00",
    "ticker": "TST",
    "expiries": {
        "2026-01-01": {
            "calls": [
                {
                    "strike": "95.00",
                    "delta": "0.75",
                    "gamma": "0.05",
                    "iv": "20.0",
                    "volume": 500,
                    "oi": 1000,
                    "bid": "5.00",
                    "ask": "5.10",
                },
                {
                    "strike": "100.00",
                    "delta": "0.50",
                    "gamma": "0.08",
                    "iv": "18.0",
                    "volume": 300,
                    "oi": 800,
                    "bid": "2.00",
                    "ask": "2.10",
                },
            ],
            "puts": [
                {
                    "strike": "95.00",
                    "delta": "-0.25",
                    "gamma": "0.05",
                    "iv": "21.0",
                    "volume": 100,
                    "oi": 400,
                    "bid": "0.40",
                    "ask": "0.45",
                },
                {
                    "strike": "100.00",
                    "delta": "-0.50",
                    "gamma": "0.08",
                    "iv": "19.0",
                    "volume": 150,
                    "oi": 500,
                    "bid": "1.80",
                    "ask": "1.90",
                },
            ],
        },
    },
}


@pytest.mark.django_db
def test_render_chain_with_unusual_activity_is_query_bounded(django_assert_max_num_queries):
    OptionChainSnapshot.objects.create(ticker="TST", expiries=["2026-01-01"], payload=_PAYLOAD)
    captured_at = datetime.now(UTC)

    with django_assert_max_num_queries(3):
        md = _render_chain(_PAYLOAD, ticker="TST", captured_at=captured_at)

    assert "### Chain analytics" in md
