"""Serializers for the portfolio app."""

from __future__ import annotations

from typing import ClassVar

from rest_framework import serializers

from apps.profiles.models import TradingProfile
from apps.thesis.models import Thesis

from .models import Position
from .services import unrealized_pnl


class PositionSerializer(serializers.ModelSerializer):
    # Explicit PrimaryKeyRelatedField declarations so the serializer reads and
    # writes via *_id keys (consistent with JournalEntrySerializer / ThesisSerializer
    # convention — see CLAUDE.md "DRF serializers expose FK ids as *_id").
    thesis_id = serializers.PrimaryKeyRelatedField(
        source="thesis",
        queryset=Thesis.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    profile_id = serializers.PrimaryKeyRelatedField(
        source="profile",
        queryset=TradingProfile.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )

    # Computed mark-to-market P&L (read-only, injected from service).
    unrealized = serializers.SerializerMethodField()

    def get_unrealized(self, obj: Position) -> dict:  # type: ignore[type-arg]
        return unrealized_pnl(obj)

    class Meta:
        model = Position
        fields: ClassVar = [
            "id",
            "ticker",
            "direction",
            "quantity",
            "avg_cost",
            "opened_at",
            "closed_at",
            "close_price",
            "realized_pnl",
            "status",
            "note",
            # FK ids — explicit PrimaryKeyRelatedField above
            "thesis_id",
            "profile_id",
            # computed
            "unrealized",
            # timestamps
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = [
            "id",
            "status",
            "closed_at",
            "realized_pnl",
            "unrealized",
            "created_at",
            "updated_at",
        ]
