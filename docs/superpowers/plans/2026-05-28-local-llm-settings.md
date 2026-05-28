# Local LLM Settings Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the "local" AI provider's settings coherent — live model discovery (doubling as a connection test), a required/validated Base URL, no misleading cost UI, and a backend that can actually reach a local endpoint on Linux.

**Architecture:** One backend network call — `AsyncOpenAI(base_url, api_key).models.list()` via a new `OpenAIProvider.list_models()` — proves reachability + OpenAI-compatibility + returns the installed models. A `probe` action on the existing `ProviderConfigViewSet` persists the discovered list onto `ProviderConfig`, so the frontend dropdown is populated from stored data and refreshed on demand. A compose `host-gateway` mapping makes `host.docker.internal` resolve inside the backend containers.

**Tech Stack:** Django 6 + DRF, Celery, `openai` SDK (AsyncOpenAI), Postgres; React + TypeScript + TanStack Query + Vitest; Docker Compose.

**Spec:** `docs/superpowers/specs/2026-05-28-local-llm-settings-design.md`

---

## Conventions for every task

- **Append the repo's commit trailer** to every commit message:
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- If a commit is blocked by a lefthook container-path error, prefix it with `LEFTHOOK=0`.
- **Running tests against this worktree:** the `docker compose exec` commands below assume a
  running stack that mounts *this* worktree's code. If you are sharing the main dev stack,
  run the equivalent via a one-off container that mounts this worktree (reuse the prebuilt
  images + a throwaway db/redis) rather than against the shared stack — otherwise you test
  the wrong code. Container WORKDIR is `/app/backend`, so pytest paths drop the `backend/`
  prefix.
- TDD throughout: failing test → minimal implementation → green → commit.

---

## File Structure

**Backend**
- `compose.yaml` — add `extra_hosts: ["host.docker.internal:host-gateway"]` to `web`/`worker`/`beat`.
- `backend/apps/secrets/models.py` — `ProviderConfig` gains `discovered_models`, `models_synced_at`.
- `backend/apps/secrets/migrations/0005_providerconfig_model_discovery.py` — new (generated).
- `backend/apps/secrets/serializers.py` — expose the two fields read-only.
- `backend/apps/secrets/views.py` — `probe` action + `_friendly_probe_error` helper.
- `backend/apps/ai/providers/openai.py` — `list_models()` method (inherited by `LocalProvider`).
- `backend/apps/ai/tests/test_list_models.py` — new.
- `backend/apps/secrets/tests/test_provider_config_discovery.py` — new (model defaults).
- `backend/apps/secrets/tests/test_provider_probe.py` — new (endpoint).
- `backend/apps/secrets/tests/test_provider_config_endpoints.py` — add serializer-exposure test.

**Frontend**
- `frontend/src/api/ai.ts` — `ProviderConfig` type + `ProbeResult` + `probeProvider()`.
- `frontend/src/hooks/useProviderConfigs.ts` — `useProbeProvider()`.
- `frontend/src/components/settings/ModelSelect.tsx` — optional `models` prop.
- `frontend/src/components/settings/ProviderCard.tsx` — local-branch overhaul.
- `frontend/src/__tests__/ModelSelect.test.tsx` — add `models`-prop test.
- `frontend/src/__tests__/ProviderCard.test.tsx` — update mock + add local tests.

> **Note on `base.py`:** We intentionally do **not** add `list_models` to the
> `@runtime_checkable` `Provider` protocol. Doing so would make
> `isinstance(claude_provider, Provider)` return `False` (Claude has no `list_models`) and
> could break the factory/tests. `list_models` lives on `OpenAIProvider`, and the probe
> restricts discovery to the `local`/`openai` providers that have it.

---

## Task 1: Infra — host-gateway mapping

**Files:**
- Modify: `compose.yaml` (services `web`, `worker`, `beat`)

- [ ] **Step 1: Add `extra_hosts` to `web`**

In `compose.yaml`, inside the `web:` service, add the block right after `env_file: .env` (line ~39):

```yaml
    env_file: .env
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

- [ ] **Step 2: Add `extra_hosts` to `worker`**

Inside the `worker:` service, after its `env_file: .env`:

```yaml
    env_file: .env
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

- [ ] **Step 3: Add `extra_hosts` to `beat`**

Inside the `beat:` service, after its `env_file: .env`:

```yaml
    env_file: .env
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

- [ ] **Step 4: Verify the compose merge resolves the mapping**

Run: `docker compose config | grep -A1 extra_hosts`
Expected: three `extra_hosts:` blocks each followed by `- host.docker.internal:host-gateway`.

- [ ] **Step 5: (If a stack is running) recreate the backend containers and confirm resolution**

Run: `docker compose up -d --force-recreate web worker beat`
Then: `docker compose exec web getent hosts host.docker.internal`
Expected: a line resolving `host.docker.internal` to the host-gateway IP (non-empty output).
(Recreate is required — a plain `restart` does not re-read `extra_hosts`.)

- [ ] **Step 6: Commit**

```bash
git add compose.yaml
git commit -m "feat(infra): map host.docker.internal in web/worker/beat

