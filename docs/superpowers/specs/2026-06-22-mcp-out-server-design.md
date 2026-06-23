# MCP-Out Server — Design

**Written 2026-06-22.** Feature #19. Expose the second brain (house view, theses,
predictions, recall) as MCP tools so external agents (Claude Desktop, this CLI)
can query it. Dependency-free: a hand-rolled JSON-RPC 2.0 endpoint (the MCP
protocol surface is small) — no `mcp` SDK (which would need an image rebuild).

## Transport
`POST /api/mcp/` — JSON-RPC 2.0, synchronous JSON responses (MCP Streamable-HTTP
compatible; SSE deferred). Read-only; same 127.0.0.1 boundary (no auth).

## Methods
- `initialize` → `{protocolVersion, serverInfo:{name,version}, capabilities:{tools:{}}}`.
- `notifications/initialized` → accepted (no result).
- `tools/list` → the 4 tool schemas (name, description, inputSchema).
- `tools/call` (params {name, arguments}) → `{content:[{type:"text", text:<json>}]}`.
- Unknown method → JSON-RPC error -32601; unknown tool → -32602.

## Tools (read-only)
- `house_view(ticker)` → CoverageNote stance/conviction/cases.
- `theses(ticker?, status?)` → tracked Thesis rows.
- `predictions(ticker?, status?)` → AIPrediction rows.
- `recall_search(query, k?)` → recall.search hits.

## Module
`apps/core/mcp.py` (pure dispatch + tool fns) + a `mcp_endpoint` view in core.views
+ route `/api/mcp/` (top-level, before generic api/). Tool fns query the models
directly (.values()), defensive.

## Tests
initialize handshake, tools/list lists 4 tools, each tool returns expected rows,
unknown method/tool → JSON-RPC error, non-POST → 405.

## Out of scope
SSE streaming, auth/tokens, write tools, MCP resources/prompts (tools only in v1).
