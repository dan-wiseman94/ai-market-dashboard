# TradingView MCP Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the dashboard to TradingView's official MCP server so the in-app AI can call a read-only allowlist of TradingView tools and TradingView serves as the first market-data fallback provider.

**Architecture:** A dependency-free JSON-RPC-over-Streamable-HTTP client on the existing `httpx` dependency, an OAuth 2.1 flow in `apps.secrets` mirroring the Schwab one (per-nonce Redis state, dynamic client registration, PKCE, lazy refresh under a Redis lock), normalizers in `apps.market.services` that feed the existing fallback router, and a bridge in `apps.ai.tools` that turns allowlisted tools into `tv_*` ToolSpecs. Tool schemas resolve on the sync request-assembly path; execution goes through a pure dynamic resolver so the async provider loops never touch the ORM.

**Tech Stack:** Django 6 / DRF, Celery, Redis, `httpx`, pytest + `fakeredis` + `unittest.mock`, React + TanStack Query + vitest.

**Spec:** `docs/superpowers/specs/2026-09-19-tradingview-mcp-design.md`

## Global Constraints

- Everything runs in Docker. From the main checkout: backend tests `docker compose exec web pytest apps/<app>/tests/test_<x>.py -v` (container WORKDIR is `/app/backend`), frontend `docker compose exec frontend pnpm exec vitest run <path>`. **From a worktree** (no `.env` there; the main stack mounts the main checkout's tree, not the worktree's) use the isolated project via the untracked `compose.worktree.yaml` overlay: `DC="docker compose -f compose.yaml -f compose.worktree.yaml -p tvmcp"`; `$DC up -d db redis` once; then `$DC run --rm --no-deps -T web uv run pytest apps/<app>/tests/test_<x>.py -v`, `$DC run --rm --no-deps -T --entrypoint "" -w /app web uv run ruff check backend/apps/<app>` (any `-w /app` run needs `--entrypoint ""`: the image entrypoint runs `manage.py migrate` from the cwd), `$DC run --rm --no-deps -T web uv run python manage.py makemigrations --check --dry-run`, `$DC run --rm --no-deps -T -w /app/backend web uv run python manage.py spectacular --file schema.yml --validate`, and `$DC run --rm --no-deps -T frontend pnpm exec vitest run <path>` / `pnpm run lint`. Every `docker compose exec …` / `make …` command elsewhere in this plan maps onto the matching `$DC run --rm --no-deps -T …` form when executing from the worktree. For the e2e lanes use a dedicated project with the e2e overlay layered LAST and an interpolation file for `${POSTGRES_*}`: `E2E="docker compose -p tvmcp-e2e --env-file worktree.vars -f compose.yaml -f compose.worktree.yaml -f compose.e2e.yaml"`; `$E2E up -d` (API lane: `db-e2e redis web` is enough), `$E2E exec -T --workdir /app web uv run pytest --timeout=180 e2e/api/<file> -m integration -v`, UI lanes via `worker`, `$E2E down -v` when done.
- The worktree has no `lefthook` binary: commit with `LEFTHOOK=0 git commit ...` and run `make lint` before the final task instead.
- A PreToolUse hook rejects Bash commands whose text mentions `.env` — edit `.env.example` with the Edit tool, never via shell.
- No new Python or JS dependencies. No new Celery tasks (`apps/core/scheduled_tasks.py` stays untouched). No new compose services.
- Every new `env.bool` flag gets a `FeatureFlag` entry in `apps/core/feature_flags.py` in the same change (drift gate).
- Never log or echo a bearer/refresh token. Use `apps.market.services.safe_log.safe_err` for exceptions and `scrub_secret_params` for user-facing text.
- Provider selection stays behind `get_provider()`; concrete AI providers are private to `apps.ai` (import-linter).
- `ruff` complexity ≤ 15 per function; mypy zero-baseline — annotate everything.
- Conventional commits, one per task: `feat(secrets): …`, `feat(market): …`, `feat(ai): …`, `feat(frontend): …`, `test(e2e): …`, `docs: …`. End every commit message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Read-only allowlist is fixed at these 25 names: `list_watchlists`, `get_watchlist`, `get_active_watchlist`, `get_ohlcv`, `get_economic_data`, `get_economic_symbols`, `search_symbols`, `run_screener`, `get_symbol_data`, `get_symbol_data_batch`, `get_screener_columns`, `get_technicals_rating`, `get_news`, `get_news_story`, `get_forecasts`, `get_financials`, `get_financial_history`, `get_documents`, `get_document_view`, `get_earnings_calendar`, `get_economic_calendar`, `get_dividends_calendar`, `list_alerts`, `get_alerts`, `get_alerts_log`.

---

## File map

| File | Responsibility |
|---|---|
| `backend/config/settings/base.py` | `TRADINGVIEW_MCP_URL`, `TRADINGVIEW_CALLBACK_URL`, `TRADINGVIEW_TOOLS_ENABLED` |
| `backend/apps/core/feature_flags.py`, `models.py`, `runtime_config.py`, `migrations/0004_…` | The global AI-tools toggle |
| `backend/apps/secrets/models.py`, `migrations/0008_…`, `data_sources.py` | `tradingview` credential provider + catalog card |
| `backend/apps/secrets/tradingview_oauth.py` | Discovery, registration, PKCE authorize, exchange, refresh, persist, lock-guarded freshness, revoke |
| `backend/apps/secrets/views.py`, `urls.py` | authorize / callback / test / disconnect endpoints; OAuth status in the data-sources list |
| `backend/apps/market/services/tradingview_mcp.py` | MCP transport: session, SSE/JSON parsing, 401/404 retry, `list_tools`, `call_tool`, `probe`, mock catalogue |
| `backend/apps/market/services/tradingview.py` | `is_connected`, symbol mapping, bars/quotes/news/earnings/macro normalizers |
| `backend/apps/market/services/fallback.py`, `events.py` | TradingView-first precedence; calendars |
| `backend/apps/ai/tools/__init__.py` | `Toolset.dynamic_resolvers`, `merge`, `resolve` |
| `backend/apps/ai/tools/tradingview.py`, `registry.py` | Allowlist bridge, `resolve_dynamic`, `request_toolset` |
| `backend/apps/threads/_request.py`, `tasks.py` | Schema merge on the two sync call sites |
| `frontend/src/api/dataSources.ts`, `api/settings.ts`, `components/settings/DataSourcesPanel.tsx`, `pages/settings/ConnectionsSettings.tsx` | OAuth card, toggle, return-query toast |
| `e2e/api/test_tradingview_contract.py` | Mock connect → test → toggle → disconnect |
| `CLAUDE.md`, `docs/feature-flags.md`, `.env.example` | Docs |

---

### Task 1: Settings, feature flag, and the `tradingview_tools_enabled` runtime toggle

**Files:**
- Modify: `backend/config/settings/base.py` (after the `MCP_AUTH_TOKEN` block, ~line 264)
- Modify: `backend/apps/core/feature_flags.py` (append to `FEATURE_FLAGS`)
- Modify: `backend/apps/core/models.py` (`SystemSettings`, after `aieval_scheduled_limit`)
- Create: `backend/apps/core/migrations/0004_systemsettings_tradingview_tools_enabled.py`
- Modify: `backend/apps/core/runtime_config.py` (`_SPEC` + `RuntimeConfig`)
- Modify: `docs/feature-flags.md` (opt-in table), `.env.example` (after the Schwab block, Edit tool only)
- Test: `backend/apps/core/tests/test_system_settings.py`

**Interfaces:**
- Produces: `settings.TRADINGVIEW_MCP_URL: str`, `settings.TRADINGVIEW_CALLBACK_URL: str`, `settings.TRADINGVIEW_TOOLS_ENABLED: bool`, `runtime_config().tradingview_tools_enabled: bool`, `PATCH /api/settings/ {"tradingview_tools_enabled": bool}`.

- [ ] **Step 1: Write the failing tests** (append to `backend/apps/core/tests/test_system_settings.py`)

```python
@pytest.mark.django_db
@override_settings(TRADINGVIEW_TOOLS_ENABLED=False)
def test_tradingview_tools_enabled_inherits_then_overrides():
    assert runtime_config().tradingview_tools_enabled is False
    cfg = SystemSettings.load()
    cfg.tradingview_tools_enabled = True
    cfg.save()
    assert runtime_config().tradingview_tools_enabled is True


@pytest.mark.django_db
def test_patch_accepts_tradingview_tools_enabled():
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"tradingview_tools_enabled": True}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["tradingview_tools_enabled"] is True
    assert SystemSettings.load().tradingview_tools_enabled is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/core/tests/test_system_settings.py -k tradingview -v`
Expected: FAIL (`AttributeError`/`unknown_field`).

- [ ] **Step 3: Settings** — add to `backend/config/settings/base.py` right after `MCP_AUTH_TOKEN`:

```python
# TradingView's official MCP server. The client only ever talks to this URL (the OAuth
# metadata URLs derive from it), so no user input reaches a request URL. The callback
# must be reachable by the browser after consent — in dev that's the Caddy tls-proxy.
TRADINGVIEW_MCP_URL = env.str("TRADINGVIEW_MCP_URL", default="https://mcp.tradingview.com/mcp")
TRADINGVIEW_CALLBACK_URL = env.str(
    "TRADINGVIEW_CALLBACK_URL",
    default="https://127.0.0.1:8000/api/schwab/data-sources/tradingview/callback/",
)
# Expose the read-only tv_* TradingView tools to the in-app AI. Env default behind the
# SystemSettings.tradingview_tools_enabled UI override; needs a connected TradingView.
TRADINGVIEW_TOOLS_ENABLED = env.bool("TRADINGVIEW_TOOLS_ENABLED", default=False)
```

- [ ] **Step 4: Feature-flag registry** — append to `FEATURE_FLAGS` in `backend/apps/core/feature_flags.py`:

```python
    FeatureFlag(
        "TRADINGVIEW_TOOLS_ENABLED",
        False,
        "feature",
        "Expose the read-only tv_* TradingView MCP tools to the in-app AI (needs a connected TradingView).",
    ),
```

- [ ] **Step 5: Model field + migration** — in `SystemSettings` after `aieval_scheduled_limit`:

```python
    # TradingView MCP tools for the in-app AI — apps.ai.tools.tradingview.
    tradingview_tools_enabled = models.BooleanField(null=True, blank=True)
```

Create `backend/apps/core/migrations/0004_systemsettings_tradingview_tools_enabled.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_systemsettings_retention_book_days_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsettings",
            name="tradingview_tools_enabled",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
```

- [ ] **Step 6: Runtime config** — in `backend/apps/core/runtime_config.py` append to `_SPEC`:

```python
    ("tradingview_tools_enabled", "TRADINGVIEW_TOOLS_ENABLED", False),
```

and add the dataclass field at the end of `RuntimeConfig`:

```python
    tradingview_tools_enabled: bool
```

- [ ] **Step 7: Docs** — add a row to the "Opt-in product features" table in `docs/feature-flags.md`:

```
| `TRADINGVIEW_TOOLS_ENABLED` | keep opt-in — adds prompt tokens; needs a connected TradingView | Expose the read-only `tv_*` TradingView MCP tools to the in-app AI. Also a UI toggle on the TradingView connection card (`SystemSettings.tradingview_tools_enabled` overrides the env value). |
```

Using the **Edit tool**, add after the `SCHWAB_CALLBACK_URL=` line in `.env.example`:

```
# TradingView official MCP server (OAuth 2.1 — connect from Settings → Connections; no key).
# The callback must be reachable by your browser after consent (dev: the Caddy tls-proxy).
TRADINGVIEW_MCP_URL=https://mcp.tradingview.com/mcp
TRADINGVIEW_CALLBACK_URL=https://127.0.0.1:8000/api/schwab/data-sources/tradingview/callback/
# Expose the read-only tv_* TradingView tools to the in-app AI (the UI toggle overrides this).
TRADINGVIEW_TOOLS_ENABLED=false
```

- [ ] **Step 8: Run tests + gates**

Run: `docker compose exec web pytest apps/core/tests/test_system_settings.py apps/core/tests/test_feature_flag_inventory.py -v` → PASS.
Run: `make check-migrations` → clean. Run: `make schema && git -C /home/dan/ledger/.claude/worktrees/tradingview-mcp diff --stat backend/schema.yml` — commit the regenerated schema if it changed.

- [ ] **Step 9: Commit**

```bash
LEFTHOOK=0 git add -A backend/config backend/apps/core docs/feature-flags.md .env.example backend/schema.yml
LEFTHOOK=0 git commit -m "feat(core): TradingView MCP settings + tradingview_tools_enabled runtime toggle"
```

---

### Task 2: `tradingview` credential provider, data-source catalog card, OAuth status in the list

**Files:**
- Modify: `backend/apps/secrets/models.py` (`ApiCredential.PROVIDER_CHOICES`)
- Create: `backend/apps/secrets/migrations/0008_alter_apicredential_provider.py`
- Modify: `backend/apps/secrets/data_sources.py` (docstring + entry after `schwab`)
- Modify: `backend/apps/secrets/views.py` (`_schwab_connected` → `_oauth_connected`, `_data_source_payload`)
- Test: `backend/apps/secrets/tests/test_data_sources.py`

**Interfaces:**
- Produces: `ApiCredential(provider="tradingview")` rows; `GET /api/schwab/data-sources/` entry `{provider:"tradingview", auth:"oauth", status:{configured, fields_present:[], env_fields:[], auth_error}}`; `views._oauth_connected(provider) -> bool`.

- [ ] **Step 1: Failing tests** (append to `backend/apps/secrets/tests/test_data_sources.py`; add `import fakeredis` at the top)

```python
@pytest.mark.django_db
def test_list_includes_tradingview_oauth_entry(api):
    r = api.get("/api/schwab/data-sources/")
    tv = {d["provider"]: d for d in r.json()["data_sources"]}["tradingview"]
    assert tv["auth"] == "oauth"
    assert tv["fields"] == []
    assert tv["status"]["configured"] is False


@pytest.mark.django_db
def test_list_reports_tradingview_connected_and_auth_error(api):
    ApiCredential.objects.create(provider="tradingview", token={"access_token": "a"})
    fake = fakeredis.FakeStrictRedis()
    with patch("apps.core.provider_health._redis", lambda: fake):
        from apps.core import provider_health

        provider_health.mark_auth_error("tradingview", "rejected")
        r = api.get("/api/schwab/data-sources/")
    tv = {d["provider"]: d for d in r.json()["data_sources"]}["tradingview"]
    assert tv["status"]["configured"] is True
    assert tv["status"]["auth_error"] == "rejected"
    assert "access_token" not in r.content.decode()


@pytest.mark.django_db
def test_put_on_tradingview_is_not_key_managed(api):
    r = api.put("/api/schwab/data-sources/tradingview/", data={"api_key_write": "x"}, format="json")
    assert r.status_code == 400
    assert r.json()["code"] == "not_key_managed"
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/secrets/tests/test_data_sources.py -k tradingview -v` → FAIL (`KeyError: 'tradingview'`).

- [ ] **Step 3: Model + migration** — add `("tradingview", "TradingView"),` after the `fred` tuple in `PROVIDER_CHOICES`. Create `backend/apps/secrets/migrations/0008_alter_apicredential_provider.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("secrets_app", "0007_alter_apicredential_provider"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apicredential",
            name="provider",
            field=models.CharField(
                choices=[
                    ("schwab", "Charles Schwab"),
                    ("finnhub", "Finnhub"),
                    ("marketaux", "Marketaux"),
                    ("alpaca", "Alpaca"),
                    ("tiingo", "Tiingo"),
                    ("twelvedata", "Twelve Data"),
                    ("polygon", "Polygon.io"),
                    ("tradier", "Tradier"),
                    ("fred", "FRED (St. Louis Fed)"),
                    ("tradingview", "TradingView"),
                ],
                max_length=32,
                unique=True,
            ),
        ),
    ]
```

- [ ] **Step 4: Catalog entry** — in `backend/apps/secrets/data_sources.py` change the docstring line for `oauth` to ``- ``oauth`` — Schwab (its own authorize/callback) and TradingView (``data-sources/tradingview/authorize|callback``).`` and insert after the `schwab` dict:

```python
    {
        "provider": "tradingview",
        "label": "TradingView",
        "auth": "oauth",
        "fields": [],
        "blurb": "TradingView's MCP server — OHLCV, screener, fundamentals, news and calendars. "
        "Sign in with your TradingView account (Essential plan or above).",
        "signup_url": "https://www.tradingview.com/pricing/",
        "docs_url": "https://www.tradingview.com/mcp/docs",
    },
```

- [ ] **Step 5: Views** — in `backend/apps/secrets/views.py` add `from apps.core import provider_health` if not already imported (it is: `from apps.core import provider_health`). Replace `_schwab_connected` with:

```python
def _oauth_connected(provider: str) -> bool:
    """True when an OAuth credential row exists for ``provider`` and decrypts."""
    try:
        ApiCredential.objects.get(provider=provider)
    except (ApiCredential.DoesNotExist, InvalidToken):
        return False
    return True


def _schwab_connected() -> bool:
    return _oauth_connected("schwab")
```

and change the `oauth` branch of `_data_source_payload` to:

```python
    elif ds["auth"] == "oauth":
        entry["status"] = {
            "configured": _oauth_connected(ds["provider"]),
            "fields_present": [],
            "env_fields": [],
            "auth_error": provider_health.auth_error(ds["provider"]),
        }
```

- [ ] **Step 6: Run tests + migration check**

Run: `docker compose exec web pytest apps/secrets/tests/test_data_sources.py apps/secrets/tests/test_views.py -v` → PASS. Run: `make check-migrations` → clean. Run the `migration-reviewer` agent on the new migration.

- [ ] **Step 7: Commit**

```bash
LEFTHOOK=0 git add backend/apps/secrets
LEFTHOOK=0 git commit -m "feat(secrets): tradingview credential provider + data-source card with OAuth status"
```

---

### Task 3: OAuth module — discovery, dynamic registration, PKCE authorize URL, one-time state

**Files:**
- Create: `backend/apps/secrets/tradingview_oauth.py`
- Test: `backend/apps/secrets/tests/test_tradingview_oauth.py`

**Interfaces:**
- Consumes: `settings.TRADINGVIEW_MCP_URL`, `settings.TRADINGVIEW_CALLBACK_URL` (Task 1).
- Produces: `TradingViewOAuthError`, `TradingViewTokenRejected`, `SCOPE`, `REJECTED_MESSAGE`, `mcp_url() -> str`, `discover() -> dict`, `register_client(meta) -> dict`, `build_authorize_url() -> str`, `consume_oauth_state(state) -> dict | None`, `_redis()` (patch point), `_protected_resource_metadata_url(resource) -> str`.

- [ ] **Step 1: Failing tests** — create `backend/apps/secrets/tests/test_tradingview_oauth.py`:

