import ast
from pathlib import Path

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

import apps
from apps.observer.models import Notification
from apps.observer.services.notifications import notify


@pytest.mark.django_db
def test_notify_writes_row_with_defaults():
    n = notify(user_id=None, kind="observer_done", title="t", body="b", link="/x")
    assert n.id is not None
    assert n.user is None
    assert n.kind == "observer_done"
    assert n.body == "b"
    assert n.link == "/x"
    assert n.meta == {}
    assert Notification.objects.count() == 1


@pytest.mark.django_db
def test_notify_broadcasts_to_anonymous_group(settings):
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }
    layer = get_channel_layer()
    async_to_sync(layer.group_add)("user.anonymous.notifications", "test-channel")
    notify(user_id=None, kind="error", title="boom")
    msg = async_to_sync(layer.receive)("test-channel")
    assert msg["type"] == "notification.event"
    assert msg["payload"]["kind"] == "error"
    assert msg["payload"]["title"] == "boom"


def _notify_kind_literals() -> list[tuple[str, str]]:
    """Every string literal passed as ``kind=`` to a ``notify(...)`` call across
    backend/apps. AST-based so it only inspects real notify() call sites, not
    unrelated ``kind=`` uses (SnapshotSection kinds, etc.). Returns
    ``(literal, "path:lineno")`` pairs."""
    root = Path(apps.__file__).resolve().parent
    found: list[tuple[str, str]] = []
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (
                fn.attr
                if isinstance(fn, ast.Attribute)
                else fn.id
                if isinstance(fn, ast.Name)
                else None
            )
            if name != "notify":
                continue
            for kw in node.keywords:
                if kw.arg == "kind" and isinstance(kw.value, ast.Constant):
                    found.append((kw.value.value, f"{py}:{kw.value.lineno}"))
    return found


def test_all_notify_kind_literals_are_valid():
    """Guard against the varchar(16) silent-overflow landmine: every kind literal
    handed to notify() must fit Notification.kind (max_length=16) AND be a
    registered choice, so a too-long/unknown kind fails CI, not Postgres at
    runtime inside a best-effort try/except."""
    valid = {k for k, _ in Notification.KIND_CHOICES}
    literals = _notify_kind_literals()
    assert literals, "expected to find notify(kind=...) call sites"
    too_long = [(k, loc) for k, loc in literals if len(k) > 16]
    unknown = [(k, loc) for k, loc in literals if k not in valid]
    assert not too_long, f"notify kind exceeds Notification.kind max_length=16: {too_long}"
    assert not unknown, f"notify kind not in Notification.KIND_CHOICES: {unknown}"
