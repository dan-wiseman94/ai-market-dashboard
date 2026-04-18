# M7 — Event Triggers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add condition-based event triggers: users define DSL rules via a guided visual builder, a Celery-beat scheduled task evaluates them every 10s during market hours, matching rules fire a snapshot + AI analysis + OS/bell notification. Honors cost caps and cooldown + re-arm gates.

**Architecture:** New `apps/triggers/` Django app. Two models (`EventTrigger`, `TriggerFiring`). The evaluator is a pure function over a flat `MetricsSnapshot` dict populated by `metrics.build_snapshot(triggers)` — the only module that touches Schwab + Redis. Crossings use Redis `trigger:last:<TICKER>` (TTL 60s). Cooldown is time-elapsed AND re-armed-on-false. Frontend adds `/triggers` list, `/triggers/:id` editor with form-row rule builder + natural-language echo + live-preview, a `RecentTriggersCard` on the dashboard. Reuses M6's `notify()`, `market_hours`, and `NotificationBell`.

**Tech Stack:** Django 5 + DRF, Celery + django-celery-beat, Postgres 16, Redis 7, `redis` py client, React 18 + Vite + TanStack Query v5.

**Spec:** `docs/superpowers/specs/2026-04-18-m7-event-triggers-design.md`

**Scope note:** `volume_z` metric is deferred to M8 (needs a volume-history store that doesn't exist). The DSL supports `not`, but the UI doesn't expose it. No nested condition groups in the UI (single top-level `all|any` over flat leaves).

---

## Task 1: Create `apps/triggers/` Django app skeleton

**Files:**
- Create: `backend/apps/triggers/__init__.py` (empty)
- Create: `backend/apps/triggers/apps.py`
- Create: `backend/apps/triggers/migrations/__init__.py` (empty)
- Create: `backend/apps/triggers/tests/__init__.py` (empty)
- Modify: `backend/config/settings/base.py` (add `"apps.triggers"` to `INSTALLED_APPS`)
- Modify: `backend/config/celery.py` (add `"apps.triggers"` to autodiscover list)

- [ ] **Step 1.1: Create directory skeleton**

```bash
mkdir -p backend/apps/triggers/migrations backend/apps/triggers/services backend/apps/triggers/tests
touch backend/apps/triggers/__init__.py
touch backend/apps/triggers/migrations/__init__.py
touch backend/apps/triggers/services/__init__.py
touch backend/apps/triggers/tests/__init__.py
```

- [ ] **Step 1.2: Write `apps.py`**

`backend/apps/triggers/apps.py`:
```python
from django.apps import AppConfig


class TriggersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.triggers"
    label = "triggers"
```

- [ ] **Step 1.3: Add to INSTALLED_APPS**

Read `backend/config/settings/base.py` first. Locate the `INSTALLED_APPS` list and add `"apps.triggers",` alongside the other `apps.*` entries (alphabetical after `apps.threads`).

- [ ] **Step 1.4: Register in Celery autodiscover list**

Edit `backend/config/celery.py`. Find the `app.autodiscover_tasks([...])` call and add `"apps.triggers",` to the list (alphabetical after `"apps.threads"`).

- [ ] **Step 1.5: Smoke check — Django loads the app**

```bash
docker compose exec web python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 1.6: Commit**

```bash
git add backend/apps/triggers backend/config/settings/base.py backend/config/celery.py
git commit -m "feat(triggers): scaffold apps.triggers Django app"
```

---

## Task 2: `EventTrigger` model + migration

**Files:**
- Create: `backend/apps/triggers/models.py`
- Create: `backend/apps/triggers/tests/test_event_trigger_model.py`
- Migration: auto-generated

- [ ] **Step 2.1: Write the failing test**

`backend/apps/triggers/tests/test_event_trigger_model.py`:
```python
import pytest
from django.db import IntegrityError

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger


@pytest.mark.django_db
def test_event_trigger_defaults():
    p = TradingProfile.objects.create(name="Default", style="x")
    t = EventTrigger.objects.create(
        name="SPY > 550", profile=p,
        condition={"all": [{"metric": "price", "ticker": "SPY", "op": ">", "value": 550}]},
    )
    assert t.enabled is True
    assert t.cooldown_seconds == 1800
    assert t.last_fired_at is None


@pytest.mark.django_db
def test_event_trigger_unique_name_per_profile():
    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(name="rule", profile=p, condition={"all": []})
    with pytest.raises(IntegrityError):
        EventTrigger.objects.create(name="rule", profile=p, condition={"all": []})


@pytest.mark.django_db
def test_event_trigger_same_name_different_profile_ok():
    p1 = TradingProfile.objects.create(name="P1", style="x")
    p2 = TradingProfile.objects.create(name="P2", style="x")
    EventTrigger.objects.create(name="rule", profile=p1, condition={"all": []})
    EventTrigger.objects.create(name="rule", profile=p2, condition={"all": []})
```

- [ ] **Step 2.2: Run test, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_event_trigger_model.py -v
```
Expected: ImportError on `apps.triggers.models` (no `EventTrigger`).

- [ ] **Step 2.3: Write the model**

`backend/apps/triggers/models.py`:
```python
"""EventTrigger + TriggerFiring models."""
from __future__ import annotations

from django.db import models


class EventTrigger(models.Model):
    name = models.CharField(max_length=100)
    profile = models.ForeignKey(
        "profiles.TradingProfile", on_delete=models.CASCADE,
        related_name="triggers",
    )
    condition = models.JSONField()
    cooldown_seconds = models.PositiveIntegerField(default=1800)
    enabled = models.BooleanField(default=True)
    last_fired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["enabled", "-last_fired_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "name"],
                name="unique_trigger_name_per_profile",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (profile={self.profile_id})"
```

- [ ] **Step 2.4: Generate + apply migration**

```bash
docker compose exec web python manage.py makemigrations triggers
docker compose exec web python manage.py migrate triggers
```
Expected: creates `0001_initial.py`, applies without errors.

- [ ] **Step 2.5: Run test, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_event_trigger_model.py -v
```
Expected: 3 passed.

- [ ] **Step 2.6: Commit**

```bash
git add backend/apps/triggers/models.py backend/apps/triggers/migrations/ backend/apps/triggers/tests/test_event_trigger_model.py
git commit -m "feat(triggers): EventTrigger model + migration"
```

---

## Task 3: `TriggerFiring` model + migration

**Files:**
- Modify: `backend/apps/triggers/models.py`
- Create: `backend/apps/triggers/tests/test_trigger_firing_model.py`
- Migration: auto-generated (0002)

- [ ] **Step 3.1: Write the failing test**

`backend/apps/triggers/tests/test_trigger_firing_model.py`:
```python
import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Thread
from apps.triggers.models import EventTrigger, TriggerFiring


@pytest.mark.django_db
def test_trigger_firing_minimal():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    f = TriggerFiring.objects.create(
        trigger=t,
        matched_values={"price:SPY": 551.2},
    )
    assert f.cost_capped is False
    assert f.snapshot is None
    assert f.thread is None
    assert f.fired_at is not None


@pytest.mark.django_db
def test_trigger_firing_with_refs():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    snap = Snapshot.objects.create(profile=p, includes=[])
    thread = Thread.objects.create(kind="chat", profile=p, title="t")
    f = TriggerFiring.objects.create(
        trigger=t, matched_values={}, snapshot=snap, thread=thread,
    )
    assert f.snapshot_id == snap.id
    assert f.thread_id == thread.id


@pytest.mark.django_db
def test_trigger_firing_deleted_on_trigger_cascade():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    TriggerFiring.objects.create(trigger=t, matched_values={})
    t.delete()
    assert TriggerFiring.objects.count() == 0
```

- [ ] **Step 3.2: Run test, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_trigger_firing_model.py -v
```
Expected: ImportError on `TriggerFiring`.

- [ ] **Step 3.3: Add the model**

Append to `backend/apps/triggers/models.py`:
```python
class TriggerFiring(models.Model):
    trigger = models.ForeignKey(
        EventTrigger, on_delete=models.CASCADE, related_name="firings",
    )
    fired_at = models.DateTimeField(auto_now_add=True)
    matched_values = models.JSONField()
    snapshot = models.ForeignKey(
        "snapshots.Snapshot", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="trigger_firings",
    )
    thread = models.ForeignKey(
        "threads.Thread", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="trigger_firings",
    )
    cost_capped = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["trigger", "-fired_at"]),
            models.Index(fields=["-fired_at"]),
        ]
```

- [ ] **Step 3.4: Generate + apply migration**

```bash
docker compose exec web python manage.py makemigrations triggers
docker compose exec web python manage.py migrate triggers
```
Expected: creates `0002_triggerfiring.py`.

- [ ] **Step 3.5: Run tests**

```bash
docker compose exec web pytest apps/triggers/tests/ -v
```
Expected: 6 passed.

- [ ] **Step 3.6: Commit**

```bash
git add backend/apps/triggers/models.py backend/apps/triggers/migrations/ backend/apps/triggers/tests/test_trigger_firing_model.py
git commit -m "feat(triggers): TriggerFiring model + migration"
```

---

## Task 4: DSL validator (`apps/triggers/dsl.py`)

**Files:**
- Create: `backend/apps/triggers/dsl.py`
- Create: `backend/apps/triggers/tests/test_dsl_validation.py`

- [ ] **Step 4.1: Write the failing tests**

`backend/apps/triggers/tests/test_dsl_validation.py`:
```python
import pytest
from django.core.exceptions import ValidationError

from apps.triggers.dsl import validate_condition


def test_validate_price_leaf_ok():
    validate_condition({"metric": "price", "ticker": "SPY", "op": ">", "value": 550})


def test_validate_pct_change_requires_window():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "pct_change", "ticker": "SPY", "op": ">=", "value": 0.01})
    assert "window" in str(exc.value)


def test_validate_price_rejects_window():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "price", "ticker": "SPY", "op": ">", "value": 550, "window": "5m"})
    assert "window" in str(exc.value)


def test_validate_all_group_ok():
    validate_condition({"all": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        {"metric": "vix", "op": ">", "value": 20},
    ]})


def test_validate_any_group_ok():
    validate_condition({"any": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        {"metric": "price", "ticker": "QQQ", "op": ">", "value": 480},
    ]})


def test_validate_not_wraps_one_node():
    validate_condition({"not": {"metric": "vix", "op": ">", "value": 30}})


def test_validate_not_rejects_multiple():
    with pytest.raises(ValidationError):
        validate_condition({"not": [
            {"metric": "vix", "op": ">", "value": 30},
            {"metric": "vix", "op": "<", "value": 10},
        ]})


def test_validate_unknown_metric():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "foo", "ticker": "SPY", "op": ">", "value": 1})
    assert "metric" in str(exc.value)


def test_validate_unknown_op():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "price", "ticker": "SPY", "op": "??", "value": 1})
    assert "op" in str(exc.value)


def test_validate_price_requires_ticker():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "price", "op": ">", "value": 1})
    assert "ticker" in str(exc.value)


def test_validate_vix_ticker_optional():
    # vix forces $VIX downstream; ticker presence is tolerated but unused.
    validate_condition({"metric": "vix", "op": ">", "value": 20})
    validate_condition({"metric": "vix", "ticker": "$VIX", "op": ">", "value": 20})


def test_validate_window_must_be_valid():
    with pytest.raises(ValidationError):
        validate_condition({"metric": "pct_change", "ticker": "SPY", "op": ">", "value": 0.01, "window": "7m"})


def test_validate_value_must_be_number():
    with pytest.raises(ValidationError):
        validate_condition({"metric": "price", "ticker": "SPY", "op": ">", "value": "550"})


def test_validate_error_path_reports_location():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"all": [
            {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
            {"metric": "bad", "ticker": "SPY", "op": ">", "value": 1},
        ]})
    assert ".all[1]" in str(exc.value)


def test_validate_empty_group_ok():
    # Empty all → always True, empty any → always False. Both valid shapes.
    validate_condition({"all": []})
    validate_condition({"any": []})
```

- [ ] **Step 4.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_dsl_validation.py -v
```
Expected: ImportError on `apps.triggers.dsl`.

- [ ] **Step 4.3: Write the validator**

`backend/apps/triggers/dsl.py`:
```python
"""Condition DSL validator.

Called from EventTrigger.clean() and the DRF serializer. Keeps invalid JSON
out of the database and returns user-facing error paths like ".all[1].op".
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

VALID_METRICS = {"price", "pct_change", "vix", "position_pl", "position_pl_pct"}
VALID_OPS = {">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"}
VALID_WINDOWS = {"1m", "5m", "15m", "1h", "1d"}
TICKER_REQUIRED = {"price", "pct_change"}
WINDOW_REQUIRED = {"pct_change"}


def validate_condition(node: Any, *, path: str = "") -> None:
    """Recurse the tree. Raises ValidationError with path on any invalid shape."""
    if not isinstance(node, dict):
        raise ValidationError(f"{path or '<root>'}: expected object, got {type(node).__name__}")

    # Group nodes
    for key in ("all", "any"):
        if key in node:
            children = node[key]
            if not isinstance(children, list):
                raise ValidationError(f"{path}.{key}: must be a list")
            for i, child in enumerate(children):
                validate_condition(child, path=f"{path}.{key}[{i}]")
            if len(node) != 1:
                raise ValidationError(f"{path}.{key}: group node must have only '{key}' key")
            return

    if "not" in node:
        if len(node) != 1:
            raise ValidationError(f"{path}.not: must have only 'not' key")
        child = node["not"]
        if isinstance(child, list):
            raise ValidationError(f"{path}.not: must wrap a single node, got list")
        validate_condition(child, path=f"{path}.not")
        return

    # Leaf node
    metric = node.get("metric")
    if metric not in VALID_METRICS:
        raise ValidationError(f"{path}.metric: unknown metric {metric!r}")
    op = node.get("op")
    if op not in VALID_OPS:
        raise ValidationError(f"{path}.op: unknown operator {op!r}")
    value = node.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(f"{path}.value: must be a number")
    if metric in TICKER_REQUIRED and not node.get("ticker"):
        raise ValidationError(f"{path}.ticker: required for metric {metric!r}")
    window = node.get("window")
    if metric in WINDOW_REQUIRED and window is None:
        raise ValidationError(f"{path}.window: required for metric {metric!r}")
    if metric not in WINDOW_REQUIRED and window is not None:
        raise ValidationError(f"{path}.window: not allowed for metric {metric!r}")
    if window is not None and window not in VALID_WINDOWS:
        raise ValidationError(f"{path}.window: {window!r} is not a valid window")
```

- [ ] **Step 4.4: Run tests, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_dsl_validation.py -v
```
Expected: 15 passed.

- [ ] **Step 4.5: Wire into `EventTrigger.clean()`**

Edit `backend/apps/triggers/models.py`. Add `clean()` to `EventTrigger`:
```python
    def clean(self) -> None:
        from apps.triggers.dsl import validate_condition
        validate_condition(self.condition)
```

Add a test to `test_event_trigger_model.py`:
```python
from django.core.exceptions import ValidationError


@pytest.mark.django_db
def test_event_trigger_clean_runs_dsl_validator():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger(name="bad", profile=p, condition={"metric": "nope"})
    with pytest.raises(ValidationError):
        t.full_clean()
```

- [ ] **Step 4.6: Run tests**

```bash
docker compose exec web pytest apps/triggers/tests/ -v
```
Expected: 16 passed (15 DSL + 4 model = 19 actually, confirm the count locally).

- [ ] **Step 4.7: Commit**

```bash
git add backend/apps/triggers/dsl.py backend/apps/triggers/models.py backend/apps/triggers/tests/
git commit -m "feat(triggers): DSL validator + EventTrigger.clean wiring"
```

---

## Task 5: Pure evaluator — comparison ops

**Files:**
- Create: `backend/apps/triggers/evaluator.py`
- Create: `backend/apps/triggers/tests/test_evaluator_compare.py`

- [ ] **Step 5.1: Write the failing tests**

`backend/apps/triggers/tests/test_evaluator_compare.py`:
```python
import pytest

from apps.triggers.evaluator import evaluate


METRICS = {
    "price:SPY": 551.2,
    "price:QQQ": 480.0,
    "vix": 22.5,
    "position_pl": -350.0,
    "position_pl_pct": -0.025,
}


@pytest.mark.parametrize("op,value,expected", [
    (">", 550, True),
    (">=", 551.2, True),
    ("<", 600, True),
    ("<=", 551.2, True),
    ("==", 551.2, True),
    (">", 551.2, False),
    (">=", 551.3, False),
    ("<", 551.2, False),
    ("<=", 551.19, False),
    ("==", 551.19, False),
])
def test_price_comparison_ops(op, value, expected):
    node = {"metric": "price", "ticker": "SPY", "op": op, "value": value}
    matched, values = evaluate(node, METRICS)
    assert matched is expected
    assert values == {"price:SPY": 551.2}


def test_vix_leaf_reads_bare_key():
    node = {"metric": "vix", "op": ">", "value": 20}
    matched, values = evaluate(node, METRICS)
    assert matched is True
    assert values == {"vix": 22.5}


def test_position_pl_reads_bare_key():
    node = {"metric": "position_pl", "op": "<", "value": -300}
    matched, values = evaluate(node, METRICS)
    assert matched is True
    assert values == {"position_pl": -350.0}


def test_position_pl_pct_reads_bare_key():
    node = {"metric": "position_pl_pct", "op": "<=", "value": -0.02}
    matched, _ = evaluate(node, METRICS)
    assert matched is True


def test_pct_change_reads_keyed_with_window():
    m = {"pct_change:SPY:5m": 0.014}
    node = {"metric": "pct_change", "ticker": "SPY", "op": ">=", "value": 0.01, "window": "5m"}
    matched, values = evaluate(node, m)
    assert matched is True
    assert values == {"pct_change:SPY:5m": 0.014}


def test_missing_metric_returns_false():
    node = {"metric": "price", "ticker": "TSLA", "op": ">", "value": 100}
    matched, values = evaluate(node, METRICS)
    assert matched is False
    # matched_values still records which key we attempted to read
    assert values == {"price:TSLA": None}


def test_none_metric_returns_false():
    m = {"price:SPY": None}
    node = {"metric": "price", "ticker": "SPY", "op": ">", "value": 0}
    matched, values = evaluate(node, m)
    assert matched is False
    assert values == {"price:SPY": None}
```

- [ ] **Step 5.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_evaluator_compare.py -v
```
Expected: ImportError on `apps.triggers.evaluator`.

- [ ] **Step 5.3: Write the evaluator skeleton (leaf dispatcher + compare ops)**

`backend/apps/triggers/evaluator.py`:
```python
"""Pure evaluator for the trigger condition DSL.

No I/O: takes a MetricsSnapshot dict literal and returns (matched, matched_values).
matched_values records every metric key the evaluator read during this call —
used to populate TriggerFiring.matched_values and the notification body.
"""
from __future__ import annotations

import operator
from collections.abc import Mapping
from typing import Any

MetricsSnapshot = Mapping[str, float | None]

_COMPARE_OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}


def evaluate(node: dict, metrics: MetricsSnapshot) -> tuple[bool, dict[str, float | None]]:
    """Recurse the tree; return (matched, matched_values_this_call)."""
    values: dict[str, float | None] = {}
    matched = _eval_node(node, metrics, values)
    return matched, values


def _eval_node(node: dict, metrics: MetricsSnapshot, values: dict) -> bool:
    if "all" in node:
        for child in node["all"]:
            if not _eval_node(child, metrics, values):
                return False
        return True
    if "any" in node:
        for child in node["any"]:
            if _eval_node(child, metrics, values):
                return True
        return False
    if "not" in node:
        return not _eval_node(node["not"], metrics, values)
    return _eval_leaf(node, metrics, values)


def _leaf_key(node: dict) -> str:
    metric = node["metric"]
    if metric == "vix":
        return "vix"
    if metric.startswith("position_"):
        return metric
    if metric == "pct_change":
        return f"pct_change:{node['ticker']}:{node['window']}"
    # price
    return f"price:{node['ticker']}"


def _eval_leaf(node: dict, metrics: MetricsSnapshot, values: dict) -> bool:
    key = _leaf_key(node)
    current = metrics.get(key)
    values[key] = current
    if current is None:
        return False
    op = node["op"]
    if op in _COMPARE_OPS:
        return bool(_COMPARE_OPS[op](current, node["value"]))
    # crossing ops handled in a later task; raise so tests don't silently pass yet
    raise NotImplementedError(f"op {op} not implemented")
```

- [ ] **Step 5.4: Run tests, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_evaluator_compare.py -v
```
Expected: all passed (14 rows via parametrize + 6 others = 20 test IDs).

- [ ] **Step 5.5: Commit**

```bash
git add backend/apps/triggers/evaluator.py backend/apps/triggers/tests/test_evaluator_compare.py
git commit -m "feat(triggers): pure evaluator with comparison ops"
```

---

## Task 6: Evaluator — crossing operators

**Files:**
- Modify: `backend/apps/triggers/evaluator.py`
- Create: `backend/apps/triggers/tests/test_evaluator_crossings.py`

- [ ] **Step 6.1: Write the failing tests**

`backend/apps/triggers/tests/test_evaluator_crossings.py`:
```python
import pytest

from apps.triggers.evaluator import evaluate


def test_crosses_above_fires_on_sign_change():
    metrics = {"price:SPY": 551.0, "_prior:price:SPY": 549.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, values = evaluate(node, metrics)
    assert matched is True
    assert values == {"price:SPY": 551.0, "_prior:price:SPY": 549.0}


def test_crosses_above_requires_prior_below_or_equal():
    # Already above threshold last tick → no edge
    metrics = {"price:SPY": 552.0, "_prior:price:SPY": 551.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_above_requires_current_strictly_above():
    metrics = {"price:SPY": 550.0, "_prior:price:SPY": 549.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_below_fires_on_sign_change():
    metrics = {"price:SPY": 549.5, "_prior:price:SPY": 550.5}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_below", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is True


def test_crosses_below_requires_prior_above_or_equal():
    metrics = {"price:SPY": 548.0, "_prior:price:SPY": 549.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_below", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_missing_prior_returns_false():
    metrics = {"price:SPY": 551.0, "_prior:price:SPY": None}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_missing_current_returns_false():
    metrics = {"price:SPY": None, "_prior:price:SPY": 549.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_on_vix():
    metrics = {"vix": 30.5, "_prior:vix": 29.0}
    node = {"metric": "vix", "op": "crosses_above", "value": 30}
    matched, _ = evaluate(node, metrics)
    assert matched is True
```

- [ ] **Step 6.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_evaluator_crossings.py -v
```
Expected: failures on NotImplementedError.

- [ ] **Step 6.3: Extend evaluator with crossing ops**

In `backend/apps/triggers/evaluator.py`, replace the `_eval_leaf` function:
```python
def _eval_leaf(node: dict, metrics: MetricsSnapshot, values: dict) -> bool:
    key = _leaf_key(node)
    current = metrics.get(key)
    values[key] = current
    op = node["op"]
    if op in _COMPARE_OPS:
        if current is None:
            return False
        return bool(_COMPARE_OPS[op](current, node["value"]))
    if op in ("crosses_above", "crosses_below"):
        prior_key = f"_prior:{key}"
        prior = metrics.get(prior_key)
        values[prior_key] = prior
        if current is None or prior is None:
            return False
        threshold = node["value"]
        if op == "crosses_above":
            return prior <= threshold < current
        return prior >= threshold > current
    raise ValueError(f"unknown op {op!r}")
```

- [ ] **Step 6.4: Run tests, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_evaluator_crossings.py -v apps/triggers/tests/test_evaluator_compare.py -v
```
Expected: all passed.

- [ ] **Step 6.5: Commit**

```bash
git add backend/apps/triggers/evaluator.py backend/apps/triggers/tests/test_evaluator_crossings.py
git commit -m "feat(triggers): crossing operators in evaluator"
```

---

## Task 7: Evaluator — groups + `not` recursion

**Files:**
- Create: `backend/apps/triggers/tests/test_evaluator_groups.py`

- [ ] **Step 7.1: Write the failing tests**

`backend/apps/triggers/tests/test_evaluator_groups.py`:
```python
from apps.triggers.evaluator import evaluate


METRICS = {"price:SPY": 551.0, "vix": 22.0, "price:QQQ": 480.0}


def test_all_group_true_when_all_leaves_match():
    node = {"all": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        {"metric": "vix", "op": ">", "value": 20},
    ]}
    matched, values = evaluate(node, METRICS)
    assert matched is True
    assert "price:SPY" in values and "vix" in values


def test_all_group_false_short_circuits():
    # Second leaf would read a missing key; we short-circuit on the first failing leaf.
    node = {"all": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
        {"metric": "price", "ticker": "NOPE", "op": ">", "value": 0},
    ]}
    matched, values = evaluate(node, METRICS)
    assert matched is False
    # Only the first leaf's key landed in values
    assert values == {"price:SPY": 551.0}


def test_any_group_true_on_first_match():
    node = {"any": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        {"metric": "vix", "op": ">", "value": 100},
    ]}
    matched, _ = evaluate(node, METRICS)
    assert matched is True


def test_any_group_false_when_all_miss():
    node = {"any": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
        {"metric": "vix", "op": ">", "value": 100},
    ]}
    matched, _ = evaluate(node, METRICS)
    assert matched is False


def test_not_flips_leaf():
    node = {"not": {"metric": "vix", "op": ">", "value": 100}}
    matched, _ = evaluate(node, METRICS)
    assert matched is True


def test_not_flips_group():
    node = {"not": {"all": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
    ]}}
    matched, _ = evaluate(node, METRICS)
    assert matched is True


def test_empty_all_group_is_true():
    matched, values = evaluate({"all": []}, METRICS)
    assert matched is True
    assert values == {}


def test_empty_any_group_is_false():
    matched, values = evaluate({"any": []}, METRICS)
    assert matched is False
    assert values == {}


def test_nested_all_inside_any():
    node = {"any": [
        {"all": [
            {"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
            {"metric": "vix", "op": ">", "value": 10},
        ]},
        {"metric": "price", "ticker": "QQQ", "op": ">", "value": 400},
    ]}
    matched, _ = evaluate(node, METRICS)
    assert matched is True   # second branch matches
```

- [ ] **Step 7.2: Run tests — expect all pass**

(Group recursion was already implemented in Task 5; this task is verifying coverage.)

```bash
docker compose exec web pytest apps/triggers/tests/test_evaluator_groups.py -v
```
Expected: 9 passed.

- [ ] **Step 7.3: Commit**

```bash
git add backend/apps/triggers/tests/test_evaluator_groups.py
git commit -m "test(triggers): evaluator group/negation coverage"
```

---

## Task 8: `describe(matched_values)` helper

**Files:**
- Create: `backend/apps/triggers/services/describe.py`
- Create: `backend/apps/triggers/tests/test_describe.py`

- [ ] **Step 8.1: Write the failing tests**

`backend/apps/triggers/tests/test_describe.py`:
```python
from apps.triggers.services.describe import describe


def test_describe_price_leaf():
    assert describe({"price:SPY": 551.23}) == "SPY=551.23"


def test_describe_pct_change():
    # Percentage with two decimals, leading +/-
    assert describe({"pct_change:SPY:5m": 0.0142}) == "SPY +1.42% / 5m"
    assert describe({"pct_change:NVDA:1h": -0.024}) == "NVDA -2.40% / 1h"


def test_describe_vix():
    assert describe({"vix": 22.5}) == "vix=22.50"


def test_describe_position_pl():
    assert describe({"position_pl": -312.4}) == "position_pl=-312.40"


def test_describe_position_pl_pct():
    assert describe({"position_pl_pct": -0.018}) == "position_pl -1.80%"


def test_describe_multiple_joined_with_comma():
    out = describe({"price:SPY": 551.2, "vix": 22.5})
    assert "SPY=551.20" in out
    assert "vix=22.50" in out
    assert "," in out


def test_describe_ignores_prior_keys():
    out = describe({"price:SPY": 551.2, "_prior:price:SPY": 549.0})
    assert out == "SPY=551.20"


def test_describe_ignores_none_values():
    out = describe({"price:SPY": None, "vix": 22.5})
    assert out == "vix=22.50"


def test_describe_empty():
    assert describe({}) == ""
```

- [ ] **Step 8.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_describe.py -v
```
Expected: ImportError.

- [ ] **Step 8.3: Write the service**

`backend/apps/triggers/services/describe.py`:
```python
"""Format a matched_values dict into a human-readable string for notifications."""
from __future__ import annotations


def describe(matched_values: dict[str, float | None]) -> str:
    parts: list[str] = []
    for key, value in matched_values.items():
        if value is None or key.startswith("_prior:"):
            continue
        parts.append(_format_one(key, value))
    return ", ".join(parts)


def _format_one(key: str, value: float) -> str:
    if key.startswith("price:"):
        _, ticker = key.split(":", 1)
        return f"{ticker}={value:.2f}"
    if key.startswith("pct_change:"):
        _, ticker, window = key.split(":")
        sign = "+" if value >= 0 else ""
        return f"{ticker} {sign}{value * 100:.2f}% / {window}"
    if key == "vix":
        return f"vix={value:.2f}"
    if key == "position_pl":
        return f"position_pl={value:.2f}"
    if key == "position_pl_pct":
        sign = "+" if value >= 0 else ""
        return f"position_pl {sign}{value * 100:.2f}%"
    return f"{key}={value}"
```

- [ ] **Step 8.4: Run tests, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_describe.py -v
```
Expected: 9 passed.

- [ ] **Step 8.5: Commit**

```bash
git add backend/apps/triggers/services/describe.py backend/apps/triggers/tests/test_describe.py
git commit -m "feat(triggers): describe(matched_values) formatter"
```

---

## Task 9: `metrics.build_snapshot` — quotes + Redis last-price

**Files:**
- Create: `backend/apps/triggers/metrics.py`
- Create: `backend/apps/triggers/tests/test_metrics_quotes.py`

- [ ] **Step 9.1: Install fakeredis (if missing)**

```bash
docker compose exec web python -c "import fakeredis; print('OK')" 2>&1 | tail -1
```

If import fails, append `"fakeredis>=2.20,<3.0",` to `pyproject.toml` `[tool.uv.dev-dependencies]` (or main deps if no split), then:
```bash
docker compose build web worker beat
docker compose up -d web worker beat
docker compose exec web python -c "import fakeredis; print('OK')"
```

- [ ] **Step 9.2: Write the failing tests**

`backend/apps/triggers/tests/test_metrics_quotes.py`:
```python
from unittest.mock import patch

import fakeredis
import pytest

from apps.profiles.models import TradingProfile
from apps.triggers.metrics import build_snapshot
from apps.triggers.models import EventTrigger


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.triggers.metrics._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_build_snapshot_collects_price_leaves(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"all": [
            {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
            {"metric": "price", "ticker": "QQQ", "op": ">", "value": 480},
        ]},
    )

    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}, "QQQ": {"last": 481.0}}
        snap = build_snapshot([t])

    assert snap["price:SPY"] == 551.0
    assert snap["price:QQQ"] == 481.0
    fq.assert_called_once()
    # Distinct ticker union passed to Schwab
    tickers = sorted(fq.call_args[0][0]) if fq.call_args[0] else sorted(fq.call_args.kwargs["tickers"])
    assert tickers == ["QQQ", "SPY"]


@pytest.mark.django_db
def test_build_snapshot_stamps_redis_last_price(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}}
        build_snapshot([t])

    assert fake_redis.get("trigger:last:SPY") == b"551.0"


@pytest.mark.django_db
def test_build_snapshot_populates_prior_for_crossings(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    # Seed redis with a prior
    fake_redis.setex("trigger:last:SPY", 60, "549.5")

    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}}
        snap = build_snapshot([t])

    assert snap["_prior:price:SPY"] == 549.5
    assert snap["price:SPY"] == 551.0


@pytest.mark.django_db
def test_build_snapshot_missing_ticker_is_none(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "NOPE", "op": ">", "value": 1},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {}  # Schwab returned nothing for our ticker
        snap = build_snapshot([t])

    assert snap["price:NOPE"] is None


@pytest.mark.django_db
def test_build_snapshot_vix_metric_fetches_vix_symbol(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "vix", "op": ">", "value": 20},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"$VIX": {"last": 22.5}}
        snap = build_snapshot([t])

    tickers = sorted(fq.call_args[0][0]) if fq.call_args[0] else sorted(fq.call_args.kwargs["tickers"])
    assert "$VIX" in tickers
    assert snap["vix"] == 22.5


@pytest.mark.django_db
def test_build_snapshot_skips_positions_when_not_needed(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.metrics.fetch_positions") as fp:
        fq.return_value = {"SPY": {"last": 551.0}}
        build_snapshot([t])

    fp.assert_not_called()


@pytest.mark.django_db
def test_build_snapshot_stamps_last_tick_at(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}}
        build_snapshot([t])

    assert fake_redis.get("trigger:last_tick_at") is not None
```

- [ ] **Step 9.3: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_metrics_quotes.py -v
```
Expected: ImportError on `apps.triggers.metrics`.

- [ ] **Step 9.4: Write the metrics module**

`backend/apps/triggers/metrics.py`:
```python
"""Build a MetricsSnapshot dict for one beat tick.

This is the only module in apps.triggers that talks to Schwab + Redis.
The evaluator is pure and consumes whatever dict we return here.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any

import redis
from django.conf import settings

from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.triggers.evaluator import MetricsSnapshot
from apps.triggers.models import EventTrigger

log = logging.getLogger(__name__)

_WINDOW_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def build_snapshot(triggers: Iterable[EventTrigger]) -> MetricsSnapshot:
    """Populate the flat metrics dict the evaluator will read.

    Failure modes: any Schwab/Redis error is logged; affected keys land as None
    in the snapshot. The tick proceeds and downstream leaves simply don't fire.
    """
    leaves = _collect_leaves(triggers)
    tickers = _ticker_union(leaves)
    needs_positions = any(l["metric"].startswith("position_") for l in leaves)
    has_vix = any(l["metric"] == "vix" for l in leaves)

    quote_tickers = set(tickers)
    if has_vix:
        quote_tickers.add("$VIX")

    quotes: dict[str, dict] = {}
    if quote_tickers:
        try:
            quotes = fetch_quotes(sorted(quote_tickers))
        except Exception as exc:
            log.warning("trigger.metrics.quotes_failed: %s", exc)

    positions_total_pl: float | None = None
    positions_total_mkt: float | None = None
    if needs_positions:
        try:
            rows = fetch_positions()
            positions_total_pl = sum((r.get("unrealized_pl") or 0) for r in rows) or 0.0
            positions_total_mkt = sum((r.get("mkt_value") or 0) for r in rows) or 0.0
        except Exception as exc:
            log.warning("trigger.metrics.positions_failed: %s", exc)

    snapshot: dict[str, float | None] = {}
    r = _redis()

    for leaf in leaves:
        metric = leaf["metric"]
        op = leaf["op"]
        window = leaf.get("window")
        ticker = leaf.get("ticker")

        if metric == "price":
            assert ticker is not None
            key = f"price:{ticker}"
            last = _extract_last(quotes.get(ticker))
            snapshot[key] = last
            if op in ("crosses_above", "crosses_below"):
                prior = _read_redis_float(r, f"trigger:last:{ticker}")
                snapshot[f"_prior:{key}"] = prior
            if last is not None:
                r.setex(f"trigger:last:{ticker}", 60, str(last))

        elif metric == "vix":
            last = _extract_last(quotes.get("$VIX"))
            snapshot["vix"] = last
            if op in ("crosses_above", "crosses_below"):
                prior = _read_redis_float(r, "trigger:last:$VIX")
                snapshot["_prior:vix"] = prior
            if last is not None:
                r.setex("trigger:last:$VIX", 60, str(last))

        elif metric == "pct_change":
            assert ticker is not None and window is not None
            key = f"pct_change:{ticker}:{window}"
            last = _extract_last(quotes.get(ticker))
            window_key = f"trigger:window:{ticker}:{window}"
            prior = _read_redis_float(r, window_key)
            if last is None:
                snapshot[key] = None
            elif prior is None:
                snapshot[key] = None
                # No prior observation yet; seed one now (TTL = 2 × window so it
                # survives long enough to drive the next tick's comparison).
                r.setex(window_key, 2 * _WINDOW_SECONDS[window], str(last))
            else:
                snapshot[key] = (last - prior) / prior if prior != 0 else None
                # Do NOT overwrite the prior on every tick — only on window expiry.
                # The key's TTL enforces that: expired → setex fresh on next call.
                if not r.exists(window_key):
                    r.setex(window_key, 2 * _WINDOW_SECONDS[window], str(last))

        elif metric == "position_pl":
            snapshot["position_pl"] = positions_total_pl

        elif metric == "position_pl_pct":
            if positions_total_mkt and positions_total_mkt > 0:
                snapshot["position_pl_pct"] = (positions_total_pl or 0) / positions_total_mkt
            else:
                snapshot["position_pl_pct"] = None

    try:
        r.setex("trigger:last_tick_at", 120, str(int(time.time())))
    except Exception as exc:  # noqa: BLE001
        log.warning("trigger.metrics.last_tick_at_failed: %s", exc)

    return snapshot


def _collect_leaves(triggers: Iterable[EventTrigger]) -> list[dict]:
    leaves: list[dict] = []
    for t in triggers:
        _walk(t.condition, leaves)
    return leaves


def _walk(node: Any, out: list[dict]) -> None:
    if not isinstance(node, dict):
        return
    if "all" in node:
        for c in node["all"]:
            _walk(c, out)
        return
    if "any" in node:
        for c in node["any"]:
            _walk(c, out)
        return
    if "not" in node:
        _walk(node["not"], out)
        return
    if "metric" in node:
        out.append(node)


def _ticker_union(leaves: list[dict]) -> set[str]:
    return {l["ticker"] for l in leaves if l.get("ticker") and l["metric"] in ("price", "pct_change")}


def _extract_last(quote_blob: dict | None) -> float | None:
    if not quote_blob:
        return None
    last = quote_blob.get("last")
    return float(last) if last is not None else None


def _read_redis_float(r: redis.Redis, key: str) -> float | None:
    try:
        raw = r.get(key)
    except Exception as exc:  # noqa: BLE001
        log.warning("trigger.metrics.redis_get_failed key=%s: %s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 9.5: Run tests, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_metrics_quotes.py -v
```
Expected: 7 passed.

- [ ] **Step 9.6: Commit**

```bash
git add backend/apps/triggers/metrics.py backend/apps/triggers/tests/test_metrics_quotes.py pyproject.toml
git commit -m "feat(triggers): metrics.build_snapshot (quotes + crossings prior)"
```

---

## Task 10: `metrics.build_snapshot` — positions path

**Files:**
- Create: `backend/apps/triggers/tests/test_metrics_positions.py`

- [ ] **Step 10.1: Write the failing tests**

`backend/apps/triggers/tests/test_metrics_positions.py`:
```python
from unittest.mock import patch

import fakeredis
import pytest

from apps.profiles.models import TradingProfile
from apps.triggers.metrics import build_snapshot
from apps.triggers.models import EventTrigger


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.triggers.metrics._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_position_pl_fetches_positions_once(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "position_pl", "op": "<", "value": -500},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.metrics.fetch_positions") as fp:
        fq.return_value = {}
        fp.return_value = [
            {"ticker": "SPY", "unrealized_pl": -100.0, "mkt_value": 5000.0},
            {"ticker": "TSLA", "unrealized_pl": -400.0, "mkt_value": 3000.0},
        ]
        snap = build_snapshot([t])

    fp.assert_called_once()
    assert snap["position_pl"] == -500.0


@pytest.mark.django_db
def test_position_pl_pct_computed_from_totals(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "position_pl_pct", "op": "<", "value": -0.05},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.metrics.fetch_positions") as fp:
        fq.return_value = {}
        fp.return_value = [
            {"ticker": "SPY", "unrealized_pl": -500.0, "mkt_value": 5000.0},
        ]
        snap = build_snapshot([t])

    assert snap["position_pl_pct"] == pytest.approx(-0.1)


@pytest.mark.django_db
def test_position_pl_pct_handles_zero_mkt_value(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "position_pl_pct", "op": "<", "value": -0.05},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.metrics.fetch_positions") as fp:
        fq.return_value = {}
        fp.return_value = []  # no positions
        snap = build_snapshot([t])

    assert snap["position_pl_pct"] is None


@pytest.mark.django_db
def test_positions_failure_yields_none_metric(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "position_pl", "op": "<", "value": -500},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.metrics.fetch_positions") as fp:
        fq.return_value = {}
        fp.side_effect = RuntimeError("schwab down")
        snap = build_snapshot([t])

    assert snap["position_pl"] is None
```

- [ ] **Step 10.2: Run tests, expect pass (positions path already implemented in Task 9)**

```bash
docker compose exec web pytest apps/triggers/tests/test_metrics_positions.py -v
```
Expected: 4 passed. If `test_positions_failure_yields_none_metric` fails, it's because the `positions_total_pl = None` default in `build_snapshot` isn't being respected — the current implementation has `positions_total_pl: float | None = None` which is correct. Verify.

- [ ] **Step 10.3: Commit**

```bash
git add backend/apps/triggers/tests/test_metrics_positions.py
git commit -m "test(triggers): metrics positions coverage"
```

---

## Task 11: Cooldown gate service

**Files:**
- Create: `backend/apps/triggers/services/cooldown.py`
- Create: `backend/apps/triggers/tests/test_cooldown.py`

- [ ] **Step 11.1: Verify `freezegun` is available**

```bash
docker compose exec web python -c "import freezegun; print('OK')"
```
(If missing, add to deps and rebuild; `freezegun` was already added during M6 Task 5.)

- [ ] **Step 11.2: Write the failing tests**

`backend/apps/triggers/tests/test_cooldown.py`:
```python
from datetime import timedelta
from unittest.mock import patch

import fakeredis
import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger
from apps.triggers.services.cooldown import cooldown_blocks, mark_fired, mark_rearmed


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.triggers.services.cooldown._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_never_fired_never_blocks(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []},
                                    cooldown_seconds=60)
    assert cooldown_blocks(t) is False


@pytest.mark.django_db
def test_within_time_window_blocks(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []},
                                    cooldown_seconds=60)
    t.last_fired_at = timezone.now() - timedelta(seconds=30)
    t.save()
    assert cooldown_blocks(t) is True


