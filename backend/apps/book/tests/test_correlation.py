import pytest
from django.utils import timezone

from apps.book.services.correlation import correlation_clusters
from apps.market.models import OHLCBar

pytestmark = pytest.mark.django_db


def _seed(ticker, closes):
    base = timezone.now()
    for i, px in enumerate(closes):
        OHLCBar.objects.create(
            ticker=ticker,
            timeframe="1d",
            open=px,
            high=px,
            low=px,
            close=px,
            volume=1,
            ts=base - timezone.timedelta(days=len(closes) - i),
        )


def test_perfectly_correlated_names_cluster():
    series_a = [100 + i for i in range(40)]
    _seed("NVDA", series_a)
    _seed("AMD", [2 * x for x in series_a])  # same daily returns -> corr 1.0
    _seed("TLT", [200 - i for i in range(40)])  # opposite
    clusters = correlation_clusters(["NVDA", "AMD", "TLT"])
    members = [set(c["members"]) for c in clusters]
    assert any({"NVDA", "AMD"} <= m for m in members)


def test_thin_history_excluded():
    _seed("XYZ", [10, 11])  # < CORR_MIN_BARS
    clusters = correlation_clusters(["XYZ"])
    assert clusters == []