```python
"""TradingView MCP OAuth 2.1 client — discovery, registration, PKCE, state, tokens."""

from __future__ import annotations

import base64
import hashlib
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import fakeredis
import httpx
import pytest
from django.test import override_settings

from apps.secrets import tradingview_oauth as tvo

MCP = "https://mcp.tradingview.com/mcp"
CALLBACK = "https://127.0.0.1:8000/api/schwab/data-sources/tradingview/callback/"
AS_META = {
    "issuer": "https://www.tradingview.com",
    "authorization_endpoint": "https://www.tradingview.com/mcp/oauth/authorize",
    "token_endpoint": "https://www.tradingview.com/mcp/oauth/token",
    "registration_endpoint": "https://www.tradingview.com/mcp/oauth/register",
    "revocation_endpoint": "https://www.tradingview.com/mcp/oauth/revoke",
}
PRM = {"resource": MCP, "authorization_servers": ["https://www.tradingview.com"]}


@pytest.fixture
def fake_redis():
    fake = fakeredis.FakeStrictRedis()
    with patch("apps.secrets.tradingview_oauth._redis", lambda: fake):
        yield fake


def _get_by_url(table: dict[str, httpx.Response]):
    def _get(url, **_kw):
        return table.get(url, httpx.Response(404, json={"detail": "Not found"}))

    return _get


def test_protected_resource_metadata_url_is_path_based():
    assert (
        tvo._protected_resource_metadata_url(MCP)
        == "https://mcp.tradingview.com/.well-known/oauth-protected-resource/mcp"
    )


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_discover_uses_path_based_document_and_caches(fake_redis):
    table = {
        "https://mcp.tradingview.com/.well-known/oauth-protected-resource/mcp": httpx.Response(200, json=PRM),
        "https://www.tradingview.com/.well-known/oauth-authorization-server": httpx.Response(200, json=AS_META),
    }
    with patch("apps.secrets.tradingview_oauth.httpx.get", side_effect=_get_by_url(table)) as g:
        assert tvo.discover()["token_endpoint"] == AS_META["token_endpoint"]
        assert tvo.discover()["token_endpoint"] == AS_META["token_endpoint"]  # cached
    assert g.call_count == 2
    assert json.loads(fake_redis.get("tradingview:oauth:metadata"))["issuer"] == AS_META["issuer"]


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_discover_falls_back_to_www_authenticate_pointer(fake_redis):
    pointer = "https://mcp.tradingview.com/.well-known/oauth-protected-resource/mcp"
    table = {
        pointer: httpx.Response(200, json=PRM),
        "https://www.tradingview.com/.well-known/oauth-authorization-server": httpx.Response(200, json=AS_META),
    }
    calls = {"n": 0}

    def _get(url, **_kw):
        calls["n"] += 1
        if calls["n"] == 1:  # first hop: the well-known path answers a non-200
            return httpx.Response(400, json={"detail": "deprecated"})
        return table.get(url, httpx.Response(404))

    challenge = httpx.Response(401, headers={"WWW-Authenticate": f'Bearer resource_metadata="{pointer}"'})
    with (
        patch("apps.secrets.tradingview_oauth.httpx.get", side_effect=_get),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=challenge),
    ):
        assert tvo.discover()["authorization_endpoint"] == AS_META["authorization_endpoint"]


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_discover_raises_when_no_authorization_server(fake_redis):
    with (
        patch("apps.secrets.tradingview_oauth.httpx.get", return_value=httpx.Response(404)),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=httpx.Response(401)),
        pytest.raises(tvo.TradingViewOAuthError),
    ):
        tvo.discover()


@override_settings(TRADINGVIEW_CALLBACK_URL=CALLBACK)
def test_register_client_posts_public_client_payload():
    resp = httpx.Response(201, json={"client_id": "cid-1"})
    with patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp) as p:
        out = tvo.register_client(AS_META)
    assert out == {"client_id": "cid-1", "client_secret": ""}
    body = p.call_args.kwargs["json"]
    assert body["redirect_uris"] == [CALLBACK]
    assert body["token_endpoint_auth_method"] == "none"
    assert body["grant_types"] == ["authorization_code", "refresh_token"]
    assert body["scope"] == "mcp:read mcp:tools"


def test_register_client_surfaces_rejection_message():
    resp = httpx.Response(400, json={"error": "invalid_redirect_uri", "error_description": "loopback not allowed"})
    with (
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp),
        pytest.raises(tvo.TradingViewOAuthError, match="loopback not allowed"),
    ):
        tvo.register_client(AS_META)


@override_settings(TRADINGVIEW_MCP_URL=MCP, TRADINGVIEW_CALLBACK_URL=CALLBACK)
def test_build_authorize_url_carries_pkce_state_and_resource(fake_redis):
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth.register_client", return_value={"client_id": "cid", "client_secret": ""}),
    ):
        url = tvo.build_authorize_url()
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == AS_META["authorization_endpoint"]
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert q["response_type"] == "code"
    assert q["client_id"] == "cid"
    assert q["redirect_uri"] == CALLBACK
    assert q["scope"] == "mcp:read mcp:tools"
    assert q["code_challenge_method"] == "S256"
    assert q["resource"] == MCP
    flow = tvo.consume_oauth_state(q["state"])
    assert flow["client_id"] == "cid"
    digest = hashlib.sha256(flow["code_verifier"].encode()).digest()
    assert q["code_challenge"] == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def test_consume_oauth_state_is_one_time_and_fails_closed(fake_redis):
    tvo._store_flow("s1", {"client_id": "c", "code_verifier": "v"})
    assert tvo.consume_oauth_state(None) is None
    assert tvo.consume_oauth_state("wrong") is None
    assert tvo.consume_oauth_state("s1") == {"client_id": "c", "code_verifier": "v"}
    assert tvo.consume_oauth_state("s1") is None  # replay rejected


@override_settings(TRADINGVIEW_CALLBACK_URL=CALLBACK)
def test_build_authorize_url_is_stub_under_mock():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        url = tvo.build_authorize_url()
    assert url == f"{CALLBACK}?code=MOCK_OAUTH&state=mock"
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/secrets/tests/test_tradingview_oauth.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — create `backend/apps/secrets/tradingview_oauth.py` (Task 4 appends the token half to this same file):

```python
"""TradingView MCP OAuth 2.1 client: discovery, dynamic registration, PKCE authorize,
code exchange, refresh, persistence.

Mirrors ``schwab_oauth`` (per-nonce Redis state, InvalidToken self-heal on reconnect,
provider_health marker) but follows the MCP authorization spec: the authorization
server is discovered from the MCP server's protected-resource metadata (RFC 9728), the
client registers itself dynamically (RFC 7591, a fresh public client per Connect click),
and every authorize/token request carries the MCP server URL as ``resource`` (RFC 8707).
Refresh is lazy (``ensure_fresh_token``) under a Redis lock — there is no beat task.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from secrets import token_urlsafe
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import redis
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.market.services.safe_log import scrub_secret_params

log = logging.getLogger(__name__)

SCOPE = "mcp:read mcp:tools"
CLIENT_NAME = "Ledger"
REJECTED_MESSAGE = "TradingView rejected the stored token; reconnect in Settings → Connections."
_TIMEOUT = 15.0

_STATE_KEY_PREFIX = "tradingview:oauth:state:"
_STATE_TTL_SECONDS = 600  # ample for consent, short enough to bound replay
_METADATA_KEY = "tradingview:oauth:metadata"
_METADATA_TTL_SECONDS = 86_400
_REFRESH_LOCK_KEY = "tradingview:oauth:refresh_lock"
_REFRESH_LOCK_TTL_SECONDS = 30
_REFRESH_SKEW_SECONDS = 60
_RESOURCE_METADATA_RE = re.compile(r'resource_metadata="([^"]+)"')


class TradingViewOAuthError(RuntimeError):
    """Discovery, registration, or token-endpoint failure. Message is client-safe."""


class TradingViewTokenRejected(TradingViewOAuthError):
    """The token endpoint rejected our grant (HTTP 400/401) — a reconnect is required."""


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def mcp_url() -> str:
    return str(settings.TRADINGVIEW_MCP_URL)


# --- discovery -------------------------------------------------------------------------


def _protected_resource_metadata_url(resource: str) -> str:
    """RFC 9728 path-based document: insert the well-known segment before the path."""
    parts = urlsplit(resource)
    path = parts.path.rstrip("/")
    return urlunsplit(
        (parts.scheme, parts.netloc, f"/.well-known/oauth-protected-resource{path}", "", "")
    )


def _get_json(url: str) -> dict | None:
    try:
        resp = httpx.get(url, headers={"Accept": "application/json"}, timeout=_TIMEOUT)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _resource_metadata_url_from_challenge() -> str | None:
    """Fallback discovery: an unauthenticated ``initialize`` answers 401 with a
    ``WWW-Authenticate: Bearer resource_metadata="…"`` pointer."""
    try:
        resp = httpx.post(
            mcp_url(),
            json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}},
            headers={"Accept": "application/json, text/event-stream"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        return None
    match = _RESOURCE_METADATA_RE.search(resp.headers.get("WWW-Authenticate", ""))
    return match.group(1) if match else None


def discover() -> dict:
    """Authorization-server metadata (RFC 8414) for the MCP server, cached 24h in Redis.

    Raises TradingViewOAuthError when any hop fails or the document lacks the endpoints."""
    r = _redis()
    try:
        cached = r.get(_METADATA_KEY)
    except Exception:
        cached = None
    if cached:
        return json.loads(cached)

    prm = _get_json(_protected_resource_metadata_url(mcp_url()))
    if prm is None:
        pointer = _resource_metadata_url_from_challenge()
        prm = _get_json(pointer) if pointer else None
    servers = (prm or {}).get("authorization_servers") or []
    if not servers:
        raise TradingViewOAuthError("Could not discover TradingView's authorization server.")
    issuer = str(servers[0]).rstrip("/")
    meta = _get_json(f"{issuer}/.well-known/oauth-authorization-server")
    required = ("authorization_endpoint", "token_endpoint", "registration_endpoint")
    if meta is None or any(not meta.get(k) for k in required):
        raise TradingViewOAuthError("TradingView's authorization-server metadata is incomplete.")
    try:
        r.set(_METADATA_KEY, json.dumps(meta), ex=_METADATA_TTL_SECONDS)
    except Exception:
        log.warning("Could not cache TradingView OAuth metadata", exc_info=True)
    return meta


# --- registration + authorize ----------------------------------------------------------


def _failure_message(prefix: str, resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    detail = ""
    if isinstance(body, dict):
        detail = str(body.get("error_description") or body.get("error") or "")
    detail = scrub_secret_params(detail)[:200]
    return f"{prefix} (HTTP {resp.status_code})" + (f": {detail}" if detail else "")


def register_client(meta: dict) -> dict:
    """Dynamically register a public client (RFC 7591).

    Returns ``{"client_id": str, "client_secret": str}`` (secret "" for a public client)."""
    payload = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [settings.TRADINGVIEW_CALLBACK_URL],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPE,
    }
    try:
        resp = httpx.post(meta["registration_endpoint"], json=payload, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise TradingViewOAuthError("Could not reach TradingView's registration endpoint.") from exc
    if resp.status_code not in (200, 201):
        raise TradingViewOAuthError(
            _failure_message("TradingView rejected the client registration", resp)
        )
    body = resp.json()
    client_id = body.get("client_id") if isinstance(body, dict) else None
    if not client_id:
        raise TradingViewOAuthError("TradingView's registration response had no client_id.")
    return {"client_id": str(client_id), "client_secret": str(body.get("client_secret") or "")}


def _pkce_pair() -> tuple[str, str]:
    verifier = token_urlsafe(64)  # 86 chars — inside RFC 7636's 43..128
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _state_key(state: str) -> str:
    return f"{_STATE_KEY_PREFIX}{state}"


def _store_flow(state: str, flow: dict) -> None:
    """Stash the per-flow secrets (client + PKCE verifier) under a one-time nonce."""
    try:
        _redis().set(_state_key(state), json.dumps(flow), ex=_STATE_TTL_SECONDS)
    except Exception:  # a miss just makes the callback fail closed
        log.warning("Could not store TradingView OAuth state", exc_info=True)


def consume_oauth_state(state: str | None) -> dict | None:
    """Return the flow stored under ``state`` and delete it (one-time use), else None.

    Fails closed on a missing/unknown/empty nonce or any Redis error, so a cross-site
    callback carrying an attacker's code is rejected before token exchange
    (RFC 6749 §10.12). GETDEL is atomic: a concurrent replay wins at most once."""
    if not state:
        return None
    try:
        raw = _redis().getdel(_state_key(state))
    except Exception:
        log.warning("Could not validate TradingView OAuth state", exc_info=True)
        return None
    if not raw:
        return None
    try:
        flow = json.loads(raw)
    except ValueError:
        return None
    return flow if isinstance(flow, dict) else None


def build_authorize_url() -> str:
    """Register a client, mint state + PKCE, stash the flow, return the consent URL."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return f"{settings.TRADINGVIEW_CALLBACK_URL}?code=MOCK_OAUTH&state=mock"

    meta = discover()
    client = register_client(meta)
    verifier, challenge = _pkce_pair()
    state = token_urlsafe(32)
    _store_flow(state, {**client, "code_verifier": verifier})
    params = {
        "response_type": "code",
        "client_id": client["client_id"],
        "redirect_uri": settings.TRADINGVIEW_CALLBACK_URL,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": mcp_url(),
    }
    return f"{meta['authorization_endpoint']}?{urlencode(params)}"
```

(Import hygiene: in this task include only the imports this half uses — drop `time`, `datetime`, `InvalidToken`, `transaction`, and `timezone` from the block above so `ruff check` is clean at this commit. Task 4 adds them back with the token half.)

- [ ] **Step 4: Run tests**

Run: `docker compose exec web pytest apps/secrets/tests/test_tradingview_oauth.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
LEFTHOOK=0 git add backend/apps/secrets/tradingview_oauth.py backend/apps/secrets/tests/test_tradingview_oauth.py
LEFTHOOK=0 git commit -m "feat(secrets): TradingView OAuth discovery, dynamic registration and PKCE authorize URL"
```

---

### Task 4: OAuth module — code exchange, refresh, persistence, lock-guarded freshness, revoke

**Files:**
- Modify: `backend/apps/secrets/tradingview_oauth.py` (append)
- Test: `backend/apps/secrets/tests/test_tradingview_oauth.py` (append)

**Interfaces:**
- Consumes: `discover()`, `TradingViewTokenRejected`, `REJECTED_MESSAGE` (Task 3); `apps.core.provider_health`; `apps.secrets.credentials.decrypt_token`.
- Produces: `exchange_code(code: str, flow: dict) -> dict`, `refresh(token: dict) -> dict`, `persist_token(token: dict) -> None`, `load_token() -> dict | None`, `ensure_fresh_token(*, force: bool = False) -> str | None`, `revoke_and_disconnect() -> None`, `_SLEEP` (patch point). Token dict keys: `access_token, refresh_token, token_type, scope, expires_at (int epoch), client_id, client_secret, registered_at`.

- [ ] **Step 1: Failing tests** (append to `test_tradingview_oauth.py`; add `import time` and `from apps.secrets.models import ApiCredential` at the top)

```python
FLOW = {"client_id": "cid", "client_secret": "", "code_verifier": "verifier"}


def _token(**over) -> dict:
    base = {
        "access_token": "A",
        "refresh_token": "R",
        "token_type": "Bearer",
        "scope": "mcp:read mcp:tools",
        "expires_at": int(time.time()) + 3600,
        "client_id": "cid",
        "client_secret": "",
        "registered_at": 1,
    }
    return {**base, **over}


@override_settings(TRADINGVIEW_MCP_URL=MCP, TRADINGVIEW_CALLBACK_URL=CALLBACK)
def test_exchange_code_posts_pkce_verifier_client_id_and_resource():
    resp = httpx.Response(200, json={"access_token": "A", "refresh_token": "R", "expires_in": 1800})
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp) as p,
    ):
        token = tvo.exchange_code("CODE", FLOW)
    form = p.call_args.kwargs["data"]
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "CODE"
    assert form["code_verifier"] == "verifier"
    assert form["client_id"] == "cid"
    assert form["redirect_uri"] == CALLBACK
    assert form["resource"] == MCP
    assert "client_secret" not in form
    assert token["access_token"] == "A" and token["client_id"] == "cid"
    assert token["expires_at"] >= int(time.time()) + 1700
    assert token["registered_at"] > 0


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_refresh_keeps_previous_refresh_token_when_omitted():
    resp = httpx.Response(200, json={"access_token": "A2", "expires_in": 3600})
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp) as p,
    ):
        new = tvo.refresh(_token())
    assert p.call_args.kwargs["data"]["grant_type"] == "refresh_token"
    assert p.call_args.kwargs["data"]["refresh_token"] == "R"
    assert new["access_token"] == "A2" and new["refresh_token"] == "R"
    assert new["registered_at"] == 1


@override_settings(TRADINGVIEW_MCP_URL=MCP)
@pytest.mark.parametrize(("status", "exc"), [(400, tvo.TradingViewTokenRejected), (401, tvo.TradingViewTokenRejected), (503, tvo.TradingViewOAuthError)])
def test_token_endpoint_failures_classify(status, exc):
    resp = httpx.Response(status, json={"error": "invalid_grant"})
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp),
        pytest.raises(exc),
    ):
        tvo.refresh(_token())


@pytest.mark.django_db
def test_persist_token_upserts_and_clears_marker():
    fake = fakeredis.FakeStrictRedis()
    with patch("apps.core.provider_health._redis", lambda: fake):
        from apps.core import provider_health

        provider_health.mark_auth_error("tradingview", "was rejected")
        tvo.persist_token(_token())
        tvo.persist_token(_token(access_token="B"))
        assert provider_health.auth_error("tradingview") is None
    cred = ApiCredential.objects.get(provider="tradingview")
    assert cred.token["access_token"] == "B"
    assert cred.expires_at is not None


@pytest.mark.django_db
def test_persist_token_self_heals_undecryptable_row():
    from cryptography.fernet import InvalidToken

    with patch(
        "apps.secrets.models.ApiCredential.objects.update_or_create",
        side_effect=InvalidToken,
    ):
        tvo.persist_token(_token())
    assert ApiCredential.objects.get(provider="tradingview").token["access_token"] == "A"


@pytest.mark.django_db
def test_load_token_none_when_not_connected():
    assert tvo.load_token() is None


@pytest.mark.django_db
def test_ensure_fresh_token_returns_token_when_fresh_without_refresh(fake_redis):
    tvo.persist_token(_token())
    with patch("apps.secrets.tradingview_oauth.refresh") as r:
        assert tvo.ensure_fresh_token() == "A"
    r.assert_not_called()


@pytest.mark.django_db
def test_ensure_fresh_token_refreshes_when_stale_and_persists(fake_redis):
    tvo.persist_token(_token(expires_at=int(time.time()) + 10))
    with patch("apps.secrets.tradingview_oauth.refresh", return_value=_token(access_token="A2")) as r:
        assert tvo.ensure_fresh_token() == "A2"
    r.assert_called_once()
    assert ApiCredential.objects.get(provider="tradingview").token["access_token"] == "A2"
    assert fake_redis.get("tradingview:oauth:refresh_lock") is None  # lock released


@pytest.mark.django_db
def test_ensure_fresh_token_force_refreshes_a_fresh_token(fake_redis):
    tvo.persist_token(_token())
    with patch("apps.secrets.tradingview_oauth.refresh", return_value=_token(access_token="A3")):
        assert tvo.ensure_fresh_token(force=True) == "A3"


@pytest.mark.django_db
def test_ensure_fresh_token_rejected_refresh_marks_auth_error(fake_redis):
    tvo.persist_token(_token(expires_at=int(time.time()) + 10))
    with (
        patch("apps.core.provider_health._redis", lambda: fake_redis),
        patch("apps.secrets.tradingview_oauth.refresh", side_effect=tvo.TradingViewTokenRejected("nope")),
    ):
        assert tvo.ensure_fresh_token() is None
        from apps.core import provider_health

        assert provider_health.auth_error("tradingview") == tvo.REJECTED_MESSAGE


@pytest.mark.django_db
def test_ensure_fresh_token_transient_refresh_failure_keeps_current(fake_redis):
    tvo.persist_token(_token(expires_at=int(time.time()) + 10))
    with patch("apps.secrets.tradingview_oauth.refresh", side_effect=tvo.TradingViewOAuthError("down")):
        assert tvo.ensure_fresh_token() == "A"


@pytest.mark.django_db
def test_ensure_fresh_token_waits_for_other_process_when_locked(fake_redis):
    tvo.persist_token(_token(expires_at=int(time.time()) + 10))
    fake_redis.set("tradingview:oauth:refresh_lock", "1", ex=30)

    def _other_process_refreshes(_seconds):
        tvo.persist_token(_token(access_token="FROM-OTHER", expires_at=int(time.time()) + 3600))

    with (
        patch("apps.secrets.tradingview_oauth._SLEEP", side_effect=_other_process_refreshes),
        patch("apps.secrets.tradingview_oauth.refresh") as r,
    ):
        assert tvo.ensure_fresh_token() == "FROM-OTHER"
    r.assert_not_called()


@pytest.mark.django_db
def test_revoke_and_disconnect_deletes_row_even_if_revocation_fails(fake_redis):
    tvo.persist_token(_token())
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth.httpx.post", side_effect=httpx.ConnectError("x")) as p,
        patch("apps.market.services.tradingview_mcp.reset_state") as reset,
    ):
        tvo.revoke_and_disconnect()
    assert p.call_args.kwargs["data"] == {"token": "R", "client_id": "cid"}
    assert not ApiCredential.objects.filter(provider="tradingview").exists()
    reset.assert_called_once()


