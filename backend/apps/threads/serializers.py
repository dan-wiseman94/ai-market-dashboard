from typing import ClassVar

from rest_framework import serializers

from apps.profiles.models import TradingProfile

from .models import AIRun, Message, Thread


class AIRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIRun
        fields: ClassVar = [
            "id",
            "provider",
            "model",
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "cost_usd",
            "latency_ms",
            "status",
            "error",
        ]


class MessageSerializer(serializers.ModelSerializer):
    ai_run = AIRunSerializer(read_only=True)
    parent_message_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Message
        fields: ClassVar = [
            "id",
            "role",
            "content",
            "status",
            "error",
            "created_at",
            "ai_run",
            "parent_message_id",
        ]


class ProfileInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingProfile
        fields: ClassVar = ["id", "name", "default_provider", "default_model"]


class ThreadSerializer(serializers.ModelSerializer):
    profile = ProfileInlineSerializer(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Thread
        fields: ClassVar = [
            "id",
            "kind",
            "title",
            "profile",
            "pinned_snapshot_id",
            "created_at",
            "messages",
        ]
