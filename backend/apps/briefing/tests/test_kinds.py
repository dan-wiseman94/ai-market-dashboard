from apps.observer.models import Notification
from apps.threads.models import Thread


def test_thread_supports_briefing_kind():
    assert "briefing" in dict(Thread.KIND_CHOICES)


def test_notification_supports_briefing_kind():
    assert "briefing" in dict(Notification.KIND_CHOICES)
