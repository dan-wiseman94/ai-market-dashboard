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


# --- vision: a per-ProviderConfig declaration, not a Claude-only feature ----------


def test_images_dropped_is_reported_for_a_vision_less_provider():
    out = unsupported_features(
        "local", None, supports_tools=True, supports_vision=False, carries_images=True
    )
    assert out == ["chart images"]


def test_images_dropped_is_reported_for_claude_too():
    """supports_vision is declared per config row, so Claude is not exempt."""
    prof = _profile()
    out = unsupported_features(
        "claude", prof, supports_tools=True, supports_vision=False, carries_images=True
    )
    assert out == ["chart images"]


def test_no_image_gap_when_the_run_carries_no_images():
    out = unsupported_features(
        "local", None, supports_tools=True, supports_vision=False, carries_images=False
    )
    assert out == []


def test_no_image_gap_when_the_endpoint_declares_vision():
    out = unsupported_features(
        "local", None, supports_tools=True, supports_vision=True, carries_images=True
    )
    assert out == []


def test_image_gap_joins_the_other_gaps():
    prof = _profile(enable_tools=True, enable_thinking=True)
    out = unsupported_features(
        "openai",
        prof,
        supports_tools=False,
        supports_vision=False,
        carries_images=True,
        content_kinds=["file attachments"],
    )
    assert out == ["chart images", "file attachments", "tool use", "extended thinking"]
