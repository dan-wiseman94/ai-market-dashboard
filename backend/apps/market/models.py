"""Market data tables — append-only caches of what we've fetched from Schwab."""
from __future__ import annotations

from typing import ClassVar

from django.db import models


class Quote(models.Model):
    ticker = models.CharField(max_length=16, db_index=True)
    last = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    bid = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    ask = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    volume = models.BigIntegerField(null=True)
    high = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    low = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    pct_change = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    ts = models.DateTimeField(db_index=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["ticker", "-ts"])]

    def __str__(self) -> str:
        return f"Quote({self.ticker}, {self.ts})"


class OHLCBar(models.Model):
    TIMEFRAMES: ClassVar = [("1m", "1m"), ("5m", "5m"), ("15m", "15m"), ("1h", "1h"), ("1d", "1d")]

    ticker = models.CharField(max_length=16)
    timeframe = models.CharField(max_length=4, choices=TIMEFRAMES)
    open = models.DecimalField(max_digits=14, decimal_places=4)
    high = models.DecimalField(max_digits=14, decimal_places=4)
    low = models.DecimalField(max_digits=14, decimal_places=4)
    close = models.DecimalField(max_digits=14, decimal_places=4)
    volume = models.BigIntegerField()
    ts = models.DateTimeField()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["ticker", "timeframe", "ts"], name="uniq_bar"),
        ]
        indexes: ClassVar = [models.Index(fields=["ticker", "timeframe", "-ts"])]

    def __str__(self) -> str:
        return f"OHLCBar({self.ticker}, {self.timeframe}, {self.ts})"


class Position(models.Model):
    ticker = models.CharField(max_length=16, db_index=True)
    qty = models.DecimalField(max_digits=16, decimal_places=6)
    avg_cost = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    mkt_value = models.DecimalField(max_digits=16, decimal_places=4, null=True)
    unrealized_pl = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    day_pl = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    as_of = models.DateTimeField()

    class Meta:
        indexes: ClassVar = [models.Index(fields=["ticker", "-as_of"])]

    def __str__(self) -> str:
        return f"Position({self.ticker}, {self.as_of})"


class MarketContext(models.Model):
    spy_last = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    qqq_last = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    vix_last = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    sectors = models.JSONField(default=dict)
    breadth = models.JSONField(default=dict)
    as_of = models.DateTimeField(db_index=True)

    def __str__(self) -> str:
        return f"MarketContext({self.as_of})"


class OptionChainSnapshot(models.Model):
    """One row per fetch of an option chain. Full chain in JSONB."""

    ticker = models.CharField(max_length=16, db_index=True)
    expiries = models.JSONField(default=list)
    payload = models.JSONField()
    fetched_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["ticker", "-fetched_at"])]

    def __str__(self) -> str:
        return f"OptionChainSnapshot({self.ticker}, {self.fetched_at})"


class NewsItem(models.Model):
    """One row per news article. Deduplicated on (provider, external_id)."""

    provider = models.CharField(max_length=16)
    external_id = models.CharField(max_length=64, db_index=True)
    ticker = models.CharField(max_length=16, db_index=True, blank=True, default="")
    headline = models.CharField(max_length=512)
    summary = models.TextField(blank=True, default="")
    url = models.URLField(max_length=1024)
    source = models.CharField(max_length=64, blank=True, default="")
    published_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["provider", "external_id"], name="uniq_news_provider_id",
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["ticker", "-published_at"])]

    def __str__(self) -> str:
        return f"NewsItem({self.provider}/{self.external_id})"
