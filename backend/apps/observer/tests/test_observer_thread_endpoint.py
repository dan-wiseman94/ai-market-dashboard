import pytest

from apps.profiles.models import TradingProfile
from apps.threads.models import Message


@pytest.mark.django_db
def test_observer_thread_endpoint_creates_on_first_call(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp = api.get(f"/api/observer/threads/{p.id}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "observer"
    assert body["profile_id"] == p.id


@pytest.mark.django_db
def test_observer_thread_endpoint_idempotent(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp1 = api.get(f"/api/observer/threads/{p.id}/")
    resp2 = api.get(f"/api/observer/threads/{p.id}/")
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.django_db
def test_observer_thread_endpoint_exposes_attribution_status_and_error(api):
    """The timeline reads Messages, so it needs the run's provider/model/cost and the
    terminal state: without them a failed fire renders as an ordinary response."""
    from decimal import Decimal

    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import AIRun

    p = TradingProfile.objects.create(name="P", style="x")
    t = get_or_create_observer_thread(p)
    plain = Message.objects.create(thread=t, role="assistant", content={"text": "ok"})
    AIRun.objects.create(
        message=plain,
        provider="openai",
        model="gpt-5.6-sol",
        cost_usd=Decimal("0.0123"),
        status="done",
    )
    Message.objects.create(
        thread=t,
        role="assistant",
        content={
            "kind": "structured_observation",
            "report": {},
            "provider": "claude",
            "model": "claude-opus-5",
        },
    )
    Message.objects.create(
        thread=t,
        role="assistant",
        content={"text": "Structured run failed: boom"},
        status="failed",
        error="boom",
    )

    body = api.get(f"/api/observer/threads/{p.id}/").json()
    by_id = {m["id"]: m for m in body["messages"]}
    assert by_id[plain.id]["ai_run"] == {
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "cost_usd": "0.012300",
    }
    assert by_id[plain.id]["status"] == "done"
    structured = next(
        m for m in body["messages"] if m["content"].get("kind") == "structured_observation"
    )
    assert structured["ai_run"] is None  # one-shot runs carry no Message
    assert structured["content"]["provider"] == "claude"
    failed = next(m for m in body["messages"] if m["status"] == "failed")
    assert failed["error"] == "boom"


@pytest.mark.django_db
def test_observer_thread_endpoint_includes_messages(api):
    from apps.observer.services.threads import get_or_create_observer_thread

    p = TradingProfile.objects.create(name="P", style="x")
    t = get_or_create_observer_thread(p)
    Message.objects.create(thread=t, role="user", content={"text": "snap1"})
    Message.objects.create(thread=t, role="assistant", content={"text": "ok"})
    resp = api.get(f"/api/observer/threads/{p.id}/")
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 2
