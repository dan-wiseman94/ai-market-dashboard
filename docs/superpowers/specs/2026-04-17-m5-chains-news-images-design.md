# M5 — Option Chains + News + Images: Design

**Status:** approved 2026-04-17
**Milestone:** M5 (per main spec §16)
**Predecessor:** M4 (full threads, tag `m4-full-threads`)
**Successor:** M6 (observer)

## Goal

Round out the snapshot pipeline so that a captured market state can include option chains, financial news, and chart images — both client-captured screenshots ("snap what I'm looking at") and deterministic server-rendered chart PNGs. Add the per-ticker view (`/market/:ticker`) that makes the new data consumable in the live UI as well as inside snapshots.

## Non-goals

- Multiple news providers behind an interface. Single concrete impl (Finnhub) only.
- Per-contract greeks history / option-chain time series. Each fetch is a single JSONB blob.
- Real-time chain streaming. Polled with a 15s Redis cache, same shape as quotes/OHLC.
- Server-rendered chart pool / browser warm-up. Single-shot Playwright launch per render.
- Whitenoise SPA-mode fix. Render route reachable in prod via hash routing on `index.html`.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | All four pieces (chains, news, screenshot, Playwright render) ship in M5 | Each piece touches the snapshot pipeline; landing them together avoids two rounds of pipeline plumbing |
| 2 | Finnhub as the only news provider; no `NewsProvider` abstraction yet | Generous free tier; YAGNI on abstraction until a second provider is needed |
| 3 | `OptionChainSnapshot` = one row per fetch with full chain in JSONB | Chains are read-once, displayed, then stale within 15s; per-contract rows would explode counts (~800 per fetch) for no current query benefit |
| 4 | `lightweight-charts` as the chart library | Spec-specified; smallest bundle (~45kb); first-class candlesticks |
| 5 | Playwright lives in the existing `worker` container, not a separate service | Single-user app, no concurrency pressure; +1 service is YAGNI |
| 6 | Capture button overlays the chart component itself; auto-attaches to next snapshot | The natural moment to capture is "I'm looking at this chart" — composer-first flow is friction |
| 7 | Build `/market/:ticker` page in M5 | Gives chain table and news feed a live home; exercises new fetchers from a real UI |
| 8 | Image bytes stored in `BinaryField` on `SnapshotImage` model (not FileField / object storage) | Single-user, low volume (~200KB × few per snapshot); transactional with snapshot row; simple backup |

## Data model

Three new models, all with migrations.

### `OptionChainSnapshot` (in `apps/market/models.py`)

```python
class OptionChainSnapshot(models.Model):
    ticker = models.CharField(max_length=16, db_index=True)
    expiries = models.JSONField(default=list)   # list of "YYYY-MM-DD"
    payload = models.JSONField()                # full normalized chain blob
    fetched_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["ticker", "-fetched_at"])]
```

`payload` shape:

```json
{
  "underlying_last": "521.30",
  "expiries": {
    "2026-04-25": {
      "calls": [{"strike": "515", "bid": "7.20", "ask": "7.30", "last": "7.25",
                 "volume": 1234, "oi": 5678, "delta": "0.72", "gamma": "0.04",
                 "theta": "-0.12", "vega": "0.18", "iv": "18.4"}, ...],
      "puts":  [...]
    },
    "2026-05-16": {...}
  }
}
```

### `NewsItem` (in `apps/market/models.py`)

```python
class NewsItem(models.Model):
    provider = models.CharField(max_length=16)              # "finnhub"
    external_id = models.CharField(max_length=64, db_index=True)
    ticker = models.CharField(max_length=16, db_index=True, blank=True, default="")
    headline = models.CharField(max_length=512)
    summary = models.TextField(blank=True, default="")
    url = models.URLField(max_length=1024)
    source = models.CharField(max_length=64, blank=True, default="")
    published_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "external_id"], name="uniq_news_provider_id"),
        ]
        indexes = [models.Index(fields=["ticker", "-published_at"])]
```

`ticker = ""` for general/market-wide news.

### `SnapshotImage` (in `apps/snapshots/models.py`)

```python
class SnapshotImage(models.Model):
    KIND_CHOICES = [("client_capture", "Client capture"), ("server_render", "Server render")]

    snapshot = models.ForeignKey(Snapshot, on_delete=models.CASCADE,
                                 related_name="images", null=True, blank=True)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    data = models.BinaryField()
    mime_type = models.CharField(max_length=32, default="image/png")
    caption = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
```

Snapshot FK is nullable so client captures can be staged before snapshot creation, then attached on capture.

### `SnapshotSection` extension

No schema change. Existing `chain` / `news` / `image` kind values get fetcher implementations.

