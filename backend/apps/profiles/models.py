from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.text import slugify


class Watchlist(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class WatchlistSymbol(models.Model):
    watchlist = models.ForeignKey(Watchlist, related_name="symbols", on_delete=models.CASCADE)
    ticker = models.CharField(max_length=16)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["watchlist", "ticker"], name="uniq_watchlist_ticker"),
        ]
        ordering: ClassVar = ["watchlist_id", "sort_order"]

    def __str__(self) -> str:
        return f"{self.watchlist} / {self.ticker}"

    def save(self, *args, **kwargs) -> None:
        self.ticker = (self.ticker or "").upper()
        super().save(*args, **kwargs)


class TradingProfile(models.Model):
    """A named trading style + AI preferences applied when capturing snapshots."""

    DEFAULT_INCLUDES: ClassVar[list[str]] = ["quotes", "positions", "breadth"]

    name = models.CharField(max_length=100, unique=True)
    style = models.TextField(help_text="The trading style text. Prepended as system prompt.")
    default_includes = models.JSONField(default=list)
    default_provider = models.CharField(max_length=32, default="claude")
    default_model = models.CharField(max_length=100, default="claude-sonnet-4-6")
    active = models.BooleanField(default=True)
    # M10 — opt-in AI platform features (Claude-only surfaces).
    enable_tools = models.BooleanField(
        default=False,
        help_text="Expose the default Toolset (get_quote, fetch_ohlc, search_news, "
        "get_option_chain, compute_indicator) to Claude.",
    )
    enable_thinking = models.BooleanField(
        default=False,
        help_text="Turn on extended thinking on Claude.",
    )
    thinking_budget = models.PositiveIntegerField(
        default=8_000,
        help_text="Thinking token budget when enable_thinking=True. Billed as output.",
    )
    enable_memory = models.BooleanField(
        default=False,
        help_text="Expose the Memory tool with a per-profile namespace under "
        "/data/memory/<profile_id>/.",
    )
    enable_coach = models.BooleanField(
        default=True,
        help_text="Inject the Decision Coach context (prior theses, diff-vs-last "
        "snapshot, per-ticker track record, recall) plus a base observational "
        "system prompt. Off = legacy behavior (system prompt is just the style).",
    )
    skills = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Anthropic Skill ids to attach per run. Empty = none.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-active", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.default_includes:
            self.default_includes = list(self.DEFAULT_INCLUDES)
        super().save(*args, **kwargs)


class AgentPreset(models.Model):
    """A capture template that pre-fills the snapshot composer's objective text."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=300, blank=True, default="")
    objective_template = models.TextField()
    structured = models.BooleanField(default=False)
    builtin = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-active", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