@pytest.mark.django_db
def test_exchange_code_is_canned_under_mock():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        token = tvo.exchange_code("MOCK_OAUTH", {"client_id": "mock", "code_verifier": "v"})
    assert token["access_token"] and token["refresh_token"] and token["expires_at"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/secrets/tests/test_tradingview_oauth.py -v` → the new tests FAIL (`AttributeError: exchange_code`).

- [ ] **Step 3: Implement** — append to `backend/apps/secrets/tradingview_oauth.py`:

```python
# --- tokens ---------------------------------------------------------------------------

_SLEEP = time.sleep  # patch point for the lock-wait test


def _token_request(meta: dict, flow: dict, data: dict) -> dict:
    """POST the token endpoint with the flow's client identity + RFC 8707 resource.

    Raises TradingViewTokenRejected on 400/401 (invalid grant — reconnect), else
    TradingViewOAuthError. Stamps an absolute ``expires_at`` and carries the client ids."""
    form = {**data, "client_id": flow["client_id"], "resource": mcp_url()}
    if flow.get("client_secret"):
        form["client_secret"] = flow["client_secret"]
    try:
        resp = httpx.post(meta["token_endpoint"], data=form, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise TradingViewOAuthError("Could not reach TradingView's token endpoint.") from exc
    if resp.status_code in (400, 401):
        raise TradingViewTokenRejected(_failure_message("TradingView rejected the grant", resp))
    if resp.status_code != 200:
        raise TradingViewOAuthError(_failure_message("TradingView token request failed", resp))
    body = resp.json()
    if not isinstance(body, dict) or not body.get("access_token"):
        raise TradingViewOAuthError("TradingView's token response had no access_token.")
    body["expires_at"] = int(time.time()) + int(body.get("expires_in") or 3600)
    body["client_id"] = flow["client_id"]
    body["client_secret"] = flow.get("client_secret") or ""
    return body


def exchange_code(code: str, flow: dict) -> dict:
    """Exchange the authorization code (PKCE verifier from the stored flow) for tokens."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return {
            "access_token": "mock-tv-access",
            "refresh_token": "mock-tv-refresh",
            "token_type": "Bearer",
            "scope": SCOPE,
            "expires_at": int(time.time()) + 3600,
            "client_id": str(flow.get("client_id") or "mock-client"),
            "client_secret": "",
            "registered_at": int(time.time()),
        }
    token = _token_request(
        discover(),
        flow,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.TRADINGVIEW_CALLBACK_URL,
            "code_verifier": flow["code_verifier"],
        },
    )
    token["registered_at"] = int(time.time())
    return token


def refresh(token: dict) -> dict:
    """Refresh-token grant. A response without a refresh_token keeps the previous one."""
    new = _token_request(
        discover(), token, {"grant_type": "refresh_token", "refresh_token": token["refresh_token"]}
    )
    if not new.get("refresh_token"):
        new["refresh_token"] = token.get("refresh_token", "")
    new["registered_at"] = token.get("registered_at")
    return new


def persist_token(token: dict) -> None:
    """Upsert the TradingView token; self-heals an undecryptable row; clears the marker."""
    from apps.core import provider_health
    from apps.secrets.models import ApiCredential

    expires_at = datetime.fromtimestamp(token["expires_at"], tz=timezone.get_current_timezone())
    try:
        ApiCredential.objects.update_or_create(
            provider="tradingview", defaults={"token": token, "expires_at": expires_at}
        )
    except InvalidToken:
        # The existing row is encrypted under a rotated key: update_or_create's lookup
        # SELECT can't read it. Delete (no decrypt) + create so reconnect self-heals.
        log.warning("Overwriting undecryptable TradingView credential on reconnect.")
        with transaction.atomic():
            ApiCredential.objects.filter(provider="tradingview").delete()
            ApiCredential.objects.create(
                provider="tradingview", token=token, expires_at=expires_at
            )
    provider_health.clear_auth_error("tradingview")


def load_token() -> dict | None:
    """The stored token dict, or None when not connected / undecryptable."""
    from apps.secrets.credentials import decrypt_token

    token = decrypt_token("tradingview")
    return token if token and token.get("access_token") else None


def _is_stale(token: dict) -> bool:
    return int(token.get("expires_at") or 0) - int(time.time()) < _REFRESH_SKEW_SECONDS


def _wait_for_other_refresh(stale: dict) -> str | None:
    """Another process holds the refresh lock: poll the row up to 5s for a newer token."""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        _SLEEP(0.25)
        fresh = load_token()
        if fresh is None:
            return None
        if int(fresh.get("expires_at") or 0) > int(stale.get("expires_at") or 0):
            return str(fresh["access_token"])
    return str(stale.get("access_token") or "") or None


def _refresh_under_lock(token: dict, *, force: bool) -> str | None:
    from apps.core import provider_health

    current = load_token() or token  # another process may have refreshed meanwhile
    if not force and not _is_stale(current):
        return str(current["access_token"])
    try:
        new = refresh(current)
    except TradingViewTokenRejected:
        log.warning("TradingView refused to refresh the stored token; reconnect required.")
        provider_health.mark_auth_error("tradingview", REJECTED_MESSAGE)
        return None
    except TradingViewOAuthError:
        log.warning("TradingView token refresh failed (transient); using the current token.")
        return str(current["access_token"])
    persist_token(new)
    return str(new["access_token"])


def ensure_fresh_token(*, force: bool = False) -> str | None:
    """The access token to send. Refreshes under a Redis lock when < 60s remain (or on
    ``force``, after a 401) so web + worker never double-refresh a rotating refresh
    token. None when not connected or the refresh was rejected (marker recorded)."""
    from apps.core import provider_health

    token = load_token()
    if token is None:
        return None
    if not force and not _is_stale(token):
        return str(token["access_token"])
    if not token.get("refresh_token"):
        provider_health.mark_auth_error("tradingview", REJECTED_MESSAGE)
        return None

    r = _redis()
    try:
        acquired = bool(r.set(_REFRESH_LOCK_KEY, "1", nx=True, ex=_REFRESH_LOCK_TTL_SECONDS))
    except Exception:
        acquired = True  # no lock available: refresh anyway rather than stall every call
    if not acquired:
        return _wait_for_other_refresh(token)
    try:
        return _refresh_under_lock(token, force=force)
    finally:
        try:
            r.delete(_REFRESH_LOCK_KEY)
        except Exception:
            log.debug("Could not release the TradingView refresh lock", exc_info=True)


def revoke_and_disconnect() -> None:
    """Best-effort upstream revocation, then delete the row, clear the marker, and drop
    the process-local MCP session + cached tool list."""
    from apps.core import provider_health
    from apps.core.mocks import is_mock_mode
    from apps.secrets.models import ApiCredential

    token = load_token()
    if token and token.get("refresh_token") and not is_mock_mode():
        try:
            endpoint = discover().get("revocation_endpoint")
            if endpoint:
                httpx.post(
                    endpoint,
                    data={"token": token["refresh_token"], "client_id": token.get("client_id", "")},
                    timeout=_TIMEOUT,
                )
        except Exception:
            log.info("TradingView token revocation skipped (best-effort)", exc_info=True)
    ApiCredential.objects.filter(provider="tradingview").delete()
    provider_health.clear_auth_error("tradingview")
    from apps.market.services import tradingview_mcp  # lazy: market imports secrets

    tradingview_mcp.reset_state()
```

Note: `revoke_and_disconnect` imports `apps.market.services.tradingview_mcp`, which is created in Task 5. Until Task 5 lands, the last test in this task fails on import — either execute Tasks 4 and 5 back-to-back before running that one test, or temporarily mark `test_revoke_and_disconnect_deletes_row_even_if_revocation_fails` with `@pytest.mark.xfail(strict=True, reason="tradingview_mcp lands in Task 5")` and remove the marker in Task 5.

- [ ] **Step 4: Run tests + lint**

Run: `docker compose exec web pytest apps/secrets/tests/test_tradingview_oauth.py -v` → PASS (or the single xfail noted above).
Run: `docker compose exec web ruff check apps/secrets` and `docker compose exec web ruff format apps/secrets` → clean.

- [ ] **Step 5: Commit**

```bash
LEFTHOOK=0 git add backend/apps/secrets
LEFTHOOK=0 git commit -m "feat(secrets): TradingView token exchange, lock-guarded refresh, persistence and revoke"
```

---

### Task 5: MCP transport — session, JSON/SSE parsing, 401/404 retry, `list_tools`, `call_tool`, `probe`, mock catalogue

**Files:**
- Create: `backend/apps/market/services/tradingview_mcp.py`
- Test: `backend/apps/market/tests/test_tradingview_mcp.py`

**Interfaces:**
- Consumes: `apps.secrets.tradingview_oauth.ensure_fresh_token`, `REJECTED_MESSAGE`; `apps.market.cache.get_or_fetch`; `apps.core.provider_health`.
- Produces: `TradingViewMCPError`, `TradingViewNotConnected`, `TradingViewRateLimited`, `TradingViewToolError`, `list_tools(*, use_cache=True) -> list[dict]`, `call_tool(name, arguments=None) -> Any`, `probe() -> dict`, `reset_state() -> None`, `MOCK_TOOLS`, `mock_call(name, arguments) -> Any`, `TOOLS_CACHE_KEY`.

- [ ] **Step 1: Failing tests** — create `backend/apps/market/tests/test_tradingview_mcp.py`:

```python
"""TradingView MCP transport: JSON + SSE responses, session id, 401/404 retry, tool results."""

from __future__ import annotations

import json
from unittest.mock import patch

import fakeredis
import httpx
import pytest

from apps.market.services import tradingview_mcp as mcp

_PASSTHRU = {"side_effect": lambda key, *, ttl_seconds, fetcher: fetcher()}


@pytest.fixture(autouse=True)
def _fresh_state():
    fake = fakeredis.FakeStrictRedis()
    with (
        patch("apps.market.services.tradingview_mcp._redis", lambda: fake),
        patch("apps.market.services.tradingview_mcp.cache.get_or_fetch", **_PASSTHRU),
        patch("apps.market.services.tradingview_mcp.oauth.ensure_fresh_token", return_value="tok"),
    ):
        mcp.reset_state()
        yield
        mcp.reset_state()


def _rpc(rpc_id, result=None, error=None, **headers):
    body = {"jsonrpc": "2.0", "id": rpc_id}
    body["error" if error else "result"] = error or (result if result is not None else {})
    return httpx.Response(200, json=body, headers=headers)


class _Server:
    """Scripted httpx.post: answers initialize/initialized/tools calls in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.headers: list[dict] = []

    def __call__(self, url, *, json, headers, timeout):
        self.requests.append(json)
        self.headers.append(dict(headers))
        resp = self.responses.pop(0)
        return resp(json) if callable(resp) else resp


def _answer(result):
    return lambda req: _rpc(req["id"], result)


def test_call_tool_parses_json_response_and_sends_headers():
    server = _Server([
        lambda req: _rpc(req["id"], {"protocolVersion": "2025-06-18"}, **{"Mcp-Session-Id": "s-1"}),
        httpx.Response(202),
        _answer({"content": [{"type": "text", "text": json.dumps({"bars": [1, 2]})}]}),
    ])
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        out = mcp.call_tool("get_ohlcv", {"symbol": "NASDAQ:AAPL"})
    assert out == {"bars": [1, 2]}
    assert [r["method"] for r in server.requests] == ["initialize", "notifications/initialized", "tools/call"]
    last = server.headers[-1]
    assert last["Authorization"] == "Bearer tok"
    assert last["Accept"] == "application/json, text/event-stream"
    assert last["MCP-Protocol-Version"] == "2025-06-18"
    assert last["Mcp-Session-Id"] == "s-1"
    assert server.requests[-1]["params"] == {"name": "get_ohlcv", "arguments": {"symbol": "NASDAQ:AAPL"}}


def test_sse_response_picks_the_message_answering_our_id():
    def sse(req):
        body = (
            'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n\n'
            f'data: {json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"structuredContent": {"ok": 1}}})}\n\n'
        )
        return httpx.Response(200, content=body.encode(), headers={"Content-Type": "text/event-stream"})

    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), sse])
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.call_tool("x") == {"ok": 1}


def test_stateless_server_initializes_once_per_process():
    server = _Server([
        lambda req: _rpc(req["id"], {}),
        httpx.Response(202),
        _answer({"content": [{"type": "text", "text": "a"}]}),
        _answer({"content": [{"type": "text", "text": "b"}]}),
    ])
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.call_tool("x") == "a"
        assert mcp.call_tool("x") == "b"
    assert [r["method"] for r in server.requests].count("initialize") == 1


def test_404_reinitializes_once_and_retries():
    server = _Server([
        lambda req: _rpc(req["id"], {}, **{"Mcp-Session-Id": "old"}),
        httpx.Response(202),
        httpx.Response(404),
        lambda req: _rpc(req["id"], {}, **{"Mcp-Session-Id": "new"}),
        httpx.Response(202),
        _answer({"content": [{"type": "text", "text": "ok"}]}),
    ])
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.call_tool("x") == "ok"
    assert server.headers[-1]["Mcp-Session-Id"] == "new"


def test_401_forces_one_refresh_and_retry():
    server = _Server([
        lambda req: _rpc(req["id"], {}),
        httpx.Response(202),
        httpx.Response(401),
        _answer({"content": [{"type": "text", "text": "ok"}]}),
    ])
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        patch("apps.market.services.tradingview_mcp.oauth.ensure_fresh_token", side_effect=["tok", "tok2"]) as e,
    ):
        assert mcp.call_tool("x") == "ok"
    assert e.call_args_list[-1].kwargs == {"force": True}
    assert server.headers[-1]["Authorization"] == "Bearer tok2"


def test_second_401_marks_auth_error_and_raises_not_connected():
    fake = fakeredis.FakeStrictRedis()
    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), httpx.Response(401), httpx.Response(401)])
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        patch("apps.core.provider_health._redis", lambda: fake),
        pytest.raises(mcp.TradingViewNotConnected),
    ):
        mcp.call_tool("x")
    from apps.core import provider_health

    assert provider_health.auth_error("tradingview") is not None


def test_not_connected_raises_without_http():
    with (
        patch("apps.market.services.tradingview_mcp.oauth.ensure_fresh_token", return_value=None),
        patch("apps.market.services.tradingview_mcp.httpx.post") as p,
        pytest.raises(mcp.TradingViewNotConnected),
    ):
        mcp.call_tool("x")
    p.assert_not_called()


def test_429_raises_rate_limited_without_retry():
    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), httpx.Response(429)])
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        pytest.raises(mcp.TradingViewRateLimited),
    ):
        mcp.call_tool("x")
    assert len(server.requests) == 3


def test_jsonrpc_error_object_raises():
    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), lambda req: _rpc(req["id"], error={"code": -32602, "message": "bad"})])
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        pytest.raises(mcp.TradingViewMCPError, match="-32602"),
    ):
        mcp.call_tool("x")


def test_is_error_result_raises_tool_error():
    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), _answer({"isError": True, "content": [{"type": "text", "text": "symbol not found"}]})])
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        pytest.raises(mcp.TradingViewToolError, match="symbol not found"),
    ):
        mcp.call_tool("x")


def test_multiple_text_blocks_decode_to_a_list():
    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), _answer({"content": [{"type": "text", "text": "{\"a\": 1}"}, {"type": "text", "text": "plain"}]})])
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.call_tool("x") == [{"a": 1}, "plain"]


def test_list_tools_follows_pagination():
    server = _Server([
        lambda req: _rpc(req["id"], {}),
        httpx.Response(202),
        _answer({"tools": [{"name": "a"}], "nextCursor": "c2"}),
        _answer({"tools": [{"name": "b"}]}),
    ])
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert [t["name"] for t in mcp.list_tools()] == ["a", "b"]
    assert server.requests[-1]["params"] == {"cursor": "c2"}


def test_probe_reports_tool_count_and_never_raises():
    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), _answer({"tools": [{"name": "a"}, {"name": "b"}]})])
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.probe() == {"ok": True, "message": "Connected — 2 tools available."}
    with patch("apps.market.services.tradingview_mcp.oauth.ensure_fresh_token", return_value=None):
        assert mcp.probe()["ok"] is False


def test_mock_mode_serves_canned_catalogue_and_results():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        names = {t["name"] for t in mcp.list_tools()}
        bars = mcp.call_tool("get_ohlcv", {"symbol": "NASDAQ:AAPL", "count": 5})
    assert {"search_symbols", "get_ohlcv", "get_news", "create_alert"} <= names
    assert len(bars["bars"]) == 5 and {"t", "o", "h", "l", "c", "v"} <= set(bars["bars"][0])
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/market/tests/test_tradingview_mcp.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — create `backend/apps/market/services/tradingview_mcp.py`:

```python
"""MCP client for TradingView's official server (Streamable HTTP, JSON-RPC 2.0).

Dependency-free — we need only ``initialize`` / ``notifications/initialized`` /
``tools/list`` / ``tools/call``, mirroring the hand-rolled MCP-out server in
``apps.core.mcp``. The bearer token comes from ``tradingview_oauth.ensure_fresh_token``
(lazy refresh under a Redis lock).

Responses arrive as ``application/json`` or as an SSE stream (``text/event-stream``);
both are reduced to the JSON-RPC message answering our id. A ``Mcp-Session-Id`` from
``initialize`` is echoed on later calls; a 404 means the session expired → re-initialize
once. A 401 forces one token refresh and one retry; a second 401 records the
provider_health marker (the fallback router then stops consulting TradingView).
Never logs the token.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from itertools import count
from typing import Any

import httpx
import redis
from django.conf import settings

from apps.market import cache
from apps.market.services.safe_log import safe_err
from apps.secrets import tradingview_oauth as oauth

log = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "ledger", "version": "1.0.0"}
TOOLS_CACHE_KEY = "tradingview:mcp:tools"
TOOLS_CACHE_TTL_SECONDS = 3600
_TIMEOUT = 20.0
_MAX_PAGES = 20

_state: dict[str, Any] = {"initialized": False, "session_id": None, "last_id": 0}
_session_lock = threading.Lock()
_ids = count(1)


class TradingViewMCPError(RuntimeError):
    """Transport / protocol failure (HTTP error, malformed body, JSON-RPC error)."""


class TradingViewNotConnected(TradingViewMCPError):
    """No usable token: not connected, or the refresh/access token was rejected."""


class TradingViewRateLimited(TradingViewMCPError):
    """HTTP 429 — the ~100 calls/min per-user budget is spent. Not retried."""


class TradingViewToolError(TradingViewMCPError):
    """``tools/call`` answered ``isError`` — the tool ran but reported failure."""


class _Unauthorized(Exception):
    pass


class _SessionExpired(Exception):
    pass


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def _last_id() -> int:
    return int(_state["last_id"])


def _next_id() -> int:
    rpc_id = next(_ids)
    _state["last_id"] = rpc_id
    return rpc_id


def _forget_session() -> None:
    _state["initialized"] = False
    _state["session_id"] = None


def reset_state() -> None:
    """Forget the process-local session and the cached tool list (disconnect / tests)."""
    _forget_session()
    try:
        _redis().delete(TOOLS_CACHE_KEY)
    except Exception:
        log.debug("Could not clear the TradingView tools cache", exc_info=True)


# --- wire -------------------------------------------------------------------------------


def _headers(token: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }
    if _state["session_id"]:
        headers["Mcp-Session-Id"] = str(_state["session_id"])
    return headers


def _post(message: dict, token: str) -> httpx.Response:
    try:
        return httpx.post(
            settings.TRADINGVIEW_MCP_URL, json=message, headers=_headers(token), timeout=_TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise TradingViewMCPError(f"TradingView MCP unreachable: {safe_err(exc)}") from exc


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code == 401:
        raise _Unauthorized
    if resp.status_code == 404:
        raise _SessionExpired
    if resp.status_code == 429:
        raise TradingViewRateLimited("TradingView MCP rate limit reached (HTTP 429)")
    if resp.status_code >= 400:
        raise TradingViewMCPError(f"TradingView MCP returned HTTP {resp.status_code}")


def _parse_sse(text: str, rpc_id: int) -> dict | None:
    """The JSON-RPC message with ``id == rpc_id`` from an SSE body. Each event's
    ``data:`` lines are joined; server-initiated requests/notifications are ignored."""
    data_lines: list[str] = []
    for raw in [*text.splitlines(), ""]:
        line = raw.rstrip("\r")
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
        if line == "" and data_lines:
            try:
                msg = json.loads("\n".join(data_lines))
            except ValueError:
                msg = None
            data_lines = []
            if isinstance(msg, dict) and msg.get("id") == rpc_id:
                return msg
    return None


def _parse_response(resp: httpx.Response, rpc_id: int) -> dict:
    ctype = resp.headers.get("content-type", "")
    if ctype.startswith("text/event-stream"):
        msg = _parse_sse(resp.text, rpc_id)
    else:
        try:
            body = resp.json()
        except ValueError as exc:
            raise TradingViewMCPError("TradingView MCP returned a non-JSON body") from exc
        msg = body if isinstance(body, dict) else None
    if msg is None:
        raise TradingViewMCPError("TradingView MCP response did not answer the request")
    if msg.get("error"):
        err = msg["error"] if isinstance(msg["error"], dict) else {}
        raise TradingViewMCPError(f"JSON-RPC error {err.get('code')}: {err.get('message')}")
    return msg


def _initialize(token: str) -> None:
    rpc_id = _next_id()
    resp = _post(
        {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        },
        token,
    )
    _raise_for_status(resp)
    _parse_response(resp, rpc_id)
    _state["session_id"] = resp.headers.get("Mcp-Session-Id") or None
    ack = _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, token)
    _raise_for_status(ack)
    _state["initialized"] = True


def _mark_rejected() -> None:
    from apps.core import provider_health

    provider_health.mark_auth_error("tradingview", oauth.REJECTED_MESSAGE)


def _send(method: str, params: dict, token: str) -> dict:
    with _session_lock:
        if not _state["initialized"]:
            _initialize(token)
    rpc_id = _next_id()
    resp = _post({"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}, token)
    _raise_for_status(resp)
    result = _parse_response(resp, rpc_id).get("result")
    return result if isinstance(result, dict) else {}


def _request(method: str, params: dict | None = None) -> dict:
    """One JSON-RPC request with session bootstrap, 404 re-init and 401 refresh-retry."""
    token = oauth.ensure_fresh_token()
    if token is None:
        raise TradingViewNotConnected("TradingView is not connected")
    refreshed = reinitialized = False
    while True:
        try:
            return _send(method, params or {}, token)
        except _Unauthorized:
            if refreshed:
                _mark_rejected()
                raise TradingViewNotConnected("TradingView rejected the access token") from None
            refreshed = True
            # Keep the session: a 401 is about the token, not the session id. If the
            # server also dropped the session it answers 404 next, which re-inits.
            token = oauth.ensure_fresh_token(force=True)
            if token is None:
                raise TradingViewNotConnected("TradingView token refresh failed") from None
        except _SessionExpired:
            if reinitialized:
                raise TradingViewMCPError("TradingView MCP session could not be re-established") from None
            reinitialized = True
            _forget_session()


# --- results ----------------------------------------------------------------------------


def _text_of(result: dict) -> str:
    blocks = result.get("content") or []
    return "\n".join(str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text")


def _decode_tool_result(result: dict) -> Any:
    if result.get("isError"):
        raise TradingViewToolError(_text_of(result)[:500] or "tool reported an error")
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    decoded: list[Any] = []
    for block in result.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = str(block.get("text", ""))
        try:
            decoded.append(json.loads(text))
        except ValueError:
            decoded.append(text)
    if not decoded:
        return None
    return decoded[0] if len(decoded) == 1 else decoded


# --- public API --------------------------------------------------------------------------


def _fetch_all_tools() -> list[dict]:
    tools: list[dict] = []
    cursor: str | None = None
    for _ in range(_MAX_PAGES):
        result = _request("tools/list", {"cursor": cursor} if cursor else {})
        tools.extend(t for t in result.get("tools") or [] if isinstance(t, dict))
        cursor = result.get("nextCursor") or None
        if not cursor:
            break
    return tools


def list_tools(*, use_cache: bool = True) -> list[dict]:
    """The server's tool schemas (``name``/``description``/``inputSchema``), Redis-cached 1h."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return [dict(t) for t in MOCK_TOOLS]
    if not use_cache:
        return _fetch_all_tools()
    return cache.get_or_fetch(
        TOOLS_CACHE_KEY, ttl_seconds=TOOLS_CACHE_TTL_SECONDS, fetcher=_fetch_all_tools
    )


def call_tool(name: str, arguments: dict | None = None) -> Any:
    """Run one tool. Returns ``structuredContent`` when present, else the JSON-decoded
    text block(s). Raises TradingViewToolError on ``isError``."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return mock_call(name, arguments or {})
    return _decode_tool_result(_request("tools/call", {"name": name, "arguments": arguments or {}}))


def probe() -> dict:
    """Settings → "Test connection": ``{ok, message}``; never raises."""
    try:
        tools = list_tools(use_cache=False)
    except TradingViewNotConnected:
        return {"ok": False, "message": "Not connected — connect TradingView first."}
    except TradingViewMCPError as exc:
        return {"ok": False, "message": f"Couldn't reach TradingView MCP ({exc})."}
    except Exception as exc:
        log.warning("tradingview.probe.failed: %s", safe_err(exc))
        return {"ok": False, "message": "Couldn't reach TradingView MCP."}
    return {"ok": True, "message": f"Connected — {len(tools)} tools available."}


# --- MOCK_EXTERNAL catalogue -------------------------------------------------------------

_MOCK_NOW = 1_760_000_000  # fixed epoch so fixtures are stable
_DAY = 86_400


def _schema(props: dict, required: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


MOCK_TOOLS: list[dict] = [
    {"name": "search_symbols", "description": "Search symbols.", "inputSchema": _schema({"query": {"type": "string"}, "type_filter": {"type": "string"}}, ["query"])},
    {"name": "get_ohlcv", "description": "OHLCV bars.", "inputSchema": _schema({"symbol": {"type": "string"}, "interval": {"type": "string"}, "count": {"type": "integer"}, "summary": {"type": "boolean"}}, ["symbol"])},
    {"name": "get_symbol_data_batch", "description": "Screener columns for symbols.", "inputSchema": _schema({"symbols": {"type": "array", "items": {"type": "string"}}, "columns": {"type": "array", "items": {"type": "string"}}}, ["symbols"])},
    {"name": "get_news", "description": "Headlines for a symbol.", "inputSchema": _schema({"symbol": {"type": "string"}, "limit": {"type": "integer"}}, ["symbol"])},
    {"name": "get_earnings_calendar", "description": "Earnings dates.", "inputSchema": _schema({"symbols": {"type": "array", "items": {"type": "string"}}}, ["symbols"])},
    {"name": "get_economic_calendar", "description": "Macro events.", "inputSchema": _schema({"countries": {"type": "array", "items": {"type": "string"}}, "from_date": {"type": "string"}, "to_date": {"type": "string"}})},
    {"name": "create_alert", "description": "Create a price alert (write).", "inputSchema": _schema({"symbol": {"type": "string"}, "price": {"type": "number"}}, ["symbol", "price"])},
]


def _mock_search(a: dict) -> Any:
    q = str(a.get("query") or "AAPL").upper()
    return {"symbols": [{"symbol": f"NASDAQ:{q}", "ticker": q, "exchange": "NASDAQ", "type": "stock"}]}


def _mock_ohlcv(a: dict) -> Any:
    n = max(1, min(int(a.get("count") or 30), 30))
    bars = [
        {"t": _MOCK_NOW - (n - i) * _DAY, "o": 150.0, "h": 152.0, "l": 148.0, "c": 150.0 + (i % 3), "v": 1_000_000 + i}
        for i in range(n)
    ]
    return {"symbol": a.get("symbol"), "bars": bars}


def _mock_batch(a: dict) -> Any:
    rows = [{"symbol": s, "close": 150.0, "change": 1.23, "volume": 1_000_000, "high": 152.0, "low": 148.0} for s in a.get("symbols") or []]
    return {"data": rows}


def _mock_news(a: dict) -> Any:
    sym = str(a.get("symbol") or "NASDAQ:AAPL")
    item = {"id": f"tv-{sym}-1", "title": f"Mock TradingView headline for {sym}", "published": _MOCK_NOW, "provider": "MockWire", "storyPath": "/news/mock-1/", "link": "", "relatedSymbols": [{"symbol": sym}]}
    return {"items": [item], "has_more": False}


def _mock_earnings(a: dict) -> Any:
    return {"events": [{"symbol": s, "date": "2026-10-28", "time": "amc", "eps_estimate": 1.5, "revenue_estimate": 9.0e10} for s in a.get("symbols") or []]}


def _mock_macro(_a: dict) -> Any:
    return {"events": [{"title": "Consumer Price Index (MoM)", "country": "US", "importance": "high", "date": "2026-10-14T12:30:00Z", "forecast": 0.3, "previous": 0.2, "actual": None}]}


_MOCK_RESULTS: dict[str, Callable[[dict], Any]] = {
    "search_symbols": _mock_search,
    "get_ohlcv": _mock_ohlcv,
    "get_symbol_data_batch": _mock_batch,
    "get_news": _mock_news,
    "get_earnings_calendar": _mock_earnings,
    "get_economic_calendar": _mock_macro,
}


def mock_call(name: str, arguments: dict) -> Any:
    """Deterministic canned results for MOCK_EXTERNAL (shapes per the TradingView docs;
    the normalizers in ``tradingview.py`` are lenient about key spellings)."""
    handler = _MOCK_RESULTS.get(name)
    return handler(arguments) if handler else {"ok": True}
```

- [ ] **Step 4: Run tests + lint**

Run: `docker compose exec web pytest apps/market/tests/test_tradingview_mcp.py apps/secrets/tests/test_tradingview_oauth.py -v` → PASS (remove the Task 4 xfail marker if you added it).
Run: `docker compose exec web ruff check apps/market/services/tradingview_mcp.py && docker compose exec web ruff format apps/market/services/tradingview_mcp.py`.

- [ ] **Step 5: Commit**

```bash
LEFTHOOK=0 git add backend/apps/market/services/tradingview_mcp.py backend/apps/market/tests/test_tradingview_mcp.py backend/apps/secrets/tests/test_tradingview_oauth.py
LEFTHOOK=0 git commit -m "feat(market): dependency-free MCP client for TradingView (Streamable HTTP, session, retry, mock catalogue)"
```

---

### Task 6: Connection endpoints — authorize, callback, test, disconnect

**Files:**
- Modify: `backend/apps/secrets/views.py` (new views; extend `data_source_detail` DELETE and `data_source_test`)
- Modify: `backend/apps/secrets/urls.py`
- Test: `backend/apps/secrets/tests/test_tradingview_views.py`

**Interfaces:**
- Consumes: `tradingview_oauth.build_authorize_url / consume_oauth_state / exchange_code / persist_token / revoke_and_disconnect / TradingViewOAuthError` (Tasks 3–4); `tradingview_mcp.probe` (Task 5).
- Produces: `GET /api/schwab/data-sources/tradingview/authorize/` → `{url}` | 502 `tradingview_registration_failed`; `GET /api/schwab/data-sources/tradingview/callback/` → 302 | 400 `missing_code` / `invalid_state` | 502 `oauth_exchange_failed`; `POST /api/schwab/data-sources/tradingview/test/` → `{ok, message}`; `DELETE /api/schwab/data-sources/tradingview/` → status dict.

- [ ] **Step 1: Failing tests** — create `backend/apps/secrets/tests/test_tradingview_views.py`:

```python
"""TradingView connection endpoints under /api/schwab/data-sources/tradingview/."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.secrets.models import ApiCredential
from apps.secrets.tradingview_oauth import TradingViewOAuthError

BASE = "/api/schwab/data-sources/tradingview"
FLOW = {"client_id": "cid", "client_secret": "", "code_verifier": "v"}
TOKEN = {"access_token": "A", "refresh_token": "R", "expires_at": 9999999999, "client_id": "cid"}


@pytest.mark.django_db
def test_authorize_returns_url(api):
    with patch("apps.secrets.views.tv_build_authorize_url", return_value="https://tv/authorize?x=1"):
        r = api.get(f"{BASE}/authorize/")
    assert r.status_code == 200
    assert r.json() == {"url": "https://tv/authorize?x=1"}


@pytest.mark.django_db
def test_authorize_registration_failure_is_502_with_safe_message(api):
    with patch(
        "apps.secrets.views.tv_build_authorize_url",
        side_effect=TradingViewOAuthError("TradingView rejected the client registration (HTTP 400): loopback not allowed"),
    ):
        r = api.get(f"{BASE}/authorize/")
    assert r.status_code == 502
    assert r.json()["code"] == "tradingview_registration_failed"
    assert "loopback not allowed" in r.json()["message"]


@pytest.mark.django_db
@override_settings(FRONTEND_BASE_URL="http://localhost:5173")
def test_callback_denied_redirects_with_denied_flag(api):
    r = api.get(f"{BASE}/callback/?error=access_denied&state=s")
    assert r.status_code == 302
    assert r["Location"] == "http://localhost:5173/settings?tradingview=denied"


@pytest.mark.django_db
def test_callback_missing_code_400(api):
    r = api.get(f"{BASE}/callback/?state=s")
    assert r.status_code == 400
    assert r.json()["code"] == "missing_code"


@pytest.mark.django_db
def test_callback_invalid_state_400_and_no_exchange(api):
    with (
        patch("apps.secrets.views.tv_consume_oauth_state", return_value=None),
        patch("apps.secrets.views.tv_exchange_code") as ex,
    ):
        r = api.get(f"{BASE}/callback/?code=C&state=bad")
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_state"
    ex.assert_not_called()


@pytest.mark.django_db
def test_callback_exchange_failure_502(api):
    with (
        patch("apps.secrets.views.tv_consume_oauth_state", return_value=FLOW),
        patch("apps.secrets.views.tv_exchange_code", side_effect=TradingViewOAuthError("down")),
    ):
        r = api.get(f"{BASE}/callback/?code=C&state=ok")
    assert r.status_code == 502
    assert r.json()["code"] == "oauth_exchange_failed"


@pytest.mark.django_db
@override_settings(FRONTEND_BASE_URL="http://localhost:5173")
def test_callback_success_persists_and_redirects(api):
    with (
        patch("apps.secrets.views.tv_consume_oauth_state", return_value=FLOW),
        patch("apps.secrets.views.tv_exchange_code", return_value=dict(TOKEN)) as ex,
    ):
        r = api.get(f"{BASE}/callback/?code=C&state=ok")
    ex.assert_called_once_with("C", FLOW)
    assert r.status_code == 302
    assert r["Location"] == "http://localhost:5173/settings?tradingview=connected"
    assert ApiCredential.objects.get(provider="tradingview").token["access_token"] == "A"


@pytest.mark.django_db
def test_callback_under_mock_skips_state_check(api):
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        r = api.get(f"{BASE}/callback/?code=MOCK_OAUTH&state=mock")
    assert r.status_code == 302
    assert ApiCredential.objects.filter(provider="tradingview").exists()


@pytest.mark.django_db
def test_test_endpoint_delegates_to_probe(api):
    with patch("apps.secrets.views.tv_probe", return_value={"ok": True, "message": "Connected — 3 tools available."}):
        r = api.post(f"{BASE}/test/")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.django_db
def test_schwab_test_endpoint_still_not_key_managed(api):
    r = api.post("/api/schwab/data-sources/schwab/test/")
    assert r.status_code == 400
    assert r.json()["code"] == "not_key_managed"


@pytest.mark.django_db
def test_delete_disconnects(api):
    ApiCredential.objects.create(provider="tradingview", token=dict(TOKEN))
    with patch("apps.secrets.views.tv_revoke_and_disconnect", side_effect=lambda: ApiCredential.objects.filter(provider="tradingview").delete()) as rev:
        r = api.delete(f"{BASE}/")
    rev.assert_called_once()
    assert r.status_code == 200
    assert r.json()["configured"] is False


@pytest.mark.django_db
def test_schwab_delete_still_rejected(api):
    r = api.delete("/api/schwab/data-sources/schwab/")
    assert r.status_code == 400
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/secrets/tests/test_tradingview_views.py -v` → FAIL (404s / AttributeError on the patch targets).

- [ ] **Step 3: Implement views** — in `backend/apps/secrets/views.py` add these imports next to the Schwab OAuth ones (aliased so tests patch `apps.secrets.views.tv_*`):

```python
from apps.market.services.tradingview_mcp import probe as tv_probe
from apps.secrets.tradingview_oauth import TradingViewOAuthError
from apps.secrets.tradingview_oauth import build_authorize_url as tv_build_authorize_url
from apps.secrets.tradingview_oauth import consume_oauth_state as tv_consume_oauth_state
from apps.secrets.tradingview_oauth import exchange_code as tv_exchange_code
from apps.secrets.tradingview_oauth import persist_token as tv_persist_token
from apps.secrets.tradingview_oauth import revoke_and_disconnect as tv_revoke_and_disconnect
```

Add the two new views after `data_source_test`:

```python
@require_GET
def tradingview_authorize(_request: HttpRequest) -> JsonResponse:
    """Register a client with TradingView's authorization server and return the consent
    URL (PKCE + one-time state minted server-side). A rejected registration — e.g. an
    unacceptable redirect URI — surfaces as a 502 with the server's reason."""
    try:
        return JsonResponse({"url": tv_build_authorize_url()})
    except TradingViewOAuthError as exc:
        log.warning("TradingView OAuth authorize failed: %s", exc)
        return _ds_err("tradingview_registration_failed", str(exc), 502)


@require_GET
def tradingview_callback(request: HttpRequest) -> JsonResponse | HttpResponseRedirect:
    """TradingView redirects here with ?code&state after consent (or ?error on denial)."""
    from apps.core.mocks import is_mock_mode

    settings_page = f"{settings.FRONTEND_BASE_URL}/settings"
    if request.GET.get("error"):
        return HttpResponseRedirect(f"{settings_page}?tradingview=denied")
    code = request.GET.get("code")
    if not code:
        return _ds_err("missing_code", "TradingView callback did not include a code parameter.", 400)
    # CSRF / auth-code-injection guard (RFC 6749 §10.12): the callback is a cross-site GET
    # with no auth cookies. The one-time state nonce also carries the PKCE verifier, so a
    # missing/replayed nonce cannot complete an exchange. Mock mode carries no real state.
    if is_mock_mode():
        flow: dict | None = {"client_id": "mock-client", "client_secret": "", "code_verifier": "mock"}
    else:
        flow = tv_consume_oauth_state(request.GET.get("state"))
    if flow is None:
        return _ds_err("invalid_state", "Missing or invalid OAuth state.", 400)
    try:
        token = tv_exchange_code(code, flow)
    except Exception:
        log.warning("TradingView OAuth code exchange failed", exc_info=True)
        return _ds_err("oauth_exchange_failed", "Failed to complete TradingView OAuth. Please try again.", 502)
    tv_persist_token(token)
    return HttpResponseRedirect(f"{settings_page}?tradingview=connected")
```

Change `data_source_detail` so DELETE works for TradingView (PUT stays rejected):

```python
    if request.method == "DELETE" and provider == "tradingview":
        tv_revoke_and_disconnect()
        return JsonResponse({"configured": False, "fields_present": [], "env_fields": []})
    if ds["auth"] in ("none", "oauth"):
        return _ds_err("not_key_managed", f"{ds['label']} isn't configured with a key here.", 400)
```

(the new `if` goes *before* the existing `not_key_managed` guard). Change `data_source_test`:

```python
    if provider == "tradingview":
        return JsonResponse(tv_probe())
    if ds["auth"] in ("none", "oauth"):
        return _ds_err("not_key_managed", f"{ds['label']} has no key to test.", 400)
```

- [ ] **Step 4: URLs** — in `backend/apps/secrets/urls.py` insert before the `data-sources/<str:provider>/test/` line:

```python
    path("data-sources/tradingview/authorize/", views.tradingview_authorize, name="tradingview-authorize"),
    path("data-sources/tradingview/callback/", views.tradingview_callback, name="tradingview-callback"),
```

- [ ] **Step 5: Run tests + lint**

Run: `docker compose exec web pytest apps/secrets -v` → PASS. Run `ruff check` + `ruff format` on `apps/secrets`.

