# Local LLM Settings Overhaul — Design

**Date:** 2026-05-28
**Status:** Approved (brainstorming → ready for implementation plan)
**Scope:** Make the "local" AI provider's settings coherent and usable.

## Problem

The local provider (`apps/ai/providers/local.py` — an `OpenAIProvider` pointed at a
user-supplied `base_url`, so it talks to Ollama / LM Studio / vLLM via the OpenAI-compatible
API) is configured through the same `ProviderCard` as Claude/OpenAI. Four things make its
settings confusing or broken, plus one underlying reachability bug:

1. **Empty model dropdown.** `catalog.py` has zero `ModelInfo` entries for `local`, so
   `ModelSelect` silently falls back to free-text. The user must hand-type a model id
   (e.g. `llama3`) every time, with no validation.
2. **Base URL looks optional but is required.** `LocalProvider.__init__` raises if it's
   blank, but the field renders like an optional text input and a bad URL only fails at
   run time (inside a Celery task), not at save time.
3. **No connection test.** Nothing pings the endpoint or lists its models, so a typo'd URL
   or unreachable server is invisible until a thread run fails.
4. **Cost caps are inert.** `cost.py` hardcodes local to `$0.00`, so the daily/monthly cap
   inputs and the `$` cost meter on the local card do nothing.
5. **Underlying reachability bug.** The UI placeholder is
   `http://host.docker.internal:11434/v1`, but **no compose file maps `host.docker.internal`**
   (`extra_hosts: ["host.docker.internal:host-gateway"]` is absent from `web`/`worker`/`beat`).
   On a Linux host that hostname does not resolve inside containers, so a local endpoint on
   the host is unreachable regardless of what the user types.

## Goals

- A model dropdown for local that lists the models the endpoint actually serves.
- A Base URL that is clearly required, validated, and reachable.
- A single "Test connection" action that verifies reachability + OpenAI-compatibility +
  returns the model list.
- No misleading cost UI for local.
- Local endpoints reachable from the backend on Linux.

## Non-goals (YAGNI)

- Dynamic per-model context-window / token-budget detection.
- A generation ("can it actually complete?") test beyond listing models.
- Real cost tracking for local (decided: hide the cost UI instead).
- Moving AI provider config off the `/api/schwab/...` URL prefix. It is a pre-existing
  oddity (provider config lives in the `secrets`/schwab app), but relocating it is a
  breaking change touching `config/urls.py` include-ordering, the frontend api layer, and
  tests — out of scope for this work.

## Key insight

`GET {base_url}/v1/models` does triple duty: it proves the endpoint is **reachable**
(connection test), proves it speaks the **OpenAI dialect** (compatibility test), and returns
the **installed models** (dropdown source). "Test connection," "validate URL," and "populate
models" are therefore one feature, not three. The probe reuses the provider's own
`AsyncOpenAI` client so the test cannot drift from what real runs do.

## Approach (chosen: "Persisted probe")

The discovered model list is persisted on `ProviderConfig` so the dropdown is populated on
every page load, with a "synced Xm ago" label and a manual refresh. (Alternatives considered:
ephemeral in-memory discovery — rejected because the dropdown would empty on every reload;
and a maximal variant with dynamic context-windows + generation test + auto-probe-on-type —
rejected as YAGNI for a single-user box.)

## Design

### 1. Infra — host-gateway mapping

Add to the `web`, `worker`, and `beat` services in `compose.yaml` (the base file, so the
prod overlay inherits it; the e2e overlay stays mocked and does not need it):

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

This is load-bearing: without it nothing about local works on Linux. It is harmless on
Docker Desktop (Mac/Windows), where the hostname already resolves.

### 2. Data model — `ProviderConfig` (+ migration `0005`)

Add two additive fields to `apps/secrets/models.py`:

- `discovered_models = models.JSONField(default=list, blank=True)` — list of model-id
  strings most recently returned by the endpoint.
- `models_synced_at = models.DateTimeField(null=True, blank=True)` — timestamp of the last
  successful probe.

New migration `apps/secrets/migrations/0005_providerconfig_model_discovery.py` (next after the
existing `0004`). Both fields are additive with safe defaults — forward/backward reversible,
no data backfill, no locking concern. Only `local` populates them today; harmless for other
providers.

### 3. Backend — provider `list_models()`

Add to `OpenAIProvider` (inherited unchanged by `LocalProvider`):

```python
async def list_models(self) -> list[str]:
    from apps.core.mocks import is_mock_mode
    if is_mock_mode():
        return ["local-7b", "local-13b"]   # canned, mirrors run() short-circuit
    resp = await self._client.models.list()
    return sorted(m.id for m in resp.data)
```

Declare an optional `list_models` on the `Provider` protocol in `providers/base.py`. Claude
need not implement it for this work (only local/openai use it). Reusing `self._client` means
the probe exercises the same auth + base_url path as a real run.

### 4. Backend — probe endpoint

Action on the existing provider-config viewset (`apps/secrets/views.py`):

`POST /api/schwab/providers/{provider}/probe/`

- **Request body (optional):** `{ "base_url": "...", "api_key_write": "..." }`. When present,
  the backend persists those onto the row *first*, then probes the saved row — so the stored
  `discovered_models` always corresponds to the saved `base_url` (one source of truth).
- **Behavior:** construct the provider via `get_provider(provider, api_key=cfg.api_key,
  base_url=cfg.base_url)`, call `list_models()` with a short (~5s) timeout. On success, save
  `discovered_models` + `models_synced_at = now()`.