`image` section's `payload` shape: `{"image_ids": [<SnapshotImage.id>, ...]}`. One section can carry multiple images (e.g. SPY 5m + TSLA 1h on a single snapshot).

## Service layer

Existing `apps/snapshots/services.py` becomes `apps/snapshots/services/__init__.py`. Logic split out into focused modules.

### `apps/market/services/chain.py`

```python
def fetch_chain(ticker: str, *, expiries: int = 4, strikes_around_atm: int = 10) -> dict:
    """Fetch + cache + persist an option chain for `ticker`.

    Cache key:  market:chain:<ticker>:<params_hash>  TTL 15s.
    On cache miss: call Schwab, normalize to flat shape, persist OptionChainSnapshot,
    return payload. On cache hit: return cached payload (no DB write).
    """
```

Schwab returns nested `callExpDateMap[<expiry>:<dte>][<strike>][0]`. Normalization flattens to the model `payload` shape.

### `apps/market/services/news.py`

```python
def fetch_news(tickers: list[str], *, lookback_hours: int = 24, limit: int = 15) -> list[dict]:
    """Fetch + dedup + return latest news across `tickers` plus market-wide.

    Per-ticker call: GET /company-news?symbol=<T>&from=<date>&to=<date>
    Plus one general call:  GET /news?category=general
    Upsert each item into NewsItem keyed by (provider, external_id) for dedup.
    Cache per-ticker results in Redis (market:news:<ticker>:<lookback>) for 5min.
    Return the latest `limit` items, newest first.
    """
```

Finnhub API key stored in `ApiCredential(kind="finnhub")` (encrypted, same django-cryptography pattern as Schwab tokens).

### `apps/snapshots/services/screenshot.py`

```python
def attach_client_image(snapshot_id: int | None, png_bytes: bytes,
                        caption: str = "") -> SnapshotImage:
    """Validate PNG magic bytes (max 5MB), persist as SnapshotImage(kind='client_capture').

    snapshot_id=None → staged image (snapshot FK null), retrievable via ?staged=true.
    """
```

### `apps/snapshots/services/render.py`

```python
def render_chart_png(ticker: str, timeframe: str, bars: int,
                     *, snapshot_id: int) -> SnapshotImage:
    """Drive Playwright headless chromium to navigate /render/chart?... and screenshot.

    URL = settings.RENDER_BASE_URL + render path + query params.
    Wait for body[data-render-ready='true'] (15s timeout).
    Screenshot the #chart-root element only (not full viewport).
    Persist as SnapshotImage(kind='server_render', snapshot_id=...).
    """
```

### `apps/snapshots/services/__init__.py` `_FETCHERS` extension

Three new entries:

```python
"chain": lambda *, watchlist_tickers, **_: {
    "data": fetch_chain(watchlist_tickers[0] if watchlist_tickers else "SPY"),
},
"news":  lambda *, watchlist_tickers, **_: {
    "data": {"items": fetch_news(list(watchlist_tickers))},
},
"image": lambda *, snapshot_id, watchlist_tickers, ohlc_ticker, ohlc_timeframe, ohlc_bars, **_: {
    "data": {"image_ids": [
        render_chart_png(
            ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
            ohlc_timeframe, ohlc_bars, snapshot_id=snapshot_id,
        ).id,
    ]},
},
```

The `image` fetcher needs `snapshot_id` — `capture_for_existing` is updated to pass it through the lambda kwargs.

### Failure modes

- **Chain**: Schwab 401 → re-raise; section marked failed. Empty chain (illiquid ticker) → succeed with empty `expiries`.
- **News**: Finnhub 503/429 → retry once with 1s backoff, then fail section.
- **Screenshot upload**: malformed PNG (no `\x89PNG\r\n\x1a\n` header) → 400 to client.
- **Render**: timeout on `data-render-ready` selector (15s) → fail section with `"render timeout: chart did not signal ready within 15s"`.

## Frontend

### Components (new)

- **`Chart.tsx`** (~150 LOC). Imperative `lightweight-charts` wrapper. Props: `ticker`, `timeframe`, `bars`, optional `onReady`. Fetches OHLC from existing M2 endpoint, paints candles, calls `onReady` once painted.
- **`ChartCaptureButton.tsx`**. Floating button overlaying the chart's top-right. Click → `html2canvas(chartContainerRef.current)` → POST `/api/snapshots/images/?staged=true` → toast + write image ID to `localStorage.staged_image_ids` (JSON array).
- **`OptionChainTable.tsx`**. Expiry tabs across the top; per-expiry table with calls left of strike, puts right. ATM row highlighted. Greeks columns toggle-able.
- **`NewsFeed.tsx`**. Vertical list of 15 items, headline + source + relative time, click opens `url` in new tab.

