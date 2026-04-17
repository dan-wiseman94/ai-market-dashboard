# M3 Snapshots + AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End-to-end one-shot consult flow. User picks a trading profile, chooses which market data to include, enters an objective, and clicks Capture. The backend fans out to M2 market services, assembles a snapshot payload, streams a Claude response over a WebSocket, and renders it with live markdown in the UI. A thread, messages, and AIRun rows are persisted with cost tracking and a daily cap.

**Architecture:**
- `apps.ai` (new) — provider abstraction (`Provider` Protocol, `ClaudeProvider`), model catalog with pricing, cost math.
- `apps.snapshots` (new) — `Snapshot`/`SnapshotSection` models, the `capture()` orchestrator, the payload serializer, Celery tasks, WebSocket consumer for per-snapshot progress.
- `apps.threads` (new) — `Thread`/`Message`/`AIRun` models, thread-level WebSocket consumer, the AI run Celery task.
- `apps.profiles` (modify) — add `TradingProfile` model (watchlists already exist).
- `apps.secrets` (modify) — add `ProviderConfig` model (Fernet-encrypted API keys + per-provider cost caps + default model).
- Frontend — new `/profiles`, `/snapshot`, `/threads`, `/threads/:id` pages + WebSocket provider.

**Tech Stack (additions to M2):**
- `anthropic` Python SDK (Claude API).
- `tiktoken` (OpenAI tokenizer, used as a fast approximation for Claude when we can't afford a live `count_tokens` call).
- Frontend: `react-markdown` + `remark-gfm` for streaming markdown render.

---

## File Layout Added by This Plan

```
backend/apps/
├── ai/                               # New — provider abstraction
│   ├── __init__.py  apps.py
│   ├── catalog.py                    # ModelInfo + pricing table (Claude models for M3; OpenAI+Local in M4)
│   ├── types.py                      # RunRequest, RunEvent union, CostEstimate
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                   # Provider Protocol
│   │   └── claude.py                 # ClaudeProvider (async streaming)
│   ├── cost.py                       # cost_usd_for_run(usage, model) + daily-cap guard
│   └── tests/
│       ├── test_catalog.py
│       ├── test_cost.py
│       └── test_claude_provider.py
│
├── snapshots/                        # New — capture pipeline
│   ├── __init__.py  apps.py  admin.py
│   ├── models.py                     # Snapshot, SnapshotSection
│   ├── services.py                   # capture(profile, objective, includes, notes, source)
│   ├── serializer.py                 # serialize_for_ai(snapshot) → AIPayload
│   ├── token_budget.py               # estimate + prune
│   ├── tasks.py                      # Celery fan-out + finalize
│   ├── consumers.py                  # snapshot.<id> WS channel
│   ├── serializers.py                # DRF
│   ├── urls.py  views.py             # POST/GET /api/snapshots/
│   ├── migrations/
│   └── tests/
│       ├── test_models.py
│       ├── test_serializer.py
│       ├── test_token_budget.py
│       ├── test_capture.py
│       ├── test_consumer.py
│       └── test_endpoints.py
│
├── threads/                          # New — conversation persistence
│   ├── __init__.py  apps.py  admin.py
│   ├── models.py                     # Thread, Message, AIRun
│   ├── services.py                   # start_consult(profile, snapshot, objective) → Thread
│   ├── tasks.py                      # run_ai_on_thread(thread_id, message_id) → streams
│   ├── consumers.py                  # thread.<id> WS channel
│   ├── serializers.py
│   ├── urls.py  views.py             # POST /threads/, GET /threads/, POST /threads/<id>/send
│   ├── migrations/
│   └── tests/
│       ├── test_models.py
│       ├── test_run_ai.py
│       ├── test_consumer.py
│       └── test_endpoints.py
│
├── profiles/                         # Modify — add TradingProfile
│   ├── models.py                     # + TradingProfile
│   ├── serializers.py                # + TradingProfileSerializer
│   ├── urls.py  views.py             # + /api/profiles/ endpoints
│   ├── migrations/0002_tradingprofile.py
│   └── tests/test_trading_profile.py (new)
│
└── secrets/                          # Modify — add ProviderConfig
    ├── models.py                     # + ProviderConfig
    ├── serializers.py                # new file for ProviderConfig (not used elsewhere in M2)
    ├── urls.py                       # + provider-config endpoints
    ├── views.py                      # + provider-config views
    ├── migrations/0002_providerconfig.py
    └── tests/test_provider_config.py (new)

backend/config/
├── routing.py                        # Modify — add snapshot.<id> and thread.<id> consumers

frontend/src/
├── api/
│   ├── ai.ts                         # fetchModels, fetchProviderConfigs, updateProviderConfig, totalCostToday
│   ├── profiles.ts                   # CRUD
│   ├── snapshots.ts                  # POST + GET
│   └── threads.ts                    # list, get, send message
├── hooks/
│   ├── useProfiles.ts
│   ├── useProviderConfigs.ts
│   ├── useSnapshot.ts                # GET one + live progress via WS
│   ├── useThread.ts                  # GET + live message stream
│   ├── useWebSocket.ts               # singleton WS connection (one per tab)
│   ├── useChannel.ts                 # subscribe to thread.<id> / snapshot.<id>
│   └── useCreateSnapshot.ts
├── components/
│   ├── ProviderConfigCard.tsx        # API key + cost cap + default model
│   ├── ProfileForm.tsx
│   ├── SnapshotSectionPicker.tsx     # multi-select checkboxes
│   ├── SnapshotProgress.tsx          # per-section started/done/failed
│   ├── StreamingMessage.tsx          # markdown render of partial text
│   ├── CostChip.tsx                  # $0.04 pill, clickable → /costs
│   └── ThreadHeader.tsx              # profile + snapshot summary + cost
├── pages/
│   ├── ProfilesPage.tsx
│   ├── ProvidersPage.tsx             # split from Settings; rendered AT /settings alongside Schwab
│   ├── SnapshotComposerPage.tsx      # /snapshot
│   ├── ThreadsPage.tsx               # /threads
│   ├── ThreadDetailPage.tsx          # /threads/:id
│   └── Dashboard.tsx                 # + "Snapshot now" CTA
├── realtime/
│   ├── WebSocketProvider.tsx         # context; opens /ws/events/ with a shared socket
│   └── subscriptions.ts              # channel subscribe/unsubscribe plumbing
└── router.tsx                        # + 4 new routes
```

Responsibility recap:
- **`apps.ai`** owns the provider abstraction + cost math. It doesn't know about snapshots or threads.
- **`apps.snapshots`** captures data via M2 services; produces an opaque payload suitable for the AI layer.
- **`apps.threads`** owns conversation persistence and drives the AI layer. It depends on `apps.ai` + `apps.snapshots` but neither depends on it.

---

## Task 1: Install M3 dependencies

**Files:** `pyproject.toml`, `frontend/package.json`

- [ ] **Step 1.1: Add Python deps**

In `[project].dependencies`, after `"drf-nested-routers>=0.94,<1.0",`:

```toml
    "anthropic>=0.72,<1.0",
    "tiktoken>=0.8,<1.0",
```

- [ ] **Step 1.2: Add frontend deps**

In `frontend/package.json` `dependencies`:

```json
    "react-markdown": "^9.0.1",
    "remark-gfm": "^4.0.0"
```

- [ ] **Step 1.3: Rebuild + verify**

```bash
cd /home/dan/ai-dashboard
docker compose build web worker beat frontend
docker volume rm ai-dashboard_frontend_node_modules
docker compose up -d
sleep 10
docker compose exec web python -c "import anthropic, tiktoken; print('ok')"
docker compose exec frontend node -e "require('react-markdown'); require('remark-gfm'); console.log('ok')"
```

Expected: both print `ok`.

- [ ] **Step 1.4: Commit**

```bash
git add pyproject.toml frontend/package.json
git commit -m "chore(deps): add anthropic + tiktoken + react-markdown for M3"
```

---

## Task 2: TradingProfile model + migration (TDD)

**Files:**
- Modify: `backend/apps/profiles/models.py`
- Create: `backend/apps/profiles/tests/test_trading_profile.py`
- Create: migration

- [ ] **Step 2.1: Write failing test**

Write `backend/apps/profiles/tests/test_trading_profile.py`:

```python
import pytest

from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_create_profile_with_defaults():
    p = TradingProfile.objects.create(
        name="0DTE scalps",
        style="Fast SPY scalps. 1-5 min holds. VWAP reclaims.",
    )
    assert p.active is True
    assert p.default_includes == ["quotes", "positions", "breadth"]
    assert p.default_provider == "claude"
    assert p.default_model == "claude-sonnet-4-6"


@pytest.mark.django_db
def test_profile_stores_custom_includes():
    p = TradingProfile.objects.create(
        name="Swings",
        style="Multi-day swings.",
        default_includes=["quotes", "ohlc", "positions", "notes"],
        default_model="claude-opus-4-7",
    )
    p.refresh_from_db()
    assert p.default_includes == ["quotes", "ohlc", "positions", "notes"]
    assert p.default_model == "claude-opus-4-7"


@pytest.mark.django_db
def test_profile_name_unique():
    TradingProfile.objects.create(name="A", style="x")
    with pytest.raises(Exception):
        TradingProfile.objects.create(name="A", style="y")
```

- [ ] **Step 2.2: Add `TradingProfile` to `backend/apps/profiles/models.py`**

Append to the existing file:

```python
class TradingProfile(models.Model):
    """A named trading style + AI preferences applied when capturing snapshots."""

    DEFAULT_INCLUDES: ClassVar[list[str]] = ["quotes", "positions", "breadth"]

    name = models.CharField(max_length=100, unique=True)
    style = models.TextField(help_text="The trading style text. Prepended as system prompt.")
    default_includes = models.JSONField(default=list)
    default_provider = models.CharField(max_length=32, default="claude")
    default_model = models.CharField(max_length=100, default="claude-sonnet-4-6")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-active", "name"]

    def save(self, *args, **kwargs) -> None:
        if not self.default_includes:
            self.default_includes = list(self.DEFAULT_INCLUDES)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name
```

**Note:** `ClassVar` is already imported at the top of the file (from M2's ruff fixes). If not, add `from typing import ClassVar` at the top.

- [ ] **Step 2.3: Migrate + test**

```bash
docker compose exec web python manage.py makemigrations profiles
docker compose exec web python manage.py migrate
docker compose exec web pytest apps/profiles/tests/test_trading_profile.py -v
```

Expected: 3 passed.

- [ ] **Step 2.4: Commit**

```bash
git add backend/apps/profiles/models.py backend/apps/profiles/migrations/ \
        backend/apps/profiles/tests/test_trading_profile.py
git commit -m "feat(profiles): TradingProfile model with defaults"
```

---

## Task 3: `ProviderConfig` model + migration (TDD)

**Files:**
- Modify: `backend/apps/secrets/models.py`
- Create: `backend/apps/secrets/tests/test_provider_config.py`

- [ ] **Step 3.1: Write failing test**

Write `backend/apps/secrets/tests/test_provider_config.py`:

```python
import pytest
from decimal import Decimal

from apps.secrets.models import ProviderConfig


@pytest.mark.django_db
def test_create_provider_config_defaults():
    pc = ProviderConfig.objects.create(provider="claude")
    assert pc.enabled is True
    assert pc.supports_vision is True
    assert pc.daily_cost_cap_usd == Decimal("10.00")
    assert pc.default_model == ""          # user fills in; catalog may suggest
    assert pc.base_url == ""               # Anthropic / OpenAI use SDK default


@pytest.mark.django_db
def test_api_key_roundtrip_encrypted():
    pc = ProviderConfig.objects.create(provider="claude", api_key="sk-ant-xxx")
    pc.refresh_from_db()
    assert pc.api_key == "sk-ant-xxx"


@pytest.mark.django_db
def test_one_row_per_provider():
    ProviderConfig.objects.create(provider="claude")
    with pytest.raises(Exception):
        ProviderConfig.objects.create(provider="claude")
```

- [ ] **Step 3.2: Add `ProviderConfig` to `backend/apps/secrets/models.py`**

Append:

```python
class ProviderConfig(models.Model):
    """Knobs for a given AI provider. API key is Fernet-encrypted at rest.

    One row per provider — created on first settings write, read by apps.ai.
    """

    PROVIDER_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("claude", "Anthropic Claude"),
        ("openai", "OpenAI"),
        ("local", "Local (OpenAI-compatible)"),
    ]

    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, unique=True)
    # api_key stored as EncryptedJSONField containing {"k": "<the key>"} so both
    # the Fernet wrapper and JSON schema stay the same as ApiCredential.token.
    _api_key = EncryptedJSONField(null=True, blank=True, db_column="api_key")
    base_url = models.CharField(max_length=255, blank=True, default="")
    default_model = models.CharField(max_length=100, blank=True, default="")
    enabled = models.BooleanField(default=True)
    supports_vision = models.BooleanField(default=True)
    daily_cost_cap_usd = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("10.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "secrets_providerconfig"

    @property
    def api_key(self) -> str:
        return (self._api_key or {}).get("k", "") if self._api_key else ""

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key = {"k": value} if value else None

    def __str__(self) -> str:
        return f"{self.get_provider_display()} ({'on' if self.enabled else 'off'})"
```

Add imports at top of file if missing:

```python
from decimal import Decimal
from typing import ClassVar
```

- [ ] **Step 3.3: Migrate + test**

```bash
docker compose exec web python manage.py makemigrations secrets_app
docker compose exec web python manage.py migrate
docker compose exec web pytest apps/secrets/tests/test_provider_config.py -v
```

Expected: 3 passed.

- [ ] **Step 3.4: Commit**

```bash
git add backend/apps/secrets/models.py backend/apps/secrets/migrations/ \
        backend/apps/secrets/tests/test_provider_config.py
git commit -m "feat(secrets): ProviderConfig model (encrypted api key + cost cap)"
```

---

## Task 4: Snapshots app — models + migration (TDD)

**Files:**
- Create: `backend/apps/snapshots/__init__.py`, `apps.py`, `admin.py`, `models.py`
- Create: `backend/apps/snapshots/tests/__init__.py`, `test_models.py`
- Modify: `backend/config/settings/base.py` — register app

- [ ] **Step 4.1: Scaffold**

```bash
mkdir -p /home/dan/ai-dashboard/backend/apps/snapshots/tests
touch /home/dan/ai-dashboard/backend/apps/snapshots/__init__.py
touch /home/dan/ai-dashboard/backend/apps/snapshots/tests/__init__.py
```

Write `backend/apps/snapshots/apps.py`:

```python
from django.apps import AppConfig


class SnapshotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.snapshots"
    label = "snapshots"
```

Edit `backend/config/settings/base.py` — add `"apps.snapshots",` to `INSTALLED_APPS` after `"apps.profiles",`.

- [ ] **Step 4.2: Write failing test**

Write `backend/apps/snapshots/tests/test_models.py`:

```python
import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


@pytest.mark.django_db
def test_create_snapshot_with_sections():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(
        profile=p,
        objective="Looking for long entry on NVDA",
        includes=["quotes", "positions"],
        source="manual",
    )
    assert s.status == "pending"
    assert s.captured_at is not None

    SnapshotSection.objects.create(snapshot=s, kind="quotes", payload={"SPY": {"last": 550}}, status="done")
    SnapshotSection.objects.create(snapshot=s, kind="positions", payload=[], status="failed", error="network")
    assert s.sections.count() == 2


@pytest.mark.django_db
def test_snapshot_finalizes_when_all_sections_done():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, objective="", includes=["quotes"], source="manual")

    s.status = "ready"
    s.save()
    s.refresh_from_db()
    assert s.status == "ready"


@pytest.mark.django_db
def test_section_kind_choices():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual")
    for kind in ["quotes", "ohlc", "positions", "breadth", "notes"]:
        SnapshotSection.objects.create(snapshot=s, kind=kind, payload={}, status="done")
    assert s.sections.count() == 5
```

- [ ] **Step 4.3: Write `backend/apps/snapshots/models.py`**

```python
"""Snapshot domain. A Snapshot is a captured market state + metadata."""
from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.profiles.models import TradingProfile


class Snapshot(models.Model):
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("ready", "Ready"),
        ("failed", "Failed"),
    ]
    SOURCE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("manual", "Manual"),
        ("observer", "Observer"),
        ("trigger", "Trigger"),
    ]

    profile = models.ForeignKey(TradingProfile, on_delete=models.PROTECT, related_name="snapshots")
    objective = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    includes = models.JSONField(default=list)  # ["quotes", "ohlc", ...]
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="manual")
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["-captured_at"])]
        ordering: ClassVar[list[str]] = ["-captured_at"]

    def __str__(self) -> str:
        return f"Snapshot #{self.pk} ({self.status})"


class SnapshotSection(models.Model):
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("quotes", "Quotes"),
        ("ohlc", "OHLC"),
        ("chain", "Option chain"),
        ("positions", "Positions"),
        ("breadth", "Market breadth"),
        ("news", "News"),
        ("notes", "User notes"),
        ("image", "Chart image"),
    ]
    SECTION_STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    snapshot = models.ForeignKey(Snapshot, on_delete=models.CASCADE, related_name="sections")
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=SECTION_STATUS_CHOICES, default="pending")
    error = models.TextField(blank=True, default="")

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["snapshot", "kind"], name="uniq_snapshot_section"),
        ]

    def __str__(self) -> str:
        return f"{self.snapshot_id}:{self.kind} ({self.status})"
```

- [ ] **Step 4.4: Migrate + test + commit**

```bash
docker compose exec web python manage.py makemigrations snapshots
docker compose exec web python manage.py migrate
docker compose exec web pytest apps/snapshots/tests/test_models.py -v
git add backend/apps/snapshots backend/config/settings/base.py
git commit -m "feat(snapshots): Snapshot + SnapshotSection models"
```

Expected: 3 passed.

---

## Task 5: Threads app — models + migration (TDD)

**Files:**
- Create: `backend/apps/threads/__init__.py`, `apps.py`, `admin.py`, `models.py`
- Create: `backend/apps/threads/tests/__init__.py`, `test_models.py`
- Modify: `backend/config/settings/base.py` — register app

- [ ] **Step 5.1: Scaffold**

```bash
mkdir -p /home/dan/ai-dashboard/backend/apps/threads/tests
touch /home/dan/ai-dashboard/backend/apps/threads/__init__.py
touch /home/dan/ai-dashboard/backend/apps/threads/tests/__init__.py
```

Write `backend/apps/threads/apps.py`:

```python
from django.apps import AppConfig


class ThreadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.threads"
    label = "threads"
```

Register in `INSTALLED_APPS` after `"apps.snapshots",`.

- [ ] **Step 5.2: Write failing test**

Write `backend/apps/threads/tests/test_models.py`:

```python
import pytest
from decimal import Decimal

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Thread, Message, AIRun


@pytest.mark.django_db
def test_create_consult_thread_with_snapshot():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", status="ready")
    t = Thread.objects.create(kind="consult", profile=p, pinned_snapshot=s, title="NVDA long?")
    assert t.kind == "consult"
    assert t.pinned_snapshot == s


@pytest.mark.django_db
def test_message_streaming_states():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    m = Message.objects.create(thread=t, role="user", content={"text": "hi"})
    assert m.status == "done"  # user messages don't stream; default done
    a = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="streaming")
    assert a.status == "streaming"


@pytest.mark.django_db
def test_airun_persisted_after_stream():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    m = Message.objects.create(thread=t, role="assistant", content={"text": "hello"}, status="done")
    r = AIRun.objects.create(
        message=m,
        provider="claude",
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cached_tokens=200,
        cost_usd=Decimal("0.0105"),
        latency_ms=1234,
        status="done",
    )
    assert r.cost_usd == Decimal("0.0105")
```

- [ ] **Step 5.3: Write `backend/apps/threads/models.py`**

```python
"""Conversations: Thread + Message + AIRun."""
from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


class Thread(models.Model):
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("consult", "One-shot consult"),
        ("chat", "Ongoing chat"),
        ("observer", "Observer timeline"),
    ]

    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="consult")
    title = models.CharField(max_length=200, blank=True, default="")
    profile = models.ForeignKey(
        TradingProfile, null=True, blank=True, on_delete=models.PROTECT, related_name="threads",
    )
    pinned_snapshot = models.ForeignKey(
        Snapshot, null=True, blank=True, on_delete=models.SET_NULL, related_name="threads",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["kind", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title or f'#{self.pk}'}"


class Message(models.Model):
    ROLE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("done", "Done"),
        ("streaming", "Streaming"),
        ("failed", "Failed"),
    ]

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.JSONField(default=dict)  # {"text": "...", "blocks": [...]} — flexible
    snapshot_ref = models.ForeignKey(
        Snapshot, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages_referencing",
    )
    parent_message = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="branches",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="done")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["thread_id", "created_at"]
        indexes: ClassVar = [models.Index(fields=["thread_id", "created_at"])]

    def __str__(self) -> str:
        return f"{self.role}@thread#{self.thread_id}"


class AIRun(models.Model):
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("streaming", "Streaming"),
        ("done", "Done"),
        ("failed", "Failed"),
        ("cost_capped", "Cost capped"),
    ]

    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="ai_run")
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=100)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cached_tokens = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    error = models.TextField(blank=True, default="")
    raw_request_summary = models.JSONField(default=dict)  # redacted headers, model name, …
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"AIRun {self.provider}/{self.model} (${self.cost_usd})"
```

- [ ] **Step 5.4: Migrate + test + commit**

```bash
docker compose exec web python manage.py makemigrations threads
docker compose exec web python manage.py migrate
docker compose exec web pytest apps/threads/tests/test_models.py -v
git add backend/apps/threads backend/config/settings/base.py
git commit -m "feat(threads): Thread + Message + AIRun models"
```

Expected: 3 passed.

---

## Task 6: AI model catalog + cost math (TDD)

**Files:**
- Create: `backend/apps/ai/__init__.py`, `apps.py`, `catalog.py`, `cost.py`, `types.py`
- Create: `backend/apps/ai/tests/__init__.py`, `test_catalog.py`, `test_cost.py`
- Modify: `backend/config/settings/base.py` — register app

- [ ] **Step 6.1: Scaffold**

```bash
mkdir -p /home/dan/ai-dashboard/backend/apps/ai/{providers,tests}
touch /home/dan/ai-dashboard/backend/apps/ai/__init__.py
touch /home/dan/ai-dashboard/backend/apps/ai/providers/__init__.py
touch /home/dan/ai-dashboard/backend/apps/ai/tests/__init__.py
```

Write `backend/apps/ai/apps.py`:

```python
from django.apps import AppConfig


class AIConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    label = "ai"
```

Register in `INSTALLED_APPS` after `"apps.threads",`.

- [ ] **Step 6.2: Write failing tests**

Write `backend/apps/ai/tests/test_catalog.py`:

```python
import pytest

from apps.ai.catalog import list_models, get_model, KNOWN_PROVIDERS


def test_lists_claude_models():
    models = list_models("claude")
    names = [m.id for m in models]
    assert "claude-opus-4-7" in names
    assert "claude-sonnet-4-6" in names
    assert "claude-haiku-4-5-20251001" in names


def test_get_model_returns_pricing():
    m = get_model("claude", "claude-sonnet-4-6")
    assert m is not None
    assert m.provider == "claude"
    assert m.input_per_mtok > 0
    assert m.output_per_mtok > m.input_per_mtok
    assert m.supports_vision is True


def test_get_model_unknown_returns_none():
    assert get_model("claude", "imaginary-model") is None


def test_known_providers_contains_claude_openai_local():
    assert "claude" in KNOWN_PROVIDERS
    assert "openai" in KNOWN_PROVIDERS
    assert "local" in KNOWN_PROVIDERS
```

Write `backend/apps/ai/tests/test_cost.py`:

```python
import pytest
from decimal import Decimal

from apps.ai.cost import cost_usd_for, TokenUsage


def test_cost_basic_sonnet():
    # Sonnet 4.6: $3/M in, $15/M out; 10k in + 5k out = 0.03 + 0.075 = $0.105
    usage = TokenUsage(input_tokens=10_000, output_tokens=5_000)
    cost = cost_usd_for("claude", "claude-sonnet-4-6", usage)
    assert cost == pytest.approx(Decimal("0.1050"), abs=Decimal("0.0001"))


def test_cost_counts_cached_tokens_cheaper():
    # With 10k input, 2k cached, 5k output:
    # non-cached input: 8k * $3/M = 0.024
    # cached input:     2k * $0.375/M = 0.00075  (Anthropic cache reads ~10% of input)
    # output:           5k * $15/M = 0.075
    usage = TokenUsage(input_tokens=10_000, output_tokens=5_000, cached_tokens=2_000)
    cost = cost_usd_for("claude", "claude-sonnet-4-6", usage)
    assert cost == pytest.approx(Decimal("0.09975"), abs=Decimal("0.0001"))


def test_cost_for_unknown_model_uses_provider_ceiling():
    """Unknown hosted models fall back to the highest-priced catalog entry."""
    usage = TokenUsage(input_tokens=1000, output_tokens=1000)
    cost = cost_usd_for("claude", "claude-made-up-model", usage)
    # Ceiling is Opus 4.7: $15/M in, $75/M out → 0.015 + 0.075 = 0.09
    assert cost > Decimal("0.08")


def test_cost_local_provider_is_zero():
    usage = TokenUsage(input_tokens=100_000, output_tokens=50_000)
    assert cost_usd_for("local", "anything", usage) == Decimal("0")
```

- [ ] **Step 6.3: Write `backend/apps/ai/types.py`**

```python
"""Shared types for the AI provider layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RoleType = Literal["user", "assistant", "system"]


@dataclass
class ChatMessage:
    role: RoleType
    content: str


@dataclass
class RunRequest:
    model: str
    system: str                           # trading style + instructions (goes into system prompt)
    messages: list[ChatMessage]
    max_tokens: int = 4096
    temperature: float = 1.0
    cache_system: bool = True             # Claude-specific: mark system prompt as cacheable


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0                # "cache_read_input_tokens" in Anthropic's vocabulary


@dataclass
class CostEstimate:
    low: float
    high: float
    model: str


# Streaming events — a normalized union the WS layer consumes.
@dataclass
class TextDelta:
    type: Literal["text_delta"] = "text_delta"
    text: str = ""


@dataclass
class UsageEvent:
    type: Literal["usage"] = "usage"
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass
class DoneEvent:
    type: Literal["done"] = "done"


@dataclass
class ErrorEvent:
    type: Literal["error"] = "error"
    message: str = ""


RunEvent = TextDelta | UsageEvent | DoneEvent | ErrorEvent
```

- [ ] **Step 6.4: Write `backend/apps/ai/catalog.py`**

```python
"""Model catalog with per-model pricing. Source of truth for cost estimation.

Pricing as of 2026-04. Update when providers revise. Sticking with conservative
estimates — if a model drops in price, we'll over-estimate cost for a day or two.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


KNOWN_PROVIDERS = ["claude", "openai", "local"]


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    id: str
    name: str
    input_per_mtok: float    # $ per 1M input tokens
    output_per_mtok: float   # $ per 1M output tokens
    cached_per_mtok: float   # $ per 1M cache-read tokens (usually 10% of input)
    context_window: int
    supports_vision: bool
    supports_cache: bool


_CATALOG: list[ModelInfo] = [
    # Anthropic Claude
    ModelInfo(
        provider="claude", id="claude-opus-4-7", name="Claude Opus 4.7",
        input_per_mtok=15.00, output_per_mtok=75.00, cached_per_mtok=1.875,
        context_window=200_000, supports_vision=True, supports_cache=True,
    ),
    ModelInfo(
        provider="claude", id="claude-sonnet-4-6", name="Claude Sonnet 4.6",
        input_per_mtok=3.00, output_per_mtok=15.00, cached_per_mtok=0.375,
        context_window=200_000, supports_vision=True, supports_cache=True,
    ),
    ModelInfo(
        provider="claude", id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5",
        input_per_mtok=1.00, output_per_mtok=5.00, cached_per_mtok=0.125,
        context_window=200_000, supports_vision=True, supports_cache=True,
    ),
    # OpenAI + local come in M4.
]


def list_models(provider: str | None = None) -> list[ModelInfo]:
    if provider is None:
        return list(_CATALOG)
    return [m for m in _CATALOG if m.provider == provider]


def get_model(provider: str, model_id: str) -> ModelInfo | None:
    for m in _CATALOG:
        if m.provider == provider and m.id == model_id:
            return m
    return None


def ceiling_for_provider(provider: str) -> ModelInfo | None:
    """Highest-priced model for a provider — used as a cost-ceiling fallback."""
    entries = [m for m in _CATALOG if m.provider == provider]
    if not entries:
        return None
    return max(entries, key=lambda m: m.output_per_mtok)
```

- [ ] **Step 6.5: Write `backend/apps/ai/cost.py`**

```python
"""Cost math + daily cap guard."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from apps.ai.catalog import ceiling_for_provider, get_model
from apps.ai.types import TokenUsage


class CostCapExceededError(RuntimeError):
    """Raised to abort an AI run when the provider's daily cap is breached."""


def cost_usd_for(provider: str, model_id: str, usage: TokenUsage) -> Decimal:
    """Compute USD cost for the given run. Returns Decimal for DB-friendly math.

    For local provider, always $0 (cost_unknown=True in catalog terms).
    For hosted providers with an unknown model, falls back to the provider's
    highest-priced catalog entry as a safety ceiling (design spec §6.3).
    """
    if provider == "local":
        return Decimal("0")

    model = get_model(provider, model_id)
    if model is None:
        model = ceiling_for_provider(provider)
    if model is None:
        # Unknown provider entirely — refuse to silently free-ride.
        return Decimal("0")

    non_cached = max(0, usage.input_tokens - usage.cached_tokens)
    input_cost = _dec(non_cached) / Decimal("1000000") * _dec(model.input_per_mtok)
    cached_cost = _dec(usage.cached_tokens) / Decimal("1000000") * _dec(model.cached_per_mtok)
    output_cost = _dec(usage.output_tokens) / Decimal("1000000") * _dec(model.output_per_mtok)
    return (input_cost + cached_cost + output_cost).quantize(Decimal("0.000001"))


def _dec(v: float | int) -> Decimal:
    return Decimal(str(v))


def daily_spend_usd(provider: str) -> Decimal:
    """Sum today's AIRun.cost_usd for the given provider (UTC day)."""
    from django.db.models import Sum
    from apps.threads.models import AIRun

    today_start = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    agg = AIRun.objects.filter(
        provider=provider, created_at__gte=today_start,
    ).aggregate(total=Sum("cost_usd"))
    return agg["total"] or Decimal("0")


def check_daily_cap(provider: str, cap_usd: Decimal, prospective_cost: Decimal = Decimal("0")) -> None:
    """Raise if today's spend + the prospective cost would exceed cap."""
    spent = daily_spend_usd(provider)
    if spent + prospective_cost > cap_usd:
        raise CostCapExceededError(
            f"{provider} daily cap ${cap_usd} would be exceeded "
            f"(spent ${spent}, this run ~${prospective_cost})"
        )
```

- [ ] **Step 6.6: Test + commit**

```bash
docker compose exec web pytest apps/ai/tests/test_catalog.py apps/ai/tests/test_cost.py -v
git add backend/apps/ai/__init__.py backend/apps/ai/apps.py backend/apps/ai/catalog.py \
        backend/apps/ai/cost.py backend/apps/ai/types.py backend/apps/ai/providers/__init__.py \
        backend/apps/ai/tests/ backend/config/settings/base.py
git commit -m "feat(ai): model catalog + cost math + cap guard"
```

Expected: 8 passed.

---

## Task 7: Provider Protocol + ClaudeProvider (TDD)

**Files:**
- Create: `backend/apps/ai/providers/base.py`
- Create: `backend/apps/ai/providers/claude.py`
- Create: `backend/apps/ai/tests/test_claude_provider.py`

- [ ] **Step 7.1: Write failing test**

Write `backend/apps/ai/tests/test_claude_provider.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.ai.providers.claude import ClaudeProvider
from apps.ai.types import ChatMessage, RunRequest, TextDelta, UsageEvent, DoneEvent


class _FakeStream:
    """Mimics anthropic's async streaming context manager."""

    def __init__(self, text_chunks, usage):
        self._text_chunks = text_chunks
        self._usage = usage

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    def __aiter__(self):
        async def gen():
            for c in self._text_chunks:
                yield MagicMock(type="text", text=c)
            yield MagicMock(type="message_stop")
        return gen()

    async def get_final_message(self):
        msg = MagicMock()
        msg.usage.input_tokens = self._usage["input"]
        msg.usage.output_tokens = self._usage["output"]
        msg.usage.cache_read_input_tokens = self._usage.get("cached", 0)
        msg.usage.cache_creation_input_tokens = 0
        return msg


@pytest.mark.asyncio
async def test_claude_streams_text_and_usage(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(return_value=_FakeStream(
        ["Hello", " ", "world"], {"input": 100, "output": 50, "cached": 10},
    ))

    with patch("apps.ai.providers.claude.AsyncAnthropic", return_value=fake_client):
        provider = ClaudeProvider(api_key="sk-ant-test")
        req = RunRequest(
            model="claude-sonnet-4-6",
            system="You are helpful.",
            messages=[ChatMessage(role="user", content="hi")],
        )
        events = []
        async for evt in provider.run(req):
            events.append(evt)

    text_parts = [e.text for e in events if isinstance(e, TextDelta)]
    assert "".join(text_parts) == "Hello world"

    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.usage.input_tokens == 100
    assert usage.usage.output_tokens == 50
    assert usage.usage.cached_tokens == 10

    assert isinstance(events[-1], DoneEvent)


@pytest.mark.asyncio
async def test_claude_sends_cache_control_when_enabled():
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(return_value=_FakeStream(["hi"], {"input": 1, "output": 1}))

    with patch("apps.ai.providers.claude.AsyncAnthropic", return_value=fake_client):
        provider = ClaudeProvider(api_key="sk-ant-test")
        req = RunRequest(
            model="claude-sonnet-4-6",
            system="LONG STYLE PROMPT",
            messages=[ChatMessage(role="user", content="hi")],
            cache_system=True,
        )
        async for _ in provider.run(req):
            pass

    kwargs = fake_client.messages.stream.call_args.kwargs
    sys_blocks = kwargs["system"]
    assert isinstance(sys_blocks, list)
    assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}
```

- [ ] **Step 7.2: Write `backend/apps/ai/providers/base.py`**

```python
"""Provider Protocol — structural interface for Claude/OpenAI/Local."""
from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from apps.ai.types import RunEvent, RunRequest


@runtime_checkable
class Provider(Protocol):
    name: str

    def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        """Yield RunEvents: text_delta* → usage → done | error."""
        ...
```

- [ ] **Step 7.3: Write `backend/apps/ai/providers/claude.py`**

```python
"""Claude provider — streams via anthropic SDK."""
from __future__ import annotations

from typing import AsyncIterator

from anthropic import AsyncAnthropic

from apps.ai.types import (
    ChatMessage, DoneEvent, ErrorEvent, RunEvent, RunRequest, TextDelta, TokenUsage, UsageEvent,
)


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, base_url: str = "") -> None:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**kwargs)

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        system_blocks = _system_blocks(req.system, cache=req.cache_system)
        messages = [{"role": m.role, "content": m.content} for m in req.messages]

        try:
            async with self._client.messages.stream(
                model=req.model,
                system=system_blocks,
                messages=messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(text=event.text)
                final = await stream.get_final_message()
            u = final.usage
            yield UsageEvent(usage=TokenUsage(
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cached_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            ))
            yield DoneEvent()
        except Exception as exc:  # noqa: BLE001 — normalize to ErrorEvent
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")


def _system_blocks(system: str, *, cache: bool) -> list[dict]:
    block: dict = {"type": "text", "text": system}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return [block]
```

- [ ] **Step 7.4: Test + commit**

```bash
docker compose exec web pytest apps/ai/tests/test_claude_provider.py -v
git add backend/apps/ai/providers backend/apps/ai/tests/test_claude_provider.py
git commit -m "feat(ai): provider protocol + ClaudeProvider with streaming + cache_control"
```

Expected: 2 passed.

---

## Task 8: Payload serializer + token budget (TDD)

**Files:**
- Create: `backend/apps/snapshots/serializer.py`
- Create: `backend/apps/snapshots/token_budget.py`
- Create: `backend/apps/snapshots/tests/test_serializer.py`
- Create: `backend/apps/snapshots/tests/test_token_budget.py`

- [ ] **Step 8.1: Write failing tests**

Write `backend/apps/snapshots/tests/test_serializer.py`:

```python
import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import serialize_for_ai


@pytest.mark.django_db
def test_serializes_quotes_section_as_table():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", objective="buy the dip?")
    SnapshotSection.objects.create(
        snapshot=s, kind="quotes", status="done",
        payload={"SPY": {"last": 550.0, "pct_change": 0.5, "bid": 549.9, "ask": 550.1,
                         "volume": 12345, "high": 552.0, "low": 548.0}},
    )
    out = serialize_for_ai(s)
    assert "## Quotes" in out
    assert "SPY" in out
    assert "550" in out
    assert "buy the dip" in out  # objective at top


@pytest.mark.django_db
def test_missing_section_marked_unavailable():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes", "news"], source="manual")
    SnapshotSection.objects.create(
        snapshot=s, kind="news", status="failed", error="Finnhub 503",
    )
    out = serialize_for_ai(s)
    assert "News" in out
    assert "unavailable" in out
    assert "Finnhub 503" in out


@pytest.mark.django_db
def test_ohlc_section_csv_block():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["ohlc"], source="manual")
    SnapshotSection.objects.create(
        snapshot=s, kind="ohlc", status="done",
        payload={"ticker": "SPY", "timeframe": "1m", "bars": [
            {"ts": "2026-01-01T00:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100},
            {"ts": "2026-01-01T00:01:00+00:00", "open": 2, "high": 3, "low": 1, "close": 3, "volume": 200},
        ]},
    )
    out = serialize_for_ai(s)
    assert "ts,open,high,low,close,volume" in out
    assert "```" in out


@pytest.mark.django_db
def test_notes_section_appears_at_top():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["notes"], source="manual", notes="looking risk-on")
    out = serialize_for_ai(s)
    # Notes text should appear before any section headings
    idx_notes = out.find("looking risk-on")
    idx_any_section = min(
        (out.find(h) for h in ["## Quotes", "## OHLC", "## Positions"] if out.find(h) != -1),
        default=10**9,
    )
    assert idx_notes < idx_any_section or idx_any_section == 10**9
```

Write `backend/apps/snapshots/tests/test_token_budget.py`:

```python
import pytest

from apps.snapshots.token_budget import estimate_tokens, prune_to_budget


def test_estimate_tokens_returns_positive():
    t = estimate_tokens("Hello, world!")
    assert t > 0


def test_prune_returns_same_when_small():
    sections = {
        "quotes": "tiny",
        "ohlc": "tiny",
        "chain": "tiny",
        "news": "tiny",
    }
    out, pruned = prune_to_budget(sections, max_tokens=10_000)
    assert out == sections
    assert pruned == []


def test_prune_drops_chain_first_then_news():
    # Construct oversized sections
    big = "x " * 50_000
    sections = {
        "chain": big,
        "news": big,
        "ohlc": "medium",
        "quotes": "small",
    }
    out, pruned = prune_to_budget(sections, max_tokens=100)
    # Chain should be pruned first; then news; quotes should survive
    assert "chain" not in out
    assert "quotes" in out
    assert "chain" in pruned
```

- [ ] **Step 8.2: Write `backend/apps/snapshots/serializer.py`**

```python
"""AI payload serializer: Snapshot → single markdown string for the user message."""
from __future__ import annotations

from apps.snapshots.models import Snapshot
from apps.snapshots.token_budget import prune_to_budget


def serialize_for_ai(snapshot: Snapshot, *, max_tokens: int = 40_000) -> str:
    """Return the Snapshot as a compact markdown blob suitable for the `user` turn.

    The trading style belongs in the system prompt and is NOT included here —
    that's the caller's responsibility (the AI run task does that).
    """
    sections_by_kind = {s.kind: s for s in snapshot.sections.all()}
    parts: list[str] = []

    # Objective + notes at top.
    if snapshot.objective.strip():
        parts.append(f"**Objective:** {snapshot.objective.strip()}")
    if snapshot.notes.strip():
        parts.append(f"**Notes:** {snapshot.notes.strip()}")

    rendered: dict[str, str] = {}

    # Render each included kind.
    for kind in snapshot.includes:
        sec = sections_by_kind.get(kind)
        if sec is None or sec.status == "failed":
            err = (sec.error if sec else "missing")
            rendered[kind] = f"## {_title(kind)}\n_(unavailable: {err})_"
            continue
        text = _render_section(kind, sec.payload)
        if text:
            rendered[kind] = text

    pruned_sections, pruned_kinds = prune_to_budget(rendered, max_tokens=max_tokens)
    for kind in snapshot.includes:
        if kind in pruned_sections:
            parts.append(pruned_sections[kind])
    if pruned_kinds:
        parts.append(f"_(pruned for token budget: {', '.join(pruned_kinds)})_")

    return "\n\n".join(parts).strip() or "_(empty snapshot)_"


def _title(kind: str) -> str:
    return {
        "quotes": "Quotes", "ohlc": "OHLC", "chain": "Option chain",
        "positions": "Positions", "breadth": "Market breadth",
        "news": "News", "notes": "Notes", "image": "Chart image",
    }.get(kind, kind.title())


def _render_section(kind: str, payload) -> str:
    if kind == "quotes":
        return _render_quotes(payload)
    if kind == "ohlc":
        return _render_ohlc(payload)
    if kind == "positions":
        return _render_positions(payload)
    if kind == "breadth":
        return _render_breadth(payload)
    if kind == "news":
        return _render_news(payload)
    if kind == "notes":
        # User's notes live on Snapshot.notes directly; this section is optional and rarely used.
        return ""
    return f"## {_title(kind)}\n```json\n{payload}\n```"


def _render_quotes(payload: dict) -> str:
    if not payload:
        return "## Quotes\n_(empty)_"
    lines = ["## Quotes", "| Ticker | Last | %chg | Bid | Ask | Vol | High | Low |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for ticker, q in payload.items():
        lines.append(
            f"| {ticker} | {_fmt(q.get('last'))} | {_fmt(q.get('pct_change'))}% | "
            f"{_fmt(q.get('bid'))} | {_fmt(q.get('ask'))} | {_fmt_int(q.get('volume'))} | "
            f"{_fmt(q.get('high'))} | {_fmt(q.get('low'))} |"
        )
    return "\n".join(lines)


def _render_ohlc(payload: dict) -> str:
    bars = payload.get("bars", [])
    if not bars:
        return "## OHLC\n_(empty)_"
    header = f"## OHLC ({payload.get('ticker', '?')} @ {payload.get('timeframe', '?')})"
    csv_lines = ["ts,open,high,low,close,volume"]
    for b in bars:
        csv_lines.append(f"{b['ts']},{b['open']},{b['high']},{b['low']},{b['close']},{b['volume']}")
    return f"{header}\n```csv\n" + "\n".join(csv_lines) + "\n```"


def _render_positions(payload: list) -> str:
    if not payload:
        return "## Positions\n_(empty)_"
    lines = ["## Positions", "| Ticker | Qty | Avg | Mkt Val | Day P/L | Unrealized |",
             "|---|---:|---:|---:|---:|---:|"]
    total_day = total_unrl = 0.0
    for p in payload:
        total_day += p.get("day_pl") or 0
        total_unrl += p.get("unrealized_pl") or 0
        lines.append(
            f"| {p['ticker']} | {_fmt(p.get('qty'))} | {_fmt(p.get('avg_cost'))} | "
            f"{_fmt(p.get('mkt_value'))} | {_fmt(p.get('day_pl'))} | {_fmt(p.get('unrealized_pl'))} |"
        )
    lines.append(f"| **Total** |  |  |  | **{total_day:.2f}** | **{total_unrl:.2f}** |")
    return "\n".join(lines)


def _render_breadth(payload: dict) -> str:
    lines = ["## Market breadth"]
    lines.append(f"- SPY: {_fmt(payload.get('spy_last'))}")
    lines.append(f"- QQQ: {_fmt(payload.get('qqq_last'))}")
    lines.append(f"- VIX: {_fmt(payload.get('vix_last'))}")
    if payload.get("sectors"):
        lines.append("- Sectors: " + ", ".join(f"{k}={_fmt(v)}" for k, v in payload["sectors"].items()))
    if payload.get("breadth"):
        lines.append("- Breadth: " + ", ".join(f"{k}={_fmt(v)}" for k, v in payload["breadth"].items()))
    return "\n".join(lines)


def _render_news(payload: list) -> str:
    if not payload:
        return "## News\n_(no headlines)_"
    lines = ["## News"]
    for item in payload[:15]:
        lines.append(f"- **{item.get('headline', '?')}** — {item.get('summary', '')} ({item.get('source', '')})")
    return "\n".join(lines)


def _fmt(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_int(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return str(v)
```

- [ ] **Step 8.3: Write `backend/apps/snapshots/token_budget.py`**

```python
"""Token estimation + pruning for payload sections.

We use tiktoken (GPT-4 tokenizer) as a cheap proxy for Claude's tokenizer.
It's close enough for budgeting — the goal is to stay well below the model
context, not to be byte-accurate.
"""
from __future__ import annotations

import tiktoken


_ENC = tiktoken.get_encoding("cl100k_base")

# Prune in this order — least useful first.
_PRUNE_ORDER = ["chain", "news", "ohlc", "breadth", "quotes", "positions"]


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENC.encode(text))


def prune_to_budget(
    sections: dict[str, str],
    *,
    max_tokens: int,
) -> tuple[dict[str, str], list[str]]:
    """Progressively drop sections until the total is under max_tokens.

    Returns (kept_sections, pruned_kinds).
    """
    kept = dict(sections)
    pruned: list[str] = []

    def total() -> int:
        return sum(estimate_tokens(v) for v in kept.values())

    for kind in _PRUNE_ORDER:
        if total() <= max_tokens:
            break
        if kind in kept:
            del kept[kind]
            pruned.append(kind)

    return kept, pruned
```

- [ ] **Step 8.4: Test + commit**

```bash
docker compose exec web pytest apps/snapshots/tests/test_serializer.py apps/snapshots/tests/test_token_budget.py -v
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/token_budget.py backend/apps/snapshots/tests/
git commit -m "feat(snapshots): payload serializer + token budget + pruning"
```

Expected: 7 passed.

---

## Task 9: Capture orchestrator (TDD)

**Files:**
- Create: `backend/apps/snapshots/services.py`
- Create: `backend/apps/snapshots/tasks.py`
- Create: `backend/apps/snapshots/tests/test_capture.py`

- [ ] **Step 9.1: Write failing test**

Write `backend/apps/snapshots/tests/test_capture.py`:

```python
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.services import capture


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_creates_snapshot_with_sections():
    p = TradingProfile.objects.create(name="P", style="x")

    with patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 550}}), \
         patch("apps.snapshots.services.fetch_positions", return_value=[{"ticker": "SPY", "qty": 1}]):
        snap = capture(
            profile=p,
            objective="short SPY?",
            includes=["quotes", "positions"],
            notes="",
            source="manual",
            watchlist_tickers=["SPY"],
        )

    snap.refresh_from_db()
    assert snap.status == "ready"
    kinds = list(snap.sections.values_list("kind", "status"))
    assert ("quotes", "done") in kinds
    assert ("positions", "done") in kinds


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_records_partial_failure():
    p = TradingProfile.objects.create(name="P", style="x")

    with patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 550}}), \
         patch("apps.snapshots.services.fetch_positions", side_effect=RuntimeError("schwab down")):
        snap = capture(
            profile=p, objective="", includes=["quotes", "positions"], notes="",
            source="manual", watchlist_tickers=["SPY"],
        )

    snap.refresh_from_db()
    assert snap.status == "ready"  # at least one succeeded
    quotes_sec = snap.sections.get(kind="quotes")
    positions_sec = snap.sections.get(kind="positions")
    assert quotes_sec.status == "done"
    assert positions_sec.status == "failed"
    assert "schwab down" in positions_sec.error


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_fails_when_all_sections_fail():
    p = TradingProfile.objects.create(name="P", style="x")

    with patch("apps.snapshots.services.fetch_quotes", side_effect=RuntimeError("down")):
        snap = capture(
            profile=p, objective="", includes=["quotes"], notes="",
            source="manual", watchlist_tickers=["SPY"],
        )

    snap.refresh_from_db()
    assert snap.status == "failed"
