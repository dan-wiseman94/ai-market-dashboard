"""Market data tables — append-only caches of what we've fetched from Schwab."""

from __future__ import annotations

from typing import ClassVar

from django.db import models


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
                fields=["provider", "external_id"],
                name="uniq_news_provider_id",
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["ticker", "-published_at"])]

    def __str__(self) -> str:
        return f"NewsItem({self.provider}/{self.external_id})"
