import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import serialize_for_ai


@pytest.mark.django_db
def test_oversized_ohlc_is_truncated_to_newest_bars_not_dropped():
    """When OHLC alone overflows the budget, trim its oldest bars instead of
    letting the pruner drop whole sections (the audit's pre-open run lost news
    AND all price history to a 40k-token bar dump)."""
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["ohlc", "news"], source="manual")
    bars = [
        {
            "ts": f"2026-07-22T{h:02d}:{m:02d}:00+00:00",
            "open": 100 + h,
            "high": 101 + h,
            "low": 99 + h,
            "close": 100.5 + h,
            "volume": 1000 + m,
        }
        for h in range(10)
        for m in range(60)
    ]  # 600 bars ≈ well over a 2k-token budget when rendered
    SnapshotSection.objects.create(
        snapshot=s,
        kind="ohlc",
        status="done",
        payload={"ticker": "NQ", "timeframe": "1m", "window": "24h", "bars": bars},
    )
    SnapshotSection.objects.create(
        snapshot=s,
        kind="news",
        status="done",
        payload={"items": [{"headline": "keep me", "source": "S", "datetime": 1784725100}]},
    )

    out = serialize_for_ai(s, max_tokens=2000)

    assert "keep me" in out  # news survives
    assert "## OHLC" in out  # ohlc survives, truncated
    assert "older bars trimmed" in out
    assert bars[-1]["ts"] in out  # newest bar kept
    assert bars[0]["ts"] not in out  # oldest bar trimmed
    assert "pruned for token budget" not in out


@pytest.mark.django_db
def test_ohlc_within_budget_is_not_truncated():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["ohlc"], source="manual")
    bars = [
        {"ts": "2026-07-22T13:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 5}
    ]
    SnapshotSection.objects.create(
        snapshot=s,
        kind="ohlc",
        status="done",
        payload={"ticker": "NQ", "timeframe": "1m", "window": "24h", "bars": bars},
    )
    out = serialize_for_ai(s)
    assert "older bars trimmed" not in out
    assert bars[0]["ts"] in out


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
def test_manual_positions_rendered_for_ai_to_parse():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(
        profile=p,
        includes=[],
        source="manual",
        objective="risk check",
        manual_positions="100 SPY @ 450\n2x AAPL 180c exp 6/20",
    )
    out = serialize_for_ai(s)
    assert "## Positions (current holdings" in out
    assert "100 SPY @ 450" in out
    assert "AAPL 180c" in out


@pytest.mark.django_db
def test_blank_manual_positions_omitted():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=[], source="manual", objective="o")
    assert "current holdings" not in serialize_for_ai(s)


@pytest.mark.django_db
def test_candidate_positions_rendered_with_entry_framing():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(
        profile=p,
        includes=[],
        source="manual",
        objective="what should I add?",
        candidate_positions="long NVDA 6mo\nshort QQQ hedge",
    )
    out = serialize_for_ai(s)
    assert "## Candidate positions (potential trades under consideration" in out
    assert "long NVDA 6mo" in out
    assert "short QQQ hedge" in out


@pytest.mark.django_db
def test_blank_candidate_positions_omitted():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=[], source="manual", objective="o")
    assert "Candidate positions" not in serialize_for_ai(s)


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