```

- [ ] **Step 9.2: Write `backend/apps/snapshots/services.py`**

```python
"""Snapshot capture orchestration — sync variant (Celery task calls it)."""
from __future__ import annotations

from typing import Iterable

from apps.market.services.context import fetch_market_context
from apps.market.services.ohlc import fetch_ohlc
from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


_FETCHERS = {
    "quotes": lambda *, watchlist_tickers, **_: {"_kind": "quotes", "data": fetch_quotes(watchlist_tickers)},
    "ohlc": lambda *, watchlist_tickers, ohlc_ticker=None, ohlc_timeframe="1m", ohlc_bars=60, **_: {
        "_kind": "ohlc",
        "data": {
            "ticker": ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
            "timeframe": ohlc_timeframe,
            "bars": fetch_ohlc(
                ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
                timeframe=ohlc_timeframe, bars=ohlc_bars,
            ),
        },
    },
    "positions": lambda **_: {"_kind": "positions", "data": fetch_positions()},
    "breadth": lambda **_: {"_kind": "breadth", "data": fetch_market_context()},
    "notes": lambda **_: {"_kind": "notes", "data": {}},  # user notes live on Snapshot.notes; nothing to fetch
}


def capture(
    *,
    profile: TradingProfile,
    objective: str,
    includes: list[str],
    notes: str = "",
    source: str = "manual",
    watchlist_tickers: Iterable[str] = (),
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
) -> Snapshot:
    """Synchronously capture a snapshot. Each included section is fetched in order.

    (Parallel fan-out via Celery lands in the broader M6 observer work — this
    M3 version runs serially which is fine at single-user scale and keeps the
    consult flow easy to reason about.)
    """
    snap = Snapshot.objects.create(
        profile=profile, objective=objective, notes=notes,
        includes=includes, source=source, status="pending",
    )

    ok_count = 0
    for kind in includes:
        fetcher = _FETCHERS.get(kind)
        section = SnapshotSection.objects.create(snapshot=snap, kind=kind, status="pending", payload={})
        if fetcher is None:
            section.status = "failed"
            section.error = f"No fetcher registered for section kind '{kind}'"
            section.save()
            continue
        try:
            result = fetcher(
                watchlist_tickers=list(watchlist_tickers),
                ohlc_ticker=ohlc_ticker,
                ohlc_timeframe=ohlc_timeframe,
                ohlc_bars=ohlc_bars,
            )
            section.payload = result["data"] or {}
            section.status = "done"
            section.save()
            ok_count += 1
        except Exception as exc:  # noqa: BLE001
            section.status = "failed"
            section.error = f"{type(exc).__name__}: {exc}"
            section.save()

    snap.status = "ready" if ok_count > 0 else "failed"
    snap.save()
    return snap
