"""Living house view per ticker (M14 F3 COVERAGE).

Fixes the "amnesiac-by-snapshot" limitation: each watchlist name gets ONE
persistent ``CoverageNote`` — a maintained research view (stance / conviction /
bull case / bear case / key levels / watching-for) the AI *revises with a
reason*, behind a hysteresis gate, instead of re-deriving it every snapshot.
``CoverageRevision`` is the append-only audit trail of those revisions, so the
house view is version-controlled and you can read *why* it moved.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class CoverageNote(models.Model):
    STANCE_CHOICES: ClassVar = [
        ("bull", "Bull"),
        ("bear", "Bear"),
        ("neutral", "Neutral"),
    ]

    ticker = models.CharField(max_length=16, unique=True)
    stance = models.CharField(max_length=8, choices=STANCE_CHOICES, default="neutral")
    conviction = models.PositiveSmallIntegerField(default=1)  # 1 (low) .. 5 (high)
    bull_case = models.TextField(blank=True, default="")
    bear_case = models.TextField(blank=True, default="")
    key_levels = models.JSONField(default=dict)  # {"label": price, ...} or richer
    watching_for = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar = ["ticker"]

    def __str__(self) -> str:
        return f"CoverageNote({self.ticker} {self.stance} c{self.conviction})"


class CoverageRevision(models.Model):
    """One append-only revision of a CoverageNote — what the view was, what it
    became, and the reason. ``source_snapshot`` is SET_NULL so pruning old
    snapshots never deletes the audit trail."""

    note = models.ForeignKey(
        CoverageNote,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    prior = models.JSONField(default=dict)  # the note before this revision
    new = models.JSONField(default=dict)  # the revised note
    reason = models.TextField()  # WHY the view changed (or was reaffirmed)
    source_snapshot = models.ForeignKey(
        "snapshots.Snapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"CoverageRevision(#{self.pk} note={self.note_id})"
