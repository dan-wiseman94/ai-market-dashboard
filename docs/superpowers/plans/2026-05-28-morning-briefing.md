# Morning Briefing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily hybrid briefing — deterministic data sections (open theses status, upcoming events, overnight trigger firings, overnight news, a fresh market snapshot) + a best-effort AI synthesis — on a `/briefing` page + notification, in a new `apps.briefing` app.

**Architecture:** New `apps.briefing` app. `BriefingConfig` (singleton) + `BriefingRun` (own model like `PostMortem`). `assemble()` gathers deterministic sections; `run_briefing()` stores them, captures a fresh snapshot, and posts a synthetic user `Message` into a dedicated `kind="briefing"` thread routed through the existing `run_ai_on_message` pipeline for the best-effort AI synthesis. A `briefing.run_scheduled` beat task fires once/day via a unique `scheduled_date` claim.

**Tech Stack:** Django 5 + DRF, Celery beat, Postgres; React 18 + TS, TanStack Query.

**Spec:** `docs/superpowers/specs/2026-05-28-morning-briefing-design.md`

**Dependency:** This branch (`feat/morning-briefing`) is stacked on `feat/market-events` (PR #20) — `assemble()` imports `upcoming_events` from the events feature. Do not rebase onto bare `origin/main`.

---

## Conventions for this plan

- The dev stack must be up (`make dev`). Tests run in containers.
- **Backend test** (WORKDIR `/app/backend`, drop the `backend/` prefix): `docker compose exec -T web pytest apps/briefing/tests/test_x.py -v`
- **Frontend test/check:** `docker compose exec -T frontend pnpm exec vitest run src/__tests__/<path>` · `... pnpm exec tsc --noEmit` · `... pnpm run lint`
- **Migrations:** `docker compose exec -T web python manage.py makemigrations <app>` then `... migrate <app>`
- TDD: failing test → run fail → implement → run pass → commit.
- **GUARDRAIL:** Do NOT run `git pull`/`git fetch`/`git merge`/`git rebase`/`git checkout <branch>`. Stay on `feat/morning-briefing`. Only `git add <specific files>` + `git commit`. NEVER `git add -A`; NEVER stage `e2e/visual/__screenshots__/`.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`. If the pre-commit hook errors on container paths, prefix `LEFTHOOK=0`.
- Worker/beat don't hot-reload — after Task 5, `docker compose restart worker beat`.
- `ty` is advisory/non-gating — ignore its diagnostics.

## File structure

**Create (new app `apps.briefing`):** `__init__.py`, `apps.py`, `models.py`, `urls.py`, `views.py`, `serializers.py`, `tasks.py`, `services/__init__.py`, `services/assemble.py`, `services/run.py`, `migrations/__init__.py`, `tests/__init__.py` + test modules.
**Create (frontend):** `frontend/src/api/briefing.ts`, `frontend/src/hooks/useBriefing.ts`, `frontend/src/pages/BriefingPage.tsx`, tests.
**Modify:** `config/settings/base.py` (INSTALLED_APPS), `config/urls.py` (include), `config/celery.py` (autodiscover + beat), `apps/threads/models.py` (Thread kind), `apps/observer/models.py` (Notification kind), `frontend/src/router.tsx`, `frontend/src/components/layout/SideNav.tsx`, `frontend/src/components/layout/AppLayout.tsx`, `frontend/src/hooks/useKeyboardShortcuts.ts`, `CLAUDE.md`.

---

### Task 1: Scaffold `apps.briefing` + models + migration

**Files:** Create `backend/apps/briefing/{__init__.py,apps.py,models.py,urls.py,views.py,migrations/__init__.py,tests/__init__.py}`; Create `backend/apps/briefing/tests/test_models.py`; Modify `backend/config/settings/base.py`, `backend/config/urls.py`.

- [ ] **Step 1: Write the failing test** — create `backend/apps/briefing/tests/test_models.py`:

```python
from datetime import date

import pytest
from django.db import IntegrityError

from apps.briefing.models import BriefingConfig, BriefingRun


@pytest.mark.django_db
def test_briefing_config_is_singleton():
    a = BriefingConfig.load()
    b = BriefingConfig.load()
    assert a.pk == b.pk == 1
    assert a.enabled is True


@pytest.mark.django_db
def test_scheduled_date_unique_claim():
    BriefingRun.objects.create(scheduled_date=date(2026, 5, 28), status="ready")
    with pytest.raises(IntegrityError):
        BriefingRun.objects.create(scheduled_date=date(2026, 5, 28), status="assembling")


@pytest.mark.django_db
def test_manual_runs_have_null_scheduled_date_and_are_unlimited():
    BriefingRun.objects.create(scheduled_date=None, status="ready")
    BriefingRun.objects.create(scheduled_date=None, status="ready")  # no constraint
    assert BriefingRun.objects.filter(scheduled_date__isnull=True).count() == 2
```

- [ ] **Step 2: Run to verify it fails**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_models.py -v`
Expected: collection/import error (`apps.briefing` doesn't exist).

- [ ] **Step 3: Scaffold the app + models**

`backend/apps/briefing/__init__.py`: empty. `backend/apps/briefing/migrations/__init__.py`: empty. `backend/apps/briefing/tests/__init__.py`: empty.

`backend/apps/briefing/apps.py`:
```python
from django.apps import AppConfig


class BriefingConfigApp(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.briefing"
    label = "briefing"
```

`backend/apps/briefing/models.py`:
```python
"""Morning Briefing domain — singleton config + per-run record."""

from __future__ import annotations

from datetime import time
from typing import ClassVar

from django.db import models


class BriefingConfig(models.Model):
    """Singleton config for the daily briefing. Use BriefingConfig.load()."""

    enabled = models.BooleanField(default=True)
    send_at_local = models.TimeField(default=time(8, 30))
    profile = models.ForeignKey(
        "profiles.TradingProfile", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    news_lookback_hours = models.PositiveIntegerField(default=14)
    events_within_days = models.PositiveIntegerField(default=7)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls) -> "BriefingConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return f"BriefingConfig(enabled={self.enabled}, send_at={self.send_at_local})"


class BriefingRun(models.Model):
    STATUS: ClassVar = [("assembling", "Assembling"), ("ready", "Ready"), ("failed", "Failed")]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS, default="assembling")
    data = models.JSONField(default=dict)
    snapshot = models.ForeignKey(
        "snapshots.Snapshot", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    synthesis_message = models.ForeignKey(
        "threads.Message", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    # Set ONLY on scheduled runs -> unique once-per-day claim. NULL for manual run-now.
    scheduled_date = models.DateField(null=True, blank=True, unique=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"BriefingRun(#{self.pk} {self.status})"
```

`backend/apps/briefing/views.py`: `# views added in Task 6` (empty module for now, or a single `from __future__ import annotations`). `backend/apps/briefing/urls.py`:
```python
from django.urls import path

app_name = "briefing"

urlpatterns: list = []  # populated in Tasks 6-7
```

In `backend/config/settings/base.py`, add `"apps.briefing",` to `INSTALLED_APPS` after `"apps.thesis",`.

In `backend/config/urls.py`, add this line **after** `path("api/files/", include("apps.files.urls")),` and **before** the generic `path("api/", include("apps.profiles.urls")),` (specific prefix before generic — URL-ordering convention):
```python
    path("api/briefings/", include("apps.briefing.urls")),
```

- [ ] **Step 4: Migrate + run tests**
```bash
docker compose exec -T web python manage.py makemigrations briefing
docker compose exec -T web python manage.py migrate briefing
docker compose exec -T web pytest apps/briefing/tests/test_models.py -v
```
Expected: `0001_initial.py` created; 3 tests pass.

- [ ] **Step 5: Commit**
```bash
git add backend/apps/briefing/ backend/config/settings/base.py backend/config/urls.py
LEFTHOOK=0 git commit -m "feat(briefing): scaffold apps.briefing + BriefingConfig/BriefingRun models

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add `briefing` kind to Thread + Notification

**Files:** Modify `backend/apps/threads/models.py` (Thread.KIND_CHOICES), `backend/apps/observer/models.py` (Notification.KIND_CHOICES); Create `backend/apps/briefing/tests/test_kinds.py`.

- [ ] **Step 1: Write the failing test** — create `backend/apps/briefing/tests/test_kinds.py`:

```python
from apps.observer.models import Notification
from apps.threads.models import Thread


def test_thread_supports_briefing_kind():
    assert "briefing" in dict(Thread.KIND_CHOICES)


def test_notification_supports_briefing_kind():
    assert "briefing" in dict(Notification.KIND_CHOICES)
```

- [ ] **Step 2: Run to verify it fails**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_kinds.py -v`
Expected: both FAIL (`briefing` not in choices).

- [ ] **Step 3: Add the choices**
In `backend/apps/threads/models.py`, add to `Thread.KIND_CHOICES` (after the `("observer", ...)` entry):
```python
        ("briefing", "Morning briefing"),
```
In `backend/apps/observer/models.py`, add to `Notification.KIND_CHOICES` (after the `("postmortem", ...)` entry):
```python
        ("briefing", "Briefing"),
```

- [ ] **Step 4: Migrate (choices-only) + run tests**
```bash
docker compose exec -T web python manage.py makemigrations threads observer
docker compose exec -T web python manage.py migrate
docker compose exec -T web pytest apps/briefing/tests/test_kinds.py -v
```
Expected: two small `alter_field` migrations created (choices metadata); tests pass. Also run `docker compose exec -T web pytest apps/threads apps/observer -q` to confirm no regression.

- [ ] **Step 5: Commit**
```bash
git add backend/apps/threads/models.py backend/apps/observer/models.py \
        backend/apps/threads/migrations/ backend/apps/observer/migrations/ \
        backend/apps/briefing/tests/test_kinds.py
LEFTHOOK=0 git commit -m "feat(briefing): add 'briefing' kind to Thread + Notification

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `assemble()` — deterministic data sections

**Files:** Create `backend/apps/briefing/services/__init__.py` (empty), `backend/apps/briefing/services/assemble.py`, `backend/apps/briefing/tests/test_assemble.py`.

- [ ] **Step 1: Write the failing tests** — create `backend/apps/briefing/tests/test_assemble.py`:

```python
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.briefing.models import BriefingConfig, BriefingRun
from apps.briefing.services import assemble as A
from apps.thesis.models import Thesis


def test_pct_move():
    assert A._pct_move(100, 110) == 10.0
    assert A._pct_move(100, 90) == -10.0
    assert A._pct_move(None, 110) is None
    assert A._pct_move(0, 110) is None


@pytest.mark.django_db
def test_theses_section_computes_distances():
    Thesis.objects.create(title="t", ticker="NVDA", direction="bullish",
                          target_price=Decimal("110"), invalidation_price=Decimal("90"),
                          status="open")
    with patch("apps.briefing.services.assemble.fetch_quotes",
               return_value={"NVDA": {"last": 100.0}}):
        rows = A._theses_section()
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["current"] == 100.0
    assert rows[0]["pct_to_target"] == 10.0
    assert rows[0]["pct_to_invalidation"] == -10.0


@pytest.mark.django_db
def test_since_uses_prior_ready_run_else_24h():
    # no prior run -> ~24h ago
    s1 = A._since()
    assert s1 < timezone.now() - timedelta(hours=23)
    prev = BriefingRun.objects.create(status="ready")
    assert A._since() == prev.created_at


@pytest.mark.django_db
def test_assemble_combines_sections_and_captures_snapshot():
    cfg = BriefingConfig.load()
    fake_snap = type("S", (), {"sections": None})  # replaced by the patch return
    with (
        patch("apps.briefing.services.assemble._theses_section", return_value=[{"ticker": "NVDA"}]),
        patch("apps.briefing.services.assemble.upcoming_events",
              return_value={"earnings": [], "macro": [{"kind": "cpi"}]}),
        patch("apps.briefing.services.assemble._triggers_section", return_value=[]),
        patch("apps.briefing.services.assemble._news_section", return_value=[]),
        patch("apps.briefing.services.assemble._capture_market", return_value=(None, {"vix_last": 18.2})),
    ):
        data, snap = A.assemble(cfg)
    assert data["theses"] == [{"ticker": "NVDA"}]
    assert data["events"]["macro"][0]["kind"] == "cpi"
    assert data["market"]["vix_last"] == 18.2
    assert "since" in data
```

- [ ] **Step 2: Run to verify it fails**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_assemble.py -v`
Expected: import error (`assemble` module missing).

- [ ] **Step 3: Implement** — create `backend/apps/briefing/services/__init__.py` (empty) and `backend/apps/briefing/services/assemble.py`:

```python
"""Gather the deterministic briefing sections. Defensive: a failing section degrades to empty."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.utils import timezone

from apps.market.services.events import upcoming_events
from apps.market.services.news import fetch_news
from apps.market.services.quotes import fetch_quotes
from apps.profiles.models import TradingProfile, WatchlistSymbol
from apps.snapshots.services import capture
from apps.thesis.models import Thesis
from apps.triggers.models import TriggerFiring
from apps.triggers.services.describe import describe

log = logging.getLogger(__name__)


def _watchlist_union() -> list[str]:
    return list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())


def _pct_move(current, level) -> float | None:
    if current is None or level is None:
        return None
    c = float(current)
    if c == 0:
        return None
    return round((float(level) - c) / c * 100, 2)


def _theses_section() -> list[dict]:
    theses = list(Thesis.objects.filter(status="open"))
    if not theses:
        return []
    tickers = sorted({t.ticker for t in theses})
    try:
        quotes = fetch_quotes(tickers)
    except Exception as exc:
        log.warning("briefing.theses.quotes_failed: %s", exc)
        quotes = {}
    out: list[dict] = []
    for t in theses:
        current = (quotes.get(t.ticker) or {}).get("last")
        out.append({
            "id": t.id, "ticker": t.ticker, "direction": t.direction, "conviction": t.conviction,
            "entry": float(t.entry_price) if t.entry_price is not None else None,
            "target": float(t.target_price) if t.target_price is not None else None,
            "invalidation": float(t.invalidation_price) if t.invalidation_price is not None else None,
            "current": float(current) if current is not None else None,
            "pct_to_target": _pct_move(current, t.target_price),
            "pct_to_invalidation": _pct_move(current, t.invalidation_price),
        })
    return out


def _since() -> datetime:
    from apps.briefing.models import BriefingRun

    prev = BriefingRun.objects.filter(status="ready").order_by("-created_at").first()
    return prev.created_at if prev else timezone.now() - timedelta(hours=24)


def _triggers_section(since: datetime) -> list[dict]:
    rows = (TriggerFiring.objects.filter(fired_at__gte=since)
            .select_related("trigger").order_by("-fired_at"))
    out: list[dict] = []
    for f in rows:
        name = getattr(f.trigger, "name", None) or str(f.trigger)
        out.append({"trigger_id": f.trigger_id, "name": name,
                    "fired_at": f.fired_at.isoformat(), "summary": describe(f.matched_values)})
    return out


def _news_section(tickers: list[str], lookback_hours: int) -> list[dict]:
    try:
        items = fetch_news(tickers, lookback_hours=lookback_hours)
    except Exception as exc:
        log.warning("briefing.news_failed: %s", exc)
        return []
    return [{"headline": it.get("headline"), "source": it.get("source"), "url": it.get("url"),
             "published_at": it.get("datetime"), "ticker": it.get("related", "")}
            for it in items[:15]]


def _capture_market(profile, tickers: list[str]):
    """Capture a breadth-only snapshot; return (snapshot, market_dict). Defensive."""
    if profile is None:
        return None, {}
    try:
        snap = capture(profile=profile, objective="Morning briefing market context",
                       includes=["breadth"], source="briefing", watchlist_tickers=tickers)
    except Exception as exc:
        log.warning("briefing.market_capture_failed: %s", exc)
        return None, {}
    sec = snap.sections.filter(kind="breadth", status="done").first()
    return snap, (sec.payload if sec else {})


def _safe(fn, default):
    try:
        return fn()
    except Exception as exc:
        log.warning("briefing.section_failed: %s", exc)
        return default


def assemble(config) -> tuple[dict, object | None]:
    tickers = _watchlist_union()
    since = _since()
    profile = config.profile or TradingProfile.objects.first()
    snapshot, market = _capture_market(profile, tickers)
    data = {
        "theses": _safe(_theses_section, []),
        "events": _safe(lambda: upcoming_events(tickers, within_days=config.events_within_days),
                        {"earnings": [], "macro": []}),
        "triggers": _safe(lambda: _triggers_section(since), []),
        "news": _safe(lambda: _news_section(tickers, config.news_lookback_hours), []),
        "market": market,
        "since": since.isoformat(),
    }
    return data, snapshot
```

> Note: the `_capture_market` test patches it directly; the `assemble` test patches the section helpers. If `Thesis.target_price`/`invalidation_price` are `Decimal`, `_pct_move` casts via `float()`. Verify `TriggerFiring.trigger` has a `.name` attr — the `getattr(..., str(...))` fallback is defensive if not.

- [ ] **Step 4: Run to verify pass**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_assemble.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**
```bash
git add backend/apps/briefing/services/__init__.py backend/apps/briefing/services/assemble.py \
        backend/apps/briefing/tests/test_assemble.py
LEFTHOOK=0 git commit -m "feat(briefing): assemble() deterministic data sections

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `run_briefing()` — orchestration + AI synthesis

**Files:** Create `backend/apps/briefing/services/run.py`, `backend/apps/briefing/tests/test_run.py`.

- [ ] **Step 1: Write the failing tests** — create `backend/apps/briefing/tests/test_run.py`:

```python
from datetime import date
from unittest.mock import patch

import pytest

from apps.briefing.models import BriefingConfig, BriefingRun
from apps.briefing.services import run as R
from apps.profiles.models import TradingProfile


@pytest.fixture
def cfg(db):
    c = BriefingConfig.load()
    c.profile = TradingProfile.objects.create(name="B", style="brief")
    c.save()
    return c


def _patches():
    return (
        patch("apps.briefing.services.run.assemble", return_value=({"theses": [], "events": {},
              "triggers": [], "news": [], "market": {}, "since": "x"}, None)),
        patch("apps.briefing.services.run.run_ai_on_message") as _,  # placeholder; see below
    )


@pytest.mark.django_db
def test_render_briefing_markdown_mentions_sections():
    md = R.render_briefing_markdown({"theses": [{"ticker": "NVDA", "direction": "bullish",
        "current": 100, "pct_to_target": 10, "pct_to_invalidation": -10, "conviction": 4}],
        "events": {"earnings": [{"ticker": "NVDA", "days_until": 2}], "macro": []},
        "triggers": [], "news": [], "market": {"vix_last": 18}, "since": "x"})
    assert "NVDA" in md and "Upcoming" in md


@pytest.mark.django_db
def test_run_briefing_manual_creates_run_and_dispatches_ai(cfg):
    with (
        patch("apps.briefing.services.run.assemble",
              return_value=({"theses": [], "since": "x"}, None)),
        patch("apps.briefing.services.run.run_ai_on_message.delay") as delay,
        patch("apps.briefing.services.run.notify") as notify,
    ):
        run = R.run_briefing(scheduled=False)
    assert run.status == "ready"
    assert run.scheduled_date is None
    assert run.synthesis_message is not None
    delay.assert_called_once()
    notify.assert_called_once()
    assert notify.call_args.kwargs["kind"] == "briefing"


@pytest.mark.django_db
def test_run_briefing_scheduled_is_idempotent_per_day(cfg):
    with (
        patch("apps.briefing.services.run.assemble", return_value=({"since": "x"}, None)),
        patch("apps.briefing.services.run.run_ai_on_message.delay"),
        patch("apps.briefing.services.run.notify"),
        patch("apps.briefing.services.run._local_today", return_value=date(2026, 5, 28)),
    ):
        first = R.run_briefing(scheduled=True)
        second = R.run_briefing(scheduled=True)
    assert first is not None and first.scheduled_date == date(2026, 5, 28)
    assert second is None  # claim already taken
    assert BriefingRun.objects.filter(scheduled_date=date(2026, 5, 28)).count() == 1
```

- [ ] **Step 2: Run to verify it fails**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_run.py -v`
Expected: import error (`run` module missing).

- [ ] **Step 3: Implement** — create `backend/apps/briefing/services/run.py`:

```python
"""Orchestrate one briefing: assemble data, persist, post the AI synthesis, notify."""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from apps.briefing.models import BriefingConfig, BriefingRun
from apps.briefing.services.assemble import assemble
from apps.observer.services.notifications import notify
from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message

log = logging.getLogger(__name__)


def _now_local() -> datetime:
    tz = ZoneInfo(getattr(settings, "OBSERVER_BEAT_TIMEZONE", "UTC"))
    return timezone.now().astimezone(tz)


def _local_today() -> date:
    return _now_local().date()


def get_or_create_briefing_thread(profile: TradingProfile) -> Thread:
    obj, _ = Thread.objects.get_or_create(
        profile=profile, kind="briefing", defaults={"title": "Morning briefing"}
    )
    return obj


def _fmt(v, suffix="") -> str:
    return "—" if v is None else f"{v}{suffix}"


def render_briefing_markdown(data: dict) -> str:
    lines = [
        "You are writing a concise morning market briefing. Synthesize what matters most "
        "today in 3-6 sentences; lead with the single most actionable item. Do not restate "
        "every row — interpret. Here is today's data:\n",
    ]
    theses = data.get("theses") or []
    if theses:
        lines.append("## Open theses")
        for t in theses:
            lines.append(
                f"- {t.get('ticker')} {t.get('direction')} (conv {t.get('conviction')}): "
                f"now {_fmt(t.get('current'))}, →target {_fmt(t.get('pct_to_target'), '%')}, "
                f"→invalidation {_fmt(t.get('pct_to_invalidation'), '%')}"
            )
    events = data.get("events") or {}
    earn, macro = events.get("earnings") or [], events.get("macro") or []
    if earn or macro:
        lines.append("## Upcoming events")
        for e in earn:
            lines.append(f"- {e.get('ticker')} earnings in {e.get('days_until')}d")
        for m in macro:
            lines.append(f"- {m.get('title') or m.get('kind')} in {m.get('days_until')}d")
    trig = data.get("triggers") or []
    if trig:
        lines.append("## Triggers fired overnight")
        lines += [f"- {t.get('name')}: {t.get('summary')}" for t in trig]
    news = data.get("news") or []
    if news:
        lines.append("## Overnight news")
        lines += [f"- {n.get('headline')} ({n.get('source')})" for n in news[:10]]
    market = data.get("market") or {}
    if market:
        lines.append(
            f"## Market: SPX {_fmt(market.get('spx_last'))}, QQQ {_fmt(market.get('qqq_last'))}, "
            f"VIX {_fmt(market.get('vix_last'))}"
        )
    return "\n".join(lines)


def _one_line_summary(data: dict) -> str:
    n_theses = len(data.get("theses") or [])
    n_trig = len(data.get("triggers") or [])
    return f"{n_theses} open theses · {n_trig} triggers fired overnight"


def run_briefing(*, scheduled: bool) -> BriefingRun | None:
    cfg = BriefingConfig.load()
    if scheduled:
        try:
            run = BriefingRun.objects.create(scheduled_date=_local_today(), status="assembling")
        except IntegrityError:
            return None  # already claimed today
    else:
        run = BriefingRun.objects.create(scheduled_date=None, status="assembling")

    try:
        data, snapshot = assemble(cfg)
    except Exception as exc:
        log.exception("briefing.assemble_failed")
        run.status, run.error = "failed", str(exc)
        run.save(update_fields=["status", "error"])
        return run

    run.data, run.snapshot, run.status = data, snapshot, "ready"
    run.save()

    profile = cfg.profile or TradingProfile.objects.first()
    if profile is not None:
        thread = get_or_create_briefing_thread(profile)
        msg = Message.objects.create(
            thread=thread, role="user", content={"text": render_briefing_markdown(data)},
            snapshot_ref=snapshot, status="done",
        )
        run.synthesis_message = msg
        run.save(update_fields=["synthesis_message"])
        run_ai_on_message.delay(thread_id=thread.id, user_message_id=msg.id)

    notify(user_id=None, kind="briefing", title="Your morning briefing is ready",
           body=_one_line_summary(data), link="/briefing")
    return run
```

- [ ] **Step 4: Run to verify pass**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_run.py -v`
Expected: all pass. (The idempotency test relies on the unique `scheduled_date`; the manual test asserts dispatch + notify.)

- [ ] **Step 5: Commit**
```bash
git add backend/apps/briefing/services/run.py backend/apps/briefing/tests/test_run.py
LEFTHOOK=0 git commit -m "feat(briefing): run_briefing orchestration + AI synthesis dispatch

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `briefing.run_scheduled` beat task

**Files:** Create `backend/apps/briefing/tasks.py`, `backend/apps/briefing/tests/test_tasks.py`; Modify `backend/config/celery.py`.

- [ ] **Step 1: Write the failing tests** — create `backend/apps/briefing/tests/test_tasks.py`:

```python
from datetime import datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from apps.briefing.models import BriefingConfig
from apps.briefing.tasks import run_scheduled

UTC = ZoneInfo("UTC")


@pytest.mark.django_db
def test_skips_when_disabled():
    cfg = BriefingConfig.load()
    cfg.enabled = False
    cfg.save()
    assert run_scheduled() == {"skipped": "disabled"}


@pytest.mark.django_db
def test_skips_before_send_at():
    cfg = BriefingConfig.load()
    cfg.send_at_local = time(8, 30)
    cfg.save()
    with patch("apps.briefing.tasks._now_local",
               return_value=datetime(2026, 5, 28, 7, 0, tzinfo=UTC)):
        assert run_scheduled() == {"skipped": "before_send_at"}


@pytest.mark.django_db
def test_fires_when_due():
    cfg = BriefingConfig.load()
    cfg.send_at_local = time(8, 30)
    cfg.save()
    with (
        patch("apps.briefing.tasks._now_local",
              return_value=datetime(2026, 5, 28, 9, 0, tzinfo=UTC)),
        patch("apps.briefing.tasks.run_briefing", return_value=type("R", (), {"id": 7})()) as rb,
    ):
        assert run_scheduled() == {"ran": 7}
        rb.assert_called_once_with(scheduled=True)
```

- [ ] **Step 2: Run to verify it fails**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_tasks.py -v`
Expected: import error (`tasks` missing).

- [ ] **Step 3: Implement** — create `backend/apps/briefing/tasks.py`:

```python
"""Beat task: fire the daily briefing once when due."""

from __future__ import annotations

from celery import shared_task

from apps.briefing.models import BriefingConfig
from apps.briefing.services.run import _now_local, run_briefing


@shared_task(name="briefing.run_scheduled")
def run_scheduled() -> dict:
    cfg = BriefingConfig.load()
    if not cfg.enabled:
        return {"skipped": "disabled"}
    if _now_local().time() < cfg.send_at_local:
        return {"skipped": "before_send_at"}
    run = run_briefing(scheduled=True)  # idempotent claim handles already-ran-today
    return {"ran": run.id if run else None}
```

In `backend/config/celery.py`: add `"apps.briefing"` to the `autodiscover_tasks([...])` list, and add to `app.conf.beat_schedule`:
```python
    "briefing-run-scheduled": {
        "task": "briefing.run_scheduled",
        "schedule": crontab(minute="*/15"),
    },
```

- [ ] **Step 4: Run tests + restart workers**
```bash
docker compose exec -T web pytest apps/briefing/tests/test_tasks.py -v
docker compose restart worker beat
```
Expected: 3 tests pass; workers restarted so the schedule registers.

- [ ] **Step 5: Commit**
```bash
git add backend/apps/briefing/tasks.py backend/config/celery.py \
        backend/apps/briefing/tests/test_tasks.py
LEFTHOOK=0 git commit -m "feat(briefing): briefing.run_scheduled beat task (15-min cadence)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Config API (`GET|PATCH /api/briefings/config/`)

**Files:** Create `backend/apps/briefing/serializers.py`; Modify `backend/apps/briefing/views.py`, `backend/apps/briefing/urls.py`; Create `backend/apps/briefing/tests/test_config_endpoint.py`.

- [ ] **Step 1: Write the failing test** — create `backend/apps/briefing/tests/test_config_endpoint.py`:

```python
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_get_config_returns_singleton(api):
    r = api.get("/api/briefings/config/")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert "send_at_local" in r.json()


@pytest.mark.django_db
def test_patch_config_updates(api):
    r = api.patch("/api/briefings/config/", {"enabled": False, "events_within_days": 14},
                  format="json")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["events_within_days"] == 14
```

- [ ] **Step 2: Run to verify it fails**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_config_endpoint.py -v`
Expected: 404.

- [ ] **Step 3: Implement**

`backend/apps/briefing/serializers.py`:
```python
from rest_framework import serializers

from apps.briefing.models import BriefingConfig


class BriefingConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = BriefingConfig
        fields = ["enabled", "send_at_local", "profile", "news_lookback_hours",
                  "events_within_days", "updated_at"]
        read_only_fields = ["updated_at"]
```

`backend/apps/briefing/views.py`:
```python
from __future__ import annotations

from rest_framework import generics

from apps.briefing.models import BriefingConfig
from apps.briefing.serializers import BriefingConfigSerializer


class BriefingConfigView(generics.RetrieveUpdateAPIView):
    serializer_class = BriefingConfigSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self) -> BriefingConfig:
        return BriefingConfig.load()
```

`backend/apps/briefing/urls.py`:
```python
from django.urls import path

from apps.briefing import views

app_name = "briefing"

urlpatterns = [
    path("config/", views.BriefingConfigView.as_view(), name="config"),
]
```

- [ ] **Step 4: Run to verify pass**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_config_endpoint.py -v`
Expected: 2 pass.

- [ ] **Step 5: Commit**
```bash
git add backend/apps/briefing/serializers.py backend/apps/briefing/views.py \
        backend/apps/briefing/urls.py backend/apps/briefing/tests/test_config_endpoint.py
LEFTHOOK=0 git commit -m "feat(briefing): config API (GET|PATCH /api/briefings/config/)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Briefings list/latest/run API

**Files:** Modify `backend/apps/briefing/serializers.py`, `backend/apps/briefing/views.py`, `backend/apps/briefing/urls.py`; Create `backend/apps/briefing/tests/test_runs_endpoint.py`.

- [ ] **Step 1: Write the failing test** — create `backend/apps/briefing/tests/test_runs_endpoint.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.briefing.models import BriefingRun


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_latest_returns_most_recent(api):
    BriefingRun.objects.create(status="ready", data={"theses": []})
    newer = BriefingRun.objects.create(status="ready", data={"theses": [{"ticker": "NVDA"}]})
    r = api.get("/api/briefings/latest/")
    assert r.status_code == 200
    assert r.json()["id"] == newer.id
    assert r.json()["data"]["theses"][0]["ticker"] == "NVDA"


@pytest.mark.django_db
def test_latest_empty_returns_204(api):
    r = api.get("/api/briefings/latest/")
    assert r.status_code == 204


@pytest.mark.django_db
def test_run_now_creates_run(api):
    with pytest.MonkeyPatch.context() as mp:
        from apps.briefing import views
        mp.setattr(views, "run_briefing",
                   lambda *, scheduled: BriefingRun.objects.create(status="ready", data={}))
        r = api.post("/api/briefings/run/")
    assert r.status_code == 201
    assert BriefingRun.objects.count() == 1
```

- [ ] **Step 2: Run to verify it fails**
Run: `docker compose exec -T web pytest apps/briefing/tests/test_runs_endpoint.py -v`
Expected: 404s.

- [ ] **Step 3: Implement**

Append to `backend/apps/briefing/serializers.py`:
```python
from apps.briefing.models import BriefingRun


class BriefingRunSerializer(serializers.ModelSerializer):
    synthesis_text = serializers.SerializerMethodField()
    synthesis_status = serializers.SerializerMethodField()

    class Meta:
        model = BriefingRun
        fields = ["id", "created_at", "status", "data", "snapshot", "scheduled_date",
                  "synthesis_text", "synthesis_status"]

    def get_synthesis_text(self, obj) -> str:
        m = obj.synthesis_message
        return (m.content or {}).get("text", "") if m else ""

    def get_synthesis_status(self, obj) -> str:
        return obj.synthesis_message.status if obj.synthesis_message else ""
```

Append to `backend/apps/briefing/views.py`:
```python
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.briefing.models import BriefingRun
from apps.briefing.serializers import BriefingRunSerializer
from apps.briefing.services.run import run_briefing


class BriefingListView(generics.ListAPIView):
    serializer_class = BriefingRunSerializer
    queryset = BriefingRun.objects.all()[:30]


class BriefingLatestView(APIView):
    def get(self, request):
        run = BriefingRun.objects.order_by("-created_at").first()
        if run is None:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)
        return Response(BriefingRunSerializer(run).data)


