# Provider-Neutral UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose every provider/model/structured-output knob and every AI output's provider attribution in the frontend, on the ledger design system, with the small backend additions that make those flows complete (catalog defaults, vendor guards, attribution stamps, eval provider setting, manual eval trigger).

**Architecture:** Backend adds read-only facts (`defaults`, `max_payload_tokens`, `ai_run`, `ai` stamps), one shared vendor guard (`apps/ai/catalog.py::foreign_model_error`) used by three serializers, one `SystemSettings` knob, and one queued Celery task behind `POST /api/aieval/runs/`. Frontend adds a `components/ai/` primitive set (`ProviderSelect`, `ModelFacts`, `AiTargetPicker`, `AiAttribution`, `CapabilityHint`, `ModeBadges`) plus a `useCatalog()` hook that is the only source of model defaults, then rebuilds the Providers/System settings, Profiles, Schedules, observer timeline, thread detail and Scorecard eval surfaces on those primitives.

**Tech Stack:** Django 5 / DRF / drf-spectacular, Celery, pytest-django; React 19, TanStack Query 5, Tailwind (ledger tokens in `frontend/src/styles/globals.css`), vitest + Testing Library; pnpm 11 on the host.

**Spec:** `docs/superpowers/specs/2026-09-20-provider-neutral-ui-design.md`

## Global Constraints

- Work happens in the worktree `/home/dan/ledger/.claude/worktrees/provider-neutral-structured-output` on branch `feat/provider-neutral-ui`. Never `cd` to `/home/dan/ledger`. Frontend parallel tasks (F2–F7) run in their own git worktrees branched from the F1 commit and are merged back by the orchestrator.
- **Backend harness** (the dev stack mounts the main checkout; tests run against the worktree through a compose override that already exists at `/tmp/claude-1000/-home-dan-ledger/28e4fe18-1309-45f6-bf71-c618b9253ad8/scratchpad/wt-override.yaml`). Shell state does not persist between tool calls, so every command is written out in full. In this plan the placeholders below stand for these literal prefixes — expand them, do not define variables:
  - `$PYTEST` = `docker compose -f /home/dan/ledger/compose.yaml -f /tmp/claude-1000/-home-dan-ledger/28e4fe18-1309-45f6-bf71-c618b9253ad8/scratchpad/wt-override.yaml run --rm --no-deps --entrypoint "" web uv run pytest -p no:randomly -q --no-header`
  - `$RUN` = `docker compose -f /home/dan/ledger/compose.yaml -f /tmp/claude-1000/-home-dan-ledger/28e4fe18-1309-45f6-bf71-c618b9253ad8/scratchpad/wt-override.yaml run --rm --no-deps --entrypoint ""`
  - `$WT` = `/home/dan/ledger/.claude/worktrees/provider-neutral-structured-output`

  `--entrypoint ""` (an empty string, quoted on the command line) skips the image entrypoint, which would otherwise run `manage.py migrate` against the dev DB with this branch's new migrations. Test paths are relative to `/app/backend` (container WORKDIR), e.g. `$PYTEST apps/ai/tests/test_catalog.py`. Lint/type tools need `-w /app`: `$RUN -w /app web uv run ruff check backend`, `$RUN -w /app web uv run ruff format --check backend`, `$RUN -w /app web uv run mypy`, `$RUN -w /app web uv run lint-imports`, `$RUN -w /app web uv run deptry .`. `makemigrations`: `$RUN web uv run python manage.py makemigrations <app> -n <name>` (writes into the worktree because `backend/` is bind-mounted). Semgrep rules: `docker run --rm -v "$WT:/src" -w /src semgrep/semgrep semgrep scan --error --quiet --config tools/semgrep/rules backend/`. Only one pytest run at a time (they share the `test_` database).
- **Frontend harness** runs on the host (node 22, pnpm 11): `cd $WT/frontend && pnpm install --frozen-lockfile --prefer-offline` once per worktree, then `pnpm exec vitest run --project unit <files>`, `pnpm lint` (eslint + tsc), `pnpm test:cov`, `pnpm depcruise`, `pnpm type-coverage`. `pnpm gen:api` works on the host (it fails only inside the frontend container).
- The host has no `lefthook`; commit with `LEFTHOOK=0 git commit ...`. Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Conventional prefixes: `feat(ai):`, `feat(frontend):`, `fix(...)`, `docs:`.
- Never run a Bash command whose text mentions `.env` (a PreToolUse hook rejects it); read `.env.example` with the Read tool.
- Code comments and docstrings are present-tense invariants. No "was", "legacy", "now supports", milestone tags, origin stories.
- `ruff C901` complexity ≤ 15; no `assert` in shipped code; never log an API key; mypy zero baseline.
- Frontend: `src/api` must not import from `src/pages` or `src/components` (dependency-cruiser). Reach for `Field`, `Toggle`, `SettingsSection`, `Skeleton`/`SkeletonRows`, `EmptyState`, toasts (`useToast().push`). No `slate-*` / `emerald-*` / `rose-*` utility colours on touched pages — use `ink-*`, `copper-*`, `gain-*`, `loss-*`, `ledger-*` classes. Model ids render in `font-mono`. Provider display names: Claude / OpenAI / Local.
- Preserve every selector listed in each task's "Preserved" line (e2e and unit tests pin them).
- A new component under `frontend/src/components/` (root) or `components/settings/` needs a co-located `*.stories.tsx` (`storyCoverage.test.ts` ratchets the storyless count). `components/ai/` and `pages/` are exempt.
- Two smoke tests render pages with minimal fixtures: `__tests__/testids/rows.test.tsx` renders `SchedulesPage` with a schedule lacking `mode/structured/use_batch/consensus/investigate/override_*` and a fetch mock that returns `[]` for every other URL, and `__tests__/SchedulesPage.fireMode.test.tsx` renders it with **no QueryClientProvider** and `vi.mock`s for `@/hooks/useSchedules` and `@/hooks/useProfiles` only. New code on that page must tolerate undefined fields, and any new hook it calls (`useCatalog`/`useAiModels`, `useProviderConfigs`, `useUpdateSchedule`) must be added to the fireMode test's mocks.
- Ids and defaults: catalog defaults are `claude-opus-5` (Claude) and `gpt-5.6-sol` (OpenAI); Local has none. `TradingProfile` flag defaults: `enable_tools=False`, `enable_thinking=False`, `thinking_budget=8000`, `enable_memory=False`, `enable_coach=True`, `active=True`.

## Execution topology

1. **B1 → B7** sequentially in this worktree (they share one Postgres test database); B6 (schema + gates) runs last, after B7.
2. **F1** in this worktree (every frontend task depends on it).
3. **F2, F3, F4, F5, F6, F7** in parallel, each in an isolated worktree branched from the F1 commit; each owns a disjoint file set (listed per task) and commits on its branch; the orchestrator merges the branches back.
4. **F8** integration gates + docs in this worktree.

---

### Task B1: Catalog — `is_foreign_model` / `foreign_model_error` public, models endpoint facts

**Files:**
- Modify: `backend/apps/ai/catalog.py` (append after `ceiling_for_provider`)
- Modify: `backend/apps/ai/structured.py:107-115` (delete `_foreign_catalog_model`, import the catalog helper)
- Modify: `backend/apps/secrets/views.py:260-279` (`ai_models`)
- Test: `backend/apps/ai/tests/test_catalog.py`, `backend/apps/secrets/tests/test_provider_config_endpoints.py`

**Interfaces:**
- Produces: `catalog_owner(model_id: str) -> str | None`, `is_foreign_model(provider: str, model: str) -> bool`, `foreign_model_error(provider: str, model: str) -> str | None` in `apps.ai.catalog`; `GET /api/schwab/models/` rows carry `max_payload_tokens`, response carries `defaults: {claude, openai, local}`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/ai/tests/test_catalog.py`:

```python
from apps.ai.catalog import catalog_owner, foreign_model_error, is_foreign_model


def test_catalog_owner_maps_ids_to_provider():
    assert catalog_owner("claude-opus-5") == "claude"
    assert catalog_owner("gpt-5.6-sol") == "openai"
    assert catalog_owner("llama-3.1-70b") is None


@pytest.mark.parametrize(
    ("provider", "model", "foreign"),
    [
        ("claude", "claude-opus-5", False),
        ("anthropic", "claude-opus-5", False),
        ("claude", "gpt-5.6-sol", True),
        ("openai", "claude-sonnet-5", True),
        ("local", "llama-3.1-70b", False),
        ("local", "gpt-5", True),
        ("openai", "", False),
    ],
)
def test_is_foreign_model(provider, model, foreign):
    assert is_foreign_model(provider, model) is foreign


def test_foreign_model_error_names_owner():
    assert foreign_model_error("claude", "claude-opus-5") is None
    msg = foreign_model_error("claude", "gpt-5.6-sol")
    assert msg == "gpt-5.6-sol is an openai catalog model; pick a claude model or clear the field."
```

(`pytest` is already imported in that file from the previous task's additions; add `import pytest` at the top if it is not.)

Append to `backend/apps/secrets/tests/test_provider_config_endpoints.py`:

```python
@pytest.mark.django_db
def test_ai_models_endpoint_carries_payload_budget_and_defaults(api):
    r = api.get("/api/schwab/models/")
    assert r.status_code == 200
    body = r.json()
    row = next(m for m in body["models"] if m["id"] == "claude-opus-5")
    assert row["max_payload_tokens"] == 150_000
    assert body["defaults"] == {"claude": "claude-opus-5", "openai": "gpt-5.6-sol", "local": ""}


@pytest.mark.django_db
def test_ai_models_endpoint_provider_filter_keeps_full_defaults(api):
    r = api.get("/api/schwab/models/?provider=openai")
    assert {m["provider"] for m in r.json()["models"]} == {"openai"}
    assert r.json()["defaults"]["claude"] == "claude-opus-5"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$PYTEST apps/ai/tests/test_catalog.py apps/secrets/tests/test_provider_config_endpoints.py`
Expected: FAIL — `ImportError: cannot import name 'catalog_owner'`, and `KeyError: 'max_payload_tokens'` / `'defaults'`.

- [ ] **Step 3: Implement**

Append to `backend/apps/ai/catalog.py`:

```python
def catalog_owner(model_id: str) -> str | None:
    """The provider whose catalog row has ``model_id``; None for ids the catalog does not know."""
    for m in _CATALOG:
        if m.id == model_id:
            return m.provider
    return None


def is_foreign_model(provider: str, model: str) -> bool:
    """True when ``model`` is a catalog row for a provider other than ``provider``.

    An id unknown to the catalog (a local model name, a brand-new vendor id) is not
    foreign — it is accepted verbatim. Any name in ``CLAUDE_FAMILY_PROVIDERS`` owns
    the ``claude`` rows.
    """
    if not model:
        return False
    owner = catalog_owner(model)
    if owner is None:
        return False
    family = "claude" if provider in CLAUDE_FAMILY_PROVIDERS else provider
    return owner != family


def foreign_model_error(provider: str, model: str) -> str | None:
    """A field-error message when ``model`` belongs to another provider's catalog, else None."""
    if not is_foreign_model(provider, model):
        return None
    owner = catalog_owner(model)
    article = "an" if owner and owner[0] in "aeiou" else "a"
    return f"{model} is {article} {owner} catalog model; pick a {provider} model or clear the field."
```

In `backend/apps/ai/structured.py`: delete the `_foreign_catalog_model` function (lines 107–115), add `is_foreign_model` to the `from apps.ai.catalog import ...` line, and replace the one call `if model and _foreign_catalog_model(cfg.provider, model):` with `if is_foreign_model(cfg.provider, model):`.

In `backend/apps/secrets/views.py`, change the import `from apps.ai.catalog import list_models as _list_catalog` to `from apps.ai.catalog import default_model_for, list_models as _list_catalog`, add `"max_payload_tokens": m.max_payload_tokens,` after `"supports_vision"` in each row, and add a sibling key after `"models": [...]`:

```python
            "defaults": {p: default_model_for(p) for p in ("claude", "openai", "local")},
```

- [ ] **Step 4: Run the tests**

Run: `$PYTEST apps/ai/tests apps/secrets/tests/test_provider_config_endpoints.py`
Expected: all pass (the facade tests that covered `_foreign_catalog_model` still pass through `is_foreign_model`).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/ai/catalog.py backend/apps/ai/structured.py backend/apps/secrets/views.py backend/apps/ai/tests/test_catalog.py backend/apps/secrets/tests/test_provider_config_endpoints.py
LEFTHOOK=0 git commit -m "feat(ai): public vendor guard in the catalog; models endpoint carries payload budgets and defaults" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task B2: Cross-vendor model guards on the three serializers

**Files:**
- Modify: `backend/apps/profiles/serializers.py` (`TradingProfileSerializer`)
- Modify: `backend/apps/secrets/serializers.py` (`ProviderConfigSerializer`)
- Modify: `backend/apps/observer/serializers.py` (`ObserverScheduleSerializer.validate`)
- Test: `backend/apps/profiles/tests/test_profile_vendor_guard.py` (new), `backend/apps/secrets/tests/test_provider_config_endpoints.py`, `backend/apps/observer/tests/test_schedules_endpoint.py`

**Interfaces:**
- Consumes: `apps.ai.catalog.foreign_model_error` (B1).
- Produces: 400 `{"default_model": [...]}` / `{"override_model": [...]}` on foreign ids.

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/profiles/tests/test_profile_vendor_guard.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_create_profile_rejects_foreign_model(api):
    r = api.post(
        "/api/profiles/",
        {"name": "P", "style": "s", "default_provider": "openai", "default_model": "claude-opus-5"},
        format="json",
    )
    assert r.status_code == 400
    assert "claude catalog model" in r.json()["default_model"][0]


@pytest.mark.django_db
def test_create_profile_accepts_same_vendor_and_unknown_ids(api):
    ok = api.post(
        "/api/profiles/",
        {"name": "A", "style": "s", "default_provider": "openai", "default_model": "gpt-5.6-sol"},
        format="json",
    )
    assert ok.status_code == 201
    local = api.post(
        "/api/profiles/",
        {"name": "B", "style": "s", "default_provider": "local", "default_model": "llama-3.1-70b"},
        format="json",
    )
    assert local.status_code == 201


@pytest.mark.django_db
def test_patch_provider_alone_is_checked_against_stored_model(api):
    p = TradingProfile.objects.create(
        name="P", style="s", default_provider="claude", default_model="claude-opus-5"
    )
    r = api.patch(f"/api/profiles/{p.id}/", {"default_provider": "openai"}, format="json")
    assert r.status_code == 400
    assert "default_model" in r.json()
```

Append to `backend/apps/secrets/tests/test_provider_config_endpoints.py`:

```python
@pytest.mark.django_db
def test_provider_config_rejects_foreign_default_model(api):
    ProviderConfig.objects.create(provider="openai")
    r = api.patch(
        "/api/schwab/providers/openai/", {"default_model": "claude-sonnet-5"}, format="json"
    )
    assert r.status_code == 400
    assert "claude catalog model" in r.json()["default_model"][0]


@pytest.mark.django_db
def test_provider_config_accepts_own_and_unknown_models(api):
    ProviderConfig.objects.create(provider="local")
    r = api.patch("/api/schwab/providers/local/", {"default_model": "llama3"}, format="json")
    assert r.status_code == 200
    ProviderConfig.objects.create(provider="claude")
    r = api.patch(
        "/api/schwab/providers/claude/", {"default_model": "claude-fable-5-1"}, format="json"
    )
    assert r.status_code == 200
```

