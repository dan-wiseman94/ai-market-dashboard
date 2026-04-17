"""Watchlist + WatchlistSymbol CRUD + reorder."""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Watchlist, WatchlistSymbol
from .serializers import WatchlistSerializer, WatchlistSymbolSerializer


class WatchlistViewSet(viewsets.ModelViewSet):
    queryset = Watchlist.objects.prefetch_related("symbols")
    serializer_class = WatchlistSerializer

    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        """Body: {'order': [symbol_id, ...]}"""
        wl = self.get_object()
        ids = request.data.get("order", [])
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
        next_order = wl.symbols.count()
        try:
            sym = WatchlistSymbol.objects.create(watchlist=wl, ticker=ticker, sort_order=next_order)
        except IntegrityError:
            return Response(
                {"code": "duplicate", "message": f"{ticker} is already in this watchlist"},
                status=400,
            )
        return Response(WatchlistSymbolSerializer(sym).data, status=201)
