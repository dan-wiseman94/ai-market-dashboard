"""Market data tables — append-only caches of what we've fetched from Schwab."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.market.calendar.registry import MARKET_CHOICES


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


class CalendarOverride(models.Model):
    """Explicit symbol -> market-key override; beats heuristics in calendar_for()."""

    symbol = models.CharField(max_length=16, unique=True)
    market_key = models.CharField(max_length=16, choices=MARKET_CHOICES)
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.symbol} -> {self.market_key}"

    def save(self, *args, **kwargs) -> None:
        self.symbol = (self.symbol or "").strip().upper()
        super().save(*args, **kwargs)
        from apps.market.calendar.resolve import clear_resolution_cache

        clear_resolution_cache()

    def delete(self, *args, **kwargs):
        from apps.market.calendar.resolve import clear_resolution_cache

        result = super().delete(*args, **kwargs)
        clear_resolution_cache()
        return result


class MarketEvent(models.Model):
    """A scheduled market catalyst — per-ticker earnings or curated US macro. Deduped on (source, external_id)."""

    KINDS: ClassVar = [
        ("earnings", "earnings"),
        ("fomc", "fomc"),
        ("cpi", "cpi"),
        ("nfp", "nfp"),
        ("pce", "pce"),
        ("gdp", "gdp"),
    ]
    source = models.CharField(max_length=16)  # "finnhub" | "seed"
    external_id = models.CharField(max_length=80, db_index=True)
    kind = models.CharField(max_length=16, choices=KINDS)
    ticker = models.CharField(max_length=16, blank=True, default="", db_index=True)
    title = models.CharField(max_length=200)
    event_time = models.DateTimeField(db_index=True)
    when_hint = models.CharField(max_length=8, blank=True, default="")  # bmo|amc|""
    impact = models.CharField(max_length=8, blank=True, default="")  # high|medium|low
    detail = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["source", "external_id"], name="uniq_event_source_id"),
        ]
        indexes: ClassVar = [
            models.Index(fields=["ticker", "event_time"]),
            models.Index(fields=["kind", "event_time"]),
            models.Index(fields=["event_time"]),
        ]

    def __str__(self) -> str:
        return f"MarketEvent({self.kind}, {self.ticker or '-'}, {self.event_time:%Y-%m-%d})"


class CompanyFundamentals(models.Model):
    """Current-snapshot fundamental metrics for a single ticker. Upserted on each fetch."""

    ticker = models.CharField(max_length=16, db_index=True)
    sector = models.CharField(max_length=64, blank=True, default="")
    industry = models.CharField(max_length=96, blank=True, default="")
    metrics = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["ticker"], name="uniq_fundamentals_ticker"),
        ]

    def __str__(self) -> str:
        return f"CompanyFundamentals({self.ticker})"


class CorporateAction(models.Model):
    """A stock split or dividend, keyed by ex-date. Deduped on (source, external_id).

    Used by ``apps.market.returns`` to adjust forward-return math so a split
    doesn't read as a crash. ``ratio`` is ``shares_after / shares_before`` for a
    split (3:1 forward → 3.0; 1:10 reverse → 0.1); ``amount`` is cash-per-share
    for a dividend. Each row uses exactly one of the two.
    """

    KINDS: ClassVar = [("split", "split"), ("dividend", "dividend")]

    source = models.CharField(max_length=16)  # "finnhub" | "mock"
    external_id = models.CharField(max_length=80, db_index=True)
    kind = models.CharField(max_length=16, choices=KINDS)
    ticker = models.CharField(max_length=16, db_index=True)
    ex_date = models.DateField(db_index=True)
    # Split ratio = shares_after / shares_before (price divides by this). Null for dividends.
    ratio = models.DecimalField(max_digits=16, decimal_places=6, null=True, blank=True)
    # Dividend cash per share. Null for splits.
    amount = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    detail = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="uniq_corpaction_source_id"
            ),
        ]
        indexes: ClassVar = [
            models.Index(fields=["ticker", "ex_date"]),
            models.Index(fields=["kind", "ex_date"]),
        ]

    def __str__(self) -> str:
        return f"CorporateAction({self.kind}, {self.ticker}, {self.ex_date})"
