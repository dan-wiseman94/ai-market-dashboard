from typing import ClassVar

from rest_framework import serializers

from .models import ProviderConfig


class ProviderConfigSerializer(serializers.ModelSerializer):
    api_key_present = serializers.SerializerMethodField()
    api_key_write = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ProviderConfig
        fields: ClassVar = [
            "provider", "base_url", "default_model", "enabled", "supports_vision",
            "daily_cost_cap_usd", "monthly_cost_cap_usd",
            "api_key_present", "api_key_write",
        ]

    def get_api_key_present(self, obj) -> bool:
        return bool(obj.api_key)

    def update(self, instance, validated_data):
        key = validated_data.pop("api_key_write", None)
        instance = super().update(instance, validated_data)
        if key is not None:
            instance.api_key = key
            instance.save()
        return instance

    def create(self, validated_data):
        key = validated_data.pop("api_key_write", None)
        instance = super().create(validated_data)
        if key is not None:
            instance.api_key = key
            instance.save()
        return instance
