"""Serializers for the thesis app."""

from __future__ import annotations

from typing import ClassVar

from rest_framework import serializers

from apps.snapshots.models import Snapshot
from apps.threads.models import Thread

from .models import DecisionJournalEntry, PostMortem, Thesis


class PostMortemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostMortem
        fields: ClassVar = [
            "id",
            "horizon_days",
            "due_at",
            "status",
            "forward_return_pct",
            "verdict",
            "report",
            "message_id",
            "created_at",
            "completed_at",
        ]


class ThesisSerializer(serializers.ModelSerializer):
    postmortems = PostMortemSerializer(many=True, read_only=True)
    guard_trigger_id = serializers.SerializerMethodField()

    def get_guard_trigger_id(self, obj):
        g = obj.guard_triggers.first()
        return g.id if g else None

    def validate(self, attrs: dict) -> dict:
        """Pre-trade discipline: a new thesis must state its rationale AND
        what would invalidate it (a price level or a written note). Enforced on
        CREATE only — existing theses can be edited freely (and ORM creates,
        e.g. fixtures, bypass the serializer entirely)."""
        if self.instance is None:
            if not (attrs.get("rationale") or "").strip():
                raise serializers.ValidationError(
                    {"rationale": "State your rationale — why this thesis, and why now."}
                )
            has_invalidation = (
                attrs.get("invalidation_price") is not None
                or (attrs.get("invalidation_note") or "").strip()
            )
            if not has_invalidation:
                raise serializers.ValidationError(
                    {
                        "invalidation_note": (
                            "State what would invalidate this thesis "
                            "(a price level in invalidation_price, or a note)."
                        )
                    }
                )
        return attrs

    class Meta:
        model = Thesis
        fields: ClassVar = [
            "id",
            "title",
            "ticker",
            "direction",
            "rationale",
            "conviction",
            "entry_price",
            "target_price",
            "invalidation_price",
            "invalidation_note",
            "horizon_days",
            "status",
            # FK ids — DRF exposes these as plain integer PK fields by default
            "profile_id",
            "thread_id",
            "snapshot_id",
            "review_thread_id",
            # guard fields
            "guard_enabled",
            "guard_trigger_id",
            # timestamps
            "opened_at",
            "closed_at",
            "close_note",
            "created_at",
            "updated_at",
            "postmortems",
        ]
        read_only_fields: ClassVar = [
            "status",
            "closed_at",
            "created_at",
            "updated_at",
            "guard_trigger_id",
        ]


class JournalEntrySerializer(serializers.ModelSerializer):
    # Explicit PrimaryKeyRelatedField declarations so the serializer reads and
    # writes via *_id keys (consistent with ThesisSerializer convention).
    # No circular import: apps.thesis already imports Thread + Snapshot in views.py.
    thread_id = serializers.PrimaryKeyRelatedField(
        source="thread",
        queryset=Thread.objects.all(),
    )
    thesis_id = serializers.PrimaryKeyRelatedField(
        source="thesis",
        queryset=Thesis.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    snapshot_id = serializers.PrimaryKeyRelatedField(
        source="snapshot",
        queryset=Snapshot.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )

    class Meta:
        model = DecisionJournalEntry
        fields: ClassVar = [
            "id",
            "thread_id",
            "thesis_id",
            "snapshot_id",
            "decision",
            "note",
            "created_at",
        ]
        read_only_fields: ClassVar = ["id", "created_at"]
