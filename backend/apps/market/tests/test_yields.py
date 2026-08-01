"""Tests for live_yields (CBOE yield-index quotes, yield x 10)."""

from __future__ import annotations

from unittest.mock import patch

from apps.market.services import yields as yields_mod


def test_live_yields_divides_cboe_quote_by_ten():
    with patch.object(
        yields_mod,
        "fetch_quotes",
        return_value={"$TNX": {"last": 47.1}, "$TYX": {"last": 48.9}},
    ):
        out = yields_mod.live_yields()
    assert out["10Y"] == {"ticker": "$TNX", "yield_pct": 4.71}
    assert out["30Y"]["yield_pct"] == 4.89
    assert "5Y" not in out


def test_live_yields_skips_zero_and_missing_last():
    with patch.object(
        yields_mod,
        "fetch_quotes",
        return_value={"$TNX": {"last": 0}, "$FVX": {}, "$IRX": {"last": None}},
    ):
        assert yields_mod.live_yields() == {}


def test_live_yields_degrades_to_empty_on_error():
    with patch.object(yields_mod, "fetch_quotes", side_effect=RuntimeError("boom")):
        assert yields_mod.live_yields() == {}