- [ ] **Step 6: Commit**

```bash
LEFTHOOK=0 git add backend/apps/secrets
LEFTHOOK=0 git commit -m "feat(secrets): TradingView connect/callback/test/disconnect endpoints"
```

---

### Task 7: Provider normalizers — `is_connected`, symbol mapping, bars, quotes, news

**Files:**
- Create: `backend/apps/market/services/tradingview.py`
- Test: `backend/apps/market/tests/test_tradingview_provider.py`

**Interfaces:**
- Consumes: `tradingview_mcp.call_tool` (Task 5); `tradingview_oauth.load_token` (Task 4); `apps.market.cache`; `apps.market.services._bars.persist_bars`; `apps.market.services.news._upsert_items`; `apps.market.symbols.normalize_symbol`.
- Produces: `PROVIDER = "tradingview"`, `is_connected() -> bool`, `to_tv_symbol(ticker) -> str | None`, `fetch_bars(ticker, *, timeframe="1d", limit=60) -> list[dict]` (BARS CONTRACT), `fetch_quotes(tickers) -> dict[str, dict]` (QUOTES CONTRACT), `fetch_news(tickers, *, limit=15) -> list[dict]`, plus helpers `_rows`, `_first`, `_float`, `_int` reused by Task 8.

- [ ] **Step 1: Failing tests** — create `backend/apps/market/tests/test_tradingview_provider.py`:

```python
"""TradingView as a market-data provider: symbol mapping + contract normalizers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.models import NewsItem, OHLCBar
from apps.market.services import tradingview as tv

_PASSTHRU = {"side_effect": lambda key, *, ttl_seconds, fetcher: fetcher()}


@pytest.fixture(autouse=True)
def _no_cache():
    with patch("apps.market.services.tradingview.cache.get_or_fetch", **_PASSTHRU):
        yield


def _tools(table: dict):
    def _call(name, arguments=None):
        handler = table[name]
        return handler(arguments or {}) if callable(handler) else handler

    return patch("apps.market.services.tradingview.mcp.call_tool", side_effect=_call)


@pytest.mark.django_db
def test_is_connected_requires_token_and_no_marker():
    with patch("apps.market.services.tradingview.load_token", return_value=None):
        assert tv.is_connected() is False
    with (
        patch("apps.market.services.tradingview.load_token", return_value={"access_token": "a"}),
        patch("apps.core.provider_health.auth_error", return_value=None),
    ):
        assert tv.is_connected() is True
    with (
        patch("apps.market.services.tradingview.load_token", return_value={"access_token": "a"}),
        patch("apps.core.provider_health.auth_error", return_value="rejected"),
    ):
        assert tv.is_connected() is False


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [("$VIX", "TVC:VIX"), ("VIX", "TVC:VIX"), ("SPX", "SP:SPX"), ("/ES", "CME_MINI:ES1!"), ("ES", "CME_MINI:ES1!"), ("/VX", "CFE:VX1!"), ("$ADVN", None), ("", None)],
)
def test_symbol_table(ticker, expected):
    with patch("apps.market.services.tradingview.mcp.call_tool") as c:
        assert tv.to_tv_symbol(ticker) == expected
    c.assert_not_called()


def test_equity_resolves_via_search_preferring_us_exchange():
    hits = {"symbols": [{"symbol": "LSE:AAPL", "ticker": "AAPL", "exchange": "LSE"}, {"symbol": "NASDAQ:AAPL", "ticker": "AAPL", "exchange": "NASDAQ"}]}
    with _tools({"search_symbols": hits}) as c:
        assert tv.to_tv_symbol("aapl") == "NASDAQ:AAPL"
    assert c.call_args.args == ("search_symbols", {"query": "AAPL", "type_filter": "stock"})


def test_equity_retries_as_etf_then_gives_up():
    calls = []

    def _search(a):
        calls.append(a["type_filter"])
        return {"symbols": [{"symbol": "AMEX:SPY", "ticker": "SPY", "exchange": "AMEX"}] if a["type_filter"] == "etf" else []}

    with _tools({"search_symbols": _search}):
        assert tv.to_tv_symbol("SPY") == "AMEX:SPY"
    assert calls == ["stock", "etf"]
    with _tools({"search_symbols": {"symbols": []}}):
        assert tv.to_tv_symbol("ZZZZ") is None


def test_symbol_resolution_failure_returns_none():
    with _tools({"search_symbols": lambda a: (_ for _ in ()).throw(RuntimeError("boom"))}):
        assert tv.to_tv_symbol("AAPL") is None


@pytest.mark.django_db
def test_fetch_bars_normalizes_sorts_and_persists():
    raw = {"bars": [{"t": 1_760_086_400, "o": 2, "h": 3, "l": 1, "c": 2.5, "v": 20}, {"t": 1_760_000_000, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}, {"t": None}]}
    with _tools({"search_symbols": {"symbols": [{"symbol": "NASDAQ:AAPL", "ticker": "AAPL", "exchange": "NASDAQ"}]}, "get_ohlcv": raw}) as c:
        bars = tv.fetch_bars("AAPL", timeframe="1d", limit=60)
    assert c.call_args_list[-1].args == ("get_ohlcv", {"symbol": "NASDAQ:AAPL", "interval": "1D", "count": 60, "summary": False})
    assert [b["close"] for b in bars] == [1.5, 2.5]
    assert bars[0]["ts"] == "2025-10-09T08:53:20+00:00"
    assert OHLCBar.objects.filter(ticker="AAPL", timeframe="1d").count() == 2


@pytest.mark.parametrize(("tf", "interval"), [("1m", "1"), ("5m", "5"), ("15m", "15"), ("1h", "60"), ("1d", "1D")])
@pytest.mark.django_db
def test_fetch_bars_interval_map(tf, interval):
    with _tools({"get_ohlcv": {"bars": []}}) as c, patch("apps.market.services.tradingview.to_tv_symbol", return_value="SP:SPX"):
        tv.fetch_bars("$SPX", timeframe=tf, limit=5)
    assert c.call_args.args[1]["interval"] == interval


@pytest.mark.django_db
def test_fetch_bars_unmappable_or_failing_returns_empty():
    assert tv.fetch_bars("$ADVN", timeframe="1d") == []
    with _tools({"get_ohlcv": lambda a: (_ for _ in ()).throw(RuntimeError("x"))}), patch("apps.market.services.tradingview.to_tv_symbol", return_value="SP:SPX"):
        assert tv.fetch_bars("$SPX", timeframe="1d") == []


def test_fetch_quotes_maps_batch_rows_to_contract():
    raw = {"data": [{"symbol": "NASDAQ:AAPL", "close": "171.3", "change": -0.5, "volume": "1234.0", "high": 172, "low": 169}]}
    with _tools({"get_symbol_data_batch": raw}) as c, patch("apps.market.services.tradingview.to_tv_symbol", side_effect=lambda t: {"AAPL": "NASDAQ:AAPL", "$ADVN": None}[t]):
        out = tv.fetch_quotes(["AAPL", "$ADVN"])
    assert c.call_args.args[1]["symbols"] == ["NASDAQ:AAPL"]
    assert out == {"AAPL": {"last": 171.3, "bid": None, "ask": None, "volume": 1234, "high": 172.0, "low": 169.0, "pct_change": -0.5}}


def test_fetch_quotes_accepts_scanner_style_rows():
    raw = {"columns": ["close", "change", "volume", "high", "low"], "data": [{"s": "NASDAQ:AAPL", "d": [1, 2, 3, 4, 5]}]}
    with _tools({"get_symbol_data_batch": raw}), patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"):
        assert tv.fetch_quotes(["AAPL"])["AAPL"]["last"] == 1.0


def test_fetch_quotes_failure_returns_empty():
    with _tools({"get_symbol_data_batch": lambda a: (_ for _ in ()).throw(RuntimeError("x"))}), patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"):
        assert tv.fetch_quotes(["AAPL"]) == {}


@pytest.mark.django_db
def test_fetch_news_normalizes_dedups_and_upserts():
    item = {"id": 77, "title": "Apple beats", "published": 1_760_000_000, "provider": "Reuters", "storyPath": "/news/apple-beats/", "link": ""}
    with _tools({"get_news": {"items": [item, item]}}), patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"):
        items = tv.fetch_news(["AAPL"], limit=5)
    assert len(items) == 1
    it = items[0]
    assert it["headline"] == "Apple beats" and it["source"] == "Reuters" and it["datetime"] == 1_760_000_000
    assert it["url"] == "https://www.tradingview.com/news/apple-beats/"
    assert it["ticker"] == "AAPL" and it["tickers"] == ["AAPL"] and it["related"] == "AAPL"
    assert NewsItem.objects.get(provider="tradingview", external_id="77").headline == "Apple beats"


@pytest.mark.django_db
def test_fetch_news_failure_per_ticker_is_skipped():
    with _tools({"get_news": lambda a: (_ for _ in ()).throw(RuntimeError("x"))}), patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"):
        assert tv.fetch_news(["AAPL"]) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/market/tests/test_tradingview_provider.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — create `backend/apps/market/services/tradingview.py`:

```python
"""TradingView (official MCP server) as a market-data provider.

Normalizes TradingView tool results to the app's QUOTES / BARS / NEWS contracts so
``fallback.py`` routes to it exactly like the free providers (it sits FIRST among the
fallbacks). TradingView symbols are ``EXCHANGE:TICKER``; ``to_tv_symbol`` maps the app's
Schwab-style spellings (``$VIX``, ``/ES``) through a table and resolves equities via
``search_symbols`` (cached 7 days). Every fetcher returns empty on any failure, and
``is_connected`` treats a provider_health auth-error marker as "not connected" so a
rejected token stops costing a failing round trip per call. Result key spellings are
handled leniently — the live shapes are confirmed against the captured fixture (spec §9).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from apps.market import cache
from apps.market.services import tradingview_mcp as mcp
from apps.market.services._bars import persist_bars
from apps.market.services.safe_log import safe_err
from apps.market.symbols import normalize_symbol
from apps.secrets.tradingview_oauth import load_token

log = logging.getLogger(__name__)

PROVIDER = "tradingview"
TV_NEWS_BASE = "https://www.tradingview.com"

# App spelling -> TradingView symbol. None = no TradingView equivalent (breadth internals).
INDEX_SYMBOLS: dict[str, str | None] = {
    "$VIX": "TVC:VIX",
    "$SPX": "SP:SPX",
    "$NDX": "NASDAQ:NDX",
    "$DJI": "DJ:DJI",
    "$RUT": "TVC:RUT",
    "$TNX": "TVC:TNX",
    "$COMPX": "NASDAQ:IXIC",
    "$OEX": "SP:OEX",
    "$ADVN": None,
    "$DECN": None,
    "$TICK": None,
    "$TRIN": None,
}
FUTURE_SYMBOLS: dict[str, str] = {
    "/ES": "CME_MINI:ES1!",
    "/NQ": "CME_MINI:NQ1!",
    "/RTY": "CME_MINI:RTY1!",
    "/YM": "CBOT_MINI:YM1!",
    "/CL": "NYMEX:CL1!",
    "/GC": "COMEX:GC1!",
    "/SI": "COMEX:SI1!",
    "/ZB": "CBOT:ZB1!",
    "/ZN": "CBOT:ZN1!",
    "/ZF": "CBOT:ZF1!",
    "/NG": "NYMEX:NG1!",
    "/HG": "COMEX:HG1!",
    "/VX": "CFE:VX1!",
    "/6E": "CME:6E1!",
}
_US_EXCHANGES = ("NASDAQ", "NYSE", "AMEX", "CBOE", "ARCA", "BATS")
_INTERVALS = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "1d": "1D"}
_SYMBOL_CACHE_TTL = 7 * 86_400
_QUOTE_COLUMNS = ["close", "change", "volume", "high", "low"]
_MAX_NEWS_TICKERS = 5


def is_connected() -> bool:
    """A usable token exists and no auth-error marker is set (circuit breaker)."""
    from apps.core import provider_health

    return load_token() is not None and provider_health.auth_error(PROVIDER) is None


# --- lenient result helpers (shared with the calendar normalizers) ----------------------


def _rows(result: Any, *keys: str) -> list[dict]:
    """A list of dict rows from a tool result that is either a list or a dict holding one."""
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def _first(row: dict, *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# --- symbols ---------------------------------------------------------------------------


def _full_symbol(hit: dict) -> str | None:
    symbol = str(hit.get("symbol") or "")
    if ":" in symbol:
        return symbol
    exchange = str(hit.get("exchange") or "")
    ticker = str(_first(hit, "ticker", "name") or symbol)
    return f"{exchange}:{ticker}" if exchange and ticker else None


def _pick(hits: list[dict], ticker: str) -> str | None:
    """The hit whose ticker equals ``ticker``, preferring US exchanges."""
    matches = [
        h for h in hits if str(_first(h, "ticker", "name", "symbol") or "").upper().split(":")[-1] == ticker
    ]
    for exchange in _US_EXCHANGES:
        for hit in matches:
            if str(hit.get("exchange") or "").upper() == exchange:
                return _full_symbol(hit)
    return _full_symbol(matches[0]) if matches else None


def _search(ticker: str, type_filter: str) -> str | None:
    result = mcp.call_tool("search_symbols", {"query": ticker, "type_filter": type_filter})
    return _pick(_rows(result, "symbols", "results", "data", "items"), ticker)


def to_tv_symbol(ticker: str) -> str | None:
    """TradingView ``EXCHANGE:TICKER`` for an app ticker, or None when unmappable."""
    t = normalize_symbol(ticker)
    if not t:
        return None
    if t.startswith("$"):
        return INDEX_SYMBOLS.get(t)
    if t.startswith("/"):
        return FUTURE_SYMBOLS.get(t)
    try:
        # "" marks a miss so get_or_fetch caches it (a None value is never cached).
        resolved = cache.get_or_fetch(
            f"tradingview:symbol:{t}",
            ttl_seconds=_SYMBOL_CACHE_TTL,
            fetcher=lambda: _search(t, "stock") or _search(t, "etf") or "",
        )
    except Exception as exc:
        log.warning("tradingview.symbol_resolve_failed ticker=%s: %s", t, safe_err(exc))
        return None
    return str(resolved) or None


# --- bars ------------------------------------------------------------------------------


def _normalize_bar(raw: dict) -> dict | None:
    t = _float(_first(raw, "t", "time", "timestamp"))
    if t is None:
        return None
    if t > 1e11:  # milliseconds
        t /= 1000
    open_ = _float(_first(raw, "o", "open"))
    high = _float(_first(raw, "h", "high"))
    low = _float(_first(raw, "l", "low"))
    close = _float(_first(raw, "c", "close"))
    volume = _int(_first(raw, "v", "volume"))
    if None in (open_, high, low, close, volume):
        return None
    ts = datetime.fromtimestamp(int(t), tz=UTC).isoformat()
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume, "ts": ts}


def _fetch_bars_uncached(ticker: str, symbol: str, timeframe: str, interval: str, limit: int) -> list[dict]:
    result = mcp.call_tool(
        "get_ohlcv", {"symbol": symbol, "interval": interval, "count": int(limit), "summary": False}
    )
    bars = [b for b in (_normalize_bar(r) for r in _rows(result, "bars", "data", "candles", "ohlcv")) if b]
    bars.sort(key=lambda b: b["ts"])
    bars = bars[-int(limit) :]
    persist_bars(ticker, timeframe, bars, source=PROVIDER)
    return bars


def fetch_bars(ticker: str, *, timeframe: str = "1d", limit: int = 60) -> list[dict]:
    """BARS CONTRACT rows (oldest first), persisted to OHLCBar. [] on any failure."""
    interval = _INTERVALS.get(timeframe)
    symbol = to_tv_symbol(ticker)
    if interval is None or symbol is None:
        return []
    t = normalize_symbol(ticker)
    try:
        return cache.get_or_fetch(
            f"tradingview:ohlc:{t}:{timeframe}:{limit}",
            ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
            fetcher=lambda: _fetch_bars_uncached(t, symbol, timeframe, interval, limit),
        )
    except Exception as exc:
        log.warning("tradingview.bars_failed ticker=%s: %s", t, safe_err(exc))
        return []


# --- quotes ----------------------------------------------------------------------------


def _batch_rows(result: Any) -> dict[str, dict]:
    """``{symbol: row}`` from a batch result, accepting either flat rows or the scanner
    ``{"s": symbol, "d": [values in column order]}`` shape."""
    columns = result.get("columns") if isinstance(result, dict) else None
    out: dict[str, dict] = {}
    for row in _rows(result, "data", "symbols", "results", "rows", "items"):
        if "d" in row and isinstance(row.get("d"), list):
            names = columns if isinstance(columns, list) else _QUOTE_COLUMNS
            flat = dict(zip(names, row["d"], strict=False))
            out[str(_first(row, "s", "symbol") or "")] = flat
        else:
            out[str(_first(row, "symbol", "name", "s") or "")] = row
    return out


def fetch_quotes(tickers: list[str]) -> dict[str, dict]:
    """QUOTES CONTRACT keyed by the app's ticker spelling. {} on any failure."""
    mapping = {normalize_symbol(t): to_tv_symbol(t) for t in tickers if t}
    symbols = [s for s in mapping.values() if s]
    if not symbols:
        return {}
    try:
        result = mcp.call_tool("get_symbol_data_batch", {"symbols": symbols, "columns": _QUOTE_COLUMNS})
    except Exception as exc:
        log.warning("tradingview.quotes_failed: %s", safe_err(exc))
        return {}
    by_symbol = _batch_rows(result)
    out: dict[str, dict] = {}
    for ticker, symbol in mapping.items():
        row = by_symbol.get(symbol or "")
        if row is None:
            continue
        out[ticker] = {
            "last": _float(row.get("close")),
            "bid": None,
            "ask": None,
            "volume": _int(row.get("volume")),
            "high": _float(row.get("high")),
            "low": _float(row.get("low")),
            "pct_change": _float(row.get("change")),
        }
    return out


# --- news ------------------------------------------------------------------------------


def _normalize_news(raw: dict, ticker: str) -> dict | None:
    external_id = _first(raw, "id", "uuid", "story_id")
    headline = str(_first(raw, "title", "headline") or "").strip()
    published = _int(_first(raw, "published", "published_at", "datetime", "timestamp"))
    if external_id is None or not headline or published is None:
        return None
    if published > 1e11:
        published //= 1000
    url = str(raw.get("link") or raw.get("url") or "")
    if not url and raw.get("storyPath"):
        url = f"{TV_NEWS_BASE}{raw['storyPath']}"
    return {
        "id": str(external_id),
        "external_id": str(external_id),
        "headline": headline[:512],
        "summary": str(raw.get("summary") or raw.get("description") or ""),
        "url": url[:1024],
        "source": str(_first(raw, "provider", "source") or "")[:64],
        "datetime": published,
        "published_at": datetime.fromtimestamp(published, tz=UTC).isoformat(),
        "ticker": ticker,
        "related": ticker,
        "tickers": [ticker],
        "sentiment": {},
    }


def fetch_news(tickers: list[str], *, limit: int = 15) -> list[dict]:
    """Newest-first headlines for up to five tickers, deduped, upserted as NewsItem rows."""
    from apps.market.services.news import _upsert_items

    items: list[dict] = []
    for raw_ticker in [t for t in tickers if t][:_MAX_NEWS_TICKERS]:
        ticker = normalize_symbol(raw_ticker)
        symbol = to_tv_symbol(ticker)
        if symbol is None:
            continue
        try:
            result = mcp.call_tool("get_news", {"symbol": symbol, "limit": int(limit)})
        except Exception as exc:
            log.warning("tradingview.news_failed ticker=%s: %s", ticker, safe_err(exc))
            continue
        for raw in _rows(result, "items", "news", "data", "results"):
            item = _normalize_news(raw, ticker)
            if item:
                items.append(item)
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in sorted(items, key=lambda i: i["datetime"], reverse=True):
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)
    deduped = deduped[:limit]
    _upsert_items(PROVIDER, deduped)
    return deduped
