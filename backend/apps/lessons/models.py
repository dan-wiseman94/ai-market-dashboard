"""Distilled lessons (M14 F2): recurring, tagged rules clustered from decisive
post-mortems. The embedding (a plain JSON list of floats — lessons are few, so
cosine runs in Python during the batch distillation, no pgvector needed) drives
the greedy clustering; `tags` records the directions/sectors the cluster spans so
the coach can match it to the current situation."""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class Lesson(models.Model):
    text = models.TextField(help_text="Representative bullet of the cluster.")
    embedding = models.JSONField(null=True, blank=True)  # list[float], for cosine clustering
    tags = models.JSONField(default=dict)  # {"directions": [...], "sectors": [...]}
    evidence = models.ManyToManyField("thesis.PostMortem", related_name="lessons", blank=True)
    support_n = models.PositiveIntegerField(
        default=0, help_text="Number of post-mortems supporting this lesson."
    )
    muted = models.BooleanField(default=False, help_text="Hidden from the coach when True.")
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar = ["-support_n", "-last_seen"]
        indexes: ClassVar = [models.Index(fields=["muted", "-support_n"])]

    def __str__(self) -> str:
        return f"Lesson(#{self.pk} n={self.support_n} {self.text[:40]!r})"
