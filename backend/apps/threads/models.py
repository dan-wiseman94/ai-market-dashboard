"""Conversations: Thread + Message + AIRun."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


class Thread(models.Model):
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("consult", "One-shot consult"),
        ("chat", "Ongoing chat"),
        ("observer", "Observer timeline"),
        ("briefing", "Morning briefing"),
        ("diff", "Diff"),
    ]

    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="consult")
    title = models.CharField(max_length=200, blank=True, default="")
    profile = models.ForeignKey(
        TradingProfile,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="threads",
    )
    pinned_snapshot = models.ForeignKey(
        Snapshot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="threads",
    )
    schedule = models.ForeignKey(
        "observer.ObserverSchedule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="threads",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["kind", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title or f'#{self.pk}'}"


class Message(models.Model):
    ROLE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("done", "Done"),
        ("streaming", "Streaming"),
        ("failed", "Failed"),
    ]

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.JSONField(default=dict)
    snapshot_ref = models.ForeignKey(
        Snapshot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="messages_referencing",
    )
    parent_message = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="branches",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="done")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["thread_id", "created_at"]
        indexes: ClassVar = [models.Index(fields=["thread_id", "created_at"])]

    def __str__(self) -> str:
        return f"{self.role}@thread#{self.thread_id}"


class AIRun(models.Model):
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("streaming", "Streaming"),
        ("done", "Done"),
        ("failed", "Failed"),
        ("cost_capped", "Cost capped"),
    ]

    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="ai_run")
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=100)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cached_tokens = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    error = models.TextField(blank=True, default="")
    raw_request_summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["created_at"], name="airun_created_idx"),
            models.Index(fields=["provider", "model", "created_at"], name="airun_prov_model_idx"),
        ]

    def __str__(self) -> str:
        return f"AIRun {self.provider}/{self.model} (${self.cost_usd})"


class ToolCall(models.Model):
    """Audit row for one tool_use → tool_result round-trip inside an AI run."""

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="tool_calls",
    )
    tool_use_id = models.CharField(max_length=64)
    tool_name = models.CharField(max_length=64)
    tool_input = models.JSONField(default=dict)
    tool_output = models.JSONField(default=dict)
    ok = models.BooleanField(default=True)
    error = models.TextField(blank=True, default="")
    latency_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["message", "created_at"])]
        ordering: ClassVar[list[str]] = ["message_id", "created_at"]

    def __str__(self) -> str:
        return f"ToolCall({self.tool_name}, ok={self.ok})"
