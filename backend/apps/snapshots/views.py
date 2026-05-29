from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from apps.profiles.models import TradingProfile
from apps.snapshots.diff import diff_sections
from apps.snapshots.models import Snapshot, SnapshotImage
from apps.snapshots.serializers import (
    SnapshotImageSerializer,
    SnapshotListSerializer,
    SnapshotSerializer,
)
from apps.snapshots.services.screenshot import (
    ImageTooLargeError,
    InvalidPNGError,
    attach_client_image,
)
from apps.snapshots.tasks import capture_task
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message


class _SnapshotPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200


class SnapshotViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SnapshotSerializer
    pagination_class = _SnapshotPagination

    def get_serializer_class(self):
        return SnapshotListSerializer if self.action == "list" else SnapshotSerializer

    def get_queryset(self):
        qs = Snapshot.objects.select_related("profile").prefetch_related("sections")
        p = self.request.query_params
        if p.get("profile"):
            qs = qs.filter(profile_id=p["profile"])
        if p.get("ticker"):
            qs = qs.filter(primary_ticker__iexact=p["ticker"])
        if p.get("source"):
            qs = qs.filter(source=p["source"])
        if p.get("since"):
            qs = qs.filter(captured_at__gte=p["since"])
        if p.get("until"):
            qs = qs.filter(captured_at__lte=p["until"])
        if p.get("overnight") in ("true", "1"):
            qs = qs.filter(overnight=True)
        return qs

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
            manual_positions=data.get("manual_positions", ""),
            includes=data.get("includes") or profile.default_includes,
            source="manual",
            status="pending",
            overnight=bool(data.get("overnight", False)),
        )
        image_ids = data.get("image_ids") or []
        if image_ids:
            SnapshotImage.objects.filter(id__in=image_ids, snapshot__isnull=True).update(
                snapshot=snap
            )
        from apps.core.mocks import current_scenario, is_mock_mode

        capture_task.delay(
            snapshot_id=snap.id,
            watchlist_tickers=data.get("watchlist_tickers") or [],
            ohlc_ticker=data.get("ohlc_ticker"),
            ohlc_timeframe=data.get("ohlc_timeframe", "1m"),
            ohlc_bars=data.get("ohlc_bars", 60),
            overnight=bool(data.get("overnight", False)),
            scenario=current_scenario() if is_mock_mode() else None,
        )
        return Response(SnapshotSerializer(snap).data, status=202)

    @action(detail=False, methods=["get"], url_path="timeline")
    def timeline(self, request):
        """GET /api/snapshots/timeline/?ticker=NVDA — ready snapshots for one ticker,
        oldest->newest, each with headline_delta_pct (primary-ticker last % vs the prior node)."""
        ticker = (request.query_params.get("ticker") or "").upper()
        if not ticker:
            return Response({"code": "missing_ticker"}, status=400)
        snaps = list(
            Snapshot.objects.filter(primary_ticker=ticker, status="ready")
            .select_related("profile")
            .prefetch_related("sections")
            .order_by("captured_at")
        )

        def last_price(s):
            q = next((x for x in s.sections.all() if x.kind == "quotes"), None)
            if q is None or not s.primary_ticker or not isinstance(q.payload, dict):
                return None
            try:
                return float(q.payload[s.primary_ticker]["last"])
            except (KeyError, TypeError, ValueError):
                return None

        rows, prev = [], None
        for s in snaps:
            cur = last_price(s)
            delta = ((cur - prev) / prev * 100.0) if (cur is not None and prev) else None
            data = SnapshotListSerializer(s).data
            data["headline_delta_pct"] = delta
            rows.append(data)
            if cur is not None:
                prev = cur
        return Response({"results": rows})

    @action(detail=True, methods=["post"], url_path="explain-diff")
    def explain_diff(self, request, pk=None):
        from apps.snapshots.primary import previous_snapshot_for

        curr = get_object_or_404(Snapshot.objects.prefetch_related("sections"), id=pk)
        against_id = request.data.get("against")
        if against_id:
            prev = get_object_or_404(Snapshot.objects.prefetch_related("sections"), id=against_id)
        else:
            prev = previous_snapshot_for(curr)
            if prev is None:
                return Response({"code": "no_prior"}, status=400)
        delta = diff_sections(
            {s.kind: s.payload for s in prev.sections.all()},
            {s.kind: s.payload for s in curr.sections.all()},
        )
        thread = Thread.objects.create(
            kind="diff",
            profile=curr.profile,
            pinned_snapshot=curr,
            title=f"What changed: {curr.primary_ticker or 'snapshot'} #{prev.id}→#{curr.id}"[:200],
        )
        framing = (
            f"Below is a deterministic diff between two market snapshots of "
            f"{curr.primary_ticker or 'the same set'} captured {prev.captured_at:%Y-%m-%d %H:%M} → "
            f"{curr.captured_at:%Y-%m-%d %H:%M}. Explain what materially changed and why it might "
            f"matter for the objective: '{curr.objective}'. Be concise; lead with the most significant change."
        )
        msg = Message.objects.create(
            thread=thread,
            role="user",
            status="done",
            snapshot_ref=curr,
            content={"text": f"{framing}\n\n{delta}"},
        )
        run_ai_on_message.delay(thread_id=thread.id, user_message_id=msg.id)
        return Response({"thread_id": thread.id, "message_id": msg.id, "delta": delta}, status=201)

    @action(detail=True, methods=["get"])
    def diff(self, request, pk=None):
        """GET /api/snapshots/<id>/diff/?against=<other_id>

        Returns {delta: <markdown>, prev_id, curr_id}. When `against` is
        omitted, auto-selects the most-recent prior ready snapshot sharing
        the same primary_ticker. Returns {code: no_prior} 400 when none.
        """
        from apps.snapshots.primary import previous_snapshot_for

        curr = get_object_or_404(Snapshot.objects.prefetch_related("sections"), id=pk)
        against_id = request.query_params.get("against")
        if against_id:
            try:
                prev = Snapshot.objects.prefetch_related("sections").get(id=against_id)
            except Snapshot.DoesNotExist:
                return Response({"code": "not_found"}, status=404)
        else:
            prev = previous_snapshot_for(curr)
            if prev is None:
                return Response({"code": "no_prior"}, status=400)
        prev_sections = {s.kind: s.payload for s in prev.sections.all()}
        curr_sections = {s.kind: s.payload for s in curr.sections.all()}
        delta = diff_sections(prev_sections, curr_sections)
        return Response({"delta": delta, "prev_id": prev.id, "curr_id": curr.id})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def images_collection(request):
    if request.method == "POST":
        try:
            body = request.body
        except RequestDataTooBig as e:
            # Django's body-buffer guard (DATA_UPLOAD_MAX_MEMORY_SIZE) fires before
            # we can reach attach_client_image's own size check. Translate it into the
            # same clean 413 the image cap would have produced, rather than Django's
            # bare 400 HTML page. See apps/snapshots/services/screenshot.MAX_BYTES.
            return JsonResponse({"code": "too_large", "message": str(e)}, status=413)
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
    qs = (
        SnapshotImage.objects.filter(snapshot__isnull=True)
        if staged
        else SnapshotImage.objects.all()
    )
    qs = qs.order_by("-created_at")[:50]
    return JsonResponse({"images": SnapshotImageSerializer(qs, many=True).data})


def serve_image(_request, image_id: int):
    img = get_object_or_404(SnapshotImage, id=image_id)
    return HttpResponse(bytes(img.data), content_type=img.mime_type or "image/png")
