"""Claude provider must attach cache_control to the final prior turn when
cache_last_message=True."""

from __future__ import annotations

from apps.ai.providers.claude import _maybe_cache_last_message


def test_maybe_cache_last_message_attaches_cache_control() -> None:
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "now analyze this snapshot..."},
    ]
    out = _maybe_cache_last_message(msgs, cache=True)
    assert out[0]["content"] == "hello"
    assert out[1]["content"] == "hi"
    last = out[-1]
    assert isinstance(last["content"], list)
    assert last["content"][-1]["cache_control"] == {"type": "ephemeral"}


def test_maybe_cache_last_message_noop_when_flag_false() -> None:
    msgs = [{"role": "user", "content": "hello"}]
    out = _maybe_cache_last_message(msgs, cache=False)
    assert out == msgs


def test_maybe_cache_last_message_noop_on_empty() -> None:
    assert _maybe_cache_last_message([], cache=True) == []


def test_maybe_cache_last_message_doesnt_mutate_input() -> None:
    msgs = [{"role": "user", "content": "a"}]
    _ = _maybe_cache_last_message(msgs, cache=True)
    assert msgs[0]["content"] == "a"
