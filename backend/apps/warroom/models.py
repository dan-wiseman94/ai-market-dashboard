from __future__ import annotations

from typing import ClassVar

from django.db import models


class WarRoomRun(models.Model):
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
        "coverage.CoverageNote", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
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
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"WarRoomRun(#{self.pk} {self.subject_label})"
