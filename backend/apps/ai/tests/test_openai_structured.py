"""Structured runs against OpenAI-compatible endpoints: a sanitized strict-schema
request for ``openai``, the same plus a ``json_object`` fallback for ``local``, and
an ``AIRun`` recorded under the real provider so cost caps see the spend.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import BadRequestError
from pydantic import BaseModel, Field

pytestmark = pytest.mark.django_db

MOD = "apps.ai.providers.openai_structured"


class _Out(BaseModel):
    summary: str


def _usage(prompt=1000, completion=200, cached=0):
    usage = MagicMock()
    usage.prompt_tokens = prompt
    usage.completion_tokens = completion
    usage.prompt_tokens_details = MagicMock()
    usage.prompt_tokens_details.cached_tokens = cached
    return usage


def _completion(
    *, content='{"summary": "ok"}', refusal=None, finish_reason="stop", choices=True, **usage_kw
):
    message = MagicMock()
    message.content = content
    message.refusal = refusal
    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason
    completion = MagicMock()
    completion.choices = [choice] if choices else []
    completion.usage = _usage(**usage_kw)
    return completion


def _bad_request() -> BadRequestError:
    request = httpx.Request("POST", "http://local/v1/chat/completions")
    response = httpx.Response(400, request=request)
    return BadRequestError("unsupported response_format", response=response, body=None)


def _run(*, provider="openai", client=None, **overrides):
    from apps.ai.providers.openai_structured import run_structured

    fake_client = client or MagicMock()
    if client is None:
        fake_client.chat.completions.create.return_value = _completion()
    kwargs = dict(
        provider=provider,
        api_key="sk-test",
        model="gpt-5.6-sol",
        system="sys",
        user="hi",
        output_model=_Out,
    )
    kwargs.update(overrides)
    with patch(f"{MOD}.OpenAI", return_value=fake_client) as ctor:
        result = run_structured(**kwargs)
    return result, fake_client, ctor


def test_openai_parse_records_airun_with_cost():
    from apps.threads.models import AIRun

    out, _client, _ctor = _run()

    assert out.summary == "ok"
    run = AIRun.objects.get()
    assert run.provider == "openai"
    assert run.model == "gpt-5.6-sol"
    assert run.input_tokens == 1000
    assert run.output_tokens == 200
    assert run.cost_usd > Decimal("0")


def test_local_records_airun_at_zero_cost():
    from apps.threads.models import AIRun

    _run(provider="local", base_url="http://host.docker.internal:11434/v1", model="llama")

    run = AIRun.objects.get()
    assert run.provider == "local"
    assert run.cost_usd == Decimal("0")


def test_refusal_raises_parse_error():
    from apps.ai.providers.claude_structured import StructuredParseError

    client = MagicMock()
    client.chat.completions.create.return_value = _completion(refusal="no")
    with pytest.raises(StructuredParseError, match="refused"):
        _run(client=client)


def test_invalid_json_content_raises_parse_error():
    from apps.ai.providers.claude_structured import StructuredParseError

    client = MagicMock()
    client.chat.completions.create.return_value = _completion(content='{"nope": 1}')
    with pytest.raises(StructuredParseError):
        _run(client=client)


def test_length_finish_reason_raises_parse_error():
    from apps.ai.providers.claude_structured import StructuredParseError

    client = MagicMock()
    client.chat.completions.create.return_value = _completion(finish_reason="length")
    with pytest.raises(StructuredParseError, match="truncated"):
        _run(client=client)


def test_empty_choices_raises_parse_error():
    from apps.ai.providers.claude_structured import StructuredParseError

    client = MagicMock()
    client.chat.completions.create.return_value = _completion(choices=False)
    with pytest.raises(StructuredParseError):
        _run(client=client)

    local_client = MagicMock()
    local_client.chat.completions.create.side_effect = [
        _bad_request(),
        _completion(choices=False),
    ]
    with pytest.raises(StructuredParseError):
        _run(provider="local", base_url="http://x/v1", client=local_client)


def test_openai_uses_max_completion_tokens():
    _out, client, _ctor = _run(max_tokens=777)
    kw = client.chat.completions.create.call_args.kwargs
    assert kw["max_completion_tokens"] == 777
    assert "max_tokens" not in kw
    assert kw["response_format"]["type"] == "json_schema"
    assert kw["response_format"]["json_schema"]["strict"] is True
    assert kw["model"] == "gpt-5.6-sol"


def test_local_uses_max_tokens():
    _out, client, _ctor = _run(provider="local", base_url="http://x/v1", max_tokens=555)
    kw = client.chat.completions.create.call_args.kwargs
    assert kw["max_tokens"] == 555
    assert "max_completion_tokens" not in kw


def test_system_message_precedes_user_and_is_omitted_when_empty():
    _out, client, _ctor = _run(system="be terse")
    msgs = client.chat.completions.create.call_args.kwargs["messages"]
    assert msgs == [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}]

    _out, client, _ctor = _run(system="")
    msgs = client.chat.completions.create.call_args.kwargs["messages"]
    assert msgs == [{"role": "user", "content": "hi"}]


def test_local_falls_back_to_json_object_on_400():
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _bad_request(),
        _completion(content='```json\n{"summary": "from fallback"}\n```'),
    ]

    out, client, _ctor = _run(provider="local", base_url="http://x/v1", client=client)

    assert out.summary == "from fallback"
    kw = client.chat.completions.create.call_args.kwargs
    assert kw["response_format"] == {"type": "json_object"}
    system_text = kw["messages"][0]["content"]
    assert kw["messages"][0]["role"] == "system"
    assert "JSON" in system_text
    assert '"summary"' in system_text  # the schema is in the prompt
    assert kw["messages"][1] == {"role": "user", "content": "hi"}


def test_local_fallback_invalid_json_raises_parse_error():
    from apps.ai.providers.claude_structured import StructuredParseError

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _bad_request(),
        _completion(content='{"nope": 1}'),
    ]

    with pytest.raises(StructuredParseError):
        _run(provider="local", base_url="http://x/v1", client=client)


def test_openai_400_is_not_retried():
    client = MagicMock()
    client.chat.completions.create.side_effect = _bad_request()

    with pytest.raises(BadRequestError):
        _run(provider="openai", client=client)
    assert client.chat.completions.create.call_count == 1


def test_request_schema_is_sanitized():
    """``maxLength`` never reaches the API; it survives in the description, and
    Pydantic still enforces it client-side."""
    from apps.ai.providers.claude_structured import StructuredParseError

    class _Bounded(BaseModel):
        title: str = Field(max_length=5, description="Short")

    ok_client = MagicMock()
    ok_client.chat.completions.create.return_value = _completion(content='{"title": "ok"}')
    _out, client, _ctor = _run(output_model=_Bounded, client=ok_client)

    sent = client.chat.completions.create.call_args.kwargs["response_format"]
    assert sent["type"] == "json_schema"
    assert sent["json_schema"]["strict"] is True
    schema = sent["json_schema"]["schema"]
    assert "maxLength" not in schema["properties"]["title"]
    assert "maxLength 5" in schema["properties"]["title"]["description"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["title"]

    # client-side enforcement still holds even though the API never saw maxLength:
    bad_client = MagicMock()
    bad_client.chat.completions.create.return_value = _completion(
        content='{"title": "way too long"}'
    )
    with pytest.raises(StructuredParseError):
        _run(output_model=_Bounded, client=bad_client)


def test_token_usage_from_openai_maps_cached_subset():
    from apps.ai.providers.openai_structured import token_usage_from_openai

    usage = token_usage_from_openai(_usage(prompt=1000, completion=200, cached=300))
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 200
    assert usage.cached_tokens == 300
    assert usage.cache_write_tokens == 0


def test_token_usage_from_openai_tolerates_missing_details():
    from apps.ai.providers.openai_structured import token_usage_from_openai

    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.prompt_tokens_details = None
    out = token_usage_from_openai(usage)
    assert (out.input_tokens, out.output_tokens, out.cached_tokens) == (10, 5, 0)


def test_client_gets_resilience_kwargs_and_local_placeholder_key(settings):
    settings.AI_PROVIDER_MAX_RETRIES = 4
    settings.AI_PROVIDER_TIMEOUT_SECONDS = 12.5

    _out, _client, ctor = _run(provider="local", api_key="", base_url="http://x/v1")
    kw = ctor.call_args.kwargs
    assert kw["max_retries"] == 4
    assert kw["timeout"] == 12.5
    assert kw["base_url"] == "http://x/v1"
    assert kw["api_key"]  # placeholder, never empty

    _out, _client, ctor = _run(provider="openai", api_key="sk-real")
    assert ctor.call_args.kwargs["api_key"] == "sk-real"
    assert ctor.call_args.kwargs["base_url"] is None


def test_airun_write_failure_does_not_lose_result():
    with patch("apps.ai.cost.record_ai_run", side_effect=RuntimeError("db down")):
        out, _client, _ctor = _run()
    assert out.summary == "ok"
