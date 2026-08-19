"""Layer 3: API tests — CRUD, filters, unrealized dict on read, close action.

Mirrors thesis test style: APIClient, real URLs, real DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.market.models import OHLCBar
from apps.profiles.models import TradingProfile
from apps.thesis.models import Position, Thesis


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="API Test Profile", style="swing trader")


@pytest.fixture
def thesis(db, profile):
    return Thesis.objects.create(
        title="Long NVDA",
        ticker="NVDA",
        direction="bullish",
        profile=profile,
    )


@pytest.fixture
def open_position(db, profile, thesis):
    return Position.objects.create(
        ticker="NVDA",
        direction="long",
        quantity=Decimal("100.0000"),
        avg_cost=Decimal("450.0000"),
        profile=profile,
        thesis=thesis,
    )


def _seed_bar(ticker: str, close: float) -> OHLCBar:
    return OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1d",
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000_000,
        ts=timezone.now(),
    )


@pytest.mark.django_db
def test_create_position(api, profile, thesis):
    """POST /api/portfolio/positions/ creates a position; ticker is normalised."""
    resp = api.post(
        "/api/portfolio/positions/",
        data={
            "ticker": "aapl",
            "direction": "long",
            "quantity": "50.0000",
            "avg_cost": "180.0000",
            "profile_id": profile.id,
            "thesis_id": thesis.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ticker"] == "AAPL"
    assert data["status"] == "open"
    assert data["profile_id"] == profile.id
    assert data["thesis_id"] == thesis.id
    assert "unrealized" in data


@pytest.mark.django_db
def test_create_position_without_thesis(api, profile):
    """POST without thesis_id creates an unlinked position (thesis_id is null)."""
    resp = api.post(
        "/api/portfolio/positions/",
        data={
            "ticker": "SPY",
            "direction": "long",
            "quantity": "10.0000",
            "avg_cost": "500.0000",
            "profile_id": profile.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["thesis_id"] is None


@pytest.mark.django_db
def test_list_positions(api, open_position):
    """GET /api/portfolio/positions/ returns at least our position."""
    resp = api.get("/api/portfolio/positions/")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert open_position.id in ids


@pytest.mark.django_db
def test_list_positions_query_count_is_constant(api, profile, django_assert_max_num_queries):
    """The list endpoint must not issue one OHLCBar query per row (N+1). Query count
    stays bounded regardless of how many positions/tickers are returned."""
    for i in range(6):
        ticker = f"TKR{i}"
        Position.objects.create(
            ticker=ticker, direction="long", quantity="10", avg_cost="100", profile=profile
        )
        _seed_bar(ticker, 100.0 + i)
    with django_assert_max_num_queries(5):
        resp = api.get("/api/portfolio/positions/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 6


@pytest.mark.django_db
def test_list_unrealized_uses_batched_price(api, profile):
    """The batched price path yields the same mark-to-market as the per-row path."""
    Position.objects.create(
        ticker="NVDA", direction="long", quantity="100", avg_cost="450", profile=profile
    )
    _seed_bar("NVDA", 480.0)
    resp = api.get("/api/portfolio/positions/")
    assert resp.status_code == 200
    row = next(p for p in resp.json() if p["ticker"] == "NVDA")
    assert row["unrealized"]["last"] == pytest.approx(480.0)
    assert row["unrealized"]["unrealized_pnl"] == pytest.approx(3_000.0)


@pytest.mark.django_db
def test_filter_by_status_open(api, db, profile):
    """?status=open returns only open positions."""
    pos_open = Position.objects.create(
        ticker="AAPL", quantity="10", avg_cost="180", profile=profile
    )
    pos_closed = Position.objects.create(
        ticker="MSFT",
        quantity="5",
        avg_cost="300",
        profile=profile,
        status="closed",
        close_price="310",
        realized_pnl="50",
        closed_at=timezone.now(),
    )
    resp = api.get("/api/portfolio/positions/?status=open")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert pos_open.id in ids
    assert pos_closed.id not in ids


@pytest.mark.django_db
def test_filter_by_status_closed(api, db, profile):
    """?status=closed returns only closed positions."""
    pos_open = Position.objects.create(
        ticker="AAPL", quantity="10", avg_cost="180", profile=profile
    )
    pos_closed = Position.objects.create(
        ticker="MSFT",
        quantity="5",
        avg_cost="300",
        profile=profile,
        status="closed",
        close_price="310",
        realized_pnl="50",
        closed_at=timezone.now(),
    )
    resp = api.get("/api/portfolio/positions/?status=closed")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert pos_closed.id in ids
    assert pos_open.id not in ids


@pytest.mark.django_db
def test_filter_by_ticker(api, db, profile):
    """?ticker=NVDA returns only NVDA positions."""
    pos_nvda = Position.objects.create(
        ticker="NVDA", quantity="100", avg_cost="450", profile=profile
    )
    pos_aapl = Position.objects.create(
        ticker="AAPL", quantity="50", avg_cost="180", profile=profile
    )
    resp = api.get("/api/portfolio/positions/?ticker=NVDA")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert pos_nvda.id in ids
    assert pos_aapl.id not in ids


@pytest.mark.django_db
def test_filter_by_thesis(api, open_position, profile):
    """?thesis=<id> returns only positions linked to that thesis."""
    pos_unlinked = Position.objects.create(
        ticker="SPY", quantity="5", avg_cost="500", profile=profile
    )
    resp = api.get(f"/api/portfolio/positions/?thesis={open_position.thesis_id}")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert open_position.id in ids
    assert pos_unlinked.id not in ids


@pytest.mark.django_db
def test_retrieve_includes_unrealized_dict(api, open_position):
    """GET /api/portfolio/positions/<id>/ includes the 'unrealized' dict."""
    resp = api.get(f"/api/portfolio/positions/{open_position.id}/")
    assert resp.status_code == 200
    data = resp.json()
    assert "unrealized" in data
    unrealized = data["unrealized"]
    # No bar seeded — all None (honest gap)
    assert unrealized["last"] is None
    assert unrealized["market_value"] is None
    assert unrealized["unrealized_pnl"] is None
    assert unrealized["unrealized_pct"] is None


@pytest.mark.django_db
def test_retrieve_unrealized_with_bar(api, open_position):
    """GET returns non-None unrealized when a bar exists. Verify the values."""
    _seed_bar("NVDA", 480.0)
    resp = api.get(f"/api/portfolio/positions/{open_position.id}/")
    assert resp.status_code == 200
    unrealized = resp.json()["unrealized"]
    # Long 100 NVDA @ 450, mark @ 480: pnl = (480-450)*100 = 3000
    assert unrealized["last"] == pytest.approx(480.0)
    assert unrealized["unrealized_pnl"] == pytest.approx(3_000.0)
    assert unrealized["unrealized_pct"] == pytest.approx(6.666_666, rel=1e-4)


@pytest.mark.django_db
def test_close_action_long_sets_realized_pnl(api, open_position):
    """POST .../close/ with close_price flips status→closed and sets realized_pnl.

    Long 100 NVDA @ $450, close at $500: realized = (500-450)*100 = $5 000.
    """
    resp = api.post(
        f"/api/portfolio/positions/{open_position.id}/close/",
        data={"close_price": "500.0000"},
        format="json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "closed"
    assert float(data["realized_pnl"]) == pytest.approx(5_000.0)
    assert data["close_price"] == "500.0000"
    assert data["closed_at"] is not None

    open_position.refresh_from_db()
    assert open_position.status == "closed"
    assert float(open_position.realized_pnl) == pytest.approx(5_000.0)


@pytest.mark.django_db
def test_close_action_short_sets_realized_pnl(api, profile, db):
    """POST .../close/ on a short position computes sign-correct realized_pnl.

    Short 50 TSLA @ $250, close at $200: realized = (200-250)*50*-1 = +$2 500.
    """
    pos = Position.objects.create(
        ticker="TSLA",
        direction="short",
        quantity=Decimal("50.0000"),
        avg_cost=Decimal("250.0000"),
        profile=profile,
    )
    resp = api.post(
        f"/api/portfolio/positions/{pos.id}/close/",
        data={"close_price": "200.0000"},
        format="json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "closed"
    assert float(data["realized_pnl"]) == pytest.approx(2_500.0)


@pytest.mark.django_db
def test_close_action_missing_close_price_returns_400(api, open_position):
    """POST .../close/ without close_price returns 400."""
    resp = api.post(
        f"/api/portfolio/positions/{open_position.id}/close/",
        data={},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_close_action_custom_closed_at(api, open_position):
    """POST .../close/ accepts an explicit closed_at timestamp."""
    ts = "2026-01-15T14:30:00Z"
    resp = api.post(
        f"/api/portfolio/positions/{open_position.id}/close/",
        data={"close_price": "460.0000", "closed_at": ts},
        format="json",
    )
    assert resp.status_code == 200
    # closed_at reflects the provided value (ISO string in response)
    assert "2026-01-15" in resp.json()["closed_at"]


@pytest.mark.django_db
def test_patch_note(api, open_position):
    """PATCH /api/portfolio/positions/<id>/ updates the note field."""
    resp = api.patch(
        f"/api/portfolio/positions/{open_position.id}/",
        data={"note": "Watching for breakout"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["note"] == "Watching for breakout"


@pytest.mark.django_db
def test_delete_position(api, open_position):
    """DELETE /api/portfolio/positions/<id>/ removes the row."""
    pos_id = open_position.id
    resp = api.delete(f"/api/portfolio/positions/{pos_id}/")
    assert resp.status_code == 204
    assert not Position.objects.filter(id=pos_id).exists()
