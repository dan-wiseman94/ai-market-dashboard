"""Observer HTTP endpoints."""
from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.observer.models import ObserverSchedule
from apps.observer.serializers import ObserverScheduleSerializer
from apps.observer.services.sync import delete_periodic_task, sync_periodic_task
from apps.observer.tasks import run_observer_task


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
