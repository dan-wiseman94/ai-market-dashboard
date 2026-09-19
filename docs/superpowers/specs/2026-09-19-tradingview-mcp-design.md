# TradingView MCP Integration — Design

**Written 2026-09-19.** Connect the dashboard to TradingView's official MCP server
(`https://mcp.tradingview.com/mcp`) so that (1) the in-app AI can call TradingView's
read-only tools during thread, observer, trigger, and investigate runs, and (2) TradingView
serves as the first market-data fallback provider (bars, quotes, news, calendars) when
Schwab is not connected. The connection is OAuth 2.1 with the user's TradingView account,
managed from Settings → Connections like Schwab.

Approach: an in-app, dependency-free MCP *client* (JSON-RPC 2.0 over Streamable HTTP on the
existing `httpx` dependency), symmetric with the hand-rolled MCP-out server in
`apps/core/mcp.py`. Tools bridge into the shared `Toolset`, so Claude, OpenAI, and Local all
get them (provider parity, unlike Anthropic's Claude-only MCP connector). The official `mcp`
SDK was rejected: new dependency, async-first API in a sync Celery/ORM codebase, image rebuild.

## 1. Facts about the server (verified 2026-09-19)

- Endpoint `https://mcp.tradingview.com/mcp`, Streamable HTTP. Unauthenticated POST → 401 with
  `WWW-Authenticate: Bearer resource_metadata="https://mcp.tradingview.com/.well-known/oauth-protected-resource/mcp"`.
- Protected-resource metadata: `authorization_servers: ["https://www.tradingview.com"]`,
  `bearer_methods_supported: ["header"]`.
- Authorization-server metadata at `https://www.tradingview.com/.well-known/oauth-authorization-server`:
  authorize `/mcp/oauth/authorize`, token `/mcp/oauth/token`, revoke `/mcp/oauth/revoke`,
  registration `/mcp/oauth/register` (dynamic client registration), grants
  `authorization_code` + `refresh_token`, PKCE `S256`, token-endpoint auth `none` allowed
  (public client), scopes `mcp:read`, `mcp:tools`.
- Requires an Essential-or-above TradingView plan; ~100 tool calls/min per user. Toolset is
  in beta (42 tools today across watchlists, market data, search, screener, news,
  fundamentals, documents, calendars, alerts). Symbols are `EXCHANGE:TICKER`
  (`NASDAQ:AAPL`); `search_symbols` resolves bare tickers.
- `get_ohlcv(symbol, interval, count≤5000, summary)` returns bars `[{t (unix s), o, h, l, c, v}]`.
  `get_symbol_data_batch(symbols≤50, columns)` returns screener columns (`close`, `change`,
  `volume`, …). `get_news` returns `{id, title, published (unix), provider, storyPath, link,
  relatedSymbols, …}` plus `has_more`. Calendars: `get_earnings_calendar(symbols)`,
  `get_economic_calendar(country/currency/category)`.

Exact parameter enums and result field names are confirmed from the live `tools/list` during
implementation (see §9) — the normalizers are written defensively against the shapes above.

## 2. Components and files

| Concern | File | Notes |
|---|---|---|
| OAuth 2.1 flow + token lifecycle | `backend/apps/secrets/tradingview_oauth.py` (new) | Mirrors `schwab_oauth.py` |
| Connection endpoints | `backend/apps/secrets/views.py`, `urls.py`, `data_sources.py` | Under the existing `/api/schwab/data-sources/` prefix |
| MCP transport | `backend/apps/market/services/tradingview_mcp.py` (new) | `list_tools`, `call_tool`, `probe`, session + retry |
| Market-data normalizers | `backend/apps/market/services/tradingview.py` (new) | bars/quotes/news/earnings/macro + symbol mapping |
| Fallback wiring | `backend/apps/market/services/fallback.py`, `events.py` | TradingView first among fallbacks |
| AI tool bridge | `backend/apps/ai/tools/tradingview.py` (new), `tools/__init__.py`, `tools/registry.py` | Allowlist, `tv_` prefix, dynamic dispatch |
| Request assembly | `backend/apps/threads/_request.py`, `threads/tasks.py` | Two sync call sites switch to `request_toolset()` |
| Runtime toggle | `backend/apps/core/models.py`, `runtime_config.py`, `feature_flags.py`, `config/settings/base.py` | `tradingview_tools_enabled` |
| Settings UI | `frontend/src/components/settings/DataSourcesPanel.tsx`, `api/dataSources.ts`, `api/settings.ts` | Generic OAuth card + toggle |

No new Celery tasks, no new compose services, no new Python or JS dependencies.

## 3. Connection (OAuth 2.1)

### 3.1 Settings
- `TRADINGVIEW_MCP_URL` (str, default `https://mcp.tradingview.com/mcp`). The only host the
  client ever talks to for MCP; metadata URLs derive from it and from the authorization-server
  metadata. No user input reaches any URL (no SSRF surface).
- `TRADINGVIEW_CALLBACK_URL` (str, default
  `https://127.0.0.1:8000/api/schwab/data-sources/tradingview/callback/`) — served by the dev
  `tls-proxy`, same origin as the Schwab callback.
- `TRADINGVIEW_TOOLS_ENABLED` (`env.bool`, default False) — the env default behind the
  `SystemSettings.tradingview_tools_enabled` override (§6). Registered in
  `apps/core/feature_flags.py` (category `feature`) in the same change, or the inventory gate reds.

### 3.2 Credential row
`ApiCredential.PROVIDER_CHOICES` gains `("tradingview", "TradingView")` (migration). The
encrypted `token` dict holds:

```
{access_token, refresh_token, token_type, scope, expires_at (int epoch),
 client_id, client_secret (only if registration returned one), registered_at}
```

`expires_at` is mirrored to the column. All reads go through `decrypt_token("tradingview")`
(degrades to `None`), per the repo rule. There is no `DATA_SOURCE_ENV_KEYS` entry — an OAuth
token cannot be env-provided.

### 3.3 Flow (`tradingview_oauth.py`)
- `discover()` — resolve authorization-server metadata. Try the RFC 9728 path-based document
  (`<scheme>://<host>/.well-known/oauth-protected-resource<path>`); if that is not a 200 JSON
  document, POST an unauthenticated `initialize` and parse `resource_metadata` from the 401's
  `WWW-Authenticate`. Take `authorization_servers[0]`, then GET
  `<issuer>/.well-known/oauth-authorization-server`. Result cached in Redis
  (`tradingview:oauth:metadata`, 24 h). Any failure raises `TradingViewOAuthError`.
- `register_client(meta)` — POST `registration_endpoint` with `client_name="Ledger"`,
  `redirect_uris=[TRADINGVIEW_CALLBACK_URL]`, `grant_types=["authorization_code","refresh_token"]`,
  `response_types=["code"]`, `token_endpoint_auth_method="none"`, `scope="mcp:read mcp:tools"`.
  A fresh client is registered on every Connect click (always valid; no stale-client failure
  mode). Registration errors surface to the UI as a 502 with the server's `error_description`
  (scrubbed by `safe_log.scrub_secret_params`).
- `build_authorize_url()` — mint `state` (`token_urlsafe(32)`) and a PKCE verifier
  (`token_urlsafe(64)`, challenge = base64url(SHA-256)), register the client, store
  `{client_id, client_secret, code_verifier}` as JSON under `tradingview:oauth:state:<state>`
  (TTL 600 s; per-nonce keys as in Schwab so concurrent Connect clicks stay independent).
  Return `authorization_endpoint` + `response_type=code`, `client_id`, `redirect_uri`,
  `scope=mcp:read mcp:tools`, `state`, `code_challenge`, `code_challenge_method=S256`,
  `resource=<TRADINGVIEW_MCP_URL>` (RFC 8707, required by the MCP authorization spec).
- `consume_oauth_state(state)` — atomic `GETDEL`; returns the stored dict or `None`
  (fail-closed on missing/empty/Redis error — CSRF/auth-code-injection guard, RFC 6749 §10.12).
- `exchange_code(code, flow)` — POST `token_endpoint` form: `grant_type=authorization_code`,
  `code`, `redirect_uri`, `client_id`, `code_verifier`, `resource` (+ `client_secret` when
  present). Stamp `expires_at = now + expires_in` (default 3600 when absent) and carry
  `client_id`/`client_secret` into the token dict.
- `refresh(token)` — POST `grant_type=refresh_token`, `refresh_token`, `client_id`, `resource`
  (+ secret). If the response omits `refresh_token`, keep the previous one.
- `persist_token(token)` — `update_or_create`; on `InvalidToken` (row encrypted under a rotated
  key) delete + create so reconnect is self-healing (Schwab pattern). Clears the
  `provider_health` auth-error marker.
- `ensure_fresh_token() -> str | None` — the accessor every MCP request uses. Returns the
  access token; when fewer than 60 s remain it refreshes under a Redis lock
  (`tradingview:oauth:refresh_lock`, `SET NX EX 30`) so web and worker cannot double-refresh a
  rotating refresh token: acquire → re-read the row (another process may have refreshed) →
  refresh only if still stale → persist. If the lock is held, poll the row for up to 5 s for a
  fresher `expires_at`, else return the current token. A refresh rejected with 400/401
  (`invalid_grant`) marks `provider_health.mark_auth_error("tradingview", "TradingView rejected
  the stored token; reconnect in Settings → Connections.")` and returns `None`. No beat task:
  refresh is lazy, so `scheduled_tasks.py` is untouched.
- `revoke_and_disconnect()` — best-effort POST `revocation_endpoint` (`token=<refresh_token>`,
  `client_id`; errors ignored), delete the row, clear the marker, clear the cached tool list and
  the process-local MCP session id.
- `MOCK_EXTERNAL`: `build_authorize_url` returns the callback URL with `?code=MOCK_OAUTH&state=mock`;
  the callback skips the state check in mock mode (as Schwab does); `exchange_code` returns a
  canned token; no HTTP anywhere.

### 3.4 Endpoints (`apps/secrets`, mounted at `/api/schwab/`)
| Route | Behaviour |
|---|---|
| `GET data-sources/tradingview/authorize/` | `{url}`; 502 `tradingview_registration_failed` with a safe message on discovery/registration failure |
| `GET data-sources/tradingview/callback/` | `?error=` → redirect `${FRONTEND_BASE_URL}/settings?tradingview=denied`; missing code → 400 `missing_code`; bad state → 400 `invalid_state`; exchange failure → 502 `oauth_exchange_failed`; success → persist + redirect `/settings?tradingview=connected` |
| `POST data-sources/tradingview/test/` | Existing `data_source_test` view: for `tradingview` run `tradingview_mcp.probe()` → `{ok, message}` ("Connected — N tools available" / the failure reason). Schwab keeps its 400 |
| `DELETE data-sources/tradingview/` | Existing `data_source_detail`: for `tradingview` call `revoke_and_disconnect()` and return the status. PUT stays 400 for OAuth sources |
| `GET data-sources/` | `tradingview` entry (`auth: "oauth"`, `fields: []`, blurb, `docs_url` = the MCP docs page). For OAuth entries the status carries `configured` (token present) and a new `auth_error` (from `provider_health`, else `null`) |

These are plain Django views like the rest of the data-source surface, so they are outside
the OpenAPI schema and schemathesis; the e2e API lane covers them instead (§8).

## 4. MCP transport (`apps/market/services/tradingview_mcp.py`)

- Exceptions: `TradingViewMCPError` (transport/protocol), `TradingViewNotConnected`
  (no usable token), `TradingViewToolError` (a `tools/call` result with `isError`),
  `TradingViewRateLimited` (HTTP 429).
- `_post(message)` — `httpx.post(TRADINGVIEW_MCP_URL, json=message, timeout=20)` with
  `Authorization: Bearer <token>`, `Accept: application/json, text/event-stream`,
  `Content-Type: application/json`, `MCP-Protocol-Version: 2025-06-18`, and `Mcp-Session-Id`
  when known. Response handling: `application/json` → the JSON-RPC object; `text/event-stream`
  → parse `data:` lines, JSON-decode each, return the message whose `id` matches the request
  (server-initiated requests/notifications on the stream are ignored); HTTP 202 → `None`.
- Session: process-local `_session_id`. `_ensure_session()` sends `initialize`
  (`protocolVersion="2025-06-18"`, `clientInfo={name:"ledger", version}`) and captures the
  `Mcp-Session-Id` response header if the server sets one, then `notifications/initialized`.
  A 404 on any later call resets the session and re-initializes once. A stateless server
  (no session header) just works.
- Auth: token from `ensure_fresh_token()`; `None` → `TradingViewNotConnected`. A 401 forces one
  refresh and one retry; a second 401 marks the auth-error and raises `TradingViewNotConnected`.
  429 → `TradingViewRateLimited` (no retry; the ~100/min budget is the user's). Any other
  non-2xx → `TradingViewMCPError`. A JSON-RPC `error` object → `TradingViewMCPError(code, message)`.
- `list_tools(*, use_cache=True) -> list[dict]` — follows `nextCursor` pagination; cached in
  Redis (`tradingview:mcp:tools`, 3600 s) via `cache.get_or_fetch`.
- `call_tool(name, arguments) -> Any` — `tools/call`. `isError` → `TradingViewToolError(text)`.
  Prefer `structuredContent` when present; else collect `text` blocks, JSON-decode each that
  parses, and return the single value or the list; else the joined text.
- `probe() -> {ok, message}` — uncached `list_tools()`; never raises (Test button).
- `MOCK_EXTERNAL`: `list_tools` returns a fixed catalogue of seven canned schemas
  (`search_symbols`, `get_ohlcv`, `get_symbol_data_batch`, `get_news`, `get_earnings_calendar`,
  `get_economic_calendar`, and the write tool `create_alert` to prove the allowlist filters it);
  `call_tool` returns deterministic canned results keyed by tool name (30 daily bars at 150±2,
  one headline per symbol, one earnings row, one CPI row). The normalizers in §5 run unchanged
  over these, so the e2e stack exercises the real code paths.
- Never log the bearer token; log errors via `safe_log.safe_err`.

## 5. Market-data provider (`apps/market/services/tradingview.py`)

- `is_connected() -> bool` — a token with `access_token` exists AND
  `provider_health.auth_error("tradingview")` is `None`. The marker (1 h TTL) acts as a circuit
  breaker: after a rejected token, fallback and tool assembly stop consulting TradingView
  instead of paying a failing round trip per call.
- Symbol mapping `to_tv_symbol(ticker) -> str | None`:
  - Indices: `$VIX→TVC:VIX`, `$SPX→SP:SPX`, `$NDX→NASDAQ:NDX`, `$DJI→DJ:DJI`, `$RUT→TVC:RUT`,
    `$TNX→TVC:TNX`. Breadth internals (`$ADVN`, `$DECN`, `$TICK`, `$TRIN`) map to `None`.
  - Futures roots: `/ES→CME_MINI:ES1!`, `/NQ→CME_MINI:NQ1!`, `/RTY→CME_MINI:RTY1!`,
    `/YM→CBOT_MINI:YM1!`, `/CL→NYMEX:CL1!`, `/GC→COMEX:GC1!`, `/ZB→CBOT:ZB1!`, `/ZN→CBOT:ZN1!`,
    `/VX→CFE:VX1!`, `/6E→CME:6E1!`.
  - Equities/ETFs: `search_symbols(query=<ticker>, type_filter="stock")`, first hit whose
    ticker equals the input, preferring US exchanges (NASDAQ, NYSE, AMEX, CBOE); if none,
    retry with `type_filter="etf"`; else `None`. Resolutions cache in Redis
    (`tradingview:symbol:<TICKER>`, 7 days). A `None` symbol makes every fetcher return empty
    for that ticker (never raises).
- `fetch_bars(ticker, *, timeframe, limit) -> list[dict]` — `get_ohlcv(symbol, interval,
  count=limit, summary=False)`; interval map `1m→"1"`, `5m→"5"`, `15m→"15"`, `1h→"60"`,
  `1d→"1D"` (confirmed against the live enum in §9). Normalize `{t,o,h,l,c,v}` to the BARS
  CONTRACT `{open, high, low, close, volume, ts (ISO UTC)}`, ascending; drop malformed bars;
  `persist_bars(ticker, timeframe, bars, source="tradingview")`; cache
  `tradingview:ohlc:<ticker>:<tf>:<limit>` with `ttl_for_kind("ohlc_<tf>")`. `[]` on any error.
- `fetch_quotes(tickers) -> dict[str, dict]` — one `get_symbol_data_batch(symbols, columns=
  ["close","change","volume","high","low"])`; QUOTES CONTRACT `{last=close, bid=None,
  ask=None, volume, high, low, pct_change=change}` keyed by the app's ticker spelling.
  `{}` on error.
- `fetch_news(tickers, *, limit) -> list[dict]` — `get_news(symbol, limit)` per ticker (at most
  five tickers, like the other news providers); items in the news-provider shape
  (`headline=title`, `summary=""`, `url=link or https://www.tradingview.com<storyPath>`,
  `source=provider`, `datetime=published`, `tickers=[ticker]`, `id`), upserted into `NewsItem`
  with `provider="tradingview"` (mirrors Marketaux). `[]` on error.
- `fetch_earnings(tickers) -> list[dict]` — `get_earnings_calendar(symbols)` → rows in the
  shape `events._upsert_earnings` consumes (`symbol`, `date` YYYY-MM-DD, `hour` bmo/amc/"",
  `epsEstimate`, `revenueEstimate`). `_upsert_earnings` gains a `source` parameter
  (default `"finnhub"`); TradingView rows persist as `source="tradingview"`.
- `fetch_economic_calendar(*, ahead_days) -> list[dict]` — `get_economic_calendar` for the
  US, next `ahead_days` days → rows in the shape `_upsert_macro` consumes (`event`, `impact`,
  `country="US"`, `time` ISO, `estimate`, `prev`, `actual`). `_macro_kind`'s keyword table is
  extended so TradingView's event names ("Fed Interest Rate Decision", "Consumer Price Index
  (MoM)", "Non Farm Payrolls", "Core PCE Price Index", "GDP Growth Rate QoQ") classify to
  `fomc/cpi/nfp/pce/gdp`; unmatched names are skipped as today.

### 5.1 Fallback precedence (`fallback.py`, `events.py`)
- `alt_quotes`: **tradingview** → alpaca → twelvedata.
- `alt_bars`: **tradingview** (every timeframe) → alpaca → twelvedata → tiingo/polygon (daily).
- `alt_news`: **tradingview** → marketaux → tiingo (still only when Finnhub has no key).
- `alt_chain`: unchanged (TradingView exposes no option chain).
- `fetch_earnings`: Finnhub when keyed (unchanged); else TradingView when connected; else `[]`.
- `fetch_macro`: Finnhub (unchanged, 403 on free keys) → TradingView when connected → the
  `SEED_MACRO_EVENTS` fallback. A connected TradingView therefore retires the hand-maintained
  seed as the live macro source.
- The existing rule stands: the first *configured* provider answers, even if it answers empty.
  "Configured" for TradingView is `is_connected()`, so an auth-error marker skips it.
- `MarketEvent.source` and `NewsItem.provider` (`max_length=16`) fit `"tradingview"` (11).

## 6. AI tool bridge (`apps/ai/tools/tradingview.py`)

- `TRADINGVIEW_TOOL_ALLOWLIST` (frozen, explicit, read-only — 25 names):
  `list_watchlists`, `get_watchlist`, `get_active_watchlist`, `get_ohlcv`,
  `get_economic_data`, `get_economic_symbols`, `search_symbols`, `run_screener`,
  `get_symbol_data`, `get_symbol_data_batch`, `get_screener_columns`, `get_technicals_rating`,
  `get_news`, `get_news_story`, `get_forecasts`, `get_financials`, `get_financial_history`,
  `get_documents`, `get_document_view`, `get_earnings_calendar`, `get_economic_calendar`,
  `get_dividends_calendar`, `list_alerts`, `get_alerts`, `get_alerts_log`.
  Write tools (create/update/delete/stop/restart for watchlists and alerts) are never exposed,
  matching the app's strictly-observational posture. New beta tools do not appear until added
  here; tools TradingView removes simply drop out (allowlist ∩ live list).
- Naming: every bridged tool is `tv_<name>` (e.g. `tv_get_ohlcv`) so provenance is visible in
  `ToolCall` rows and the thread UI, and native names (`fetch_ohlc`, `search_news`) cannot
  collide. Descriptions become `"TradingView: <server description>"`; tools whose schema has a
  `symbol`/`symbols` property get the suffix
  `" Symbols are EXCHANGE:TICKER (e.g. NASDAQ:AAPL, CME_MINI:ES1!, TVC:VIX); use
  tv_search_symbols to resolve a bare ticker."`. Input schemas pass through verbatim
  (`type: "object"` enforced).
- Gating: `tradingview_toolset() -> Toolset` returns an **empty** toolset unless
  `runtime_config().tradingview_tools_enabled` is true AND
  `apps.market.services.tradingview.is_connected()`.
  Otherwise it builds specs from the cached `list_tools()`; a transport error logs and returns
  empty (a TradingView outage never fails an AI run). The toggle is global (`SystemSettings`,
  §6.1) — connect for data fallback, opt the AI in separately.
- **Async-ORM landmine.** `default_toolset()` is called *inside* the providers' async
  streaming loops (`claude._resolve_toolset`, `openai._resolve_toolset`), so it must stay
  free of ORM and network I/O. Therefore:
  - `Toolset` gains `dynamic_resolvers: list[Callable[[str], ToolSpec | None]]`, consulted by
    `run()` on a name miss, and `merge(other)`.
  - `default_toolset()` registers `apps.ai.tools.tradingview.resolve_dynamic` — pure: `tv_<name>` with
    `<name>` in the allowlist → a `ToolSpec` whose `fn` calls `call_tool(name, kwargs)`;
    anything else → `None`. Dispatch already runs under
    `sync_to_async(thread_sensitive=True)`, so the ORM/network work inside `call_tool` is safe.
  - A new sync `registry.request_toolset()` = `default_toolset().merge(tradingview_toolset())`.
    The two sync call sites that build request tool *schemas* —
    `_request._resolve_capabilities` and `tasks._apply_investigation_mode` — switch to it.
    Providers keep calling `default_toolset()` for execution.
- Tool results are model-untrusted data; the existing data-boundary directive in
  `coach.build_system_prompt` already covers tool output. Cost: TradingView schemas add roughly
  3–6k prompt tokens per tool-enabled run (cached on Claude via the system/tools prefix).

### 6.1 Runtime toggle
- `SystemSettings.tradingview_tools_enabled = BooleanField(null=True, blank=True)` (migration);
  `_SPEC` entry `("tradingview_tools_enabled", "TRADINGVIEW_TOOLS_ENABLED", False)`;
  `RuntimeConfig` field; `EDITABLE_FIELDS` derives it, so `PATCH /api/settings/` accepts it.
  It is a sync-context knob (read in the Celery task), which the runtime-config contract allows.

## 7. Settings UI (frontend)

- `DataSourcesPanel.tsx` now excludes only `schwab` (which keeps its own card) and renders an
  OAuth variant for `auth === "oauth"` entries: status pill (Connected / Not connected;
  `auth_error` rendered as the same `role="alert"` box the Schwab card uses), **Connect** (GET
  authorize → `window.open(url, "_blank", "noopener,noreferrer")`, as Schwab), and when
  connected **Test connection** and **Disconnect**. For `tradingview` the card also shows a
  checkbox "Expose TradingView tools to the AI" bound to `useSystemSettings()` and
  `updateSystemSettings({ tradingview_tools_enabled })`, invalidating `["system-settings"]`.
- `api/dataSources.ts`: `fetchDataSourceAuthorizeUrl(provider)`,
  `disconnectDataSource(provider)` (DELETE), `DataSourceStatus.auth_error?: string | null`.
  `api/settings.ts`: `tradingview_tools_enabled: boolean`.
- The Connections page reads `?tradingview=connected|denied` on mount, shows a success or
  error toast, invalidates `["data-sources"]`, and strips the query parameter. (The Schwab
  return still arrives as `?schwab=connected` with no handler today; that stays as is.)
- `schema.yml` and `schema.d.ts` regenerate (the settings endpoint is in the schema; see the
  `gen:api` container caveat in memory — run openapi-typescript against a copied schema).

## 8. Testing

Backend (pytest, `httpx`/Redis patched at the boundary with `unittest.mock.patch`):
- `secrets/tests/test_tradingview_oauth.py` — discovery (path-based document, then the
  401-header fallback), registration payload, authorize URL (state stored with verifier +
  client, S256 challenge verifies, `resource` present), `consume_oauth_state` one-shot and
  fail-closed, exchange form fields, refresh keeps the old refresh token when omitted,
  `persist_token` self-heals `InvalidToken`, `ensure_fresh_token` (fresh → no refresh; stale →
  refresh under lock; lock held → re-read; `invalid_grant` → marker + `None`), revoke is
  best-effort, mock-mode flow.
- `secrets/tests/test_tradingview_views.py` — authorize 200 / 502; callback `?error=`,
  missing code, invalid state, exchange failure, success redirect; test endpoint delegates to
  `probe`; DELETE disconnects; data-sources list carries the entry with `auth_error`.
- `market/tests/test_tradingview_mcp.py` — JSON and SSE response parsing (matching id, ignores
  notifications), session id captured and sent, 404 → re-init once, 401 → refresh → retry,
  second 401 → marker + `NotConnected`, 429, JSON-RPC error object, `isError`,
  `structuredContent` preferred, text JSON decoded, `tools/list` pagination, mock catalogue.
- `market/tests/test_tradingview_provider.py` — symbol table, search resolution (US
  preference, ETF retry, cache, `None`), bars normalize/sort/persist, quotes contract, news
  shape + upsert, earnings/macro row shapes and `_macro_kind` names, every fetcher never raises.
- `market/tests/test_fallback.py` — TradingView-first precedence for quotes/bars/news; skipped
  when the auth-error marker is set. `test_events.py` — earnings via TradingView when Finnhub
  is unkeyed; macro prefers TradingView over the seed.
- `ai/tests/test_tradingview_tools.py` — allowlist ∩ live list, `tv_` prefix, write tools
  excluded, symbol note only on symbol-taking tools, empty when toggle off / not connected /
  transport error; `resolve_dynamic` rejects non-allowlisted names; `Toolset.run` consults
  dynamic resolvers; `request_toolset` merges; `_resolve_capabilities` and investigation mode
  emit `tv_*` schemas in both Anthropic and OpenAI shapes only when enabled + connected.
- `core/tests` — runtime-config field, settings PATCH accepts the bool, feature-flag inventory.
- Migrations reviewed with the `migration-reviewer` agent; `make check-migrations` clean.

E2E (`MOCK_EXTERNAL`): one API-lane contract test — authorize → callback → list shows
`tradingview` connected → test → toggle on → disconnect. Frontend (vitest): OAuth card renders
Connect / Test / Disconnect by state, Connect opens a new tab, the toggle PATCHes settings,
`auth_error` renders as an alert.

## 9. Implementation-time verification (needs a live TradingView account)

1. After the OAuth flow lands, the user connects once from Settings. If dynamic registration
   rejects the loopback HTTPS redirect URI, the authorize endpoint's 502 shows the server's
   reason; resolving that (e.g. a different callback host) is a follow-up decision, not a
   silent fallback.
2. Capture the live `tools/list` into `backend/apps/market/tests/fixtures/tradingview_tools_list.json`
   and confirm: the `get_ohlcv` interval enum strings, the bar field names, the
   `get_symbol_data_batch` column names, the news and calendar field names. Adjust the maps in
   §5 if they differ; the fixture then backs the transport and bridge tests.

## 10. Out of scope

Write tools (watchlists/alerts), TradingView alerts as trigger sources, chart images, the
server-to-client SSE channel (GET stream), rate-limit budgeting, generalizing the client to
arbitrary MCP servers, and a dev-side `.mcp.json` entry for Claude Code.

## 11. Documentation to update in the same change

CLAUDE.md (app roster: `secrets` owns the TradingView OAuth, `market/services/tradingview*.py`;
landmines: `request_toolset()` vs `default_toolset()` async-ORM rule, `EXCHANGE:TICKER`
symbol mapping, TradingView-first precedence with the auth-error marker as circuit breaker,
lazy refresh under a Redis lock with no beat task, the explicit allowlist);
`docs/feature-flags.md`; `.env.example`.
