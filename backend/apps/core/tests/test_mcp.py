"""MCP-out server (#19): minimal JSON-RPC 2.0 over /api/mcp/ exposing the second brain."""

from __future__ import annotations

import json

import pytest
from django.test import Client

from apps.core.mcp import handle
from apps.strategy.models import CoverageNote


def test_initialize_handshake():
    r = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r["result"]["protocolVersion"]
    assert r["result"]["serverInfo"]["name"] == "ledger-second-brain"
    assert "tools" in r["result"]["capabilities"]


def test_tools_list_has_the_four_tools():
    r = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in r["result"]["tools"]}
    assert names == {"house_view", "theses", "predictions", "recall_search"}


@pytest.mark.django_db
def test_house_view_tool_returns_coverage_note():
    CoverageNote.objects.create(ticker="NVDA", stance="bull", conviction=3)
    r = handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "house_view", "arguments": {"ticker": "nvda"}},
        }
    )
    data = json.loads(r["result"]["content"][0]["text"])
    assert data["ticker"] == "NVDA" and data["stance"] == "bull"


@pytest.mark.django_db
def test_recall_search_tool_returns_a_list():
    r = handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "recall_search", "arguments": {"query": "nvda"}},
        }
    )
    assert isinstance(json.loads(r["result"]["content"][0]["text"]), list)


def test_unknown_method_and_unknown_tool_are_jsonrpc_errors():
    assert handle({"id": 5, "method": "bogus"})["error"]["code"] == -32601
    r = handle({"id": 6, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
    assert r["error"]["code"] == -32602


def test_initialized_notification_has_no_response():
    assert handle({"method": "notifications/initialized"}) is None


@pytest.mark.django_db
def test_http_endpoint_initialize_and_get_405():
    c = Client()
    r = c.post(
        "/api/mcp/",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["result"]["serverInfo"]["name"] == "ledger-second-brain"
    assert c.get("/api/mcp/").status_code == 405


@pytest.mark.django_db
def test_mcp_requires_bearer_token_when_configured(settings):
    settings.MCP_AUTH_TOKEN = "unit-test-token-placeholder"
    c = Client()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    # no header / wrong token → 401; correct token → 200
    assert c.post("/api/mcp/", data=body, content_type="application/json").status_code == 401
    assert (
        c.post(
            "/api/mcp/",
            data=body,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer nope",
        ).status_code
        == 401
    )
    ok = c.post(
        "/api/mcp/",
        data=body,
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer unit-test-token-placeholder",
    )
    assert ok.status_code == 200


@pytest.mark.django_db
def test_mcp_open_when_token_unset(settings):
    settings.MCP_AUTH_TOKEN = ""  # default — localhost posture, no auth required
    c = Client()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert c.post("/api/mcp/", data=body, content_type="application/json").status_code == 200
