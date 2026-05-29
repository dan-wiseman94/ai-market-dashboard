from __future__ import annotations

from typing import ClassVar

from rest_framework import serializers

from .models import AgentPreset, TradingProfile, Watchlist, WatchlistSymbol


class WatchlistSymbolSerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchlistSymbol
        fields: ClassVar = ["id", "ticker", "sort_order"]
        read_only_fields: ClassVar = ["sort_order"]


class WatchlistSerializer(serializers.ModelSerializer):
    symbols = WatchlistSymbolSerializer(many=True, read_only=True)

    class Meta:
        model = Watchlist
        fields: ClassVar = ["id", "name", "created_at", "symbols"]
        read_only_fields: ClassVar = ["created_at"]


class TradingProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingProfile
        fields: ClassVar = [
            "id",
            "name",
            "style",
            "default_includes",
            "default_provider",
            "default_model",
            "enable_tools",
            "enable_thinking",
            "thinking_budget",
            "enable_memory",
            "enable_coach",
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = ["created_at", "updated_at"]


class AgentPresetSerializer(serializers.ModelSerializer):
    # slug is optional on create — the model auto-generates from name when blank.
    slug = serializers.SlugField(required=False, allow_blank=True, default="")

    class Meta:
        model = AgentPreset
        fields: ClassVar = [
            "id",
            "name",
            "slug",
            "description",
            "objective_template",
            "default_includes",
            "structured",
            "builtin",
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = ["builtin", "created_at", "updated_at"]
