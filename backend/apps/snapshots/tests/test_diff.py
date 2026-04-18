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
    prev = {"breadth": {"spy_last": 520, "qqq_last": 440, "vix_last": 14}}
    curr = {"breadth": {"spy_last": 525, "qqq_last": 440, "vix_last": 17}}
    out = diff_sections(prev, curr)
    assert "spy_last" in out
    assert "vix_last" in out
    assert "qqq_last" not in out  # unchanged


def test_no_change_returns_nothing_meaningful() -> None:
    prev = {"quotes": {"SPY": {"last": 520.0}}}
    curr = {"quotes": {"SPY": {"last": 520.0}}}
    out = diff_sections(prev, curr)
    assert "No meaningful changes" in out or "below 0.5%" in out
