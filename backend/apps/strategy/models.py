"""Strategy domain — the AI's active deliberation + house-view surfaces.

Consolidates the former apps.coverage (per-ticker house view), apps.warroom
(multi-agent debate), and apps.desk (anomaly sweep) per the 27→12 plan. These three
formed a closed FK-connected component (warroom→coverage, desk→warroom), so they had
to merge together — co-locating them turns those cross-app FKs into intra-app ones.
Every model pins ``db_table`` to its original name so the move preserves the tables.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class CoverageNote(models.Model):
    """Living per-ticker house view the AI revises with a reason (was apps.coverage)."""

    STANCE_CHOICES: ClassVar = [("bull", "Bull"), ("bear", "Bear"), ("neutral", "Neutral")]

    ticker = models.CharField(max_length=16, unique=True)
    stance = models.CharField(max_length=8, choices=STANCE_CHOICES, default="neutral")
    conviction = models.PositiveSmallIntegerField(default=1)
    bull_case = models.TextField(blank=True, default="")
    bear_case = models.TextField(blank=True, default="")
    key_levels = models.JSONField(default=dict)
    watching_for = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "coverage_coveragenote"
        ordering: ClassVar = ["ticker"]

    def __str__(self) -> str:
        return f"CoverageNote({self.ticker} {self.stance} c{self.conviction})"


class CoverageRevision(models.Model):
    """Append-only revision audit of a CoverageNote (was apps.coverage)."""

    note = models.ForeignKey(CoverageNote, on_delete=models.CASCADE, related_name="revisions")
    prior = models.JSONField(default=dict)
    new = models.JSONField(default=dict)
    reason = models.TextField()
    source_snapshot = models.ForeignKey(
        "snapshots.Snapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "coverage_coveragerevision"
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"CoverageRevision(#{self.pk} note={self.note_id})"


class WarRoomRun(models.Model):
    """Multi-agent 'courtroom' debate run (was apps.warroom). Streams over
    thread.<id> via run_ai_on_message; persists the synthesized verdict."""

    STATUS_CHOICES: ClassVar = [("running", "Running"), ("done", "Done"), ("error", "Error")]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    thread = models.ForeignKey(
        "threads.Thread", on_delete=models.CASCADE, related_name="warroom_runs"
    )
    subject_kind = models.CharField(max_length=16)  # thesis | coverage | book | free
    subject_label = models.CharField(max_length=200, blank=True, default="")
    thesis = models.ForeignKey(
        "thesis.Thesis", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    coverage_note = models.ForeignKey(
        "strategy.CoverageNote", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    book_snapshot = models.ForeignKey(
        "book.BookSnapshot", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    free_prompt = models.TextField(blank=True, default="")
    params = models.JSONField(default=dict)
    verdict = models.JSONField(default=dict)
    confidence = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="done")
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "warroom_warroomrun"
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"WarRoomRun(#{self.pk} {self.subject_label})"


class DeskEntry(models.Model):
    """Agentic anomaly-sweep finding (was apps.desk)."""

    STATUS_CHOICES: ClassVar = [("new", "New"), ("acted", "Acted"), ("dismissed", "Dismissed")]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    anomaly_type = models.CharField(max_length=32, db_index=True)
    ticker = models.CharField(
        max_length=16, blank=True, default="", db_index=True
    )  # "" = book-wide
    severity = models.FloatField(default=0.0)
    evidence = models.JSONField(default=dict)
    finding = models.TextField(blank=True, default="")
    suggested_actions = models.JSONField(default=list)  # [{"type","label","params"}]
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="new", db_index=True)
    warroom_run = models.ForeignKey(
        "strategy.WarRoomRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    investigation_thread = models.ForeignKey(
        "threads.Thread", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "desk_deskentry"
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["ticker", "anomaly_type", "-created_at"])]

    def __str__(self) -> str:
        return f"DeskEntry({self.anomaly_type} {self.ticker or 'book'})"


class RegimeReading(models.Model):
    """Append-only market-regime reading (moved from apps.regime); the latest row is
    the current regime. Completes the M15 strategist cluster here. No FKs — a leaf."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    composite = models.CharField(max_length=20)
    axes = models.JSONField(default=dict)
    drivers = models.JSONField(default=list)
    narrative = models.TextField(blank=True, default="")
    inputs = models.JSONField(default=dict)
    changed_axes = models.JSONField(default=list)

    class Meta:
        db_table = "regime_regimereading"
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"RegimeReading({self.composite} @ {self.created_at:%Y-%m-%d %H:%M})"
