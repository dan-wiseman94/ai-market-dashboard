from typing import ClassVar

from cryptography.fernet import InvalidToken
from rest_framework import serializers

from .models import ProviderConfig


class ProviderConfigSerializer(serializers.ModelSerializer):
    api_key_present = serializers.SerializerMethodField()
    api_key_write = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ProviderConfig
        fields: ClassVar = [
            "provider",
            "base_url",
            "default_model",
            "enabled",
            "supports_vision",
            "supports_tools",
            "daily_cost_cap_usd",
            "monthly_cost_cap_usd",
            "api_key_present",
            "api_key_write",
            "discovered_models",
            "models_synced_at",
        ]
        read_only_fields: ClassVar = ["discovered_models", "models_synced_at"]

    def get_api_key_present(self, obj) -> bool:
        # A key that can't be decrypted (DJANGO_SECRET_KEY / salt rotation) is unusable,
        # so report it as absent: avoids 500-ing the list/detail endpoint and prompts the
        # user to re-enter it. Reachable because the viewset defers `_api_key`, so the
        # decrypt is attempted lazily here rather than crashing the row fetch.
        try:
            return bool(obj.api_key)
        except InvalidToken:
            return False

    def update(self, instance, validated_data):
        key = validated_data.pop("api_key_write", None)
        instance = super().update(instance, validated_data)
        return self._apply_api_key(instance, key)

    def create(self, validated_data):
        key = validated_data.pop("api_key_write", None)
        instance = super().create(validated_data)
        return self._apply_api_key(instance, key)

    @staticmethod
    def _apply_api_key(instance, key):
        """Persist the write-only api_key onto the (already-saved) instance."""
        if key is not None:
            instance.api_key = key
            instance.save()
        return instance
