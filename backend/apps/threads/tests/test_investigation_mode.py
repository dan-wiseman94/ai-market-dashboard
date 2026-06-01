from apps.ai.types import RunRequest
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
