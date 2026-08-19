import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.primary import last_price


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="P", default_includes=["quotes"])


def _snap(profile, *, primary_ticker="NVDA"):
    return Snapshot.objects.create(
        profile=profile, includes=["quotes"], status="ready", primary_ticker=primary_ticker
    )


def _quotes(snap, payload, *, status="done"):
    return SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status=status, payload=payload
    )


@pytest.mark.django_db
def test_done_section_returns_float(profile):
    snap = _snap(profile)
    _quotes(snap, {"NVDA": {"last": 123.45}})
    assert last_price(snap, "NVDA") == 123.45
    assert isinstance(last_price(snap, "NVDA"), float)


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["failed", "pending"])
def test_non_done_quotes_section_is_ignored(profile, status):
    snap = _snap(profile)
    _quotes(snap, {"NVDA": {"last": 123.45}}, status=status)
    assert last_price(snap, "NVDA") is None


@pytest.mark.django_db
def test_default_ticker_is_snapshot_primary(profile):
    snap = _snap(profile, primary_ticker="AMD")
    _quotes(snap, {"AMD": {"last": 101.0}, "NVDA": {"last": 202.0}})
    assert last_price(snap) == 101.0
    assert last_price(snap, "NVDA") == 202.0


@pytest.mark.django_db
def test_missing_ticker_and_missing_section_return_none(profile):
    snap = _snap(profile)
    _quotes(snap, {"NVDA": {"last": 1.0}})
    assert last_price(snap, "TSLA") is None
    bare = _snap(profile)
    assert last_price(bare, "NVDA") is None
    no_primary = _snap(profile, primary_ticker="")
    _quotes(no_primary, {"NVDA": {"last": 1.0}})
    assert last_price(no_primary) is None


@pytest.mark.django_db
@pytest.mark.parametrize("row", [{"last": "n/a"}, {"last": None}, {}, "junk", 5])
def test_junk_value_returns_none(profile, row):
    snap = _snap(profile)
    _quotes(snap, {"NVDA": row})
    assert last_price(snap, "NVDA") is None


def test_none_snapshot_returns_none():
    assert last_price(None, "NVDA") is None
