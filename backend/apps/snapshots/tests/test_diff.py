"""Snapshot diff must produce a compact, human-readable delta for AI context."""

from __future__ import annotations

from apps.snapshots.diff import diff_sections


def test_quotes_delta_highlights_movers() -> None:
    prev = {"quotes": {"SPY": {"last": 520.0}, "QQQ": {"last": 440.0}}}
    curr = {"quotes": {"SPY": {"last": 525.0}, "QQQ": {"last": 440.5}}}
    out = diff_sections(prev, curr)
    assert "SPY" in out
    assert "+0.96%" in out  # movement magnitude (525-520)/520 = 0.9615%


def test_news_delta_lists_only_new_headlines() -> None:
    prev = {"news": [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]}
    curr = {"news": [{"id": 2, "title": "B"}, {"id": 3, "title": "C"}]}
    out = diff_sections(prev, curr)
    assert "C" in out
    assert "- A" not in out
    assert "- B" not in out


def test_news_delta_handles_stored_items_shape() -> None:
    # Regression: news is stored as {"items": [...]} with `headline`, not a flat
    # list with `title`; the diff must read that real shape, not silently skip it.
    prev = {"news": {"items": [{"id": 1, "headline": "Old"}]}}
    curr = {"news": {"items": [{"id": 1, "headline": "Old"}, {"id": 2, "headline": "Fresh take"}]}}
    out = diff_sections(prev, curr)
    assert "Fresh take" in out
    assert "Old" not in out


def test_empty_prev_shows_everything_as_new() -> None:
    curr = {"quotes": {"SPY": {"last": 525.0}}}
    out = diff_sections({}, curr)
    assert "SPY" in out
    assert "new" in out.lower() or "525" in out


def test_missing_current_section_logs_removed() -> None:
    prev = {"news": [{"id": 1, "title": "A"}]}
    curr = {"quotes": {"SPY": {"last": 1}}}
    out = diff_sections(prev, curr)
    assert "news" in out.lower()
    assert "removed" in out.lower() or "dropped" in out.lower()


def test_breadth_shift_reported() -> None:
    prev = {"breadth": {"spx_last": 520, "qqq_last": 440, "vix_last": 14}}
    curr = {"breadth": {"spx_last": 525, "qqq_last": 440, "vix_last": 17}}
    out = diff_sections(prev, curr)
    assert "spx_last" in out
    assert "vix_last" in out
    assert "qqq_last" not in out  # unchanged


def test_no_change_returns_nothing_meaningful() -> None:
    prev = {"quotes": {"SPY": {"last": 520.0}}}
    curr = {"quotes": {"SPY": {"last": 520.0}}}
    out = diff_sections(prev, curr)
    assert "No meaningful changes" in out or "below 0.5%" in out


def test_malformed_section_does_not_raise_or_400_the_whole_diff() -> None:
    """A single bad section payload must be skipped, not raise (which core's
    exception_handler turns into a 400 'Invalid input.'). Regression: a new
    'quotes' section whose value isn't a dict would AttributeError out."""
    prev = {"ohlc": {"data": {"ticker": "SPY", "bars": [{"close": 100.0}]}}}
    curr = {
        "ohlc": {"data": {"ticker": "SPY", "bars": [{"close": 101.0}]}},
        "quotes": {"AAPL": "not-a-dict"},  # malformed — would raise in _summarize_new
    }
    out = diff_sections(prev, curr)  # must not raise
    assert isinstance(out, str)
    assert "SPY last: 100.0 → 101.0" in out  # the good section still diffs


def test_section_helper_exception_is_isolated() -> None:
    """If a helper raises on a hostile payload, diff_sections skips that section
    and still returns the other deltas (per-section isolation)."""
    prev = {"quotes": {"AAPL": {"last": 100.0}}, "breadth": {"spx_last": 4000}}
    curr = {"quotes": {"AAPL": 12345}, "breadth": {"spx_last": 4010}}  # quote value not a dict
    out = diff_sections(prev, curr)
    assert isinstance(out, str)
    assert "spx_last: 4000 → 4010" in out  # breadth still reported
