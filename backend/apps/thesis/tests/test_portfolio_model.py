"""Layer 1: Position model tests — ticker normalisation, FK links, SET_NULL behaviour."""

from __future__ import annotations

import pytest

from apps.thesis.models import Position, Thesis


@pytest.fixture
def thesis(db, profile):
    return Thesis.objects.create(
        title="Long NVDA",
        ticker="NVDA",
        direction="bullish",
        profile=profile,
    )


@pytest.mark.django_db
def test_ticker_stripped_on_save(profile):
    """save() strips surrounding whitespace before upper-casing."""
    pos = Position.objects.create(
        ticker=" nvda ",
        direction="long",
        quantity="100.0000",
        avg_cost="450.0000",
        profile=profile,
    )
    assert pos.ticker == "NVDA"


@pytest.mark.django_db
def test_thesis_set_null_on_delete(profile, thesis):
    """Deleting the linked Thesis sets thesis_id to NULL — position survives."""
    pos = Position.objects.create(
        ticker="NVDA",
        quantity="100.0000",
        avg_cost="450.0000",
        thesis=thesis,
        profile=profile,
    )
    pos_id = pos.id
    thesis.delete()
    surviving = Position.objects.get(id=pos_id)
    assert surviving.thesis_id is None
    assert surviving.ticker == "NVDA"


@pytest.mark.django_db
def test_profile_set_null_on_delete(profile, thesis):
    """Deleting the linked TradingProfile sets profile_id to NULL — position survives."""
    pos = Position.objects.create(
        ticker="TSLA",
        quantity="25.0000",
        avg_cost="200.0000",
        profile=profile,
    )
    pos_id = pos.id
    profile_id = profile.id
    # Thesis references the same profile; delete it via cascade or set to null first
    # so profile deletion doesn't cascade through thesis onto position incorrectly.
    # (The position itself has SET_NULL on profile directly.)
    Thesis.objects.filter(profile_id=profile_id).update(profile=None)
    profile.delete()
    surviving = Position.objects.get(id=pos_id)
    assert surviving.profile_id is None
    assert surviving.ticker == "TSLA"