```

- [ ] **Step 9.3: Write `backend/apps/snapshots/tasks.py`**

```python
"""Celery wrappers around capture."""
from __future__ import annotations

from celery import shared_task

from apps.snapshots.services import capture


@shared_task(name="snapshots.capture")
def capture_task(
    *,
    profile_id: int,
    objective: str,
    includes: list[str],
    notes: str = "",
    source: str = "manual",
    watchlist_tickers: list[str] | None = None,
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
) -> int:
    """Run capture and return the Snapshot id."""
    from apps.profiles.models import TradingProfile

    profile = TradingProfile.objects.get(id=profile_id)
    snap = capture(
        profile=profile, objective=objective, includes=includes,
        notes=notes, source=source, watchlist_tickers=watchlist_tickers or [],
        ohlc_ticker=ohlc_ticker, ohlc_timeframe=ohlc_timeframe, ohlc_bars=ohlc_bars,
    )
    return snap.id
```

- [ ] **Step 9.4: Test + commit**

```bash
docker compose exec web pytest apps/snapshots/tests/test_capture.py -v
git add backend/apps/snapshots/services.py backend/apps/snapshots/tasks.py backend/apps/snapshots/tests/test_capture.py
git commit -m "feat(snapshots): capture orchestrator + celery task"
```

Expected: 3 passed.

---

## Task 10: Snapshot WebSocket consumer (TDD)

**Files:**
- Create: `backend/apps/snapshots/consumers.py`
- Create: `backend/apps/snapshots/tests/test_consumer.py`
- Modify: `backend/config/routing.py`

- [ ] **Step 10.1: Write failing test**

Write `backend/apps/snapshots/tests/test_consumer.py`:

```python
import pytest
from channels.testing import WebsocketCommunicator

