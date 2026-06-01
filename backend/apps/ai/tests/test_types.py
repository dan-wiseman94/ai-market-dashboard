from apps.ai.types import RunRequest


def test_run_request_max_tool_iterations_defaults_to_unlimited():
    req = RunRequest(model="m", system="s", messages=[])
    assert req.max_tool_iterations == 0  # 0 = unlimited (chat default, behavior unchanged)
