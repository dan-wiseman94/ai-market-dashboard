from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.desk.models import DeskEntry
from apps.desk.serializers import DeskEntrySerializer
from apps.desk.services.sweep import run_sweep
from apps.warroom.services.convene import convene


class DeskViewSet(ReadOnlyModelViewSet):
    queryset = DeskEntry.objects.all()
    serializer_class = DeskEntrySerializer

    @action(detail=False, methods=["post"])
    def sweep(self, request: Request) -> Response:
        return Response({"created": run_sweep()})

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
        return Response(DeskEntrySerializer(entry).data)