from config.asgi import application
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_snapshot_consumer_connects_and_closes():
    from channels.db import database_sync_to_async
    p = await database_sync_to_async(TradingProfile.objects.create)(name="P", style="x")
    snap = await database_sync_to_async(Snapshot.objects.create)(
        profile=p, includes=["quotes"], source="manual",
    )
    communicator = WebsocketCommunicator(application, f"/ws/snapshots/{snap.id}/")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_broadcast_section_done_event():
    from channels.db import database_sync_to_async
    from channels.layers import get_channel_layer

    p = await database_sync_to_async(TradingProfile.objects.create)(name="P", style="x")
    snap = await database_sync_to_async(Snapshot.objects.create)(
        profile=p, includes=["quotes"], source="manual",
    )
    communicator = WebsocketCommunicator(application, f"/ws/snapshots/{snap.id}/")
    connected, _ = await communicator.connect()
    assert connected

    layer = get_channel_layer()
    await layer.group_send(
        f"snapshot.{snap.id}",
        {"type": "snapshot_event", "payload": {"event": "section_done", "kind": "quotes"}},
    )

    msg = await communicator.receive_json_from(timeout=2)
    assert msg == {"event": "section_done", "kind": "quotes"}
    await communicator.disconnect()
```

- [ ] **Step 10.2: Write `backend/apps/snapshots/consumers.py`**

```python
"""Per-snapshot WebSocket channel."""
from __future__ import annotations

from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class SnapshotConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.snapshot_id = int(self.scope["url_route"]["kwargs"]["snapshot_id"])
        self.group_name = f"snapshot.{self.snapshot_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def snapshot_event(self, event: dict[str, Any]) -> None:
        """Receive group_send with type=snapshot_event; forward payload to the client."""
        await self.send_json(event["payload"])
```

- [ ] **Step 10.3: Update `backend/config/routing.py`**

```python
"""Channels WebSocket URL routing."""
from django.urls import path

from apps.core.consumers import PingConsumer
from apps.snapshots.consumers import SnapshotConsumer

websocket_urlpatterns = [
    path("ws/ping/", PingConsumer.as_asgi()),
    path("ws/snapshots/<int:snapshot_id>/", SnapshotConsumer.as_asgi()),
]
```

- [ ] **Step 10.4: Test + commit**

```bash
docker compose exec web pytest apps/snapshots/tests/test_consumer.py -v
git add backend/apps/snapshots/consumers.py backend/config/routing.py backend/apps/snapshots/tests/test_consumer.py
git commit -m "feat(snapshots): per-snapshot WebSocket consumer + routing"
```

Expected: 2 passed.

---

## Task 11: Broadcast capture progress over WebSocket

**Files:**
- Modify: `backend/apps/snapshots/services.py` (add broadcasts)
- Create: `backend/apps/snapshots/tests/test_broadcast.py`

- [ ] **Step 11.1: Write failing test**

Write `backend/apps/snapshots/tests/test_broadcast.py`:

```python
from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture


@pytest.mark.django_db
def test_capture_broadcasts_section_events():
    p = TradingProfile.objects.create(name="P", style="x")
    events = []

    def collect(group, msg):
        events.append((group, msg))

    with patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 1}}), \
         patch("apps.snapshots.services.fetch_positions", side_effect=RuntimeError("x")), \
         patch("apps.snapshots.services._broadcast", side_effect=collect):
        capture(profile=p, objective="", includes=["quotes", "positions"],
                source="manual", watchlist_tickers=["SPY"])

    # We expect: section_started quotes, section_done quotes, section_started positions, section_failed positions, ready
    kinds = [msg["event"] for _, msg in events]
    assert "section_started" in kinds
    assert "section_done" in kinds
    assert "section_failed" in kinds
    assert "ready" in kinds
```

- [ ] **Step 11.2: Add `_broadcast` helper + call it from `capture()`**

In `backend/apps/snapshots/services.py`, add near the top:

```python
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def _broadcast(snapshot_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        f"snapshot.{snapshot_id}",
        {"type": "snapshot_event", "payload": payload},
    )
```

Then in `capture()`, after creating the Snapshot row, and around each section fetch:

```python
# after creating snap
_broadcast(snap.id, {"event": "pending", "snapshot_id": snap.id, "includes": includes})

# in the for loop — before fetcher:
_broadcast(snap.id, {"event": "section_started", "kind": kind})

# on success:
_broadcast(snap.id, {"event": "section_done", "kind": kind})

# on failure:
_broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})

# at the end:
_broadcast(snap.id, {"event": "ready" if ok_count > 0 else "failed", "snapshot_id": snap.id})
```

- [ ] **Step 11.3: Test + commit**

```bash
docker compose exec web pytest apps/snapshots/tests/test_broadcast.py apps/snapshots/tests/test_capture.py -v
git add backend/apps/snapshots/services.py backend/apps/snapshots/tests/test_broadcast.py
git commit -m "feat(snapshots): broadcast per-section progress over WS"
```

Expected: 4 passed (3 capture + 1 broadcast).

---

## Task 12: Thread WebSocket consumer (TDD)

**Files:**
- Create: `backend/apps/threads/consumers.py`
- Create: `backend/apps/threads/tests/test_consumer.py`
- Modify: `backend/config/routing.py`

- [ ] **Step 12.1: Write failing test**

Write `backend/apps/threads/tests/test_consumer.py`:

```python
import pytest
from channels.testing import WebsocketCommunicator

from config.asgi import application


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_thread_consumer_forwards_text_delta():
    from channels.db import database_sync_to_async
    from channels.layers import get_channel_layer

    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread

    p = await database_sync_to_async(TradingProfile.objects.create)(name="P", style="x")
    t = await database_sync_to_async(Thread.objects.create)(kind="consult", profile=p, title="x")

    communicator = WebsocketCommunicator(application, f"/ws/threads/{t.id}/")
    connected, _ = await communicator.connect()
    assert connected

    layer = get_channel_layer()
    await layer.group_send(
        f"thread.{t.id}",
        {"type": "thread_event", "payload": {"event": "text_delta", "message_id": 1, "text": "Hello"}},
    )
    msg = await communicator.receive_json_from(timeout=2)
    assert msg == {"event": "text_delta", "message_id": 1, "text": "Hello"}
    await communicator.disconnect()
```

- [ ] **Step 12.2: Write `backend/apps/threads/consumers.py`**

```python
"""Per-thread WebSocket channel."""
from __future__ import annotations

from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ThreadConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.thread_id = int(self.scope["url_route"]["kwargs"]["thread_id"])
        self.group_name = f"thread.{self.thread_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def thread_event(self, event: dict[str, Any]) -> None:
        await self.send_json(event["payload"])
```

- [ ] **Step 12.3: Update routing**

Edit `backend/config/routing.py`:

```python
from django.urls import path

from apps.core.consumers import PingConsumer
from apps.snapshots.consumers import SnapshotConsumer
from apps.threads.consumers import ThreadConsumer

websocket_urlpatterns = [
    path("ws/ping/", PingConsumer.as_asgi()),
    path("ws/snapshots/<int:snapshot_id>/", SnapshotConsumer.as_asgi()),
    path("ws/threads/<int:thread_id>/", ThreadConsumer.as_asgi()),
]
```

- [ ] **Step 12.4: Test + commit**

```bash
docker compose exec web pytest apps/threads/tests/test_consumer.py -v
git add backend/apps/threads/consumers.py backend/config/routing.py backend/apps/threads/tests/test_consumer.py
git commit -m "feat(threads): per-thread WebSocket consumer + routing"
```

Expected: 1 passed.

---

## Task 13: AI run Celery task (TDD)

**Files:**
- Create: `backend/apps/threads/tasks.py`
- Create: `backend/apps/threads/tests/test_run_ai.py`

- [ ] **Step 13.1: Write failing test**

Write `backend/apps/threads/tests/test_run_ai.py`:

```python
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Thread, Message
from apps.threads.tasks import run_ai_on_message


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_run_ai_appends_assistant_message_and_airun():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-test")
    p = TradingProfile.objects.create(name="P", style="You trade.")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    user_msg = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import DoneEvent, TextDelta, TokenUsage, UsageEvent

    async def fake_stream(self, req):
        yield TextDelta(text="Hello")
        yield TextDelta(text=" world")
        yield UsageEvent(usage=TokenUsage(input_tokens=100, output_tokens=50, cached_tokens=0))
        yield DoneEvent()

    with patch("apps.threads.tasks.ClaudeProvider.run", fake_stream):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=user_msg.id).get(timeout=5)

    assert result["ok"] is True
    assistant = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert "Hello world" in assistant.content.get("text", "")
    assert assistant.status == "done"
    run = assistant.ai_run
    assert run.provider == "claude"
    assert run.input_tokens == 100
    assert run.output_tokens == 50
    assert run.cost_usd > 0


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_run_ai_marks_failed_on_error():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-test")
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import ErrorEvent

    async def fake_stream(self, req):
        yield ErrorEvent(message="Anthropic rate limit")

    with patch("apps.threads.tasks.ClaudeProvider.run", fake_stream):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=u.id).get(timeout=5)

    assert result["ok"] is False
    assistant = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert assistant.status == "failed"
    assert "rate limit" in assistant.error
