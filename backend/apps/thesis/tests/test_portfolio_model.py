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
def test_ticker_uppercased_on_save(profile):
    """save() normalises ticker to upper-case."""
    pos = Position.objects.create(
        ticker="nvda",
        direction="long",
        quantity="100.0000",
        avg_cost="450.0000",
        profile=profile,
    )
    assert pos.ticker == "NVDA"


@pytest.mark.django_db
def test_ticker_already_upper_stays(profile):
    """Upper-case ticker is preserved unchanged."""
    pos = Position.objects.create(
        ticker="AAPL",
        direction="long",
        quantity="50.0000",
        avg_cost="180.0000",
        profile=profile,
    )
    assert pos.ticker == "AAPL"


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
def test_defaults(profile):
    """Default values: direction=long, status=open, note=''."""
    pos = Position.objects.create(
        ticker="SPY",
        quantity="10.0000",
        avg_cost="500.0000",
        profile=profile,
    )
    assert pos.direction == "long"
    assert pos.status == "open"
    assert pos.note == ""
    assert pos.close_price is None
    assert pos.realized_pnl is None
    assert pos.closed_at is None


@pytest.mark.django_db
def test_thesis_fk_link(profile, thesis):
    """Position can be linked to a Thesis via FK."""
    pos = Position.objects.create(
        ticker="NVDA",
        quantity="100.0000",
        avg_cost="450.0000",
        thesis=thesis,
        profile=profile,
    )
    assert pos.thesis_id == thesis.id
    assert thesis.positions.filter(id=pos.id).exists()


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


@pytest.mark.django_db
def test_short_direction_stored(profile):
    """Short direction is stored and retrievable."""
    pos = Position.objects.create(
        ticker="TSLA",
        direction="short",
        quantity="50.0000",
        avg_cost="250.0000",
        profile=profile,
    )
    pos.refresh_from_db()
    assert pos.direction == "short"