### Pages (new)

- **`/market/:ticker`** (`MarketTickerPage.tsx`). Layout: `<Chart>` (top, with `<ChartCaptureButton>`), `<OptionChainTable>` (middle), `<NewsFeed>` (bottom). URL params `?timeframe=5m&bars=120` control the chart.
- **`/render/chart`** (`RenderChart.tsx`). Reads `ticker`, `timeframe`, `bars` from query. Renders `<Chart>` full-viewport, no chrome. On `Chart` `onReady` callback, sets `document.body.dataset.renderReady = "true"`. Same component works in dev (React Router path) and prod (hash route on `index.html`).

### Snapshot composer extension

`SnapshotComposerPage.tsx` adds:
- Three new section checkboxes: **Option chain**, **News**, **Charts** (image kind).
- Below the checkboxes: thumbnail strip showing staged client captures (read from `localStorage.staged_image_ids`); each thumbnail has × to drop. On capture, IDs are POSTed alongside the snapshot create call and `localStorage` is cleared.

### New deps

`frontend/package.json`:
- `lightweight-charts ^4.2.0` (MIT)
- `html2canvas ^1.4.1` (MIT)

## AI payload serialization

`apps/snapshots/serializer.py` extensions per spec §5.3.

### Chain serializer

Filters payload to the front-month expiry + the next monthly expiry, ±10 strikes around ATM per expiry (per spec §5.3). Output:

```
## Option chain — SPY (underlying $521.30)

### Expiry 2026-04-25 (8d)
| strike | call bid | call ask | call Δ | call IV | put bid | put ask | put Δ | put IV |
|--------|----------|----------|--------|---------|---------|---------|-------|--------|
| 515    | 7.20     | 7.30     | 0.72   | 18.4    | 0.95    | 1.00    | -0.28 | 19.1   |
| ...    |
```

Token estimate: ~1.5k per typical 2-expiry chain. On token-budget prune: collapses to single expiry.

### News serializer

```
## News (last 24h)

- **2026-04-17 09:12** — *Reuters* — Fed minutes show split on rate path
  Brief one-line summary if non-empty.
- ...
```

Cap 15 items, newest first.

### Image serializer

For each image ID in `payload["image_ids"]`, loads `SnapshotImage.data` bytes, base64-encodes, emits provider-shaped image blocks via:

```python
def build_image_blocks(image_ids: list[int], provider_name: str) -> list[dict]:
    # claude  → {"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}}
    # openai  → {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
```

Image blocks emitted alongside the text section in the same user message:

```
## Charts attached
- chart_1: SPY 5m, 60 bars (server-rendered)
- chart_2: TSLA 1h, 100 bars (your screenshot)

[image blocks follow]
```

### Token-budget pruning order (updates spec §5.4)

1. Drop chain (largest single section)
2. Drop older news (keep newest 5)
3. Drop older OHLC bars
4. Images stay (pruning images defeats the purpose of attaching them)

### Partial-failure markers

Per spec §5.5, each new section uses the existing convention:

```
## Option chain
_(unavailable: Schwab returned 401)_

## News
_(unavailable: Finnhub returned 503)_
```

## Worker image + Playwright

### Dockerfile changes (`backend/Dockerfile`)

New build target `worker-base` extending `runtime`:

```dockerfile
FROM runtime AS worker-base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

RUN uv add playwright && playwright install chromium --with-deps
```

Image grows ~600MB → ~1.1GB. Acceptable for desktop / single-user.

### Compose changes (`compose.yaml`)

`worker` service uses the new target:

```yaml
worker:
  build:
    context: .
    dockerfile: backend/Dockerfile
    target: worker-base
```

`web` and `beat` keep the smaller `runtime` target (no chromium needed there).

### Playwright invocation (`apps/snapshots/services/render.py`)

```python
from playwright.async_api import async_playwright

async def _render_async(url: str) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 1200, "height": 700})
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await page.wait_for_selector("body[data-render-ready='true']", timeout=15000)
        chart_handle = await page.locator("#chart-root").element_handle()
        png = await chart_handle.screenshot(type="png")
        await browser.close()
        return png

def render_chart_png(...) -> SnapshotImage:
    png = async_to_sync(_render_async)(url)
    return SnapshotImage.objects.create(snapshot_id=snapshot_id,
                                        kind="server_render", data=png, ...)
```

Single launch per render (no pool) — single-user, low volume; ~1.5s startup overhead per call is fine.

### `RENDER_BASE_URL` setting

