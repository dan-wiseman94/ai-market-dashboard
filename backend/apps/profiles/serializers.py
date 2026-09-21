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
    tickers = WatchlistSymbolSerializer(many=True, read_only=True)

    class Meta:
        model = Watchlist
        fields: ClassVar = ["id", "name", "created_at", "tickers"]
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
            "effort",
            "enable_memory",
            "enable_coach",
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = ["created_at", "updated_at"]

    def validate(self, attrs):
        """``default_model`` must belong to ``default_provider``'s catalog — a Claude id
        sent to OpenAI fails every run. Ids the catalog does not know pass verbatim.

        Only a write that touches the pair is checked: a PATCH of an unrelated field
        (the Activate control sends ``{"active": …}``) must not fail on a mismatch the
        user isn't editing — those rows still degrade through the resolver at run time.
        """
        from apps.ai.catalog import foreign_model_error

        if "default_provider" not in attrs and "default_model" not in attrs:
            return attrs
        provider = self._resolved(attrs, "default_provider")
        model = self._resolved(attrs, "default_model")
        err = foreign_model_error(provider, model)
        if err:
            raise serializers.ValidationError({"default_model": err})
        return attrs

    def _resolved(self, attrs, field: str):
        """The value this write resolves to: incoming attr, else the stored value
        (PATCH omits unchanged fields), else the model field's own default — which is
        what an omitted field on create actually persists."""
        if field in attrs:
            return attrs[field]
        if self.instance is not None:
            return getattr(self.instance, field)
        return getattr(TradingProfile(), field)


class MemoryEntrySerializer(serializers.Serializer):
    """One file the model wrote into this profile's memory store."""

    path = serializers.CharField(help_text="Path relative to the profile's memory directory.")
    size_bytes = serializers.IntegerField()
    modified_at = serializers.DateTimeField()
    preview = serializers.CharField(
        allow_blank=True,
        help_text="The first characters of the file, so injected content is visible.",
    )
    preview_truncated = serializers.BooleanField(
        help_text="True when the file is longer than the preview."
    )


class ProfileMemorySerializer(serializers.Serializer):
    """Everything stored under `<AI_MEMORY_ROOT>/<profile_id>/`."""

    profile = serializers.IntegerField()
    exists = serializers.BooleanField(
        help_text="False when the profile has never run with memory on (no directory yet)."
    )
    entries = MemoryEntrySerializer(many=True)
    total_files = serializers.IntegerField()
    total_bytes = serializers.IntegerField()
    preview_chars = serializers.IntegerField(
        help_text="Preview length each entry was truncated to."
    )


class ProfileMemoryClearedSerializer(serializers.Serializer):
    """What a clear removed."""

    profile = serializers.IntegerField()
    removed_files = serializers.IntegerField()
    removed_bytes = serializers.IntegerField()


class ProfileMemoryErrorSerializer(serializers.Serializer):
    """Refusal envelope — the requested id did not resolve inside the memory root."""

    code = serializers.CharField()
    message = serializers.CharField()


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
            "structured",
            "builtin",
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = ["builtin", "created_at", "updated_at"]