```

- [ ] **Step 13.2: Write `backend/apps/threads/tasks.py`**

```python
"""AI run Celery task — drives ClaudeProvider and broadcasts to the thread channel."""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.db import transaction

from apps.ai.cost import CostCapExceededError, check_daily_cap, cost_usd_for
from apps.ai.providers.claude import ClaudeProvider
from apps.ai.types import (
    ChatMessage, DoneEvent, ErrorEvent, RunRequest, TextDelta, UsageEvent,
)
from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread


def _broadcast(thread_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        f"thread.{thread_id}", {"type": "thread_event", "payload": payload}
    )


@shared_task(name="threads.run_ai_on_message")
def run_ai_on_message(*, thread_id: int, user_message_id: int) -> dict:
    thread = Thread.objects.select_related("profile").get(id=thread_id)
    profile = thread.profile
    user_msg = Message.objects.get(id=user_message_id)

    provider_name = (profile.default_provider if profile else "claude")
    model_id = (profile.default_model if profile else "claude-sonnet-4-6")

    try:
        cfg = ProviderConfig.objects.get(provider=provider_name)
    except ProviderConfig.DoesNotExist:
        assistant = Message.objects.create(
            thread=thread, role="assistant", content={"text": ""}, status="failed",
            error=f"No API key configured for provider '{provider_name}'. Visit /settings.",
        )
        _broadcast(thread_id, {"event": "error", "message_id": assistant.id, "error": assistant.error})
        return {"ok": False, "error": "no_key"}

    # Cost pre-check — treat unknown usage conservatively (ceiling).
    try:
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
    except CostCapExceededError as exc:
        assistant = Message.objects.create(
            thread=thread, role="assistant", content={"text": ""}, status="failed",
            error=str(exc),
        )
        _broadcast(thread_id, {"event": "cost_capped", "message_id": assistant.id, "error": str(exc)})
        return {"ok": False, "error": "cost_capped"}

    # Build the request.
    system = (profile.style if profile else "")
    history = list(Message.objects.filter(thread=thread, role__in=["user", "assistant"]).order_by("created_at"))
    chat_messages = []
    for m in history:
        chat_messages.append(ChatMessage(role=m.role, content=_extract_text(m)))

    # If the user_msg was already in history, don't double-add. If not, do.
    if not any(m.id == user_msg.id for m in history):
        chat_messages.append(ChatMessage(role="user", content=_extract_text(user_msg)))

    req = RunRequest(model=model_id, system=system, messages=chat_messages, cache_system=True)

    # Create the streaming assistant message up front so the UI has an id to subscribe to.
    assistant = Message.objects.create(
        thread=thread, role="assistant", content={"text": ""}, status="streaming",
    )
    _broadcast(thread_id, {"event": "message_started", "message_id": assistant.id})

    provider = ClaudeProvider(api_key=cfg.api_key, base_url=cfg.base_url or "")
    t0 = time.perf_counter()
    buffer: list[str] = []
    usage = None
    err: str | None = None

    async def drive():
        nonlocal usage, err
        async for evt in provider.run(req):
            if isinstance(evt, TextDelta):
                buffer.append(evt.text)
                _broadcast(thread_id, {
                    "event": "text_delta", "message_id": assistant.id, "text": evt.text,
                })
            elif isinstance(evt, UsageEvent):
                usage = evt.usage
            elif isinstance(evt, ErrorEvent):
                err = evt.message
            elif isinstance(evt, DoneEvent):
                return

    asyncio.run(drive())
    latency_ms = int((time.perf_counter() - t0) * 1000)

    with transaction.atomic():
        if err:
            assistant.content = {"text": "".join(buffer)}
            assistant.status = "failed"
            assistant.error = err
            assistant.save()
            AIRun.objects.create(
                message=assistant, provider=provider_name, model=model_id,
                status="failed", error=err, latency_ms=latency_ms,
            )
            _broadcast(thread_id, {"event": "error", "message_id": assistant.id, "error": err})
            return {"ok": False, "error": err}

        assistant.content = {"text": "".join(buffer)}
        assistant.status = "done"
        assistant.save()

        cost = Decimal("0")
        if usage is not None:
            cost = cost_usd_for(provider_name, model_id, usage)
        AIRun.objects.create(
            message=assistant, provider=provider_name, model=model_id,
            input_tokens=(usage.input_tokens if usage else 0),
            output_tokens=(usage.output_tokens if usage else 0),
            cached_tokens=(usage.cached_tokens if usage else 0),
            cost_usd=cost, latency_ms=latency_ms, status="done",
        )
        _broadcast(thread_id, {
            "event": "message_done", "message_id": assistant.id, "cost_usd": str(cost),
        })
        return {"ok": True}


def _extract_text(m: Message) -> str:
    c = m.content or {}
    if isinstance(c, dict) and "text" in c:
        return c["text"]
    return str(c)
```

- [ ] **Step 13.3: Test + commit**

```bash
docker compose exec web pytest apps/threads/tests/test_run_ai.py -v
git add backend/apps/threads/tasks.py backend/apps/threads/tests/test_run_ai.py
git commit -m "feat(threads): run_ai_on_message Celery task with streaming + cost tracking"
```

Expected: 2 passed.

---

## Task 14: Thread + Snapshot DRF endpoints (TDD)

**Files:**
- Create: `backend/apps/snapshots/serializers.py`, `urls.py`, `views.py`
- Create: `backend/apps/snapshots/tests/test_endpoints.py`
- Create: `backend/apps/threads/serializers.py`, `urls.py`, `views.py`
- Create: `backend/apps/threads/tests/test_endpoints.py`
- Modify: `backend/config/urls.py`

- [ ] **Step 14.1: Write failing endpoint tests**

Write `backend/apps/snapshots/tests/test_endpoints.py`:

```python
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def profile():
    import pytest_django
    return None  # created per-test


@pytest.mark.django_db
def test_create_snapshot_kicks_off_capture(api):
    p = TradingProfile.objects.create(name="P", style="x")
    with patch("apps.snapshots.views.capture_task.delay") as task:
        task.return_value.id = "task-1"
        resp = api.post(
            "/api/snapshots/",
            {
                "profile_id": p.id,
                "objective": "test",
                "includes": ["quotes"],
                "watchlist_tickers": ["SPY"],
            },
            format="json",
        )
    assert resp.status_code == 202
    body = resp.json()
    assert "id" in body
    assert body["status"] == "pending"


@pytest.mark.django_db
def test_get_snapshot_returns_with_sections(api):
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", status="ready")
    SnapshotSection.objects.create(snapshot=s, kind="quotes", status="done", payload={"SPY": {"last": 1}})
    r = api.get(f"/api/snapshots/{s.id}/")
    assert r.status_code == 200
    assert r.json()["sections"][0]["kind"] == "quotes"
```

Write `backend/apps/threads/tests/test_endpoints.py`:

```python
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Thread, Message


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_create_consult_thread(api):
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", status="ready")
    resp = api.post("/api/threads/", {
        "kind": "consult", "profile_id": p.id, "pinned_snapshot_id": s.id, "title": "NVDA long?",
    }, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "consult"
    assert body["profile"]["id"] == p.id


@pytest.mark.django_db
def test_send_message_enqueues_ai_run(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    with patch("apps.threads.views.run_ai_on_message.delay") as enqueue:
        enqueue.return_value.id = "task-1"
        r = api.post(f"/api/threads/{t.id}/send/", {"text": "hello"}, format="json")
    assert r.status_code == 202
    user_msg = Message.objects.get(thread=t, role="user")
    assert user_msg.content["text"] == "hello"
    enqueue.assert_called_once()
```

- [ ] **Step 14.2: Refactor services — split row creation from fetching**

`capture()` currently creates the Snapshot row AND fetches sections. The view path needs to create the row synchronously (so the 202 can return the id) and have the Celery task fill in sections. Split it.

Replace the body of `backend/apps/snapshots/services.py` entirely with:

```python
"""Snapshot capture orchestration."""
from __future__ import annotations

from typing import Iterable

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.market.services.context import fetch_market_context
from apps.market.services.ohlc import fetch_ohlc
from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


_FETCHERS = {
    "quotes": lambda *, watchlist_tickers, **_: {"data": fetch_quotes(watchlist_tickers)},
    "ohlc": lambda *, watchlist_tickers, ohlc_ticker=None, ohlc_timeframe="1m", ohlc_bars=60, **_: {
        "data": {
            "ticker": ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
            "timeframe": ohlc_timeframe,
            "bars": fetch_ohlc(
                ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
                timeframe=ohlc_timeframe, bars=ohlc_bars,
            ),
        },
    },
    "positions": lambda **_: {"data": fetch_positions()},
    "breadth": lambda **_: {"data": fetch_market_context()},
    "notes": lambda **_: {"data": {}},  # user notes live on Snapshot.notes; nothing to fetch
}


def _broadcast(snapshot_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        f"snapshot.{snapshot_id}",
        {"type": "snapshot_event", "payload": payload},
    )


def capture_for_existing(
    snap: Snapshot,
    *,
    watchlist_tickers: Iterable[str] = (),
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
) -> Snapshot:
    """Fill in sections for an already-created Snapshot. Broadcasts progress over WS.

    Runs the fetchers serially (fine at single-user scale; Celery fan-out lands in M6).
    """
    _broadcast(snap.id, {"event": "pending", "snapshot_id": snap.id, "includes": snap.includes})
    ok_count = 0

    for kind in snap.includes:
        fetcher = _FETCHERS.get(kind)
        section = SnapshotSection.objects.create(snapshot=snap, kind=kind, status="pending", payload={})
        _broadcast(snap.id, {"event": "section_started", "kind": kind})

        if fetcher is None:
            section.status = "failed"
            section.error = f"No fetcher for '{kind}'"
            section.save()
            _broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})
            continue

        try:
            result = fetcher(
                watchlist_tickers=list(watchlist_tickers),
                ohlc_ticker=ohlc_ticker,
                ohlc_timeframe=ohlc_timeframe,
                ohlc_bars=ohlc_bars,
            )
            section.payload = result["data"] or {}
            section.status = "done"
            section.save()
            ok_count += 1
            _broadcast(snap.id, {"event": "section_done", "kind": kind})
        except Exception as exc:  # noqa: BLE001
            section.status = "failed"
            section.error = f"{type(exc).__name__}: {exc}"
            section.save()
            _broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})

    snap.status = "ready" if ok_count > 0 else "failed"
    snap.save()
    _broadcast(snap.id, {"event": snap.status, "snapshot_id": snap.id})
    return snap


def capture(
    *,
    profile: TradingProfile,
    objective: str,
    includes: list[str],
    notes: str = "",
    source: str = "manual",
    watchlist_tickers: Iterable[str] = (),
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
) -> Snapshot:
    """Create a Snapshot row and immediately fill it. Used by tests + any sync path."""
    snap = Snapshot.objects.create(
        profile=profile, objective=objective, notes=notes,
        includes=includes, source=source, status="pending",
    )
    return capture_for_existing(
        snap,
        watchlist_tickers=watchlist_tickers,
        ohlc_ticker=ohlc_ticker,
        ohlc_timeframe=ohlc_timeframe,
        ohlc_bars=ohlc_bars,
    )
```

Replace `backend/apps/snapshots/tasks.py` with:

```python
"""Celery wrappers around capture."""
from __future__ import annotations

from celery import shared_task

from apps.snapshots.models import Snapshot
from apps.snapshots.services import capture_for_existing


@shared_task(name="snapshots.capture")
def capture_task(
    *,
    snapshot_id: int,
    watchlist_tickers: list[str] | None = None,
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
) -> int:
    """Fill in sections for the given Snapshot id. Returns the same id."""
    snap = Snapshot.objects.get(id=snapshot_id)
    capture_for_existing(
        snap,
        watchlist_tickers=watchlist_tickers or [],
        ohlc_ticker=ohlc_ticker,
        ohlc_timeframe=ohlc_timeframe,
        ohlc_bars=ohlc_bars,
    )
    return snap.id
```

**Note:** the earlier `test_capture.py` tests call `capture(profile=..., ...)` which still works — we kept the top-level `capture()` as a thin wrapper. The broadcast tests still pass because `capture_for_existing` calls `_broadcast` at the same points.

- [ ] **Step 14.3: Write the serializers / views / urls**

Write `backend/apps/snapshots/serializers.py`:

```python
from rest_framework import serializers

from .models import Snapshot, SnapshotSection


class SnapshotSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SnapshotSection
        fields = ["id", "kind", "status", "payload", "error"]


class SnapshotSerializer(serializers.ModelSerializer):
    sections = SnapshotSectionSerializer(many=True, read_only=True)

    class Meta:
        model = Snapshot
        fields = [
            "id", "profile_id", "objective", "notes", "status", "includes",
            "source", "captured_at", "sections",
        ]
        read_only_fields = ["captured_at", "status"]
```

Write `backend/apps/snapshots/views.py`:

```python
from rest_framework import viewsets
from rest_framework.response import Response

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.serializers import SnapshotSerializer
from apps.snapshots.tasks import capture_task


class SnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Snapshot.objects.prefetch_related("sections")
    serializer_class = SnapshotSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        try:
            profile = TradingProfile.objects.get(id=data.get("profile_id"))
        except TradingProfile.DoesNotExist:
            return Response({"code": "invalid_profile", "message": "No such profile"}, status=400)

        snap = Snapshot.objects.create(
            profile=profile,
            objective=data.get("objective", ""),
            notes=data.get("notes", ""),
            includes=data.get("includes") or profile.default_includes,
            source="manual",
            status="pending",
        )
        capture_task.delay(
            snapshot_id=snap.id,
            watchlist_tickers=data.get("watchlist_tickers") or [],
            ohlc_ticker=data.get("ohlc_ticker"),
            ohlc_timeframe=data.get("ohlc_timeframe", "1m"),
            ohlc_bars=data.get("ohlc_bars", 60),
        )
        return Response(SnapshotSerializer(snap).data, status=202)
```

Write `backend/apps/snapshots/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("snapshots", views.SnapshotViewSet, basename="snapshot")

urlpatterns = router.urls
```

Write `backend/apps/threads/serializers.py`:

```python
from rest_framework import serializers

from apps.profiles.models import TradingProfile
from .models import AIRun, Message, Thread


class AIRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIRun
        fields = [
            "id", "provider", "model", "input_tokens", "output_tokens", "cached_tokens",
            "cost_usd", "latency_ms", "status", "error",
        ]


class MessageSerializer(serializers.ModelSerializer):
    ai_run = AIRunSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "role", "content", "status", "error", "created_at", "ai_run"]


class ProfileInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingProfile
        fields = ["id", "name", "default_provider", "default_model"]


class ThreadSerializer(serializers.ModelSerializer):
    profile = ProfileInlineSerializer(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Thread
        fields = ["id", "kind", "title", "profile", "pinned_snapshot_id", "created_at", "messages"]
```

Write `backend/apps/threads/views.py`:

```python
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Message, Thread
from apps.threads.serializers import MessageSerializer, ThreadSerializer
from apps.threads.tasks import run_ai_on_message


class ThreadViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Thread.objects.select_related("profile").prefetch_related("messages__ai_run")
    serializer_class = ThreadSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        profile = None
        if pid := data.get("profile_id"):
            profile = TradingProfile.objects.filter(id=pid).first()
        snap = None
        if sid := data.get("pinned_snapshot_id"):
            snap = Snapshot.objects.filter(id=sid).first()
        t = Thread.objects.create(
            kind=data.get("kind", "consult"),
            title=data.get("title", ""),
            profile=profile,
            pinned_snapshot=snap,
        )
        return Response(ThreadSerializer(t).data, status=201)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        thread = self.get_object()
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"code": "empty", "message": "text is required"}, status=400)

        user_msg = Message.objects.create(
            thread=thread, role="user", content={"text": text}, status="done",
        )
        run_ai_on_message.delay(thread_id=thread.id, user_message_id=user_msg.id)
        return Response(MessageSerializer(user_msg).data, status=202)
