"""Triggers HTTP endpoints."""
from __future__ import annotations

from django.db.models import Count
from rest_framework import viewsets

from apps.triggers.models import EventTrigger
from apps.triggers.serializers import EventTriggerSerializer


class EventTriggerViewSet(viewsets.ModelViewSet):
    serializer_class = EventTriggerSerializer

    def get_queryset(self):
        return (
            EventTrigger.objects.select_related("profile")
            .annotate(firings_count=Count("firings"))
            .order_by("-created_at")
        )
