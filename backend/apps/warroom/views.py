from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.warroom.models import WarRoomRun
from apps.warroom.serializers import WarRoomRunSerializer
from apps.warroom.services.convene import convene


def _subject_models() -> dict:
    """Return a static mapping of kwarg-name -> Django model class.

    Imported lazily to avoid circular imports at module load time.
    The mapping is fixed — never derived from request data — so there
    is no dynamic-import / arbitrary-code-load risk.
    """
    from apps.coverage.models import CoverageNote
    from apps.thesis.models import Thesis

    # apps.book may not exist yet; degrade gracefully
    try:
        from apps.book.models import BookSnapshot

        book_cls = BookSnapshot
    except ImportError:
        book_cls = None

    mapping: dict = {"thesis": Thesis, "coverage_note": CoverageNote}
    if book_cls is not None:
        mapping["book_snapshot"] = book_cls
    return mapping


class WarRoomViewSet(ReadOnlyModelViewSet):
    queryset = WarRoomRun.objects.all()
    serializer_class = WarRoomRunSerializer

    @action(detail=False, methods=["post"])
    def convene(self, request: Request) -> Response:
        d = request.data
        kwargs: dict = {
            "free_prompt": d.get("free_prompt", ""),
            "structure": d.get("structure", "rebuttal"),
            "voice_mode": d.get("voice_mode", "single"),
            "grounding": bool(d.get("grounding", True)),
        }
        subject_models = _subject_models()
        for key, model in subject_models.items():
            oid = d.get(f"{key}_id")
            if oid:
                kwargs[key] = model.objects.filter(id=oid).first()
        run = convene(**kwargs)
        return Response(WarRoomRunSerializer(run).data)
