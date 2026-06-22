"""Themes CRUD + narrative health (#18)."""

from __future__ import annotations

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.market.models import Theme


class ThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Theme
        fields = ["id", "name", "tickers", "note", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ThemeViewSet(viewsets.ModelViewSet):
    queryset = Theme.objects.all()
    serializer_class = ThemeSerializer

    @action(detail=True, methods=["get"])
    def health(self, request: Request, pk: str | None = None) -> Response:
        from apps.market.services.themes import theme_health

        theme = self.get_object()
        try:
            window = max(2, min(250, int(request.query_params.get("window_days", "20"))))
        except (TypeError, ValueError):
            window = 20
        return Response(theme_health(theme, window_days=window))
