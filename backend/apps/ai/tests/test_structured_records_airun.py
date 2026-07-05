"""Structured Claude runs must be recorded as AIRun rows so their cost counts
against the daily/monthly caps.

``run_structured`` (used by post-mortems, coverage revisions, regime/book
narratives, war-room, eval, predictions) is the strategist layer's spend path:
if it recorded no ``AIRun`` and computed no cost, that entire layer would spend
money invisibly to ``check_daily_cap`` / ``check_monthly_cap`` (which sum
``AIRun.cost_usd``).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

pytestmark = pytest.mark.django_db


class _Out(BaseModel):
    summary: str


def _fake_parse_response(*, input_tokens=1000, output_tokens=200):
    resp = MagicMock()
    resp.parsed_output = _Out(summary="ok")
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    resp.usage = usage
    return resp


def _run_with_fake_client(**overrides):
    from apps.ai.providers.claude_structured import run_structured

    fake_client = MagicMock()
    fake_client.messages.parse.return_value = _fake_parse_response(**overrides)
    with patch("apps.ai.providers.claude_structured.Anthropic", return_value=fake_client):
        return run_structured(
            api_key="sk-test",
            model="claude-opus-4-8",
            system="sys",
            user="hi",
            output_model=_Out,
        )


def test_run_structured_records_an_airun_with_cost():
    from apps.threads.models import AIRun

    out = _run_with_fake_client()

    assert out.summary == "ok"  # parsed result still returned
    run = AIRun.objects.get()  # exactly one row recorded
    assert run.provider == "claude"
    assert run.model == "claude-opus-4-8"
    assert run.input_tokens == 1000
    assert run.output_tokens == 200
    assert run.message_id is None  # not tied to a chat Message
    assert run.cost_usd > Decimal("0")


def test_structured_run_counts_against_daily_spend():
    from apps.ai.cost import daily_spend_usd

    before = daily_spend_usd("claude")
    _run_with_fake_client()
    after = daily_spend_usd("claude")

    assert after > before
