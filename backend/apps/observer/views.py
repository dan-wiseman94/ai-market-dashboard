"""Observer HTTP endpoints."""
from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.observer.models import Notification, ObserverSchedule
from apps.observer.serializers import NotificationSerializer, ObserverScheduleSerializer
from apps.observer.services.market_hours import market_status
from apps.observer.services.sync import delete_periodic_task, sync_periodic_task
from apps.observer.services.threads import get_or_create_observer_thread
from apps.observer.tasks import run_observer_task
from apps.profiles.models import TradingProfile


class ObserverScheduleViewSet(viewsets.ModelViewSet):
    queryset = ObserverSchedule.objects.select_related("profile", "periodic_task__crontab")
    serializer_class = ObserverScheduleSerializer

    def perform_create(self, serializer):
        cron = serializer.validated_data.pop("cron")
        instance = serializer.save()
        sync_periodic_task(instance, cron=cron)

    def perform_update(self, serializer):
        cron = serializer.validated_data.pop("cron", None)
        instance = serializer.save()
        if cron is not None or "enabled" in serializer.validated_data:
            existing_cron = cron
            if existing_cron is None and instance.periodic_task and instance.periodic_task.crontab:
                c = instance.periodic_task.crontab
                existing_cron = f"{c.minute} {c.hour} {c.day_of_month} {c.month_of_year} {c.day_of_week}"
            if existing_cron is None:
                existing_cron = "0 * * * *"
            sync_periodic_task(instance, cron=existing_cron)

    def perform_destroy(self, instance):
        delete_periodic_task(instance)
        instance.delete()

    @action(detail=True, methods=["post"], url_path="run-now")
    def run_now(self, request, pk=None):
        run_observer_task.delay(schedule_id=int(pk))
        return Response(status=status.HTTP_202_ACCEPTED)


class NotificationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet,
):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        # v1: filter to anonymous rows; switch to request.user when auth lands.
        qs = Notification.objects.filter(user__isnull=True)
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        try:
            limit = int(self.request.query_params.get("limit", "50"))
        except ValueError:
            limit = 50
        return qs[:limit]

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        n = Notification.objects.get(id=pk, user__isnull=True)
        n.read_at = timezone.now()
        n.save(update_fields=["read_at"])
        return Response(NotificationSerializer(n).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        Notification.objects.filter(user__isnull=True, read_at__isnull=True).update(
            read_at=timezone.now(),
        )
        return Response({"ok": True})


@require_GET
def market_status_view(_request: HttpRequest) -> JsonResponse:
    s = market_status()
    return JsonResponse({
        "is_open": s["is_open"],
        "next_open": s["next_open"].isoformat() if s["next_open"] else None,
        "next_close": s["next_close"].isoformat() if s["next_close"] else None,
    })


@require_GET
def observer_thread_view(_request: HttpRequest, profile_id: int) -> JsonResponse:
    profile = get_object_or_404(TradingProfile, id=profile_id)
    thread = get_or_create_observer_thread(profile)
    messages = list(thread.messages.all().order_by("created_at").values(
        "id", "role", "content", "created_at",
    ))
    return JsonResponse({
        "id": thread.id,
        "kind": thread.kind,
        "profile_id": thread.profile_id,
        "title": thread.title,
        "messages": [
            {"id": m["id"], "role": m["role"], "content": m["content"],
             "created_at": m["created_at"].isoformat()}
            for m in messages
        ],
    })