```

- [ ] **Step 4: Run tests + lint**

Run: `docker compose exec web pytest apps/market/tests/test_tradingview_provider.py -v` → PASS. `ruff check`/`format` on the new file. If `lint-imports` (import-linter) objects to `apps.market → apps.secrets.tradingview_oauth`, switch the `load_token` import to a function-level import inside `is_connected` (the `fallback.py` → `apps.secrets.credentials` import already crosses this boundary, so it should pass).

- [ ] **Step 5: Commit**

```bash
LEFTHOOK=0 git add backend/apps/market/services/tradingview.py backend/apps/market/tests/test_tradingview_provider.py
LEFTHOOK=0 git commit -m "feat(market): TradingView provider normalizers (symbols, bars, quotes, news)"
```

---

### Task 8: Calendars — earnings + economic calendar normalizers, wired into `events.py`

**Files:**
- Modify: `backend/apps/market/services/tradingview.py` (append)
- Modify: `backend/apps/market/services/events.py` (`_upsert_earnings` source param; `fetch_earnings`; `fetch_macro`)
- Test: `backend/apps/market/tests/test_tradingview_provider.py` (append), `backend/apps/market/tests/test_events_service.py` (append)

**Interfaces:**
- Consumes: `_rows/_first/_float/_int`, `to_tv_symbol`, `is_connected` (Task 7); `events._upsert_earnings`, `events._upsert_macro`, `SEED_MACRO_EVENTS`.
- Produces: `tradingview.fetch_earnings(tickers) -> list[dict]` (rows `{symbol, date, hour, epsEstimate, revenueEstimate}`), `tradingview.fetch_economic_calendar(*, ahead_days=45) -> list[dict]` (rows `{event, impact, country, time, estimate, prev, actual}`), `events._upsert_earnings(rows, *, source="finnhub")`.

- [ ] **Step 1: Failing tests** — append to `test_tradingview_provider.py`:

```python
def test_fetch_earnings_rows_for_events_upsert():
    raw = {"events": [{"symbol": "NASDAQ:NVDA", "date": "2026-11-19", "time": "after market close", "eps_estimate": "0.84", "revenue_estimate": 2.6e10}, {"symbol": "NASDAQ:NVDA", "date": None}]}
    with _tools({"get_earnings_calendar": raw}) as c, patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:NVDA"):
        rows = tv.fetch_earnings(["NVDA"])
    assert c.call_args.args == ("get_earnings_calendar", {"symbols": ["NASDAQ:NVDA"]})
    assert rows == [{"symbol": "NVDA", "date": "2026-11-19", "hour": "amc", "epsEstimate": 0.84, "revenueEstimate": 2.6e10}]


def test_fetch_earnings_accepts_epoch_dates_and_bmo():
    raw = [{"symbol": "NASDAQ:NVDA", "timestamp": 1_760_000_000, "session": "pre-market"}]
    with _tools({"get_earnings_calendar": raw}), patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:NVDA"):
        rows = tv.fetch_earnings(["NVDA"])
    assert rows[0]["date"] == "2025-10-09" and rows[0]["hour"] == "bmo"


def test_fetch_economic_calendar_rows_for_macro_upsert():
    raw = {"events": [{"title": "Consumer Price Index (MoM)", "country": "US", "importance": "high", "date": "2026-10-14T12:30:00Z", "forecast": "0.3", "previous": 0.2, "actual": None}, {"title": "no time"}]}
    with _tools({"get_economic_calendar": raw}) as c:
        rows = tv.fetch_economic_calendar(ahead_days=10)
    args = c.call_args.args[1]
    assert args["countries"] == ["US"] and "from_date" in args and "to_date" in args
    assert rows == [{"event": "Consumer Price Index (MoM)", "impact": "high", "country": "US", "time": "2026-10-14T12:30:00+00:00", "estimate": 0.3, "prev": 0.2, "actual": None}]


def test_calendar_failures_return_empty():
    boom = lambda a: (_ for _ in ()).throw(RuntimeError("x"))  # noqa: E731
    with _tools({"get_earnings_calendar": boom, "get_economic_calendar": boom}), patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:NVDA"):
        assert tv.fetch_earnings(["NVDA"]) == []
        assert tv.fetch_economic_calendar() == []
```

Append to `backend/apps/market/tests/test_events_service.py`:

```python
@pytest.mark.django_db
def test_fetch_earnings_uses_tradingview_when_finnhub_unkeyed():
    rows = [{"symbol": "NVDA", "date": _soon(3), "hour": "amc", "epsEstimate": 1.0, "revenueEstimate": 2.0}]
    with (
        patch("apps.market.services.events._finnhub_api_key", return_value=None),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch("apps.market.services.tradingview.fetch_earnings", return_value=rows) as f,
    ):
        out = events.fetch_earnings(["NVDA", "/ES"])
    f.assert_called_once_with(["NVDA"])  # equity-like only
    assert len(out) == 1 and out[0].source == "tradingview" and out[0].ticker == "NVDA"


@pytest.mark.django_db
def test_fetch_macro_prefers_tradingview_over_seed():
    rows = [{"event": "Consumer Price Index (MoM)", "impact": "high", "country": "US", "time": f"{_soon(5)}T12:30:00+00:00", "estimate": 0.3, "prev": 0.2, "actual": None}]
    with (
        patch("apps.market.services.events._finnhub_api_key", return_value=None),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch("apps.market.services.tradingview.fetch_economic_calendar", return_value=rows),
    ):
        out = events.fetch_macro(ahead_days=45)
    assert {e.source for e in out} == {"tradingview"}
    assert out[0].kind == "cpi"


@pytest.mark.django_db
def test_fetch_macro_falls_to_seed_when_tradingview_empty():
    with (
        patch("apps.market.services.events._finnhub_api_key", return_value=None),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch("apps.market.services.tradingview.fetch_economic_calendar", return_value=[]),
    ):
        out = events.fetch_macro(ahead_days=45)
    assert all(e.source == "seed" for e in out)


@pytest.mark.parametrize(
    ("name", "kind"),
    [("Fed Interest Rate Decision", "fomc"), ("Consumer Price Index (MoM)", "cpi"), ("Non Farm Payrolls", "nfp"), ("Core PCE Price Index (YoY)", "pce"), ("GDP Growth Rate QoQ Adv", "gdp"), ("Retail Sales", None)],
)
def test_macro_kind_classifies_tradingview_names(name, kind):
    assert events._macro_kind(name) == kind
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/market/tests/test_tradingview_provider.py apps/market/tests/test_events_service.py -k "earnings or economic or macro" -v` → the new tests FAIL (`AttributeError: fetch_earnings` / source mismatch). `test_macro_kind_classifies_tradingview_names` should already PASS — the existing `_MACRO_MAP` needles cover these names; do not add entries.

- [ ] **Step 3: Normalizers** — append to `backend/apps/market/services/tradingview.py` (add `from datetime import UTC, datetime, timedelta` and `import re` at the top):

```python
# --- calendars -------------------------------------------------------------------------

_BMO = ("bmo", "before", "pre")
_AMC = ("amc", "after", "post")


def _date_str(value: Any) -> str | None:
    """'YYYY-MM-DD' from a date string, an ISO datetime, or a unix timestamp; else None."""
    if value is None:
        return None
    if isinstance(value, int | float):
        ts = float(value) / 1000 if value > 1e11 else float(value)
        return datetime.fromtimestamp(ts, tz=UTC).date().isoformat()
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _session_hint(value: Any) -> str:
    text = str(value or "").lower()
    if any(k in text for k in _BMO):
        return "bmo"
    if any(k in text for k in _AMC):
        return "amc"
    return ""


def _iso_datetime(value: Any) -> str | None:
    """Timezone-aware ISO string from an ISO string or unix timestamp; else None."""
    if value is None:
        return None
    if isinstance(value, int | float):
        ts = float(value) / 1000 if value > 1e11 else float(value)
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def fetch_earnings(tickers: list[str]) -> list[dict]:
    """Rows in the shape ``events._upsert_earnings`` consumes. [] on any failure."""
    mapping = {normalize_symbol(t): to_tv_symbol(t) for t in tickers if t}
    symbols = [s for s in mapping.values() if s]
    if not symbols:
        return []
    try:
        result = mcp.call_tool("get_earnings_calendar", {"symbols": symbols})
    except Exception as exc:
        log.warning("tradingview.earnings_failed: %s", safe_err(exc))
        return []
    back = {s: t for t, s in mapping.items() if s}
    rows: list[dict] = []
    for raw in _rows(result, "events", "earnings", "data", "results", "items"):
        symbol = str(_first(raw, "symbol", "name") or "")
        ticker = back.get(symbol) or symbol.split(":")[-1]
        date = _date_str(_first(raw, "date", "earnings_release_date", "timestamp")) or _date_str(raw.get("time"))
        if not ticker or not date:
            continue
        rows.append(
            {
                "symbol": ticker,
                "date": date,
                "hour": _session_hint(_first(raw, "time", "session", "hour", "release_time")),
                "epsEstimate": _float(_first(raw, "eps_estimate", "epsEstimate", "eps_forecast")),
                "revenueEstimate": _float(_first(raw, "revenue_estimate", "revenueEstimate", "revenue_forecast")),
            }
        )
    return rows


def fetch_economic_calendar(*, ahead_days: int = 45) -> list[dict]:
    """US macro rows in the shape ``events._upsert_macro`` consumes. [] on any failure."""
    today = datetime.now(UTC).date()
    end = today + timedelta(days=ahead_days)
    try:
        result = mcp.call_tool(
            "get_economic_calendar",
            {"countries": ["US"], "from_date": today.isoformat(), "to_date": end.isoformat()},
        )
    except Exception as exc:
        log.warning("tradingview.macro_failed: %s", safe_err(exc))
        return []
    rows: list[dict] = []
    for raw in _rows(result, "events", "data", "results", "items"):
        when = _iso_datetime(_first(raw, "date", "time", "timestamp", "datetime"))
        if when is None:
            continue
        rows.append(
            {
                "event": str(_first(raw, "title", "event", "name") or ""),
                "impact": str(_first(raw, "importance", "impact") or ""),
                "country": str(_first(raw, "country", "country_code") or "US"),
                "time": when,
                "estimate": _float(_first(raw, "forecast", "estimate", "consensus")),
                "prev": _float(_first(raw, "previous", "prev", "prior")),
                "actual": _float(raw.get("actual")),
            }
        )
    return rows
```

- [ ] **Step 4: Wire `events.py`** — change the signature `def _upsert_earnings(rows: list[dict]) -> list[MarketEvent]:` to `def _upsert_earnings(rows: list[dict], *, source: str = "finnhub") -> list[MarketEvent]:` and its `source="finnhub",` line to `source=source,`. In `fetch_earnings` replace the `if not api_key:` block with:

```python
    if not api_key:
        from apps.market.services import tradingview

        if tradingview.is_connected():
            rows = tradingview.fetch_earnings([t.upper() for t in tickers if is_equity_like(t)])
            return _upsert_earnings(rows, source="tradingview")
        log.info("Finnhub credential not configured; no earnings fetched")
        return []
```

In `fetch_macro` replace the two lines `upserted = _upsert_macro(rows, source="finnhub")` / `if not upserted: upserted = _upsert_macro(SEED_MACRO_EVENTS, source="seed")` with:

```python
    upserted = _upsert_macro(rows, source="finnhub")
    if not upserted:
        from apps.market.services import tradingview

        if tradingview.is_connected():
            upserted = _upsert_macro(
                tradingview.fetch_economic_calendar(ahead_days=ahead_days), source="tradingview"
            )
    if not upserted:
        upserted = _upsert_macro(SEED_MACRO_EVENTS, source="seed")
```

Update the `fetch_macro` docstring to: `"""Fetch + upsert curated US high-impact macro: Finnhub → TradingView (when connected) → SEED_MACRO_EVENTS."""`.

- [ ] **Step 5: Run tests + lint**

Run: `docker compose exec web pytest apps/market/tests/test_tradingview_provider.py apps/market/tests/test_events_service.py -v` → PASS. `ruff check`/`format` on both files (watch `C901` on `fetch_earnings`; it is under 15).

- [ ] **Step 6: Commit**

```bash
LEFTHOOK=0 git add backend/apps/market
LEFTHOOK=0 git commit -m "feat(market): TradingView earnings + economic calendar as the source ahead of the macro seed"
```

---

### Task 9: Fallback precedence — TradingView first

**Files:**
- Modify: `backend/apps/market/services/fallback.py`
- Test: `backend/apps/market/tests/test_fallback.py` (append)

**Interfaces:**
- Consumes: `tradingview.is_connected / fetch_quotes / fetch_bars / fetch_news` (Task 7).
- Produces: `alt_quotes`, `alt_bars`, `alt_news` consult TradingView first.

- [ ] **Step 1: Failing tests** — append to `backend/apps/market/tests/test_fallback.py`:

```python
def _tv_cred() -> None:
    ApiCredential.objects.create(
        provider="tradingview", token={"access_token": "a", "refresh_token": "r", "expires_at": 9999999999}
    )


@pytest.mark.django_db
def test_alt_quotes_prefers_tradingview_over_alpaca():
    _tv_cred()
    _cred("alpaca")
    with (
        patch("apps.core.provider_health.auth_error", return_value=None),
        patch("apps.market.services.tradingview.fetch_quotes", return_value={"AAPL": {"last": 9.0}}) as tv,
        patch("apps.market.services.alpaca.fetch_quotes") as al,
    ):
        assert fallback.alt_quotes(["AAPL"]) == {"AAPL": {"last": 9.0}}
    tv.assert_called_once_with(["AAPL"])
    al.assert_not_called()


@pytest.mark.django_db
def test_alt_bars_prefers_tradingview_for_intraday():
    _tv_cred()
    _cred("alpaca")
    with (
        patch("apps.core.provider_health.auth_error", return_value=None),
        patch("apps.market.services.tradingview.fetch_bars", return_value=[{"close": 1}]) as tv,
    ):
        assert fallback.alt_bars("AAPL", "5m", limit=10) == [{"close": 1}]
    tv.assert_called_once_with("AAPL", timeframe="5m", limit=10)


@pytest.mark.django_db
def test_alt_news_prefers_tradingview():
    _tv_cred()
    _cred("marketaux")
    with (
        patch("apps.core.provider_health.auth_error", return_value=None),
        patch("apps.market.services.tradingview.fetch_news", return_value=[{"headline": "x"}]) as tv,
    ):
        assert fallback.alt_news(["AAPL"], limit=3) == [{"headline": "x"}]
    tv.assert_called_once_with(["AAPL"], limit=3)


@pytest.mark.django_db
def test_tradingview_skipped_when_auth_error_marker_set():
    _tv_cred()
    _cred("alpaca")
    with (
        patch("apps.core.provider_health.auth_error", return_value="rejected"),
        patch("apps.market.services.tradingview.fetch_quotes") as tv,
        patch("apps.market.services.alpaca.fetch_quotes", return_value={"AAPL": {"last": 1.0}}),
    ):
        assert fallback.alt_quotes(["AAPL"]) == {"AAPL": {"last": 1.0}}
    tv.assert_not_called()
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/market/tests/test_fallback.py -k tradingview -v` → FAIL.

- [ ] **Step 3: Implement** — in `backend/apps/market/services/fallback.py` add after `_has`:

```python
def _tradingview() -> bool:
    """TradingView (official MCP server) is connected and not auth-errored. It is a paid,
    exchange-routed feed with a per-user budget, so it outranks every free provider."""
    from apps.market.services import tradingview

    return tradingview.is_connected()
```

Then at the top of each of the three functions:

```python
def alt_quotes(tickers: list[str]) -> dict | None:
    """Quotes from the first configured provider (TradingView -> Alpaca -> Twelve Data), else None."""
    if _tradingview():
        from apps.market.services import tradingview

        return tradingview.fetch_quotes(tickers)
    ...

def alt_bars(...):
    """... Precedence: TradingView (any timeframe) -> Alpaca (any timeframe) -> Twelve Data ..."""
    if _tradingview():
        from apps.market.services import tradingview

        return tradingview.fetch_bars(ticker, timeframe=timeframe, limit=limit)
    ...

def alt_news(...):
    """News from the first configured provider (TradingView -> Marketaux -> Tiingo), else None."""
    if _tradingview():
        from apps.market.services import tradingview

        return tradingview.fetch_news(tickers, limit=limit)
    ...
```

Update the module docstring's precedence sentence to name TradingView first and note that "configured" for TradingView means connected without an auth-error marker.

- [ ] **Step 4: Run tests**

Run: `docker compose exec web pytest apps/market/tests/test_fallback.py apps/market/tests/test_quotes*.py apps/market/tests/test_ohlc*.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
LEFTHOOK=0 git add backend/apps/market/services/fallback.py backend/apps/market/tests/test_fallback.py
LEFTHOOK=0 git commit -m "feat(market): TradingView first in the quotes/bars/news fallback order"
```

---

### Task 10: `Toolset` dynamic resolvers + `merge`

**Files:**
- Modify: `backend/apps/ai/tools/__init__.py`
- Test: `backend/apps/ai/tests/test_toolset_dynamic.py`

**Interfaces:**
- Produces: `Toolset.dynamic_resolvers: list[Callable[[str], ToolSpec | None]]`, `Toolset.add_resolver(resolver)`, `Toolset.merge(other) -> Toolset` (in place, returns self), `Toolset.resolve(name) -> ToolSpec | None`; `Toolset.run` consults resolvers on a miss.

- [ ] **Step 1: Failing tests** — create `backend/apps/ai/tests/test_toolset_dynamic.py`:

```python
"""Toolset: dynamic resolvers (tv_* dispatch without pre-registered specs) and merge."""

from __future__ import annotations

from apps.ai.tools import ToolSpec, Toolset


def _spec(name: str, value: str) -> ToolSpec:
    return ToolSpec(name=name, description=name, input_schema={"type": "object"}, fn=lambda **kw: value)


def test_run_consults_dynamic_resolvers_on_a_miss() -> None:
    ts = Toolset()
    ts.register(_spec("native", "n"))
    ts.add_resolver(lambda name: _spec(name, "dyn") if name.startswith("tv_") else None)
    assert ts.run("native", {}) == {"ok": True, "result": "n"}
    assert ts.run("tv_anything", {}) == {"ok": True, "result": "dyn"}
    assert ts.run("nope", {}) == {"ok": False, "error": "Unknown tool: nope"}


def test_registered_spec_wins_over_resolvers() -> None:
    ts = Toolset()
    ts.register(_spec("tv_x", "registered"))
    ts.add_resolver(lambda name: _spec(name, "dyn"))
    assert ts.run("tv_x", {}) == {"ok": True, "result": "registered"}


def test_merge_adds_specs_and_resolvers_and_serializes_them() -> None:
    a = Toolset()
    a.register(_spec("a", "a"))
    b = Toolset()
    b.register(_spec("b", "b"))
    b.add_resolver(lambda name: None)
    out = a.merge(b)
    assert out is a
    assert set(a.specs) == {"a", "b"}
    assert len(a.dynamic_resolvers) == 1
    assert [t["name"] for t in a.anthropic_tools()] == ["a", "b"]
    assert [t["function"]["name"] for t in a.openai_tools()] == ["a", "b"]


def test_resolver_exception_surfaces_as_tool_error() -> None:
    ts = Toolset()
    ts.add_resolver(lambda name: _spec(name, "x"))

    def boom(**kw):
        raise ValueError("bad input")

    ts.register(ToolSpec(name="boom", description="", input_schema={}, fn=boom))
    assert ts.run("boom", {}) == {"ok": False, "error": "ValueError: bad input"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/ai/tests/test_toolset_dynamic.py -v` → FAIL (`AttributeError: add_resolver`).

- [ ] **Step 3: Implement** — replace the `Toolset` class in `backend/apps/ai/tools/__init__.py` with:

```python
@dataclass
class Toolset:
    specs: dict[str, ToolSpec] = field(default_factory=dict)
    # Consulted by run() when a name has no registered spec. Lets a family of tools whose
    # schemas are only known on the sync request path (TradingView's tv_*) still be
    # executed from the providers' async loops, which build the toolset without I/O.
    dynamic_resolvers: list[Callable[[str], ToolSpec | None]] = field(default_factory=list)

    def register(self, spec: ToolSpec) -> None:
        self.specs[spec.name] = spec

    def add_resolver(self, resolver: Callable[[str], ToolSpec | None]) -> None:
        self.dynamic_resolvers.append(resolver)

    def merge(self, other: Toolset) -> Toolset:
        """Add ``other``'s specs and resolvers into this toolset (in place); returns self."""
        self.specs.update(other.specs)
        self.dynamic_resolvers.extend(other.dynamic_resolvers)
        return self

    def resolve(self, name: str) -> ToolSpec | None:
        spec = self.specs.get(name)
        if spec is not None:
            return spec
        for resolver in self.dynamic_resolvers:
            spec = resolver(name)
            if spec is not None:
                return spec
        return None

    def anthropic_tools(self) -> list[dict]:
        """Serialize specs to the shape Claude's tools= param expects."""
        return [
            {"name": s.name, "description": s.description, "input_schema": s.input_schema}
            for s in self.specs.values()
        ]

    def openai_tools(self) -> list[dict]:
        """Serialize specs to the shape OpenAI's tools= param expects."""
        return [
            {
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.input_schema,
                },
            }
            for s in self.specs.values()
        ]

    def run(self, name: str, tool_input: dict) -> dict:
        """Execute the named tool. Returns {"ok": bool, "result"|"error": ...}."""
        spec = self.resolve(name)
        if spec is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        try:
            result = spec.fn(**tool_input)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
