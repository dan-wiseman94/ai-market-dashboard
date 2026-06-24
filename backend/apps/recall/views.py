"""Recall API views — function-based, on-demand (no extra models)."""

from __future__ import annotations

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.recall.models import RecallDocument
from apps.recall.services import search as S


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
    counts: dict[str, int] = {}
    for kind, _ in RecallDocument.KIND_CHOICES:
        counts[kind] = RecallDocument.objects.filter(kind=kind).count()
    counts["total"] = RecallDocument.objects.count()
    return Response({"counts": counts, "mode": S.mode()})
