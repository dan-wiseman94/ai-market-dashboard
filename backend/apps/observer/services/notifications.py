"""Persist + broadcast Notification rows."""

from __future__ import annotations

from apps.core.realtime import group_broadcast
from apps.observer.models import Notification
from apps.observer.serializers import NotificationSerializer


def notify(
    *,
    user_id: int | None,
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    meta: dict | None = None,
) -> Notification:
    n = Notification.objects.create(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        link=link,
        meta=meta or {},
    )
    # v1: no user-auth surface, all notifications go to the anonymous group.
    # When auth lands, switch to f"user.{user_id}.notifications".
    group_name = f"user.{user_id}.notifications" if user_id else "user.anonymous.notifications"
    group_broadcast(group_name, "notification.event", NotificationSerializer(n).data)
    return n