```

- [ ] **Step 4: Run tests**

Run: `docker compose exec web pytest apps/ai/tests/test_toolset_dynamic.py apps/ai/tests/test_tool_registry.py apps/ai/tests/test_claude_tools.py apps/ai/tests/test_provider_tool_cap.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
LEFTHOOK=0 git add backend/apps/ai/tools/__init__.py backend/apps/ai/tests/test_toolset_dynamic.py
LEFTHOOK=0 git commit -m "feat(ai): Toolset dynamic resolvers + merge"
```

---

### Task 11: AI bridge — allowlist, `tv_` specs, `resolve_dynamic`, `request_toolset`

**Files:**
- Create: `backend/apps/ai/tools/tradingview.py`
- Modify: `backend/apps/ai/tools/registry.py` (`default_toolset` registers the resolver; new `request_toolset`)
- Test: `backend/apps/ai/tests/test_tradingview_tools.py`

**Interfaces:**
- Consumes: `Toolset.add_resolver/merge` (Task 10); `runtime_config().tradingview_tools_enabled` (Task 1); `apps.market.services.tradingview.is_connected` (Task 7); `tradingview_mcp.list_tools/call_tool` (Task 5).
- Produces: `TV_PREFIX = "tv_"`, `TRADINGVIEW_TOOL_ALLOWLIST: frozenset[str]`, `tradingview_toolset() -> Toolset` (sync path; I/O), `resolve_dynamic(name) -> ToolSpec | None` (pure), `registry.request_toolset() -> Toolset`.

- [ ] **Step 1: Failing tests** — create `backend/apps/ai/tests/test_tradingview_tools.py`:

```python
"""TradingView tools bridged into the AI Toolset: allowlist, tv_ prefix, gating, dispatch."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.ai.tools import tradingview as bridge
from apps.ai.tools.registry import default_toolset, request_toolset

LIVE = [
    {"name": "get_ohlcv", "description": "Bars.", "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "get_screener_columns", "description": "Columns.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "create_alert", "description": "Write!", "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}}},
    {"name": "brand_new_beta_tool", "description": "?", "inputSchema": {"type": "object"}},
    {"name": "search_symbols", "description": "Search."},
]


def _enabled(value: bool):
    class _RC:
        tradingview_tools_enabled = value

    return patch("apps.core.runtime_config.runtime_config", return_value=_RC())


def test_allowlist_has_25_read_only_names() -> None:
    assert len(bridge.TRADINGVIEW_TOOL_ALLOWLIST) == 25
    assert not any(n.startswith(("create_", "update_", "delete_", "add_", "remove_", "stop_", "restart_")) for n in bridge.TRADINGVIEW_TOOL_ALLOWLIST)


@pytest.mark.django_db
def test_toolset_is_allowlist_intersected_with_live_list_and_prefixed() -> None:
    with (
        _enabled(True),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch("apps.market.services.tradingview_mcp.list_tools", return_value=LIVE),
    ):
        ts = bridge.tradingview_toolset()
    assert set(ts.specs) == {"tv_get_ohlcv", "tv_get_screener_columns", "tv_search_symbols"}
    ohlcv = ts.specs["tv_get_ohlcv"]
    assert ohlcv.description.startswith("TradingView: Bars.")
    assert "EXCHANGE:TICKER" in ohlcv.description and "tv_search_symbols" in ohlcv.description
    assert "EXCHANGE:TICKER" not in ts.specs["tv_get_screener_columns"].description
    assert ohlcv.input_schema["required"] == ["symbol"]
    assert ts.specs["tv_search_symbols"].input_schema == {"type": "object", "properties": {}}


@pytest.mark.django_db
@pytest.mark.parametrize(("enabled", "connected"), [(False, True), (True, False), (False, False)])
def test_toolset_empty_unless_enabled_and_connected(enabled, connected) -> None:
    with (
        _enabled(enabled),
        patch("apps.market.services.tradingview.is_connected", return_value=connected),
        patch("apps.market.services.tradingview_mcp.list_tools", return_value=LIVE) as lt,
    ):
        assert bridge.tradingview_toolset().specs == {}
    lt.assert_not_called()


@pytest.mark.django_db
def test_toolset_empty_when_list_tools_fails() -> None:
    with (
        _enabled(True),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch("apps.market.services.tradingview_mcp.list_tools", side_effect=RuntimeError("down")),
    ):
        assert bridge.tradingview_toolset().specs == {}


def test_resolve_dynamic_only_allowlisted_tv_names() -> None:
    assert bridge.resolve_dynamic("get_quote") is None
    assert bridge.resolve_dynamic("tv_create_alert") is None
    spec = bridge.resolve_dynamic("tv_get_news")
    assert spec is not None and spec.name == "tv_get_news"


def test_tv_spec_runs_call_tool_with_kwargs() -> None:
    spec = bridge.resolve_dynamic("tv_get_ohlcv")
    with patch("apps.market.services.tradingview_mcp.call_tool", return_value={"bars": []}) as c:
        assert spec.fn(symbol="NASDAQ:AAPL", interval="1D") == {"bars": []}
    c.assert_called_once_with("get_ohlcv", {"symbol": "NASDAQ:AAPL", "interval": "1D"})


def test_default_toolset_dispatches_tv_names_without_io() -> None:
    ts = default_toolset()
    with patch("apps.market.services.tradingview_mcp.call_tool", return_value="ok") as c:
        assert ts.run("tv_get_news", {"symbol": "NASDAQ:AAPL"}) == {"ok": True, "result": "ok"}
        assert ts.run("tv_create_alert", {"symbol": "x", "price": 1})["ok"] is False
    c.assert_called_once()


@pytest.mark.django_db
def test_request_toolset_merges_tradingview_specs() -> None:
    with (
        _enabled(True),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch("apps.market.services.tradingview_mcp.list_tools", return_value=LIVE),
    ):
        names = set(request_toolset().specs)
    assert {"get_quote", "fetch_ohlc", "tv_get_ohlcv"} <= names
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/ai/tests/test_tradingview_tools.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement bridge** — create `backend/apps/ai/tools/tradingview.py`:

```python
"""TradingView MCP tools bridged into the AI Toolset (read-only allowlist).

Two halves, split on purpose:
- ``tradingview_toolset()`` does I/O (runtime_config → ORM, cached tools/list → Redis /
  HTTP) and is only called on the SYNC request-assembly path
  (``registry.request_toolset``), where the tool *schemas* go on the RunRequest.
- ``resolve_dynamic(name)`` is pure. ``default_toolset()`` registers it, so the
  providers' async streaming loops can dispatch a ``tv_*`` call without touching the ORM
  or the network at lookup time (execution runs under sync_to_async, where I/O is fine).

Every bridged tool is ``tv_<name>`` so provenance shows in ToolCall rows and the thread
UI and native names never collide. Write tools are never exposed — the allowlist is the
only source of exposable names; new beta tools stay out until added here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from apps.ai.tools import ToolSpec, Toolset

log = logging.getLogger(__name__)

TV_PREFIX = "tv_"
TRADINGVIEW_TOOL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "list_watchlists",
        "get_watchlist",
        "get_active_watchlist",
        "get_ohlcv",
        "get_economic_data",
        "get_economic_symbols",
        "search_symbols",
        "run_screener",
        "get_symbol_data",
        "get_symbol_data_batch",
        "get_screener_columns",
        "get_technicals_rating",
        "get_news",
        "get_news_story",
        "get_forecasts",
        "get_financials",
        "get_financial_history",
        "get_documents",
        "get_document_view",
        "get_earnings_calendar",
        "get_economic_calendar",
        "get_dividends_calendar",
        "list_alerts",
        "get_alerts",
        "get_alerts_log",
    }
)
_SYMBOL_NOTE = (
    " Symbols are EXCHANGE:TICKER (e.g. NASDAQ:AAPL, CME_MINI:ES1!, TVC:VIX); "
    "use tv_search_symbols to resolve a bare ticker."
)


def _runner(tool_name: str) -> Callable[..., Any]:
    def run(**kwargs: Any) -> Any:
        from apps.market.services.tradingview_mcp import call_tool

        return call_tool(tool_name, kwargs)

    run.__name__ = f"{TV_PREFIX}{tool_name}"
    return run


def _spec_from(tool: dict) -> ToolSpec | None:
    name = str(tool.get("name") or "")
    if name not in TRADINGVIEW_TOOL_ALLOWLIST:
        return None
    schema = dict(tool.get("inputSchema") or {})
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    description = f"TradingView: {tool.get('description') or name}"
    props = schema.get("properties") or {}
    if isinstance(props, dict) and ("symbol" in props or "symbols" in props):
        description += _SYMBOL_NOTE
    return ToolSpec(
        name=f"{TV_PREFIX}{name}", description=description, input_schema=schema, fn=_runner(name)
    )


def tradingview_toolset() -> Toolset:
    """Allowlisted ``tv_*`` specs when the toggle is on AND TradingView is connected;
    otherwise (or on any transport error) an empty toolset. Sync path only."""
    toolset = Toolset()
    try:
        from apps.core.runtime_config import runtime_config
        from apps.market.services import tradingview, tradingview_mcp

        if not runtime_config().tradingview_tools_enabled or not tradingview.is_connected():
            return toolset
        for tool in tradingview_mcp.list_tools():
            spec = _spec_from(tool)
            if spec is not None:
                toolset.register(spec)
    except Exception:
        log.warning("TradingView tools unavailable for this run", exc_info=True)
        return Toolset()
    return toolset


def resolve_dynamic(name: str) -> ToolSpec | None:
    """Pure resolver for ``default_toolset()``: ``tv_<allowlisted>`` → a runnable spec."""
    if not name.startswith(TV_PREFIX):
        return None
    bare = name[len(TV_PREFIX) :]
    if bare not in TRADINGVIEW_TOOL_ALLOWLIST:
        return None
    return ToolSpec(
        name=name, description=f"TradingView: {bare}", input_schema={"type": "object"}, fn=_runner(bare)
    )
```

- [ ] **Step 4: Registry** — in `backend/apps/ai/tools/registry.py` add the top-level import `from apps.ai.tools.tradingview import resolve_dynamic`, add `ts.add_resolver(resolve_dynamic)` immediately before the final `return ts` of `default_toolset()`, and append (the `tradingview_toolset` import is deliberately inside the function so tests can patch `apps.ai.tools.tradingview.tradingview_toolset`):

```python
def request_toolset() -> Toolset:
    """The toolset whose SCHEMAS go on a RunRequest: the defaults plus TradingView's
    ``tv_*`` tools when the toggle is on and TradingView is connected.

    Sync path only — this does ORM + Redis/HTTP. Providers keep calling
    ``default_toolset()`` for execution; its dynamic resolver dispatches ``tv_*`` names."""
    from apps.ai.tools.tradingview import tradingview_toolset

    return default_toolset().merge(tradingview_toolset())
```

Also update the `TradingProfile.enable_tools` help_text? No — leave it (a help_text change needs a migration + schema regen; the doc lives in CLAUDE.md).

- [ ] **Step 5: Run tests + lint**

Run: `docker compose exec web pytest apps/ai -v` → PASS. `ruff check`/`format` on `apps/ai/tools`.

- [ ] **Step 6: Commit**

```bash
LEFTHOOK=0 git add backend/apps/ai
LEFTHOOK=0 git commit -m "feat(ai): bridge allowlisted TradingView MCP tools as tv_* ToolSpecs"
```

---

### Task 12: Request assembly — merge `tv_*` schemas on the two sync call sites

**Files:**
- Modify: `backend/apps/threads/_request.py` (`_resolve_capabilities`)
- Modify: `backend/apps/threads/tasks.py` (`_apply_investigation_mode`)
- Test: `backend/apps/threads/tests/test_investigation_mode.py` (append), `backend/apps/threads/tests/test_request_tradingview_tools.py` (new)

**Interfaces:**
- Consumes: `apps.ai.tools.registry.request_toolset` (Task 11).
- Produces: `RunRequest.tools` includes `tv_*` schemas (Anthropic or OpenAI shape) whenever the profile has `enable_tools` (or investigation forces tools) and `tradingview_toolset()` is non-empty.

- [ ] **Step 1: Failing tests** — append to `backend/apps/threads/tests/test_investigation_mode.py`:

```python
def test_investigation_mode_includes_tradingview_tools_when_available(settings):
    from apps.ai.tools import ToolSpec, Toolset

    tv = Toolset()
    tv.register(ToolSpec(name="tv_get_ohlcv", description="d", input_schema={"type": "object"}, fn=lambda **k: None))
    req = RunRequest(model="m", system="Base.", messages=[], tools=[])
    with patch("apps.ai.tools.tradingview.tradingview_toolset", return_value=tv):
        _apply_investigation_mode(req, provider_name="openai", cfg=_Cfg())
    assert "tv_get_ohlcv" in {t["function"]["name"] for t in req.tools}
