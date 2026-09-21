"""tv_* schemas ride the RunRequest only via the sync request-assembly path."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.ai.tools import Toolset, ToolSpec
from apps.profiles.models import TradingProfile
from apps.threads._request import _resolve_capabilities
from apps.threads.models import Thread


def _tv_toolset() -> Toolset:
    ts = Toolset()
    ts.register(
        ToolSpec(
            name="tv_get_news",
            description="d",
            input_schema={"type": "object"},
            fn=lambda **k: None,
        )
    )
    return ts


@pytest.mark.django_db
@pytest.mark.parametrize(("provider", "key"), [("claude", "name"), ("openai", None)])
def test_resolve_capabilities_merges_tradingview_schemas(provider, key):
    prof = TradingProfile.objects.create(name="p", style="x", enable_tools=True)
    thread = Thread.objects.create(kind="chat", profile=prof)
    with patch("apps.ai.tools.tradingview.tradingview_toolset", return_value=_tv_toolset()):
        caps = _resolve_capabilities(thread, provider_name=provider, supports_tools=True)
    names = {t["name"] if key else t["function"]["name"] for t in caps.tools}
    assert {"get_quote", "tv_get_news"} <= names


@pytest.mark.django_db
def test_resolve_capabilities_without_enable_tools_has_no_tools():
    prof = TradingProfile.objects.create(name="p", style="x", enable_tools=False)
    thread = Thread.objects.create(kind="chat", profile=prof)
    with patch("apps.ai.tools.tradingview.tradingview_toolset") as tv:
        caps = _resolve_capabilities(thread, provider_name="claude", supports_tools=True)
    assert caps.tools == []
    tv.assert_not_called()
