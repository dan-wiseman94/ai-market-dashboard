from apps.snapshots.token_budget import _PRUNE_ORDER, estimate_tokens, prune_to_budget


def test_estimate_tokens_returns_positive():
    t = estimate_tokens("Hello, world!")
    assert t > 0


def test_prune_returns_same_when_small():
    sections = {
        "quotes": "tiny",
        "ohlc": "tiny",
        "chain": "tiny",
        "news": "tiny",
    }
    out, pruned = prune_to_budget(sections, max_tokens=10_000)
    assert out == sections
    assert pruned == []


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


def test_prune_drops_fed_before_breadth():
    # fed/flowlite are enrichment sections — they must drop before core context
    # (breadth/quotes/positions) when the budget is tight.
    big = "x " * 50_000
    sections = {
        "fed": big,
        "breadth": "small",
        "quotes": "small",
    }
    out, pruned = prune_to_budget(sections, max_tokens=10)
    assert pruned == ["fed"]
    assert "breadth" in out
    assert "quotes" in out
