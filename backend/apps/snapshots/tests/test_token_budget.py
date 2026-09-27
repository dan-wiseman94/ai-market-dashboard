from apps.snapshots.token_budget import _PRUNE_ORDER, prune_to_budget


def test_prune_drops_chain_then_ohlc_before_news():
    # OHLC is the chronic oversize section — it must go before news does, so a
    # bloated bar dump can never evict the day's headlines.
    big = "x " * 50_000
    sections = {
        "chain": big,
        "ohlc": big,
        "news": "a few headlines",
        "quotes": "small",
    }
    out, pruned = prune_to_budget(sections, max_tokens=100)
    assert pruned == ["chain", "ohlc"]
    assert "news" in out
    assert "quotes" in out


def test_prune_order_places_fed_and_flowlite_between_news_and_breadth():
    assert _PRUNE_ORDER == [
        "chain",
        "ohlc",
        "news",
        "fed",
        "flowlite",
        "breadth",
        "quotes",
        "positions",
    ]
