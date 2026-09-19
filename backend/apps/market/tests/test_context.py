"""Tests for market context payload."""


def _quotes(**overrides):
    base = {
        s: {"last": 100.0, "pct_change": 0.5}
        for s in [
            "$SPX",
            "QQQ",
            "$VIX",
            "SPY",
            "UUP",
            "XLK",
            "XLF",
            "XLE",
            "XLV",
            "XLY",
            "XLP",
            "XLI",
            "XLU",
            "XLB",
            "XLRE",
            "XLC",
        ]
    }
    base["$ADVN"] = {"last": 2000}
    base["$DECN"] = {"last": 900}
    base["$UVOL"] = {"last": 5.1e9}
    base["$DVOL"] = {"last": 2.2e9}
    base.update(overrides)
    return base


def test_fetch_carries_sector_pct_dollar_and_index_complex(monkeypatch, db):
    from apps.market.services import context

    calls = []

    def fake_fetch(symbols):
        calls.append(sorted(symbols))
        return (
            {
                "/ES": {"last": 6500.0, "pct_change": 0.3},
                "/NQ": {"last": 24000.0, "pct_change": 0.4},
            }
            if any(s.startswith("/") for s in symbols)
            else _quotes()
        )

    monkeypatch.setattr(context, "fetch_quotes", fake_fetch)
    p = context._fetch(None)
    assert p["sector_pct"]["XLK"] == 0.5
    assert p["dollar"]["symbol"] == "UUP"
    assert [r["symbol"] for r in p["index_complex"]] == ["$SPX", "SPY", "QQQ", "/ES", "/NQ"]
    assert p["breadth"]["$UVOL"] == 5.1e9
    assert len(calls) == 2  # futures fetched in their OWN call


def test_rejected_futures_call_cannot_blank_the_etf_batch(monkeypatch, db):
    from apps.market.services import context

    def fake_fetch(symbols):
        if any(s.startswith("/") for s in symbols):
            raise RuntimeError("provider rejected /ES")
        return _quotes()

    monkeypatch.setattr(context, "fetch_quotes", fake_fetch)
    p = context._fetch(None)
    assert p["sectors"]["XLK"] == 100.0  # ETF batch intact
    assert [r["symbol"] for r in p["index_complex"]] == ["$SPX", "SPY", "QQQ"]