Append to `backend/apps/observer/tests/test_schedules_endpoint.py` (reuse that file's existing fixtures for a profile and client; if it builds payloads through a helper, mirror it):

```python
@pytest.mark.django_db
def test_schedule_rejects_override_model_from_another_vendor(api, profile):
    r = api.post(
        "/api/observer/schedules/",
        {
            "name": "S",
            "profile": profile.id,
            "cron": "*/15 * * * *",
            "override_provider": "openai",
            "override_model": "claude-opus-5",
        },
        format="json",
    )
    assert r.status_code == 400
    assert "override_model" in r.json()


@pytest.mark.django_db
def test_schedule_override_model_checked_against_profile_provider(api, profile):
    # profile.default_provider is "claude"; no override_provider → guard uses the profile's.
    r = api.post(
        "/api/observer/schedules/",
        {"name": "S", "profile": profile.id, "cron": "*/15 * * * *", "override_model": "gpt-5"},
        format="json",
    )
    assert r.status_code == 400
    ok = api.post(
        "/api/observer/schedules/",
        {"name": "T", "profile": profile.id, "cron": "*/15 * * * *", "override_model": "claude-sonnet-5"},
        format="json",
    )
    assert ok.status_code == 201
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$PYTEST apps/profiles/tests/test_profile_vendor_guard.py apps/secrets/tests/test_provider_config_endpoints.py apps/observer/tests/test_schedules_endpoint.py`
Expected: the new tests FAIL with 201/200 where 400 is expected.

- [ ] **Step 3: Implement**

`backend/apps/profiles/serializers.py` — add to `TradingProfileSerializer`:

```python
    def validate(self, attrs):
        from apps.ai.catalog import foreign_model_error

        provider = self._resolved(attrs, "default_provider", default="claude")
        model = self._resolved(attrs, "default_model", default="")
        err = foreign_model_error(provider, model)
        if err:
            raise serializers.ValidationError({"default_model": err})
        return attrs

    def _resolved(self, attrs, field: str, *, default):
        """The value this write resolves to: incoming attr, else the stored value
        (PATCH omits unchanged fields), else the default."""
        if field in attrs:
            return attrs[field]
        if self.instance is not None:
            return getattr(self.instance, field)
        return default
```

`backend/apps/secrets/serializers.py` — add to `ProviderConfigSerializer`:

```python
    def validate(self, attrs):
        from apps.ai.catalog import foreign_model_error

        provider = attrs.get("provider") or (self.instance.provider if self.instance else "")
        model = attrs.get("default_model", self.instance.default_model if self.instance else "")
        err = foreign_model_error(provider, model)
        if err:
            raise serializers.ValidationError({"default_model": err})
        return attrs
```

`backend/apps/observer/serializers.py` — in `validate`, after `self._validate_claude_only_modes(attrs)`, add `self._validate_override_model(attrs)`, and add the method:

```python
    def _validate_override_model(self, attrs) -> None:
        """``override_model`` must belong to the provider the schedule resolves to
        (``override_provider``, else the profile's default) — a Claude id sent to
        OpenAI fails every fire."""
        from apps.ai.catalog import foreign_model_error

        model = self._resolved(attrs, "override_model", default="")
        if not model:
            return
        profile = self._resolved(attrs, "profile", default=None)
        provider = self._resolved(attrs, "override_provider", default="") or getattr(
            profile, "default_provider", ""
        )
        err = foreign_model_error(provider, model) if provider else None
        if err:
            raise serializers.ValidationError({"override_model": err})
```

- [ ] **Step 4: Run the tests**

Run: `$PYTEST apps/profiles apps/secrets apps/observer/tests/test_schedules_endpoint.py apps/observer/tests/test_relative_schedule_api.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/profiles backend/apps/secrets/serializers.py backend/apps/secrets/tests backend/apps/observer/serializers.py backend/apps/observer/tests/test_schedules_endpoint.py
LEFTHOOK=0 git commit -m "feat(api): reject a default/override model that belongs to another provider's catalog" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task B3: Provider attribution on observer fires, post-mortems and War Room verdicts

**Files:**
- Modify: `backend/apps/observer/services/run.py:52-53, 119-122, 322, 343-347` (one model resolution; structured message content)
- Modify: `backend/apps/observer/views.py:106-120` (`observer_thread_view`)
- Modify: `backend/apps/thesis/services/postmortem.py:130`
- Modify: `backend/apps/strategy/tasks.py:109-124` (`run_debate` verdict dict)
- Modify: `backend/apps/strategy/warroom/serializers.py` (`get_messages`)
- Test: `backend/apps/observer/tests/test_structured_outputs.py`, `backend/apps/observer/tests/test_observer_thread_endpoint.py`, `backend/apps/observer/tests/test_observer_model_resolution.py` (new), `backend/apps/thesis/tests/test_postmortem.py` (or the file that already patches `run_structured` for the narrative), `backend/apps/strategy/warroom/tests/test_verdict.py` (or the task test that patches `synthesize`), `backend/apps/strategy/warroom/tests/test_views.py` (or the file that tests `/api/warroom/runs/<id>/`)

**Interfaces:**
- Produces: `run.py::_observer_model(sched, cfg, provider_name) -> str`; structured message `content.provider` / `content.model`; observer thread messages `ai_run: {provider, model, cost_usd} | null`, `status`, `error`; `PostMortem.report["ai"]` and `WarRoomRun.verdict["ai"]` = `{"provider", "model"}`; War Room run `messages[].provider/model` (null when no run).

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/observer/tests/test_observer_thread_endpoint.py`:

```python
@pytest.mark.django_db
def test_observer_thread_endpoint_exposes_ai_run_and_null_without_one(api):
    from decimal import Decimal

    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import AIRun

    p = TradingProfile.objects.create(name="P", style="x")
    t = get_or_create_observer_thread(p)
    plain = Message.objects.create(thread=t, role="assistant", content={"text": "ok"})
    AIRun.objects.create(
        message=plain, provider="openai", model="gpt-5.6-sol", cost_usd=Decimal("0.0123"), status="done"
    )
    Message.objects.create(
        thread=t,
        role="assistant",
        content={"kind": "structured_observation", "report": {}, "provider": "claude", "model": "claude-opus-5"},
    )
    Message.objects.create(
        thread=t, role="assistant", content={"text": "Structured run failed: boom"}, status="failed", error="boom"
    )
    body = api.get(f"/api/observer/threads/{p.id}/").json()
    by_id = {m["id"]: m for m in body["messages"]}
    assert by_id[plain.id]["ai_run"] == {"provider": "openai", "model": "gpt-5.6-sol", "cost_usd": "0.012300"}
    assert by_id[plain.id]["status"] == "done"
    structured = next(m for m in body["messages"] if m["content"].get("kind") == "structured_observation")
    assert structured["ai_run"] is None
    assert structured["content"]["provider"] == "claude"
    failed = next(m for m in body["messages"] if m["status"] == "failed")
    assert failed["error"] == "boom"
```

Create `backend/apps/observer/tests/test_observer_model_resolution.py`:

```python
import pytest

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import _observer_model
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(
        name="P", style="s", default_provider="claude", default_model="claude-sonnet-5"
    )


def _sched(profile, **kw):
    return ObserverSchedule(name="S", profile=profile, **kw)


@pytest.mark.django_db
def test_override_model_wins(profile):
    cfg = ProviderConfig(provider="claude", default_model="claude-opus-5")
    assert _observer_model(_sched(profile, override_model="claude-fable-5-1"), cfg, "claude") == "claude-fable-5-1"


@pytest.mark.django_db
def test_profile_model_used_on_the_profiles_own_provider(profile):
    cfg = ProviderConfig(provider="claude", default_model="claude-opus-5")
    assert _observer_model(_sched(profile), cfg, "claude") == "claude-sonnet-5"


@pytest.mark.django_db
def test_profile_model_skipped_when_schedule_overrides_the_provider(profile):
    cfg = ProviderConfig(provider="openai", default_model="")
    # override_provider=openai; the profile's Claude id must not be sent to OpenAI.
    assert _observer_model(_sched(profile, override_provider="openai"), cfg, "openai") == "gpt-5.6-sol"


@pytest.mark.django_db
def test_config_default_then_catalog_default(profile):
    profile.default_model = ""
    assert _observer_model(_sched(profile), ProviderConfig(provider="claude", default_model="claude-opus-4-8"), "claude") == "claude-opus-4-8"
    assert _observer_model(_sched(profile), ProviderConfig(provider="claude", default_model=""), "claude") == "claude-opus-5"
    assert _observer_model(_sched(profile), None, "claude") == "claude-opus-5"
```

In the War Room views test file, add (adapting to its fixtures for a finished run with persona messages):

```python
    body = api.get(f"/api/warroom/runs/{run.id}/").json()
    assert {"provider", "model"} <= set(body["messages"][0].keys())
```

and, for a persona message that has an `AIRun` (create one with `provider="openai", model="gpt-5.6-sol"` on that message), assert those values come through.

In `backend/apps/observer/tests/test_structured_outputs.py`, find the test that fires a structured schedule with `run_structured` patched and asserts a `structured_observation` Message; add right after its assertions (or as a new test copying its setup):

```python
    assert msg.content["provider"] == "claude"
    assert msg.content["model"]  # the resolved model id, never blank
```

In the post-mortem test file that patches the narrative (`grep -rn "PostMortemReport(" backend/apps/thesis/tests` to find it), add:

```python
    assert pm.report["ai"] == {"provider": "claude", "model": pm_target_model}
```

where `pm_target_model` is whatever that test configures (the `ProviderConfig.default_model` it creates, or `"claude-opus-5"` when it leaves the config's model blank).

In the War Room task test that patches `synthesize` (`grep -rn "synthesize" backend/apps/strategy/tests backend/apps/strategy/warroom/tests`), add:

```python
    assert run.verdict["ai"]["provider"] == "claude"
    assert run.verdict["ai"]["model"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$PYTEST apps/observer/tests/test_observer_thread_endpoint.py apps/observer/tests/test_structured_outputs.py apps/thesis apps/strategy`
Expected: the new assertions FAIL (`KeyError: 'ai_run'` / `'provider'` / `'ai'`).

- [ ] **Step 3: Implement**

`run.py` — add the resolver (module level, near `_prompt_hash`) and use it in `fire_observer` (replace `model_name = sched.override_model or sched.profile.default_model` with `model_name = _observer_model(sched, cfg, provider_name)` **after** `cfg` is fetched; pass `model_name` into `_run_structured_and_record` as a new keyword `model_id=` and delete the local `model_id = ...` line 322 there):

```python
def _observer_model(sched: ObserverSchedule, cfg: ProviderConfig | None, provider_name: str) -> str:
    """The model this fire runs on: the schedule's override, else the profile's model when
    the fire runs on the profile's own provider, else the config's default, else the
    catalog default. A catalog id owned by another provider is skipped, never sent."""
    from apps.ai.catalog import is_foreign_model

    same_provider = not sched.override_provider or sched.override_provider == sched.profile.default_provider
    candidates = [
        sched.override_model,
        sched.profile.default_model if same_provider else "",
        cfg.default_model if cfg is not None else "",
    ]
    for candidate in candidates:
        if candidate and not is_foreign_model(provider_name, candidate):
            return candidate
    return default_model_for(provider_name)
```

`_run_structured_and_record(sched, thread, payload_text, provider_name, cfg, *, model_id: str, snap=None)`; the prompt hash at line 122 already uses `model_name`, which is now the same id.

`run.py`: change the structured message to

```python
    msg = Message.objects.create(
        thread=thread,
        role="assistant",
        content={
            "kind": "structured_observation",
            "report": report.model_dump(),
            "provider": provider_name,
            "model": model_id,
        },
        status="done",
    )
```

`observer/views.py::observer_thread_view`:

```python
@require_GET
def observer_thread_view(_request: HttpRequest, profile_id: int) -> JsonResponse:
    profile = get_object_or_404(TradingProfile, id=profile_id)
    thread = get_or_create_observer_thread(profile)
    messages = thread.messages.select_related("ai_run").order_by("created_at")
    return JsonResponse(
        {
            "id": thread.id,
            "kind": thread.kind,
            "profile_id": thread.profile_id,
            "title": thread.title,
            "messages": [_timeline_message(m) for m in messages],
        }
    )


def _timeline_message(m) -> dict:
    run = getattr(m, "ai_run", None)  # reverse OneToOne: AttributeError-family when absent
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "status": m.status,
        "error": m.error,
        "created_at": m.created_at.isoformat(),
        "ai_run": (
            {"provider": run.provider, "model": run.model, "cost_usd": str(run.cost_usd)}
            if run is not None
            else None
        ),
    }
```

`strategy/warroom/serializers.py::get_messages`:

```python
    def get_messages(self, obj) -> list[dict]:
        out = []
        for m in obj.thread.messages.select_related("ai_run").order_by("created_at"):
            run = getattr(m, "ai_run", None)
            out.append(
                {
                    "role": m.role,
                    "content": m.content,
                    "provider": run.provider if run is not None else None,
                    "model": run.model if run is not None else None,
                }
            )
        return out
```

`postmortem.py`: replace `pm.report = report.model_dump()` with

```python
    pm.report = {
        **report.model_dump(),
        "ai": {"provider": target.provider, "model": target.model},
    }
```

`strategy/tasks.py`: inside the `verdict = {...}` literal add `"ai": {"provider": target.provider, "model": target.model},`.

- [ ] **Step 4: Run the tests**

Run: `$PYTEST apps/observer apps/thesis apps/strategy apps/threads`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/observer backend/apps/thesis/services/postmortem.py backend/apps/thesis/tests backend/apps/strategy
LEFTHOOK=0 git commit -m "feat(observer,thesis,strategy): record which provider and model produced each structured output" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task B4: Scheduled eval provider knob

**Files:**
- Modify: `backend/apps/core/models.py` (`SystemSettings`, after `aieval_scheduled_limit`)
- Create: `backend/apps/core/migrations/0005_systemsettings_aieval_scheduled_provider.py` (via makemigrations)
- Modify: `backend/config/settings/base.py:290` (add `AIEVAL_SCHEDULED_PROVIDER`)
- Modify: `backend/apps/core/runtime_config.py` (`_SPEC`, `RuntimeConfig`)
- Modify: `backend/apps/core/views.py` (`_coerce_setting`)
- Modify: `backend/apps/analytics/tasks.py:70-107` (`run_scheduled`)
- Modify: `.env.example` (Read tool to inspect; Edit tool to add `AIEVAL_SCHEDULED_PROVIDER=claude` next to `AIEVAL_SCHEDULED_MODEL` if that key is documented there)
- Test: `backend/apps/core/tests/test_system_settings.py`, `backend/apps/analytics/tests/test_aieval_scheduled_provider.py` (new)

**Interfaces:**
- Produces: `runtime_config().aieval_scheduled_provider: str`; `GET/PATCH /api/settings/` field `aieval_scheduled_provider`; PATCH validation for `ai_failover_provider` and `aieval_scheduled_provider` ∈ {"", "claude", "openai", "local"}.

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/core/tests/test_system_settings.py`:

```python
@pytest.mark.django_db
@override_settings(AIEVAL_SCHEDULED_PROVIDER="claude")
def test_aieval_provider_defaults_to_setting_and_accepts_override():
    assert runtime_config().aieval_scheduled_provider == "claude"
    c = Client()
    r = c.patch(
        "/api/settings/",
        data=json.dumps({"aieval_scheduled_provider": "openai"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["aieval_scheduled_provider"] == "openai"
    assert runtime_config().aieval_scheduled_provider == "openai"


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["aieval_scheduled_provider", "ai_failover_provider"])
def test_provider_knobs_reject_unknown_provider(key):
    c = Client()
    r = c.patch("/api/settings/", data=json.dumps({key: "bogus"}), content_type="application/json")
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_value"
    ok = c.patch("/api/settings/", data=json.dumps({key: ""}), content_type="application/json")
    assert ok.status_code == 200
```

Create `backend/apps/analytics/tests/test_aieval_scheduled_provider.py`:

```python
from unittest.mock import patch

import pytest

from apps.core.models import SystemSettings


@pytest.mark.django_db
def test_run_scheduled_uses_configured_provider_and_repairs_foreign_model():
    cfg = SystemSettings.load()
    cfg.aieval_scheduled_enabled = True
    cfg.aieval_scheduled_provider = "openai"
    cfg.aieval_scheduled_model = "claude-sonnet-4-6"  # a Claude id must not reach OpenAI
    cfg.save()

    from apps.analytics import tasks

    with (
        patch.object(tasks, "preflight_cost_cap") as preflight,
        patch.object(tasks, "evaluate", return_value={"n": 0}) as evaluate,
    ):
        out = tasks.run_scheduled()

    preflight.assert_called_once_with("openai")
    assert evaluate.call_args.kwargs["provider"] == "openai"
    assert evaluate.call_args.kwargs["model"] == "gpt-5.6-sol"
    assert out == {"skipped": "no_data"}


@pytest.mark.django_db
def test_run_scheduled_keeps_a_same_vendor_model():
    cfg = SystemSettings.load()
    cfg.aieval_scheduled_enabled = True
    cfg.aieval_scheduled_provider = "claude"
    cfg.aieval_scheduled_model = "claude-sonnet-5"
    cfg.save()

    from apps.analytics import tasks

    with (
        patch.object(tasks, "preflight_cost_cap"),
        patch.object(tasks, "evaluate", return_value={"n": 0}) as evaluate,
    ):
        tasks.run_scheduled()
    assert evaluate.call_args.kwargs["model"] == "claude-sonnet-5"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$PYTEST apps/core/tests/test_system_settings.py apps/analytics/tests/test_aieval_scheduled_provider.py`
Expected: FAIL — `AttributeError: 'RuntimeConfig' object has no attribute 'aieval_scheduled_provider'`, 400 `unknown_field`, `preflight_cost_cap` called with `"claude"`.

- [ ] **Step 3: Implement**

`core/models.py` — after `aieval_scheduled_limit`:

```python
    aieval_scheduled_provider = models.CharField(max_length=32, null=True, blank=True)  # noqa: DJ001
```

Run: `$RUN web uv run python manage.py makemigrations core -n systemsettings_aieval_scheduled_provider` and confirm `backend/apps/core/migrations/0005_systemsettings_aieval_scheduled_provider.py` appeared with a single `AddField`.

`config/settings/base.py` — change the model default and add the provider knob:

```python
AIEVAL_SCHEDULED_MODEL = env.str("AIEVAL_SCHEDULED_MODEL", default="claude-opus-5")
AIEVAL_SCHEDULED_PROVIDER = env.str("AIEVAL_SCHEDULED_PROVIDER", default="claude")
```

`core/runtime_config.py` — the `aieval_scheduled_model` `_SPEC` hard default becomes `"claude-opus-5"`, and a new entry follows it:

```python
    ("aieval_scheduled_provider", "AIEVAL_SCHEDULED_PROVIDER", "claude"),
```

(If any existing test asserts the old `claude-sonnet-4-6` default, update it to `claude-opus-5`.)

and the dataclass field `aieval_scheduled_provider: str` after `aieval_scheduled_model: str`.

`core/views.py` — add a module constant and a check in `_coerce_setting` just before `return coerced, None`:

```python
_PROVIDER_KNOBS = frozenset({"ai_failover_provider", "aieval_scheduled_provider"})
_PROVIDER_VALUES = ("", "claude", "openai", "local")
```

```python
    if key in _PROVIDER_KNOBS and coerced not in _PROVIDER_VALUES:
        return None, f"{key} must be one of claude, openai, local (or blank)"
```

`analytics/tasks.py::run_scheduled` — replace the body from `model = rc.aieval_scheduled_model` down to the `evaluate(...)` call with:

```python
    from apps.ai.catalog import default_model_for, is_foreign_model

    provider = rc.aieval_scheduled_provider or "claude"
    model = rc.aieval_scheduled_model
    if not model or is_foreign_model(provider, model):
        # The user changed the provider but not the model: never send another
        # vendor's id — fall back to that provider's catalog default.
        model = default_model_for(provider)
    horizon = rc.aieval_scheduled_horizon
    limit = rc.aieval_scheduled_limit

    try:
        preflight_cost_cap(provider)
    except CostCapExceededError as exc:
        log.warning("analytics.aieval_run_scheduled skipped — cost cap: %s", exc)
        return {"skipped": "cost_cap"}

    res = evaluate(
        system=DEFAULT_EVAL_SYSTEM,
        model=model,
        label="scheduled",
        horizon=horizon,
        limit=limit,
        provider=provider,
    )
```

Update the module docstring's "through the real model" sentence to "through the configured provider and model".

- [ ] **Step 4: Run the tests**

Run: `$PYTEST apps/core apps/analytics`
Expected: all pass. Then `$RUN web uv run python manage.py makemigrations --check --dry-run` → "No changes detected".

- [ ] **Step 5: Commit**

```bash
git add backend/apps/core backend/config/settings/base.py backend/apps/analytics/tasks.py backend/apps/analytics/tests/test_aieval_scheduled_provider.py .env.example
LEFTHOOK=0 git commit -m "feat(core,analytics): scheduled eval runs on a configurable provider" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

(Drop `.env.example` from `git add` if it was not changed.)

---

### Task B5: `EvalRun.provider` + `POST /api/aieval/runs/` + `analytics.aieval_run` task

**Files:**
- Modify: `backend/apps/analytics/models.py` (`EvalRun`)
- Create: `backend/apps/analytics/migrations/0002_evalrun_provider.py` (via makemigrations)
- Modify: `backend/apps/analytics/services/aieval.py` (`persist_eval_run`)
- Modify: `backend/apps/analytics/aieval_serializers.py`
- Modify: `backend/apps/analytics/aieval_views.py`, `backend/apps/analytics/aieval_urls.py`
- Modify: `backend/apps/analytics/tasks.py` (new task)
- Modify: `frontend/src/api/observer.ts` is NOT touched here (F7 adds the `eval_done` kind)
- Test: `backend/apps/analytics/tests/test_aieval_manual_run.py` (new); `backend/apps/analytics/tests/test_aieval.py::test_persist_eval_run_maps_result_to_row` gains a provider assertion

**Interfaces:**
- Produces: `EvalRun.provider: str`; serializer field `provider`; `POST /api/aieval/runs/` → 202 `{"queued": true, "provider", "model", "horizon", "limit", "label"}` or 400 `{"code": "invalid_provider" | "foreign_model" | "no_provider" | "undecryptable_key", "message"}` or 409 `{"code": "cost_cap", "message"}`; Celery task `analytics.aieval_run(provider, model, horizon, limit, label)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/analytics/tests/test_aieval_manual_run.py`:

```python
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.cost import CostCapExceededError
from apps.analytics.models import EvalRun
from apps.secrets.models import ProviderConfig


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def openai_cfg(db):
    cfg = ProviderConfig.objects.create(provider="openai", default_model="gpt-5.6-sol")
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


@pytest.mark.django_db
def test_post_queues_task_with_resolved_defaults(api, openai_cfg):
    with patch("apps.analytics.aieval_views.aieval_run") as task:
        r = api.post("/api/aieval/runs/", {"provider": "openai"}, format="json")
    assert r.status_code == 202
    assert r.json() == {
        "queued": True,
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "horizon": 30,
        "limit": 25,
        "label": "manual",
    }
    task.delay.assert_called_once_with(
        provider="openai", model="gpt-5.6-sol", horizon=30, limit=25, label="manual"
    )


@pytest.mark.django_db
def test_post_rejects_unknown_provider_and_foreign_model(api, openai_cfg):
    r = api.post("/api/aieval/runs/", {"provider": "gemini"}, format="json")
    assert r.status_code == 400
    r = api.post(
        "/api/aieval/runs/", {"provider": "openai", "model": "claude-opus-5"}, format="json"
    )
    assert r.status_code == 400
    assert r.json()["code"] == "foreign_model"


@pytest.mark.django_db
def test_post_400_when_provider_has_no_credential(api):
    ProviderConfig.objects.create(provider="openai")  # enabled, no key
    r = api.post("/api/aieval/runs/", {"provider": "openai"}, format="json")
    assert r.status_code == 400
    assert r.json()["code"] == "no_provider"


@pytest.mark.django_db
def test_post_409_when_cap_exceeded(api, openai_cfg):
    with patch(
        "apps.analytics.aieval_views.ensure_within_caps",
        side_effect=CostCapExceededError("daily cap hit"),
    ):
        r = api.post("/api/aieval/runs/", {"provider": "openai"}, format="json")
    assert r.status_code == 409
    assert r.json()["code"] == "cost_cap"


@pytest.mark.django_db
@override_settings(THESIS_POSTMORTEM_HORIZONS=[7, 30, 90])
def test_post_validates_horizon_limit_and_label(api, openai_cfg):
    bad_h = api.post("/api/aieval/runs/", {"provider": "openai", "horizon": 12}, format="json")
    assert bad_h.status_code == 400
    bad_l = api.post("/api/aieval/runs/", {"provider": "openai", "limit": 500}, format="json")
    assert bad_l.status_code == 400
    with patch("apps.analytics.aieval_views.aieval_run") as task:
        ok = api.post(
            "/api/aieval/runs/",
            {"provider": "openai", "horizon": 90, "limit": 3, "label": "ab-openai"},
            format="json",
        )
    assert ok.status_code == 202
    assert task.delay.call_args.kwargs["label"] == "ab-openai"


def test_task_is_at_most_once():
    from apps.analytics.tasks import aieval_run

    assert aieval_run.acks_late is False


@pytest.mark.django_db
def test_task_persists_run_with_provider_and_notifies():
    from apps.analytics import tasks
    from apps.observer.models import Notification

    fake = {
        "model": "gpt-5.6-sol",
        "provider": "openai",
        "label": "manual",
        "horizon": 30,
        "n": 2,
        "skipped": 0,
        "scored": 2,
        "hit_rate": 0.5,
        "brier": 0.25,
        "avg_confidence": 0.7,
        "calibration_error": 0.1,
        "calibration": [],
        "results": [],
    }
    with (
        patch.object(tasks, "preflight_cost_cap"),
        patch.object(tasks, "evaluate", return_value=fake),
    ):
        out = tasks.aieval_run(provider="openai", model="gpt-5.6-sol", horizon=30, limit=25, label="manual")
    run = EvalRun.objects.get(id=out["ran"])
    assert run.provider == "openai"
    assert run.source == "manual"
    assert Notification.objects.filter(kind="eval_done").exists()


@pytest.mark.django_db
def test_list_serializer_exposes_provider(api):
    EvalRun.objects.create(model="gpt-5.6-sol", provider="openai", label="x")
    r = api.get("/api/aieval/runs/")
    assert r.json()[0]["provider"] == "openai"
```

In `backend/apps/analytics/tests/test_aieval.py::test_persist_eval_run_maps_result_to_row`, add `"provider": "openai"` to the result dict it builds and assert `run.provider == "openai"`. In `test_persist_eval_run_defaults_source_manual`, assert `run.provider == "claude"` when the result has no `provider` key (if that test passes a result without one).

- [ ] **Step 2: Run them to verify they fail**

Run: `$PYTEST apps/analytics/tests/test_aieval_manual_run.py apps/analytics/tests/test_aieval.py`
Expected: FAIL — 405 on POST, `FieldError: provider`, `ImportError: aieval_run`.

- [ ] **Step 3: Implement**

`analytics/models.py` — after `model = models.CharField(...)`:

```python
    provider = models.CharField(max_length=32, default="claude", blank=True)
```

Run: `$RUN web uv run python manage.py makemigrations analytics -n evalrun_provider` → `0002_evalrun_provider.py` (one `AddField`, default `"claude"`, so existing rows are labelled honestly: every run before this field was Claude).

`services/aieval.py::persist_eval_run` — add `provider=result.get("provider", "claude"),` to the `EvalRun.objects.create(...)` call.

`aieval_serializers.py` — add `"provider",` after `"model",` in `EvalRunSerializer.Meta.fields`, and append:

```python
class EvalRunRequestSerializer(serializers.Serializer):
    """Body of ``POST /api/aieval/runs/`` — a manual, bounded, billed eval run."""

    provider = serializers.ChoiceField(choices=["claude", "openai", "local"], default="claude")
    model = serializers.CharField(required=False, allow_blank=True, default="")
    horizon = serializers.IntegerField(required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=25)
    label = serializers.CharField(max_length=64, default="manual")

    def validate_horizon(self, value: int) -> int:
        from django.conf import settings

        allowed = list(settings.THESIS_POSTMORTEM_HORIZONS)
        if value not in allowed:
            raise serializers.ValidationError(f"horizon must be one of {allowed}")
        return value
```

`aieval_views.py`:

```python
from __future__ import annotations

from cryptography.fernet import InvalidToken
from django.conf import settings
from rest_framework import generics
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.catalog import default_model_for, foreign_model_error
from apps.ai.cost import CostCapExceededError
from apps.ai.structured import ensure_within_caps, resolve_structured_target
from apps.analytics.aieval_serializers import EvalRunRequestSerializer, EvalRunSerializer
from apps.analytics.models import EvalRun
from apps.analytics.tasks import aieval_run


def _err(code: str, message: str, status: int) -> Response:
    return Response({"code": code, "message": message}, status=status)


class EvalRunListCreateView(generics.ListAPIView):
    """GET: the 50 newest runs. POST: queue one bounded, billed eval run on a provider."""

    serializer_class = EvalRunSerializer

    def get_queryset(self):
        return EvalRun.objects.order_by("-created_at")[:50]

    def post(self, request):
        ser = EvalRunRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        provider: str = d["provider"]
        model: str = d["model"] or default_model_for(provider)
        horizon: int = d.get("horizon") or settings.AIEVAL_SCHEDULED_HORIZON
        err = foreign_model_error(provider, model)
        if err:
            return _err("foreign_model", err, 400)
        try:
            target = resolve_structured_target(override_provider=provider, override_model=model)
        except InvalidToken:
            return _err(
                "undecryptable_key",
                f"The stored {provider} key cannot be decrypted; re-enter it in Settings → AI Providers.",
                400,
            )
        if target is None:
            need = "a base URL" if provider == "local" else "an API key"
            return _err(
                "no_provider",
                f"No usable {provider} provider: add {need} and enable it in Settings → AI Providers.",
                400,
            )
        try:
            ensure_within_caps(target)
        except CostCapExceededError as exc:
            return _err("cost_cap", str(exc), 409)
        aieval_run.delay(
            provider=provider, model=model, horizon=horizon, limit=d["limit"], label=d["label"]
        )
        return Response(
            {
                "queued": True,
                "provider": provider,
                "model": model,
                "horizon": horizon,
                "limit": d["limit"],
                "label": d["label"],
            },
            status=drf_status.HTTP_202_ACCEPTED,
        )


class EvalRunLatestView(APIView):
    def get(self, request):
        run = EvalRun.objects.order_by("-created_at").first()
        if run is None:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)
        return Response(EvalRunSerializer(run).data)
```

`aieval_urls.py`: point `runs/` at `views.EvalRunListCreateView.as_view()`.

`analytics/tasks.py` — append:

```python
@shared_task(name="analytics.aieval_run", acks_late=False, reject_on_worker_lost=False)
def aieval_run(*, provider: str, model: str, horizon: int, limit: int, label: str = "manual") -> dict:
    """One manual eval run queued by ``POST /api/aieval/runs/``. At-most-once: it bills a
    provider and is not idempotent, so a worker crash must not redeliver it."""
    from apps.core.safe_log import scrub_secret_params
    from apps.observer.services.notifications import notify

    try:
        preflight_cost_cap(provider)
    except CostCapExceededError as exc:
        log.warning("analytics.aieval_run skipped — cost cap: %s", exc)
        notify(user_id=None, kind="eval_done", title="Eval run skipped", body=str(exc), link="/scorecard")
        return {"skipped": "cost_cap"}
    try:
        res = evaluate(
            system=DEFAULT_EVAL_SYSTEM,
            model=model,
            label=label,
            horizon=horizon,
            limit=limit,
            provider=provider,
        )
    except Exception as exc:
        notify(
            user_id=None,
            kind="error",
            title="Eval run failed",
            body=scrub_secret_params(str(exc))[:500],
            link="/scorecard",
        )
        raise
    if not res["n"]:
        notify(
            user_id=None,
            kind="eval_done",
            title="Eval run: nothing to replay",
            body=f"No decisive post-mortems with a frozen snapshot at {horizon}d.",
            link="/scorecard",
        )
        return {"skipped": "no_data"}
    run = persist_eval_run(res, source="manual")
    hit = res.get("hit_rate")
    hit_txt = f"hit-rate {hit:.0%}" if hit is not None else "no scored rows"
    notify(
        user_id=None,
        kind="eval_done",
        title=f"Eval run #{run.id} finished",
        body=f"{provider} · {model}: {hit_txt} over {res['scored']} scored ({label}).",
        link="/scorecard",
    )
    return {"ran": run.id, "n": res["n"], "hit_rate": hit}
```

Check `apps.core.safe_log.scrub_secret_params` exists with that name (`grep -n "def scrub_secret_params" backend/apps/core/safe_log.py`); if it lives elsewhere, import from where the observer's `run.py` imports it.

- [ ] **Step 4: Run the tests**

Run: `$PYTEST apps/analytics apps/core/tests/test_celery_registration.py`
Expected: all pass (the registration test only guards beat tasks; `analytics.aieval_run` is queued). Then `$RUN web uv run python manage.py makemigrations --check --dry-run` → "No changes detected".

- [ ] **Step 5: Commit**

```bash
git add backend/apps/analytics
LEFTHOOK=0 git commit -m "feat(analytics): EvalRun.provider and a manual, provider-aware eval trigger endpoint" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task B7: Ledger dedup per provider/model; consensus fires feed the ledger

**Files:**
- Modify: `backend/apps/observer/models.py` (`AIPrediction.Meta.constraints`)
- Create: `backend/apps/observer/migrations/0022_aiprediction_open_call_per_provider_model.py` (via makemigrations)
- Modify: `backend/apps/observer/predictions/services/extract.py` (the `existing` lookup)
- Modify: `backend/apps/observer/schemas.py` (`ProviderTake.report`)
- Modify: `backend/apps/observer/services/consensus.py` (set `report=` on each take)
- Modify: `backend/apps/observer/services/run.py` (`_run_consensus_and_record` extracts per take; call site passes `snap=`)
- Modify: `CLAUDE.md` Prediction Ledger line (dedup key)
- Test: `backend/apps/observer/predictions/tests/test_extract.py`, `backend/apps/observer/tests/test_consensus_observer.py`, `backend/apps/observer/tests/test_consensus_schema.py`

**Interfaces:**
- Consumes: `_extract_prediction(report, *, snap, message, provider, model, profile)` (run.py).
- Produces: `ProviderTake.report: ObservationReport | None` (excluded from `model_dump`); one open `AIPrediction` per `(ticker, horizon_days, profile, provider, model)`.

- [ ] **Step 1: Write the failing tests**

In `test_extract.py`'s dedup class, add (mirroring `_extract`/`_report`/`_snap` helpers there; `_extract` must accept `provider=`/`model=` overrides — extend the helper with keyword defaults `provider="claude", model="claude-sonnet-5"` if it hard-codes them):

```python
    def test_two_providers_keep_two_open_calls_on_one_target(self, profile):
        snap = _snap(profile)
        a = _extract(_report(direction="bullish"), snap, profile, provider="claude", model="claude-opus-5")
        b = _extract(_report(direction="bearish"), snap, profile, provider="openai", model="gpt-5.6-sol")
        a.refresh_from_db()
        assert a.status == "open" and b.status == "open"
        assert AIPrediction.objects.filter(status="open").count() == 2

    def test_same_provider_model_still_dedups(self, profile):
        snap = _snap(profile)
        a = _extract(_report(direction="bullish"), snap, profile, provider="openai", model="gpt-5.6-sol")
        b = _extract(_report(direction="bullish"), snap, profile, provider="openai", model="gpt-5.6-sol")
        assert a.id == b.id
```

Also update the "Dedup invariant" test block below it (it asserts the constraint name / an `IntegrityError` on a duplicate open row): duplicates must now include the same `provider` and `model`, and the constraint name becomes `uniq_open_prediction_per_target`.

In `test_consensus_observer.py::test_consensus_fire_persists_consensus_report_message`, after the existing assertions add:

```python
    preds = AIPrediction.objects.filter(status="open").order_by("provider")
    assert [(p.provider, p.model) for p in preds] == [("claude", CLAUDE_MODEL), ("openai", OPENAI_MODEL)]
```

where `CLAUDE_MODEL`/`OPENAI_MODEL` are the model ids that test's two `ProviderConfig`s carry, and the patched `run_structured` returns an `ObservationReport` with `predicted_direction="bullish"`, `predicted_horizon_days=5`, `predicted_confidence=0.7` and one signal for the snapshot's primary ticker (read the test's report factory; extend it). Also assert the persisted consensus Message content has no `report` key inside `takes[*]` (`"report" not in body["takes"][0]`).

In `test_consensus_schema.py` add:

```python
def test_provider_take_report_is_in_memory_only():
    from apps.observer.schemas import ObservationReport, ProviderTake

    take = ProviderTake(
        provider="claude", model="claude-opus-5", bias="bullish", signal_bias={},
        report=ObservationReport(headline="h", bias="bullish", summary="s", next_check_in="n"),
    )
    assert take.report is not None
    assert "report" not in take.model_dump()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$PYTEST apps/observer/predictions/tests/test_extract.py apps/observer/tests/test_consensus_observer.py apps/observer/tests/test_consensus_schema.py`
Expected: FAIL — second provider's call collapses onto the first; `ProviderTake` rejects `report`; no predictions after a consensus fire.

- [ ] **Step 3: Implement**

`observer/models.py` — replace the constraint:

```python
            # ≤1 ``open`` prediction per target = (ticker, horizon_days, profile, provider,
            # model): two providers watching the same profile each keep their own call, so a
            # provider A/B never collapses into one row. The check-then-act in extract.py
            # races under worker concurrency; this partial unique index is the real guard
            # (extract.py catches the IntegrityError as the race-loser no-op).
            # nulls_distinct=False so a NULL profile still collides (PG15+).
            models.UniqueConstraint(
                fields=["ticker", "horizon_days", "profile", "provider", "model"],
                condition=models.Q(status="open"),
                name="uniq_open_prediction_per_target",
                nulls_distinct=False,
            ),
```

Run: `$RUN web uv run python manage.py makemigrations observer -n aiprediction_open_call_per_provider_model` → one `RemoveConstraint` + one `AddConstraint`.

`extract.py`:

```python
    existing = AIPrediction.objects.filter(
        ticker=ticker,
        horizon_days=horizon,
        profile=profile,
        provider=provider,
        model=model,
        status="open",
    ).first()
```

`observer/schemas.py::ProviderTake` — add:

```python
    report: ObservationReport | None = Field(
        default=None,
        exclude=True,
        description="The full report behind this take, for ledger extraction; never serialised.",
    )
```

`consensus.py` — pass `report=report` into the `ProviderTake(...)` constructor.

`run.py`:

```python
def _run_consensus_and_record(sched: ObserverSchedule, thread, payload_text: str, *, snap=None) -> None:
    ...
    msg = Message.objects.create(
        thread=thread,
        role="assistant",
        content={"kind": "consensus_report", "report": report.model_dump()},
        status="done",
    )
    for take in report.takes:
        if take.report is not None:
            _extract_prediction(
                take.report,
                snap=snap,
                message=msg,
                provider=take.provider,
                model=take.model,
                profile=sched.profile,
            )
```

and the call site: `_run_consensus_and_record(sched, thread, user_text, snap=snap)`. Update the function docstring's first paragraph to say each take's call is recorded in the ledger under that take's provider and model.

`CLAUDE.md` Prediction Ledger bullet: `Dedup: ≤1 \`open\` per \`(ticker, horizon, profile, provider, model)\`` and append "consensus fires extract one call per take."

- [ ] **Step 4: Run the tests**

Run: `$PYTEST apps/observer apps/analytics/tests/test_ai_calibration.py`
Expected: all pass; `$RUN web uv run python manage.py makemigrations --check --dry-run` → "No changes detected".

- [ ] **Step 5: Commit**

```bash
git add backend/apps/observer CLAUDE.md
LEFTHOOK=0 git commit -m "feat(observer): one open prediction per provider and model; consensus fires feed the ledger" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task B6: Schema regeneration and backend gates

**Files:**
- Modify: `backend/schema.yml`, `frontend/src/api/schema.d.ts` (generated)

- [ ] **Step 1: Regenerate the OpenAPI schema and the FE types**

```bash
$RUN web uv run python manage.py spectacular --file schema.yml
cd $WT/frontend && pnpm gen:api && cd $WT
git diff --stat backend/schema.yml frontend/src/api/schema.d.ts
```

Expected: both files change (`/api/aieval/runs/` gains `post`, `EvalRun` gains `provider`, the settings description is unchanged). If `schema.d.ts` shows no diff, the generation did not run — do not proceed.

- [ ] **Step 2: Run every backend gate**

```bash
$RUN -w /app web uv run ruff check backend
$RUN -w /app web uv run ruff format --check backend
$RUN -w /app web uv run mypy
$RUN -w /app web uv run lint-imports
$RUN -w /app web uv run deptry .
docker run --rm -v "$WT:/src" -w /src semgrep/semgrep semgrep scan --error --quiet --config tools/semgrep/rules backend/
$PYTEST
```

Expected: every tool clean; full suite green. Fix anything red in the task that introduced it (amend that commit or add a `fix(...)` commit).

- [ ] **Step 3: Commit**

```bash
git add backend/schema.yml frontend/src/api/schema.d.ts
LEFTHOOK=0 git commit -m "chore(api): regenerate OpenAPI schema and frontend types" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task F1: Frontend foundation — catalog hook, model defaults, `components/ai/` primitives

**Files:**
- Modify: `frontend/src/api/ai.ts`
- Modify: `frontend/src/api/observation.ts`
- Modify: `frontend/src/lib/modelDefaults.ts`
- Create: `frontend/src/hooks/useCatalog.ts`
- Create: `frontend/src/components/ai/ProviderSelect.tsx`, `ModelFacts.tsx`, `AiTargetPicker.tsx`, `AiAttribution.tsx`, `CapabilityHint.tsx`, `ModeBadges.tsx`
- Modify: `frontend/src/components/settings/ModelSelect.tsx`
- Modify: `frontend/src/components/ProviderModelPicker.tsx`
- Test: `frontend/src/__tests__/useCatalog.test.tsx`, `ProviderSelect.test.tsx`, `ModelFacts.test.tsx`, `AiTargetPicker.test.tsx`, `AiAttribution.test.tsx`, `CapabilityHint.test.tsx` (new); `ModelSelect.test.tsx`, `ProviderModelPicker.test.tsx`, `CompareDialog.test.tsx`, `ThreadDetailPage.test.tsx` (keep green)

**Interfaces:**
- Produces (used by F2–F7):
  - `api/ai.ts`: `type ProviderId = "claude" | "openai" | "local"`, `PROVIDER_IDS`, `PROVIDER_LABEL`, `AiModel.max_payload_tokens?: number`, `AiModelsResponse = { models: AiModel[]; defaults?: Partial<Record<ProviderId, string>> }`, `ProviderConfig.supports_tools?: boolean`.
  - `hooks/useCatalog.ts`: `useCatalog(): Catalog` with `models`, `defaults`, `isLoading`, `modelsFor(p)`, `defaultFor(p)`, `byId(id)`; `pickModelFor(provider, catalog): string`.
  - `api/observation.ts`: `ProviderTake`, `ConsensusReport`, `AiAttributionInfo`, `StructuredKind`, `StructuredReport`, `isConsensusReport(r)`.
  - `components/ai/ProviderSelect`: props `{ value; onChange(p: string); id?; ariaLabel?; describedBy?; emptyOption?: string; className? }`; exported `providerReadiness(cfg, provider): string`.
  - `components/ai/ModelFacts`: props `{ provider: string; modelId: string }`; exported `fmtTokens(n): string`.
  - `components/ai/AiTargetPicker`: props `{ value: { provider; model }; onChange(v); inherit?: { label: string }; facts?: boolean; providerLabel?: string; modelLabel?: string }`.
  - `components/ai/AiAttribution`: props `{ provider?; model?; cost?; qualifier?; className? }`, `data-testid="ai-attribution"`.
  - `components/ai/CapabilityHint`: props `{ feature: "tools" | "thinking" | "memory"; provider: string; supportsTools?: boolean }`; exported `capabilityHint(...)`.
  - `components/ai/ModeBadges`: props `{ mode: "full" | "diff"; structured; consensus; use_batch; investigate }`.
  - `components/settings/ModelSelect`: adds `ariaLabel?: string`, `facts?: boolean`.

- [ ] **Step 1: Data layer + defaults**

`frontend/src/api/ai.ts` — replace the top of the file down to `fetchAiModels` with:

```ts
import { ApiError, apiGet, apiPatch, apiPost } from "./client";

export type ProviderId = "claude" | "openai" | "local";
export const PROVIDER_IDS: readonly ProviderId[] = ["claude", "openai", "local"];
export const PROVIDER_LABEL: Record<ProviderId, string> = { claude: "Claude", openai: "OpenAI", local: "Local" };

/** Display name for a provider id; unknown ids render verbatim. */
export const providerLabel = (p: string): string => PROVIDER_LABEL[p as ProviderId] ?? p;

export type AiModel = {
  id: string; name: string; provider: string;
  input_per_mtok: number; output_per_mtok: number; cached_per_mtok: number;
  context_window: number; supports_vision: boolean;
  /** Snapshot payload budget the serializer targets for this model. */
  max_payload_tokens?: number;
};

/** `/api/schwab/models/`: the catalog plus the backend's per-provider fallback model. */
export type AiModelsResponse = {
  models: AiModel[];
  defaults?: Partial<Record<ProviderId, string>>;
};

export type ProviderConfig = {
  provider: ProviderId;
  base_url: string;
  default_model: string;
  enabled: boolean;
  supports_vision: boolean;
  supports_tools?: boolean;
  daily_cost_cap_usd: string;
  monthly_cost_cap_usd: string | null;
  api_key_present: boolean;
  discovered_models?: string[];
  models_synced_at?: string | null;
};

export const fetchAiModels = (provider?: string) => {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  return apiGet<AiModelsResponse>(`/api/schwab/models/${query}`);
};
```

(Keep everything below `fetchAiModels` unchanged.)

`frontend/src/lib/modelDefaults.ts` — set `claude: "claude-opus-5"`, `openai: "gpt-5.6-sol"`; leave `local: ""` and `DEFAULT_COMPARE_BRANCH` (`gpt-5-mini`). Rewrite the header comment to: "Seed values for provider/model pickers before `/api/schwab/models/` (`useCatalog().defaults`) has loaded. The backend catalog is the source of truth; when a default id churns there, update it here too."

`frontend/src/hooks/useCatalog.ts` (new — separate from `useAiModels.ts` so tests that mock `@/hooks/useAiModels` keep working):

```ts
import { useAiModels } from "@/hooks/useAiModels";
import type { AiModel } from "@/api/ai";
import { DEFAULT_MODEL_BY_PROVIDER } from "@/lib/modelDefaults";

export type Catalog = {
  models: AiModel[];
  /** Backend fallback model per provider (API value, else the seed literal). */
  defaults: Record<string, string>;
  isLoading: boolean;
  modelsFor: (provider: string) => AiModel[];
  defaultFor: (provider: string) => string;
  byId: (id: string) => AiModel | undefined;
};

export function useCatalog(): Catalog {
  const { data, isLoading } = useAiModels();
  const models = data?.models ?? [];
  const defaults: Record<string, string> = { ...DEFAULT_MODEL_BY_PROVIDER, ...(data?.defaults ?? {}) };
  return {
    models,
    defaults,
    isLoading,
    modelsFor: (provider) => models.filter((m) => m.provider === provider),
    defaultFor: (provider) => defaults[provider] ?? "",
    byId: (id) => models.find((m) => m.id === id),
  };
}

/** The model a picker lands on after a provider change: the provider's default when
 * the catalog lists it, else the first catalog model, else "" (local: user-typed). */
export function pickModelFor(provider: string, catalog: Catalog): string {
  const list = catalog.modelsFor(provider);
  const d = catalog.defaultFor(provider);
  if (d && list.some((m) => m.id === d)) return d;
  return list[0]?.id ?? "";
}
```

`frontend/src/api/observation.ts` — append:

```ts
/** One provider's opinion inside a consensus fan-out (mirrors observer/schemas.py ProviderTake). */
export type ProviderTake = {
  provider: string;
  model: string;
  bias: Bias;
  signal_bias: Record<string, Bias>;
};

/** Cross-provider agreement signal (mirrors observer/schemas.py ConsensusReport).
 * `per_ticker[ticker].takes` is keyed `"<provider>/<model>"`. */
export type ConsensusReport = {
  n_providers: number;
  bias_agreement: number | null;
  modal_bias: Bias | null;
  divergent: boolean;
  per_ticker: Record<string, { agreement: number | null; modal: Bias | null; takes: Record<string, Bias> }>;
  takes: ProviderTake[];
  note: string;
};

export type AiAttributionInfo = { provider: string; model: string };

/** Post-mortem narrative as stored in `PostMortem.report` / the `postmortem_report` Message. */
export type PostMortemReportContent = {
  summary: string;
  what_worked: string[];
  what_missed: string[];
  lessons: string[];
  would_repeat: boolean;
  ai?: AiAttributionInfo;
};

/** War Room synthesis as spread into the `warroom_verdict` Message content. */
export type WarRoomVerdictContent = {
  verdict?: string;
  confidence?: number;
  strongest_bull?: string;
  strongest_bear?: string;
  what_would_change_my_mind?: string;
  ai?: AiAttributionInfo;
};

/** Every `content.kind` the backend writes on an assistant/system Message. */
export type StructuredKind =
  | "structured_observation"
  | "consensus_report"
  | "postmortem_report"
  | "warroom_verdict"
  | "cached_observation"
  | "capability_warning"
  | "investigation";
export type StructuredReport = ObservationReport | ConsensusReport | PostMortemReportContent;

export function isConsensusReport(r: StructuredReport | undefined | null): r is ConsensusReport {
  return !!r && typeof r === "object" && "n_providers" in r;
}
export function isPostMortemReport(r: StructuredReport | undefined | null): r is PostMortemReportContent {
  return !!r && typeof r === "object" && "would_repeat" in r;
}
```

Also extend `ObservationReport` in the same file with the optional fields the backend emits (they feed the Prediction Ledger and were never typed):

```ts
  predicted_direction?: "bullish" | "bearish" | "neutral" | null;
  predicted_horizon_days?: number | null;
  predicted_confidence?: number | null;
  grounding?: string[];
```

- [ ] **Step 2: Write the primitive tests (failing)**

`frontend/src/__tests__/useCatalog.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));

import { pickModelFor, useCatalog } from "@/hooks/useCatalog";

const MODELS = [
  { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude", input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5, context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000 },
  { id: "claude-sonnet-5", name: "Claude Sonnet 5", provider: "claude", input_per_mtok: 2, output_per_mtok: 10, cached_per_mtok: 0.2, context_window: 1_000_000, supports_vision: true },
  { id: "gpt-5", name: "GPT-5", provider: "openai", input_per_mtok: 1.25, output_per_mtok: 10, cached_per_mtok: 0.125, context_window: 400_000, supports_vision: true },
];

describe("useCatalog", () => {
  it("prefers API defaults over the seed literals", () => {
    mockUseAiModels.mockReturnValue({ data: { models: MODELS, defaults: { claude: "claude-sonnet-5" } }, isLoading: false });
    const { result } = renderHook(() => useCatalog());
    expect(result.current.defaultFor("claude")).toBe("claude-sonnet-5");
    expect(result.current.defaultFor("openai")).toBe("gpt-5.6-sol"); // seed fallback
    expect(result.current.modelsFor("openai").map((m) => m.id)).toEqual(["gpt-5"]);
    expect(result.current.byId("claude-opus-5")?.max_payload_tokens).toBe(150_000);
  });

  it("pickModelFor uses the default when listed, else the first model, else blank", () => {
    mockUseAiModels.mockReturnValue({ data: { models: MODELS }, isLoading: false });
    const { result } = renderHook(() => useCatalog());
    expect(pickModelFor("claude", result.current)).toBe("claude-opus-5");
    expect(pickModelFor("openai", result.current)).toBe("gpt-5"); // gpt-5.6-sol not listed
    expect(pickModelFor("local", result.current)).toBe("");
  });
});
```

`frontend/src/__tests__/ProviderSelect.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

const mockUseProviderConfigs = vi.fn();
vi.mock("@/hooks/useProviderConfigs", () => ({ useProviderConfigs: () => mockUseProviderConfigs() }));

import ProviderSelect, { providerReadiness } from "@/components/ai/ProviderSelect";

const CFG = (o: object) => ({
  provider: "claude", base_url: "", default_model: "", enabled: true, supports_vision: true,
  daily_cost_cap_usd: "10", monthly_cost_cap_usd: null, api_key_present: false, ...o,
});

describe("ProviderSelect", () => {
  it("labels each provider with its readiness", async () => {
    mockUseProviderConfigs.mockReturnValue({ data: [
      CFG({ provider: "claude", api_key_present: true }),
      CFG({ provider: "openai", enabled: false, api_key_present: true }),
      CFG({ provider: "local", base_url: "" }),
    ] });
    const onChange = vi.fn();
    render(<ProviderSelect ariaLabel="Default provider" value="claude" onChange={onChange} emptyOption="Inherit" />);
    const sel = screen.getByLabelText("Default provider");
    const texts = Array.from(sel.querySelectorAll("option")).map((o) => o.textContent);
    expect(texts).toEqual(["Inherit", "Claude · ready", "OpenAI · disabled", "Local · no base URL"]);
    await userEvent.selectOptions(sel, "openai");
    expect(onChange).toHaveBeenCalledWith("openai");
    await userEvent.selectOptions(sel, "");
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("providerReadiness handles a missing config", () => {
    expect(providerReadiness(undefined, "openai")).toBe("no key");
    expect(providerReadiness(undefined, "local")).toBe("no base URL");
  });
});
```

`frontend/src/__tests__/ModelFacts.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));

import ModelFacts, { fmtTokens } from "@/components/ai/ModelFacts";

const DATA = { models: [
  { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude", input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5, context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000 },
], defaults: { claude: "claude-opus-5" } };

describe("ModelFacts", () => {
  it("formats token counts", () => {
    expect(fmtTokens(1_000_000)).toBe("1M");
    expect(fmtTokens(1_050_000)).toBe("1.05M");
    expect(fmtTokens(150_000)).toBe("150k");
    expect(fmtTokens(40_000)).toBe("40k");
  });

  it("shows prices, context, payload budget and the default pill", () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    render(<ModelFacts provider="claude" modelId="claude-opus-5" />);
    const line = screen.getByTestId("model-facts").textContent ?? "";
    expect(line).toContain("$5.00 in");
    expect(line).toContain("$0.50 cached");
    expect(line).toContain("$25.00 out");
    expect(line).toContain("1M ctx");
    expect(line).toContain("150k payload");
    expect(line).toContain("vision");
    expect(screen.getByText("default")).toBeInTheDocument();
  });

  it("explains unknown ids per provider", () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    render(<ModelFacts provider="openai" modelId="gpt-99" />);
    expect(screen.getByText(/not in catalog/i)).toBeInTheDocument();
  });

  it("describes local models as free", () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    render(<ModelFacts provider="local" modelId="llama3" />);
    expect(screen.getByText(/no API cost/i)).toBeInTheDocument();
  });
});
```

`frontend/src/__tests__/AiTargetPicker.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));
vi.mock("@/hooks/useProviderConfigs", () => ({ useProviderConfigs: () => ({ data: [] }) }));

import AiTargetPicker from "@/components/ai/AiTargetPicker";

const DATA = { models: [
  { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude", input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5, context_window: 1_000_000, supports_vision: true },
  { id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai", input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4, context_window: 1_050_000, supports_vision: true },
  { id: "gpt-5-mini", name: "GPT-5 mini", provider: "openai", input_per_mtok: 0.25, output_per_mtok: 2, cached_per_mtok: 0.025, context_window: 400_000, supports_vision: true },
], defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" } };

describe("AiTargetPicker", () => {
  it("switching provider lands on that provider's default model", async () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    const onChange = vi.fn();
    render(<AiTargetPicker value={{ provider: "claude", model: "claude-opus-5" }} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText("Provider"), "openai");
    expect(onChange).toHaveBeenCalledWith({ provider: "openai", model: "gpt-5.6-sol" });
  });

  it("inherit mode emits blanks and hides the model select", async () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    const onChange = vi.fn();
    const { rerender } = render(
      <AiTargetPicker value={{ provider: "claude", model: "claude-opus-5" }} onChange={onChange}
        inherit={{ label: "Inherit from profile — Claude · claude-opus-5" }} />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Provider"), "");
    expect(onChange).toHaveBeenCalledWith({ provider: "", model: "" });
    rerender(
      <AiTargetPicker value={{ provider: "", model: "" }} onChange={onChange}
        inherit={{ label: "Inherit from profile — Claude · claude-opus-5" }} />,
    );
    expect(screen.queryByLabelText("Model")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Provider")).toHaveValue("");
  });
});
```

`frontend/src/__tests__/AiAttribution.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import AiAttribution from "@/components/ai/AiAttribution";

describe("AiAttribution", () => {
  it("renders provider name, model id, cost and qualifier", () => {
    render(<AiAttribution provider="openai" model="gpt-5.6-sol" cost="0.0123" qualifier="override" />);
    const pill = screen.getByTestId("ai-attribution");
    expect(pill.textContent).toBe("OpenAI · gpt-5.6-sol · $0.0123 (override)");
  });

  it("renders nothing without provider or model", () => {
    const { container } = render(<AiAttribution />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

`frontend/src/__tests__/CapabilityHint.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { capabilityHint } from "@/components/ai/CapabilityHint";

describe("capabilityHint", () => {
  it("is silent on Claude", () => {
    expect(capabilityHint("thinking", "claude", true)).toBeNull();
    expect(capabilityHint("tools", "claude", false)).toBeNull();
  });
  it("flags Claude-only features on other providers", () => {
    expect(capabilityHint("thinking", "openai", true)).toBe("Claude only — ignored on OpenAI");
    expect(capabilityHint("memory", "local", true)).toBe("Claude only — ignored on Local");
  });
  it("flags tools only when the provider config has them off", () => {
    expect(capabilityHint("tools", "openai", true)).toBeNull();
    expect(capabilityHint("tools", "openai", false)).toBe("Tool use is off for OpenAI in Settings → AI Providers");
  });
});
```

Run: `cd $WT/frontend && pnpm exec vitest run --project unit src/__tests__/useCatalog.test.tsx src/__tests__/ProviderSelect.test.tsx src/__tests__/ModelFacts.test.tsx src/__tests__/AiTargetPicker.test.tsx src/__tests__/AiAttribution.test.tsx src/__tests__/CapabilityHint.test.tsx`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement the primitives**

`frontend/src/components/ai/ProviderSelect.tsx`:

```tsx
import { PROVIDER_IDS, PROVIDER_LABEL, type ProviderConfig, type ProviderId } from "@/api/ai";
import { useProviderConfigs } from "@/hooks/useProviderConfigs";

type Props = {
  value: string;
  onChange: (provider: string) => void;
  id?: string;
  ariaLabel?: string;
  describedBy?: string;
  /** When set, a first option with this label emits "" (e.g. "Inherit from profile", "None"). */
  emptyOption?: string;
  className?: string;
};

/** One-word readiness for a provider row: ready / no key / no base URL / disabled. */
export function providerReadiness(cfg: ProviderConfig | undefined, provider: ProviderId): string {
  if (!cfg) return provider === "local" ? "no base URL" : "no key";
  if (!cfg.enabled) return "disabled";
  if (provider === "local") return cfg.base_url ? "ready" : "no base URL";
  return cfg.api_key_present ? "ready" : "no key";
}

export default function ProviderSelect({ value, onChange, id, ariaLabel, describedBy, emptyOption, className }: Props) {
  const { data: configs } = useProviderConfigs();
  return (
    <select
      id={id}
      aria-label={ariaLabel}
      aria-describedby={describedBy}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`ledger-input py-2 ${className ?? ""}`}
    >
      {emptyOption !== undefined && <option value="">{emptyOption}</option>}
      {PROVIDER_IDS.map((p) => (
        <option key={p} value={p}>
          {PROVIDER_LABEL[p]} · {providerReadiness(configs?.find((c) => c.provider === p), p)}
        </option>
      ))}
    </select>
  );
}
```

`frontend/src/components/ai/ModelFacts.tsx`:

```tsx
import { useCatalog } from "@/hooks/useCatalog";

/** 1_000_000 → "1M", 1_050_000 → "1.05M", 150_000 → "150k". */
export function fmtTokens(n: number): string {
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    return `${Number.isInteger(m) ? m : m.toFixed(2).replace(/0+$/, "")}M`;
  }
  return `${Math.round(n / 1000)}k`;
}

const money = (n: number) => `$${n.toFixed(2)}`;

export default function ModelFacts({ provider, modelId }: { provider: string; modelId: string }) {
  const { byId, defaultFor } = useCatalog();
  if (!modelId) return null;
  const m = byId(modelId);
  const base = "font-mono text-[11px] text-ink-400 tabular-nums flex flex-wrap items-center gap-x-1.5";
  if (!m || m.provider !== provider) {
    return (
      <p data-testid="model-facts" className={base}>
        {provider === "local"
          ? "local model — no API cost · 40k payload budget"
          : "not in catalog — billed at the provider's top rate · 40k payload budget"}
      </p>
    );
  }
  const parts = [
    `${money(m.input_per_mtok)} in`,
    `${money(m.cached_per_mtok)} cached`,
    `${money(m.output_per_mtok)} out per MTok`,
    `${fmtTokens(m.context_window)} ctx`,
    m.max_payload_tokens != null ? `${fmtTokens(m.max_payload_tokens)} payload` : null,
    m.supports_vision ? "vision" : null,
  ].filter(Boolean) as string[];
  return (
    <p data-testid="model-facts" className={base}>
      {parts.map((p, i) => (
        <span key={p}>{i > 0 && <span className="text-ink-600"> · </span>}{p}</span>
      ))}
      {defaultFor(provider) === m.id && (
        <span className="ledger-pill ml-1" data-tone="copper">default</span>
      )}
    </p>
  );
}
```

`frontend/src/components/settings/ModelSelect.tsx` — add `ariaLabel?: string; facts?: boolean;` to `Props`, pass `aria-label={ariaLabel}` on the `<select>`, read the catalog via `useCatalog()` instead of `useAiModels(provider)` (`const { modelsFor } = useCatalog(); const options = explicit ? … : modelsFor(provider).map(...)`), and render `{facts && <ModelFacts provider={provider} modelId={value} />}` after the custom input. Option text stays `o.name`; the Custom… option and the `Custom model id` input stay.

`frontend/src/components/ai/AiTargetPicker.tsx`:

```tsx
import ProviderSelect from "@/components/ai/ProviderSelect";
import ModelSelect from "@/components/settings/ModelSelect";
import { pickModelFor, useCatalog } from "@/hooks/useCatalog";
import { useProviderConfigs } from "@/hooks/useProviderConfigs";

export type AiTarget = { provider: string; model: string };

type Props = {
  value: AiTarget;
  onChange: (v: AiTarget) => void;
  /** Adds an "inherit" first option; picking it emits { provider: "", model: "" }. */
  inherit?: { label: string };
  facts?: boolean;
  providerLabel?: string;
  modelLabel?: string;
};

export default function AiTargetPicker({
  value, onChange, inherit, facts, providerLabel = "Provider", modelLabel = "Model",
}: Props) {
  const catalog = useCatalog();
  const { data: configs } = useProviderConfigs();
  const inheriting = inherit !== undefined && value.provider === "";
  const discovered = configs?.find((c) => c.provider === "local")?.discovered_models ?? [];
  return (
    <div className="grid gap-3 sm:grid-cols-[minmax(0,200px)_1fr]">
      <ProviderSelect
        ariaLabel={providerLabel}
        value={value.provider}
        emptyOption={inherit?.label}
        onChange={(provider) =>
          onChange(provider === "" ? { provider: "", model: "" } : { provider, model: pickModelFor(provider, catalog) })}
      />
      {!inheriting && (
        <ModelSelect
          ariaLabel={modelLabel}
          provider={value.provider}
          value={value.model}
          models={value.provider === "local" && discovered.length > 0 ? discovered : undefined}
          onChange={(model) => onChange({ ...value, model })}
          facts={facts}
        />
      )}
    </div>
  );
}
```

`frontend/src/components/ai/AiAttribution.tsx`:

```tsx
import { providerLabel } from "@/api/ai";
import { usd } from "@/utils/format";

type Props = {
  provider?: string | null;
  model?: string | null;
  cost?: string | number | null;
  /** e.g. "override" / "profile" — rendered dimmed in parentheses. */
  qualifier?: string;
  className?: string;
};

/** `Provider · model-id · $cost (qualifier)` as a mono ledger pill. */
export default function AiAttribution({ provider, model, cost, qualifier, className }: Props) {
  if (!provider && !model) return null;
  const parts = [provider ? providerLabel(provider) : null, model || null, cost != null && cost !== "" ? usd(cost) : null]
    .filter(Boolean) as string[];
  return (
    <span data-testid="ai-attribution" className={`ledger-pill font-mono ${className ?? ""}`}>
      {parts.join(" · ")}
      {qualifier && <span className="text-ink-500"> ({qualifier})</span>}
    </span>
  );
}
```

(Confirm `usd("0.0123")` yields `$0.0123` from `frontend/src/utils/format.ts`; adjust the test expectation only if `usd`'s formatting differs — do not change `usd`.)

`frontend/src/components/ai/CapabilityHint.tsx`:

```tsx
import { providerLabel } from "@/api/ai";

export type Feature = "tools" | "thinking" | "memory";

/** The consequence of enabling `feature` on `provider`, or null when fully supported. */
export function capabilityHint(feature: Feature, provider: string, supportsTools: boolean | undefined): string | null {
  if (provider === "claude") return null;
  const name = providerLabel(provider);
  if (feature === "thinking" || feature === "memory") return `Claude only — ignored on ${name}`;
  return supportsTools === false ? `Tool use is off for ${name} in Settings → AI Providers` : null;
}

export default function CapabilityHint(props: { feature: Feature; provider: string; supportsTools?: boolean }) {
  const text = capabilityHint(props.feature, props.provider, props.supportsTools);
  return text ? <span role="note" className="text-[11px] text-copper-300">{text}</span> : null;
}
```

`frontend/src/components/ai/ModeBadges.tsx`:

```tsx
type Props = { mode: "full" | "diff"; structured: boolean; consensus: boolean; use_batch: boolean; investigate?: boolean };

/** A schedule's AI mode as pills: payload shape, then each opt-in flag. */
export default function ModeBadges({ mode, structured, consensus, use_batch, investigate }: Props) {
  const flags = [structured && "structured", consensus && "consensus", use_batch && "batch", investigate && "investigate"]
    .filter(Boolean) as string[];
  return (
    <span className="inline-flex flex-wrap gap-1" data-testid="mode-badges">
      <span className="ledger-pill">{mode}</span>
      {flags.map((f) => <span key={f} className="ledger-pill" data-tone="copper">{f}</span>)}
    </span>
  );
}
```

`frontend/src/components/ProviderModelPicker.tsx` — keep its compact two-select layout (its tests pin DOM order: provider combobox first, model combobox second; unique provider option values; the placeholder text). Change: list the fixed provider trio so Local is selectable, use `pickModelFor` on provider change, and add a mono text input when the provider has no catalog rows:

```tsx
import { PROVIDER_IDS, PROVIDER_LABEL } from "@/api/ai";
import { pickModelFor, useCatalog } from "@/hooks/useCatalog";

type Value = { provider: string; model: string };
type Props = { value: Value; onChange: (v: Value) => void };

/** Compact provider + model picker for the thread composer and Compare dialog. */
export default function ProviderModelPicker({ value, onChange }: Props) {
  const catalog = useCatalog();
  const modelsForProvider = catalog.modelsFor(value.provider);
  return (
    <div className="flex gap-2 text-[12px]">
      <select
        aria-label="Provider"
        value={value.provider}
        onChange={(e) => {
          const provider = e.target.value;
          onChange({ provider, model: pickModelFor(provider, catalog) });
        }}
        className="ledger-input py-1 pr-6 text-[12px] font-mono uppercase tracking-wider"
      >
        {PROVIDER_IDS.map((p) => <option key={p} value={p}>{PROVIDER_LABEL[p]}</option>)}
      </select>
      <select
        aria-label="Model"
        value={value.model}
        onChange={(e) => onChange({ ...value, model: e.target.value })}
        className="ledger-input flex-1 py-1 pr-6 text-[12px] font-mono"
      >
        {modelsForProvider.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        {modelsForProvider.length === 0 && (
          <option value={value.model}>(no catalog models — type your own)</option>
        )}
      </select>
      {modelsForProvider.length === 0 && (
        <input
          aria-label="Model id"
          value={value.model}
          onChange={(e) => onChange({ ...value, model: e.target.value })}
          placeholder="model id"
          className="ledger-input flex-1 py-1 text-[12px] font-mono"
        />
      )}
    </div>
  );
}
```

(The test "renders provider options from data (unique providers)" passes because the trio is unique and contains `claude` and `openai`.)

- [ ] **Step 4: Run the primitive tests and the suites that pin defaults**

Run: `cd $WT/frontend && pnpm exec vitest run --project unit src/__tests__/useCatalog.test.tsx src/__tests__/ProviderSelect.test.tsx src/__tests__/ModelFacts.test.tsx src/__tests__/AiTargetPicker.test.tsx src/__tests__/AiAttribution.test.tsx src/__tests__/CapabilityHint.test.tsx src/__tests__/ModelSelect.test.tsx src/__tests__/ProviderModelPicker.test.tsx src/__tests__/CompareDialog.test.tsx src/__tests__/ThreadDetailPage.test.tsx src/__tests__/profiles.types.test.ts`
Expected: all pass. If `CompareDialog.test` or `ThreadDetailPage.test` assert the seeded default is `claude-sonnet-4-6`, change that expectation (and its mocked catalog row) to `claude-opus-5` — the seed changed on purpose.

- [ ] **Step 5: Whole-suite + lint**

Run: `cd $WT/frontend && pnpm lint && pnpm exec vitest run --project unit`
Expected: clean. Then commit:

```bash
git add frontend/src/api/ai.ts frontend/src/api/observation.ts frontend/src/lib/modelDefaults.ts frontend/src/hooks/useCatalog.ts frontend/src/components/ai frontend/src/components/settings/ModelSelect.tsx frontend/src/components/ProviderModelPicker.tsx frontend/src/__tests__
LEFTHOOK=0 git commit -m "feat(frontend): catalog hook, provider-neutral AI primitives, current default models" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task F2: Settings › AI Providers — capabilities, catalog default, model catalog panel

**Owns:** `frontend/src/components/settings/ProviderCard.tsx`, `frontend/src/components/settings/ModelCatalogPanel.tsx` (new), `frontend/src/pages/settings/ProvidersSettings.tsx`, `frontend/src/__tests__/ProviderCard.test.tsx`, `frontend/src/__tests__/ModelCatalogPanel.test.tsx` (new), `frontend/src/__tests__/ProvidersSettings.test.tsx`.

**Interfaces:** consumes F1 (`useCatalog`, `ModelFacts`, `ProviderConfig.supports_tools`).

**Preserved:** label `"<Provider> API key"`, `Daily cap (USD)`, `Monthly cap (USD)`, `Base URL`, switch `"<Provider> enabled"`, button `Save`, `data-testid="provider-card-<p>"`, `/no API cost/i` note for local, the save-body rules (`api_key_write` only when typed; `monthly_cost_cap_usd: null` when blank), heading `AI Providers`.

- [ ] **Step 1: Failing tests**

Append to `ProviderCard.test.tsx` (its `beforeEach` mocks `useAiModels` — extend the mocked data with `defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" }` and add a `claude-opus-5` row):

```tsx
describe("ProviderCard — catalog default and capabilities", () => {
  it("falls back to the catalog default model when none is stored", () => {
    mockUseProviderConfigs.mockReturnValue({ data: [cfg({ default_model: "" })] });
    render(<ProviderCard provider="claude" />);
    expect(screen.getByRole("combobox", { name: "Default model" })).toHaveValue("claude-opus-5");
    expect(screen.getByText(/doesn't name a model/i)).toBeInTheDocument();
  });

  it("offers tool-use and vision toggles for OpenAI and saves only touched ones", async () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "openai", default_model: "gpt-5.6-sol", supports_tools: true, supports_vision: true })],
    });
    render(<ProviderCard provider="openai" />);
    await userEvent.click(screen.getByRole("switch", { name: "Tool use" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const [arg] = mockMutate.mock.calls[0];
    expect(arg.body.supports_tools).toBe(false);
    expect("supports_vision" in arg.body).toBe(false);
  });

  it("shows Claude's fixed capability line instead of toggles", () => {
    render(<ProviderCard provider="claude" />);
    expect(screen.queryByRole("switch", { name: "Tool use" })).not.toBeInTheDocument();
    expect(screen.getByText(/structured output/i)).toBeInTheDocument();
  });
});
```

`frontend/src/__tests__/ModelCatalogPanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));

import ModelCatalogPanel from "@/components/settings/ModelCatalogPanel";

describe("ModelCatalogPanel", () => {
  it("lists every catalog model with prices, budgets and the default marker", () => {
    mockUseAiModels.mockReturnValue({ data: { models: [
      { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude", input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5, context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000 },
      { id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai", input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4, context_window: 1_050_000, supports_vision: true, max_payload_tokens: 300_000 },
    ], defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" } }, isLoading: false });
    render(<ModelCatalogPanel />);
    expect(screen.getByRole("heading", { name: /model catalog/i })).toBeInTheDocument();
    const opus = screen.getByTestId("catalog-row-claude-opus-5");
    expect(opus.textContent).toContain("$5.00");
    expect(opus.textContent).toContain("150k");
    expect(opus.textContent).toContain("default");
    expect(screen.getByTestId("catalog-row-gpt-5.6-sol").textContent).toContain("1.05M");
    expect(screen.getByText(/billed at its provider's top rate/i)).toBeInTheDocument();
  });

  it("renders skeleton rows while loading", () => {
    mockUseAiModels.mockReturnValue({ data: undefined, isLoading: true });
    render(<ModelCatalogPanel />);
    expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
  });
});
```

In `ProvidersSettings.test.tsx`, also mock `@/components/settings/ModelCatalogPanel` (`default: () => <div data-testid="catalog-panel" />`) and assert it renders.

Run the three files; expected FAIL.

- [ ] **Step 2: Implement `ProviderCard`**

- `Draft` gains `supports_tools?: boolean; supports_vision?: boolean`.
- `resolveFields` takes a `catalogDefault: string` argument: `model: draft.default_model ?? cfg?.default_model ?? catalogDefault`; `deriveState` receives it from `useCatalog().defaultFor(provider)` in the component. Delete the `DEFAULT_MODEL_BY_PROVIDER` import.
- `ModelField`: hint becomes `"Used when a profile or schedule doesn't name a model."` (keep the local "Test the connection…" hint when `isLocal && discovered.length === 0`), and pass `facts` to `ModelSelect`.
- New `CapabilitiesRow` rendered after `ModelField` in the grid (`sm:col-span-2`):

```tsx
const CLAUDE_CAPS = "Streaming · tools · structured output · thinking · memory · files · citations · batches";

function CapabilitiesRow({
  provider, supportsTools, supportsVision, setDraft,
}: { provider: ProviderId; supportsTools: boolean; supportsVision: boolean; setDraft: SetDraft }) {
  return (
    <div className="sm:col-span-2 border-t border-rule-soft pt-4">
      <p className="font-mono text-[10px] uppercase tracking-loose2 text-copper-400">Capabilities</p>
      {provider === "claude" ? (
        <p className="mt-1.5 text-[12px] text-ink-300">{CLAUDE_CAPS}</p>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-6 text-[12px] text-ink-300">
          <span>Streaming · structured output</span>
          <label className="flex items-center gap-2">
            <Toggle checked={supportsTools} onChange={(v) => setDraft({ supports_tools: v })} label="Tool use" />
            <span>Tool use</span>
          </label>
          <label className="flex items-center gap-2">
            <Toggle checked={supportsVision} onChange={(v) => setDraft({ supports_vision: v })} label="Vision" />
            <span>Vision</span>
          </label>
          <span className="text-ink-500">Thinking, memory, files, citations and batches are Claude only.</span>
        </div>
      )}
    </div>
  );
}
```

  `supportsTools = draft.supports_tools ?? cfg?.supports_tools ?? true`, `supportsVision = draft.supports_vision ?? cfg?.supports_vision ?? true` (add both to `ResolvedFields`/`DerivedState`).
- `save()`: after building `body`, add `if (draft.supports_tools !== undefined) body.supports_tools = draft.supports_tools; if (draft.supports_vision !== undefined) body.supports_vision = draft.supports_vision;`. For OpenAI, include `base_url: d.baseUrl` in the body (the backend accepts it for every provider).
- Give the default-model `ModelSelect` `ariaLabel="Default model"` (the `Field` label already links by `id`; the aria-label makes `getByRole("combobox", { name })` deterministic).
- **OpenAI base URL + probe:** render a `Base URL (optional)` field for `provider === "openai"` (hint "Leave blank for api.openai.com; set for a proxy or Azure-compatible endpoint.") with the same `Test connection` button and `probeMsg` line the Local card has (the backend probe already allows `openai`; it lists models with the stored key). Extract today's `LocalBaseUrlField` into `BaseUrlField({ label, hint, required, … })` and use it for both. `baseUrlInvalid` stays `isLocal && baseUrl.trim() === ""`; for OpenAI the probe button is enabled when a key is stored or typed.
- **Synced line:** under the model field for OpenAI/Local, when `cfg?.models_synced_at` is set: `Models synced {formatRelative(models_synced_at)} · {discovered.length} discovered` (`formatRelative` from `@/utils/format`), `font-mono text-[11px] text-ink-400`.
- Add one test: `it("offers an optional base URL and Test connection for OpenAI", …)` asserting `getByLabelText("Base URL (optional)")` and the `Test connection` button exist for `provider="openai"`, and that Save includes `base_url` when typed.

- [ ] **Step 3: Implement `ModelCatalogPanel`**

```tsx
import { PROVIDER_IDS, PROVIDER_LABEL } from "@/api/ai";
import { fmtTokens } from "@/components/ai/ModelFacts";
import { SkeletonRows } from "@/components/Skeleton";
import { useCatalog } from "@/hooks/useCatalog";

const money = (n: number) => `$${n.toFixed(2)}`;

export default function ModelCatalogPanel() {
  const { models, defaultFor, isLoading } = useCatalog();
  return (
    <section className="ledger-surface p-5" aria-labelledby="model-catalog-heading">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="ledger-eyebrow">Reference</p>
          <h3 id="model-catalog-heading" className="font-display text-[1.05rem] text-ink-50">Model catalog</h3>
        </div>
        <p className="text-[11px] text-ink-400 max-w-sm text-right">
          Prices per million tokens; the payload budget is how much snapshot the serializer sends before pruning.
        </p>
      </div>
      {isLoading ? (
        <div className="mt-4"><SkeletonRows rows={4} /></div>
      ) : (
        PROVIDER_IDS.map((p) => {
          const rows = models.filter((m) => m.provider === p);
          if (rows.length === 0) return null;
          return (
            <div key={p} className="mt-5 min-w-0 overflow-x-auto">
              <p className="font-mono text-[10px] uppercase tracking-loose2 text-copper-400 mb-2">{PROVIDER_LABEL[p]}</p>
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-ink-400 text-left">
                    <th className="py-1 pr-3 font-normal">Model</th>
                    <th className="py-1 pr-3 font-normal text-right">Input</th>
                    <th className="py-1 pr-3 font-normal text-right">Cached</th>
                    <th className="py-1 pr-3 font-normal text-right">Output</th>
                    <th className="py-1 pr-3 font-normal text-right">Context</th>
                    <th className="py-1 pr-3 font-normal text-right">Payload</th>
                    <th className="py-1 font-normal">Vision</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((m) => (
                    <tr key={m.id} data-testid={`catalog-row-${m.id}`} className="border-t border-rule-soft align-top">
                      <td className="py-1.5 pr-3">
                        <div className="text-ink-100 flex items-center gap-2">
                          {m.name}
                          {defaultFor(p) === m.id && <span className="ledger-pill" data-tone="copper">default</span>}
                        </div>
                        <div className="font-mono text-[11px] text-ink-400">{m.id}</div>
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{money(m.input_per_mtok)}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{money(m.cached_per_mtok)}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{money(m.output_per_mtok)}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{fmtTokens(m.context_window)}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{m.max_payload_tokens != null ? fmtTokens(m.max_payload_tokens) : "40k"}</td>
                      <td className="py-1.5 text-ink-300">{m.supports_vision ? "yes" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })
      )}
      <p className="mt-4 border-t border-rule-soft pt-3 text-[11px] text-ink-400">
        These prices drive cost estimates and caps. A model id that is not listed is billed at its provider's
        top rate and capped at a 40k-token snapshot payload — add it to the catalog first.
      </p>
    </section>
  );
}
```

`ProvidersSettings.tsx`: render `<ModelCatalogPanel />` after the cards inside `SettingsSection`.

Add `frontend/src/components/settings/ModelCatalogPanel.stories.tsx` (mirror `ProviderCard.stories.tsx`'s msw/hook setup: one story with a mocked `/api/schwab/models/` payload of three rows and defaults, `play` asserting the heading is visible).

- [ ] **Step 4: Run and commit**

Run: `cd <worktree>/frontend && pnpm exec vitest run --project unit src/__tests__/ProviderCard.test.tsx src/__tests__/ModelCatalogPanel.test.tsx src/__tests__/ProvidersSettings.test.tsx src/__tests__/storyCoverage.test.ts && pnpm lint`
Expected: pass, clean.

```bash
git add frontend/src/components/settings frontend/src/pages/settings/ProvidersSettings.tsx frontend/src/__tests__/ProviderCard.test.tsx frontend/src/__tests__/ModelCatalogPanel.test.tsx frontend/src/__tests__/ProvidersSettings.test.tsx
LEFTHOOK=0 git commit -m "feat(frontend): provider capabilities toggles, catalog default fallback, model catalog panel" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task F3: Settings › System — provider selects and a catalog-backed eval model

**Owns:** `frontend/src/api/settings.ts`, `frontend/src/pages/settings/SystemSettings.tsx`, `frontend/src/__tests__/SystemSettings.test.tsx`.

**Interfaces:** consumes F1 (`ProviderSelect`, `ModelSelect` with `ariaLabel`/`facts`, `useCatalog`); consumes B4 (`aieval_scheduled_provider`).

**Preserved:** `getByLabelText(/OHLC bars/i)` numeric inputs, button `Save changes`, `skeleton-row` skeletons, the PATCH-only-changed-fields behaviour, section headings `Data retention` / `AI failover` / `Observer response cache` / `Scheduled eval`.

- [ ] **Step 1: Failing tests**

In `SystemSettings.test.tsx`: add `aieval_scheduled_provider: "claude"` to `DEFAULTS`; mock `@/hooks/useProviderConfigs` (`useProviderConfigs: () => ({ data: [] })`) and `@/hooks/useAiModels` (models `claude-opus-5` (claude), `gpt-5.6-sol` (openai); `defaults` for both). Add:

```tsx
  it("picks the failover provider from a select and PATCHes it", async () => {
    renderPage();
    await userEvent.selectOptions(screen.getByLabelText("Failover provider"), "openai");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(updateSystemSettings).toHaveBeenCalledWith({ ai_failover_provider: "openai" });
  });

  it("changing the eval provider resets the eval model to that provider's default", async () => {
    renderPage();
    await userEvent.selectOptions(screen.getByLabelText("Eval provider"), "openai");
    expect(screen.getByLabelText("Eval model")).toHaveValue("gpt-5.6-sol");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(updateSystemSettings).toHaveBeenCalledWith({
      aieval_scheduled_provider: "openai",
      aieval_scheduled_model: "gpt-5.6-sol",
    });
  });

  it("offers the post-mortem horizons for the eval horizon", async () => {
    renderPage();
    await userEvent.selectOptions(screen.getByLabelText("Horizon (days)"), "90");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(updateSystemSettings).toHaveBeenCalledWith({ aieval_scheduled_horizon: 90 });
  });
```

- [ ] **Step 2: Implement**

`api/settings.ts`: add `aieval_scheduled_provider: string;` after `aieval_scheduled_enabled`.

`SystemSettings.tsx`:
- Import `ProviderSelect`, `ModelSelect`, `useCatalog`, `FALLBACK_HORIZONS`.
- Failover: replace the text input with
  `<ProviderSelect ariaLabel="Failover provider" emptyOption="None" value={eff.ai_failover_provider} onChange={(v) => set("ai_failover_provider", v)} className="w-56" />` inside the same `<label className="grid gap-1">` (keep the visible caption "Failover provider" as a `<span>`; the select's aria-label wins for queries).
- Scheduled eval: replace the model text input with two labelled controls:

```tsx
          <label className="grid gap-1">
            <span className="text-[12px] text-ink-300">Provider</span>
            <ProviderSelect
              ariaLabel="Eval provider"
              value={eff.aieval_scheduled_provider}
              onChange={(p) => {
                set("aieval_scheduled_provider", p);
                set("aieval_scheduled_model", defaultFor(p));
              }}
              className="w-56"
            />
          </label>
          <div className="grid gap-1">
            <span className="text-[12px] text-ink-300">Model</span>
            <ModelSelect
              ariaLabel="Eval model"
              provider={eff.aieval_scheduled_provider}
              value={eff.aieval_scheduled_model}
              onChange={(m) => set("aieval_scheduled_model", m)}
              facts
            />
          </div>
```

  and replace `{num("aieval_scheduled_horizon", "Horizon (days)")}` with a `<select aria-label="Horizon (days)">` over `FALLBACK_HORIZONS` whose `onChange` calls `set("aieval_scheduled_horizon", Number(e.target.value))`. (`horizonsFrom` needs an analytics payload this page does not load; the fallback list mirrors `THESIS_POSTMORTEM_HORIZONS`.)
- Description under "Scheduled eval": "Offline calibration replay on the chosen provider. Enabling it makes real (billed) model calls on a schedule."

- [ ] **Step 3: Run and commit**

Run: `pnpm exec vitest run --project unit src/__tests__/SystemSettings.test.tsx && pnpm lint`

```bash
git add frontend/src/api/settings.ts frontend/src/pages/settings/SystemSettings.tsx frontend/src/__tests__/SystemSettings.test.tsx
LEFTHOOK=0 git commit -m "feat(frontend): provider selects for failover and scheduled eval; catalog-backed eval model" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task F4: Profiles — AI features, target picker, activate control, ledger styling

**Owns:** `frontend/src/api/profiles.ts`, `frontend/src/pages/profiles/{ProfileForm,ProfileList,types,useProfileForm}.ts(x)`, `frontend/src/pages/ProfilesPage.tsx`, `frontend/src/__tests__/ProfilesPage.test.tsx`, `frontend/src/__tests__/profiles.types.test.ts`, `e2e/ui/test_profiles.py`, `e2e/pages/profiles.py`.

**Interfaces:** consumes F1 (`AiTargetPicker`, `CapabilityHint`, `AiAttribution`, `useCatalog`). `Draft` gains `enable_tools: boolean; enable_thinking: boolean; thinking_budget: number; enable_memory: boolean; enable_coach: boolean`.

**Preserved:** placeholders `Profile name` / `Trading style (used as system prompt)`; buttons `Create` / `Save` / `Cancel` / `Edit` / `Delete`; `aria-label="Default provider"` on the provider select; section checkboxes named by `SECTION_LABELS` (role `checkbox`); `data-testid="vix-always-included-chip"`; `data-testid="profile-row-<name>"`; heading `Trading profiles`; preset section untouched.

- [ ] **Step 1: Failing tests**

`profiles.types.test.ts` — add:

```ts
describe("BLANK_DRAFT AI features", () => {
  it("mirrors the backend flag defaults", () => {
    expect(BLANK_DRAFT).toMatchObject({
      enable_tools: false, enable_thinking: false, thinking_budget: 8000, enable_memory: false, enable_coach: true,
    });
    expect(BLANK_DRAFT.default_model).toBe("claude-opus-5");
  });
});
```

`ProfilesPage.test.tsx` — mock `@/hooks/useProviderConfigs` (`useProviderConfigs: () => ({ data: [{ provider: "openai", enabled: true, api_key_present: true, supports_tools: false, base_url: "", default_model: "", supports_vision: true, daily_cost_cap_usd: "10", monthly_cost_cap_usd: null }] })`), extend `AI_MODELS` with `defaults: { claude: "claude-sonnet-4-6", openai: "gpt-5" }` so existing "first model" expectations hold, give `PROFILE_A`/`PROFILE_B` the five flags, and add:

```tsx
  it("posts the AI feature flags and thinking budget", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);
    fireEvent.change(screen.getByPlaceholderText("Profile name"), { target: { value: "N" } });
    fireEvent.change(screen.getByPlaceholderText("Trading style (used as system prompt)"), { target: { value: "s" } });
    await user.click(screen.getByRole("switch", { name: "Enable tools" }));
    await user.click(screen.getByRole("switch", { name: "Extended thinking" }));
    const budget = screen.getByLabelText("Thinking budget");
    await user.clear(budget);
    await user.type(budget, "16000");
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({ enable_tools: true, enable_thinking: true, thinking_budget: 16000, enable_coach: true }),
      expect.anything(),
    );
  });

  it("hints that thinking and memory are Claude only and tools are off for OpenAI", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);
    await user.selectOptions(screen.getByLabelText("Default provider"), "openai");
    expect(screen.getAllByText(/Claude only — ignored on OpenAI/)).toHaveLength(2);
    expect(screen.getByText(/Tool use is off for OpenAI/)).toBeInTheDocument();
  });

  it("toggles a profile's active flag from the list", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);
    await user.click(within(screen.getByTestId("profile-row-Swing Trader")).getByRole("button", { name: "Deactivate" }));
    expect(updateMutate).toHaveBeenCalledWith({ id: 1, body: { active: false } }, expect.anything());
  });
```

(`createMutate` / `updateMutate` are whatever names that file already uses for the mocked `mutate` functions of `useCreateProfile` / `useUpdateProfile`; `within` comes from `@testing-library/react`.)

- [ ] **Step 2: Implement**

`api/profiles.ts` — `TradingProfile` gains `enable_tools: boolean; enable_thinking: boolean; thinking_budget: number; enable_memory: boolean; enable_coach: boolean;`.

`types.ts` — `Draft` gains the five fields; `BLANK_DRAFT` sets `enable_tools: false, enable_thinking: false, thinking_budget: 8000, enable_memory: false, enable_coach: true`.

`useProfileForm.ts` — `startEdit` copies the five fields from `p`. Add `const { push } = useToast();` and pass `onError: (e) => push({ kind: "error", text: (e as Error).message })` to both mutations so the vendor-guard 400 is visible.

`ProfileForm.tsx` — rebuild on ledger primitives:

```tsx
import Field from "@/components/settings/Field";
import Toggle from "@/components/ui/Toggle";
import AiTargetPicker from "@/components/ai/AiTargetPicker";
import CapabilityHint from "@/components/ai/CapabilityHint";
import { useProviderConfigs } from "@/hooks/useProviderConfigs";
import { SECTION_LABELS, VIX_LABEL } from "@/lib/snapshotSections";
import { SECTION_OPTIONS } from "./types";
import type { useProfileForm } from "./useProfileForm";

function FeatureToggle({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="flex items-center gap-3">
        <Toggle checked={checked} onChange={onChange} label={label} />
        <span className="text-[13px] text-ink-200">{label}</span>
      </div>
      {hint}
    </div>
  );
}

export function ProfileForm({ form }: { form: ReturnType<typeof useProfileForm> }) {
  const { editing, draft, setDraft, submit, toggleSection, reset } = form;
  const { data: configs } = useProviderConfigs();
  const supportsTools = configs?.find((c) => c.provider === draft.default_provider)?.supports_tools;
  const provider = draft.default_provider;
  return (
    <form onSubmit={submit} className="ledger-surface p-5 space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name">{({ id }) => (
          <input id={id} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="Profile name" required className="ledger-input w-full py-2" />
        )}</Field>
        <div className="sm:col-span-2">
          <Field label="Trading style" hint="Prepended as the system prompt on every run.">{({ id, describedBy }) => (
            <textarea id={id} aria-describedby={describedBy} value={draft.style} rows={5}
              onChange={(e) => setDraft({ ...draft, style: e.target.value })}
              placeholder="Trading style (used as system prompt)" className="ledger-input w-full py-2" />
          )}</Field>
        </div>
      </div>

      <fieldset>
        <legend className="font-mono text-[10px] uppercase tracking-loose2 text-copper-400 mb-2">Default sections</legend>
        <div className="flex flex-wrap gap-2">
          {SECTION_OPTIONS.map((sec) => (
            <label key={sec} className="flex items-center gap-1 text-[13px] text-ink-200">
              <input type="checkbox" checked={draft.default_includes.includes(sec)} onChange={() => toggleSection(sec)} />
              {SECTION_LABELS[sec]}
            </label>
          ))}
        </div>
        <div className="mt-2">
          <span data-testid="vix-always-included-chip" className="ledger-pill">{VIX_LABEL} — always included</span>
        </div>
      </fieldset>

      <fieldset>
        <legend className="font-mono text-[10px] uppercase tracking-loose2 text-copper-400 mb-2">Default AI target</legend>
        <AiTargetPicker
          value={{ provider: draft.default_provider, model: draft.default_model }}
          onChange={(t) => setDraft({ ...draft, default_provider: t.provider, default_model: t.model })}
          providerLabel="Default provider" modelLabel="Default model" facts
        />
      </fieldset>

      <fieldset className="border-t border-rule-soft pt-4">
        <legend className="font-mono text-[10px] uppercase tracking-loose2 text-copper-400 mb-1">AI features</legend>
        <FeatureToggle label="Enable tools" checked={draft.enable_tools}
          onChange={(v) => setDraft({ ...draft, enable_tools: v })}
          hint={<CapabilityHint feature="tools" provider={provider} supportsTools={supportsTools} />} />
        <FeatureToggle label="Extended thinking" checked={draft.enable_thinking}
          onChange={(v) => setDraft({ ...draft, enable_thinking: v })}
          hint={<CapabilityHint feature="thinking" provider={provider} />} />
        {draft.enable_thinking && (
          <div className="pl-12 pb-2">
            <Field label="Thinking budget" hint="Tokens, billed as output.">{({ id, describedBy }) => (
              <input id={id} aria-label="Thinking budget" aria-describedby={describedBy} type="number" min={1024} step={1024}
                value={draft.thinking_budget}
                onChange={(e) => setDraft({ ...draft, thinking_budget: Number(e.target.value) })}
                className="ledger-input w-40 py-2 tabular-nums" />
            )}</Field>
          </div>
        )}
        <FeatureToggle label="Memory" checked={draft.enable_memory}
          onChange={(v) => setDraft({ ...draft, enable_memory: v })}
          hint={<CapabilityHint feature="memory" provider={provider} />} />
        <FeatureToggle label="Decision Coach" checked={draft.enable_coach}
          onChange={(v) => setDraft({ ...draft, enable_coach: v })}
          hint={<span className="text-[11px] text-ink-400">Calibration, base rates and lessons in the system prompt.</span>} />
      </fieldset>

      <div className="flex gap-2">
        <button type="submit" className="ledger-cta">{editing ? "Save" : "Create"}</button>
        {editing && <button type="button" onClick={reset} className="ledger-ghost">Cancel</button>}
      </div>
    </form>
  );
}
```

`ProfileList.tsx` — rows on `ledger-surface`, showing `AiAttribution provider={p.default_provider} model={p.default_model}`, feature pills (`tools`/`thinking`/`memory`/`coach` when enabled, `ledger-pill` copper), an `Inactive` pill (`data-tone="loss"`) when `!p.active`, sections joined as today, and buttons `Edit`, `Activate`/`Deactivate` (calls `useUpdateProfile().mutate({ id: p.id, body: { active: !p.active } })`), `Delete` (`text-loss`).

`ProfilesPage.tsx` — `ledger-fade-in` main, `ledger-display`-style h1 kept as text `Trading profiles`; preset section untouched.

e2e: in `e2e/ui/test_profiles.py` remove both `@pytest.mark.xfail(...)` decorators; change `test_profile_toggle_active` to click `Deactivate` then `expect(row.get_by_role("button", name="Activate")).to_be_visible(timeout=10_000)`. Update the docstring in `e2e/pages/profiles.py` to describe the form as it now is.

- [ ] **Step 3: Run and commit**

Run: `pnpm exec vitest run --project unit src/__tests__/ProfilesPage.test.tsx src/__tests__/profiles.types.test.ts && pnpm lint`

```bash
git add frontend/src/api/profiles.ts frontend/src/pages/profiles frontend/src/pages/ProfilesPage.tsx frontend/src/__tests__/ProfilesPage.test.tsx frontend/src/__tests__/profiles.types.test.ts e2e/ui/test_profiles.py e2e/pages/profiles.py
LEFTHOOK=0 git commit -m "feat(frontend): profile AI feature toggles, target picker with hints, activate control" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task F5: Schedules — per-schedule AI target and mode, editable after create

**Owns:** `frontend/src/api/observer.ts`, `frontend/src/hooks/useSchedules.ts`, `frontend/src/pages/SchedulesPage.tsx`, `frontend/src/pages/schedules/{ScheduleRow,CreateScheduleForm,ScheduleAiFields,ScheduleSectionsEditor}.tsx`, `frontend/src/pages/schedules/useScheduleForm.ts` (all new), `frontend/src/__tests__/SchedulesPage.test.tsx`, `frontend/src/__tests__/SchedulesPage.fireMode.test.tsx`, `frontend/src/__tests__/hooks/useSchedules.test.tsx`.

**Interfaces:** consumes F1 (`AiTargetPicker` with `inherit`, `ModeBadges`, `AiAttribution`, `useCatalog`). Produces `useUpdateSchedule()` (`mutate({ id, body: Partial<CreateScheduleBody> })`).

**Preserved:** h1 `Observer schedules`; button text `+ New schedule`; labels `Name` and `Profile` (`htmlFor` ids `sched-name` / `sched-profile`); button `Create` (exact); `data-testid="schedule-row-<id>"`; exactly one `checkbox` inside the row while its editors are closed (the `enabled` box); buttons `Run now`, `Sections`, `aria-label="delete <name>"`; `SkeletonRows` while loading; EmptyState `No schedules yet`; fire-mode labels `Fire mode` / `Minutes before close`; cron preset/advanced buttons; the create body shape asserted by `SchedulesPage.test` (`name`, `cron`, `profile`) and by `SchedulesPage.fireMode.test`.

- [ ] **Step 1: Failing tests**

In `SchedulesPage.test.tsx`, extend `SCHEDULES[0]` with `mode: "full", structured: true, use_batch: false, consensus: false, investigate: false, override_provider: "openai", override_model: "gpt-5.6-sol", fire_mode: "cron", close_offset_minutes: 5, last_batch_id: ""` and `PROFILES[0]` with `default_provider: "claude", default_model: "claude-opus-5"`; add mocks `"GET /api/schwab/providers/": []` and `"GET /api/schwab/models/": { models: [ {claude-opus-5 row}, {gpt-5.6-sol row} ], defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" } }` to every `mockApi` call. Add:

```tsx
  it("shows the effective AI target and mode badges on a row", async () => {
    mockApi({ ...BASE });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    const row = screen.getByTestId("schedule-row-1");
    expect(within(row).getByTestId("ai-attribution").textContent).toContain("OpenAI · gpt-5.6-sol");
    expect(within(row).getByTestId("ai-attribution").textContent).toContain("(override)");
    expect(within(row).getByTestId("mode-badges").textContent).toContain("structured");
    expect(within(row).getAllByRole("checkbox")).toHaveLength(1);
  });

  it("creates with an inherited target by default and an override when chosen", async () => {
    const mock = mockApi({ ...BASE_EMPTY, "POST /api/observer/schedules/": {} });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "AB-openai" } });
    expect(screen.getByText(/Runs on Claude · claude-opus-5 \(from profile\)/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Override provider"), "openai");
    expect(screen.getByText(/Runs on OpenAI · gpt-5.6-sol \(override\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/structured/i));
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => expect(mock.calls.some((c) => c.method === "POST")).toBe(true));
    const body = mock.calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(body).toMatchObject({ override_provider: "openai", override_model: "gpt-5.6-sol", structured: true, investigate: false });
  });

  it("disables Messages Batch off-Claude and Investigate when structured", async () => {
    mockApi({ ...BASE_EMPTY });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));
    await userEvent.selectOptions(screen.getByLabelText("Override provider"), "openai");
    expect(screen.getByLabelText(/messages batch/i)).toBeDisabled();
    expect(screen.getByText(/Claude only — Messages Batches/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/structured/i));
    expect(screen.getByLabelText(/investigate/i)).toBeDisabled();
  });

  it("edits a row's AI settings and PATCHes them", async () => {
    const mock = mockApi({ ...BASE, "PATCH /api/observer/schedules/1/": {} });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^ai$/i }));
    fireEvent.click(screen.getByLabelText(/cross-model consensus/i));
    fireEvent.click(screen.getByRole("button", { name: /save ai settings/i }));
    await waitFor(() => expect(mock.calls.some((c) => c.method === "PATCH")).toBe(true));
    const body = mock.calls.find((c) => c.method === "PATCH")!.body as Record<string, unknown>;
    expect(body).toMatchObject({ consensus: true, structured: true, override_provider: "openai", override_model: "gpt-5.6-sol" });
  });
```

(`BASE` / `BASE_EMPTY` are the two mock maps that file already builds inline; hoist them into constants including the new provider/model mocks.) In `hooks/useSchedules.test.tsx`, add a test that `useUpdateSchedule().mutate({ id: 1, body: { consensus: true } })` PATCHes `/api/observer/schedules/1/` and invalidates `["schedules"]` (mirror the existing `useUpdateScheduleIncludes` test).

- [ ] **Step 2: Implement**

`api/observer.ts`: add `investigate: boolean;` to `ObserverSchedule` and `investigate?: boolean;` to `CreateScheduleBody`.

`hooks/useSchedules.ts`:

```ts
export function useUpdateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<CreateScheduleBody> }) => patchSchedule(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}
```

`pages/schedules/ScheduleAiFields.tsx` — the AI fieldset shared by create and row edit:

```tsx
import AiTargetPicker from "@/components/ai/AiTargetPicker";
import AiAttribution from "@/components/ai/AiAttribution";
import { providerLabel } from "@/api/ai";
import type { ObserverMode } from "@/api/observer";
import type { TradingProfile } from "@/api/profiles";
import { useCatalog } from "@/hooks/useCatalog";

export type AiFieldsValue = {
  override_provider: string;
  override_model: string;
  mode: ObserverMode;
  structured: boolean;
  use_batch: boolean;
  consensus: boolean;
  investigate: boolean;
};

export const BLANK_AI_FIELDS: AiFieldsValue = {
  override_provider: "", override_model: "", mode: "full",
  structured: false, use_batch: false, consensus: false, investigate: false,
};

/** The provider/model a schedule actually runs on, and where that came from. */
export function effectiveTarget(v: Pick<AiFieldsValue, "override_provider" | "override_model">, profile: TradingProfile | undefined, defaultFor: (p: string) => string) {
  const provider = v.override_provider || profile?.default_provider || "claude";
  const model = v.override_provider
    ? v.override_model || defaultFor(provider)
    : profile?.default_model || defaultFor(provider);
  return { provider, model, qualifier: v.override_provider ? "override" : "from profile" };
}

export default function ScheduleAiFields({ value, onChange, profile, idPrefix }: {
  value: AiFieldsValue; onChange: (v: AiFieldsValue) => void; profile: TradingProfile | undefined; idPrefix: string;
}) {
  const { defaultFor } = useCatalog();
  const eff = effectiveTarget(value, profile, defaultFor);
  const isClaude = eff.provider === "claude";
  const inheritLabel = profile
    ? `Inherit from profile — ${providerLabel(profile.default_provider)} · ${profile.default_model || defaultFor(profile.default_provider)}`
    : "Inherit from profile";
  const set = (patch: Partial<AiFieldsValue>) => onChange({ ...value, ...patch });
  const check = (id: string, label: string, checked: boolean, onToggle: (v: boolean) => void, opts: { disabled?: boolean; hint?: string } = {}) => (
    <label className={`flex items-start gap-2 text-[13px] ${opts.disabled ? "text-ink-500" : "text-ink-200"}`}>
      <input id={`${idPrefix}-${id}`} type="checkbox" checked={checked} disabled={opts.disabled}
        onChange={(e) => onToggle(e.target.checked)} className="mt-0.5" />
      <span>{label}{opts.hint && <span className="block text-[11px] text-copper-300">{opts.hint}</span>}</span>
    </label>
  );
  return (
    <fieldset className="space-y-3 rounded-ledger border border-rule p-3">
      <legend className="px-1 font-mono text-[10px] uppercase tracking-loose2 text-copper-400">AI</legend>
      <AiTargetPicker
        value={{ provider: value.override_provider, model: value.override_model }}
        onChange={(t) => set({ override_provider: t.provider, override_model: t.model, use_batch: value.use_batch && (t.provider || profile?.default_provider) === "claude" })}
        inherit={{ label: inheritLabel }} providerLabel="Override provider" modelLabel="Override model" facts
      />
      <label className="flex flex-col gap-1 text-[13px] text-ink-200">
        <span className="text-[11px] text-ink-400">Payload shape</span>
        <select id={`${idPrefix}-mode`} value={value.mode} onChange={(e) => set({ mode: e.target.value as ObserverMode })} className="ledger-input py-2 sm:w-64">
          <option value="full">Full payload</option>
          <option value="diff">Diff vs previous capture</option>
        </select>
      </label>
      <div className="grid gap-2 sm:grid-cols-2">
        {check("structured", "Structured (typed observation card)", value.structured,
          (v) => set({ structured: v, consensus: v && value.consensus, investigate: v ? false : value.investigate }))}
        {check("consensus", "Cross-model consensus (fan the structured report across every ready provider; ~Nx cost)", value.consensus,
          (v) => set({ consensus: v }), { disabled: !value.structured, hint: value.structured ? undefined : "Needs Structured" })}
        {check("batch", "Messages Batch per watchlist ticker (50% cheaper, async)", value.use_batch,
          (v) => set({ use_batch: v }), { disabled: !isClaude, hint: isClaude ? undefined : "Claude only — Messages Batches" })}
        {check("investigate", "Investigate (bounded tool loop under the autonomous cap)", value.investigate,
          (v) => set({ investigate: v }), { disabled: value.structured, hint: value.structured ? "Plain mode only" : undefined })}
      </div>
      <p className="flex items-center gap-2 text-[12px] text-ink-300">
        Runs on <AiAttribution provider={eff.provider} model={eff.model} qualifier={eff.qualifier} />
      </p>
    </fieldset>
  );
}
```

The row test's "Runs on OpenAI · gpt-5.6-sol (override)" text spans the `AiAttribution` pill; assert with a function matcher if `getByText` does not cross elements: `screen.getByText((_, el) => el?.textContent === "Runs on OpenAI · gpt-5.6-sol (override)")` — or simpler, render the summary as one string in a `<span data-testid="effective-target">` and assert on its `textContent`. Choose the second and adjust the two `Runs on` assertions in Step 1 to `screen.getByTestId("effective-target").textContent`.

`pages/schedules/useScheduleForm.ts` — move every `useState` from `SchedulesPage` into a hook returning the existing `CreateFormState` fields plus `ai: AiFieldsValue`, `setAi`, `payload(): CreateScheduleBody`, `reset()`. `payload()` spreads `...ai` (all seven fields) into the body alongside `name/profile/enabled/market_hours_only/objective_template/fire_mode` and the cron/offset branch exactly as today.

`pages/schedules/CreateScheduleForm.tsx` — today's `CreateScheduleForm` + `FireModeFields` + `CronFields` on ledger classes (`ledger-input`, `ledger-cta` for Create, `ledger-ghost` for the preset/advanced toggles), with `<ScheduleAiFields value={form.ai} onChange={form.setAi} profile={profiles?.find((p) => p.id === form.profileId)} idPrefix="sched-new" />` in place of `AiModeFields`.

`pages/schedules/ScheduleSectionsEditor.tsx` — today's component unchanged except `ledger-cta` on Save sections.

`pages/schedules/ScheduleRow.tsx` — today's `ScheduleRow` on `ledger-surface`, plus: a second line `<ModeBadges …/> <AiAttribution provider model qualifier={s.override_provider ? "override" : "profile"} />` using `effectiveTarget(s, profileFor(s.profile), defaultFor)`; an `AI` button toggling a `ScheduleAiFields` editor seeded from the row (`{override_provider, override_model, mode, structured, use_batch, consensus, investigate}`) with a `Save AI settings` `ledger-cta` that calls `onSaveAi(s.id, value)`; props gain `profileFor: (id: number) => TradingProfile | undefined` and `onSaveAi`.

`SchedulesPage.tsx` — composes the above; `onSaveAi = (id, v) => updateSchedule.mutate({ id, body: v })`. `onCreate` wraps `mutateAsync` in try/catch and toasts the error (`useToast().push({ kind: "error", text })`) so a backend 400 (vendor guard, batch off-Claude) is visible; `useRunSchedule` gets `onSuccess`/`onError` toasts ("Fired — results land on the observer timeline." / the error).

Robustness the smoke tests demand: `ScheduleRow` reads `s.mode ?? "full"`, `s.structured ?? false`, etc. (`__tests__/testids/rows.test.tsx` feeds a schedule without those keys), and `effectiveTarget` tolerates `profile === undefined`. In `SchedulesPage.fireMode.test.tsx` (renders without a QueryClientProvider) add to the mocks: `useUpdateSchedule: () => ({ mutate: vi.fn() })` in the `@/hooks/useSchedules` mock, plus `vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => ({ data: { models: [], defaults: {} } }) }))`, `vi.mock("@/hooks/useProviderConfigs", () => ({ useProviderConfigs: () => ({ data: [] }) }))` and `vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ push: vi.fn() }) }))`.

- [ ] **Step 3: Run and commit**

Run: `pnpm exec vitest run --project unit src/__tests__/SchedulesPage.test.tsx src/__tests__/SchedulesPage.fireMode.test.tsx src/__tests__/hooks/useSchedules.test.tsx src/__tests__/testids/rows.test.tsx && pnpm lint`

```bash
git add frontend/src/api/observer.ts frontend/src/hooks/useSchedules.ts frontend/src/pages/SchedulesPage.tsx frontend/src/pages/schedules frontend/src/__tests__/SchedulesPage.test.tsx frontend/src/__tests__/SchedulesPage.fireMode.test.tsx frontend/src/__tests__/hooks/useSchedules.test.tsx
LEFTHOOK=0 git commit -m "feat(frontend): per-schedule AI target and mode, editable after create" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task F6: Consensus card, observer timeline attribution, thread detail kinds

**Owns:** `frontend/src/components/ConsensusReportCard.tsx` + `.stories.tsx` (new), `frontend/src/components/PostMortemReportBody.tsx` + `.stories.tsx` (new), `frontend/src/components/WarRoomVerdictBody.tsx` + `.stories.tsx` (new), `frontend/src/components/ObservationReportCard.tsx` (export `BIAS_COLOR`; render the directional call + grounding), `frontend/src/components/StreamingMessage.tsx`, `frontend/src/api/threads.ts`, `frontend/src/pages/thread-detail/types.ts`, `frontend/src/pages/thread-detail/useLiveMessages.ts`, `frontend/src/pages/ThreadDetailPage.tsx` (picker seed only), `frontend/src/pages/ObserverTimelinePage.tsx`, `frontend/src/__tests__/ConsensusReportCard.test.tsx` (new), `frontend/src/__tests__/ObserverTimelinePage.test.tsx`, `frontend/src/__tests__/StreamingMessage.test.tsx` (**exists — extend it**), `frontend/src/__tests__/ObservationReportCard.test.tsx`, `frontend/src/__tests__/ThreadDetailPage.test.tsx` (only if a type change forces a fixture edit).

**Interfaces:** consumes F1 (`ConsensusReport`, `isConsensusReport`, `isPostMortemReport`, `StructuredKind`, `StructuredReport`, `PostMortemReportContent`, `WarRoomVerdictContent`, `AiAttribution`, `useCatalog`); consumes B3 (`ai_run`, `status`, `error` on timeline messages; `content.provider/model`).

**Preserved:** timeline h1 = thread title; row buttons whose text contains `Snapshot` / `Response`; expanded plain text; every existing `StreamingMessage.test.tsx` assertion (`You`, `(empty)`, `/Openai/`, `Assistant`, `.ledger-pulse`, `$0.0042`, `bare` omits `.ledger-surface`, structured report fields, markdown fallback); `ObservationReportCard.test.tsx` assertions (headline/summary/`SPY`/levels/risks/next check, `text-slate-300` on the neutral badge, SaveCardButton).

- [ ] **Step 1: Failing tests**

`ConsensusReportCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ConsensusReportCard from "@/components/ConsensusReportCard";
import type { ConsensusReport } from "@/api/observation";

const REPORT: ConsensusReport = {
  n_providers: 3, bias_agreement: 0.6667, modal_bias: "bullish", divergent: true,
  per_ticker: { SPY: { agreement: 0.6667, modal: "bullish", takes: { "claude/claude-opus-5": "bullish", "openai/gpt-5.6-sol": "bullish", "local/llama3": "bearish" } } },
  takes: [
    { provider: "claude", model: "claude-opus-5", bias: "bullish", signal_bias: { SPY: "bullish" } },
    { provider: "openai", model: "gpt-5.6-sol", bias: "bullish", signal_bias: { SPY: "bullish" } },
    { provider: "local", model: "llama3", bias: "bearish", signal_bias: { SPY: "bearish" } },
  ],
  note: "",
};

describe("ConsensusReportCard", () => {
  it("shows agreement, divergence, every take and the per-ticker grid", () => {
    render(<ConsensusReportCard report={REPORT} />);
    expect(screen.getByText(/2 of 3 agree \(67%\)/)).toBeInTheDocument();
    expect(screen.getByText(/divergent — do more homework/i)).toBeInTheDocument();
    expect(screen.getAllByTestId("ai-attribution")).toHaveLength(3);
    expect(screen.getByRole("row", { name: /SPY/ })).toBeInTheDocument();
  });

  it("renders the degraded single-provider note honestly", () => {
    render(<ConsensusReportCard report={{ ...REPORT, n_providers: 1, bias_agreement: null, divergent: false, takes: [REPORT.takes[0]], per_ticker: {}, note: "single provider — no consensus available" }} />);
    expect(screen.getByText(/single provider — no consensus available/)).toBeInTheDocument();
    expect(screen.queryByText(/agree/)).not.toBeInTheDocument();
  });
});
```

`ObserverTimelinePage.test.tsx` — add to `FAKE_THREAD.messages` a structured message (`content: { kind: "structured_observation", report: {headline: "Range day", bias: "neutral", summary: "", signals: [], key_levels: [], risks: [], next_check_in: "close"}, provider: "claude", model: "claude-opus-5" }, ai_run: null`) and a consensus message (`content: { kind: "consensus_report", report: <REPORT above> }, ai_run: null`), and give message 2 `ai_run: { provider: "openai", model: "gpt-5.6-sol", cost_usd: "0.012300" }`. Add:

```tsx
  it("shows attribution per fire and renders the consensus card", async () => {
    renderWithProviders(<ObserverTimelinePage />, { initialEntries: ["/threads/observer/1"], routePath: "/threads/observer/:profileId" });
    await waitFor(() => expect(screen.getByText(/Observer: P/)).toBeInTheDocument());
    expect(screen.getAllByTestId("ai-attribution").map((e) => e.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining("OpenAI · gpt-5.6-sol · $0.0123"), expect.stringContaining("Claude · claude-opus-5")]),
    );
    fireEvent.click(screen.getByRole("button", { name: /Consensus — bullish · 3 providers/ }));
    expect(screen.getByText(/2 of 3 agree/)).toBeInTheDocument();
  });
```

Append to the existing `StreamingMessage.test.tsx`:

```tsx
describe("StreamingMessage — other structured kinds", () => {
  it("renders a consensus report card for kind consensus_report", () => {
    render(<StreamingMessage role="assistant" text="" status="done" kind="consensus_report" provider="claude" model="claude-opus-5"
      report={{ n_providers: 2, bias_agreement: 1, modal_bias: "bearish", divergent: false, per_ticker: {}, note: "",
        takes: [{ provider: "claude", model: "claude-opus-5", bias: "bearish", signal_bias: {} }, { provider: "openai", model: "gpt-5.6-sol", bias: "bearish", signal_bias: {} }] }} />);
    expect(screen.getByText(/2 of 2 agree \(100%\)/)).toBeInTheDocument();
  });

  it("renders the post-mortem narrative for kind postmortem_report", () => {
    render(<StreamingMessage role="assistant" text="" status="done" kind="postmortem_report"
      report={{ summary: "Thesis played out.", what_worked: ["entry timing"], what_missed: [], lessons: ["size smaller"], would_repeat: true, ai: { provider: "openai", model: "gpt-5.6-sol" } }} />);
    expect(screen.getByText("Thesis played out.")).toBeInTheDocument();
    expect(screen.getByText(/entry timing/)).toBeInTheDocument();
    expect(screen.getByText(/would repeat/i)).toBeInTheDocument();
    expect(screen.getByTestId("ai-attribution").textContent).toBe("OpenAI · gpt-5.6-sol");
  });

  it("renders the War Room verdict for kind warroom_verdict", () => {
    render(<StreamingMessage role="assistant" text="" status="done" kind="warroom_verdict"
      verdict={{ verdict: "bull case stronger", confidence: 0.7, strongest_bull: "breadth", strongest_bear: "rates", what_would_change_my_mind: "a close below 500", ai: { provider: "claude", model: "claude-opus-5" } }} />);
    expect(screen.getByText(/bull case stronger/)).toBeInTheDocument();
    expect(screen.getByText(/70%/)).toBeInTheDocument();
    expect(screen.getByText(/a close below 500/)).toBeInTheDocument();
  });

  it("marks cached, warning and investigation messages with a kind chip", () => {
    const { rerender } = render(<StreamingMessage role="assistant" text="Reused" status="done" kind="cached_observation" />);
    expect(screen.getByText("cached")).toBeInTheDocument();
    rerender(<StreamingMessage role="assistant" text="OpenAI can't do thinking" status="done" kind="capability_warning" />);
    expect(screen.getByText("warning")).toBeInTheDocument();
    rerender(<StreamingMessage role="assistant" text="" status="done" kind="investigation" />);
    expect(screen.getByText("investigation")).toBeInTheDocument();
  });
});
```

Append to `ObservationReportCard.test.tsx`:

```tsx
  it("renders the directional call and grounding when present", () => {
    render(<ObservationReportCard report={{ ...report, predicted_direction: "bullish", predicted_horizon_days: 5, predicted_confidence: 0.72, grounding: ["quotes", "chain analytics"] }} />);
    expect(screen.getByText(/Call: bullish · 5d · 72%/)).toBeInTheDocument();
    expect(screen.getByText("chain analytics")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Implement**

`ObservationReportCard.tsx`: `export const BIAS_COLOR` (was a module const).

`ConsensusReportCard.tsx`:

```tsx
import { useRef } from "react";
import { SaveCardButton } from "./SaveCardButton";
import AiAttribution from "@/components/ai/AiAttribution";
import { BIAS_COLOR } from "@/components/ObservationReportCard";
import type { Bias, ConsensusReport } from "@/api/observation";

function BiasPill({ bias }: { bias: Bias | null }) {
  if (!bias) return <span className="text-ink-500">—</span>;
  return <span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider border rounded ${BIAS_COLOR[bias]}`}>{bias}</span>;
}

/** "2 of 3 agree (67%)" for a real consensus; null when fewer than 2 takes. */
export function agreementLine(r: ConsensusReport): string | null {
  if (r.n_providers < 2 || r.bias_agreement == null) return null;
  const agreeing = Math.round(r.bias_agreement * r.n_providers);
  return `${agreeing} of ${r.n_providers} agree (${Math.round(r.bias_agreement * 100)}%)`;
}

export default function ConsensusReportCard({ report }: { report: ConsensusReport }) {
  const cardRef = useRef<HTMLDivElement>(null);
  const line = agreementLine(report);
  const columns = report.takes.map((t) => `${t.provider}/${t.model}`);
  return (
    <div ref={cardRef} className="space-y-3">
      <div className="flex items-start gap-3 flex-wrap">
        <BiasPill bias={report.modal_bias} />
        <h3 className="font-medium text-ink-100 flex-1">
          {line ?? report.note ?? "Consensus"}
        </h3>
        {report.divergent && <span className="ledger-pill" data-tone="copper">Divergent — do more homework</span>}
        <SaveCardButton targetRef={cardRef} filename="consensus.png" />
      </div>
      {line && report.note && <p className="text-[12px] text-ink-400">{report.note}</p>}
      <section>
        <div className="font-mono text-[10px] uppercase tracking-wider text-copper-400 mb-1">Takes</div>
        <ul className="space-y-1">
          {report.takes.map((t) => (
            <li key={`${t.provider}/${t.model}`} className="flex items-center gap-2 text-xs">
              <AiAttribution provider={t.provider} model={t.model} />
              <BiasPill bias={t.bias} />
            </li>
          ))}
        </ul>
      </section>
      {Object.keys(report.per_ticker).length > 0 && (
        <section className="min-w-0 overflow-x-auto">
          <div className="font-mono text-[10px] uppercase tracking-wider text-copper-400 mb-1">Per ticker</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-ink-400 text-left">
                <th className="py-1 pr-3 font-normal">Ticker</th>
                {columns.map((c) => <th key={c} className="py-1 pr-3 font-normal font-mono">{c.split("/")[0]}</th>)}
                <th className="py-1 font-normal text-right">Agreement</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.per_ticker).map(([ticker, row]) => (
                <tr key={ticker} aria-label={ticker} className="border-t border-rule-soft">
                  <td className="py-1 pr-3 font-mono text-ink-100">{ticker}</td>
                  {columns.map((c) => <td key={c} className="py-1 pr-3"><BiasPill bias={row.takes[c] ?? null} /></td>)}
                  <td className="py-1 text-right tabular-nums text-ink-300">{row.agreement == null ? "—" : `${Math.round(row.agreement * 100)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
```

(Testing Library resolves `getByRole("row", { name: /SPY/ })` from the `aria-label`; keep it.)

`api/threads.ts`: `Message.content` → `{ text?: string; kind?: StructuredKind; report?: StructuredReport; provider?: string; model?: string } & Partial<WarRoomVerdictContent>` (the verdict fields are spread directly into the content; import from `./observation`).

`thread-detail/types.ts`: `kind?: StructuredKind; report?: StructuredReport; verdict?: WarRoomVerdictContent`.

`useLiveMessages.ts::toLiveMessage`: `model: m.ai_run?.model ?? m.content?.model`, `provider: m.ai_run?.provider ?? m.content?.provider`, and `verdict: m.content?.kind === "warroom_verdict" ? pickVerdict(m.content) : undefined` where `pickVerdict` copies the five verdict keys + `ai`. `thread-detail/Conversation.tsx` passes `verdict={m.verdict}` (and `verdict={active.verdict}` for the active branch) alongside `kind`/`report` into `StreamingMessage`.

`components/PostMortemReportBody.tsx` — pure renderer for `PostMortemReportContent`: summary paragraph, three `ReportList`-style sections (`What worked` gain tone, `What missed` loss tone, `Lessons`), a `would repeat` / `would not repeat` pill, `AiAttribution` when `ai` is present. `components/WarRoomVerdictBody.tsx` — verdict line with `({confidence}% conf)`, strongest bull / bear, "What would change my mind", `AiAttribution`. Both get a `.stories.tsx`.

`StreamingMessage.tsx`: prop types → `kind?: StructuredKind; report?: StructuredReport; verdict?: WarRoomVerdictContent`; in `AssistantBody`:

```tsx
  if (kind === "consensus_report" && isConsensusReport(report)) {
    return <ConsensusReportCard report={report} />;
  }
  if (kind === "postmortem_report" && isPostMortemReport(report)) {
    return <PostMortemReportBody report={report} />;
  }
  if (kind === "warroom_verdict" && verdict) {
    return <WarRoomVerdictBody verdict={verdict} />;
  }
  if (kind === "structured_observation" && report && !isConsensusReport(report) && !isPostMortemReport(report)) {
    return <ObservationReportCard report={report} />;
  }
```

and in `AssistantHeader` a kind chip after the model: `cached_observation` → `<span className="ledger-pill">cached</span>`, `capability_warning` → `<span className="ledger-pill" data-tone="loss">warning</span>`, `investigation` → `<span className="ledger-pill" data-tone="copper">investigation</span>` (pass `kind` into the header).

`ObservationReportCard.tsx` — after the summary paragraph, when `report.predicted_direction` is set:

```tsx
      {report.predicted_direction && (
        <p className="font-mono text-[11px] text-ink-300" data-testid="observation-call">
          Call: <span className={BIAS_COLOR[report.predicted_direction].split(" ")[0]}>{report.predicted_direction}</span>
          {report.predicted_horizon_days != null && ` · ${report.predicted_horizon_days}d`}
          {report.predicted_confidence != null && ` · ${Math.round(report.predicted_confidence * 100)}%`}
        </p>
      )}
```

and, after the risks section, `grounding` as `ledger-pill` chips under a `Grounded in` heading when non-empty.

`ThreadDetailPage.tsx` — replace `useState({ ...DEFAULT_PICK })` with a seed from the loaded thread's profile: keep `DEFAULT_PICK` as the initial state, then a render-phase guarded update (the file's existing pattern for "adjust state when data changes"): `if (!pickerSeeded && thread?.profile) { setPicker({ provider: thread.profile.default_provider, model: thread.profile.default_model }); setPickerSeeded(true); }`.

`ObserverTimelinePage.tsx`:
- `Message` interface: `content: { text?; kind?: StructuredKind; report?: StructuredReport; provider?; model? }; status?: "done" | "streaming" | "failed"; error?: string; ai_run?: { provider: string; model: string; cost_usd: string } | null;`.
- `isSkipped(m)` → `m.role === "system"` (every system row is a notice: cost-cap skip, no key, undecryptable key); the row keeps the 🔒 dimmed style and shows the text.
- `messageHeadline`: user → `📷 Snapshot — ${when}`; consensus → `🧭 Consensus — ${report.modal_bias ?? "no consensus"} · ${report.n_providers} providers — ${when}`; structured → `📊 ${headline} — ${when}`; `status === "failed"` → `⚠️ Failed — ${when}`; else `🤖 Response — ${when}`.
- `TimelineRow`: header becomes a flex row: the existing `<button>` (flex-1, text-left) plus, for assistant rows, `<AiAttribution provider={m.ai_run?.provider ?? m.content.provider} model={m.ai_run?.model ?? m.content.model} cost={m.ai_run?.cost_usd} />` and a `<span className="ledger-pill" data-tone="loss">failed</span>` when failed. Body: failed → `text-loss` line with `m.error || m.content.text`; else `ConsensusReportCard` / `ObservationReportCard` / plain text by kind.
- Rows use `ledger-surface` (notice rows keep the dimmed style); main keeps `h1` with the title.
- Add a test case with a `role: "system"` cost-cap message (`text: "Observer fire skipped at 09:35: cost cap exceeded"`) asserting it renders with the 🔒 prefix, and a `status: "failed"` message asserting the `failed` pill and error text.

- [ ] **Step 3: Run and commit**

Run: `pnpm exec vitest run --project unit src/__tests__/ConsensusReportCard.test.tsx src/__tests__/ObserverTimelinePage.test.tsx src/__tests__/StreamingMessage.test.tsx src/__tests__/ThreadDetailPage.test.tsx && pnpm lint`

```bash
git add frontend/src/components/ConsensusReportCard.tsx frontend/src/components/ConsensusReportCard.stories.tsx frontend/src/components/PostMortemReportBody.tsx frontend/src/components/PostMortemReportBody.stories.tsx frontend/src/components/WarRoomVerdictBody.tsx frontend/src/components/WarRoomVerdictBody.stories.tsx frontend/src/components/ObservationReportCard.tsx frontend/src/components/StreamingMessage.tsx frontend/src/api/threads.ts frontend/src/pages/thread-detail frontend/src/pages/ThreadDetailPage.tsx frontend/src/pages/ObserverTimelinePage.tsx frontend/src/__tests__/ConsensusReportCard.test.tsx frontend/src/__tests__/ObserverTimelinePage.test.tsx frontend/src/__tests__/StreamingMessage.test.tsx frontend/src/__tests__/ObservationReportCard.test.tsx frontend/src/__tests__/ThreadDetailPage.test.tsx
LEFTHOOK=0 git commit -m "feat(frontend): render every AI message kind with provider attribution on the timeline and threads" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task F7: Scorecard offline-eval section, eval trigger, post-mortem and War Room attribution

**Owns:** `frontend/src/api/aieval.ts` (new), `frontend/src/hooks/useAieval.ts` (new), `frontend/src/hooks/useAnalytics.ts` (retype `useLatestEvalRun`), `frontend/src/api/observer.ts` is F5's — instead add `"eval_done"` to `NotificationDTO.kind` **in F8** (see below); `frontend/src/api/thesis.ts`, `frontend/src/api/warroom.ts`, `frontend/src/pages/scorecard/{EvalSection,EvalRunsTable,EvalRunForm}.tsx` (new), `frontend/src/pages/ScorecardPage.tsx`, `frontend/src/pages/thesis-detail/PostMortemCard.tsx`, `frontend/src/pages/WarRoomDetailPage.tsx`, `frontend/src/components/AISecondOpinion.tsx`, `frontend/src/__tests__/ScorecardPage.test.tsx`, `frontend/src/__tests__/EvalSection.test.tsx` (new), `frontend/src/__tests__/PostMortemCard.attribution.test.tsx` (new), `frontend/src/__tests__/WarRoomDetailPage.test.tsx` (extend if present, else new minimal), `frontend/src/__tests__/AISecondOpinion.test.tsx`.

**Interfaces:** consumes F1 (`AiTargetPicker`, `AiAttribution`, `useCatalog`), B5 (`POST /api/aieval/runs/`, `EvalRun.provider`), B3 (`report.ai`, `verdict.ai`, War Room `messages[].provider/model`).

**Preserved:** `ScorecardPage.test` spies on `useAnalytics.useLatestEvalRun` / `useCalibration` / … — `ScorecardPage` keeps calling `useLatestEvalRun` for the default selection; the `Model eval calibration` heading text and the `Hit-rate … · Brier …` summary line for the selected run; `getByText("claude")` (exact) must still match exactly one element — the provider-calibration cell — so `AiAttribution` pills (which render `Claude · …`) are fine but never render a bare lowercase `claude`; where the eval model id now appears both in the runs table and the calibration copy, switch that test's `getByText(/claude-sonnet-4-6/)` to `getAllByText(...)[0]`; `data-testid="pm-card-<h>"`; War Room `Verdict` block content; `data-testid="ai-second-opinion"` and its copy.

- [ ] **Step 1: Failing tests**

`EvalSection.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockRuns = vi.fn();
const mockTrigger = vi.fn();
vi.mock("@/hooks/useAieval", () => ({
  useEvalRuns: () => mockRuns(),
  useTriggerEvalRun: () => ({ mutateAsync: mockTrigger, isPending: false }),
}));
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => ({ data: { models: [
  { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude", input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5, context_window: 1_000_000, supports_vision: true },
  { id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai", input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4, context_window: 1_050_000, supports_vision: true },
], defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol" } } }) }));
vi.mock("@/hooks/useProviderConfigs", () => ({ useProviderConfigs: () => ({ data: [] }) }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ push: vi.fn() }) }));

import EvalSection from "@/pages/scorecard/EvalSection";

const RUN = (o: object) => ({
  id: 1, created_at: "2026-09-01T00:00:00Z", source: "manual", label: "ab", provider: "openai", model: "gpt-5.6-sol",
  horizon: 30, n: 10, skipped: 0, scored: 10, hit_rate: 0.6, brier: 0.21, avg_confidence: 0.7, calibration_error: 0.1,
  calibration: [{ bin_low: 0.7, bin_high: 0.9, n: 8, hits: 5, observed_hit_rate: 0.625, mean_confidence: 0.8 }], ...o,
});

describe("EvalSection", () => {
  beforeEach(() => { mockTrigger.mockReset(); });

  it("lists runs with attribution and selects the latest by default", () => {
    mockRuns.mockReturnValue({ data: [RUN({ id: 2, provider: "claude", model: "claude-opus-5", hit_rate: 0.7 }), RUN({ id: 1 })], isLoading: false });
    render(<EvalSection latest={RUN({ id: 2, provider: "claude", model: "claude-opus-5", hit_rate: 0.7 })} />);
    expect(screen.getAllByTestId("ai-attribution")).toHaveLength(2);
    expect(screen.getByText(/How often claude-opus-5's directional call/)).toBeInTheDocument();
  });

  it("queues an eval with the chosen target and shows the billing warning", async () => {
    mockRuns.mockReturnValue({ data: [], isLoading: false });
    mockTrigger.mockResolvedValue({ queued: true });
    render(<EvalSection latest={undefined} />);
    await userEvent.click(screen.getByRole("button", { name: /run eval/i }));
    await userEvent.selectOptions(screen.getByLabelText("Provider"), "openai");
    expect(screen.getByText(/Makes up to 25 billed calls on OpenAI/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^queue eval$/i }));
    await waitFor(() => expect(mockTrigger).toHaveBeenCalledWith({ provider: "openai", model: "gpt-5.6-sol", horizon: 30, limit: 25, label: "manual" }));
  });
});
```

`PostMortemCard.attribution.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PostMortemCard } from "@/pages/thesis-detail/PostMortemCard";

describe("PostMortemCard attribution", () => {
  it("shows which provider wrote the narrative", () => {
    render(<PostMortemCard pm={{
      id: 1, horizon_days: 30, due_at: "2026-09-01T00:00:00Z", status: "done", forward_return_pct: 2.1, verdict: "correct",
      report: { summary: "s", what_worked: [], what_missed: [], lessons: [], would_repeat: true, ai: { provider: "openai", model: "gpt-5.6-sol" } },
      message_id: null, created_at: "2026-08-01T00:00:00Z", completed_at: "2026-09-01T00:00:00Z",
    }} />);
    expect(screen.getByTestId("ai-attribution").textContent).toBe("OpenAI · gpt-5.6-sol");
  });
});
```

(`verdict: "correct"` — use a value from `PostMortemVerdict` in `api/thesis.ts`.) For the War Room, extend the existing detail-page test if one exists (`ls frontend/src/__tests__ | grep -i warroom`) with a run whose `verdict.ai = { provider: "claude", model: "claude-opus-5" }` and assert the pill; else add a minimal test that mocks `@/hooks/useWarroom` and `@/hooks/useWarRoomLive`.

In `ScorecardPage.test.tsx`, add `provider: "claude"` to `EVAL_RUN`, mock `@/hooks/useAieval` (`useEvalRuns: () => ({ data: [EVAL_RUN], isLoading: false }), useTriggerEvalRun: () => ({ mutateAsync: vi.fn(), isPending: false })`) plus `@/hooks/useAiModels` / `@/hooks/useProviderConfigs` as above; the existing eval assertions must keep passing.

- [ ] **Step 2: Implement**

`api/aieval.ts`:

```ts
import { apiGet, apiPost } from "./client";

export type EvalReliabilityBucket = {
  bin_low: number; bin_high: number; n: number; hits: number;
  observed_hit_rate: number | null; mean_confidence: number | null;
};

/** One persisted offline eval run (`/api/aieval/runs/`). */
export type EvalRun = {
  id: number; created_at: string; source: string; label: string;
  provider: string; model: string; horizon: number | null;
  n: number; skipped: number; scored: number;
  hit_rate: number | null; brier: number | null; avg_confidence: number | null; calibration_error: number | null;
  calibration: EvalReliabilityBucket[];
};

export type EvalRunRequest = { provider: string; model: string; horizon: number; limit: number; label: string };
export type EvalRunQueued = EvalRunRequest & { queued: true };

export const fetchEvalRuns = () => apiGet<EvalRun[]>("/api/aieval/runs/");
export const fetchLatestEvalRun = () => apiGet<EvalRun | null>("/api/aieval/runs/latest/");
export const triggerEvalRun = (body: EvalRunRequest) => apiPost<EvalRunQueued>("/api/aieval/runs/", body);
```

`hooks/useAieval.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchEvalRuns, triggerEvalRun } from "@/api/aieval";

export function useEvalRuns(opts: { refetchInterval?: number | false } = {}) {
  return useQuery({ queryKey: ["aieval/runs"], queryFn: fetchEvalRuns, refetchInterval: opts.refetchInterval ?? false });
}

export function useTriggerEvalRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: triggerEvalRun,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["aieval/runs"] });
      qc.invalidateQueries({ queryKey: ["aieval/latest"] });
    },
  });
}
```

`hooks/useAnalytics.ts`: replace the local `EvalReliabilityBucket` / `EvalRunSummary` interfaces with `import type { EvalRun } from "@/api/aieval"; export type EvalRunSummary = EvalRun;` and `useLatestEvalRun` fetches `apiGet<EvalRun | null>("/api/aieval/runs/latest/")` (or `fetchLatestEvalRun`).

`api/thesis.ts`: `PostMortemReport` gains `ai?: { provider: string; model: string }`. `api/warroom.ts`: `WarRoomVerdict` gains `ai?: { provider: string; model: string }`.

`pages/scorecard/EvalRunsTable.tsx` — `<table>` of runs (`data-testid="eval-run-<id>"` rows, clickable via a `<button>` in the first cell, `aria-pressed` on the selected row): Date (`toLocaleDateString`), Target (`AiAttribution provider model`), Label (`label · source`), n / scored, Hit-rate, Brier, Cal. err. Wrapped in `min-w-0 overflow-x-auto`.

`pages/scorecard/EvalRunForm.tsx` — `ledger-surface p-4` form: `AiTargetPicker` (facts), horizon `<select aria-label="Horizon (days)">` over `FALLBACK_HORIZONS`, limit `<input type="number" aria-label="Row limit" min=1 max=100>`, label `<input aria-label="Label">`; warning `<p className="text-[12px] text-copper-300">Makes up to {limit} billed calls on {providerLabel(provider)}. Skipped automatically if that provider's cost cap is hit.</p>`; submit button text `Queue eval` (`ledger-cta`). On success: `push({ kind: "success", text: "Eval queued — it appears in the table when it finishes." })` and call `onQueued()`. On error: `push({ kind: "error", text: (e as Error).message })`.

`pages/scorecard/EvalSection.tsx`:

```tsx
export default function EvalSection({ latest }: { latest: EvalRun | undefined }) {
  const [pendingUntil, setPendingUntil] = useState<number | null>(null);
  const polling = pendingUntil !== null && Date.now() < pendingUntil;
  const { data: runs, isLoading } = useEvalRuns({ refetchInterval: polling ? 15_000 : false });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const selected = runs?.find((r) => r.id === selectedId) ?? latest ?? runs?.[0];
  return (
    <section>
      <div className="flex items-center justify-between gap-3 mb-2">
        <h2 className="font-semibold">Offline eval</h2>
        <button type="button" className="ledger-ghost" onClick={() => setShowForm((v) => !v)}>{showForm ? "Close" : "Run eval"}</button>
      </div>
      <p className="mb-3 text-sm text-ink-400">Replays frozen snapshots of decisive theses through a model and scores its directional calls. Compare providers here before trusting one.</p>
      {showForm && <EvalRunForm onQueued={() => setPendingUntil(Date.now() + 3 * 60_000)} />}
      {isLoading ? <SkeletonRows rows={3} /> : !runs || runs.length === 0
        ? <EmptyState title="No eval runs yet" body="Run one to measure a model's calibration on replayed snapshots." />
        : <EvalRunsTable runs={runs} selectedId={selected?.id ?? null} onSelect={setSelectedId} />}
      {selected && selected.scored > 0 && <EvalCalibration evalRun={selected} />}
    </section>
  );
}
```

Move today's `EvalCalibration` component from `ScorecardPage.tsx` into `EvalSection.tsx` unchanged (heading `Model eval calibration`, the "How often {model}'s directional call…" copy, the reliability table). `ScorecardPage` renders `<EvalSection latest={evalRun ?? undefined} />` where today it renders `{evalRun && evalRun.scored > 0 && <EvalCalibration evalRun={evalRun} />}`.

`PostMortemCard.tsx`: in the header flex row, before `<span className="flex-1" />`, add `{!isScheduled && isPopulatedReport(pm.report) && pm.report.ai && <AiAttribution provider={pm.report.ai.provider} model={pm.report.ai.model} />}` (`isPopulatedReport` is the file's existing type guard).

`api/warroom.ts`: `WarRoomMessage` gains `provider?: string | null; model?: string | null`. `WarRoomDetailPage.tsx`: `groupByPersona` keeps `{ text, provider, model }` per argument instead of a bare string; each lane renders `<AiAttribution provider model className="mb-1" />` above the argument when present; `Verdict`: after the "Verdict" eyebrow line add `{v.ai && <AiAttribution provider={v.ai.provider} model={v.ai.model} className="mt-1" />}`.

`AISecondOpinion.tsx`: after the horizon/agreement sentence, append `{data.provider && <AiAttribution provider={data.provider} model={data.model} className="ml-2" />}`; extend `AISecondOpinion.test.tsx` with a case whose payload carries `provider: "openai", model: "gpt-5.6-sol"` and asserts the pill text.

- [ ] **Step 3: Run and commit**

Run: `pnpm exec vitest run --project unit src/__tests__/EvalSection.test.tsx src/__tests__/ScorecardPage.test.tsx src/__tests__/PostMortemCard.attribution.test.tsx src/__tests__/WarRoomDetailPage.test.tsx src/__tests__/AISecondOpinion.test.tsx && pnpm lint`

```bash
git add frontend/src/api/aieval.ts frontend/src/hooks/useAieval.ts frontend/src/hooks/useAnalytics.ts frontend/src/api/thesis.ts frontend/src/api/warroom.ts frontend/src/pages/scorecard frontend/src/pages/ScorecardPage.tsx frontend/src/pages/thesis-detail/PostMortemCard.tsx frontend/src/pages/WarRoomDetailPage.tsx frontend/src/components/AISecondOpinion.tsx frontend/src/__tests__/EvalSection.test.tsx frontend/src/__tests__/ScorecardPage.test.tsx frontend/src/__tests__/PostMortemCard.attribution.test.tsx frontend/src/__tests__/WarRoomDetailPage.test.tsx frontend/src/__tests__/AISecondOpinion.test.tsx
LEFTHOOK=0 git commit -m "feat(frontend): offline-eval history and trigger on the scorecard; provider attribution on post-mortems and verdicts" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task F8: Merge, integration gates, notification kind, docs

**Files:**
- Modify: `frontend/src/api/observer.ts` (`NotificationDTO.kind` union + `"eval_done"`)
- Modify: `CLAUDE.md` (three lines, below)
- Modify: `docs/superpowers/specs/2026-09-20-provider-neutral-ui-design.md` (status line → "implemented on `feat/provider-neutral-ui`")

- [ ] **Step 1: Merge F2–F7 branches into `feat/provider-neutral-ui`** (orchestrator): `git merge --no-ff <branch>` one at a time; resolve any conflict in favour of keeping both sides' additions (they own disjoint files; only test fixture hunks can overlap).

- [ ] **Step 2: Notification kind**

`api/observer.ts`: `kind: "trigger" | "observer_done" | "error" | "cost_limit" | "backup" | "eval_done";`.

- [ ] **Step 3: Frontend gates**

```bash
cd $WT/frontend && pnpm install --frozen-lockfile --prefer-offline && pnpm lint && pnpm test:cov && pnpm depcruise && pnpm type-coverage
```

Expected: eslint + tsc clean; coverage ≥ 80/74/77/82; depcruise no violations (nothing under `src/api` imports UI); type-coverage ≥ 99. Fix regressions in place with `fix(frontend):` commits.

- [ ] **Step 4: Backend gates once more** (the merge added no backend code, but run `$PYTEST` and `$RUN web uv run python manage.py makemigrations --check --dry-run` to be sure).

- [ ] **Step 5: Docs**

`CLAUDE.md`:
- In "AI providers & capabilities", after the structured-output bullet, add: "**Frontend AI target/attribution primitives live in `frontend/src/components/ai/`** (`ProviderSelect`, `AiTargetPicker`, `ModelFacts`, `AiAttribution`, `CapabilityHint`, `ModeBadges`); model defaults come only from `useCatalog().defaultFor(provider)` (the `/api/schwab/models/` `defaults` map, seeded by `lib/modelDefaults.ts`) — never hard-code a model id in a component."
- In the eval bullet, append: "`EvalRun.provider` names the vendor (a Local model id does not); `POST /api/aieval/runs/` queues `analytics.aieval_run` (at-most-once, cap-preflighted) for a manual run; `aieval_scheduled_provider` picks the scheduled provider and a foreign model id falls back to that provider's catalog default."
- In "Backend wiring & security", after the `*_id` bullet, add: "**Cross-vendor model guard** — `apps.ai.catalog.foreign_model_error(provider, model)` rejects a catalog id owned by another provider in `TradingProfileSerializer`, `ProviderConfigSerializer` and `ObserverScheduleSerializer`; unknown ids (local names) pass. The observer's structured path resolves its model once via `run.py::_observer_model` (override → profile model on the profile's own provider → config default → catalog default, skipping foreign ids)."
- (B7 already rewrote the Prediction Ledger bullet's dedup key; confirm it reads `(ticker, horizon, profile, provider, model)` and mentions consensus extraction.)

Optional mechanical pass (skip if time is short): replace `claude-sonnet-4-6` / `gpt-5` default-model literals in `frontend/src/components/**/*.stories.tsx` with `claude-opus-5` / `gpt-5.6-sol` where they stand for "the default" (not where a story deliberately shows an older model).

Spec status line updated. Commit:

```bash
git add CLAUDE.md docs/superpowers/specs/2026-09-20-provider-neutral-ui-design.md frontend/src/api/observer.ts
LEFTHOOK=0 git commit -m "docs: provider-neutral UI conventions; eval_done notification kind" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review

- **Spec coverage:** §4.1→B1; §4.2→B1+B2; §4.3→B3 (model resolution, timeline status/error, War Room provider/model); §4.4→B4 (incl. default bump); §4.5→B5 (+B6 schema); §4.6→B7; §4.7→B7; §5.1→F1 (+F3/F4/F5/F6/F7 for the api files each owns); §5.2→F1 (incl. `ProviderModelPicker` trio); §5.3→F2 (incl. OpenAI base URL/probe/synced line, story); §5.4→F3; §5.5→F4 (incl. e2e xfails); §5.6→F5; §5.7→F6 (all kinds, call line, notices, failed pill, picker seed, stories); §5.8→F7; §5.9→F7 (post-mortem, verdict, persona lanes, second opinion); §6→every F task's styling notes; §8 gates→B6+F8.
- **Type consistency:** `AiTargetPicker` value `{ provider; model }` everywhere; `useCatalog().defaultFor` / `modelsFor` / `byId`; `AiAttribution` props `provider/model/cost/qualifier`; `ScheduleAiFields` value type `AiFieldsValue` = the seven schedule fields the PATCH sends; `EvalRun.provider` string; `ProviderSelect` `emptyOption` emits `""`; `StructuredKind` (7 kinds) and `StructuredReport` (observation | consensus | post-mortem) are defined once in `api/observation.ts` and consumed by `api/threads.ts`, `thread-detail/types.ts`, `StreamingMessage`, `ObserverTimelinePage`; `WarRoomVerdictContent` travels as `verdict` (not `report`) because the backend spreads it into content; `_observer_model(sched, cfg, provider_name)` is the only model resolver on the observer path.
- **Placeholders:** none — every code step carries its content; the only "read the file first" instructions point at exact symbols (`usd`, the post-mortem test that patches the narrative, the War Room task test).
