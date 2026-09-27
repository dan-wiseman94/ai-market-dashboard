from django.test import override_settings


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
def test_ping_task_returns_pong():
    """ping() returns 'pong' when executed."""
    from apps.core.tasks import ping

    result = ping.delay()
    assert result.get(timeout=2) == "pong"