class BriefingRunNowView(APIView):
    def post(self, request):
        run = run_briefing(scheduled=False)
        return Response(BriefingRunSerializer(run).data, status=drf_status.HTTP_201_CREATED)
```

Update `backend/apps/briefing/urls.py` urlpatterns:
```python
urlpatterns = [
    path("", views.BriefingListView.as_view(), name="list"),
    path("latest/", views.BriefingLatestView.as_view(), name="latest"),
    path("run/", views.BriefingRunNowView.as_view(), name="run"),
    path("config/", views.BriefingConfigView.as_view(), name="config"),
]
```

- [ ] **Step 4: Run tests + regression**
```bash
docker compose exec -T web pytest apps/briefing -v
```
Expected: the whole briefing suite passes.

- [ ] **Step 5: Commit**
```bash
git add backend/apps/briefing/serializers.py backend/apps/briefing/views.py \
        backend/apps/briefing/urls.py backend/apps/briefing/tests/test_runs_endpoint.py
LEFTHOOK=0 git commit -m "feat(briefing): list/latest/run-now API

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Frontend client + hooks

**Files:** Create `frontend/src/api/briefing.ts`, `frontend/src/hooks/useBriefing.ts`, `frontend/src/__tests__/hooks/useBriefing.test.tsx`.

