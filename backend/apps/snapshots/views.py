from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.profiles.models import TradingProfile
from apps.snapshots.diff import diff_sections
from apps.snapshots.models import Snapshot, SnapshotImage
from apps.snapshots.serializers import SnapshotImageSerializer, SnapshotSerializer
from apps.snapshots.services.screenshot import (
    ImageTooLargeError,
    InvalidPNGError,
    attach_client_image,
)
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
        image_ids = data.get("image_ids") or []
        if image_ids:
            SnapshotImage.objects.filter(id__in=image_ids, snapshot__isnull=True).update(snapshot=snap)
        capture_task.delay(
            snapshot_id=snap.id,
            watchlist_tickers=data.get("watchlist_tickers") or [],
            ohlc_ticker=data.get("ohlc_ticker"),
            ohlc_timeframe=data.get("ohlc_timeframe", "1m"),
            ohlc_bars=data.get("ohlc_bars", 60),
        )
        return Response(SnapshotSerializer(snap).data, status=202)

    @action(detail=True, methods=["get"])
    def diff(self, request, pk=None):
        """GET /api/snapshots/<id>/diff/?against=<other_id>

        Returns {delta: <markdown>, prev_id, curr_id}. The caller chooses
        which snapshot is 'prev' via the `against` query param; this
        endpoint is direction-agnostic — it just diffs the two.
        """
        against_id = request.query_params.get("against")
        if not against_id:
            return Response({"code": "missing_against"}, status=400)
        try:
            prev = Snapshot.objects.prefetch_related("sections").get(id=against_id)
            curr = Snapshot.objects.prefetch_related("sections").get(id=pk)
        except Snapshot.DoesNotExist:
            return Response({"code": "not_found"}, status=404)

        prev_sections = {s.kind: s.payload for s in prev.sections.all()}
        curr_sections = {s.kind: s.payload for s in curr.sections.all()}
        delta = diff_sections(prev_sections, curr_sections)
        return Response({"delta": delta, "prev_id": prev.id, "curr_id": curr.id})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def images_collection(request):
    if request.method == "POST":
        body = request.body
        caption = request.headers.get("X-Caption", "")
        try:
            img = attach_client_image(snapshot_id=None, png_bytes=body, caption=caption)
        except InvalidPNGError as e:
            return JsonResponse({"code": "invalid_png", "message": str(e)}, status=400)
        except ImageTooLargeError as e:
            return JsonResponse({"code": "too_large", "message": str(e)}, status=413)
        return JsonResponse(SnapshotImageSerializer(img).data, status=201)

    # GET: list staged
    staged = request.GET.get("staged") == "true"
    qs = SnapshotImage.objects.filter(snapshot__isnull=True) if staged else SnapshotImage.objects.all()
    qs = qs.order_by("-created_at")[:50]
    return JsonResponse({"images": SnapshotImageSerializer(qs, many=True).data})


def serve_image(_request, image_id: int):
    img = get_object_or_404(SnapshotImage, id=image_id)
    return HttpResponse(bytes(img.data), content_type=img.mime_type or "image/png")