```

Write `backend/apps/threads/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("threads", views.ThreadViewSet, basename="thread")

urlpatterns = router.urls
```

- [ ] **Step 14.4: Mount URLs**

Edit `backend/config/urls.py`:

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/schwab/", include("apps.secrets.urls")),
    path("api/", include("apps.profiles.urls")),
    path("api/market/", include("apps.market.urls")),
    path("api/", include("apps.snapshots.urls")),
    path("api/", include("apps.threads.urls")),
]
```

- [ ] **Step 14.5: Test + commit**

```bash
docker compose exec web pytest apps/snapshots/tests/ apps/threads/tests/test_endpoints.py -v
git add backend/apps/snapshots backend/apps/threads backend/config/urls.py
git commit -m "feat(api): snapshots + threads DRF endpoints (refactor services split)"
```

Expected: all snapshots tests + 2 thread endpoint tests pass. The refactor in 14.2 keeps `capture(...)` working so earlier tests remain green.

---

## Task 15: TradingProfile + ProviderConfig DRF endpoints (TDD)

**Files:**
- Modify: `backend/apps/profiles/serializers.py` (add TradingProfileSerializer)
- Modify: `backend/apps/profiles/views.py` (add TradingProfileViewSet)
- Modify: `backend/apps/profiles/urls.py` (register it)
- Modify: `backend/apps/secrets/views.py`, `urls.py` (add ProviderConfig endpoints)
- Create: `backend/apps/secrets/serializers.py`
- Create: `backend/apps/profiles/tests/test_profile_endpoints.py`
- Create: `backend/apps/secrets/tests/test_provider_config_endpoints.py`

- [ ] **Step 15.1: Add TradingProfile serializer + viewset**

Edit `backend/apps/profiles/serializers.py` to add:

```python
class TradingProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingProfile
        fields = [
            "id", "name", "style", "default_includes", "default_provider",
            "default_model", "active", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
```

Import `TradingProfile` at the top of the file.

Edit `backend/apps/profiles/views.py` to add:

```python
from rest_framework import viewsets

from .models import TradingProfile
from .serializers import TradingProfileSerializer


class TradingProfileViewSet(viewsets.ModelViewSet):
    queryset = TradingProfile.objects.all()
    serializer_class = TradingProfileSerializer
```

Edit `backend/apps/profiles/urls.py` to add the route:

```python
router.register("profiles", views.TradingProfileViewSet, basename="profile")
```

- [ ] **Step 15.2: Write `backend/apps/secrets/serializers.py`**

```python
from rest_framework import serializers

from .models import ProviderConfig


class ProviderConfigSerializer(serializers.ModelSerializer):
    # Never expose the raw API key in GET responses.
    api_key_present = serializers.SerializerMethodField()
    api_key_write = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ProviderConfig
        fields = [
            "provider", "base_url", "default_model", "enabled", "supports_vision",
            "daily_cost_cap_usd", "api_key_present", "api_key_write",
        ]

    def get_api_key_present(self, obj) -> bool:
        return bool(obj.api_key)

    def update(self, instance, validated_data):
        if (key := validated_data.pop("api_key_write", None)) is not None:
            instance.api_key = key
        return super().update(instance, validated_data)

    def create(self, validated_data):
        key = validated_data.pop("api_key_write", None)
        instance = super().create(validated_data)
        if key is not None:
            instance.api_key = key
            instance.save()
        return instance
```

- [ ] **Step 15.3: Add ProviderConfig views + urls**

Edit `backend/apps/secrets/views.py` — append:

```python
from rest_framework import viewsets
from rest_framework.response import Response

from apps.ai.cost import daily_spend_usd
from apps.ai.catalog import list_models
from .models import ProviderConfig
from .serializers import ProviderConfigSerializer


class ProviderConfigViewSet(viewsets.ModelViewSet):
    queryset = ProviderConfig.objects.all()
    serializer_class = ProviderConfigSerializer
    lookup_field = "provider"


def ai_models(_request):
    from django.http import JsonResponse
    from apps.ai.catalog import list_models as _list
    # Query param ?provider=claude
    provider = _request.GET.get("provider")
    models = _list(provider)
    return JsonResponse({
        "models": [
            {
                "id": m.id, "name": m.name, "provider": m.provider,
                "input_per_mtok": m.input_per_mtok, "output_per_mtok": m.output_per_mtok,
                "cached_per_mtok": m.cached_per_mtok, "context_window": m.context_window,
                "supports_vision": m.supports_vision,
            }
            for m in models
        ],
    })


def ai_usage(_request):
    from django.http import JsonResponse
    return JsonResponse({
        "today": {p: str(daily_spend_usd(p)) for p in ["claude", "openai", "local"]},
    })
```

Edit `backend/apps/secrets/urls.py`:

```python
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("providers", views.ProviderConfigViewSet, basename="provider-config")

urlpatterns = [
    path("authorize/", views.schwab_authorize, name="authorize"),
    path("callback/", views.schwab_callback, name="callback"),
    path("status/", views.schwab_status, name="status"),
    path("models/", views.ai_models, name="ai-models"),
    path("usage/", views.ai_usage, name="ai-usage"),
] + router.urls
```

Mounted under `/api/schwab/` in `config/urls.py`, so:
- `/api/schwab/providers/` list+create
- `/api/schwab/providers/claude/` update (lookup is `provider`)
- `/api/schwab/models/?provider=claude` list
- `/api/schwab/usage/` today's spend

(Yes, the path prefix is a bit awkward — the `secrets_app` urls module happens to live under `/api/schwab/` historically. We can refactor in M4.)

- [ ] **Step 15.4: Write endpoint tests**

Write `backend/apps/profiles/tests/test_profile_endpoints.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_profile_crud(api):
    resp = api.post("/api/profiles/", {
        "name": "A", "style": "x", "default_includes": ["quotes"],
    }, format="json")
    assert resp.status_code == 201
    pid = resp.json()["id"]

    assert len(api.get("/api/profiles/").json()) == 1
    api.patch(f"/api/profiles/{pid}/", {"name": "B"}, format="json")
    assert TradingProfile.objects.get(id=pid).name == "B"
```

Write `backend/apps/secrets/tests/test_provider_config_endpoints.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.secrets.models import ProviderConfig


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_provider_config_create_does_not_leak_key(api):
    resp = api.post("/api/schwab/providers/", {
        "provider": "claude", "api_key_write": "sk-ant-xxx",
        "default_model": "claude-sonnet-4-6", "daily_cost_cap_usd": "5.00",
    }, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert "api_key" not in body
    assert body["api_key_present"] is True


@pytest.mark.django_db
def test_provider_config_update_key(api):
    pc = ProviderConfig.objects.create(provider="claude")
    r = api.patch("/api/schwab/providers/claude/", {"api_key_write": "sk-ant-new"}, format="json")
    assert r.status_code == 200
    pc.refresh_from_db()
    assert pc.api_key == "sk-ant-new"


@pytest.mark.django_db
def test_ai_models_endpoint(api):
    r = api.get("/api/schwab/models/?provider=claude")
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()["models"]]
    assert "claude-sonnet-4-6" in ids
```

- [ ] **Step 15.5: Test + commit**

```bash
docker compose exec web pytest apps/profiles/tests/test_profile_endpoints.py apps/secrets/tests/test_provider_config_endpoints.py -v
git add backend/apps/profiles backend/apps/secrets
git commit -m "feat(api): profile + provider-config + model catalog endpoints"
```

Expected: 4 passed.

---

## Task 16: Frontend api modules + hooks for M3

**Files:**
- Create: `frontend/src/api/profiles.ts`
- Create: `frontend/src/api/ai.ts`
- Create: `frontend/src/api/snapshots.ts`
- Create: `frontend/src/api/threads.ts`
- Create: `frontend/src/hooks/useProfiles.ts`, `useProviderConfigs.ts`, `useCreateSnapshot.ts`, `useSnapshot.ts`, `useThread.ts`, `useCreateConsultThread.ts`, `useSendMessage.ts`, `useAiModels.ts`, `useAiUsage.ts`

- [ ] **Step 16.1: Write `frontend/src/api/profiles.ts`**

```ts
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type TradingProfile = {
  id: number;
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
  active: boolean;
};

export const fetchProfiles = () => apiGet<TradingProfile[]>("/api/profiles/");
export const fetchProfile = (id: number) => apiGet<TradingProfile>(`/api/profiles/${id}/`);
export const createProfile = (body: Partial<TradingProfile>) =>
  apiPost<TradingProfile>("/api/profiles/", body);
export const updateProfile = (id: number, body: Partial<TradingProfile>) =>
  apiPatch<TradingProfile>(`/api/profiles/${id}/`, body);
export const deleteProfile = (id: number) => apiDelete(`/api/profiles/${id}/`);
```

- [ ] **Step 16.2: Write `frontend/src/api/ai.ts`**

```ts
import { apiGet, apiPatch, apiPost } from "./client";

export type AiModel = {
  id: string; name: string; provider: string;
  input_per_mtok: number; output_per_mtok: number; cached_per_mtok: number;
  context_window: number; supports_vision: boolean;
};

export type ProviderConfig = {
  provider: "claude" | "openai" | "local";
  base_url: string;
  default_model: string;
  enabled: boolean;
  supports_vision: boolean;
  daily_cost_cap_usd: string;
  api_key_present: boolean;
};

export const fetchAiModels = (provider?: string) =>
  apiGet<{ models: AiModel[] }>(`/api/schwab/models/${provider ? `?provider=${provider}` : ""}`);

export const fetchProviderConfigs = () =>
  apiGet<ProviderConfig[]>("/api/schwab/providers/");

export const upsertProviderConfig = (provider: string, body: Partial<ProviderConfig> & { api_key_write?: string }) => {
  // Try PATCH first; if 404, POST.
  return apiPatch<ProviderConfig>(`/api/schwab/providers/${provider}/`, body).catch(async (err) => {
    if ((err as { status?: number }).status === 404) {
      return apiPost<ProviderConfig>("/api/schwab/providers/", { provider, ...body });
    }
    throw err;
  });
};

export const fetchAiUsage = () => apiGet<{ today: Record<string, string> }>("/api/schwab/usage/");
```

- [ ] **Step 16.3: Write `frontend/src/api/snapshots.ts`**

```ts
import { apiGet, apiPost } from "./client";

export type SnapshotSection = {
  id: number; kind: string; status: "pending" | "done" | "failed";
  payload: unknown; error: string;
};

export type Snapshot = {
  id: number; profile_id: number; objective: string; notes: string;
  status: "pending" | "ready" | "failed";
  includes: string[]; source: string; captured_at: string;
  sections: SnapshotSection[];
};

export type CreateSnapshotBody = {
  profile_id: number;
  objective?: string;
  notes?: string;
  includes?: string[];
  watchlist_tickers?: string[];
  ohlc_ticker?: string;
  ohlc_timeframe?: string;
  ohlc_bars?: number;
};

export const createSnapshot = (body: CreateSnapshotBody) =>
  apiPost<Snapshot>("/api/snapshots/", body);

export const fetchSnapshot = (id: number) => apiGet<Snapshot>(`/api/snapshots/${id}/`);
```

- [ ] **Step 16.4: Write `frontend/src/api/threads.ts`**

```ts
import { apiGet, apiPost } from "./client";

export type AiRun = {
  id: number; provider: string; model: string;
  input_tokens: number; output_tokens: number; cached_tokens: number;
  cost_usd: string; latency_ms: number;
  status: "pending" | "streaming" | "done" | "failed" | "cost_capped";
  error: string;
};

export type Message = {
  id: number;
  role: "user" | "assistant" | "system";
  content: { text?: string };
  status: "done" | "streaming" | "failed";
  error: string;
  created_at: string;
  ai_run?: AiRun | null;
};

export type Thread = {
  id: number; kind: "consult" | "chat" | "observer"; title: string;
  profile: { id: number; name: string; default_provider: string; default_model: string } | null;
  pinned_snapshot_id: number | null;
  created_at: string;
  messages: Message[];
};

export const fetchThreads = () => apiGet<Thread[]>("/api/threads/");
export const fetchThread = (id: number) => apiGet<Thread>(`/api/threads/${id}/`);

export const createThread = (body: {
  kind: "consult" | "chat"; profile_id?: number; pinned_snapshot_id?: number; title?: string;
}) => apiPost<Thread>("/api/threads/", body);

export const sendMessage = (threadId: number, text: string) =>
  apiPost<Message>(`/api/threads/${threadId}/send/`, { text });
```

- [ ] **Step 16.5: Write the hooks**

Write `frontend/src/hooks/useProfiles.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  TradingProfile, createProfile, deleteProfile, fetchProfiles, updateProfile,
} from "@/api/profiles";

export const useProfiles = () =>
  useQuery({ queryKey: ["profiles"], queryFn: fetchProfiles });

export function useCreateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<TradingProfile>) => createProfile(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<TradingProfile> }) => updateProfile(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteProfile(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}
```

Write `frontend/src/hooks/useProviderConfigs.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchProviderConfigs, upsertProviderConfig } from "@/api/ai";

export const useProviderConfigs = () =>
  useQuery({ queryKey: ["provider-configs"], queryFn: fetchProviderConfigs });

export function useUpsertProviderConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, body }: { provider: string; body: Parameters<typeof upsertProviderConfig>[1] }) =>
      upsertProviderConfig(provider, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["provider-configs"] }),
  });
}
```

Write `frontend/src/hooks/useAiModels.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchAiModels } from "@/api/ai";

export const useAiModels = (provider?: string) =>
  useQuery({ queryKey: ["ai-models", provider ?? "all"], queryFn: () => fetchAiModels(provider) });
```

Write `frontend/src/hooks/useAiUsage.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchAiUsage } from "@/api/ai";

export const useAiUsage = () =>
  useQuery({ queryKey: ["ai-usage"], queryFn: fetchAiUsage, refetchInterval: 30_000 });
```

Write `frontend/src/hooks/useSnapshot.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchSnapshot } from "@/api/snapshots";

export const useSnapshot = (id: number | null) =>
  useQuery({
    queryKey: ["snapshot", id],
    queryFn: () => fetchSnapshot(id!),
    enabled: id !== null,
  });
```

Write `frontend/src/hooks/useCreateSnapshot.ts`:

```ts
import { useMutation } from "@tanstack/react-query";
import { CreateSnapshotBody, createSnapshot } from "@/api/snapshots";

export function useCreateSnapshot() {
  return useMutation({
    mutationFn: (body: CreateSnapshotBody) => createSnapshot(body),
  });
}
```

Write `frontend/src/hooks/useThread.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchThread, fetchThreads, sendMessage } from "@/api/threads";

export const useThreads = () => useQuery({ queryKey: ["threads"], queryFn: fetchThreads });

export const useThread = (id: number | null) =>
  useQuery({
    queryKey: ["thread", id],
    queryFn: () => fetchThread(id!),
    enabled: id !== null,
  });

export function useSendMessage(threadId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => sendMessage(threadId, text),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["thread", threadId] }),
  });
}
```

Write `frontend/src/hooks/useCreateConsultThread.ts`:

```ts
import { useMutation } from "@tanstack/react-query";
import { createThread } from "@/api/threads";

export function useCreateConsultThread() {
  return useMutation({
    mutationFn: (body: { profile_id?: number; pinned_snapshot_id?: number; title?: string }) =>
      createThread({ kind: "consult", ...body }),
  });
}
```