- [ ] **Step 1: Write the failing test** — create `frontend/src/__tests__/hooks/useBriefing.test.tsx`:

```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "@/api/briefing";
import { useLatestBriefing } from "@/hooks/useBriefing";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useLatestBriefing", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("fetches the latest briefing", async () => {
    vi.spyOn(api, "fetchLatestBriefing").mockResolvedValue({
      id: 1, status: "ready", created_at: "2026-05-28T12:00:00Z", scheduled_date: null,
      data: { theses: [], events: { earnings: [], macro: [] }, triggers: [], news: [], market: {}, since: "x" },
      synthesis_text: "Lead with NVDA.", synthesis_status: "done", snapshot: null,
    });
    const { result } = renderHook(() => useLatestBriefing(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.synthesis_text).toBe("Lead with NVDA.");
  });
});
```

- [ ] **Step 2: Run to verify it fails**
Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/hooks/useBriefing.test.tsx`
Expected: FAIL (exports missing).

- [ ] **Step 3: Implement**

`frontend/src/api/briefing.ts`:
```ts
import { apiGet, apiPost, apiPatch } from "./client";

export type BriefingThesis = {
  id: number; ticker: string; direction: string; conviction: number;
  entry: number | null; target: number | null; invalidation: number | null;
  current: number | null; pct_to_target: number | null; pct_to_invalidation: number | null;
};
export type BriefingData = {
  theses: BriefingThesis[];
  events: { earnings: Array<Record<string, unknown>>; macro: Array<Record<string, unknown>> };
  triggers: Array<{ trigger_id: number; name: string; fired_at: string; summary: string }>;
  news: Array<{ headline: string; source: string; url: string; published_at: number; ticker: string }>;
  market: Record<string, unknown>;
  since: string;
};
export type Briefing = {
  id: number; created_at: string; status: string; scheduled_date: string | null;
  data: BriefingData; snapshot: number | null;
  synthesis_text: string; synthesis_status: string;
};
export type BriefingConfig = {
  enabled: boolean; send_at_local: string; profile: number | null;
  news_lookback_hours: number; events_within_days: number; updated_at: string;
};