- **Response:**
  - success → `200 {"ok": true, "models": [...], "synced_at": "<iso8601>"}`
  - connection failure → `200 {"ok": false, "error": "<friendly message>"}` (an *expected*
    outcome, not a server error, so the frontend renders it without HTTP-error handling)
  - missing/blank `base_url` (for local) → `400`
- The api key is never echoed in the response (consistent with the existing
  `api_key_present` pattern).

### 5. Backend — friendly error mapping

The probe catches SDK/transport exceptions and maps them to actionable text:

| Failure | Message |
|---|---|
| connection refused / DNS failure | `Couldn't reach <url>. Is the server running? On Linux use http://host.docker.internal:<port>/v1.` |
| HTTP 401 / 403 | `Endpoint requires an API key.` |
| non-OpenAI / unexpected response shape | `Reached the server, but it doesn't respond like an OpenAI-compatible API.` |
| timeout | `Timed out reaching <url>.` |

The short client timeout also guarantees a hung endpoint can't block the Django worker.

### 6. Frontend — `ProviderCard.tsx` (local branch)

- **Base URL:** rendered as required (visual marker), validated non-empty + URL-shaped with
  an inline error that blocks save; clearer hint naming Ollama/LM Studio and the
  `host.docker.internal` form.
- **"Test connection" button** next to Base URL → calls the probe with the current form
  values → shows a spinner, then green `Connected — N models · synced just now` or the red
  friendly error.
- **Model dropdown (`ModelSelect`):** sourced from `config.discovered_models` for local,
  always including the currently-saved `default_model`, and keeping the existing "Custom…"
  free-text escape hatch. Empty list shows the hint `Test the connection to list available
  models.`
- **Auto-populate once:** on mount, if `provider === "local"` AND `base_url` is set AND
  `discovered_models` is empty, fire the probe silently to fill the dropdown. Auto-probe
  errors stay silent; only the explicit button surfaces errors. Implemented so it does not
  trip the `react-hooks/set-state-in-effect` eslint rule (state set from the async
  resolution / data-hook, not synchronously in the effect body).
- **Cost caps:** daily/monthly inputs and the `$` cost meter are hidden for local and
  replaced with a muted note: `Runs on your machine — no API cost.`

### 7. Frontend — plumbing

- `api/ai.ts`: add `discovered_models: string[]` and `models_synced_at: string | null` to
  the `ProviderConfig` type; add `probeProvider(provider, { base_url, api_key_write })`
  returning `{ ok, models, synced_at, error }`.
- `components/settings/ModelSelect.tsx`: accept an optional `models?: string[]` prop used for
  local; the catalog-driven path for claude/openai is unchanged.
- A `useProbeProvider()` mutation hook alongside `hooks/useProviderConfigs.ts`, invalidating
  the provider-config query on success so `discovered_models` / `models_synced_at` refresh.

### 8. Security considerations

The probe makes a backend HTTP request to a user-supplied `base_url`. This is **not** an SSRF
risk to defend against here, and SSRF private-IP filtering would be actively wrong: the entire
purpose is to reach the user's own machine (localhost / `host.docker.internal` / LAN), which
are precisely the private addresses such filters block. The security model of this app is
network isolation, not authentication — it's a single-user desktop dashboard bound to
`127.0.0.1`, and the user configuring the URL is the operator. Do **not** add an SSRF
allow/deny filter to this code path; it would break the feature without adding protection in
this threat model. The api key continues to be encrypted at rest and write-only over the API.

## Testing

**Backend unit:**
- `OpenAIProvider.list_models()` returns sorted ids (mock `self._client.models.list()`).
- mock-mode short-circuit returns the canned list without touching the SDK.

**Backend API (`apps/secrets/tests/`):**
- probe success persists `discovered_models` + `models_synced_at` and returns the list.
- probe connection failure returns `200 {ok: false, error}` (SDK mocked to raise) with a
  mapped message.
- probe with missing `base_url` for local → `400`.
- api key never appears in the probe response.

**Frontend (`vitest` + Testing Library):**
- local card renders Base URL + "Test connection", hides the cost-cap inputs/meter.
- clicking "Test connection" calls the probe and populates the dropdown from the result.
- a probe error renders the friendly message.
- `ModelSelect` honors the `models` prop (lists provided ids + "Custom…").

**E2E:** the existing `e2e/fixtures/seed_minimal.py` already seeds a local `ProviderConfig`;
the mock-mode `list_models()` canned list lets the api/ui lanes exercise discovery without a
real endpoint. No new lane required.

## Files touched

**Backend**
- `compose.yaml` — `extra_hosts` on `web`/`worker`/`beat`
- `backend/apps/secrets/models.py` — `+discovered_models`, `+models_synced_at`
- `backend/apps/secrets/migrations/0005_providerconfig_model_discovery.py` — new
- `backend/apps/secrets/serializers.py` — expose the two new fields read-only
- `backend/apps/secrets/views.py` — `probe` action
- `backend/apps/ai/providers/openai.py` — `list_models()`
- `backend/apps/ai/providers/base.py` — optional `list_models` on the protocol
- `backend/apps/secrets/tests/…`, `backend/apps/ai/tests/…` — tests

**Frontend**
- `frontend/src/api/ai.ts` — type + `probeProvider`
- `frontend/src/hooks/useProviderConfigs.ts` (or new `useProbeProvider.ts`)
- `frontend/src/components/settings/ProviderCard.tsx` — test button, required+validated URL,
  hidden caps, dropdown source, auto-populate
- `frontend/src/components/settings/ModelSelect.tsx` — `models` prop
- frontend tests