- **Dev**: `http://frontend:5173` — Vite serves `/render/chart` via React Router, history-fallback already on.
- **Prod**: `http://web:8000/static/index.html` + hash routing — `RenderChart.tsx` accepts both `/render/chart?...` (dev) and `#/render/chart?...` (prod). Avoids needing Whitenoise SPA-mode fix as part of M5.

### Concurrency / cold-start

- One browser launch per render call. No pool.
- First `make dev` after this lands rebuilds worker (~3–5min for chromium download). CLAUDE.md gets a note.

## API surface (new endpoints)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/market/chain/?ticker=SPY` | Live chain (cache-backed) |
| GET | `/api/market/news/?tickers=SPY,AAPL&lookback=24` | Live news list |
| POST | `/api/snapshots/images/?staged=true` | Upload client capture; multipart PNG |
| GET | `/api/snapshots/images/?staged=true` | List currently-staged client captures |
| GET | `/api/snapshots/images/<id>/` | Serve image bytes (token-auth) |

`POST /api/snapshots/` (existing) is extended to accept an optional `image_ids: [int]` to attach staged images to the new snapshot.

## Routes (new frontend)

| Path | Component |
|---|---|
| `/market/:ticker` | `MarketTickerPage.tsx` |
| `/render/chart` | `RenderChart.tsx` (deterministic; no chrome) |

## Testing

### Backend unit (pure logic)

- `apps/market/tests/test_chain.py` — Schwab-shaped fixture → `_normalize_chain()` flat shape; ATM filter math; expiry filtering.
- `apps/market/tests/test_news.py` — Finnhub fixture → `NewsItem` upsert + dedup on `(provider, external_id)`; lookback window filter.
- `apps/snapshots/tests/test_serializer_chain.py` — known chain → expected markdown table.
- `apps/snapshots/tests/test_serializer_news.py` — list of news items → expected markdown.
- `apps/snapshots/tests/test_serializer_image.py` — image_ids → Claude blocks; same → OpenAI blocks.
- `apps/snapshots/tests/test_token_budget.py` — extend: budget guard prunes chain first, then news, then OHLC; never images.

### Backend integration (DRF + Celery eager + respx for HTTP mocks)

- `apps/market/tests/test_chain_endpoint.py` — `GET /api/market/chain/?ticker=SPY` with Schwab mocked.
- `apps/market/tests/test_news_endpoint.py` — `GET /api/market/news/?tickers=SPY,AAPL` with Finnhub mocked; dedup test.
- `apps/snapshots/tests/test_image_upload.py` — POST PNG bytes; `?staged=true` filter; bad PNG → 400.
- `apps/snapshots/tests/test_capture_includes_chain_news.py` — full `capture()` with `includes=["quotes","chain","news"]`; assert all three sections persist.

### Playwright render (separate marker)

- `apps/snapshots/tests/test_render_chart.py` — `@pytest.mark.integration`; skipped by default. Boots Playwright against the live frontend, hits `/render/chart?ticker=SPY&timeframe=5m&bars=10` (OHLC API mocked at the schwab boundary), waits for `data-render-ready`, asserts PNG bytes start with `\x89PNG`. Skips with clear message if Playwright not installed.

### Frontend (vitest + RTL)

- `Chart.test.tsx` — renders without crashing on mock OHLC; calls `onReady` after render.
- `ChartCaptureButton.test.tsx` — click triggers POST (mock fetch); writes to localStorage on success.
- `OptionChainTable.test.tsx` — renders given mock chain payload; ATM strike highlighted.
- `NewsFeed.test.tsx` — renders 15 items, sorted newest first.
- `MarketTickerPage.test.tsx` — renders all three sub-components without errors.
- `RenderChart.test.tsx` — accepts URL params, sets `data-render-ready` after Chart's `onReady`.

### Smoke verification (end of plan)

- Frontend routes 200: `/`, `/profiles`, `/snapshot`, `/threads`, `/settings`, `/watchlists`, `/costs`, `/market/SPY`, `/render/chart?ticker=SPY&timeframe=5m&bars=10`.
- Backend endpoints work with stub credentials: `/api/market/chain/`, `/api/market/news/`, `/api/snapshots/images/` upload/serve.
- One end-to-end `capture(includes=["quotes","chain","news","image"])` succeeds; verify `SnapshotImage.data` non-empty bytes.

### Cold rebuild + tag

- `docker compose down -v && docker compose build --no-cache && docker compose up -d`
- `make check` green
- `git tag m5-chains-news-images`

## Out of scope (deferred to later milestones)

- Multi-provider news abstraction (until 2nd provider needed)
- Per-contract option-chain history / greeks time series
- Server-rendered chart pool / browser warmup (single-shot launches)
- Whitenoise SPA-mode fix (worked around with hash route)
- Object storage for images
- Per-ticker chart presets / saved layouts