export const fetchLatestBriefing = () => apiGet<Briefing | null>("/api/briefings/latest/");
export const runBriefingNow = () => apiPost<Briefing>("/api/briefings/run/", {});
export const fetchBriefingConfig = () => apiGet<BriefingConfig>("/api/briefings/config/");
export const patchBriefingConfig = (body: Partial<BriefingConfig>) =>
  apiPatch<BriefingConfig>("/api/briefings/config/", body);
```

> Verify `apiPatch` is exported by `./client` (it's used elsewhere — e.g. config/settings). If the helper is named differently, match it. `fetchLatestBriefing` may receive a 204 (null body) when there's no briefing yet — ensure `apiGet` tolerates an empty body (the page treats falsy as "no briefing").

`frontend/src/hooks/useBriefing.ts`:
```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchBriefingConfig, fetchLatestBriefing, patchBriefingConfig, runBriefingNow,
  type BriefingConfig,
} from "@/api/briefing";

export const useLatestBriefing = () =>
  useQuery({ queryKey: ["briefing-latest"], queryFn: fetchLatestBriefing, refetchInterval: 60_000 });

export const useRunBriefing = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: runBriefingNow,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["briefing-latest"] }),
  });
};

export const useBriefingConfig = () => {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["briefing-config"], queryFn: fetchBriefingConfig });
  const update = useMutation({
    mutationFn: (b: Partial<BriefingConfig>) => patchBriefingConfig(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["briefing-config"] }),
  });
  return { ...query, update };
};
```

- [ ] **Step 4: Run test + typecheck**
```bash
docker compose exec -T frontend pnpm exec vitest run src/__tests__/hooks/useBriefing.test.tsx
docker compose exec -T frontend pnpm exec tsc --noEmit
```
Expected: test passes; tsc clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/api/briefing.ts frontend/src/hooks/useBriefing.ts \
        frontend/src/__tests__/hooks/useBriefing.test.tsx
LEFTHOOK=0 git commit -m "feat(frontend): briefing client + hooks

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `/briefing` page + route/nav/command/shortcut

**Files:** Create `frontend/src/pages/BriefingPage.tsx`, `frontend/src/__tests__/BriefingPage.test.tsx`; Modify `frontend/src/router.tsx`, `frontend/src/components/layout/SideNav.tsx`, `frontend/src/components/layout/AppLayout.tsx`, `frontend/src/hooks/useKeyboardShortcuts.ts`.

- [ ] **Step 1: Create the page** — `frontend/src/pages/BriefingPage.tsx`:

```tsx
import { useLatestBriefing, useRunBriefing } from "@/hooks/useBriefing";
import { Skeleton } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";

