"""Thesis domain — a user's tracked directional call on a ticker."""

from __future__ import annotations

from typing import ClassVar

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.model_bases import Resolution


class Thesis(models.Model):
    DIRECTION_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("bullish", "Bullish"),
        ("bearish", "Bearish"),
        ("neutral", "Neutral"),
    ]
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("open", "Open"),
        ("closed_win", "Closed — Win"),
        ("closed_loss", "Closed — Loss"),
        ("closed_scratch", "Closed — Scratch"),
        ("invalidated", "Invalidated"),
    ]

    title = models.CharField(max_length=200)
    ticker = models.CharField(max_length=16)
    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES)
    rationale = models.TextField(blank=True, default="")
    conviction = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    entry_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    target_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    invalidation_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    # Written "what would prove me wrong" — the pre-trade discipline field.
    # Optional at the model layer (existing rows / ORM creates); required on API
    # create by ThesisSerializer.validate, alongside a non-empty rationale.
    invalidation_note = models.TextField(blank=True, default="")
    horizon_days = models.IntegerField(default=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")

    # FK references — all optional (SET_NULL) to survive related-object deletions
    profile = models.ForeignKey(
        "profiles.TradingProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theses",
    )
    thread = models.ForeignKey(
        "threads.Thread",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theses",
        help_text="Source thread from which this thesis was opened.",
    )
    snapshot = models.ForeignKey(
        "snapshots.Snapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theses",
        help_text="Market state at the time the thesis was opened.",
    )
    review_thread = models.ForeignKey(
        "threads.Thread",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_theses",
        help_text="Thread where post-mortems are posted.",
    )

    guard_enabled = models.BooleanField(default=False)

    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-opened_at"]
        indexes: ClassVar = [models.Index(fields=["status", "-opened_at"])]

    def __str__(self) -> str:
        return f"Thesis({self.ticker} {self.direction} {self.status})"

    def save(self, *args, **kwargs) -> None:
        # Strip before upper: a padded ticker breaks exact-key joins against
        # OHLC/quote lookups keyed on the canonical symbol.
        self.ticker = (self.ticker or "").strip().upper()
        super().save(*args, **kwargs)


class DecisionJournalEntry(models.Model):
    """A user's recorded decision on a thread — what action they took and why."""

    DECISION_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("acted", "Acted"),
        ("passed", "Passed"),
        ("watching", "Watching"),
        ("hedged", "Hedged"),
    ]

    thread = models.ForeignKey(
        "threads.Thread",
        on_delete=models.CASCADE,
        related_name="journal_entries",
    )
    thesis = models.ForeignKey(
        Thesis,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="journal_entries",
    )
    snapshot = models.ForeignKey(
        "snapshots.Snapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="journal_entries",
    )
    decision = models.CharField(max_length=16, choices=DECISION_CHOICES)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["thread", "-created_at"])]

    def __str__(self) -> str:
        return f"DecisionJournalEntry(thread#{self.thread_id} {self.decision})"


class PostMortem(Resolution):
    """A scheduled review of a thesis at a fixed horizon after it was opened.

    Closes the decision loop: at 7/30/90 days we compute the ACTUAL forward
    return + price path, assign a deterministic verdict (so the loop closes
    even with no AI key), and best-effort generate an AI narrative.
    """

    # "running" is the in-flight claim between an atomic dispatch and completion;
    # the run_postmortem claim transitions scheduled -> running -> done. "failed"
    # and "skipped" are reserved — graceful-degradation AI failures intentionally
    # stay "done" with report={} per the design, so they are not set today.
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("scheduled", "Scheduled"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]
    thesis = models.ForeignKey(
        Thesis,
        on_delete=models.CASCADE,
        related_name="postmortems",
    )
    horizon_days = models.IntegerField()
    due_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="scheduled")
    report = models.JSONField(default=dict)
    message = models.ForeignKey(
        "threads.Message",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The assistant Message posted into the review thread, if any.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["thesis_id", "horizon_days"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["thesis", "horizon_days"], name="uniq_thesis_horizon"),
        ]

    def __str__(self) -> str:
        return f"PostMortem(thesis#{self.thesis_id} {self.horizon_days}d {self.status})"


class Position(models.Model):
    """Manually maintained position record — the broker-position leg of the thesis
    loop. Strictly observational — no broker write path. ``db_table`` pinned to
    ``portfolio_position`` (see migration 0008). P&L is computed off stored OHLC bars.
    """

    DIRECTION_CHOICES: ClassVar = [("long", "Long"), ("short", "Short")]
    STATUS_CHOICES: ClassVar = [("open", "Open"), ("closed", "Closed")]

    ticker = models.CharField(max_length=16, db_index=True)
    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES, default="long")
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    avg_cost = models.DecimalField(max_digits=14, decimal_places=4)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    realized_pnl = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default="open", db_index=True)
    note = models.TextField(blank=True, default="")
    thesis = models.ForeignKey(
        "thesis.Thesis",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="positions",
    )
    profile = models.ForeignKey(
        "profiles.TradingProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="positions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "portfolio_position"
        ordering: ClassVar = ["-opened_at"]
        indexes: ClassVar = [
            models.Index(fields=["status", "-opened_at"]),
            models.Index(fields=["ticker", "status"]),
        ]

    def __str__(self) -> str:
        return f"Position({self.ticker}, {self.direction}, {self.status})"

    def save(self, *args, **kwargs):
        # Strip before upper: a padded ticker breaks exact-key joins against
        # OHLC/quote lookups keyed on the canonical symbol.
        self.ticker = (self.ticker or "").strip().upper()
        super().save(*args, **kwargs)


class Lesson(models.Model):
    """Distilled recurring lesson: clustered from decisive post-mortems, fed to the
    Coach. The embedding is a plain JSON float list (few lessons → cosine in Python).
    ``db_table`` pinned to ``lessons_lesson`` (preserves the table + its M2M).
    """

    text = models.TextField(help_text="Representative bullet of the cluster.")
    embedding = models.JSONField(null=True, blank=True)
    tags = models.JSONField(default=dict)
    evidence = models.ManyToManyField("thesis.PostMortem", related_name="lessons", blank=True)
    support_n = models.PositiveIntegerField(
        default=0, help_text="Number of post-mortems supporting this lesson."
    )
    muted = models.BooleanField(default=False, help_text="Hidden from the coach when True.")
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lessons_lesson"
        ordering: ClassVar = ["-support_n", "-last_seen"]
        indexes: ClassVar = [models.Index(fields=["muted", "-support_n"])]

    def __str__(self) -> str:
        return f"Lesson(#{self.pk} n={self.support_n} {self.text[:40]!r})"
