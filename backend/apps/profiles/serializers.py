from rest_framework import serializers

from .models import Watchlist, WatchlistSymbol


class WatchlistSymbolSerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchlistSymbol
        fields = ["id", "ticker", "sort_order"]
        read_only_fields = ["sort_order"]


class WatchlistSerializer(serializers.ModelSerializer):
    symbols = WatchlistSymbolSerializer(many=True, read_only=True)

    class Meta:
        model = Watchlist
        fields = ["id", "name", "created_at", "symbols"]
        read_only_fields = ["created_at"]
