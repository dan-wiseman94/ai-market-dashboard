"""Watchlists. (TradingProfile comes in M3.)"""
from __future__ import annotations

from django.db import models


class Watchlist(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WatchlistSymbol(models.Model):
    watchlist = models.ForeignKey(Watchlist, related_name="symbols", on_delete=models.CASCADE)
    ticker = models.CharField(max_length=16)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["watchlist", "ticker"], name="uniq_watchlist_ticker"),
        ]
        ordering = ["watchlist_id", "sort_order"]

    def save(self, *args, **kwargs) -> None:
        self.ticker = (self.ticker or "").upper()
        super().save(*args, **kwargs)
