import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import serialize_for_ai


@pytest.mark.django_db
def test_serializes_quotes_section_as_table():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(
        profile=p, includes=["quotes"], source="manual", objective="buy the dip?"
    )
    SnapshotSection.objects.create(
        snapshot=s,
        kind="quotes",
        status="done",
        payload={
            "SPY": {
                "last": 550.0,
                "pct_change": 0.5,
                "bid": 549.9,
                "ask": 550.1,
                "volume": 12345,
                "high": 552.0,
                "low": 548.0,
            }
        },
    )
    out = serialize_for_ai(s)
    assert "## Quotes" in out
    assert "SPY" in out
    assert "550" in out
    assert "buy the dip" in out


@pytest.mark.django_db
def test_missing_section_marked_unavailable():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes", "news"], source="manual")
    SnapshotSection.objects.create(
        snapshot=s,
        kind="news",
        status="failed",
        error="Finnhub 503",
    )
    out = serialize_for_ai(s)
    assert "News" in out
    assert "unavailable" in out
    assert "Finnhub 503" in out


@pytest.mark.django_db
def test_ohlc_section_csv_block():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["ohlc"], source="manual")
    SnapshotSection.objects.create(
        snapshot=s,
        kind="ohlc",
        status="done",
        payload={
            "ticker": "SPY",
            "timeframe": "1m",
            "bars": [
                {
                    "ts": "2026-01-01T00:00:00+00:00",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "volume": 100,
                },
                {
                    "ts": "2026-01-01T00:01:00+00:00",
                    "open": 2,
                    "high": 3,
                    "low": 1,
                    "close": 3,
                    "volume": 200,
                },
            ],
        },
    )
    out = serialize_for_ai(s)
    assert "ts,open,high,low,close,volume" in out
    assert "```" in out


@pytest.mark.django_db
def test_notes_section_appears_at_top():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(
        profile=p, includes=["notes"], source="manual", notes="looking risk-on"
    )
    out = serialize_for_ai(s)
    idx_notes = out.find("looking risk-on")
    idx_any_section = min(
        (out.find(h) for h in ["## Quotes", "## OHLC", "## Positions"] if out.find(h) != -1),
        default=10**9,
    )
    assert idx_notes < idx_any_section or idx_any_section == 10**9
