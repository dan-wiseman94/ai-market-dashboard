import pytest
from decimal import Decimal

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Thread, Message, AIRun


@pytest.mark.django_db
def test_create_consult_thread_with_snapshot():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", status="ready")
    t = Thread.objects.create(kind="consult", profile=p, pinned_snapshot=s, title="NVDA long?")
    assert t.kind == "consult"
    assert t.pinned_snapshot == s


@pytest.mark.django_db
def test_message_streaming_states():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    m = Message.objects.create(thread=t, role="user", content={"text": "hi"})
    assert m.status == "done"
    a = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="streaming")
    assert a.status == "streaming"


@pytest.mark.django_db
def test_airun_persisted_after_stream():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    m = Message.objects.create(thread=t, role="assistant", content={"text": "hello"}, status="done")
    r = AIRun.objects.create(
        message=m,
        provider="claude",
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cached_tokens=200,
        cost_usd=Decimal("0.0105"),
        latency_ms=1234,
        status="done",
    )
    assert r.cost_usd == Decimal("0.0105")
