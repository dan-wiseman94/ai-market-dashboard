"""Serializers for the thesis app."""

from __future__ import annotations

from typing import ClassVar

from rest_framework import serializers

from .models import PostMortem, Thesis


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
            "horizon_days",
            "status",
            # FK ids — DRF exposes these as plain integer PK fields by default
            "profile_id",
            "thread_id",
            "snapshot_id",
            "review_thread_id",
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
        ]