@pytest.mark.django_db
def test_time_elapsed_but_not_rearmed_blocks(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []},
                                    cooldown_seconds=60)
    t.last_fired_at = timezone.now() - timedelta(seconds=120)
    t.save()
    # No re-arm key set → blocked
    assert cooldown_blocks(t) is True


@pytest.mark.django_db
def test_time_elapsed_and_rearmed_passes(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []},
                                    cooldown_seconds=60)
    t.last_fired_at = timezone.now() - timedelta(seconds=120)
    t.save()
    mark_rearmed(t.id)
    assert cooldown_blocks(t) is False


@pytest.mark.django_db
def test_mark_fired_clears_rearmed_flag(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    mark_rearmed(t.id)
    assert fake_redis.exists(f"trigger:armed:{t.id}") == 1
    mark_fired(t.id)
    assert fake_redis.exists(f"trigger:armed:{t.id}") == 0
```

- [ ] **Step 11.3: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_cooldown.py -v
```
Expected: ImportError on `services.cooldown`.

- [ ] **Step 11.4: Write the service**

`backend/apps/triggers/services/cooldown.py`:
```python
"""Cooldown gate: both time-elapsed AND re-armed-on-false must pass."""
from __future__ import annotations

import redis
from django.conf import settings
from django.utils import timezone

from apps.triggers.models import EventTrigger

ARMED_KEY = "trigger:armed:{trigger_id}"
ARMED_TTL_SECONDS = 86400  # 1 day — long enough to survive overnight


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def cooldown_blocks(trigger: EventTrigger) -> bool:
    """True when we should skip firing this trigger on the current tick."""
    if trigger.last_fired_at is None:
        return False
    elapsed = (timezone.now() - trigger.last_fired_at).total_seconds()
    if elapsed < trigger.cooldown_seconds:
        return True
    # Time elapsed → require the re-arm flag (condition went False since last fire)
    return not _redis().exists(ARMED_KEY.format(trigger_id=trigger.id))


def mark_fired(trigger_id: int) -> None:
    """Called when the trigger fires — clears the re-armed flag."""
    _redis().delete(ARMED_KEY.format(trigger_id=trigger_id))


def mark_rearmed(trigger_id: int) -> None:
    """Called when the condition evaluates False — allows next fire once cooldown elapses."""
    _redis().setex(ARMED_KEY.format(trigger_id=trigger_id), ARMED_TTL_SECONDS, "1")
```

- [ ] **Step 11.5: Run tests, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_cooldown.py -v
```
Expected: 5 passed.

- [ ] **Step 11.6: Commit**

```bash
git add backend/apps/triggers/services/cooldown.py backend/apps/triggers/tests/test_cooldown.py
git commit -m "feat(triggers): cooldown gate (time + re-arm)"
```

---

## Task 12: `evaluate_triggers` Celery task

**Files:**
- Create: `backend/apps/triggers/tasks.py`
- Create: `backend/apps/triggers/tests/test_evaluate_triggers_task.py`

- [ ] **Step 12.1: Write the failing test**

`backend/apps/triggers/tests/test_evaluate_triggers_task.py`:
```python
from unittest.mock import patch

import fakeredis
import pytest
from freezegun import freeze_time

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger
from apps.triggers.tasks import evaluate_triggers


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.triggers.metrics._redis", return_value=client), \
         patch("apps.triggers.services.cooldown._redis", return_value=client):
        yield client


@pytest.mark.django_db
@freeze_time("2026-04-18 15:00:00")  # Saturday — market closed
def test_tick_noops_when_market_closed(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(name="r", profile=p,
                                condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0})
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.tasks.fire_trigger") as fire:
        evaluate_triggers()
    fq.assert_not_called()
    fire.delay.assert_not_called()


@pytest.mark.django_db
@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET — market open
def test_tick_enqueues_fire_when_matched(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.tasks.fire_trigger") as fire:
        fq.return_value = {"SPY": {"last": 551.0}}
        evaluate_triggers()
    fire.delay.assert_called_once()
    args, kwargs = fire.delay.call_args
    # First positional is trigger_id, second is matched_values dict
    assert kwargs.get("trigger_id", args[0] if args else None) == t.id


@pytest.mark.django_db
@freeze_time("2026-04-15 14:00:00")
def test_tick_skips_disabled_triggers(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(
        name="r", profile=p, enabled=False,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.tasks.fire_trigger") as fire:
        evaluate_triggers()
    fq.assert_not_called()
    fire.delay.assert_not_called()


@pytest.mark.django_db
@freeze_time("2026-04-15 14:00:00")
def test_tick_marks_rearmed_when_condition_false(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.tasks.fire_trigger") as fire:
        fq.return_value = {"SPY": {"last": 551.0}}
        evaluate_triggers()
    fire.delay.assert_not_called()
    assert fake_redis.exists(f"trigger:armed:{t.id}") == 1


@pytest.mark.django_db
@freeze_time("2026-04-15 14:00:00")
def test_tick_skips_when_cooldown_active(fake_redis):
    from django.utils import timezone as dj_tz
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p, cooldown_seconds=3600,
        last_fired_at=dj_tz.now(),
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    with patch("apps.triggers.metrics.fetch_quotes") as fq, \
         patch("apps.triggers.tasks.fire_trigger") as fire:
        fq.return_value = {"SPY": {"last": 551.0}}
        evaluate_triggers()
    fire.delay.assert_not_called()
```

- [ ] **Step 12.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_evaluate_triggers_task.py -v
```
Expected: ImportError on `apps.triggers.tasks`.

- [ ] **Step 12.3: Write the task**

`backend/apps/triggers/tasks.py`:
```python
"""Celery tasks for the trigger evaluator and fire path."""
from __future__ import annotations

import logging
import time

import structlog
from celery import shared_task

from apps.observer.services.market_hours import is_market_open
from apps.triggers import evaluator, metrics
from apps.triggers.models import EventTrigger
from apps.triggers.services.cooldown import cooldown_blocks, mark_fired, mark_rearmed

logger = structlog.get_logger(__name__)


@shared_task(name="triggers.evaluate_triggers")
def evaluate_triggers() -> dict:
    """Beat-scheduled tick. Fires matching triggers; returns a summary for logs."""
    if not is_market_open():
        logger.debug("trigger.tick.market_closed")
        return {"evaluated": 0, "fires": 0, "skipped": "market_closed"}

    t0 = time.perf_counter()
    triggers = list(
        EventTrigger.objects.filter(enabled=True).select_related("profile"),
    )
    if not triggers:
        return {"evaluated": 0, "fires": 0}

    snapshot = metrics.build_snapshot(triggers)
    fires = 0
    for trigger in triggers:
        try:
            if cooldown_blocks(trigger):
                continue
            matched, values = evaluator.evaluate(trigger.condition, snapshot)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "trigger.evaluate.failed",
                trigger_id=trigger.id, trigger_name=trigger.name, error=str(exc),
            )
            _disable_on_bad_condition(trigger, exc)
            continue

        if not matched:
            mark_rearmed(trigger.id)
            continue
        mark_fired(trigger.id)
        fire_trigger.delay(trigger_id=trigger.id, matched_values=values)
        fires += 1

    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "trigger.tick",
        triggers_evaluated=len(triggers), fires_enqueued=fires,
        duration_ms=duration_ms,
    )
    return {"evaluated": len(triggers), "fires": fires, "duration_ms": duration_ms}


def _disable_on_bad_condition(trigger: EventTrigger, exc: Exception) -> None:
    trigger.enabled = False
    trigger.save(update_fields=["enabled", "updated_at"])
    logger.error(
        "trigger.disabled.invalid_condition",
        trigger_id=trigger.id, error=str(exc),
    )


@shared_task(name="triggers.fire_trigger", autoretry_for=(), max_retries=0)
def fire_trigger(trigger_id: int, matched_values: dict) -> None:
    """Placeholder — fully implemented in Task 13."""
    raise NotImplementedError
```

- [ ] **Step 12.4: Run tests, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_evaluate_triggers_task.py -v
```
Expected: 5 passed.

- [ ] **Step 12.5: Commit**

```bash
git add backend/apps/triggers/tasks.py backend/apps/triggers/tests/test_evaluate_triggers_task.py
git commit -m "feat(triggers): evaluate_triggers beat task (orchestrator)"
```

---

## Task 13: `fire_trigger` Celery task — full implementation

**Files:**
- Modify: `backend/apps/triggers/tasks.py`
- Create: `backend/apps/triggers/tests/test_fire_trigger_task.py`

- [ ] **Step 13.1: Write the failing test**

`backend/apps/triggers/tests/test_fire_trigger_task.py`:
```python
from decimal import Decimal
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from apps.ai.cost import CostCapExceededError
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.triggers.models import EventTrigger, TriggerFiring


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.triggers.tasks._redis", return_value=client):
        yield client


@pytest.fixture
def provider_cfg(db):
    from apps.secrets.models import ProviderConfig
    cfg, _ = ProviderConfig.objects.update_or_create(
        provider="claude",
        defaults={"daily_cost_cap_usd": Decimal("10.00"), "enabled": True},
    )
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


@pytest.mark.django_db
def test_fire_trigger_happy_path(fake_redis, provider_cfg):
    from apps.triggers.tasks import fire_trigger
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="SPY>550", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )

    fake_snap = Snapshot.objects.create(profile=p, includes=["quotes"])
    with patch("apps.triggers.tasks.capture", return_value=fake_snap) as cap, \
         patch("apps.triggers.tasks.serialize_for_ai", return_value="payload"), \
         patch("apps.triggers.tasks.run_ai_on_message") as ai, \
         patch("apps.triggers.tasks.notify") as notify:
        fire_trigger(trigger_id=t.id, matched_values={"price:SPY": 551.0})

    cap.assert_called_once()
    firing = TriggerFiring.objects.get(trigger=t)
    assert firing.snapshot_id == fake_snap.id
    assert firing.thread is not None
    assert firing.cost_capped is False
    ai.delay.assert_called_once()
    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs["kind"] == "trigger"
    assert kwargs["title"] == "SPY>550"
    assert kwargs["link"] == f"/threads/{firing.thread_id}"
    t.refresh_from_db()
    assert t.last_fired_at is not None


@pytest.mark.django_db
def test_fire_trigger_cost_capped_skips_ai(fake_redis, provider_cfg):
    from apps.triggers.tasks import fire_trigger
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    fake_snap = Snapshot.objects.create(profile=p, includes=["quotes"])

    def cap_exceeded(*a, **kw):
        raise CostCapExceededError("over cap")

    with patch("apps.triggers.tasks.capture", return_value=fake_snap), \
         patch("apps.triggers.tasks.check_daily_cap", side_effect=cap_exceeded), \
         patch("apps.triggers.tasks.run_ai_on_message") as ai, \
         patch("apps.triggers.tasks.notify") as notify:
        fire_trigger(trigger_id=t.id, matched_values={"price:SPY": 100.0})

    firing = TriggerFiring.objects.get(trigger=t)
    assert firing.cost_capped is True
    assert firing.thread is None
    ai.delay.assert_not_called()
    assert notify.call_args.kwargs["kind"] == "cost_limit"


@pytest.mark.django_db
def test_fire_trigger_capture_failure_notifies_error(fake_redis, provider_cfg):
    from apps.triggers.tasks import fire_trigger
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )

    with patch("apps.triggers.tasks.capture", side_effect=RuntimeError("schwab 503")), \
         patch("apps.triggers.tasks.run_ai_on_message") as ai, \
         patch("apps.triggers.tasks.notify") as notify:
        fire_trigger(trigger_id=t.id, matched_values={"price:SPY": 100.0})

    firing = TriggerFiring.objects.get(trigger=t)
    assert firing.snapshot is None
    assert firing.thread is None
    ai.delay.assert_not_called()
    assert notify.call_args.kwargs["kind"] == "error"


@pytest.mark.django_db
def test_fire_trigger_idempotent_via_redis_lock(fake_redis, provider_cfg):
    """Second concurrent invocation should no-op while the first holds the lock."""
    from apps.triggers.tasks import fire_trigger
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    # Seed lock → second call should return without creating a firing
    fake_redis.set(f"trigger:fire:{t.id}", "1", ex=60)

    fake_snap = Snapshot.objects.create(profile=p, includes=[])
    with patch("apps.triggers.tasks.capture", return_value=fake_snap), \
         patch("apps.triggers.tasks.run_ai_on_message"), \
         patch("apps.triggers.tasks.notify"):
        fire_trigger(trigger_id=t.id, matched_values={"price:SPY": 100.0})

    assert TriggerFiring.objects.filter(trigger=t).count() == 0
```

- [ ] **Step 13.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_fire_trigger_task.py -v
```
Expected: NotImplementedError or ImportError.

- [ ] **Step 13.3: Replace the `fire_trigger` stub with the full implementation**

In `backend/apps/triggers/tasks.py`, replace imports and the `fire_trigger` function:
```python
"""Celery tasks for the trigger evaluator and fire path."""
from __future__ import annotations

import time

import redis
import structlog
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.ai.cost import CostCapExceededError, check_daily_cap
from apps.observer.services.market_hours import is_market_open
from apps.observer.services.notifications import notify
from apps.secrets.models import ProviderConfig
from apps.snapshots.serializer import serialize_for_ai
from apps.snapshots.services import capture
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message
from apps.triggers import evaluator, metrics
from apps.triggers.models import EventTrigger, TriggerFiring
from apps.triggers.services.cooldown import cooldown_blocks, mark_fired, mark_rearmed
from apps.triggers.services.describe import describe

logger = structlog.get_logger(__name__)

FIRE_LOCK_KEY = "trigger:fire:{trigger_id}"
FIRE_LOCK_TTL = 60


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


# evaluate_triggers definition kept from Task 12 above this line.
# (Copy it back into the file unchanged — do NOT overwrite it.)


@shared_task(name="triggers.fire_trigger", autoretry_for=(), max_retries=0)
def fire_trigger(trigger_id: int, matched_values: dict) -> None:
    """Run the full fire path for one trigger. Never retried (would double-fire)."""
    r = _redis()
    lock_key = FIRE_LOCK_KEY.format(trigger_id=trigger_id)
    # SET NX with TTL acts as a mutex. If the key already exists, skip.
    if not r.set(lock_key, "1", nx=True, ex=FIRE_LOCK_TTL):
        logger.warning("trigger.fire.already_running", trigger_id=trigger_id)
        return
    try:
        _do_fire(trigger_id=trigger_id, matched_values=matched_values)
    finally:
        r.delete(lock_key)


def _do_fire(*, trigger_id: int, matched_values: dict) -> None:
    trigger = EventTrigger.objects.select_related("profile").get(id=trigger_id)
    firing = TriggerFiring.objects.create(
        trigger=trigger, matched_values=matched_values,
    )
    trigger.last_fired_at = timezone.now()
    trigger.save(update_fields=["last_fired_at", "updated_at"])

    try:
        snap = capture(
            profile=trigger.profile,
            objective=f"Triggered: {trigger.name}",
            includes=trigger.profile.default_includes,
            source="trigger",
        )
    except Exception as exc:
        logger.error(
            "trigger.fire.capture_failed",
            trigger_id=trigger.id, error=str(exc),
        )
        notify(
            user_id=None, kind="error",
            title=f"{trigger.name} fired — snapshot failed",
            body=str(exc),
            link=f"/triggers/{trigger.id}",
        )
        return

    firing.snapshot = snap
    firing.save(update_fields=["snapshot"])

    # Cost-cap check: expensive part is the AI run, not the snapshot.
    provider_name = trigger.profile.default_provider
    try:
        cfg = ProviderConfig.objects.get(provider=provider_name)
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
    except ProviderConfig.DoesNotExist:
        logger.warning(
            "trigger.fire.no_provider_config",
            trigger_id=trigger.id, provider=provider_name,
        )
        # No config → no cap enforcement; proceed to AI run.
    except CostCapExceededError as exc:
        firing.cost_capped = True
        firing.save(update_fields=["cost_capped"])
        notify(
            user_id=None, kind="cost_limit",
            title=f"{trigger.name} fired — AI skipped (cap hit)",
            body=f"{describe(matched_values)} · {exc}",
            link=f"/triggers/{trigger.id}",
        )
        logger.info(
            "trigger.fire.ai_skipped_cost_capped",
            trigger_id=trigger.id, provider=provider_name,
        )
        return

    thread = Thread.objects.create(
        kind="chat", profile=trigger.profile, pinned_snapshot=snap,
        title=f"{trigger.name} fired at {timezone.localtime():%H:%M}",
    )
    firing.thread = thread
    firing.save(update_fields=["thread"])

    user_msg = Message.objects.create(
        thread=thread, role="user",
        content={"text": serialize_for_ai(snap)},
        snapshot_ref=snap, status="done",
    )
    run_ai_on_message.delay(thread_id=thread.id, user_message_id=user_msg.id)

    notify(
        user_id=None, kind="trigger",
        title=trigger.name,
        body=describe(matched_values),
        link=f"/threads/{thread.id}",
    )
    logger.info(
        "trigger.fired",
        trigger_id=trigger.id, trigger_name=trigger.name,
        profile_id=trigger.profile_id,
        snapshot_id=snap.id, thread_id=thread.id,
        cost_capped=False,
    )
```

**Important:** preserve the `evaluate_triggers` function from Task 12 when rewriting this file. Paste it back between the imports and the `fire_trigger` definition exactly as it was.

- [ ] **Step 13.4: Run both task test files**

```bash
docker compose exec web pytest apps/triggers/tests/test_fire_trigger_task.py apps/triggers/tests/test_evaluate_triggers_task.py -v
```
Expected: all green (4 fire + 5 evaluate).

- [ ] **Step 13.5: Commit**

```bash
git add backend/apps/triggers/tasks.py backend/apps/triggers/tests/test_fire_trigger_task.py
git commit -m "feat(triggers): fire_trigger task (snapshot + AI + notify + cost-cap)"
```

---

## Task 14: Celery-beat seed for `evaluate_triggers`

**Files:**
- Create: `backend/apps/triggers/migrations/0003_seed_beat_schedule.py`
- Modify: `backend/config/settings/base.py` (add `TRIGGER_TICK_SECONDS` env)

- [ ] **Step 14.1: Add the env setting**

In `backend/config/settings/base.py`, near `OBSERVER_BEAT_TIMEZONE`, add:
```python
TRIGGER_TICK_SECONDS = env.int("TRIGGER_TICK_SECONDS", default=10)
```

- [ ] **Step 14.2: Write the data migration**

`backend/apps/triggers/migrations/0003_seed_beat_schedule.py`:
```python
"""Seed the evaluate_triggers PeriodicTask on first migrate."""
import json

from django.conf import settings
from django.db import migrations


def _tick_seconds():
    return getattr(settings, "TRIGGER_TICK_SECONDS", 10)


def seed_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=_tick_seconds(), period="seconds",
    )
    PeriodicTask.objects.update_or_create(
        name="triggers.evaluate_triggers",
        defaults={
            "task": "triggers.evaluate_triggers",
            "interval": interval,
            "enabled": True,
            "kwargs": json.dumps({}),
        },
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="triggers.evaluate_triggers").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("triggers", "0002_triggerfiring"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_periodic_task, reverse_code=remove_periodic_task),
    ]
```

- [ ] **Step 14.3: Apply the migration**

```bash
docker compose exec web python manage.py migrate triggers
```

- [ ] **Step 14.4: Verify the PeriodicTask exists**

```bash
docker compose exec web python manage.py shell -c "
from django_celery_beat.models import PeriodicTask
print(PeriodicTask.objects.filter(name='triggers.evaluate_triggers').values('name', 'task', 'enabled', 'interval__every'))
"
```
Expected: `[{'name': 'triggers.evaluate_triggers', 'task': 'triggers.evaluate_triggers', 'enabled': True, 'interval__every': 10}]`.

- [ ] **Step 14.5: Commit**

```bash
git add backend/apps/triggers/migrations/0003_seed_beat_schedule.py backend/config/settings/base.py
git commit -m "feat(triggers): seed evaluate_triggers beat schedule (10s interval)"
```

---

## Task 15: DRF serializers with DSL validation

**Files:**
- Create: `backend/apps/triggers/serializers.py`
- Create: `backend/apps/triggers/tests/test_serializers.py`

- [ ] **Step 15.1: Write the failing tests**

`backend/apps/triggers/tests/test_serializers.py`:
```python
import pytest

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger, TriggerFiring
from apps.triggers.serializers import (
    EventTriggerSerializer, TriggerFiringSerializer,
)


@pytest.mark.django_db
def test_event_trigger_serializer_roundtrip():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    data = EventTriggerSerializer(t).data
    assert data["name"] == "r"
    assert data["profile"] == p.id
    assert data["condition"] == {"metric": "price", "ticker": "SPY", "op": ">", "value": 550}
    assert data["enabled"] is True
    assert data["firings_count"] == 0


@pytest.mark.django_db
def test_event_trigger_serializer_validates_dsl_on_create():
    p = TradingProfile.objects.create(name="P", style="x")
    ser = EventTriggerSerializer(data={
        "name": "bad", "profile": p.id,
        "condition": {"metric": "nope", "op": ">", "value": 1},
        "cooldown_seconds": 300,
        "enabled": True,
    })
    assert ser.is_valid() is False
    assert "condition" in ser.errors


@pytest.mark.django_db
def test_event_trigger_serializer_accepts_valid_dsl():
    p = TradingProfile.objects.create(name="P", style="x")
    ser = EventTriggerSerializer(data={
        "name": "ok", "profile": p.id,
        "condition": {"all": [
            {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        ]},
        "cooldown_seconds": 600,
        "enabled": True,
    })
    assert ser.is_valid(), ser.errors
    obj = ser.save()
    assert obj.name == "ok"


@pytest.mark.django_db
def test_firings_count_annotation_reflects_rows():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    TriggerFiring.objects.create(trigger=t, matched_values={})
    TriggerFiring.objects.create(trigger=t, matched_values={})

    # Simulate queryset annotation used by ViewSet
    from django.db.models import Count
    qs = EventTrigger.objects.annotate(firings_count=Count("firings"))
    data = EventTriggerSerializer(qs.get(id=t.id)).data
    assert data["firings_count"] == 2


@pytest.mark.django_db
def test_trigger_firing_serializer_shape():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="SPY>550", profile=p, condition={"all": []})
    f = TriggerFiring.objects.create(
        trigger=t, matched_values={"price:SPY": 551.2}, cost_capped=False,
    )
    data = TriggerFiringSerializer(f).data
    assert data["trigger_id"] == t.id
    assert data["trigger_name"] == "SPY>550"
    assert data["matched_values"] == {"price:SPY": 551.2}
    assert data["snapshot_id"] is None
    assert data["thread_id"] is None
    assert data["cost_capped"] is False
    assert "fired_at" in data
```

- [ ] **Step 15.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_serializers.py -v
```
Expected: ImportError on `apps.triggers.serializers`.

- [ ] **Step 15.3: Write the serializers**

`backend/apps/triggers/serializers.py`:
```python
"""DRF serializers for EventTrigger + TriggerFiring."""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.triggers.dsl import validate_condition
from apps.triggers.models import EventTrigger, TriggerFiring


class EventTriggerSerializer(serializers.ModelSerializer):
    firings_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = EventTrigger
        fields = [
            "id", "name", "profile", "condition", "cooldown_seconds",
            "enabled", "last_fired_at", "firings_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "last_fired_at", "created_at", "updated_at", "firings_count"]

    def validate_condition(self, value):
        try:
            validate_condition(value)
        except DjangoValidationError as exc:
            # DRF expects its own ValidationError
            raise serializers.ValidationError(str(exc)) from exc
        return value


class TriggerFiringSerializer(serializers.ModelSerializer):
    trigger_id = serializers.IntegerField(source="trigger.id", read_only=True)
    trigger_name = serializers.CharField(source="trigger.name", read_only=True)
    snapshot_id = serializers.IntegerField(source="snapshot_id", read_only=True, allow_null=True)
    thread_id = serializers.IntegerField(source="thread_id", read_only=True, allow_null=True)

    class Meta:
        model = TriggerFiring
        fields = [
            "id", "trigger_id", "trigger_name", "fired_at", "matched_values",
            "snapshot_id", "thread_id", "cost_capped",
        ]
        read_only_fields = fields
```

- [ ] **Step 15.4: Run tests, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_serializers.py -v
```
Expected: 5 passed.

- [ ] **Step 15.5: Commit**

```bash
git add backend/apps/triggers/serializers.py backend/apps/triggers/tests/test_serializers.py
git commit -m "feat(triggers): DRF serializers with DSL validation"
```

---

## Task 16: ViewSet CRUD + URL wiring

**Files:**
- Create: `backend/apps/triggers/views.py`
- Create: `backend/apps/triggers/urls.py`
- Modify: `backend/config/urls.py` (include triggers URLs)
- Create: `backend/apps/triggers/tests/test_endpoints_crud.py`

- [ ] **Step 16.1: Write the failing test**

`backend/apps/triggers/tests/test_endpoints_crud.py`:
```python
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_list_triggers(api):
    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(name="r1", profile=p, condition={"all": []})
    EventTrigger.objects.create(name="r2", profile=p, condition={"any": []})
    resp = api.get("/api/triggers/")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # firings_count annotation present
    assert all("firings_count" in row for row in body)


@pytest.mark.django_db
def test_create_trigger_validates_dsl(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp = api.post("/api/triggers/", {
        "name": "bad", "profile": p.id,
        "condition": {"metric": "nope", "op": ">", "value": 1},
        "cooldown_seconds": 300, "enabled": True,
    }, format="json")
    assert resp.status_code == 400
    assert "condition" in resp.json()


@pytest.mark.django_db
def test_create_trigger_ok(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp = api.post("/api/triggers/", {
        "name": "SPY", "profile": p.id,
        "condition": {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        "cooldown_seconds": 1800, "enabled": True,
    }, format="json")
    assert resp.status_code == 201
    assert EventTrigger.objects.filter(name="SPY").exists()


@pytest.mark.django_db
def test_patch_toggle_enabled(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    resp = api.patch(f"/api/triggers/{t.id}/", {"enabled": False}, format="json")
    assert resp.status_code == 200
    t.refresh_from_db()
    assert t.enabled is False


@pytest.mark.django_db
def test_delete_cascades_firings(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    from apps.triggers.models import TriggerFiring
    TriggerFiring.objects.create(trigger=t, matched_values={})
    resp = api.delete(f"/api/triggers/{t.id}/")
    assert resp.status_code == 204
    assert TriggerFiring.objects.count() == 0
```

- [ ] **Step 16.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_endpoints_crud.py -v
```
Expected: 404s or module import errors.

- [ ] **Step 16.3: Write the ViewSet**

`backend/apps/triggers/views.py`:
```python
"""Triggers HTTP endpoints."""
from __future__ import annotations

from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.triggers.models import EventTrigger, TriggerFiring
from apps.triggers.serializers import EventTriggerSerializer, TriggerFiringSerializer


class EventTriggerViewSet(viewsets.ModelViewSet):
    serializer_class = EventTriggerSerializer

    def get_queryset(self):
        return (
            EventTrigger.objects.select_related("profile")
            .annotate(firings_count=Count("firings"))
            .order_by("-created_at")
        )
```

- [ ] **Step 16.4: Write the URL router**

`backend/apps/triggers/urls.py`:
```python
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("", views.EventTriggerViewSet, basename="event-trigger")

urlpatterns = [*router.urls]
```

- [ ] **Step 16.5: Wire into the project URLs**

Read `backend/config/urls.py` and insert `path("api/triggers/", include("apps.triggers.urls")),` **before** the generic `/api/` includes — place it right after the `observer` line to preserve the ordering convention (CLAUDE.md: specific prefixes before generic `/api/` includes).

- [ ] **Step 16.6: Run tests, expect pass**

```bash
docker compose exec web pytest apps/triggers/tests/test_endpoints_crud.py -v
```
Expected: 5 passed.

- [ ] **Step 16.7: Commit**

```bash
git add backend/apps/triggers/views.py backend/apps/triggers/urls.py backend/config/urls.py backend/apps/triggers/tests/test_endpoints_crud.py
git commit -m "feat(triggers): CRUD ViewSet + URL wiring"
```

---

## Task 17: `fire` + `evaluate` custom actions

**Files:**
- Modify: `backend/apps/triggers/views.py`
- Create: `backend/apps/triggers/tests/test_endpoints_actions.py`

- [ ] **Step 17.1: Write the failing tests**

`backend/apps/triggers/tests/test_endpoints_actions.py`:
```python
from unittest.mock import patch

import fakeredis
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.triggers.metrics._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_fire_now_enqueues_fire_trigger(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    with patch("apps.triggers.views.fire_trigger") as ft:
        ft.delay.return_value.id = "task-123"
        resp = api.post(f"/api/triggers/{t.id}/fire/")
    assert resp.status_code == 202
    ft.delay.assert_called_once()
    kwargs = ft.delay.call_args.kwargs
    assert kwargs["trigger_id"] == t.id


@pytest.mark.django_db
def test_fire_now_rejects_disabled(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p, enabled=False,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    with patch("apps.triggers.views.fire_trigger") as ft:
        resp = api.post(f"/api/triggers/{t.id}/fire/")
    assert resp.status_code == 400
    ft.delay.assert_not_called()


@pytest.mark.django_db
def test_evaluate_with_condition_body(fake_redis, api):
    p = TradingProfile.objects.create(name="P", style="x")
    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}}
        resp = api.post("/api/triggers/evaluate/", {
            "profile": p.id,
            "condition": {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        }, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is True
    assert body["values"]["price:SPY"] == 551.0
    assert body["missing"] == []


@pytest.mark.django_db
def test_evaluate_rejects_invalid_dsl(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp = api.post("/api/triggers/evaluate/", {
        "profile": p.id, "condition": {"metric": "nope", "op": ">", "value": 1},
    }, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_evaluate_reports_missing_metric_keys(fake_redis, api):
    p = TradingProfile.objects.create(name="P", style="x")
    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {}  # Schwab returned nothing
        resp = api.post("/api/triggers/evaluate/", {
            "profile": p.id,
            "condition": {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        }, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is False
    assert "price:SPY" in body["missing"]
```

- [ ] **Step 17.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_endpoints_actions.py -v
```
Expected: 404s.

- [ ] **Step 17.3: Add the actions to the ViewSet**

In `backend/apps/triggers/views.py`, replace the file with:
```python
"""Triggers HTTP endpoints."""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.triggers import evaluator, metrics
from apps.triggers.dsl import validate_condition
from apps.triggers.models import EventTrigger, TriggerFiring
from apps.triggers.serializers import EventTriggerSerializer, TriggerFiringSerializer
from apps.triggers.tasks import fire_trigger


class EventTriggerViewSet(viewsets.ModelViewSet):
    serializer_class = EventTriggerSerializer

    def get_queryset(self):
        return (
            EventTrigger.objects.select_related("profile")
            .annotate(firings_count=Count("firings"))
            .order_by("-created_at")
        )

    @action(detail=True, methods=["post"])
    def fire(self, request: Request, pk: str | None = None) -> Response:
        trigger = self.get_object()
        if not trigger.enabled:
            return Response(
                {"code": "disabled", "message": "Enable the trigger before firing manually."},
                status=400,
            )
        task = fire_trigger.delay(trigger_id=trigger.id, matched_values={"source": "manual"})
        return Response({"task_id": str(task.id)}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"])
    def evaluate(self, request: Request) -> Response:
        """Dry-run: run the evaluator against a condition without firing.

        Body: {condition: <DSL>, profile?: <id>} OR {trigger_id: <id>}.
        Returns {matched, values, missing}.
        """
        data = request.data
        if "trigger_id" in data:
            try:
                trigger = EventTrigger.objects.get(id=data["trigger_id"])
            except EventTrigger.DoesNotExist:
                return Response({"code": "not_found"}, status=404)
            condition = trigger.condition
        else:
            condition = data.get("condition")
            if condition is None:
                return Response({"code": "missing_condition"}, status=400)
            try:
                validate_condition(condition)
            except DjangoValidationError as exc:
                return Response({"code": "invalid_condition", "message": str(exc)}, status=400)
            trigger = _synthetic_trigger(condition, profile_id=data.get("profile"))

        snapshot = metrics.build_snapshot([trigger])
        matched, values = evaluator.evaluate(condition, snapshot)
        missing = [k for k, v in values.items() if v is None]
        return Response({"matched": matched, "values": values, "missing": missing})


def _synthetic_trigger(condition: dict, *, profile_id: int | None) -> EventTrigger:
    """A detached EventTrigger used only for metrics.build_snapshot() leaf-walking.

    Not saved to the DB. Used by the `evaluate` action when the caller passes a
    raw DSL body rather than a saved trigger id.
    """
    t = EventTrigger(name="__dryrun__", profile_id=profile_id or 0, condition=condition)
    return t
```

- [ ] **Step 17.4: Run tests**

```bash
docker compose exec web pytest apps/triggers/tests/test_endpoints_actions.py -v
```
Expected: 5 passed.

- [ ] **Step 17.5: Commit**

```bash
git add backend/apps/triggers/views.py backend/apps/triggers/tests/test_endpoints_actions.py
git commit -m "feat(triggers): /fire/ and /evaluate/ ViewSet actions"
```

---

## Task 18: Per-trigger `firings` list + `firings/recent/` endpoint

**Files:**
- Modify: `backend/apps/triggers/views.py`
- Create: `backend/apps/triggers/tests/test_firings_endpoints.py`

- [ ] **Step 18.1: Write the failing tests**

`backend/apps/triggers/tests/test_firings_endpoints.py`:
```python
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.threads.models import Thread
from apps.triggers.models import EventTrigger, TriggerFiring


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_firings_list_for_trigger(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    TriggerFiring.objects.create(trigger=t, matched_values={"price:SPY": 551.0})
    TriggerFiring.objects.create(trigger=t, matched_values={"price:SPY": 552.0})
    resp = api.get(f"/api/triggers/{t.id}/firings/")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 2
    # Newest first
    assert body["results"][0]["matched_values"] == {"price:SPY": 552.0}


@pytest.mark.django_db
def test_firings_recent_global(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t1 = EventTrigger.objects.create(name="r1", profile=p, condition={"all": []})
    t2 = EventTrigger.objects.create(name="r2", profile=p, condition={"all": []})
    TriggerFiring.objects.create(trigger=t1, matched_values={"vix": 25.0})
    TriggerFiring.objects.create(trigger=t2, matched_values={"price:SPY": 550.0})

    resp = api.get("/api/triggers/firings/recent/?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # trigger_name surfaced from relation
    names = {row["trigger_name"] for row in body}
    assert names == {"r1", "r2"}


@pytest.mark.django_db
def test_firings_recent_respects_limit(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    for _ in range(7):
        TriggerFiring.objects.create(trigger=t, matched_values={})

    resp = api.get("/api/triggers/firings/recent/?limit=3")
    body = resp.json()
    assert len(body) == 3
```

- [ ] **Step 18.2: Run tests, expect failure**

```bash
docker compose exec web pytest apps/triggers/tests/test_firings_endpoints.py -v
```
Expected: 404s.

- [ ] **Step 18.3: Add the endpoints**

In `backend/apps/triggers/views.py`, add these actions inside `EventTriggerViewSet`:
```python
    @action(detail=True, methods=["get"])
    def firings(self, request: Request, pk: str | None = None) -> Response:
        trigger = self.get_object()
        qs = trigger.firings.select_related("snapshot", "thread").order_by("-fired_at")
        try:
            page = max(1, int(request.query_params.get("page", "1")))
            size = max(1, min(50, int(request.query_params.get("size", "20"))))
        except ValueError:
            page, size = 1, 20
        total = qs.count()
        start = (page - 1) * size
        rows = qs[start:start + size]
        return Response({
            "results": TriggerFiringSerializer(rows, many=True).data,
            "count": total,
            "page": page, "size": size,
        })

    @action(detail=False, methods=["get"], url_path="firings/recent")
    def firings_recent(self, request: Request) -> Response:
        try:
            limit = max(1, min(20, int(request.query_params.get("limit", "5"))))
        except ValueError:
            limit = 5
        qs = (
            TriggerFiring.objects
            .select_related("trigger", "snapshot", "thread")
            .order_by("-fired_at")[:limit]
        )
        return Response(TriggerFiringSerializer(qs, many=True).data)
```

- [ ] **Step 18.4: Run tests**

```bash
docker compose exec web pytest apps/triggers/tests/test_firings_endpoints.py -v
```
Expected: 3 passed.

- [ ] **Step 18.5: Full backend green-check**

```bash
docker compose exec web pytest apps/triggers/ -v
```
Expected: all tests pass. Record the count.

- [ ] **Step 18.6: Commit**

```bash
git add backend/apps/triggers/views.py backend/apps/triggers/tests/test_firings_endpoints.py
git commit -m "feat(triggers): per-trigger firings list + global recent-firings"
```

---

## Task 19: Frontend API client (`src/api/triggers.ts`)

**Files:**
- Create: `frontend/src/api/triggers.ts`
- Create: `frontend/src/__tests__/api.triggers.test.ts`

- [ ] **Step 19.1: Write the failing test**

`frontend/src/__tests__/api.triggers.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  fetchTriggers, createTrigger, updateTrigger, deleteTrigger,
  fireTriggerNow, evaluateTrigger, fetchFirings, fetchRecentFirings,
  type Condition,
} from "../api/triggers";

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
  ) as never;
});

describe("triggers api", () => {
  it("fetchTriggers hits /api/triggers/", async () => {
    await fetchTriggers();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/triggers/"),
      expect.any(Object),
    );
  });

  it("createTrigger POSTs the body", async () => {
    const cond: Condition = { metric: "price", ticker: "SPY", op: ">", value: 550 };
    await createTrigger({ name: "r", profile: 1, condition: cond, cooldown_seconds: 1800, enabled: true });
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body).name).toBe("r");
  });

  it("updateTrigger PATCHes /api/triggers/<id>/", async () => {
    await updateTrigger(42, { enabled: false });
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/42/");
    expect(call[1].method).toBe("PATCH");
  });

  it("deleteTrigger DELETEs", async () => {
    await deleteTrigger(42);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[1].method).toBe("DELETE");
  });

  it("fireTriggerNow hits /fire/", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true, status: 202, json: () => Promise.resolve({ task_id: "t" }),
    })) as never;
    await fireTriggerNow(42);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/42/fire/");
  });

  it("evaluateTrigger POSTs to /evaluate/", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true, status: 200, json: () => Promise.resolve({ matched: true, values: {}, missing: [] }),
    })) as never;
    await evaluateTrigger({ condition: { metric: "vix", op: ">", value: 20 } });
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/evaluate/");
  });

  it("fetchFirings hits /api/triggers/<id>/firings/", async () => {
    await fetchFirings(42);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/42/firings/");
  });

  it("fetchRecentFirings hits /api/triggers/firings/recent/", async () => {
    await fetchRecentFirings(5);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/firings/recent/");
    expect(call[0]).toContain("limit=5");
  });
});
```

- [ ] **Step 19.2: Run test, expect failure**

```bash
docker compose exec frontend npx vitest run src/__tests__/api.triggers.test.ts
```
Expected: module resolution failure.

- [ ] **Step 19.3: Write the API client**

`frontend/src/api/triggers.ts`:
```typescript
import { apiGet, apiPost, apiPatch, apiDelete } from "./client";

export type Op =
  | ">" | ">=" | "<" | "<=" | "=="
  | "crosses_above" | "crosses_below";

export type Metric =
  | "price" | "pct_change" | "vix" | "position_pl" | "position_pl_pct";

export type Window = "1m" | "5m" | "15m" | "1h" | "1d";

export type Leaf = {
  metric: Metric;
  ticker?: string;
  op: Op;
  value: number;
  window?: Window;
};

export type Condition =
  | Leaf
  | { all: Condition[] }
  | { any: Condition[] }
  | { not: Condition };

export type EventTrigger = {
  id: number;
  name: string;
  profile: number;
  condition: Condition;
  cooldown_seconds: number;
  enabled: boolean;
  last_fired_at: string | null;
  firings_count: number;
  created_at: string;
  updated_at: string;
};

export type Firing = {
  id: number;
  trigger_id: number;
  trigger_name: string;
  fired_at: string;
  matched_values: Record<string, number | null>;
  snapshot_id: number | null;
  thread_id: number | null;
  cost_capped: boolean;
};

export type EvaluateResult = {
  matched: boolean;
  values: Record<string, number | null>;
  missing: string[];
};

export const fetchTriggers = () =>
  apiGet<EventTrigger[]>("/api/triggers/");

export const createTrigger = (
  body: Pick<EventTrigger, "name" | "profile" | "condition" | "cooldown_seconds" | "enabled">,
) => apiPost<EventTrigger>("/api/triggers/", body);

export const updateTrigger = (id: number, body: Partial<EventTrigger>) =>
  apiPatch<EventTrigger>(`/api/triggers/${id}/`, body);

export const deleteTrigger = (id: number) =>
  apiDelete(`/api/triggers/${id}/`);

export const fireTriggerNow = (id: number) =>
  apiPost<{ task_id: string }>(`/api/triggers/${id}/fire/`);

export const evaluateTrigger = (
  body: { condition: Condition; profile?: number } | { trigger_id: number },
) => apiPost<EvaluateResult>("/api/triggers/evaluate/", body);

export const fetchFirings = (triggerId: number, page = 1, size = 20) =>
  apiGet<{ results: Firing[]; count: number; page: number; size: number }>(
    `/api/triggers/${triggerId}/firings/?page=${page}&size=${size}`,
  );

export const fetchRecentFirings = (limit = 5) =>
  apiGet<Firing[]>(`/api/triggers/firings/recent/?limit=${limit}`);
```

- [ ] **Step 19.4: Run tests, expect pass**

```bash
docker compose exec frontend npx vitest run src/__tests__/api.triggers.test.ts
```
Expected: 8 passed.

- [ ] **Step 19.5: Commit**

```bash
git add frontend/src/api/triggers.ts frontend/src/__tests__/api.triggers.test.ts
git commit -m "feat(frontend): triggers API client"
```

---

## Task 20: Natural-language describer (`src/lib/triggers/describe.ts`)

**Files:**
- Create: `frontend/src/lib/triggers/describe.ts`
- Create: `frontend/src/__tests__/describeTrigger.test.ts`

- [ ] **Step 20.1: Write the failing tests**

`frontend/src/__tests__/describeTrigger.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { describeLeaf, describeCondition } from "../lib/triggers/describe";
import type { Condition, Leaf } from "../api/triggers";

describe("describeLeaf", () => {
  it("formats price > 550 as 'price of SPY is greater than 550'", () => {
    const leaf: Leaf = { metric: "price", ticker: "SPY", op: ">", value: 550 };
    expect(describeLeaf(leaf)).toBe("price of SPY is greater than 550");
  });

  it("formats pct_change with window", () => {
    const leaf: Leaf = { metric: "pct_change", ticker: "NVDA", op: ">=", value: 0.01, window: "5m" };
    expect(describeLeaf(leaf)).toBe("NVDA moved ≥1% over 5m");
  });

  it("formats vix with implied ticker", () => {
    expect(describeLeaf({ metric: "vix", op: ">", value: 30 }))
      .toBe("VIX is greater than 30");
  });

  it("formats position_pl", () => {
    expect(describeLeaf({ metric: "position_pl", op: "<", value: -500 }))
      .toBe("portfolio unrealized P/L is less than -500");
  });

  it("formats position_pl_pct", () => {
    expect(describeLeaf({ metric: "position_pl_pct", op: "<=", value: -0.05 }))
      .toBe("portfolio is down ≥5%");
  });

  it("formats crosses_above", () => {
    expect(describeLeaf({ metric: "price", ticker: "SPY", op: "crosses_above", value: 550 }))
      .toBe("price of SPY crosses above 550");
  });

  it("formats crosses_below", () => {
    expect(describeLeaf({ metric: "price", ticker: "SPY", op: "crosses_below", value: 550 }))
      .toBe("price of SPY crosses below 550");
  });
});

describe("describeCondition", () => {
  it("single leaf passes through", () => {
    const c: Condition = { metric: "price", ticker: "SPY", op: ">", value: 550 };
    expect(describeCondition(c)).toBe("price of SPY is greater than 550");
  });

  it("all group joined with AND", () => {
    const c: Condition = {
      all: [
        { metric: "price", ticker: "SPY", op: ">", value: 550 },
        { metric: "vix", op: ">", value: 20 },
      ],
    };
    expect(describeCondition(c)).toBe(
      "price of SPY is greater than 550 AND VIX is greater than 20",
    );
  });

  it("any group joined with OR", () => {
    const c: Condition = {
      any: [
        { metric: "price", ticker: "SPY", op: ">", value: 550 },
        { metric: "price", ticker: "QQQ", op: ">", value: 480 },
      ],
    };
    expect(describeCondition(c)).toBe(
      "price of SPY is greater than 550 OR price of QQQ is greater than 480",
    );
  });

  it("not wraps leaf with NOT", () => {
    const c: Condition = { not: { metric: "vix", op: ">", value: 30 } };
    expect(describeCondition(c)).toBe("NOT (VIX is greater than 30)");
  });
});
```

- [ ] **Step 20.2: Write the module**

`frontend/src/lib/triggers/describe.ts`:
```typescript
import type { Condition, Leaf, Metric, Op } from "@/api/triggers";

const OP_WORDS: Record<Op, string> = {
  ">": "is greater than",
  ">=": "is greater than or equal to",
  "<": "is less than",
  "<=": "is less than or equal to",
  "==": "equals",
  crosses_above: "crosses above",
  crosses_below: "crosses below",
};

function pctLabel(value: number, dir: ">=" | "<=" | ">" | "<" | "=="): string {
  const pct = Math.abs(value * 100).toFixed(pctPrecision(value));
  const sign = dir === ">=" || dir === ">" ? "≥" : dir === "<=" || dir === "<" ? "≥" : "=";
  return `${sign}${pct}%`;
}

function pctPrecision(value: number): number {
  return Math.abs(value) < 0.01 ? 2 : 0;
}

export function describeLeaf(leaf: Leaf): string {
  const { metric, op, value, ticker, window } = leaf;

  if (metric === "pct_change") {
    // "NVDA moved ≥1% over 5m"
    return `${ticker} moved ${pctLabel(value, op as ">=" | "<=" | ">" | "<" | "==")} over ${window}`;
  }

  if (metric === "position_pl_pct") {
    // "portfolio is down ≥5%" / "portfolio is up ≥5%"
    const verb = value < 0 ? "down" : "up";
    const pct = Math.abs(value * 100).toFixed(pctPrecision(value));
    return `portfolio is ${verb} ≥${pct}%`;
  }

  if (metric === "position_pl") {
    return `portfolio unrealized P/L ${OP_WORDS[op]} ${value}`;
  }

  if (metric === "vix") {
    return `VIX ${OP_WORDS[op]} ${value}`;
  }

  // price
  return `${metric} of ${ticker} ${OP_WORDS[op]} ${value}`;
}

export function describeCondition(node: Condition): string {
  if ("all" in node) {
    return node.all.map(describeCondition).join(" AND ");
  }
  if ("any" in node) {
    return node.any.map(describeCondition).join(" OR ");
  }
  if ("not" in node) {
    return `NOT (${describeCondition(node.not)})`;
  }
  return describeLeaf(node as Leaf);
}
```

- [ ] **Step 20.3: Run tests, expect pass**

```bash
docker compose exec frontend npx vitest run src/__tests__/describeTrigger.test.ts
```
Expected: all passed.

- [ ] **Step 20.4: Commit**

```bash
git add frontend/src/lib/triggers/describe.ts frontend/src/__tests__/describeTrigger.test.ts
git commit -m "feat(frontend): describeLeaf + describeCondition helpers"
```

---

## Task 21: `RuleBuilder` + `LeafRow` components

**Files:**
- Create: `frontend/src/components/triggers/LeafRow.tsx`
- Create: `frontend/src/components/triggers/RuleBuilder.tsx`
- Create: `frontend/src/__tests__/RuleBuilder.test.tsx`

- [ ] **Step 21.1: Write the failing test**

`frontend/src/__tests__/RuleBuilder.test.tsx`:
```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import RuleBuilder from "../components/triggers/RuleBuilder";
import type { Condition } from "../api/triggers";

describe("RuleBuilder", () => {
  it("renders the top-level group selector and one empty leaf row", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByText(/Fire when/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue("SPY")).toBeInTheDocument();
    expect(screen.getByDisplayValue("550")).toBeInTheDocument();
  });

  it("emits updated condition when a leaf value changes", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    const valueInput = screen.getByDisplayValue("550") as HTMLInputElement;
    fireEvent.change(valueInput, { target: { value: "560" } });
    expect(onChange).toHaveBeenCalled();
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    expect(emitted).toEqual({ all: [{ metric: "price", ticker: "SPY", op: ">", value: 560 }] });
  });

  it("adds a new leaf row on + Add condition", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /add condition/i }));
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    expect("all" in emitted && emitted.all.length).toBe(2);
  });

  it("removes a leaf when x button clicked", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [
      { metric: "price", ticker: "SPY", op: ">", value: 550 },
      { metric: "vix", op: ">", value: 20 },
    ]};
    render(<RuleBuilder value={initial} onChange={onChange} />);
    const removeButtons = screen.getAllByRole("button", { name: /remove condition/i });
    fireEvent.click(removeButtons[1]);
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    expect("all" in emitted && emitted.all.length).toBe(1);
  });

  it("shows natural-language echo under each leaf", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByText(/price of SPY is greater than 550/i)).toBeInTheDocument();
  });

  it("toggles all/any at the top level", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    const groupSelect = screen.getByLabelText(/group operator/i) as HTMLSelectElement;
    fireEvent.change(groupSelect, { target: { value: "any" } });
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    expect("any" in emitted).toBe(true);
  });
});
```

- [ ] **Step 21.2: Write `LeafRow`**

`frontend/src/components/triggers/LeafRow.tsx`:
```typescript
import type { Leaf, Metric, Op, Window } from "@/api/triggers";
import { describeLeaf } from "@/lib/triggers/describe";

const METRICS: { value: Metric; label: string }[] = [
  { value: "price", label: "price" },
  { value: "pct_change", label: "pct_change" },
  { value: "vix", label: "vix" },
  { value: "position_pl", label: "position_pl" },
  { value: "position_pl_pct", label: "position_pl_pct" },
];

const OPS: Op[] = [">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"];
const WINDOWS: Window[] = ["1m", "5m", "15m", "1h", "1d"];

function needsTicker(m: Metric): boolean {
  return m === "price" || m === "pct_change";
}
function needsWindow(m: Metric): boolean {
  return m === "pct_change";
}

export interface LeafRowProps {
  leaf: Leaf;
  onChange: (next: Leaf) => void;
  onRemove: () => void;
}

export default function LeafRow({ leaf, onChange, onRemove }: LeafRowProps) {
  function patch(p: Partial<Leaf>) {
    let next: Leaf = { ...leaf, ...p };
    // Normalize when metric changes: drop fields that no longer apply.
    if (p.metric && p.metric !== leaf.metric) {
      if (!needsTicker(p.metric)) delete (next as Partial<Leaf>).ticker;
      else if (!leaf.ticker) next = { ...next, ticker: "SPY" };
      if (!needsWindow(p.metric)) delete (next as Partial<Leaf>).window;
      else if (!leaf.window) next = { ...next, window: "5m" };
    }
    onChange(next);
  }

  return (
    <div className="border-l-4 border-indigo-500 pl-3 py-2 bg-neutral-900 rounded">
      <div className="flex gap-2 items-center">
        <select
          aria-label="metric"
          value={leaf.metric}
          onChange={(e) => patch({ metric: e.target.value as Metric })}
          className="bg-neutral-800 px-2 py-1 rounded"
        >
          {METRICS.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>

        {needsTicker(leaf.metric) && (
          <input
            aria-label="ticker"
            value={leaf.ticker ?? ""}
            onChange={(e) => patch({ ticker: e.target.value.toUpperCase() })}
            className="bg-neutral-800 px-2 py-1 rounded w-20"
          />
        )}

        <select
          aria-label="operator"
          value={leaf.op}
          onChange={(e) => patch({ op: e.target.value as Op })}
          className="bg-neutral-800 px-2 py-1 rounded"
        >
          {OPS.map((op) => (
            <option key={op} value={op}>{op}</option>
          ))}
        </select>

        <input
          aria-label="value"
          type="number"
          step="any"
          value={leaf.value}
          onChange={(e) => patch({ value: parseFloat(e.target.value) })}
          className="bg-neutral-800 px-2 py-1 rounded w-24"
        />

        {needsWindow(leaf.metric) && (
          <select
            aria-label="window"
            value={leaf.window ?? "5m"}
            onChange={(e) => patch({ window: e.target.value as Window })}
            className="bg-neutral-800 px-2 py-1 rounded"
          >
            {WINDOWS.map((w) => (
              <option key={w} value={w}>{w}</option>
            ))}
          </select>
        )}

        <button
          type="button"
          aria-label="remove condition"
          onClick={onRemove}
          className="text-neutral-500 hover:text-rose-400 ml-auto"
        >
          ✕
        </button>
      </div>
      <div className="text-xs text-neutral-400 mt-1">{describeLeaf(leaf)}</div>
    </div>
  );
}
```

- [ ] **Step 21.3: Write `RuleBuilder`**

`frontend/src/components/triggers/RuleBuilder.tsx`:
```typescript
import type { Condition, Leaf } from "@/api/triggers";
import LeafRow from "./LeafRow";

export type GroupOp = "all" | "any";

export interface RuleBuilderProps {
  value: Condition;
  onChange: (next: Condition) => void;
}

function isGroup(c: Condition): c is { all: Condition[] } | { any: Condition[] } {
  return "all" in c || "any" in c;
}

function getGroupOp(c: Condition): GroupOp {
  return "any" in c ? "any" : "all";
}

function getLeaves(c: Condition): Leaf[] {
  if ("all" in c) return c.all as Leaf[];
  if ("any" in c) return c.any as Leaf[];
  // Single leaf at top level — wrap in all for the builder's shape.
  return [c as Leaf];
}

const EMPTY_LEAF: Leaf = { metric: "price", ticker: "SPY", op: ">", value: 0 };

export default function RuleBuilder({ value, onChange }: RuleBuilderProps) {
  const op = isGroup(value) ? getGroupOp(value) : "all";
  const leaves = getLeaves(value);

  function emit(nextLeaves: Leaf[], nextOp: GroupOp = op) {
    onChange({ [nextOp]: nextLeaves } as Condition);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-neutral-400">
        <span>Fire when</span>
        <select
          aria-label="group operator"
          value={op}
          onChange={(e) => emit(leaves, e.target.value as GroupOp)}
          className="bg-neutral-800 px-2 py-1 rounded"
        >
          <option value="all">all</option>
          <option value="any">any</option>
        </select>
        <span>of:</span>
      </div>

      <div className="space-y-2">
        {leaves.map((leaf, i) => (
          <LeafRow
            key={i}
            leaf={leaf}
            onChange={(next) => emit(leaves.map((l, j) => (j === i ? next : l)))}
            onRemove={() => emit(leaves.filter((_, j) => j !== i))}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={() => emit([...leaves, { ...EMPTY_LEAF }])}
        className="text-sm text-indigo-400 hover:text-indigo-300"
      >
        + Add condition
      </button>
    </div>
  );
}
```

- [ ] **Step 21.4: Run tests**

```bash
docker compose exec frontend npx vitest run src/__tests__/RuleBuilder.test.tsx
```
Expected: 6 passed.

- [ ] **Step 21.5: Commit**

```bash
git add frontend/src/components/triggers/ frontend/src/__tests__/RuleBuilder.test.tsx
git commit -m "feat(frontend): RuleBuilder + LeafRow components"
```

---

## Task 22: `TriggerEditorPage` — create / edit + live preview

**Files:**
- Create: `frontend/src/pages/TriggerEditorPage.tsx`
- Create: `frontend/src/__tests__/TriggerEditorPage.test.tsx`

- [ ] **Step 22.1: Write the failing test**

`frontend/src/__tests__/TriggerEditorPage.test.tsx`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TriggerEditorPage from "../pages/TriggerEditorPage";

const PROFILES = [{ id: 1, name: "Default", default_includes: [] }];

function mockFetch(responder: (url: string, init?: RequestInit) => unknown) {
  globalThis.fetch = vi.fn((url: string, init?: RequestInit) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(responder(url, init)) }),
  ) as never;
}

beforeEach(() => {
  mockFetch((url) => {
    if (url.startsWith("/api/profiles/")) return PROFILES;
    if (url.includes("/evaluate/")) return { matched: true, values: { "price:SPY": 551.2 }, missing: [] };
    return {};
  });
});

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderAt(path: string, routePath: string) {
  return render(
    <QueryClientProvider client={qc()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={<TriggerEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TriggerEditorPage", () => {
  it("renders create form on /triggers/new", async () => {
    renderAt("/triggers/new", "/triggers/new");
    await waitFor(() => expect(screen.getByText(/New trigger/i)).toBeInTheDocument());
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
  });

  it("live preview POSTs to /evaluate/ after debounce and shows YES", async () => {
    vi.useFakeTimers();
    renderAt("/triggers/new", "/triggers/new");
    // Fill name so evaluator input is non-empty
    await waitFor(() => expect(screen.getByLabelText(/name/i)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "SPY" } });
    // Advance past debounce (600ms)
    vi.advanceTimersByTime(800);
    vi.useRealTimers();
    await waitFor(() => expect(screen.getByText(/YES/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 22.2: Write the page**

`frontend/src/pages/TriggerEditorPage.tsx`:
```typescript
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type Condition, type EventTrigger,
  createTrigger, evaluateTrigger, fetchTriggers, updateTrigger,
} from "@/api/triggers";
import RuleBuilder from "@/components/triggers/RuleBuilder";
import { apiGet } from "@/api/client";

type Profile = { id: number; name: string };

const EMPTY: Pick<EventTrigger, "name" | "condition" | "cooldown_seconds" | "enabled"> = {
  name: "",
  condition: { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] },
  cooldown_seconds: 1800,
  enabled: true,
};

function useDebounced<T>(value: T, ms: number): T {
  const [deb, setDeb] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDeb(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return deb;
}

export default function TriggerEditorPage() {
  const { id: rawId } = useParams<{ id: string }>();
  const isNew = !rawId || rawId === "new";
  const id = isNew ? null : Number(rawId);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const profilesQ = useQuery({
    queryKey: ["profiles"],
    queryFn: () => apiGet<Profile[]>("/api/profiles/"),
  });

  const triggersQ = useQuery({
    queryKey: ["triggers"],
    queryFn: fetchTriggers,
    enabled: !isNew,
  });

  const existing = triggersQ.data?.find((t) => t.id === id);
  const [form, setForm] = useState(EMPTY);
  const [profileId, setProfileId] = useState<number | null>(null);

  useEffect(() => {
    if (existing) {
      setForm({
        name: existing.name,
        condition: existing.condition,
        cooldown_seconds: existing.cooldown_seconds,
        enabled: existing.enabled,
      });
      setProfileId(existing.profile);
    }
  }, [existing]);

  useEffect(() => {
    if (profilesQ.data && profileId === null && profilesQ.data.length > 0) {
      setProfileId(profilesQ.data[0].id);
    }
  }, [profilesQ.data, profileId]);

  const debounced = useDebounced(form.condition, 600);
  const previewQ = useQuery({
    queryKey: ["trigger-preview", debounced, profileId],
    queryFn: () => evaluateTrigger({ condition: debounced, profile: profileId ?? undefined }),
    enabled: profileId !== null,
    retry: false,
  });

  const save = useMutation({
    mutationFn: async () => {
      if (!profileId) throw new Error("profile required");
      const body = { ...form, profile: profileId };
      if (isNew) return createTrigger(body);
      return updateTrigger(id!, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["triggers"] });
      navigate("/triggers");
    },
  });

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-xl font-semibold">
        {isNew ? "New trigger" : `Edit trigger: ${existing?.name ?? ""}`}
      </h1>

      <div className="space-y-3">
        <div>
          <label className="block text-sm text-neutral-400 mb-1" htmlFor="tr-name">Name</label>
          <input
            id="tr-name"
            className="bg-neutral-800 px-3 py-2 rounded w-full"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>

        <div className="flex gap-4">
          <div>
            <label className="block text-sm text-neutral-400 mb-1">Profile</label>
            <select
              className="bg-neutral-800 px-3 py-2 rounded"
              value={profileId ?? ""}
              onChange={(e) => setProfileId(Number(e.target.value))}
            >
              {profilesQ.data?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-neutral-400 mb-1">Cooldown (sec)</label>
            <input
              type="number"
              className="bg-neutral-800 px-3 py-2 rounded w-24"
              value={form.cooldown_seconds}
              onChange={(e) => setForm({ ...form, cooldown_seconds: Number(e.target.value) })}
            />
          </div>
          <label className="flex items-center gap-2 mt-7">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            />
            Enabled
          </label>
        </div>
      </div>

      <RuleBuilder
        value={form.condition}
        onChange={(c: Condition) => setForm({ ...form, condition: c })}
      />

      <div className="border-t border-neutral-800 pt-4 text-sm">
        <div className="text-neutral-400 mb-1">Preview — would currently fire?</div>
        {previewQ.isLoading && <div>Evaluating…</div>}
        {previewQ.isError && <div className="text-rose-400">Invalid condition</div>}
        {previewQ.data && (
          <div>
            <span className={previewQ.data.matched ? "text-emerald-400" : "text-neutral-400"}>
              {previewQ.data.matched ? "YES" : "NO"}
            </span>
            <span className="ml-2 text-neutral-500">
              {Object.entries(previewQ.data.values)
                .filter(([k]) => !k.startsWith("_prior:"))
                .map(([k, v]) => `${k}=${v ?? "—"}`)
                .join(", ")}
            </span>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button
          className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded"
          onClick={() => save.mutate()}
          disabled={save.isPending || !form.name || !profileId}
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button
          className="bg-neutral-800 px-4 py-2 rounded"
          onClick={() => navigate("/triggers")}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 22.3: Run tests**

```bash
docker compose exec frontend npx vitest run src/__tests__/TriggerEditorPage.test.tsx
```
Expected: both passed.

- [ ] **Step 22.4: Commit**

```bash
git add frontend/src/pages/TriggerEditorPage.tsx frontend/src/__tests__/TriggerEditorPage.test.tsx
git commit -m "feat(frontend): TriggerEditorPage with live-preview"
```

---

## Task 23: `TriggersListPage` — list + toggle + delete + fire-now

**Files:**
- Create: `frontend/src/pages/TriggersListPage.tsx`
- Create: `frontend/src/__tests__/TriggersListPage.test.tsx`

- [ ] **Step 23.1: Write the failing test**

`frontend/src/__tests__/TriggersListPage.test.tsx`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TriggersListPage from "../pages/TriggersListPage";

const TRIGGERS = [
  {
    id: 1, name: "SPY>550", profile: 1,
    condition: { metric: "price", ticker: "SPY", op: ">", value: 550 },
    cooldown_seconds: 1800, enabled: true, last_fired_at: null, firings_count: 3,
    created_at: "2026-04-18T00:00:00Z", updated_at: "2026-04-18T00:00:00Z",
  },
];

beforeEach(() => {
  globalThis.fetch = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/triggers/") && (!init || init.method === "GET" || !init.method)) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(TRIGGERS) });
    }
    if (init?.method === "PATCH") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ...TRIGGERS[0], enabled: false }) });
    }
    if (init?.method === "DELETE") {
      return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
    }
    if (init?.method === "POST" && url.includes("/fire/")) {
      return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ task_id: "t" }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  }) as never;
});

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("TriggersListPage", () => {
  it("renders the list with names and firings_count", async () => {
    render(
      <QueryClientProvider client={qc()}>
        <MemoryRouter><TriggersListPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText("SPY>550")).toBeInTheDocument());
    expect(screen.getByText(/3 firings/i)).toBeInTheDocument();
  });

  it("fires manual fire on button click (after confirm)", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(
      <QueryClientProvider client={qc()}>
        <MemoryRouter><TriggersListPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText("SPY>550")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /fire now/i }));
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls;
      expect(calls.some(c => typeof c[0] === "string" && c[0].includes("/fire/"))).toBe(true);
    });
    confirmSpy.mockRestore();
  });

  it("shows empty state when no triggers", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
    ) as never;
    render(
      <QueryClientProvider client={qc()}>
        <MemoryRouter><TriggersListPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText(/no triggers yet/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 23.2: Write the page**

`frontend/src/pages/TriggersListPage.tsx`:
```typescript
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchTriggers, updateTrigger, deleteTrigger, fireTriggerNow,
  type EventTrigger,
} from "@/api/triggers";
import { describeCondition } from "@/lib/triggers/describe";

export default function TriggersListPage() {
  const qc = useQueryClient();
  const { data: triggers, isLoading } = useQuery({
    queryKey: ["triggers"],
    queryFn: fetchTriggers,
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateTrigger(id, { enabled }),
    onMutate: async ({ id, enabled }) => {
      await qc.cancelQueries({ queryKey: ["triggers"] });
      const prev = qc.getQueryData<EventTrigger[]>(["triggers"]);
      qc.setQueryData<EventTrigger[]>(["triggers"], (rows) =>
        (rows ?? []).map((t) => (t.id === id ? { ...t, enabled } : t)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["triggers"], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["triggers"] }),
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteTrigger(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["triggers"] }),
  });

  const fire = useMutation({
    mutationFn: (id: number) => fireTriggerNow(id),
  });

  if (isLoading) return <div className="p-6">Loading…</div>;

  if (!triggers?.length) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-xl font-semibold">Triggers</h1>
          <Link to="/triggers/new" className="bg-indigo-600 px-3 py-1.5 rounded text-white">New trigger</Link>
        </div>
        <p className="text-neutral-400">No triggers yet.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-semibold">Triggers</h1>
        <Link to="/triggers/new" className="bg-indigo-600 px-3 py-1.5 rounded text-white">New trigger</Link>
      </div>
      <table className="w-full text-sm">
        <thead className="text-neutral-400 text-left">
          <tr>
            <th className="py-2">Name</th>
            <th className="py-2">Condition</th>
            <th className="py-2">Last fired</th>
            <th className="py-2">Firings</th>
            <th className="py-2">Enabled</th>
            <th className="py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {triggers.map((t) => (
            <tr key={t.id} className="border-t border-neutral-800">
              <td className="py-2 font-medium">
                <Link to={`/triggers/${t.id}`} className="hover:text-indigo-400">{t.name}</Link>
              </td>
              <td className="py-2 text-neutral-400 max-w-md truncate">
                {describeCondition(t.condition)}
              </td>
              <td className="py-2 tabular-nums text-neutral-400">
                {t.last_fired_at ? new Date(t.last_fired_at).toLocaleString() : "—"}
              </td>
              <td className="py-2 tabular-nums">{t.firings_count} firings</td>
              <td className="py-2">
                <input
                  type="checkbox"
                  checked={t.enabled}
                  aria-label={`enable ${t.name}`}
                  onChange={(e) => toggle.mutate({ id: t.id, enabled: e.target.checked })}
                />
              </td>
              <td className="py-2 space-x-2">
                <button
                  className="text-amber-400 hover:text-amber-300"
                  onClick={() => {
                    if (window.confirm(`Fire "${t.name}" now? This will capture a snapshot and run the AI.`)) {
                      fire.mutate(t.id);
                    }
                  }}
                >
                  Fire now
                </button>
                <Link to={`/triggers/${t.id}`} className="text-indigo-400 hover:text-indigo-300">Edit</Link>
                <button
                  className="text-rose-400 hover:text-rose-300"
                  onClick={() => {
                    if (window.confirm(`Delete "${t.name}"? Firings history will be removed.`)) {
                      remove.mutate(t.id);
                    }
                  }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 23.3: Run tests**

```bash
docker compose exec frontend npx vitest run src/__tests__/TriggersListPage.test.tsx
```
Expected: 3 passed.

- [ ] **Step 23.4: Commit**

```bash
git add frontend/src/pages/TriggersListPage.tsx frontend/src/__tests__/TriggersListPage.test.tsx
git commit -m "feat(frontend): /triggers list page (toggle, delete, fire-now)"
```

---

## Task 24: `RecentTriggersCard` dashboard widget

**Files:**
- Create: `frontend/src/components/RecentTriggersCard.tsx`
- Create: `frontend/src/__tests__/RecentTriggersCard.test.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx` (mount the card)

- [ ] **Step 24.1: Write the failing test**

`frontend/src/__tests__/RecentTriggersCard.test.tsx`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RecentTriggersCard from "../components/RecentTriggersCard";

const FIRINGS = [
  {
    id: 1, trigger_id: 10, trigger_name: "SPY breakout",
    fired_at: "2026-04-18T14:42:00Z",
    matched_values: { "price:SPY": 551.2 },
    snapshot_id: 9, thread_id: 7, cost_capped: false,
  },
  {
    id: 2, trigger_id: 11, trigger_name: "NVDA -2%",
    fired_at: "2026-04-18T14:31:00Z",
    matched_values: { "pct_change:NVDA:5m": -0.024 },
    snapshot_id: 10, thread_id: null, cost_capped: true,
  },
];

function mount(rows: unknown[]) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(rows) }),
  ) as never;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><RecentTriggersCard /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RecentTriggersCard", () => {
  it("renders rows with trigger name + matched values", async () => {
    mount(FIRINGS);
    await waitFor(() => expect(screen.getByText(/SPY breakout/)).toBeInTheDocument());
    expect(screen.getByText(/NVDA -2%/)).toBeInTheDocument();
    expect(screen.getByText(/551\.20/)).toBeInTheDocument();
  });

  it("renders cost-capped badge when thread is null", async () => {
    mount(FIRINGS);
    await waitFor(() => expect(screen.getByText(/cost-capped/i)).toBeInTheDocument());
  });

  it("returns nothing when there are no firings", async () => {
    const { container } = mount([]);
    await waitFor(() => expect(container.textContent).toBe(""));
  });
});
```

- [ ] **Step 24.2: Write the component**

`frontend/src/components/RecentTriggersCard.tsx`:
```typescript
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchRecentFirings, type Firing } from "@/api/triggers";

function describeMatched(values: Firing["matched_values"]): string {
  return Object.entries(values)
    .filter(([k, v]) => v !== null && !k.startsWith("_prior:"))
    .map(([k, v]) => {
      if (k.startsWith("price:")) return `${k.slice("price:".length)}=${Number(v).toFixed(2)}`;
      if (k.startsWith("pct_change:")) {
        const [, ticker, window] = k.split(":");
        const pct = (Number(v) * 100).toFixed(2);
        return `${ticker} ${Number(v) >= 0 ? "+" : ""}${pct}% /${window}`;
      }
      if (k === "vix") return `vix=${Number(v).toFixed(2)}`;
      return `${k}=${v}`;
    })
    .join(", ");
}

export default function RecentTriggersCard() {
  const { data, isLoading } = useQuery({
    queryKey: ["recent-firings"],
    queryFn: () => fetchRecentFirings(5),
    refetchInterval: 30_000,
  });

  if (isLoading || !data?.length) return null;

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-sm font-semibold">Recent triggers</h3>
        <Link to="/triggers" className="text-xs text-neutral-400 hover:text-indigo-400">view all →</Link>
      </div>
      <ul className="space-y-1">
        {data.map((f) => (
          <li key={f.id} className="text-sm flex items-baseline gap-2">
            <span className="font-medium">{f.trigger_name}</span>
            <span className="text-neutral-500">·</span>
            <span className="text-neutral-400 tabular-nums">
              {new Date(f.fired_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
            <span className="text-neutral-500">·</span>
            <span className="text-neutral-300">{describeMatched(f.matched_values)}</span>
            {f.cost_capped ? (
              <span className="ml-auto text-xs text-amber-400">cost-capped</span>
            ) : f.thread_id ? (
              <Link to={`/threads/${f.thread_id}`} className="ml-auto text-xs text-indigo-400">thread →</Link>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 24.3: Mount on the Dashboard**

Read `frontend/src/pages/Dashboard.tsx`; find a reasonable grid / stack location and insert `<RecentTriggersCard />` alongside the existing widgets. Import:
```typescript
import RecentTriggersCard from "@/components/RecentTriggersCard";
```

- [ ] **Step 24.4: Run tests**

```bash
docker compose exec frontend npx vitest run src/__tests__/RecentTriggersCard.test.tsx
```
Expected: 3 passed.

- [ ] **Step 24.5: Commit**

```bash
git add frontend/src/components/RecentTriggersCard.tsx frontend/src/__tests__/RecentTriggersCard.test.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): RecentTriggersCard on Dashboard"
```

---

## Task 25: Firings drill-down tab on `TriggerEditorPage`

**Files:**
- Modify: `frontend/src/pages/TriggerEditorPage.tsx`
- Create: `frontend/src/components/triggers/FiringsTable.tsx`

- [ ] **Step 25.1: Add a FiringsTable component**

`frontend/src/components/triggers/FiringsTable.tsx`:
```typescript
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchFirings, type Firing } from "@/api/triggers";

function describeValues(values: Firing["matched_values"]): string {
  return Object.entries(values)
    .filter(([k, v]) => v !== null && !k.startsWith("_prior:"))
    .map(([k, v]) => `${k}=${typeof v === "number" ? v.toFixed(2) : v}`)
    .join(", ");
}

export default function FiringsTable({ triggerId }: { triggerId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["firings", triggerId],
    queryFn: () => fetchFirings(triggerId),
  });

  if (isLoading) return <div className="text-neutral-400">Loading…</div>;
  if (!data?.results?.length) return <div className="text-neutral-500">No firings yet.</div>;

  return (
    <table className="w-full text-sm">
      <thead className="text-neutral-400 text-left">
        <tr>
          <th className="py-2">When</th>
          <th className="py-2">Matched values</th>
          <th className="py-2">Snapshot</th>
          <th className="py-2">Thread</th>
          <th className="py-2">Status</th>
        </tr>
      </thead>
      <tbody>
        {data.results.map((f) => (
          <tr key={f.id} className="border-t border-neutral-800">
            <td className="py-2 tabular-nums text-neutral-400">
              {new Date(f.fired_at).toLocaleString()}
            </td>
            <td className="py-2">{describeValues(f.matched_values)}</td>
            <td className="py-2">
              {f.snapshot_id
                ? <Link to={`/snapshots/${f.snapshot_id}`} className="text-indigo-400">#{f.snapshot_id}</Link>
                : <span className="text-neutral-600">—</span>}
            </td>
            <td className="py-2">
              {f.thread_id
                ? <Link to={`/threads/${f.thread_id}`} className="text-indigo-400">#{f.thread_id}</Link>
                : <span className="text-neutral-600">—</span>}
            </td>
            <td className="py-2">
              {f.cost_capped
                ? <span className="text-amber-400 text-xs">cost-capped</span>
                : f.thread_id ? <span className="text-emerald-400 text-xs">fired</span>
                : <span className="text-rose-400 text-xs">error</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 25.2: Add a tab UI to `TriggerEditorPage`**

In `frontend/src/pages/TriggerEditorPage.tsx`, add a tab strip (only when editing, not on `/new`). Near the top of the returned JSX:
```tsx
// Add state
const [tab, setTab] = useState<"condition" | "firings">("condition");

// (in JSX, after the <h1>)
{!isNew && (
  <div className="flex gap-4 border-b border-neutral-800 mb-4">
    <button
      className={`py-2 ${tab === "condition" ? "text-white border-b-2 border-indigo-500" : "text-neutral-400"}`}
      onClick={() => setTab("condition")}
    >Condition</button>
    <button
      className={`py-2 ${tab === "firings" ? "text-white border-b-2 border-indigo-500" : "text-neutral-400"}`}
      onClick={() => setTab("firings")}
    >Firings ({existing?.firings_count ?? 0})</button>
  </div>
)}

// Wrap the condition body in `{tab === "condition" && ...}` when editing:
// Render <FiringsTable triggerId={id!} /> when tab === "firings".
```

Import `FiringsTable`:
```typescript
import FiringsTable from "@/components/triggers/FiringsTable";
```

- [ ] **Step 25.3: Smoke the page manually (optional but recommended)**

```bash
# Ensure the dev stack is up, then open http://localhost:5173/triggers
make dev
```

- [ ] **Step 25.4: Commit**

```bash
git add frontend/src/components/triggers/FiringsTable.tsx frontend/src/pages/TriggerEditorPage.tsx
git commit -m "feat(frontend): firings drill-down tab on trigger editor"
```

---

## Task 26: Register `/triggers` routes in `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 26.1: Read `App.tsx` and locate the Routes block**

```bash
grep -n "Route" frontend/src/App.tsx | head -20
```

- [ ] **Step 26.2: Add the routes**

Add three `<Route>` elements alongside the existing pages:
```tsx
import TriggersListPage from "@/pages/TriggersListPage";
import TriggerEditorPage from "@/pages/TriggerEditorPage";

// inside <Routes>:
<Route path="/triggers" element={<TriggersListPage />} />
<Route path="/triggers/new" element={<TriggerEditorPage />} />
<Route path="/triggers/:id" element={<TriggerEditorPage />} />
```

Also add a top-nav link if your layout has one; mirror how `/schedules` is registered (M6 Task 18 area).

- [ ] **Step 26.3: Run all frontend tests**

```bash
docker compose exec frontend npx vitest --run
```
Expected: all tests still pass (old 27 + new triggers tests).

- [ ] **Step 26.4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): route /triggers list + editor"
```

---

## Task 27: Smoke verification + cold rebuild + tag `m7-event-triggers`

**Files:** none modified — this is a verification task.

- [ ] **Step 27.1: Full backend + frontend check inside running containers**

```bash
docker compose exec -T web pytest -q
docker compose exec -T frontend npx vitest --run
```
Expected: all green. Record the final test counts.

- [ ] **Step 27.2: Lint**

```bash
docker compose exec -T web ruff check .
docker compose exec -T web mypy .
docker compose exec -T frontend npm run lint
```
Expected: ruff clean; mypy unchanged from baseline (9 pre-existing observer errors are acceptable); eslint + tsc clean apart from the pre-existing react-refresh warning on `WebSocketProvider.tsx`.

- [ ] **Step 27.3: Cold rebuild (catches reproducibility bugs)**

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

Wait for `web` to be healthy, then re-run the tests:
```bash
docker compose exec -T web pytest -q
docker compose exec -T frontend npx vitest --run
```

- [ ] **Step 27.4: Manual smoke — full end-to-end fire**

Do this during market hours (or temporarily stub `is_market_open` to return True). In a terminal:
```bash
# Create a trigger via the UI or:
docker compose exec web python manage.py shell -c "
from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger
p = TradingProfile.objects.first() or TradingProfile.objects.create(name='Smoke', style='x')
EventTrigger.objects.create(
    name='SPY>0-smoke', profile=p,
    condition={'metric': 'price', 'ticker': 'SPY', 'op': '>', 'value': 0},
    cooldown_seconds=60,
)
"
```

Tail the beat + worker logs:
```bash
docker compose logs -f beat worker | grep -E "trigger\."
```

Within ~10s you should see:
- `trigger.tick` on beat
- `trigger.fired` on worker
- a new `TriggerFiring` row, a new `Thread`, a new `Notification`
- the NotificationBell in the UI shows an unread count (refresh the page if needed)

Delete the smoke trigger when verified:
```bash
docker compose exec web python manage.py shell -c "
from apps.triggers.models import EventTrigger
EventTrigger.objects.filter(name='SPY>0-smoke').delete()
"
```

- [ ] **Step 27.5: Manual smoke — cost-capped path**

```bash
# Set a zero cap so the next fire goes cost-capped
docker compose exec web python manage.py shell -c "
from decimal import Decimal
from apps.secrets.models import ProviderConfig
p = ProviderConfig.objects.first()
p.daily_cost_cap_usd = Decimal('0.00')
p.save(update_fields=['daily_cost_cap_usd'])
"
```

Fire a trigger manually via the UI's "Fire now" or:
```bash
docker compose exec web python manage.py shell -c "
from apps.triggers.models import EventTrigger
from apps.triggers.tasks import fire_trigger
t = EventTrigger.objects.first()
fire_trigger(trigger_id=t.id, matched_values={'source': 'smoke'})
"
```

Verify:
```bash
docker compose exec web python manage.py shell -c "
from apps.triggers.models import TriggerFiring
f = TriggerFiring.objects.order_by('-id').first()
print('cost_capped=', f.cost_capped, 'thread=', f.thread_id)
"
```
Expected: `cost_capped= True`, `thread= None`.

Restore the cap:
```bash
docker compose exec web python manage.py shell -c "
from decimal import Decimal
from apps.secrets.models import ProviderConfig
p = ProviderConfig.objects.first()
p.daily_cost_cap_usd = Decimal('10.00')
p.save(update_fields=['daily_cost_cap_usd'])
"
```

- [ ] **Step 27.6: Tag the release**

```bash
git tag m7-event-triggers
git log --oneline m6-observer..HEAD   # show the M7 commit range
```

(Do not push the tag unless the user asks — tag is local.)

- [ ] **Step 27.7: Commit a carry-over note (final)**

`docs/superpowers/plans/2026-04-18-m7-event-triggers.md` stays as-is (it's the plan). For carry-over, add a small note at the bottom of the spec if anything was intentionally punted in-flight, following the M5/M6 precedent. Otherwise:

```bash
git commit --allow-empty -m "chore: tag m7-event-triggers release"
```

---

## Self-review checklist

After running through the tasks, confirm each of the 14 Decisions from the spec is covered:

| Decision | Where |
|---|---|
| 1. 5 metrics, skip `volume_z` | Tasks 4 (DSL VALID_METRICS), 9/10 (metrics builder) |
| 2. 10s tick, market-hours only | Tasks 12 (beat task gate), 14 (interval schedule seed) |
| 3. Ticker-union fetch; positions conditional | Task 9 (_ticker_union, needs_positions branch) |
| 4. Crossings use Redis `trigger:last:<TICKER>` TTL 60 | Task 9 (`r.setex(f"trigger:last:{ticker}", 60, ...)`) |
| 5. Cooldown = time AND re-arm | Task 11 (cooldown_blocks + mark_fired/rearmed) |
| 6. `EventTrigger.profile` required | Task 2 (ForeignKey without null=True) |
| 7. Rule builder form + NL echo | Tasks 20 (describer), 21 (LeafRow inline echo) |
| 8. Notify: bell + toast + OS | Task 13 (notify(kind="trigger")) — reuses M6 NotificationBell |
| 9. Cost-cap → skip AI, notify cost_limit | Task 13 (cost-capped branch) |
| 10. Both /fire/ and /evaluate/ | Task 17 |
| 11. `/triggers/:id` drill-down + RecentTriggersCard | Tasks 24, 25 |
| 12. Pure evaluator, I/O in metrics | Tasks 5–7 (evaluator), 9 (metrics) |
| 13. `fire_trigger` not retried; redis_lock | Task 13 (`autoretry_for=()`, `max_retries=0`, `r.set nx=True`) |
| 14. Invalid DSL → disable trigger | Task 12 (`_disable_on_bad_condition`) |

If any row is blank, go back and add a task.

---

## Milestone completion criteria

- `make test` green (backend + frontend).
- `make lint` clean (modulo pre-existing warnings noted in §M6 carry-over).
- `/triggers` page renders, create/edit/toggle/fire-now all work.
- One live fire observed in market hours, one cost-capped fire observed.
- Tagged `m7-event-triggers`.
