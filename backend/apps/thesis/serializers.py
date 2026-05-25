"""Serializers for the thesis app."""

from __future__ import annotations

from typing import ClassVar

from rest_framework import serializers

from .models import Thesis


class ThesisSerializer(serializers.ModelSerializer):
    # Phase 2 will add: postmortems = PostMortemSerializer(many=True, read_only=True)

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
        ]
        read_only_fields: ClassVar = [
            "status",
            "closed_at",
            "created_at",
            "updated_at",
        ]