export default function BriefingPage() {
  const { data: briefing, isLoading } = useLatestBriefing();
  const run = useRunBriefing();

  if (isLoading) return <Skeleton className="h-48" />;
  if (!briefing) {
    return (
      <EmptyState
        title="No briefing yet"
        body="Run your first briefing to see open theses, upcoming events, and overnight activity."
        action={{ label: run.isPending ? "Running…" : "Run now", onClick: () => run.mutate() }}
      />
    );
  }

  const d = briefing.data;
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Morning briefing</h1>
        <button
          className="rounded border border-rule px-3 py-1 text-sm text-ink-400 hover:text-copper-300"
          disabled={run.isPending}
          onClick={() => run.mutate()}
        >
          {run.isPending ? "Running…" : "Run now"}
        </button>
      </div>

      <section className="rounded border border-rule p-4">
        <h2 className="mb-2 text-sm font-semibold text-ink-400">Synthesis</h2>
        {briefing.synthesis_text
          ? <p className="whitespace-pre-wrap">{briefing.synthesis_text}</p>
          : <p className="text-ink-400">Synthesizing… (refreshes automatically)</p>}
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Open theses</h2>
        {d.theses.length === 0 ? <EmptyState title="No open theses" /> : (
          <table className="w-full text-sm">
            <thead><tr className="text-ink-400">
              <th className="text-left">Ticker</th><th>Dir</th><th>Now</th>
              <th>→Target</th><th>→Invalid.</th><th>Conv</th>
            </tr></thead>
            <tbody>
              {d.theses.map((t) => (
                <tr key={t.id} className="border-t border-rule">
                  <td>{t.ticker}</td><td>{t.direction}</td><td>{t.current ?? "—"}</td>
                  <td>{t.pct_to_target ?? "—"}%</td><td>{t.pct_to_invalidation ?? "—"}%</td>
                  <td>{t.conviction}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Upcoming events</h2>
        {d.events.earnings.length + d.events.macro.length === 0
          ? <EmptyState title="No upcoming events" />
          : <ul className="text-sm">
              {[...d.events.earnings, ...d.events.macro].map((e, i) => (
                <li key={i}>{String((e as { title?: string; ticker?: string }).title
                  ?? (e as { ticker?: string }).ticker)} · in {String((e as { days_until?: number }).days_until)}d</li>
              ))}
            </ul>}
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Overnight triggers</h2>
        {d.triggers.length === 0 ? <EmptyState title="No triggers fired" />
          : <ul className="text-sm">{d.triggers.map((t) => <li key={t.fired_at}>{t.name}: {t.summary}</li>)}</ul>}
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Overnight news</h2>
        {d.news.length === 0 ? <EmptyState title="No news" />
          : <ul className="text-sm">{d.news.map((n, i) => <li key={i}>{n.headline} ({n.source})</li>)}</ul>}
      </section>
    </div>
  );
}
```

> Verify against sibling pages (`AnalyticsPage.tsx`, `ThesesPage.tsx`): the named-vs-default export of `Skeleton`/`EmptyState`, `EmptyState`'s prop shape (does it accept `action={{label,onClick}}`? if not, render a separate `<button>`), and the Tailwind token classes (`border-rule`/`text-ink-400`/`text-copper-300`). Adapt to what they actually use; tsc + lint are the gates.

- [ ] **Step 2: Wire route + nav + command + shortcut**

`frontend/src/router.tsx`: add `import BriefingPage from "./pages/BriefingPage";` and the route (after the `events` route, before `analytics`):
```tsx
      { path: "briefing", element: <BriefingPage />, handle: { crumb: "Briefing" } },
```
`frontend/src/components/layout/SideNav.tsx`: add to `TRADING` (after `["/events", "Events", "EV"]`):
```tsx
  ["/briefing", "Briefing", "BR"],
```
`frontend/src/components/layout/AppLayout.tsx`: add to `useDefaultCommands` (after `go-events`):
```tsx
      { id: "go-briefing", label: "Go to Briefing", keywords: "morning digest summary daily",
        run: () => nav("/briefing") },
```
`frontend/src/hooks/useKeyboardShortcuts.ts`: add to `SHORTCUTS` (after `e:`):
```ts
  b: { path: "/briefing", label: "Briefing" },
```

- [ ] **Step 3: Render test** — create `frontend/src/__tests__/BriefingPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import BriefingPage from "@/pages/BriefingPage";
import * as hooks from "@/hooks/useBriefing";

function mockLatest(value: unknown, isLoading = false) {
  vi.spyOn(hooks, "useLatestBriefing").mockReturnValue({ data: value, isLoading } as never);
  vi.spyOn(hooks, "useRunBriefing").mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
}

describe("BriefingPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows empty state with no briefing", () => {
    mockLatest(null);
    render(<MemoryRouter><BriefingPage /></MemoryRouter>);
    expect(screen.getByText(/No briefing yet/i)).toBeInTheDocument();
  });

  it("renders synthesis + theses when populated", () => {
    mockLatest({
      id: 1, status: "ready", created_at: "x", scheduled_date: null, snapshot: null,
      synthesis_text: "Lead with NVDA.", synthesis_status: "done",
      data: { theses: [{ id: 1, ticker: "NVDA", direction: "bullish", conviction: 4,
        entry: null, target: 110, invalidation: 90, current: 100, pct_to_target: 10,
        pct_to_invalidation: -10 }],
        events: { earnings: [], macro: [] }, triggers: [], news: [], market: {}, since: "x" },
    });
    render(<MemoryRouter><BriefingPage /></MemoryRouter>);
    expect(screen.getByText("Lead with NVDA.")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Verify build + lint + test**
```bash
docker compose exec -T frontend pnpm exec vitest run src/__tests__/BriefingPage.test.tsx
docker compose exec -T frontend pnpm exec tsc --noEmit
docker compose exec -T frontend pnpm run lint
```
Expected: tests pass; tsc clean; no new lint errors (no setState-in-effect).

- [ ] **Step 5: Commit**
```bash
git add frontend/src/pages/BriefingPage.tsx frontend/src/__tests__/BriefingPage.test.tsx \
        frontend/src/router.tsx frontend/src/components/layout/SideNav.tsx \
        frontend/src/components/layout/AppLayout.tsx frontend/src/hooks/useKeyboardShortcuts.ts
LEFTHOOK=0 git commit -m "feat(frontend): /briefing page + nav + command + g b shortcut

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Full check + docs

**Files:** Modify `CLAUDE.md`.

- [ ] **Step 1: Run the full gate**
Run: `make check`
Expected: ruff + pytest + frontend eslint/tsc + vitest green. (`ty` advisory non-zero is expected.) If `ruff format --check` flags new files, run `docker compose exec -T web ruff format <files>` + `ruff check --fix <files>` and commit the formatting separately. Fix any real failures.

- [ ] **Step 2: CLAUDE.md note** — under "Non-obvious conventions", add:
```markdown
- **Morning Briefing is a daily hybrid synthesis in `apps.briefing`.** `BriefingConfig` (singleton via `.load()`) + `BriefingRun` (own model). `services/assemble.py` gathers deterministic sections (open theses w/ price-vs-target via `fetch_quotes`, `upcoming_events`, overnight `TriggerFiring`, overnight news, a `breadth`-only `capture(source="briefing")`); `services/run.py` posts a synthetic user `Message` into a `kind="briefing"` thread via `run_ai_on_message` for the best-effort AI synthesis. `briefing.run_scheduled` beat (every 15min) fires once/day via a unique `scheduled_date` claim (manual `POST /api/briefings/run/` is unlimited). The AI layer degrades gracefully — the data sections render with no key.
```

- [ ] **Step 3: Commit**
```bash
git add CLAUDE.md
LEFTHOOK=0 git commit -m "docs(briefing): record convention note

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:** Models (BriefingConfig singleton + BriefingRun + scheduled_date claim) → Task 1. Thread/Notification kinds → Task 2. `assemble()` (theses/events/triggers/news/market/since) → Task 3. `run_briefing` + render + thread + AI dispatch + notify → Task 4. Beat task → Task 5. Config API → Task 6. list/latest/run API → Task 7. Frontend client/hooks → Task 8. Page + route/nav/command/`g b` → Task 9. Full check + docs → Task 10. Spec out-of-scope items (per-profile, email delivery, structured cards, analytics) have no tasks — correct.

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to". Each step has full code. The frontend tasks carry explicit "verify against sibling files" notes for the genuinely-uncertain bits (Skeleton/EmptyState export style + props, Tailwind tokens, `apiPatch` name) — these are real verification points, not placeholders, and tsc/lint gate them.

**3. Type/name consistency:** `BriefingConfig.load()`, `BriefingRun.scheduled_date`/`status`/`data`/`synthesis_message`, `assemble()→(data, snapshot)`, `run_briefing(*, scheduled)`, `render_briefing_markdown`, `get_or_create_briefing_thread`, `_now_local`/`_local_today`, `run_scheduled` — all used consistently across tasks. The `data` dict keys (theses/events/triggers/news/market/since) match between assemble (T3), render (T4), serializer (T7), and the frontend `BriefingData` type (T8) + page (T9). API paths `/api/briefings/{,latest/,run/,config/}` consistent between T6/T7 (urls) and T8 (client). `run_ai_on_message.delay(thread_id=, user_message_id=)` matches the observer usage.

**Known follow-ups flagged in-plan:** `TriggerFiring.trigger.name` (defensive `getattr` fallback), `apiPatch` export name, and the `EmptyState` `action` prop shape — all verification points the implementer confirms against the real files, gated by tests/tsc/lint.
