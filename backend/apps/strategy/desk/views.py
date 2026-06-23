from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.strategy.desk.serializers import DeskEntrySerializer
from apps.strategy.models import DeskEntry
from apps.strategy.warroom.services.convene import convene


def _revise_coverage_action(ticker: str) -> bool:
    """Best-effort: revise the house view on `ticker` using its latest ready snapshot
    + the first available profile. Returns True if a revision attempt ran."""
    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot
    from apps.strategy.coverage.services.revise import revise_coverage

    snap = (
        Snapshot.objects.filter(primary_ticker=ticker.upper(), status="ready")
        .order_by("-captured_at")
        .first()
    )
    if snap is None:
        return False
    revise_coverage(ticker.upper(), snap, profile=TradingProfile.objects.first())
    return True


class DeskViewSet(ReadOnlyModelViewSet):
    queryset = DeskEntry.objects.all()
    serializer_class = DeskEntrySerializer

    @action(detail=False, methods=["post"])
    def sweep(self, request: Request) -> Response:
        # Dispatch off the request thread: a sweep runs N AI investigations and
        # would otherwise block the HTTP call for many seconds (and dollars).
        from apps.strategy.tasks import sweep_now

        task = sweep_now.delay()
        return Response({"task_id": str(task.id), "status": "queued"}, status=202)

    @action(detail=True, methods=["post"])
    def dismiss(self, request: Request, pk=None) -> Response:
        entry = self.get_object()
        entry.status = "dismissed"
        entry.save(update_fields=["status"])
        return Response(DeskEntrySerializer(entry).data)

    @action(detail=True, methods=["post"])
    def act(self, request: Request, pk=None) -> Response:
        entry = self.get_object()
        if request.data.get("action") == "convene_warroom":
            params = {}
            for a in entry.suggested_actions or []:
                if a.get("type") == "convene_warroom":
                    params = a.get("params", {})
                    break
            run = convene(free_prompt=params.get("free_prompt") or f"Debate: {entry.finding}")
            entry.warroom_run = run
            entry.status = "acted"
            entry.save(update_fields=["warroom_run", "status"])
        elif request.data.get("action") == "revise_coverage":
            ticker = ""
            for a in entry.suggested_actions or []:
                if a.get("type") == "revise_coverage":
                    ticker = (a.get("params") or {}).get("ticker", "")
                    break
            if ticker:
                _revise_coverage_action(ticker)
                entry.status = "acted"
                entry.save(update_fields=["status"])
        return Response(DeskEntrySerializer(entry).data)
