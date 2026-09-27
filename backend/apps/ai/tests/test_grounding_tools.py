"""Tests for grounding tools: recall filters + track_record tool."""

from __future__ import annotations

from unittest.mock import patch

from apps.ai.tools.registry import _recall, _track_record, default_toolset


def test_recall_forwards_kinds_and_ticker_to_search() -> None:
    """_recall passes kinds and ticker kwargs through to search()."""
    with patch("apps.recall.services.search.search") as mock_search:
        mock_search.return_value = []
        _recall(query="NVDA breakout", kinds=["thesis"], ticker="NVDA")
        mock_search.assert_called_once_with("NVDA breakout", k=5, kinds=["thesis"], ticker="NVDA")


def test_recall_input_schema_declares_kinds_and_ticker() -> None:
    """The recall ToolSpec input_schema includes kinds and ticker properties."""
    ts = default_toolset()
    spec = ts.specs["recall"]
    props = spec.input_schema["properties"]
    assert "kinds" in props, "recall input_schema missing 'kinds' property"
    assert "ticker" in props, "recall input_schema missing 'ticker' property"
    assert "kinds" not in spec.input_schema.get("required", [])
    assert "ticker" not in spec.input_schema.get("required", [])
    assert "query" in spec.input_schema["required"]


_TRACK_RECORD_DATA = {
    "ticker": "NVDA",
    "closed_n": 5,
    "counts": {"win": 3, "loss": 1, "scratch": 1, "invalidated": 0},
    "hit_rate": 0.75,
    "last": {"direction": "bullish", "conviction": 4, "status": "closed_win"},
    "slice": None,
}


def test_track_record_handler_formats_output_with_hit_rate() -> None:
    """_track_record returns the formatted string when track_record_for_ticker returns data."""
    with patch(
        "apps.analytics.services.calibration.track_record_for_ticker",
        return_value=_TRACK_RECORD_DATA,
    ):
        result = _track_record(ticker="nvda")

    assert result == "NVDA: 5 closed theses — 3W/1L (75%)."


def test_track_record_handler_no_hit_rate_when_only_scratches() -> None:
    """_track_record omits the hit-rate percentage when hit_rate is None."""
    data = {
        **_TRACK_RECORD_DATA,
        "counts": {"win": 0, "loss": 0, "scratch": 3, "invalidated": 0},
        "closed_n": 3,
        "hit_rate": None,
    }
    with patch(
        "apps.analytics.services.calibration.track_record_for_ticker",
        return_value=data,
    ):
        result = _track_record(ticker="SPY")

    assert result == "SPY: 3 closed theses — 0W/0L."


def test_track_record_handler_none_case() -> None:
    """_track_record returns the friendly 'no track record' message when None."""
    with patch(
        "apps.analytics.services.calibration.track_record_for_ticker",
        return_value=None,
    ):
        result = _track_record(ticker="XYZ")

    assert result == "No track record for XYZ yet (need >= 3 closed theses)."


def test_track_record_handler_empty_ticker() -> None:
    """_track_record returns the prompt string for an empty ticker arg."""
    result = _track_record(ticker="")
    assert result == "Provide a ticker."


def test_track_record_handler_passes_direction_and_conviction() -> None:
    """_track_record forwards direction and conviction to the service."""
    with patch(
        "apps.analytics.services.calibration.track_record_for_ticker",
        return_value=None,
    ) as mock_fn:
        _track_record(ticker="TSLA", direction="bullish", conviction=3)
        mock_fn.assert_called_once_with("TSLA", direction="bullish", conviction=3)


def test_track_record_tool_via_toolset() -> None:
    """Toolset.run('track_record', {...}) returns ok=True with formatted string."""
    with patch(
        "apps.analytics.services.calibration.track_record_for_ticker",
        return_value=_TRACK_RECORD_DATA,
    ):
        ts = default_toolset()
        out = ts.run("track_record", {"ticker": "NVDA"})

    assert out["ok"] is True
    assert "NVDA" in out["result"]
    assert "3W/1L" in out["result"]
