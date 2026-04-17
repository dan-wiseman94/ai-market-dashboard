from apps.snapshots.token_budget import prune_to_budget


def test_image_section_never_pruned_even_under_tight_budget():
    sections = {
        "image": "## Charts attached\n- chart_1: x",
        "chain": "## Option chain\n" + ("X" * 5000),
        "news": "## News\n" + ("Y" * 5000),
        "ohlc": "## OHLC\n" + ("Z" * 5000),
    }
    kept, pruned = prune_to_budget(sections, max_tokens=50)
    assert "image" in kept
    assert "chain" in pruned
