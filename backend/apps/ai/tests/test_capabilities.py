from types import SimpleNamespace

from apps.ai.capabilities import unsupported_features


def _profile(**flags):
    base = {"enable_tools": False, "enable_thinking": False, "enable_memory": False}
    base.update(flags)
    return SimpleNamespace(**base)


def test_claude_supports_everything():
    prof = _profile(enable_tools=True, enable_thinking=True, enable_memory=True)
    assert unsupported_features("claude", prof, supports_tools=False) == []


def test_none_profile_is_empty():
    assert unsupported_features("openai", None, supports_tools=True) == []


def test_openai_thinking_and_memory_unsupported():
    prof = _profile(enable_thinking=True, enable_memory=True)
    out = unsupported_features("openai", prof, supports_tools=True)
    assert "extended thinking" in out
    assert "memory" in out
    assert "tool use" not in out


def test_local_tools_unsupported_when_flag_off():
    prof = _profile(enable_tools=True)
    assert unsupported_features("local", prof, supports_tools=False) == ["tool use"]


def test_local_tools_ok_when_flag_on():
    prof = _profile(enable_tools=True)
    assert unsupported_features("local", prof, supports_tools=True) == []
