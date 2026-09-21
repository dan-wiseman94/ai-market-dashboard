"""Recall API views — function-based, on-demand (no extra models)."""

from __future__ import annotations

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework import status as drf_status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.recall.models import RecallDocument
from apps.recall.services import search as S
from apps.recall.tasks import backfill


class BackfillQueuedSerializer(serializers.Serializer):
    """202 body of POST /api/recall/backfill/."""

    task_id = serializers.CharField()
    status = serializers.CharField(help_text='Always "queued".')


@api_view(["GET"])
def recall_search(request: Request) -> Response:
    q = request.query_params.get("q", "").strip()
    if not q:
        return Response({"results": [], "mode": S.mode()})
    try:
        k = max(1, min(50, int(request.query_params.get("k", "10"))))
    except ValueError:
        k = 10
    kinds_raw = request.query_params.get("kind", "")
    kinds = [x.strip() for x in kinds_raw.split(",") if x.strip()] if kinds_raw else None
    ticker = request.query_params.get("ticker", "").strip() or None
    results, mode = S.search_with_mode(q, k=k, kinds=kinds, ticker=ticker)
    return Response({"results": results, "mode": mode})


@api_view(["GET"])
def recall_related(request: Request) -> Response:
    kind = request.query_params.get("kind", "").strip()
    ticker = request.query_params.get("ticker", "").strip()
    try:
        k = max(1, min(20, int(request.query_params.get("k", "5"))))
    except ValueError:
        k = 5

    if ticker:
        results = S.related_to_ticker(ticker, k=k)
        return Response(results)

    obj_id_raw = request.query_params.get("id", "")
    try:
        object_id = int(obj_id_raw)
    except (ValueError, TypeError):
        return Response({"error": "id is required and must be an integer"}, status=400)

    if not kind:
        return Response({"error": "kind is required"}, status=400)

    results = S.related(kind, object_id, k=k)
    return Response(results)


@api_view(["GET"])
def recall_status(request: Request) -> Response:
    # One GROUP BY instead of a COUNT round-trip per kind plus a total.
    by_kind = dict(RecallDocument.objects.values_list("kind").annotate(n=Count("id")))
    counts: dict[str, int] = {kind: by_kind.get(kind, 0) for kind, _ in RecallDocument.KIND_CHOICES}
    counts["total"] = sum(by_kind.values())
    return Response({"counts": counts, "mode": S.mode()})


# A function view has no serializer for drf-spectacular to guess from, and the
# backfill takes no body — say both explicitly rather than ship "no response body".
@extend_schema(request=None, responses={202: BackfillQueuedSerializer})
@api_view(["POST"])
def recall_backfill(request: Request) -> Response:
    """Queue an index catch-up over every un-indexed source.

    Safe to press repeatedly: the backfill is idempotent and embeddings are computed
    locally, so it costs CPU, never provider spend. Poll /api/recall/status/ for the
    per-kind counts as they fill in.
    """
    task = backfill.delay()
    return Response(
        {"task_id": str(task.id), "status": "queued"}, status=drf_status.HTTP_202_ACCEPTED
    )