Without host-gateway, host.docker.internal does not resolve inside
containers on Linux, so a local OpenAI-compatible endpoint on the host
is unreachable. Required for the local AI provider to work."
```

---

## Task 2: Backend — `ProviderConfig` discovery fields + migration

**Files:**
- Test: `backend/apps/secrets/tests/test_provider_config_discovery.py` (create)
- Modify: `backend/apps/secrets/models.py:70` (after `supports_tools`/before caps is fine; placement shown below)
- Create: `backend/apps/secrets/migrations/0005_providerconfig_model_discovery.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/secrets/tests/test_provider_config_discovery.py`:

```python
import pytest

from apps.secrets.models import ProviderConfig


@pytest.mark.django_db
def test_discovery_fields_default_empty():
    pc = ProviderConfig.objects.create(provider="local")
    assert pc.discovered_models == []
    assert pc.models_synced_at is None


@pytest.mark.django_db
def test_discovery_fields_roundtrip():
    pc = ProviderConfig.objects.create(
        provider="local", discovered_models=["llama3", "mistral"]
    )
    pc.refresh_from_db()
    assert pc.discovered_models == ["llama3", "mistral"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/secrets/tests/test_provider_config_discovery.py -v`
Expected: FAIL — `TypeError`/`FieldError` (no `discovered_models` field) or `AttributeError`.

- [ ] **Step 3: Add the fields to the model**

In `backend/apps/secrets/models.py`, inside `ProviderConfig`, add these two fields immediately after the `supports_tools` field (line 60):

```python
    supports_tools = models.BooleanField(default=True)
    discovered_models = models.JSONField(default=list, blank=True)
    models_synced_at = models.DateTimeField(null=True, blank=True)
```

- [ ] **Step 4: Generate the migration**

Run: `docker compose exec web python manage.py makemigrations secrets_app`
Expected: creates `backend/apps/secrets/migrations/0005_providerconfig_model_discovery.py`.
Verify its contents match (regenerate/rename if Django picks a different suffix):

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('secrets_app', '0004_providerconfig_supports_tools'),
    ]

    operations = [
        migrations.AddField(
            model_name='providerconfig',
            name='discovered_models',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='providerconfig',
            name='models_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
```

- [ ] **Step 5: Apply and run the test to verify it passes**

Run: `docker compose exec web python manage.py migrate secrets_app`
Then: `docker compose exec web pytest apps/secrets/tests/test_provider_config_discovery.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/secrets/models.py backend/apps/secrets/migrations/0005_providerconfig_model_discovery.py backend/apps/secrets/tests/test_provider_config_discovery.py
git commit -m "feat(secrets): add discovered_models + models_synced_at to ProviderConfig"
```

---

## Task 3: Backend — `OpenAIProvider.list_models()`

**Files:**
- Test: `backend/apps/ai/tests/test_list_models.py` (create)
- Modify: `backend/apps/ai/providers/openai.py` (add method to `OpenAIProvider`)

- [ ] **Step 1: Write the failing test**

Create `backend/apps/ai/tests/test_list_models.py`:

```python
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from apps.ai.providers.openai import OpenAIProvider


def _provider_with_ids(ids):
    p = OpenAIProvider(api_key="x")  # real AsyncOpenAI is constructed then replaced
    client = MagicMock()
    client.with_options.return_value = client
    client.models.list = AsyncMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(id=i) for i in ids])
    )
    p._client = client
    return p, client


def test_list_models_returns_sorted_ids():
    p, client = _provider_with_ids(["mistral", "llama3", "codellama"])
    result = asyncio.run(p.list_models())
    assert result == ["codellama", "llama3", "mistral"]
    client.with_options.assert_called_once_with(timeout=10.0)


def test_list_models_honors_mock_mode(monkeypatch):
    monkeypatch.setattr("apps.core.mocks.is_mock_mode", lambda: True)
    p, client = _provider_with_ids(["ignored"])
    result = asyncio.run(p.list_models())
    assert result == ["local-7b", "local-13b"]
    client.models.list.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/ai/tests/test_list_models.py -v`
Expected: FAIL — `AttributeError: 'OpenAIProvider' object has no attribute 'list_models'`.

- [ ] **Step 3: Implement `list_models`**

In `backend/apps/ai/providers/openai.py`, add the method to `OpenAIProvider` by replacing the
seam between the end of `run()` and `_resolve_toolset`:

Find:
```python
        except Exception as exc:
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")


def _resolve_toolset():
```

Replace with:
```python
        except Exception as exc:
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")

    async def list_models(self, *, timeout: float = 10.0) -> list[str]:
        """List model ids the endpoint serves (GET /v1/models).

        Doubles as a reachability + OpenAI-compatibility probe. Honors
        MOCK_EXTERNAL like run() so e2e/mock runs never touch the network.
        """
        from apps.core.mocks import is_mock_mode

        if is_mock_mode():
            return ["local-7b", "local-13b"]
        page = await self._client.with_options(timeout=timeout).models.list()
        return sorted(m.id for m in page.data)


def _resolve_toolset():
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/ai/tests/test_list_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/ai/providers/openai.py backend/apps/ai/tests/test_list_models.py
git commit -m "feat(ai): OpenAIProvider.list_models() for endpoint model discovery"
```

---

## Task 4: Backend — serializer exposes discovery fields (read-only)

**Files:**
- Test: `backend/apps/secrets/tests/test_provider_config_endpoints.py` (append)
- Modify: `backend/apps/secrets/serializers.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/secrets/tests/test_provider_config_endpoints.py`:

```python
@pytest.mark.django_db
def test_provider_config_exposes_discovery_fields(api):
    ProviderConfig.objects.create(
        provider="local", base_url="http://x:11434/v1", discovered_models=["llama3"]
    )
    r = api.get("/api/schwab/providers/")
    assert r.status_code == 200
    row = next(c for c in r.json() if c["provider"] == "local")
    assert row["discovered_models"] == ["llama3"]
    assert "models_synced_at" in row


@pytest.mark.django_db
def test_discovery_fields_are_read_only(api):
    ProviderConfig.objects.create(provider="local", base_url="http://x:11434/v1")
    r = api.patch(
        "/api/schwab/providers/local/",
        {"discovered_models": ["injected"]},
        format="json",
    )
    assert r.status_code == 200
    pc = ProviderConfig.objects.get(provider="local")
    assert pc.discovered_models == []  # write ignored
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/secrets/tests/test_provider_config_endpoints.py -k discovery -v`
Expected: FAIL — `KeyError`/`StopIteration` (fields absent from response).

- [ ] **Step 3: Add the fields to the serializer**

In `backend/apps/secrets/serializers.py`, extend `Meta.fields` and add `read_only_fields`:

```python
    class Meta:
        model = ProviderConfig
        fields: ClassVar = [
            "provider",
            "base_url",
            "default_model",
            "enabled",
            "supports_vision",
            "supports_tools",
            "daily_cost_cap_usd",
            "monthly_cost_cap_usd",
            "api_key_present",
            "api_key_write",
            "discovered_models",
            "models_synced_at",
        ]
        read_only_fields: ClassVar = ["discovered_models", "models_synced_at"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/secrets/tests/test_provider_config_endpoints.py -k discovery -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/secrets/serializers.py backend/apps/secrets/tests/test_provider_config_endpoints.py
git commit -m "feat(secrets): expose discovered_models + models_synced_at (read-only)"
```

---

## Task 5: Backend — `probe` action + friendly errors

**Files:**
- Test: `backend/apps/secrets/tests/test_provider_probe.py` (create)
- Modify: `backend/apps/secrets/views.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/secrets/tests/test_provider_probe.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import openai
import pytest
from rest_framework.test import APIClient

from apps.secrets.models import ProviderConfig


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_probe_success_persists_and_returns_models(api):
    ProviderConfig.objects.create(provider="local", base_url="http://x:11434/v1")
    fake = SimpleNamespace(list_models=AsyncMock(return_value=["llama3", "mistral"]))
    with patch("apps.secrets.views.get_provider", return_value=fake):
        r = api.post("/api/schwab/providers/local/probe/", {}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["models"] == ["llama3", "mistral"]
    assert body["synced_at"]
    pc = ProviderConfig.objects.get(provider="local")
    assert pc.discovered_models == ["llama3", "mistral"]
    assert pc.models_synced_at is not None


@pytest.mark.django_db
def test_probe_persists_base_url_from_body(api):
    ProviderConfig.objects.create(provider="local", base_url="")
    fake = SimpleNamespace(list_models=AsyncMock(return_value=["a"]))
    with patch("apps.secrets.views.get_provider", return_value=fake) as gp:
        r = api.post(
            "/api/schwab/providers/local/probe/",
            {"base_url": "http://new:11434/v1"},
            format="json",
        )
    assert r.status_code == 200
    assert ProviderConfig.objects.get(provider="local").base_url == "http://new:11434/v1"
    assert gp.call_args.kwargs["base_url"] == "http://new:11434/v1"


@pytest.mark.django_db
def test_probe_connection_error_is_friendly(api):
    ProviderConfig.objects.create(provider="local", base_url="http://x:11434/v1")
    err = openai.APIConnectionError(request=httpx.Request("GET", "http://x"))
    fake = SimpleNamespace(list_models=AsyncMock(side_effect=err))
    with patch("apps.secrets.views.get_provider", return_value=fake):
        r = api.post("/api/schwab/providers/local/probe/", {}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "Couldn't reach" in body["error"]


@pytest.mark.django_db
def test_probe_missing_base_url_is_400(api):
    ProviderConfig.objects.create(provider="local", base_url="")
    r = api.post("/api/schwab/providers/local/probe/", {}, format="json")
    assert r.status_code == 400
    assert r.json()["ok"] is False


@pytest.mark.django_db
def test_probe_does_not_leak_api_key(api):
    ProviderConfig.objects.create(provider="local", base_url="http://x:11434/v1")
    fake = SimpleNamespace(list_models=AsyncMock(return_value=["a"]))
    with patch("apps.secrets.views.get_provider", return_value=fake):
        r = api.post(
            "/api/schwab/providers/local/probe/",
            {"api_key_write": "secret-xyz"},
            format="json",
        )
    assert "secret-xyz" not in r.text
    assert "api_key" not in r.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/secrets/tests/test_provider_probe.py -v`
Expected: FAIL — 404 (no `probe` route) on all tests.

- [ ] **Step 3: Implement the probe action + helper**

In `backend/apps/secrets/views.py`, add imports near the top (after the existing imports):

```python
import openai
from asgiref.sync import async_to_sync
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ai.providers import get_provider
```

Replace the `ProviderConfigViewSet` class body with:

```python
class ProviderConfigViewSet(viewsets.ModelViewSet):
    queryset = ProviderConfig.objects.all()
    serializer_class = ProviderConfigSerializer
    lookup_field = "provider"

    @action(detail=True, methods=["post"], url_path="probe")
    def probe(self, request, provider=None):
        """List models from the endpoint — also a reachability/compat test.

        Persists any base_url/api_key in the body first, so the stored
        model list always corresponds to the saved endpoint.
        """
        cfg = self.get_object()
        base_url = request.data.get("base_url")
        api_key_write = request.data.get("api_key_write")
        dirty = False
        if base_url is not None:
            cfg.base_url = base_url
            dirty = True
        if api_key_write:
            cfg.api_key = api_key_write
            dirty = True
        if dirty:
            cfg.save()

        if not cfg.base_url:
            return Response({"ok": False, "error": "Base URL is required."}, status=400)

        if cfg.provider not in ("local", "openai"):
            return Response(
                {"ok": False, "error": "Model discovery isn't supported for this provider."}
            )

        provider_obj = get_provider(
            cfg.provider, api_key=cfg.api_key, base_url=cfg.base_url
        )
        try:
            models = async_to_sync(provider_obj.list_models)(timeout=5.0)
        except Exception as exc:  # noqa: BLE001 — mapped to a friendly message
            return Response({"ok": False, "error": _friendly_probe_error(exc, cfg.base_url)})

        cfg.discovered_models = models
        cfg.models_synced_at = timezone.now()
        cfg.save(update_fields=["discovered_models", "models_synced_at", "updated_at"])
        return Response(
            {"ok": True, "models": models, "synced_at": cfg.models_synced_at.isoformat()}
        )


def _friendly_probe_error(exc: Exception, base_url: str) -> str:
    # APITimeoutError subclasses APIConnectionError — check it first.
    if isinstance(exc, openai.APITimeoutError):
        return f"Timed out reaching {base_url}."
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "Endpoint requires an API key."
    if isinstance(exc, openai.APIConnectionError):
        return (
            f"Couldn't reach {base_url}. Is the server running? "
            "On Linux use http://host.docker.internal:<port>/v1."
        )
    return "Reached the server, but it doesn't respond like an OpenAI-compatible API."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/secrets/tests/test_provider_probe.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/secrets/views.py backend/apps/secrets/tests/test_provider_probe.py
git commit -m "feat(secrets): probe endpoint lists endpoint models + persists them"
```

---

## Task 6: Frontend — api types, `probeProvider`, `useProbeProvider`

**Files:**
- Modify: `frontend/src/api/ai.ts`
- Modify: `frontend/src/hooks/useProviderConfigs.ts`

- [ ] **Step 1: Extend the `ProviderConfig` type and add the probe API**

In `frontend/src/api/ai.ts`, replace the `ProviderConfig` type and add `ProbeResult` +
`probeProvider` (place the function after `upsertProviderConfig`):

```typescript
export type ProviderConfig = {
  provider: "claude" | "openai" | "local";
  base_url: string;
  default_model: string;
  enabled: boolean;
  supports_vision: boolean;
  daily_cost_cap_usd: string;
  monthly_cost_cap_usd: string | null;
  api_key_present: boolean;
  discovered_models: string[];
  models_synced_at: string | null;
};

export type ProbeResult = {
  ok: boolean;
  models?: string[];
  synced_at?: string | null;
  error?: string;
};

export const probeProvider = (
  provider: string,
  body: { base_url?: string; api_key_write?: string },
) => apiPost<ProbeResult>(`/api/schwab/providers/${provider}/probe/`, body);
```

- [ ] **Step 2: Add the `useProbeProvider` hook**

In `frontend/src/hooks/useProviderConfigs.ts`, update the import and append the hook:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchProviderConfigs, probeProvider, upsertProviderConfig } from "@/api/ai";
```

```typescript
export function useProbeProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      provider,
      body,
    }: {
      provider: string;
      body: { base_url?: string; api_key_write?: string };
    }) => probeProvider(provider, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provider-configs"] });
    },
  });
}
```

- [ ] **Step 3: Type-check**

Run: `docker compose exec frontend pnpm exec tsc --noEmit`
Expected: no new errors. (Existing `ProviderConfig` consumers still compile; new fields are
additive. Mock factories in tests get fixed in Tasks 7–8.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/ai.ts frontend/src/hooks/useProviderConfigs.ts
git commit -m "feat(frontend): probeProvider api + useProbeProvider hook + config types"
```

