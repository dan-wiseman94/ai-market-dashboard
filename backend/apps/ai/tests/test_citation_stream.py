"""Citations surface as their own stream event.

The Anthropic location variants are NOT uniform — a document citation carries
`document_title` and neither `source` nor `title`, so a direct attribute read
would raise inside the stream loop, where the exception is swallowed into an
opaque error event.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from apps.ai.providers.claude import _citation_event
from apps.ai.types import ChatMessage, CitationEvent, RunRequest


class _SearchResultLocation:
    type = "search_result_location"
    source = "news://7"
    title = "Fed holds rates"
    cited_text = "left the target range unchanged"


class _CharLocation:
    """A Files-API document citation: no `source`, no `title`."""

    type = "char_location"
    document_title = "10-K.pdf"
    document_index = 0
    cited_text = "revenue grew 12%"
    start_char_index = 10
    end_char_index = 26


def test_search_result_citation_maps_source_and_title():
    evt = _citation_event(_SearchResultLocation())

    assert evt == CitationEvent(
        location="search_result_location",
        source="news://7",
        title="Fed holds rates",
        cited_text="left the target range unchanged",
    )


def test_document_citation_does_not_raise_on_missing_attributes():
    evt = _citation_event(_CharLocation())

    assert evt.location == "char_location"
    assert evt.source == ""
    assert evt.title == "10-K.pdf"
    assert evt.cited_text == "revenue grew 12%"


def test_citation_event_tolerates_a_bare_object():
    evt = _citation_event(None)

    assert evt == CitationEvent()


def test_provider_emits_a_citation_event_from_the_stream():
    from apps.ai.providers.claude import ClaudeProvider

    final = MagicMock(
        stop_reason="end_turn",
        content=[MagicMock(type="text", text="ok")],
        usage=MagicMock(input_tokens=1, output_tokens=1, cache_read_input_tokens=0),
    )
    cm = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = cm
    ctx.__aexit__.return_value = False

    async def aiter(_self):
        yield MagicMock(type="text", text="Rates held. ")
        yield MagicMock(type="citation", citation=_SearchResultLocation())

    cm.__aiter__ = aiter
    cm.get_final_message = AsyncMock(return_value=final)

    async def drain():
        out = []
        req = RunRequest(
            model="claude-opus-5",
            system="",
            messages=[ChatMessage(role="user", content="hi")],
        )
        async for evt in ClaudeProvider(api_key="x").run(req):
            out.append(evt)
        return out

    with patch("apps.ai.providers.claude.AsyncAnthropic") as ac:
        ac.return_value.messages.stream = MagicMock(return_value=ctx)
        events = asyncio.run(drain())

    citations = [e for e in events if isinstance(e, CitationEvent)]
    assert len(citations) == 1
    assert citations[0].source == "news://7"