```

(add `from unittest.mock import patch` at the top of that file). Create `backend/apps/threads/tests/test_request_tradingview_tools.py`:

```python
"""tv_* schemas ride the RunRequest only via the sync request-assembly path."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.ai.tools import ToolSpec, Toolset
from apps.profiles.models import TradingProfile
from apps.threads._request import _resolve_capabilities
from apps.threads.models import Thread


def _tv_toolset() -> Toolset:
    ts = Toolset()
    ts.register(ToolSpec(name="tv_get_news", description="d", input_schema={"type": "object"}, fn=lambda **k: None))
    return ts


@pytest.mark.django_db
@pytest.mark.parametrize(("provider", "key"), [("claude", "name"), ("openai", None)])
def test_resolve_capabilities_merges_tradingview_schemas(provider, key):
    prof = TradingProfile.objects.create(name="p", style="x", enable_tools=True)
    thread = Thread.objects.create(kind="chat", profile=prof)
    with patch("apps.ai.tools.tradingview.tradingview_toolset", return_value=_tv_toolset()):
        tools, _, _ = _resolve_capabilities(thread, provider_name=provider, supports_tools=True)
    names = {t["name"] if key else t["function"]["name"] for t in tools}
    assert {"get_quote", "tv_get_news"} <= names


@pytest.mark.django_db
def test_resolve_capabilities_without_enable_tools_has_no_tools():
    prof = TradingProfile.objects.create(name="p", style="x", enable_tools=False)
    thread = Thread.objects.create(kind="chat", profile=prof)
    with patch("apps.ai.tools.tradingview.tradingview_toolset") as tv:
        tools, _, _ = _resolve_capabilities(thread, provider_name="claude", supports_tools=True)
    assert tools == []
    tv.assert_not_called()
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec web pytest apps/threads/tests/test_investigation_mode.py apps/threads/tests/test_request_tradingview_tools.py -v` → the new tests FAIL (`tv_*` missing).

- [ ] **Step 3: Implement** — in `backend/apps/threads/_request.py::_resolve_capabilities` replace

```python
        from apps.ai.tools.registry import default_toolset

        toolset = default_toolset()
```

with

```python
        # request_toolset() = defaults + TradingView tv_* (toggle on + connected). It does
        # ORM/Redis I/O, which is fine HERE (sync Celery path) but not in the providers'
        # async loops — those keep default_toolset(), whose resolver dispatches tv_* names.
        from apps.ai.tools.registry import request_toolset

        toolset = request_toolset()
```

In `backend/apps/threads/tasks.py::_apply_investigation_mode` replace `from apps.ai.tools.registry import default_toolset` / `ts = default_toolset()` with `from apps.ai.tools.registry import request_toolset` / `ts = request_toolset()`.

- [ ] **Step 4: Run tests**

Run: `docker compose exec web pytest apps/threads -v -p no:randomly` → PASS.

- [ ] **Step 5: Commit**

```bash
LEFTHOOK=0 git add backend/apps/threads
LEFTHOOK=0 git commit -m "feat(threads): put TradingView tv_* schemas on the request via request_toolset()"
```

---

### Task 13: Frontend — OAuth card, AI-tools toggle, return-query toast, regenerated types

**Files:**
- Modify: `frontend/src/api/dataSources.ts`, `frontend/src/api/settings.ts`
- Modify: `frontend/src/components/settings/DataSourcesPanel.tsx`
- Modify: `frontend/src/pages/settings/ConnectionsSettings.tsx`
- Modify: `frontend/src/api/schema.d.ts` (regenerated), `backend/schema.yml` (regenerated)
- Test: `frontend/src/__tests__/DataSourcesPanel.test.tsx` (extend), `frontend/src/__tests__/ConnectionsSettings.test.tsx` (extend)

**Interfaces:**
- Consumes: the endpoints from Tasks 2 and 6; `PATCH /api/settings/` (Task 1).
- Produces: `fetchDataSourceAuthorizeUrl(provider)`, `disconnectDataSource(provider)`, `DataSourceStatus.auth_error?`, `SystemSettings.tradingview_tools_enabled`.

- [ ] **Step 1: Failing tests** — in `frontend/src/__tests__/DataSourcesPanel.test.tsx` extend the `@/api/dataSources` mock and add mocks for settings:

```ts
vi.mock("@/api/dataSources", () => ({
  saveDataSourceKey: vi.fn(async () => ({ configured: true, fields_present: ["api_key"] })),
  clearDataSourceKey: vi.fn(async () => ({ configured: false, fields_present: [] })),
  testDataSourceKey: vi.fn(async () => ({ ok: true, message: "Key works." })),
  fetchDataSourceAuthorizeUrl: vi.fn(async () => ({ url: "https://tv/authorize?x=1" })),
  disconnectDataSource: vi.fn(async () => undefined),
}));
const mockUseSystemSettings = vi.fn();
vi.mock("@/hooks/useSystemSettings", () => ({ useSystemSettings: () => mockUseSystemSettings() }));
vi.mock("@/api/settings", () => ({ updateSystemSettings: vi.fn(async () => ({})) }));
```

Add to the imports: `fetchDataSourceAuthorizeUrl, disconnectDataSource` from `@/api/dataSources` and `import { updateSystemSettings } from "@/api/settings";`. Add a TradingView entry to `SOURCES`:

```ts
  {
    provider: "tradingview", label: "TradingView", auth: "oauth", fields: [],
    blurb: "MCP.", signup_url: "https://tv-pricing", docs_url: "https://tv-docs",
    status: { configured: false, fields_present: [], auth_error: null },
  },
```

In `beforeEach` add `mockUseSystemSettings.mockReturnValue({ data: { tradingview_tools_enabled: false } });`. Add tests:

```ts
  it("renders the TradingView OAuth card with a Connect button and no key form", () => {
    renderPanel();
    const card = screen.getByTestId("ds-card-tradingview");
    expect(within(card).getByRole("button", { name: /connect tradingview/i })).toBeInTheDocument();
    expect(within(card).queryByLabelText(/api key/i)).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: /disconnect/i })).not.toBeInTheDocument();
  });

  it("Connect fetches the authorize URL and opens it in a new tab", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderPanel();
    const card = screen.getByTestId("ds-card-tradingview");
    await userEvent.click(within(card).getByRole("button", { name: /connect tradingview/i }));
    expect(vi.mocked(fetchDataSourceAuthorizeUrl)).toHaveBeenCalledWith("tradingview");
    expect(open).toHaveBeenCalledWith("https://tv/authorize?x=1", "_blank", "noopener,noreferrer");
    open.mockRestore();
  });

  it("connected TradingView shows Test, Disconnect, the AI toggle, and an auth error", async () => {
    const connected = SOURCES.map((s) =>
      s.provider === "tradingview"
        ? { ...s, status: { configured: true, fields_present: [], auth_error: "TradingView rejected the stored token" } }
        : s,
    );
    mockUseDataSources.mockReturnValue({ data: { data_sources: connected }, isLoading: false });
    renderPanel();
    const card = screen.getByTestId("ds-card-tradingview");
    expect(within(card).getByRole("alert")).toHaveTextContent(/rejected the stored token/i);
    expect(within(card).getByRole("button", { name: /reconnect/i })).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: /test connection/i }));
    expect(vi.mocked(testDataSourceKey)).toHaveBeenCalledWith("tradingview");
    await userEvent.click(within(card).getByLabelText(/expose tradingview tools to the ai/i));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({ tradingview_tools_enabled: true });
    await userEvent.click(within(card).getByRole("button", { name: /disconnect/i }));
    expect(vi.mocked(disconnectDataSource)).toHaveBeenCalledWith("tradingview");
  });
```

In `frontend/src/__tests__/ConnectionsSettings.test.tsx` add (the file already mocks `useDataSources`):

```ts
  it("toasts and strips the query when returning from TradingView consent", async () => {
    renderWithProviders(<ConnectionsSettings />, { initialEntries: ["/settings/connections?tradingview=connected"] });
    expect(await screen.findByText(/tradingview connected/i)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/DataSourcesPanel.test.tsx src/__tests__/ConnectionsSettings.test.tsx` → FAIL.

- [ ] **Step 3: API clients** — `frontend/src/api/dataSources.ts`: add `auth_error?: string | null;` to `DataSourceStatus` (comment: `/** OAuth sources only: the provider rejected the stored token; reconnect to clear. */`) and append:

```ts
/** OAuth sources (TradingView): the consent URL to open in a new tab. */
export const fetchDataSourceAuthorizeUrl = (provider: string) =>
  apiGet<{ url: string }>(`/api/schwab/data-sources/${provider}/authorize/`);

/** OAuth sources: revoke upstream (best-effort) and forget the token. */
export const disconnectDataSource = (provider: string) =>
  apiDelete(`/api/schwab/data-sources/${provider}/`);
```

`frontend/src/api/settings.ts`: add `tradingview_tools_enabled: boolean;` to `SystemSettings`.

- [ ] **Step 4: Panel** — in `frontend/src/components/settings/DataSourcesPanel.tsx`: import `fetchDataSourceAuthorizeUrl, disconnectDataSource` from `@/api/dataSources`, `useSystemSettings` from `@/hooks/useSystemSettings`, `updateSystemSettings` from `@/api/settings`. Add two components above `DataSourceCard`:

```tsx
function TradingViewToolsToggle({ disabled }: { disabled: boolean }) {
  const { data } = useSystemSettings();
  const qc = useQueryClient();
  const { push } = useToast();
  const [saving, setSaving] = useState(false);
  const checked = data?.tradingview_tools_enabled ?? false;
  const onChange = async (next: boolean) => {
    setSaving(true);
    try {
      await updateSystemSettings({ tradingview_tools_enabled: next });
      await qc.invalidateQueries({ queryKey: ["system-settings"] });
    } catch (e) {
      push({ kind: "error", text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };
  return (
    <label className="flex flex-wrap items-center gap-2">
      <input
        type="checkbox"
        aria-label="Expose TradingView tools to the AI"
        checked={checked}
        disabled={disabled || saving}
        onChange={(e) => void onChange(e.target.checked)}
      />
      <span className="text-[13px] text-ink-200">Expose TradingView tools to the AI</span>
      <span className="text-[11px] text-ink-500">
        Adds the read-only tv_* tools to every tool-enabled profile run (~3–6k prompt tokens).
      </span>
    </label>
  );
}

function OAuthControls({ ds, onChanged }: { ds: DataSource; onChanged: () => void }) {
  const { push } = useToast();
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const withBusy = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      push({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  const connect = () =>
    withBusy(async () => {
      const { url } = await fetchDataSourceAuthorizeUrl(ds.provider);
      // New tab, as with Schwab: a rejected registration or the provider's consent page
      // must never replace the dashboard. `noopener` severs window.opener.
      window.open(url, "_blank", "noopener,noreferrer");
    });
  const test = () =>
    withBusy(async () => {
      const res = await testDataSourceKey(ds.provider);
      setTestResult(res);
      push({ kind: res.ok ? "success" : "error", text: `${ds.label}: ${res.message}` });
    });
  const disconnect = () =>
    withBusy(async () => {
      setTestResult(null);
      await disconnectDataSource(ds.provider);
      onChanged();
      push({ kind: "success", text: `${ds.label} disconnected.` });
    });
  return (
    <div className="mt-4 grid gap-3">
      {ds.status.auth_error ? (
        <p
          role="alert"
          className="rounded-ledger border border-loss-300 bg-loss-300/10 px-3 py-2 text-[13px] text-loss-300"
        >
          {ds.status.auth_error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={connect} disabled={busy} className="ledger-cta">
          {ds.status.configured ? "Reconnect" : `Connect ${ds.label}`}
        </button>
        {ds.status.configured && (
          <>
            <button type="button" onClick={test} disabled={busy} className="text-[12px] text-copper-300 hover:text-copper-200">
              Test connection
            </button>
            <button type="button" onClick={disconnect} disabled={busy} className="text-[12px] text-ink-400 hover:text-ink-200">
              Disconnect
            </button>
          </>
        )}
        {testResult && (
          <span className="ledger-pill" data-tone={testResult.ok ? "gain" : "loss"}>
            {testResult.message}
          </span>
        )}
      </div>
      {ds.provider === "tradingview" && <TradingViewToolsToggle disabled={!ds.status.configured} />}
    </div>
  );
}
```

In `DataSourceCard` add `{ds.auth === "oauth" && <OAuthControls ds={ds} onChanged={onChanged} />}` right after the `{ds.auth === "none" && (...)}` block, and change the signup link condition from `{keyed && ds.signup_url && (` to `{(keyed || ds.auth === "oauth") && ds.signup_url && (` with the label `{keyed ? "Get a free key ↗" : "Plans ↗"}`. In `DataSourcesPanel` change the filter to `.filter((ds) => ds.provider !== "schwab")`, the heading to `More data sources`, and the subtitle to `Optional providers that run alongside Schwab. TradingView needs an Essential-or-above plan.` Update the JSDoc above the component accordingly.

- [ ] **Step 5: Connections page return toast** — in `frontend/src/pages/settings/ConnectionsSettings.tsx` add `import { useEffect } from "react";` (merge with the existing `useState` import) and `import { useSearchParams } from "react-router-dom";`, then inside `ConnectionsSettings()` after the existing hooks:

```tsx
  const [searchParams, setSearchParams] = useSearchParams();
  const tradingviewReturn = searchParams.get("tradingview");
  useEffect(() => {
    if (!tradingviewReturn) return;
    push(
      tradingviewReturn === "connected"
        ? { kind: "success", text: "TradingView connected." }
        : { kind: "error", text: "TradingView connection was cancelled or denied." },
    );
    void qc.invalidateQueries({ queryKey: ["data-sources"] });
    const next = new URLSearchParams(searchParams);
    next.delete("tradingview");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once per return value
  }, [tradingviewReturn]);
```

- [ ] **Step 6: Regenerate types** — `make schema` (backend), then the container workaround for FE types (the `gen:api` script can't see `../backend/schema.yml` inside the frontend container):

```bash
docker compose cp backend/schema.yml frontend:/app/schema.yml
docker compose exec frontend pnpm exec openapi-typescript /app/schema.yml -o src/api/schema.d.ts
```

- [ ] **Step 7: Run FE tests + lint**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/DataSourcesPanel.test.tsx src/__tests__/ConnectionsSettings.test.tsx src/__tests__/SystemSettings.test.tsx` → PASS. Run: `docker compose exec frontend pnpm run lint` → clean (if `react-hooks/set-state-in-effect` flags the effect, move the toast into a `useEffect` with `setSearchParams` outside via an event handler pattern: read the param in render, and trigger the side effects from a `useEffect` keyed on it exactly as above — the rule targets `useState` setters, which this effect does not call).

- [ ] **Step 8: Commit**

```bash
LEFTHOOK=0 git add frontend/src backend/schema.yml
LEFTHOOK=0 git commit -m "feat(frontend): TradingView OAuth card, AI-tools toggle and consent-return toast"
```

---

### Task 14: E2E API-lane contract — mock connect → test → toggle → disconnect

**Files:**
- Create: `e2e/api/test_tradingview_contract.py`

**Interfaces:**
- Consumes: every endpoint from Tasks 1, 2 and 6 under `MOCK_EXTERNAL=true` (the overlay).

- [ ] **Step 1: Write the test** — create `e2e/api/test_tradingview_contract.py`:

```python
"""TradingView MCP connection — the mock OAuth flow end to end (MOCK_EXTERNAL overlay).

The authorize URL is the app's own callback with a canned code; following it ourselves
stands in for the browser. Everything else is the real code path over canned MCP results.
"""

from __future__ import annotations

import pytest

BASE = "/api/schwab/data-sources/tradingview"


@pytest.mark.integration
def test_tradingview_connect_test_toggle_disconnect(api_client, minimal) -> None:
    r = api_client.get(f"{BASE}/authorize/")
    assert r.status_code == 200
    url = r.json()["url"]
    assert "code=MOCK_OAUTH" in url

    r = api_client.get(f"{BASE}/callback/", params={"code": "MOCK_OAUTH", "state": "mock"})
    assert r.status_code == 302  # httpx does not follow redirects by default
    assert "tradingview=connected" in r.headers["location"]

    r = api_client.get("/api/schwab/data-sources/")
    assert r.status_code == 200
    tv = {d["provider"]: d for d in r.json()["data_sources"]}["tradingview"]
    assert tv["auth"] == "oauth" and tv["status"]["configured"] is True

    r = api_client.post(f"{BASE}/test/")
    assert r.status_code == 200
    assert r.json()["ok"] is True and "tools available" in r.json()["message"]

    r = api_client.patch("/api/settings/", json={"tradingview_tools_enabled": True})
    assert r.status_code == 200 and r.json()["tradingview_tools_enabled"] is True
    try:
        r = api_client.delete(f"{BASE}/")
        assert r.status_code == 200 and r.json()["configured"] is False
        r = api_client.get("/api/schwab/data-sources/")
        assert {d["provider"]: d for d in r.json()["data_sources"]}["tradingview"]["status"]["configured"] is False
    finally:
        api_client.patch("/api/settings/", json={"tradingview_tools_enabled": None})


@pytest.mark.integration
def test_tradingview_callback_rejects_missing_code(api_client, minimal) -> None:
    r = api_client.get(f"{BASE}/callback/", params={"state": "mock"})
    assert r.status_code == 400
    assert r.json()["code"] == "missing_code"
```

- [ ] **Step 2: Run it against the e2e overlay**

Run: `make e2e-up` then `make e2e-one t=api/test_tradingview_contract.py`, then `make e2e-down` (or the equivalent teardown target in the Makefile). Expected: PASS.

- [ ] **Step 3: Commit** (the pre-commit ruff hook cannot lint `e2e/` — that is why the bypass is needed here too)

```bash
LEFTHOOK=0 git add e2e/api/test_tradingview_contract.py
LEFTHOOK=0 git commit -m "test(e2e): TradingView mock connect/test/toggle/disconnect contract"
```

---

### Task 15: Docs + full gates

**Files:**
- Modify: `CLAUDE.md` (app roster bullets for `secrets`/`market`/`ai`; new landmine bullets under "Data sources, predictions & coverage" and "AI providers & capabilities"; the `make e2e` lane list is unchanged)
- Test: `make check` (everything)

- [ ] **Step 1: CLAUDE.md** — add to the `secrets` roster bullet: `TradingView MCP OAuth 2.1 client `tradingview_oauth.py` (dynamic registration, PKCE, lazy lock-guarded refresh)`. Add to the `market` roster bullet: `TradingView MCP transport `services/tradingview_mcp.py` + provider normalizers `services/tradingview.py``. Add to the `ai` roster bullet: `TradingView tool bridge `tools/tradingview.py``. Then add these landmine bullets:

Under **AI providers & capabilities**:

```
- **TradingView `tv_*` tools ride two different toolsets on purpose** — `registry.request_toolset()` (defaults + allowlisted TradingView tools; does ORM/Redis/HTTP) builds the *schemas* on the sync request path (`_resolve_capabilities`, `_apply_investigation_mode`); the providers' async loops keep `default_toolset()`, whose pure `resolve_dynamic` dispatches `tv_<name>` by name. **Never call `request_toolset()`/`tradingview_toolset()` from provider code** (SynchronousOnlyOperation / blocked event loop). Exposure = `SystemSettings.tradingview_tools_enabled` (env default `TRADINGVIEW_TOOLS_ENABLED`) AND connected; the 25-name read-only allowlist in `apps/ai/tools/tradingview.py` is the only source of exposable names (new beta tools stay out until added).
```

Under **Data sources, predictions & coverage**:

```
- **TradingView (official MCP server) is the FIRST fallback** for quotes/bars/news when Schwab is disconnected, and the macro-calendar source ahead of `SEED_MACRO_EVENTS` (`events.fetch_macro`: Finnhub → TradingView → seed; earnings: Finnhub → TradingView). "Configured" = `tradingview.is_connected()` = token present AND no `provider_health` auth-error marker — the marker (1h TTL) is the circuit breaker after a rejected token, so a dead connection stops costing a failing round trip per call. Symbols are `EXCHANGE:TICKER`: the app's `$VIX`/`/ES` spellings map through `INDEX_SYMBOLS`/`FUTURE_SYMBOLS` in `services/tradingview.py`; equities resolve via `search_symbols` (Redis 7d; a miss caches as `""`). Breadth internals (`$ADVN`…) have no TradingView equivalent → empty, never an error. OAuth: a fresh dynamically-registered public client per Connect; per-nonce Redis state carries the PKCE verifier; refresh is **lazy** in `ensure_fresh_token()` under `tradingview:oauth:refresh_lock` (no beat task — don't add one); the transport re-inits on 404 and refresh-retries once on 401. Result shapes are normalized leniently — confirm against the live `tools/list` fixture (spec §9) before trusting a new field.
```

- [ ] **Step 2: Full gates**

Run: `make lint` → clean (ruff, mypy zero-baseline, import-linter, deptry, semgrep rules, FE eslint/tsc/depcruise/type-coverage). Run: `make test` → PASS (coverage floors hold; the new modules are unit-tested at the boundary). Run: `make check-migrations` → clean. Run: `make e2e` → all lanes PASS (schemathesis: the new views are outside the OpenAPI schema, so nothing new is fuzzed; the settings PATCH field is).

- [ ] **Step 3: Commit**

```bash
LEFTHOOK=0 git add CLAUDE.md
LEFTHOOK=0 git commit -m "docs: TradingView MCP integration landmines + roster"
```

---

### Task 16: Live verification (needs the user's TradingView account)

This task cannot be completed by an agent alone; it produces the fixture that pins the real tool shapes and either confirms or falsifies the two known unknowns from the spec.

- [ ] **Step 1: Connect** — with `make dev` running (the `dev` profile so the `tls-proxy` owns `https://127.0.0.1:8000`), open Settings → Connections → TradingView → **Connect TradingView**. Expected: the TradingView consent tab opens; after approval the app tab shows "TradingView connected." and the card reads Connected.
  - If the authorize call answers 502 `tradingview_registration_failed`, the message carries TradingView's reason (most likely the loopback HTTPS redirect URI). Decision point for the user: change `TRADINGVIEW_CALLBACK_URL` to a host TradingView accepts (e.g. `http://localhost:8000/…` via a plain proxy) and re-register; this is not silently worked around.

- [ ] **Step 2: Test** — click **Test connection**. Expected: "Connected — N tools available." (N ≈ 42).

- [ ] **Step 3: Capture the live catalogue into a fixture**

```bash
docker compose exec web uv run python -c "import json; from apps.market.services import tradingview_mcp as m; print(json.dumps(m.list_tools(use_cache=False), indent=2))" > backend/apps/market/tests/fixtures/tradingview_tools_list.json
```

Then, from `make shell`:

```bash
uv run python -c "from apps.market.services import tradingview_mcp as m; import json; print(json.dumps(m.call_tool('get_ohlcv', {'symbol': 'NASDAQ:AAPL', 'interval': '1D', 'count': 3, 'summary': False}), indent=2)); print(json.dumps(m.call_tool('get_symbol_data_batch', {'symbols': ['NASDAQ:AAPL'], 'columns': ['close','change','volume','high','low']}), indent=2)); print(json.dumps(m.call_tool('get_news', {'symbol': 'NASDAQ:AAPL', 'limit': 1}), indent=2)); print(json.dumps(m.call_tool('get_earnings_calendar', {'symbols': ['NASDAQ:AAPL']}), indent=2)); print(json.dumps(m.call_tool('get_economic_calendar', {'countries': ['US']}), indent=2))"
```

- [ ] **Step 4: Reconcile** — compare against the plan's assumptions and adjust in the same commit:
  - `get_ohlcv.inputSchema.properties.interval.enum` vs `_INTERVALS` in `services/tradingview.py` (`"1"`, `"5"`, `"15"`, `"60"`, `"1D"`).
  - Bar field names (`t/o/h/l/c/v`), batch row shape (flat rows vs `s`/`d`), news keys (`id/title/published/provider/storyPath/link`), earnings keys (`symbol/date/time`, estimate names), economic-calendar keys (`title/country/importance/date/forecast/previous`), and the `countries`/`from_date`/`to_date` parameter names of `get_economic_calendar`.
  - Update `MOCK_TOOLS`/`mock_call` in `tradingview_mcp.py` to the real spellings, and add one test per normalizer that loads the captured fixture (e.g. `test_fetch_bars_against_live_fixture`) so future drift is caught.
  - Snapshot check: with Schwab disconnected (or by temporarily forcing `SchwabNotConnectedError`), capture a snapshot and confirm quotes/OHLC/news sections fill from `source="tradingview"` rows and the macro section lists TradingView-sourced events.
  - AI check: toggle "Expose TradingView tools to the AI", run an investigate thread on a profile with `enable_tools`, and confirm `tv_*` tool calls appear in the thread.

- [ ] **Step 5: Commit**

```bash
LEFTHOOK=0 git add backend/apps/market
LEFTHOOK=0 git commit -m "test(market): pin TradingView MCP tool shapes to the live fixture"
```

---

## Self-review against the spec

- §3 Connection → Tasks 1, 2, 3, 4, 6. §4 Transport → Task 5. §5 Provider + §5.1 precedence → Tasks 7, 8, 9. §6 Bridge + §6.1 toggle → Tasks 1, 10, 11, 12. §7 UI → Task 13. §8 Testing → every task carries its tests; e2e in Task 14. §9 Live verification → Task 16. §10 Out of scope → nothing here adds write tools, SSE GET, or `.mcp.json`. §11 Docs → Tasks 1 (feature-flags.md, .env.example) and 15 (CLAUDE.md).
- Names used across tasks: `tradingview_oauth.{discover, register_client, build_authorize_url, consume_oauth_state, exchange_code, refresh, persist_token, load_token, ensure_fresh_token, revoke_and_disconnect, REJECTED_MESSAGE, TradingViewOAuthError, TradingViewTokenRejected}`; `tradingview_mcp.{list_tools, call_tool, probe, reset_state, MOCK_TOOLS, mock_call, TradingViewMCPError, TradingViewNotConnected, TradingViewRateLimited, TradingViewToolError}`; `tradingview.{is_connected, to_tv_symbol, fetch_bars, fetch_quotes, fetch_news, fetch_earnings, fetch_economic_calendar, PROVIDER}`; `apps.ai.tools.tradingview.{TRADINGVIEW_TOOL_ALLOWLIST, TV_PREFIX, tradingview_toolset, resolve_dynamic}`; `registry.request_toolset`; `Toolset.{add_resolver, merge, resolve, dynamic_resolvers}`; views `tv_*` aliases. Each is defined before it is consumed.
