"""MCP-out server (#19): expose the second brain as JSON-RPC tools over HTTP.

A dependency-free, minimal MCP server — the protocol surface is just JSON-RPC 2.0
``initialize`` / ``tools/list`` / ``tools/call`` (+ the ``initialized``
notification). Read-only tools over coverage / theses / predictions / recall, so
external agents (Claude Desktop, this CLI) can ask "what's our house view on NVDA?".
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "ledger-second-brain", "version": "1.0.0"}

TOOLS = [
    {
        "name": "house_view",
        "description": "The current house view (CoverageNote) for a ticker — stance, conviction, bull/bear case.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "theses",
        "description": "Tracked trade theses, optionally filtered by ticker and/or status.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}, "status": {"type": "string"}},
        },
    },
    {
        "name": "predictions",
        "description": "AI directional predictions, optionally filtered by ticker and/or status.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}, "status": {"type": "string"}},
        },
    },
    {
        "name": "recall_search",
        "description": "Semantic + keyword search over the second brain (snapshots, theses, observations).",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
            "required": ["query"],
        },
    },
]


def _house_view(args: dict):
    from apps.strategy.models import CoverageNote

    t = (args.get("ticker") or "").upper()
    note = (
        CoverageNote.objects.filter(ticker=t)
        .values("ticker", "stance", "conviction", "bull_case", "bear_case", "updated_at")
        .first()
    )
    return note or {"ticker": t, "found": False}


def _theses(args: dict):
    from apps.thesis.models import Thesis

    qs = Thesis.objects.all()
    if args.get("ticker"):
        qs = qs.filter(ticker=str(args["ticker"]).upper())
    if args.get("status"):
        qs = qs.filter(status=args["status"])
    return list(qs.order_by("-id").values("id", "ticker", "direction", "status", "conviction")[:50])


def _predictions(args: dict):
    from apps.observer.models import AIPrediction

    qs = AIPrediction.objects.all()
    if args.get("ticker"):
        qs = qs.filter(ticker=str(args["ticker"]).upper())
    if args.get("status"):
        qs = qs.filter(status=args["status"])
    return list(
        qs.order_by("-predicted_at").values(
            "id",
            "ticker",
            "direction",
            "horizon_days",
            "confidence",
            "status",
            "verdict",
            "forward_return_pct",
        )[:50]
    )


def _recall_search(args: dict):
    from apps.recall.services.search import search

    k = max(1, min(20, int(args.get("k") or 10)))
    return search(args.get("query") or "", k=k)


_DISPATCH = {
    "house_view": _house_view,
    "theses": _theses,
    "predictions": _predictions,
    "recall_search": _recall_search,
}


def _ok(rpc_id, result):
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _err(rpc_id, code, message):
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def handle(payload: dict) -> dict | None:
    """Dispatch one JSON-RPC request; return the response dict, or None for a
    notification (which gets a 202 with no body)."""
    method = payload.get("method")
    rpc_id = payload.get("id")

    if method == "initialize":
        return _ok(
            rpc_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _ok(rpc_id, {"tools": TOOLS})
    if method == "tools/call":
        params = payload.get("params") or {}
        name = str(params.get("name") or "")
        fn = _DISPATCH.get(name)
        if fn is None:
            return _err(rpc_id, -32602, f"Unknown tool: {name}")
        try:
            result = fn(params.get("arguments") or {})
        except Exception:
            # A tool failure is an MCP tool error (isError), not a transport error.
            # Log the detail server-side; never expose raw exception text to clients
            # (information exposure — flagged by CodeQL).
            log.exception("MCP tool %s failed", name)
            return _ok(
                rpc_id,
                {
                    "content": [{"type": "text", "text": "error: internal tool failure"}],
                    "isError": True,
                },
            )
        return _ok(rpc_id, {"content": [{"type": "text", "text": json.dumps(result, default=str)}]})

    return _err(rpc_id, -32601, f"Unknown method: {method}")
