"""Coverage API.

GET  /api/coverage/                  list of house-view notes (lean).
GET  /api/coverage/<ticker>/         one note + its full revision history.
POST /api/coverage/<ticker>/revise/  re-run the AI against the latest ready
                                     snapshot for the ticker (a no-op reaffirm is
                                     a valid, successful outcome).
"""

from __future__ import annotations

from typing import ClassVar

from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.snapshots.models import Snapshot
from apps.strategy.coverage.services.revise import revise_coverage
from apps.strategy.models import CoverageNote, CoverageRevision


class CoverageRevisionSerializer(serializers.ModelSerializer):
    source_snapshot_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = CoverageRevision
        fields: ClassVar = ["id", "prior", "new", "reason", "source_snapshot_id", "created_at"]


class CoverageNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoverageNote
        fields: ClassVar = [
            "id",
            "ticker",
            "stance",
            "conviction",
            "bull_case",
            "bear_case",
            "key_levels",
            "watching_for",
            "created_at",
            "updated_at",
        ]


class CoverageNoteDetailSerializer(CoverageNoteSerializer):
    revisions = CoverageRevisionSerializer(many=True, read_only=True)

    class Meta(CoverageNoteSerializer.Meta):
        fields: ClassVar = [*CoverageNoteSerializer.Meta.fields, "revisions"]


class CoverageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read the per-ticker house views; trigger a manual revision."""

    queryset = CoverageNote.objects.all()
    lookup_field = "ticker"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CoverageNoteDetailSerializer
        return CoverageNoteSerializer

    def get_queryset(self):
        qs = CoverageNote.objects.all()
        return qs.prefetch_related("revisions") if self.action == "retrieve" else qs

    def get_object(self):
        # Tickers are stored upper-cased; resolve case-insensitively from the URL.
        self.kwargs[self.lookup_field] = self.kwargs[self.lookup_field].upper()
        return super().get_object()

    @action(detail=True, methods=["post"])
    def revise(self, request, ticker=None):
        ticker = (ticker or "").upper()
        snap = (
            Snapshot.objects.filter(primary_ticker=ticker, status="ready")
            .order_by("-captured_at")
            .first()
        )
        if snap is None:
            return Response(
                {"detail": f"No ready snapshot for {ticker}. Capture one first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rev = revise_coverage(ticker, snap, profile=snap.profile)
        note = CoverageNote.objects.filter(ticker=ticker).prefetch_related("revisions").first()
        return Response(
            {
                "revised": rev is not None,
                "note": CoverageNoteDetailSerializer(note).data if note else None,
            }
        )
