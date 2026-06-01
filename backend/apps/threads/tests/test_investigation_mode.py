from decimal import Decimal

import pytest

from apps.ai.cost import CostCapExceededError
from apps.ai.types import RunRequest
from apps.threads import tasks as thr_tasks
from apps.threads.tasks import _apply_investigation_mode


class _Cfg:
    supports_tools = True


def test_apply_investigation_mode_forces_tools_cap_and_directive(settings):
    settings.AI_INVESTIGATION_MAX_ITERATIONS = 5
    req = RunRequest(model="m", system="Base.", messages=[], tools=[])
    _apply_investigation_mode(req, provider_name="claude", cfg=_Cfg())
    assert req.max_tool_iterations == 5
    assert req.tools, "claude investigation must force the toolset on"
    assert "What I checked" in req.system and "What to watch" in req.system


@pytest.mark.django_db
def test_investigation_gated_by_autonomous_cap(settings, monkeypatch):
    """With an autonomous daily cap set, an over-cap investigation run is blocked
    by a SECOND check_daily_cap call against that lower ceiling."""
    settings.AI_AUTONOMOUS_DAILY_CAP_USD = 1.0

    from apps.profiles.models import TradingProfile
    from apps.secrets.models import ProviderConfig
    from apps.threads.models import Message, Thread

    ProviderConfig.objects.create(provider="claude", api_key="sk", enabled=True)
    prof = TradingProfile.objects.create(name="p", style="x", default_provider="claude")
    thread = Thread.objects.create(kind="chat", profile=prof)
    user = Message.objects.create(thread=thread, role="user", content={"text": "hi"}, status="done")

    seen: dict[str, list] = {"caps": []}

    def _fake_daily(provider, *, cap_usd):
        seen["caps"].append(cap_usd)
        if cap_usd == Decimal("1.0"):
            raise CostCapExceededError("autonomous daily cap hit")

    monkeypatch.setattr(thr_tasks, "check_daily_cap", _fake_daily)
    monkeypatch.setattr(thr_tasks, "check_monthly_cap", lambda *a, **k: None)

    out = thr_tasks._resolve_run_config(
        thread=thread, user_msg=user, override=None, parent_message_id=None, investigate=True
    )
    assert Decimal("1.0") in seen["caps"], "the autonomous ceiling must be checked"
    assert isinstance(out, dict) and out["error"] == "cost_capped"