---

## Task 7: Frontend — `ModelSelect` accepts an explicit `models` list

**Files:**
- Test: `frontend/src/__tests__/ModelSelect.test.tsx` (append)
- Modify: `frontend/src/components/settings/ModelSelect.tsx`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/__tests__/ModelSelect.test.tsx`:

```tsx
describe("ModelSelect — explicit models", () => {
  it("lists the explicit models prop instead of the catalog", () => {
    render(
      <ModelSelect provider="local" value="" models={["llama3", "mistral"]} onChange={() => {}} />,
    );
    expect(screen.getByRole("option", { name: "llama3" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "mistral" })).toBeInTheDocument();
    // catalog (claude) models are NOT shown
    expect(screen.queryByRole("option", { name: "Claude Sonnet 4.6" })).not.toBeInTheDocument();
  });

  it("falls back to the Custom input when the value isn't in the explicit list", () => {
    render(
      <ModelSelect provider="local" value="custom-x" models={["llama3"]} onChange={() => {}} />,
    );
    expect(screen.getByLabelText("Custom model id")).toHaveValue("custom-x");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/ModelSelect.test.tsx`
Expected: FAIL — `llama3`/`mistral` options not found (prop ignored).

- [ ] **Step 3: Implement the `models` prop**

Replace the body of `frontend/src/components/settings/ModelSelect.tsx`:

```tsx
import { useAiModels } from "@/hooks/useAiModels";
import type { AiModel } from "@/api/ai";

const CUSTOM = "__custom__";

type Props = {
  provider: string;
  value: string;
  onChange: (model: string) => void;
  id?: string;
  describedBy?: string;
  models?: string[]; // explicit id list (used for local discovery); overrides the catalog
};

export default function ModelSelect({ provider, value, onChange, id, describedBy, models: explicit }: Props) {
  const { data } = useAiModels(provider);
  const options: { id: string; name: string }[] = explicit
    ? explicit.map((m) => ({ id: m, name: m }))
    : (data?.models ?? [])
        .filter((m: AiModel) => m.provider === provider)
        .map((m) => ({ id: m.id, name: m.name }));
  const known = options.some((o) => o.id === value);
  const showCustom = !known;

  return (
    <div className="space-y-2">
      <select
        id={id}
        aria-describedby={describedBy}
        value={showCustom ? CUSTOM : value}
        onChange={(e) => onChange(e.target.value === CUSTOM ? "" : e.target.value)}
        className="ledger-input w-full py-2"
      >
        {options.map((o) => (
          <option key={o.id} value={o.id}>{o.name}</option>
        ))}
        <option value={CUSTOM}>Custom…</option>
      </select>
      {showCustom && (
        <input
          aria-label="Custom model id"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="e.g. llama-3.1-70b"
          className="ledger-input w-full py-2 font-mono text-[12px]"
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/ModelSelect.test.tsx`
Expected: PASS (all, including the 3 pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/ModelSelect.tsx frontend/src/__tests__/ModelSelect.test.tsx
git commit -m "feat(frontend): ModelSelect accepts an explicit models list"
```

---

## Task 8: Frontend — `ProviderCard` local overhaul

**Files:**
- Test: `frontend/src/__tests__/ProviderCard.test.tsx` (update mock + add tests)
- Modify: `frontend/src/components/settings/ProviderCard.tsx` (full rewrite)

- [ ] **Step 1: Update the existing test harness, then write the failing local tests**

In `frontend/src/__tests__/ProviderCard.test.tsx`:

(a) Add a probe mock fn and include `useProbeProvider` in the existing `useProviderConfigs`
mock. Replace the mock fns block + the `vi.mock("@/hooks/useProviderConfigs", …)` call:

```tsx
const mockMutate = vi.fn();
const mockProbeMutate = vi.fn();
const mockUseProviderConfigs = vi.fn();
const mockUseAiUsage = vi.fn();
const mockUseCostsCaps = vi.fn();
const mockUseAiModels = vi.fn();
const mockPush = vi.fn();

vi.mock("@/hooks/useProviderConfigs", () => ({
  useProviderConfigs: () => mockUseProviderConfigs(),
  useUpsertProviderConfig: () => ({ mutate: mockMutate, isPending: false }),
  useProbeProvider: () => ({ mutate: mockProbeMutate, isPending: false }),
}));
```

(b) Update the `cfg()` factory to include the new fields:

```tsx
function cfg(o: Partial<ProviderConfig> = {}): ProviderConfig {
  return {
    provider: "claude", base_url: "", default_model: "claude-sonnet-4-6",
    enabled: true, supports_vision: true, daily_cost_cap_usd: "10.00",
    monthly_cost_cap_usd: null, api_key_present: true,
    discovered_models: [], models_synced_at: null, ...o,
  };
}
```

(c) Append a new describe block with the local-specific tests:

```tsx
describe("ProviderCard — local provider", () => {
  it("hides the cost caps and shows the no-cost note for local", () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", api_key_present: false, default_model: "llama3",
                   base_url: "http://x:11434/v1", discovered_models: ["llama3"] })],
    });
    render(<ProviderCard provider="local" />);
    expect(screen.queryByLabelText("Daily cap (USD)")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Monthly cap (USD)")).not.toBeInTheDocument();
    expect(screen.getByText(/no API cost/i)).toBeInTheDocument();
  });

  it("auto-probes on mount when base_url is set but no models discovered", () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", api_key_present: false,
                   base_url: "http://x:11434/v1", discovered_models: [] })],
    });
    render(<ProviderCard provider="local" />);
    expect(mockProbeMutate).toHaveBeenCalledWith(
      { provider: "local", body: {} },
    );
  });

  it("Test connection sends current base_url and shows the result", async () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", api_key_present: false, default_model: "llama3",
                   base_url: "http://x:11434/v1", discovered_models: ["llama3"] })],
    });
    mockProbeMutate.mockImplementation((_args, opts) =>
      opts?.onSuccess?.({ ok: true, models: ["llama3", "mistral"], synced_at: "now" }),
    );
    render(<ProviderCard provider="local" />);
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    const call = mockProbeMutate.mock.calls.find((c) => c[1] !== undefined);
    expect(call?.[0]).toEqual({
      provider: "local",
      body: { base_url: "http://x:11434/v1", api_key_write: undefined },
    });
    expect(screen.getByText(/Connected — 2 models found/i)).toBeInTheDocument();
  });

  it("shows the friendly error when the probe reports ok:false", async () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", api_key_present: false, default_model: "llama3",
                   base_url: "http://x:11434/v1", discovered_models: ["llama3"] })],
    });
    mockProbeMutate.mockImplementation((_args, opts) =>
      opts?.onSuccess?.({ ok: false, error: "Couldn't reach http://x:11434/v1." }),
    );
    render(<ProviderCard provider="local" />);
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(screen.getByText(/Couldn't reach/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/ProviderCard.test.tsx`
Expected: FAIL — no "Test connection" button, caps still present, etc.

- [ ] **Step 3: Rewrite `ProviderCard.tsx`**

Replace the entire contents of `frontend/src/components/settings/ProviderCard.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { useProviderConfigs, useUpsertProviderConfig, useProbeProvider } from "@/hooks/useProviderConfigs";
import { useAiUsage } from "@/hooks/useAiUsage";
import { useCostsCaps } from "@/hooks/useCosts";
import { useToast } from "@/hooks/useToast";
import type { ProviderConfig } from "@/api/ai";
import Field from "@/components/settings/Field";
import Toggle from "@/components/ui/Toggle";
import ModelSelect from "@/components/settings/ModelSelect";
import CapMeter from "@/components/settings/CapMeter";

type ProviderId = "claude" | "openai" | "local";
const LABEL: Record<ProviderId, string> = { claude: "Claude", openai: "OpenAI", local: "Local" };
const DEFAULT_MODEL: Record<ProviderId, string> = {
  claude: "claude-sonnet-4-6", openai: "gpt-5", local: "",
};

type Draft = {
  api_key_write?: string;
  default_model?: string;
  daily_cost_cap_usd?: string;
  monthly_cost_cap_usd?: string;
  base_url?: string;
};

export default function ProviderCard({ provider }: { provider: ProviderId }) {
  const { data: configs } = useProviderConfigs();
  const { data: usage } = useAiUsage();
  const { data: caps } = useCostsCaps();
  const upsert = useUpsertProviderConfig();
  const probe = useProbeProvider();
  const { push } = useToast();
  const [draft, setDraft] = useState<Draft>({});
  const [probeMsg, setProbeMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const isLocal = provider === "local";
  const cfg = configs?.find((c) => c.provider === provider);
  const capRow = caps?.find((r) => r.provider === provider);
  const spent = usage?.today?.[provider] ?? "0";
  const enabled = cfg?.enabled ?? true;

  const model = draft.default_model ?? cfg?.default_model ?? DEFAULT_MODEL[provider];
  const daily = draft.daily_cost_cap_usd ?? cfg?.daily_cost_cap_usd ?? "10.00";
  const monthly = draft.monthly_cost_cap_usd ?? cfg?.monthly_cost_cap_usd ?? "";
  const baseUrl = draft.base_url ?? cfg?.base_url ?? "";
  const apiKey = draft.api_key_write ?? "";
  const discovered = cfg?.discovered_models ?? [];

  const dailyNum = Number(daily);
  const monthlyNum = monthly === "" ? null : Number(monthly);
  const dailyInvalid = daily.trim() === "" || Number.isNaN(dailyNum) || dailyNum < 0;
  const monthlyInvalid = monthly !== "" && (Number.isNaN(monthlyNum as number) || (monthlyNum as number) < 0);
  const modelInvalid = model.trim() === "";
  const baseUrlInvalid = isLocal && baseUrl.trim() === "";
  const invalid = isLocal
    ? modelInvalid || baseUrlInvalid
    : dailyInvalid || monthlyInvalid || modelInvalid;

  const set = (patch: Draft) => setDraft((d) => ({ ...d, ...patch }));

  // Populate the local model list once when we have an endpoint but no models yet.
  // Auto-probe is silent (no status message); only the explicit button surfaces errors.
  const autoProbed = useRef(false);
  useEffect(() => {
    if (isLocal && !autoProbed.current && baseUrl.trim() !== "" && discovered.length === 0) {
      autoProbed.current = true;
      probe.mutate({ provider, body: {} });
    }
  }, [isLocal, baseUrl, discovered.length, provider, probe]);

  const runProbe = () => {
    if (baseUrlInvalid) return;
    setProbeMsg(null);
    probe.mutate(
      { provider, body: { base_url: baseUrl, api_key_write: apiKey || undefined } },
      {
        onSuccess: (res) => {
          setProbeMsg(
            res.ok
              ? { ok: true, text: `Connected — ${(res.models ?? []).length} models found.` }
              : { ok: false, text: res.error ?? "Connection failed." },
          );
        },
        onError: (e) => setProbeMsg({ ok: false, text: (e as Error).message }),
      },
    );
  };

  const toggleEnabled = (next: boolean) => {
    upsert.mutate(
      { provider, body: { enabled: next } },
      {
        onSuccess: () => push({ kind: "info", text: `${LABEL[provider]} ${next ? "enabled" : "disabled"}.` }),
        onError: (e) => push({ kind: "error", text: (e as Error).message }),
      },
    );
  };

  const save = () => {
    if (invalid) return;
    const body: Partial<ProviderConfig> & { api_key_write?: string } = isLocal
      ? { default_model: model, base_url: baseUrl }
      : {
          default_model: model,
          daily_cost_cap_usd: daily,
          monthly_cost_cap_usd: monthly === "" ? null : monthly,
        };
    if (apiKey) body.api_key_write = apiKey; // omit when blank → serializer keeps the stored key
    upsert.mutate(
      { provider, body },
      {
        onSuccess: () => { setDraft({}); push({ kind: "success", text: `${LABEL[provider]} settings saved.` }); },
        onError: (e) => push({ kind: "error", text: (e as Error).message }),
      },
    );
  };

  return (
    <div className="ledger-surface p-5" data-testid={`provider-card-${provider}`}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className={`inline-block h-2 w-2 rounded-full ${enabled ? "bg-copper-400" : "bg-ink-600"}`} aria-hidden />
          <h3 className="font-display text-[1.05rem] text-ink-50">{LABEL[provider]}</h3>
          <span className="ledger-pill" data-tone={cfg?.api_key_present ? "copper" : undefined}>
            {cfg?.api_key_present ? "key set ••••" : "no key"}
          </span>
        </div>
        <div className="flex items-center gap-4">
          {!isLocal && (
            <span className="font-mono text-[11px] text-ink-400 tabular-nums">today ${Number(spent).toFixed(4)}</span>
          )}
          <Toggle checked={enabled} onChange={toggleEnabled} label={`${LABEL[provider]} enabled`} disabled={upsert.isPending} />
        </div>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field
            label={`${LABEL[provider]} API key`}
            hint={cfg?.api_key_present ? "A key is stored. Paste to replace; leave blank to keep." : isLocal ? "Optional — most local servers ignore it." : "Paste your API key."}
          >
            {({ id, describedBy }) => (
              <input
                id={id} aria-describedby={describedBy} type="password" value={apiKey}
                placeholder={cfg?.api_key_present ? "•••••••• (unchanged)" : "sk-…"}
                onChange={(e) => set({ api_key_write: e.target.value })}
                className="ledger-input w-full py-2 font-mono text-[12px]"
              />
            )}
          </Field>
        </div>

        {isLocal && (
          <div className="sm:col-span-2">
            <Field
              label="Base URL"
              hint="Your OpenAI-compatible server (Ollama, LM Studio, vLLM). On Linux: http://host.docker.internal:<port>/v1"
              error={baseUrlInvalid ? "Base URL is required for local." : undefined}
            >
              {({ id, describedBy }) => (
                <div className="space-y-2">
                  <input
                    id={id} aria-describedby={describedBy} value={baseUrl} aria-required="true"
                    placeholder="http://host.docker.internal:11434/v1"
                    onChange={(e) => set({ base_url: e.target.value })}
                    className="ledger-input w-full py-2 font-mono text-[12px]"
                  />
                  <div className="flex items-center gap-3">
                    <button
                      type="button" className="ledger-cta"
                      onClick={runProbe}
                      disabled={baseUrlInvalid || probe.isPending}
                    >
                      {probe.isPending ? "Testing…" : "Test connection"}
                    </button>
                    {probeMsg && (
                      <span className={`text-[12px] ${probeMsg.ok ? "text-copper-300" : "text-loss"}`}>
                        {probeMsg.text}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </Field>
          </div>
        )}

        <Field
          label="Default model"
          hint={isLocal && discovered.length === 0 ? "Test the connection to list available models." : undefined}
          error={modelInvalid ? "Pick or enter a model." : undefined}
        >
          {({ id, describedBy }) => (
            <ModelSelect provider={provider} value={model} id={id} describedBy={describedBy}
              models={isLocal ? discovered : undefined}
              onChange={(m) => set({ default_model: m })} />
          )}
        </Field>

        {!isLocal && (
          <>
            <Field label="Daily cap (USD)" hint="Hard stop — runs blocked past this."
                   error={dailyInvalid ? "Enter a non-negative number." : undefined}>
              {({ id, describedBy }) => (
                <input id={id} aria-describedby={describedBy} inputMode="decimal" value={daily}
                  onChange={(e) => set({ daily_cost_cap_usd: e.target.value })}
                  className="ledger-input w-full py-2 tabular-nums" />
              )}
            </Field>

            <Field label="Monthly cap (USD)" hint="Blank = no monthly limit."
                   error={monthlyInvalid ? "Enter a non-negative number or leave blank." : undefined}>
              {({ id, describedBy }) => (
                <input id={id} aria-describedby={describedBy} inputMode="decimal" value={monthly} placeholder="none"
                  onChange={(e) => set({ monthly_cost_cap_usd: e.target.value })}
                  className="ledger-input w-full py-2 tabular-nums" />
              )}
            </Field>
          </>
        )}
      </div>

      {isLocal ? (
        <p className="mt-5 border-t border-rule-soft pt-4 text-[11px] text-ink-400">
          Runs on your machine — no API cost.
        </p>
      ) : (
        capRow && (
          <div className="mt-5 space-y-2 border-t border-rule-soft pt-4">
            <CapMeter label="Daily" cap={capRow.daily.cap} spent={capRow.daily.spent} pct={capRow.daily.pct} />
            {capRow.monthly && (
              <CapMeter label="Monthly" cap={capRow.monthly.cap} spent={capRow.monthly.spent} pct={capRow.monthly.pct} />
            )}
          </div>
        )
      )}

      <div className="mt-5">
        <button type="button" className="ledger-cta" onClick={save} disabled={upsert.isPending || invalid}>
          {upsert.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/ProviderCard.test.tsx`
Expected: PASS (all pre-existing claude tests + the 4 new local tests).

- [ ] **Step 5: Lint (catch the set-state-in-effect rule + unused imports)**

Run: `docker compose exec frontend pnpm run lint`
Expected: no errors. (The auto-probe effect calls `probe.mutate`, not a synchronous
`setState`, so `react-hooks/set-state-in-effect` does not fire.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/settings/ProviderCard.tsx frontend/src/__tests__/ProviderCard.test.tsx
git commit -m "feat(frontend): local provider card — model discovery, test connection, no cost UI"
```

---

## Task 9: Full verification + docs

**Files:**
- Modify: `CLAUDE.md` (Non-obvious conventions)

- [ ] **Step 1: Run the full backend + frontend suites for touched areas**

Run: `docker compose exec web pytest apps/secrets apps/ai -q`
Expected: PASS (no regressions).
Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/ProviderCard.test.tsx src/__tests__/ModelSelect.test.tsx`
Expected: PASS.

- [ ] **Step 2: Lint both sides**

Run: `docker compose exec web ruff check . && docker compose exec web ruff format --check .`
Run: `docker compose exec frontend pnpm run lint`
Expected: clean (ty remains advisory — ignore its `unresolved-attribute` noise).

- [ ] **Step 3: Document the new conventions**

In `CLAUDE.md`, under "## Non-obvious conventions", add this bullet (near the local/provider
bullets):

```markdown
- **Local provider needs `host.docker.internal` mapped + lists its own models.** `compose.yaml` maps `extra_hosts: ["host.docker.internal:host-gateway"]` on `web`/`worker`/`beat` so the backend can reach a host-run OpenAI-compatible server on Linux (auto on Docker Desktop, absent on Linux without this). The local **model dropdown is discovered, not cataloged**: `POST /api/schwab/providers/<provider>/probe/` calls `OpenAIProvider.list_models()` (`GET /v1/models`) — a single call that connection-tests, compatibility-tests, and persists `ProviderConfig.discovered_models` + `models_synced_at`. The frontend sources the local dropdown from `discovered_models`. Cost caps/meters are hidden for local (cost is hardcoded $0 in `cost.py`). Do **not** add SSRF private-IP filtering to the probe — local endpoints *are* on localhost/private addresses by design.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document local provider host-gateway + model-discovery probe"
```

---

## Self-Review

**1. Spec coverage:**
- Empty model dropdown → Tasks 3 (`list_models`), 5 (probe persists), 7 (`ModelSelect` prop), 8 (card sources `discovered_models`). ✓
- Base URL required + validated → Task 8 (`baseUrlInvalid`, `aria-required`, error). ✓
- No connection test → Task 5 (probe) + Task 8 ("Test connection" button). ✓
- Cost caps meaningless → Task 8 (hidden for local + note). ✓
- host.docker.internal reachability bug → Task 1. ✓
- Persisted discovery (Approach B) → Task 2 (fields) + Task 5 (persist) + Task 8 (auto-populate + load from config). ✓
- Friendly error mapping → Task 5 (`_friendly_probe_error`). ✓
- Security note (no SSRF filter) → Task 9 doc bullet. ✓
- Tests (backend unit/API, frontend) → Tasks 3, 4, 5, 7, 8. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every test step shows the test and the exact run command + expected result. ✓

**3. Type/name consistency:**
- `discovered_models` / `models_synced_at` identical across model (T2), migration (T2), serializer (T4), probe (T5), api type (T6), card (T8). ✓
- `probeProvider(provider, body)` signature matches `useProbeProvider` mutationFn (T6) and both call sites in `ProviderCard` (T8). ✓
- `ProbeResult` (`ok`, `models?`, `synced_at?`, `error?`) matches backend probe responses (T5) and the card's `res.ok`/`res.models`/`res.error` reads (T8). ✓
- `list_models(*, timeout=…)` defined in T3 matches `async_to_sync(provider_obj.list_models)(timeout=5.0)` in T5 and the `timeout=10.0` default asserted in T3's test. ✓
- `ModelSelect` `models?: string[]` prop (T7) matches `models={isLocal ? discovered : undefined}` (T8). ✓
