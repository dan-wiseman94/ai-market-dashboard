from rest_framework import mixins, viewsets
from rest_framework.response import Response

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.serializers import SnapshotSerializer
from apps.snapshots.tasks import capture_task


class SnapshotViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    queryset = Snapshot.objects.prefetch_related("sections")
    serializer_class = SnapshotSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        try:
            profile = TradingProfile.objects.get(id=data.get("profile_id"))
        except TradingProfile.DoesNotExist:
            return Response({"code": "invalid_profile", "message": "No such profile"}, status=400)

        snap = Snapshot.objects.create(
            profile=profile,
            objective=data.get("objective", ""),
            notes=data.get("notes", ""),
            includes=data.get("includes") or profile.default_includes,
            source="manual",
            status="pending",
        )
        capture_task.delay(
            snapshot_id=snap.id,
            watchlist_tickers=data.get("watchlist_tickers") or [],
            ohlc_ticker=data.get("ohlc_ticker"),
            ohlc_timeframe=data.get("ohlc_timeframe", "1m"),
            ohlc_bars=data.get("ohlc_bars", 60),
        )
        return Response(SnapshotSerializer(snap).data, status=202)
