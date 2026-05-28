import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.primary import (
    previous_snapshot_for,
    primary_ticker,
    primary_ticker_from_quotes,
)


def test_from_quotes_first_key_upper():
    assert primary_ticker_from_quotes({"nvda": {"last": 1}, "spy": {}}) == "NVDA"


def test_from_quotes_empty_or_bad():
    assert primary_ticker_from_quotes({}) is None
    assert primary_ticker_from_quotes(None) is None
    assert primary_ticker_from_quotes(["x"]) is None


@pytest.mark.django_db
def test_primary_ticker_reads_quotes_section():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    snap = Snapshot.objects.create(profile=p, includes=["quotes"], status="ready")
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={"AAPL": {"last": 10}}
    )
    assert primary_ticker(snap) == "AAPL"


@pytest.mark.django_db
def test_primary_ticker_none_without_quotes():
    p = TradingProfile.objects.create(name="P", default_includes=["news"])
    snap = Snapshot.objects.create(profile=p, includes=["news"], status="ready")
    SnapshotSection.objects.create(snapshot=snap, kind="news", status="done", payload={"items": []})
    assert primary_ticker(snap) is None


@pytest.mark.django_db
def test_previous_snapshot_for_same_ticker_prior_ready():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    older = Snapshot.objects.create(
        profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA"
    )
    newer = Snapshot.objects.create(
        profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA"
    )
    other = Snapshot.objects.create(
        profile=p, includes=["quotes"], status="ready", primary_ticker="SPY"
    )
    assert previous_snapshot_for(newer).id == older.id
    assert previous_snapshot_for(older) is None
    assert previous_snapshot_for(other) is None


@pytest.mark.django_db
def test_previous_snapshot_for_none_when_no_ticker():
    p = TradingProfile.objects.create(name="P", default_includes=["news"])
    snap = Snapshot.objects.create(
        profile=p, includes=["news"], status="ready", primary_ticker=None
    )
    assert previous_snapshot_for(snap) is None