- [ ] **Step 16.6: Test + commit**

No new vitest tests; existing suite must still pass.

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/api/profiles.ts frontend/src/api/ai.ts frontend/src/api/snapshots.ts \
        frontend/src/api/threads.ts frontend/src/hooks
git commit -m "feat(frontend): api + hooks for profiles, provider-configs, snapshots, threads"
```

Expected: existing 7 tests pass.

---

## Task 17: WebSocket infrastructure (TDD)

**Files:**
- Create: `frontend/src/realtime/WebSocketProvider.tsx`
- Create: `frontend/src/realtime/subscriptions.ts`
- Create: `frontend/src/hooks/useChannel.ts`
- Modify: `frontend/src/main.tsx`
- Create: `frontend/src/__tests__/subscriptions.test.ts`

- [ ] **Step 17.1: Write failing test**

Write `frontend/src/__tests__/subscriptions.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { Broker } from "../realtime/subscriptions";

describe("Broker", () => {
  it("fans out messages to subscribers of the same channel", () => {
    const b = new Broker();
    const handler = vi.fn();
    const unsub = b.subscribe("thread.1", handler);

    b.dispatch("thread.1", { event: "text_delta", text: "hi" });
    expect(handler).toHaveBeenCalledWith({ event: "text_delta", text: "hi" });

    unsub();
    b.dispatch("thread.1", { event: "x" });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not leak messages across channels", () => {
    const b = new Broker();
    const a = vi.fn();
    const z = vi.fn();
    b.subscribe("thread.1", a);
    b.subscribe("thread.2", z);

    b.dispatch("thread.1", { event: "one" });
    expect(a).toHaveBeenCalledTimes(1);
    expect(z).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 17.2: Write `frontend/src/realtime/subscriptions.ts`**

```ts
type Handler = (msg: any) => void;

export class Broker {
  private subs = new Map<string, Set<Handler>>();

  subscribe(channel: string, h: Handler): () => void {
    let set = this.subs.get(channel);
    if (!set) {
      set = new Set();
      this.subs.set(channel, set);
    }
    set.add(h);
    return () => {
      const s = this.subs.get(channel);
      s?.delete(h);
      if (s && s.size === 0) this.subs.delete(channel);
    };
  }

  dispatch(channel: string, msg: any): void {
    this.subs.get(channel)?.forEach((h) => {
      try { h(msg); } catch { /* swallow handler errors */ }
    });
  }

  channels(): string[] {
    return Array.from(this.subs.keys());
  }
}
```

- [ ] **Step 17.3: Write `frontend/src/realtime/WebSocketProvider.tsx`**

```tsx
import { createContext, useContext, useEffect, useMemo, useRef } from "react";
import { Broker } from "./subscriptions";

type Ctx = {
  subscribe: (channel: string, handler: (msg: any) => void) => () => void;
};

const WebSocketContext = createContext<Ctx | null>(null);

// For M3, we open one WS per channel on-demand. A single multiplexed socket can
// come later; the Broker API doesn't care which approach we use.
export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const broker = useMemo(() => new Broker(), []);
  const sockets = useRef(new Map<string, WebSocket>());

  const wsBase = import.meta.env.VITE_WS_BASE_URL ?? "";

  const openForChannel = (channel: string): WebSocket => {
    const existing = sockets.current.get(channel);
    if (existing) return existing;

    const path = channel.startsWith("thread.")
      ? `/ws/threads/${channel.slice("thread.".length)}/`
      : channel.startsWith("snapshot.")
      ? `/ws/snapshots/${channel.slice("snapshot.".length)}/`
      : null;
    if (!path) throw new Error(`Unknown channel: ${channel}`);

    const ws = new WebSocket(`${wsBase}${path}`);
    ws.addEventListener("message", (ev) => {
      try {
        broker.dispatch(channel, JSON.parse(ev.data));
      } catch { /* ignore malformed */ }
    });
    sockets.current.set(channel, ws);
    return ws;
  };

  const maybeClose = (channel: string) => {
    const subs = broker.channels().includes(channel);
    if (!subs) {
      sockets.current.get(channel)?.close();
      sockets.current.delete(channel);
    }
  };

  const ctx: Ctx = useMemo(() => ({
    subscribe: (channel, handler) => {
      openForChannel(channel);
      const unsubBroker = broker.subscribe(channel, handler);
      return () => {
        unsubBroker();
        maybeClose(channel);
      };
    },
  }), []);

  useEffect(() => {
    return () => {
      sockets.current.forEach((ws) => ws.close());
      sockets.current.clear();
    };
  }, []);

  return <WebSocketContext.Provider value={ctx}>{children}</WebSocketContext.Provider>;
}

export function useWebSocket(): Ctx {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWebSocket must be used inside WebSocketProvider");
  return ctx;
}
```

- [ ] **Step 17.4: Write `frontend/src/hooks/useChannel.ts`**

```ts
import { useEffect } from "react";
import { useWebSocket } from "@/realtime/WebSocketProvider";

export function useChannel(channel: string | null, handler: (msg: any) => void): void {
  const ws = useWebSocket();
  useEffect(() => {
    if (!channel) return;
    const unsub = ws.subscribe(channel, handler);
    return unsub;
  }, [channel, handler, ws]);
}
```

- [ ] **Step 17.5: Wrap `main.tsx` in the provider**

Edit `frontend/src/main.tsx`:

```tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { queryClient } from "./hooks/queryClient";
import { WebSocketProvider } from "./realtime/WebSocketProvider";
import "./styles/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>
        <App />
      </WebSocketProvider>
    </QueryClientProvider>
  </StrictMode>,
);
```

- [ ] **Step 17.6: Test + commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/realtime frontend/src/hooks/useChannel.ts frontend/src/main.tsx frontend/src/__tests__/subscriptions.test.ts
git commit -m "feat(frontend): WebSocket broker + provider + useChannel hook"
```

Expected: existing 7 + 2 new subscription tests pass.

---

## Task 18: Profiles CRUD page

**Files:**
- Create: `frontend/src/components/ProfileForm.tsx`
- Modify: `frontend/src/pages/ProfilesPage.tsx` (new)
- Modify: `frontend/src/router.tsx` (add /profiles route)

- [ ] **Step 18.1: Create `frontend/src/pages/ProfilesPage.tsx`**

```tsx
import { useState } from "react";
import type { TradingProfile } from "@/api/profiles";
import {
  useCreateProfile, useDeleteProfile, useProfiles, useUpdateProfile,
} from "@/hooks/useProfiles";

const SECTION_OPTIONS = ["quotes", "ohlc", "positions", "breadth", "notes"] as const;

type Draft = {
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
};

const BLANK_DRAFT: Draft = {
  name: "", style: "", default_includes: ["quotes", "positions", "breadth"],
  default_provider: "claude", default_model: "claude-sonnet-4-6",
};

export default function ProfilesPage() {
  const { data } = useProfiles();
  const create = useCreateProfile();
  const update = useUpdateProfile();
  const del = useDeleteProfile();
  const [editing, setEditing] = useState<TradingProfile | null>(null);
  const [draft, setDraft] = useState<Draft>(BLANK_DRAFT);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editing) {
      update.mutate({ id: editing.id, body: draft }, { onSuccess: () => { setEditing(null); setDraft(BLANK_DRAFT); } });
    } else {
      create.mutate(draft, { onSuccess: () => setDraft(BLANK_DRAFT) });
    }
  };

  const toggleSection = (sec: string) => {
    setDraft((d) => ({
      ...d,
      default_includes: d.default_includes.includes(sec)
        ? d.default_includes.filter((s) => s !== sec)
        : [...d.default_includes, sec],
    }));
  };

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">Trading profiles</h1>

      <form onSubmit={submit} className="space-y-3 p-4 border border-slate-800 rounded">
        <input
          value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          placeholder="Profile name" required
          className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        <textarea
          value={draft.style} onChange={(e) => setDraft({ ...draft, style: e.target.value })}
          placeholder="Trading style (used as system prompt)" rows={5}
          className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        <div>
          <div className="text-xs text-slate-500 mb-1">Default sections</div>
          <div className="flex flex-wrap gap-2">
            {SECTION_OPTIONS.map((sec) => (
              <label key={sec} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox" checked={draft.default_includes.includes(sec)}
                  onChange={() => toggleSection(sec)}
                />
                {sec}
              </label>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <input
            value={draft.default_model}
            onChange={(e) => setDraft({ ...draft, default_model: e.target.value })}
            placeholder="claude-sonnet-4-6"
            className="flex-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
          />
          <select
            value={draft.default_provider}
            onChange={(e) => setDraft({ ...draft, default_provider: e.target.value })}
            className="px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
          >
            <option value="claude">Claude</option>
            <option value="openai">OpenAI</option>
            <option value="local">Local</option>
          </select>
        </div>
        <div className="flex gap-2">
          <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">
            {editing ? "Save" : "Create"}
          </button>
          {editing && (
            <button type="button" onClick={() => { setEditing(null); setDraft(BLANK_DRAFT); }}
                    className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600">Cancel</button>
          )}
        </div>
      </form>

      <ul className="space-y-2">
        {(data ?? []).map((p) => (
          <li key={p.id} className="p-3 border border-slate-800 rounded">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-slate-400">{p.default_model} · {p.default_includes.join(", ")}</div>
              </div>
              <div className="flex gap-2 text-sm">
                <button onClick={() => { setEditing(p); setDraft({
                  name: p.name, style: p.style, default_includes: p.default_includes,
                  default_provider: p.default_provider, default_model: p.default_model,
                }); }} className="text-slate-300 hover:underline">Edit</button>
                <button onClick={() => del.mutate(p.id)} className="text-rose-400 hover:underline">Delete</button>
              </div>
            </div>
            <div className="text-xs text-slate-500 mt-2 whitespace-pre-line">{p.style}</div>
          </li>
        ))}
      </ul>
    </main>
  );
}
```

- [ ] **Step 18.2: Add route**

Edit `frontend/src/router.tsx`:

```tsx
import ProfilesPage from "./pages/ProfilesPage";
// ...
  { path: "/profiles", element: <ProfilesPage /> },
```

- [ ] **Step 18.3: Commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/pages/ProfilesPage.tsx frontend/src/router.tsx
git commit -m "feat(frontend): /profiles CRUD page"
```

---

## Task 19: Provider-config card on /settings

**Files:**
- Create: `frontend/src/components/ProviderConfigCard.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 19.1: Component**

Write `frontend/src/components/ProviderConfigCard.tsx`:

```tsx
import { useState } from "react";
import { useProviderConfigs, useUpsertProviderConfig } from "@/hooks/useProviderConfigs";
import { useAiUsage } from "@/hooks/useAiUsage";

const PROVIDERS = ["claude", "openai", "local"] as const;
type Provider = typeof PROVIDERS[number];

const DEFAULT_MODEL: Record<Provider, string> = {
  claude: "claude-sonnet-4-6",
  openai: "gpt-5",
  local: "",
};

export default function ProviderConfigCard() {
  const { data: configs } = useProviderConfigs();
  const { data: usage } = useAiUsage();
  const upsert = useUpsertProviderConfig();
  const [drafts, setDrafts] = useState<Record<string, { api_key_write?: string; default_model?: string; daily_cost_cap_usd?: string; base_url?: string }>>({});

  return (
    <div className="p-4 rounded border border-slate-800 space-y-4">
      <h2 className="text-lg font-medium">AI providers</h2>
      {PROVIDERS.map((p) => {
        const cfg = configs?.find((c) => c.provider === p);
        const draft = drafts[p] ?? {};
        const spent = usage?.today[p] ?? "0";
        return (
          <div key={p} className="border-t border-slate-800 pt-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-medium capitalize">{p}</span>
                <span className="ml-2 text-xs text-slate-500">
                  {cfg?.api_key_present ? "key: ●●●●" : "no key"}
                </span>
              </div>
              <div className="text-xs text-slate-400">today: ${Number(spent).toFixed(4)}</div>
            </div>
            <form
              className="mt-2 grid grid-cols-2 gap-2 text-sm"
              onSubmit={(e) => {
                e.preventDefault();
                upsert.mutate({ provider: p, body: {
                  api_key_write: draft.api_key_write ?? "",
                  default_model: draft.default_model ?? cfg?.default_model ?? DEFAULT_MODEL[p],
                  daily_cost_cap_usd: draft.daily_cost_cap_usd ?? cfg?.daily_cost_cap_usd ?? "10.00",
                  base_url: draft.base_url ?? cfg?.base_url ?? "",
                } }, { onSuccess: () => setDrafts((d) => ({ ...d, [p]: {} })) });
              }}
            >
              <input
                placeholder="API key (leave blank to keep)"
                type="password"
                value={draft.api_key_write ?? ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [p]: { ...draft, api_key_write: e.target.value } }))}
                className="col-span-2 px-2 py-1 rounded bg-slate-900 border border-slate-700"
              />
              <input
                placeholder={`Default model (${DEFAULT_MODEL[p]})`}
                value={draft.default_model ?? cfg?.default_model ?? ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [p]: { ...draft, default_model: e.target.value } }))}
                className="px-2 py-1 rounded bg-slate-900 border border-slate-700"
              />
              <input
                placeholder="Daily cap USD"
                value={draft.daily_cost_cap_usd ?? cfg?.daily_cost_cap_usd ?? "10.00"}
                onChange={(e) => setDrafts((d) => ({ ...d, [p]: { ...draft, daily_cost_cap_usd: e.target.value } }))}
                className="px-2 py-1 rounded bg-slate-900 border border-slate-700"
              />
              {p === "local" && (
                <input
                  placeholder="Base URL (e.g. http://host.docker.internal:11434/v1)"
                  value={draft.base_url ?? cfg?.base_url ?? ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [p]: { ...draft, base_url: e.target.value } }))}
                  className="col-span-2 px-2 py-1 rounded bg-slate-900 border border-slate-700"
                />
              )}
              <button className="col-span-2 px-3 py-1 rounded bg-slate-700 hover:bg-slate-600">
                Save
              </button>
            </form>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 19.2: Wire into Settings page**

Edit `frontend/src/pages/Settings.tsx`:

```tsx
import ProviderConfigCard from "@/components/ProviderConfigCard";
import SchwabConnectionCard from "@/components/SchwabConnectionCard";

export default function Settings() {
  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <SchwabConnectionCard />
      <ProviderConfigCard />
    </main>
  );
}
```

- [ ] **Step 19.3: Commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/components/ProviderConfigCard.tsx frontend/src/pages/Settings.tsx
git commit -m "feat(frontend): provider-config card on /settings"
```

---

## Task 20: Snapshot composer page (`/snapshot`)

**Files:**
- Create: `frontend/src/pages/SnapshotComposerPage.tsx`
- Create: `frontend/src/components/SnapshotSectionPicker.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 20.1: Component**

Write `frontend/src/components/SnapshotSectionPicker.tsx`:

```tsx
const SECTIONS = [
  { key: "quotes", label: "Quotes" },
  { key: "ohlc", label: "OHLC bars" },
  { key: "positions", label: "Positions" },
  { key: "breadth", label: "Market context" },
  { key: "notes", label: "My notes" },
];

type Props = { value: string[]; onChange: (next: string[]) => void };

export default function SnapshotSectionPicker({ value, onChange }: Props) {
  const toggle = (k: string) =>
    onChange(value.includes(k) ? value.filter((v) => v !== k) : [...value, k]);
  return (
    <div className="flex flex-wrap gap-2">
      {SECTIONS.map((s) => (
        <label key={s.key} className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={value.includes(s.key)} onChange={() => toggle(s.key)} />
          {s.label}
        </label>
      ))}
    </div>
  );
}
```

- [ ] **Step 20.2: Page**

Write `frontend/src/pages/SnapshotComposerPage.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import SnapshotSectionPicker from "@/components/SnapshotSectionPicker";
import { useProfiles } from "@/hooks/useProfiles";
import { useCreateSnapshot } from "@/hooks/useCreateSnapshot";
import { useCreateConsultThread } from "@/hooks/useCreateConsultThread";
import { useWatchlists } from "@/hooks/useWatchlists";

export default function SnapshotComposerPage() {
  const navigate = useNavigate();
  const { data: profiles } = useProfiles();
  const { data: watchlists } = useWatchlists();
  const createSnap = useCreateSnapshot();
  const createThread = useCreateConsultThread();

  const [profileId, setProfileId] = useState<number | null>(null);
  const [watchlistId, setWatchlistId] = useState<number | null>(null);
  const [includes, setIncludes] = useState<string[]>(["quotes", "positions", "breadth"]);
  const [objective, setObjective] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (profileId === null && profiles?.[0]) {
      setProfileId(profiles[0].id);
      setIncludes(profiles[0].default_includes);
    }
  }, [profiles, profileId]);
  useEffect(() => {
    if (watchlistId === null && watchlists?.[0]) setWatchlistId(watchlists[0].id);
  }, [watchlists, watchlistId]);

  const selectedWatchlist = useMemo(
    () => watchlists?.find((w) => w.id === watchlistId), [watchlists, watchlistId],
  );
  const tickers = useMemo(
    () => selectedWatchlist?.symbols.map((s) => s.ticker) ?? [],
    [selectedWatchlist],
  );

  const onCapture = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profileId) return;
    const snap = await createSnap.mutateAsync({
      profile_id: profileId,
      objective, notes, includes,
      watchlist_tickers: tickers,
      ohlc_ticker: tickers[0],
      ohlc_timeframe: "1m",
      ohlc_bars: 60,
    });
    const thread = await createThread.mutateAsync({
      profile_id: profileId, pinned_snapshot_id: snap.id,
      title: objective.slice(0, 80) || `Consult ${new Date().toLocaleString()}`,
    });
    navigate(`/threads/${thread.id}?snapshot=${snap.id}`);
  };

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">New snapshot</h1>

      <form onSubmit={onCapture} className="space-y-4">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Profile</label>
          <select
            value={profileId ?? ""} onChange={(e) => setProfileId(parseInt(e.target.value, 10) || null)}
            className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
          >
            <option value="" disabled>Select profile…</option>
            {(profiles ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">Watchlist (provides tickers for quotes + OHLC)</label>
          <select
            value={watchlistId ?? ""} onChange={(e) => setWatchlistId(parseInt(e.target.value, 10) || null)}
            className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
          >
            <option value="" disabled>Select watchlist…</option>
            {(watchlists ?? []).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
          <div className="text-xs text-slate-500 mt-1">{tickers.join(", ") || "(no symbols)"}</div>
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">Sections</label>
          <SnapshotSectionPicker value={includes} onChange={setIncludes} />
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">Objective</label>
          <textarea
            rows={3} value={objective} onChange={(e) => setObjective(e.target.value)}
            placeholder="What do you want the AI to consider right now?"
            className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
          />
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">Notes (optional)</label>
          <textarea
            rows={2} value={notes} onChange={(e) => setNotes(e.target.value)}
            className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
          />
        </div>

        <button
          disabled={!profileId || createSnap.isPending || createThread.isPending}
          className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40"
        >
          {createSnap.isPending ? "Capturing…" : "Capture + ask"}
        </button>
      </form>
    </main>
  );
}
```

- [ ] **Step 20.3: Add route + link from Dashboard**

Edit `frontend/src/router.tsx`:

```tsx
import SnapshotComposerPage from "./pages/SnapshotComposerPage";
// ...
  { path: "/snapshot", element: <SnapshotComposerPage /> },
```

Edit `frontend/src/pages/Dashboard.tsx` to add a prominent "Snapshot now" button in the header:

```tsx
        <nav className="text-sm space-x-4">
          <Link className="text-slate-300 hover:underline" to="/profiles">Profiles</Link>
          <Link className="text-slate-300 hover:underline" to="/watchlists">Watchlists</Link>
          <Link className="text-slate-300 hover:underline" to="/settings">Settings</Link>
          <Link className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white" to="/snapshot">
            + Snapshot
          </Link>
        </nav>
```

- [ ] **Step 20.4: Commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/components/SnapshotSectionPicker.tsx frontend/src/pages/SnapshotComposerPage.tsx \
        frontend/src/router.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): /snapshot composer page + Dashboard CTA"
