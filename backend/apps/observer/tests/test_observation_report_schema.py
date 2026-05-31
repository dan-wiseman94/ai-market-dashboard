"""Tests for additive ObservationReport fields (M6-5).

Covers:
- Back-compat: existing reports without predicted_*/grounding still parse.
- Round-trip: a report WITH the new fields serialises and re-parses correctly.
"""

from __future__ import annotations

import pytest

from apps.observer.schemas import ObservationReport

# --- minimal fixture (only the seven required/defaulted legacy fields) -------

MINIMAL_KWARGS = dict(
    headline="SPY grinding higher",
    bias="neutral",
    summary="Price respects the 20-period EMA but breadth is mixed.",
    next_check_in="after the 10:00 breadth reading",
)


def test_observation_report_back_compat_no_predicted_fields() -> None:
    """An ObservationReport without predicted_*/grounding must still parse.

    This is the load-bearing back-compat guarantee: existing structured runs
    that emit reports without the new fields must not break.
    """
    report = ObservationReport(**MINIMAL_KWARGS)
    assert report.predicted_direction is None
    assert report.predicted_horizon_days is None
    assert report.grounding == []


def test_observation_report_predicted_direction_round_trip() -> None:
    """predicted_direction round-trips through model_dump() / re-parse."""
    report = ObservationReport(
        **MINIMAL_KWARGS,
        predicted_direction="bullish",
    )
    assert report.predicted_direction == "bullish"
    data = report.model_dump()
    assert data["predicted_direction"] == "bullish"
    rebuilt = ObservationReport(**data)
    assert rebuilt.predicted_direction == "bullish"


def test_observation_report_all_new_fields_round_trip() -> None:
    """All three new fields (predicted_direction, predicted_horizon_days, grounding)
    round-trip via model_dump() / re-parse with real value assertions.
    """
    report = ObservationReport(
        **MINIMAL_KWARGS,
        predicted_direction="bullish",
        predicted_horizon_days=5,
        grounding=["quotes", "chain analytics"],
    )
    assert report.predicted_direction == "bullish"
    assert report.predicted_horizon_days == 5
    assert report.grounding == ["quotes", "chain analytics"]

    data = report.model_dump()
    assert data["predicted_direction"] == "bullish"
    assert data["predicted_horizon_days"] == 5
    assert data["grounding"] == ["quotes", "chain analytics"]

    rebuilt = ObservationReport(**data)
    assert rebuilt.predicted_direction == "bullish"
    assert rebuilt.predicted_horizon_days == 5
    assert rebuilt.grounding == ["quotes", "chain analytics"]


def test_observation_report_bearish_and_neutral_directions() -> None:
    """Other valid Literal values for predicted_direction parse correctly."""
    for direction in ("bearish", "neutral"):
        r = ObservationReport(**MINIMAL_KWARGS, predicted_direction=direction)  # type: ignore[arg-type]
        assert r.predicted_direction == direction


def test_observation_report_grounding_max_length() -> None:
    """grounding accepts up to 12 items."""
    items = [f"section-{i}" for i in range(12)]
    r = ObservationReport(**MINIMAL_KWARGS, grounding=items)
    assert len(r.grounding) == 12


def test_observation_report_grounding_max_length_exceeded() -> None:
    """grounding rejects more than 12 items."""
    from pydantic import ValidationError

    items = [f"section-{i}" for i in range(13)]
    with pytest.raises(ValidationError):
        ObservationReport(**MINIMAL_KWARGS, grounding=items)


def test_observation_report_new_fields_in_model_dump() -> None:
    """model_dump() always includes the new keys (even when None/empty)."""
    report = ObservationReport(**MINIMAL_KWARGS)
    data = report.model_dump()
    assert "predicted_direction" in data
    assert "predicted_horizon_days" in data
    assert "grounding" in data
