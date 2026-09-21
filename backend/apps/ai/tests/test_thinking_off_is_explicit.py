"""Turning thinking off has to be sent, not omitted.

Adaptive rows think by default server-side, so leaving the ``thinking`` parameter
out is not "off" — the run still reasons and still bills for it. That makes the
profile switch a lie unless the provider sends ``{"type": "disabled"}``, and that
pairing is itself rejected above effort "high", so the effort hint goes with it.
"""

from __future__ import annotations

import pytest

from apps.ai.providers.claude import _apply_thinking
from apps.ai.types import RunRequest


def _req(**kw: object) -> RunRequest:
    base: dict = {
        "model": "claude-opus-5",
        "system": "",
        "messages": [],
        "max_tokens": 16_000,
    }
    base.update(kw)
    return RunRequest(**base)  # type: ignore[arg-type]


def test_off_on_an_adaptive_row_sends_disabled_and_drops_effort() -> None:
    kwargs: dict = {}
    _apply_thinking(kwargs, _req(enable_thinking=False, effort="high"))

    assert kwargs["thinking"] == {"type": "disabled"}
    # `disabled` + effort above "high" is a 400, and effort only shapes thinking
    # depth, so the hint is dropped rather than risked.
    assert "output_config" not in kwargs


def test_on_sends_adaptive_summarized_plus_effort() -> None:
    kwargs: dict = {}
    _apply_thinking(kwargs, _req(enable_thinking=True, effort="xhigh"))

    assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert kwargs["output_config"] == {"effort": "xhigh"}


def test_a_row_that_cannot_disable_thinking_omits_rather_than_400s() -> None:
    kwargs: dict = {}
    _apply_thinking(kwargs, _req(model="claude-fable-5-1", enable_thinking=False))

    # Thinking is always on for this row; sending `disabled` would be rejected, so
    # the honest outcome is to omit it and let the run think.
    assert "thinking" not in kwargs


@pytest.mark.parametrize("enabled", [True, False])
def test_budget_rows_never_receive_adaptive_or_effort(enabled: bool) -> None:
    kwargs: dict = {}
    _apply_thinking(
        kwargs,
        _req(
            model="claude-haiku-4-5-20251001",
            enable_thinking=enabled,
            thinking_budget=4096,
        ),
    )

    assert kwargs.get("thinking", {}).get("type") != "adaptive"
    assert "output_config" not in kwargs