```

---

## Task 21: Thread detail page with streaming render

**Files:**
- Create: `frontend/src/components/StreamingMessage.tsx`
- Create: `frontend/src/pages/ThreadDetailPage.tsx`
- Modify: `frontend/src/pages/MarketTicker.tsx` — (unchanged, included for grep only)
- Modify: `frontend/src/router.tsx`

- [ ] **Step 21.1: Component**

Write `frontend/src/components/StreamingMessage.tsx`:

```tsx
import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  role: "user" | "assistant" | "system";
  text: string;
  status?: "done" | "streaming" | "failed";
  error?: string;
  cost?: string;
  model?: string;
};

function Message({ role, text, status, error, cost, model }: Props) {
  const isAssistant = role === "assistant";
  return (
    <div className={`p-4 rounded border ${
      isAssistant ? "border-emerald-900/50 bg-emerald-950/20" : "border-slate-800"
    }`}>
      <div className="flex justify-between text-xs text-slate-500 mb-2">
        <span>{role}{model ? ` · ${model}` : ""}</span>
        {cost && <span>${Number(cost).toFixed(4)}</span>}
      </div>
      {status === "failed" ? (
        <p className="text-rose-400">Error: {error || "unknown"}</p>
      ) : (
        <div className="prose prose-invert prose-sm max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text || (status === "streaming" ? "…" : "")}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export default memo(Message);
```

- [ ] **Step 21.2: Page**

Write `frontend/src/pages/ThreadDetailPage.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import StreamingMessage from "@/components/StreamingMessage";
import { useChannel } from "@/hooks/useChannel";
import { useSendMessage, useThread } from "@/hooks/useThread";
import { useSnapshot } from "@/hooks/useSnapshot";

type LiveMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  status: "done" | "streaming" | "failed";
  error?: string;
  cost?: string;
  model?: string;
};

export default function ThreadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [search] = useSearchParams();
  const tid = id ? parseInt(id, 10) : null;
  const snapshotId = search.get("snapshot") ? parseInt(search.get("snapshot")!, 10) : null;

  const { data: thread, refetch } = useThread(tid);
  const { data: snap } = useSnapshot(snapshotId);

  // Live buffer — keyed by message id. Seeded from thread.messages, updated by WS.
  const [live, setLive] = useState<Record<number, LiveMessage>>({});
  useEffect(() => {
    if (!thread) return;
    const seed: Record<number, LiveMessage> = {};
    for (const m of thread.messages) {
      seed[m.id] = {
        id: m.id,
        role: m.role === "system" ? "assistant" : m.role,
        text: m.content?.text ?? "",
        status: m.status,
        error: m.error,
        cost: m.ai_run?.cost_usd,
        model: m.ai_run?.model,
      };
    }
    setLive(seed);
  }, [thread]);

  const onWs = useCallback((msg: any) => {
    if (msg.event === "message_started") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: { id: msg.message_id, role: "assistant", text: "", status: "streaming" },
      }));
    } else if (msg.event === "text_delta") {
      setLive((prev) => {
        const cur = prev[msg.message_id] ?? { id: msg.message_id, role: "assistant", text: "", status: "streaming" };
        return { ...prev, [msg.message_id]: { ...cur, text: cur.text + msg.text } };
      });
    } else if (msg.event === "message_done") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: { ...prev[msg.message_id], status: "done", cost: msg.cost_usd },
      }));
      refetch();
    } else if (msg.event === "error" || msg.event === "cost_capped") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: { ...prev[msg.message_id], status: "failed", error: msg.error },
      }));
    }
  }, [refetch]);

  useChannel(tid ? `thread.${tid}` : null, onWs);

  const send = useSendMessage(tid ?? 0);
  const [input, setInput] = useState("");

  const ordered = useMemo(
    () => Object.values(live).sort((a, b) => a.id - b.id),
    [live],
  );

  if (!thread) return <main className="p-6">Loading…</main>;

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold">{thread.title || `Thread #${thread.id}`}</h1>
        <Link to="/" className="text-sm text-slate-300 hover:underline">← Dashboard</Link>
      </div>

      {snap && (
        <details className="p-3 rounded border border-slate-800">
          <summary className="cursor-pointer text-sm text-slate-300">
            Snapshot #{snap.id} · {snap.status} · {snap.includes.join(", ")}
          </summary>
          <pre className="mt-2 text-xs text-slate-400 overflow-x-auto">{JSON.stringify(snap.sections.map((s) => ({ kind: s.kind, status: s.status, error: s.error })), null, 2)}</pre>
        </details>
      )}

      <section className="space-y-3">
        {ordered.map((m) => (
          <StreamingMessage key={m.id}
            role={m.role} text={m.text} status={m.status}
            error={m.error} cost={m.cost} model={m.model}
          />
        ))}
      </section>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!input.trim()) return;
          send.mutate(input.trim(), { onSuccess: () => setInput("") });
        }}
      >
        <input
          value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={thread.kind === "consult" ? "Follow-up…" : "Message"}
          className="flex-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">Send</button>
      </form>
    </main>
  );
}
```

- [ ] **Step 21.3: Add route**

Edit `frontend/src/router.tsx`:

```tsx
import ThreadDetailPage from "./pages/ThreadDetailPage";
// ...
  { path: "/threads/:id", element: <ThreadDetailPage /> },
```

- [ ] **Step 21.4: Commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/components/StreamingMessage.tsx frontend/src/pages/ThreadDetailPage.tsx frontend/src/router.tsx
git commit -m "feat(frontend): thread detail with streaming markdown render"
```

---

## Task 22: Threads list page

**Files:**
- Create: `frontend/src/pages/ThreadsPage.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 22.1: Page**

Write `frontend/src/pages/ThreadsPage.tsx`:

```tsx
import { Link } from "react-router-dom";
import { useThreads } from "@/hooks/useThread";
import { formatDistanceToNow } from "date-fns";

export default function ThreadsPage() {
  const { data, isLoading } = useThreads();

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Threads</h1>
        <Link to="/snapshot" className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-sm">+ Snapshot</Link>
      </div>
      {isLoading ? <p>Loading…</p> : (
        <ul className="space-y-1">
          {(data ?? []).map((t) => (
            <li key={t.id} className="p-3 rounded border border-slate-800 flex justify-between">
              <Link to={`/threads/${t.id}`} className="hover:underline">
                <div className="font-medium">{t.title || `Thread #${t.id}`}</div>
                <div className="text-xs text-slate-500">{t.kind} · {t.profile?.name ?? "no profile"} · {formatDistanceToNow(new Date(t.created_at))} ago</div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 22.2: Add route + nav link**

Edit `frontend/src/router.tsx`:

```tsx
import ThreadsPage from "./pages/ThreadsPage";
// ...
  { path: "/threads", element: <ThreadsPage /> },
```

Edit `frontend/src/pages/Dashboard.tsx` — add to nav:

```tsx
          <Link className="text-slate-300 hover:underline" to="/threads">Threads</Link>
```

- [ ] **Step 22.3: Commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src/pages/ThreadsPage.tsx frontend/src/router.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): /threads list page"
```

---

## Task 23: Full test suite + lint pass

- [ ] **Step 23.1: Run full backend suite**

```bash
docker compose exec web pytest -v
```

Expected: all M1 + M2 + M3 tests pass. Counts roughly: M1 = 7, M2 = 50, M3 adds ~25, so ~80 total.

- [ ] **Step 23.2: Run full frontend suite**

```bash
docker compose exec frontend npm test -- --run
```

Expected: all previous tests + subscription tests pass (9 total).

- [ ] **Step 23.3: Lint**

```bash
make lint
```

Fix any errors with `chore: M3 lint fixes` if needed. Common expected issues:
- Unused imports in new serializers/views.
- Mypy complaints about `Any` returns from the serializer `_fmt` helpers (narrow with explicit casts).
- ESLint `@typescript-eslint/no-explicit-any` in the broker (suppress with `// eslint-disable-next-line` since it's intentional for the message-bus contract).

- [ ] **Step 23.4: Commit fixes if any**

```bash
git add -u
git commit -m "chore: M3 lint fixes" || echo "nothing"
```

---

## Task 24: End-to-end smoke (mocked AI path)

- [ ] **Step 24.1: Integration smoke via curl — real Postgres + Redis, fake AI key**

Run the critical path against the live stack. The AI call will fail because we're
using a fake key; that's expected and exercises the error-propagation path.

```bash
cd /home/dan/ai-dashboard

# 1. Create provider config with a test key
curl -s -X POST http://localhost:8000/api/schwab/providers/ \
  -H "Content-Type: application/json" \
  -d '{"provider":"claude","api_key_write":"sk-ant-test","default_model":"claude-sonnet-4-6","daily_cost_cap_usd":"5.00"}'

# 2. Create profile
curl -s -X POST http://localhost:8000/api/profiles/ \
  -H "Content-Type: application/json" \
  -d '{"name":"smoke","style":"test profile","default_includes":["notes"],"default_model":"claude-sonnet-4-6"}'

# 3. Create snapshot (notes-only so Schwab isn't needed)
curl -s -X POST http://localhost:8000/api/snapshots/ \
  -H "Content-Type: application/json" \
  -d '{"profile_id":1,"objective":"smoke","includes":["notes"],"watchlist_tickers":[]}'

# Wait for celery to process
sleep 3
curl -s http://localhost:8000/api/snapshots/1/ | head -c 500
```

Expected: the snapshot returns `status: "ready"` with a `notes` section in `done` state (payload={} — notes live on Snapshot.notes).

The Claude API call in the AI run task will fail at this point because `sk-ant-test` isn't a real key — that's OK for the smoke. The frontend error path ("Anthropic …") is visible in the Thread UI.

- [ ] **Step 24.2: UI smoke — render every page**

Open each page in a browser or curl:
- `http://localhost:5173/` — Dashboard
- `http://localhost:5173/profiles`
- `http://localhost:5173/snapshot`
- `http://localhost:5173/threads`
- `http://localhost:5173/settings`

All should render without console errors.

- [ ] **Step 24.3: Optional — real Claude smoke**

If the user has a real `ANTHROPIC_API_KEY`, they can paste it into the provider config and trigger a consult manually through the UI. Outside of that, ship without.

- [ ] **Step 24.4: Commit any final fixes**

```bash
git add -u
git commit -m "chore: M3 E2E smoke passing" || echo "nothing"
```

---

## Task 25: Cold rebuild + tag m3

- [ ] **Step 25.1: Fresh rebuild**

```bash
cd /home/dan/ai-dashboard
docker compose down -v
docker compose build --no-cache
docker compose up -d
sleep 40
curl -s http://localhost:8000/api/health/
curl -s http://localhost:8000/api/ready/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/
docker compose exec web pytest -q
docker compose exec frontend npm test -- --run 2>&1 | tail -10
```

Expected: all green from cold start.

- [ ] **Step 25.2: Tag**

```bash
git tag -a m3-snapshots-ai -m "M3: Capture pipeline + Claude streaming + one-shot consult mode"
git log --oneline -30
git tag -l
```

## Done

Next up: **M4 — Full threads** (ongoing-chat thread mode with multi-turn history, OpenAI + LocalProvider implementations, cost tracking + caps polish).
