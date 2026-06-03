from __future__ import annotations

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AgentPreset, TradingProfile, Watchlist, WatchlistSymbol
from .serializers import (
    AgentPresetSerializer,
    TradingProfileSerializer,
    WatchlistSerializer,
    WatchlistSymbolSerializer,
)


class WatchlistViewSet(viewsets.ModelViewSet):
    queryset = Watchlist.objects.prefetch_related("symbols")
    serializer_class = WatchlistSerializer

    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        """Body: {'order': [symbol_id, ...]}"""
        wl = self.get_object()
        if not isinstance(request.data, dict):
            return Response({"detail": "Request body must be a JSON object."}, status=400)
        ids = request.data.get("order", [])
        if not isinstance(ids, list):
            return Response({"detail": "'order' must be a list."}, status=400)
        with transaction.atomic():
            for idx, sid in enumerate(ids):
                WatchlistSymbol.objects.filter(id=sid, watchlist=wl).update(sort_order=idx)
        return Response({"ok": True})


class WatchlistSymbolViewSet(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    serializer_class = WatchlistSymbolSerializer

    def get_queryset(self):
        return WatchlistSymbol.objects.filter(watchlist_id=self.kwargs["watchlist_pk"])

    def create(self, request, *args, **kwargs):
        wl = get_object_or_404(Watchlist, pk=self.kwargs["watchlist_pk"])
        ticker = request.data.get("ticker", "").upper()
        if not ticker:
            return Response(
                {"code": "invalid_input", "message": "ticker is required"},
                status=400,
            )
        try:
            sym = WatchlistSymbol.objects.create(
                watchlist=wl,
                ticker=ticker,
                sort_order=wl.symbols.count(),
            )
        except IntegrityError:
            return Response(
                {"code": "duplicate", "message": f"{ticker} is already in this watchlist"},
                status=400,
            )
        return Response(WatchlistSymbolSerializer(sym).data, status=201)


class TradingProfileViewSet(viewsets.ModelViewSet):
    queryset = TradingProfile.objects.all()
    serializer_class = TradingProfileSerializer


class AgentPresetViewSet(viewsets.ModelViewSet):
    queryset = AgentPreset.objects.all()
    serializer_class = AgentPresetSerializer

    def create(self, request, *args, **kwargs):
        return self._handle_slug_collision(super().create, request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        return self._handle_slug_collision(super().update, request, *args, **kwargs)

    @staticmethod
    def _handle_slug_collision(handler, request, *args, **kwargs):
        """Turn a unique-slug IntegrityError into a 400 instead of a 500."""
        try:
            return handler(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {"code": "duplicate", "message": "A preset with this slug already exists."},
                status=400,
            )
