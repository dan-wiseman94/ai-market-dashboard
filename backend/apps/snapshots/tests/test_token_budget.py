from apps.snapshots.token_budget import estimate_tokens, prune_to_budget


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
