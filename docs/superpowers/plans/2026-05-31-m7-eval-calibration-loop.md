# M7: Eval-Driven Calibration Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop on M6's "make the AI measurable" thesis — persist the offline eval harness's results, schedule it (opt-in, cost-capped), and feed the *measured* calibration back into the live coach prompt so the AI becomes self-correcting.

**Architecture:** Five units from `docs/superpowers/specs/2026-05-31-remaining-work.md`'s recommended M7 thread (B3 → schedule → A3 → B1 → B2), resequenced by dependency: **B1** (additive schema field — prerequisite-free, improves the confidence value B3 persists) → **B3** (`EvalRun` model + read-only DRF view) → **B2** (cost-cap pre-flight helper, reused by the scheduled task) → **schedule** (opt-in beat task) → **A3** (coach reads the latest `EvalRun`). The eval harness stays look-ahead-safe (replay sees only the frozen snapshot); A3 injects calibration into the *live* coach only — never the replay path.

**Tech Stack:** Django 5 + DRF, Celery beat, Pydantic (Observer schemas), pytest. All backend. Everything runs in Docker (`docker compose exec web pytest ...`, WORKDIR `/app/backend`, so test paths drop the `backend/` prefix).

**Standing directives for the executor (from project memory):**
- Build autonomously; **commit locally only**; do **not** push / open a PR / merge without explicit confirmation.
- `run_structured` has **no** `MOCK_EXTERNAL` short-circuit → patch it directly in tests (`patch.object(svc, "run_structured", ...)`).
- `worker`/`beat` don't hot-reload tasks — after adding the task module + beat entry, a fresh `up` or CI registers it; the running stack would need `docker compose restart worker beat` (not required for tests).
- Subagents: **commits only** — never run `git pull` / `git checkout` / branch ops in a subagent.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `backend/apps/observer/schemas.py` | `ObservationReport.predicted_confidence` field (B1) | Modify |
| `backend/apps/aieval/services.py` | `_confidence_from_report` uses new field; `DEFAULT_EVAL_SYSTEM`, `persist_eval_run`, `preflight_cost_cap`, `latest_eval_for_model` | Modify |
| `backend/apps/aieval/models.py` | `EvalRun` model (B3) | Create |
| `backend/apps/aieval/migrations/__init__.py` + `0001_initial.py` | Migration for `EvalRun` | Create |
| `backend/apps/aieval/serializers.py` | `EvalRunSerializer` (B3) | Create |
| `backend/apps/aieval/views.py` | `EvalRunListView` + `EvalRunLatestView` (B3) | Create |
| `backend/apps/aieval/urls.py` | `/api/aieval/` routes (B3) | Create |
| `backend/apps/aieval/tasks.py` | `aieval.run_scheduled` beat task (schedule) | Create |
| `backend/apps/aieval/management/commands/aieval.py` | Cap pre-flight + persist on the manual command (B2) | Modify |
| `backend/apps/threads/coach.py` | `_calibration_block` + `_calibration_verdict`, wired into `assemble_coach_context` (A3) | Modify |
| `backend/config/urls.py` | Register `api/aieval/` (specific prefix, before generic `api/`) | Modify |
| `backend/config/celery.py` | Add `apps.aieval` to autodiscover + `aieval-run-scheduled` beat entry | Modify |
| `backend/config/settings/base.py` | `AIEVAL_SCHEDULED_*` defaults | Modify |
| `backend/apps/aieval/tests/test_aieval.py` | New tests for every unit | Modify |
| `backend/apps/threads/tests/test_coach.py` | A3 coach tests | Modify (or create if absent) |

---

## Task 1 — B1: `predicted_confidence` on `ObservationReport`, harness prefers it

**Why first:** purely additive schema change (the schema's own docstring mandates `Optional` + default for new fields). It improves the `avg_confidence` value Task 2 persists, and unblocks the eval harness from dropping zero-signal reports off the reliability curve.

**Files:**
- Modify: `backend/apps/observer/schemas.py` (the `ObservationReport` class, after `predicted_horizon_days`)
- Modify: `backend/apps/aieval/services.py:116-125` (`_confidence_from_report`)
- Test: `backend/apps/aieval/tests/test_aieval.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/apps/aieval/tests/test_aieval.py` (import `_confidence_from_report` — extend the existing import line `from apps.aieval.services import confidence_calibration, evaluate, labeled_examples, replay_one` to also import it):

```python
from apps.aieval.services import _confidence_from_report  # add to existing import block


def test_predicted_confidence_field_accepted():
    """ObservationReport accepts an optional predicted_confidence in [0,1]."""
    r = ObservationReport(
        headline="h", bias="bullish", summary="s", next_check_in="tomorrow",
        predicted_confidence=0.73,
    )
    assert r.predicted_confidence == 0.73
    # Default is None (additive / backward-compatible)
    r2 = ObservationReport(headline="h", bias="bullish", summary="s", next_check_in="t")
    assert r2.predicted_confidence is None


def test_confidence_prefers_predicted_confidence_over_signal_mean():
    """When predicted_confidence is set, it wins over the signal-mean fallback."""
    r = _report("bullish", confs=(0.2, 0.4))  # signal mean would be 0.3
    r.predicted_confidence = 0.9
    assert _confidence_from_report(r) == 0.9


def test_confidence_falls_back_to_signal_mean_when_unset():
    """predicted_confidence=None → mean of per-signal confidences (legacy behavior)."""
    r = _report("bullish", confs=(0.6, 1.0))  # mean 0.8
    assert r.predicted_confidence is None
    assert _confidence_from_report(r) == 0.8


def test_confidence_none_when_no_signals_and_no_predicted():
    r = ObservationReport(headline="h", bias="bullish", summary="s", next_check_in="t")
    assert _confidence_from_report(r) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -k "predicted_confidence or confidence_prefers or falls_back or none_when_no_signals" -v`
Expected: FAIL — `predicted_confidence` is not a field / `_confidence_from_report` ignores it.

- [ ] **Step 3: Add the field to the schema**

In `backend/apps/observer/schemas.py`, inside `class ObservationReport`, immediately after the `predicted_horizon_days` field (before `grounding`):

```python
    predicted_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Your confidence in predicted_direction over the horizon, 0..1. "
        "Optional; falls back to the mean of per-signal confidences when unset.",
    )
```

- [ ] **Step 4: Make the harness prefer it**

In `backend/apps/aieval/services.py`, replace the body of `_confidence_from_report`:

```python
def _confidence_from_report(report: ObservationReport) -> float | None:
    """Stated confidence: the report's own predicted_confidence when set,
    else the mean of the per-signal confidences (legacy fallback)."""
    pc = getattr(report, "predicted_confidence", None)
    if pc is not None:
        return round(float(pc), 4)
    confs = [
        s.confidence
        for s in getattr(report, "signals", [])
        if getattr(s, "confidence", None) is not None
    ]
    if not confs:
        return None
    return round(sum(confs) / len(confs), 4)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -v`
Expected: PASS — all new tests green AND all pre-existing aieval tests still green (additive change).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/observer/schemas.py backend/apps/aieval/services.py backend/apps/aieval/tests/test_aieval.py
git commit -m "feat(aieval): predicted_confidence on ObservationReport; harness prefers it over signal mean"
```

---

## Task 2 — B3a: `EvalRun` model + migration + persist helper

**Files:**
- Create: `backend/apps/aieval/models.py`
- Create: `backend/apps/aieval/migrations/__init__.py`
- Create (via makemigrations): `backend/apps/aieval/migrations/0001_initial.py`
- Modify: `backend/apps/aieval/services.py` (add `persist_eval_run`)
- Test: `backend/apps/aieval/tests/test_aieval.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/apps/aieval/tests/test_aieval.py`:

```python
from apps.aieval.services import persist_eval_run  # add to import block


def test_persist_eval_run_maps_result_to_row(db):
    result = {
        "label": "smoke", "model": "claude-sonnet-4-6", "horizon": 30,
        "n": 5, "skipped": 1, "scored": 4, "hit_rate": 0.75, "brier": 0.21,
        "avg_confidence": 0.68, "calibration_error": 0.12,
        "calibration": [{"bin_low": 0.7, "bin_high": 0.9, "n": 4, "hits": 3,
                         "observed_hit_rate": 0.75, "mean_confidence": 0.68}],
        "examples": [{"predicted_direction": "bullish", "hit": True}],
    }
    from apps.aieval.models import EvalRun

    run = persist_eval_run(result, source="scheduled")
    assert isinstance(run, EvalRun)
    assert run.pk is not None
    assert run.source == "scheduled"
    assert run.label == "smoke"
    assert run.model == "claude-sonnet-4-6"
    assert run.horizon == 30
    assert run.n == 5 and run.skipped == 1 and run.scored == 4
    assert run.hit_rate == 0.75 and run.brier == 0.21
    assert run.avg_confidence == 0.68 and run.calibration_error == 0.12
    assert run.calibration[0]["observed_hit_rate"] == 0.75
    assert run.examples[0]["hit"] is True


def test_persist_eval_run_defaults_source_manual(db):
    run = persist_eval_run({"label": "x", "model": "m", "n": 0})
    assert run.source == "manual"
    assert run.horizon is None and run.hit_rate is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -k persist_eval_run -v`
Expected: FAIL — `apps.aieval.models` / `persist_eval_run` do not exist.

- [ ] **Step 3: Create the model**

Create `backend/apps/aieval/models.py`:

```python
"""Persisted offline-eval results.

One row per harness run (manual `manage.py aieval` or the scheduled beat task).
Stores the aggregate scoring of `apps.aieval.services.evaluate` so the calibration
it measured can be read later — by the read-only API and by the live Decision
Coach (A3), which injects the latest row's calibration into the prompt.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class EvalRun(models.Model):
    SOURCE: ClassVar = [("manual", "Manual"), ("scheduled", "Scheduled")]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    source = models.CharField(max_length=12, choices=SOURCE, default="manual")
    label = models.CharField(max_length=64, default="baseline")
    model = models.CharField(max_length=128, db_index=True)
    horizon = models.PositiveIntegerField(null=True, blank=True)

    n = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)
    scored = models.PositiveIntegerField(default=0)
    hit_rate = models.FloatField(null=True, blank=True)
    brier = models.FloatField(null=True, blank=True)
    avg_confidence = models.FloatField(null=True, blank=True)
    calibration_error = models.FloatField(null=True, blank=True)

    # Reliability buckets + per-row outcomes (see services.evaluate()).
    calibration = models.JSONField(default=list)
    examples = models.JSONField(default=list)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["model", "-created_at"])]

    def __str__(self) -> str:
        return f"EvalRun(#{self.pk} {self.model} hit_rate={self.hit_rate})"
```

- [ ] **Step 4: Add the persist helper**

In `backend/apps/aieval/services.py`, add near the top-level imports:

```python
from apps.aieval.models import EvalRun
```

Then add this function (place it after `evaluate`):

```python
def persist_eval_run(result: dict[str, Any], *, source: str = "manual") -> EvalRun:
    """Map an `evaluate()` result dict onto a stored `EvalRun` row.

    `source` is 'manual' (the management command) or 'scheduled' (the beat task).
    Tolerant of partial dicts (uses .get with sensible defaults) so a caller
    never has to assemble a full result to persist a smoke run.
    """
    return EvalRun.objects.create(
        source=source,
        label=result.get("label", "baseline"),
        model=result.get("model", ""),
        horizon=result.get("horizon"),
        n=result.get("n", 0),
        skipped=result.get("skipped", 0),
        scored=result.get("scored", 0),
        hit_rate=result.get("hit_rate"),
        brier=result.get("brier"),
        avg_confidence=result.get("avg_confidence"),
        calibration_error=result.get("calibration_error"),
        calibration=result.get("calibration", []),
        examples=result.get("examples", []),
    )
```

- [ ] **Step 5: Create the migrations package + generate the migration**

```bash
# migrations package marker (makemigrations needs the package to exist)
touch backend/apps/aieval/migrations/__init__.py
docker compose exec web python manage.py makemigrations aieval
```

Expected: creates `backend/apps/aieval/migrations/0001_initial.py` with `Create model EvalRun`.

- [ ] **Step 6: Run the test to verify it passes**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -k persist_eval_run -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/aieval/models.py backend/apps/aieval/migrations/ backend/apps/aieval/services.py backend/apps/aieval/tests/test_aieval.py
git commit -m "feat(aieval): EvalRun model + persist_eval_run helper"
```

---

## Task 3 — B3b: read-only DRF view + URL wiring

**Files:**
- Create: `backend/apps/aieval/serializers.py`
- Create: `backend/apps/aieval/views.py`
- Create: `backend/apps/aieval/urls.py`
- Modify: `backend/config/urls.py`
- Test: `backend/apps/aieval/tests/test_aieval.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/apps/aieval/tests/test_aieval.py`:

```python
from rest_framework.test import APIClient  # add to import block


def test_eval_runs_list_endpoint(db):
    persist_eval_run({"label": "a", "model": "claude-sonnet-4-6", "n": 3, "scored": 3,
                      "hit_rate": 0.66, "brier": 0.2}, source="manual")
    persist_eval_run({"label": "b", "model": "claude-opus-4-8", "n": 5, "scored": 5,
                      "hit_rate": 0.8, "brier": 0.15}, source="scheduled")
    resp = APIClient().get("/api/aieval/runs/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # newest first (ordering = -created_at); both labels present
    labels = {row["label"] for row in data}
    assert labels == {"a", "b"}
    assert "calibration" in data[0] and "hit_rate" in data[0]


def test_eval_runs_latest_endpoint(db):
    persist_eval_run({"label": "old", "model": "m", "n": 1}, source="manual")
    newest = persist_eval_run({"label": "new", "model": "m", "n": 2, "hit_rate": 0.5},
                              source="scheduled")
    resp = APIClient().get("/api/aieval/runs/latest/")
    assert resp.status_code == 200
    assert resp.json()["id"] == newest.id
    assert resp.json()["label"] == "new"


def test_eval_runs_latest_204_when_empty(db):
    resp = APIClient().get("/api/aieval/runs/latest/")
    assert resp.status_code == 204
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -k "eval_runs" -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Create the serializer**

Create `backend/apps/aieval/serializers.py`:

```python
from typing import ClassVar

from rest_framework import serializers

from apps.aieval.models import EvalRun


class EvalRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvalRun
        fields: ClassVar = [
            "id", "created_at", "source", "label", "model", "horizon",
            "n", "skipped", "scored", "hit_rate", "brier", "avg_confidence",
            "calibration_error", "calibration", "examples",
        ]
        read_only_fields = fields
```

- [ ] **Step 4: Create the views**

Create `backend/apps/aieval/views.py`:

```python
from __future__ import annotations

from rest_framework import generics
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.aieval.models import EvalRun
from apps.aieval.serializers import EvalRunSerializer


class EvalRunListView(generics.ListAPIView):
    serializer_class = EvalRunSerializer

    def get_queryset(self):
        return EvalRun.objects.order_by("-created_at")[:50]


class EvalRunLatestView(APIView):
    def get(self, request):
        run = EvalRun.objects.order_by("-created_at").first()
        if run is None:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)
        return Response(EvalRunSerializer(run).data)
```

- [ ] **Step 5: Create the urls**

Create `backend/apps/aieval/urls.py`:

```python
from django.urls import path

from apps.aieval import views

app_name = "aieval"

urlpatterns = [
    path("runs/", views.EvalRunListView.as_view(), name="run-list"),
    path("runs/latest/", views.EvalRunLatestView.as_view(), name="run-latest"),
]
```

- [ ] **Step 6: Register in config/urls.py**

In `backend/config/urls.py`, add this line in the **specific-prefix block** (with the other `api/<name>/` includes, e.g. right after the `api/recall/` line) — NOT among the bare `api/` includes at the bottom:

```python
    path("api/aieval/", include("apps.aieval.urls")),
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -k "eval_runs" -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/aieval/serializers.py backend/apps/aieval/views.py backend/apps/aieval/urls.py backend/config/urls.py backend/apps/aieval/tests/test_aieval.py
git commit -m "feat(aieval): read-only EvalRun list + latest API at /api/aieval/runs/"
```

---

## Task 4 — B2: cost-cap pre-flight on the manual command (+ persist)

**Why now:** the helper `preflight_cost_cap` is reused by the scheduled task in Task 5, so it must land first. Also wires the command to persist via Task 2's helper.

**Files:**
- Modify: `backend/apps/aieval/services.py` (add `DEFAULT_EVAL_SYSTEM`, `preflight_cost_cap`)
- Modify: `backend/apps/aieval/management/commands/aieval.py`
- Test: `backend/apps/aieval/tests/test_aieval.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/apps/aieval/tests/test_aieval.py`:

```python
from decimal import Decimal

from django.core.management import CommandError

from apps.ai.cost import CostCapExceededError
from apps.aieval.services import preflight_cost_cap


def test_preflight_cost_cap_no_config_is_noop(db):
    # No ProviderConfig row → Infinity daily / None monthly → never raises.
    preflight_cost_cap("claude")  # must not raise


def test_preflight_cost_cap_raises_when_over(db):
    from apps.secrets.models import ProviderConfig
    from apps.threads.models import AIRun, Message

    ProviderConfig.objects.create(provider="claude", daily_cost_cap_usd=Decimal("1.00"))
    # Record $2 of spend today so the cap is already blown.
    AIRun.objects.create(provider="claude", model="claude-opus-4-8",
                         status="done", cost_usd=Decimal("2.00"))
    with pytest.raises(CostCapExceededError):
        preflight_cost_cap("claude")


def test_command_aborts_on_cost_cap(profile):
    from apps.secrets.models import ProviderConfig
    from apps.threads.models import AIRun

    _postmortem(_thesis(profile, snapshot=_snapshot(profile)), verdict="correct", fwd=5.0)
    ProviderConfig.objects.create(provider="claude", daily_cost_cap_usd=Decimal("1.00"))
    AIRun.objects.create(provider="claude", model="claude-opus-4-8",
                         status="done", cost_usd=Decimal("2.00"))
    with pytest.raises(CommandError):
        call_command("aieval", "--model", "claude-opus-4-8")


def test_command_persists_eval_run(profile):
    from apps.aieval.models import EvalRun

    _postmortem(_thesis(profile, snapshot=_snapshot(profile)), verdict="correct", fwd=5.0)
    out = StringIO()
    with patch.object(svc, "run_structured", return_value=_report("bullish")):
        call_command("aieval", "--model", "claude-opus-4-8", "--limit", "1",
                     "--label", "persisted", stdout=out)
    rows = EvalRun.objects.filter(label="persisted")
    assert rows.count() == 1
    assert rows.first().source == "manual"
```

NOTE on `AIRun` field names: confirm `provider`, `model`, `status`, `cost_usd` exist on `apps.threads.models.AIRun` before writing the test — `cost.py` filters `AIRun.objects.filter(provider=..., created_at__gte=...)` and aggregates `Sum("cost_usd")`, and `calibration.py` filters `status="done"`, so all four are real. `created_at` is `auto_now_add`, so a fresh row counts as "today".

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -k "preflight or cost_cap or persists_eval_run" -v`
Expected: FAIL — `preflight_cost_cap` undefined; command neither checks caps nor persists.

- [ ] **Step 3: Add `DEFAULT_EVAL_SYSTEM` + `preflight_cost_cap` to services.py**

In `backend/apps/aieval/services.py`, add the shared default system prompt near the top (after the `_CONF_BINS` constant) so both the command and the beat task import it:

```python
DEFAULT_EVAL_SYSTEM = (
    "You are a trading analyst. Read the market snapshot and state a single "
    "directional bias (bullish, bearish, or neutral) with your reasoning."
)
```

And add the pre-flight helper (place after `persist_eval_run`):

```python
def preflight_cost_cap(provider: str = "claude") -> None:
    """Raise CostCapExceededError if the provider's configured caps are already
    breached, BEFORE spending on a real eval run.

    Mirrors `apps.observer.services.run` cap resolution: no ProviderConfig row →
    Infinity daily / None monthly (no-op). Caps read AIRun spend only; they do
    not call the model, so this is safe to call from the command and the task.
    """
    from decimal import Decimal

    from apps.ai.cost import check_daily_cap, check_monthly_cap
    from apps.secrets.models import ProviderConfig

    cfg = ProviderConfig.objects.filter(provider=provider).first()
    if cfg is None:
        cap_usd: Decimal = Decimal("Infinity")
        monthly_cap: Decimal | None = None
    else:
        cap_usd = cfg.daily_cost_cap_usd
        monthly_cap = cfg.monthly_cost_cap_usd
    check_daily_cap(provider, cap_usd=cap_usd)
    check_monthly_cap(provider, cap_usd=monthly_cap)
```

- [ ] **Step 4: Wire the command**

In `backend/apps/aieval/management/commands/aieval.py`:

Replace the import line `from apps.aieval.services import evaluate` with:

```python
from apps.ai.cost import CostCapExceededError
from apps.aieval.services import (
    DEFAULT_EVAL_SYSTEM,
    evaluate,
    persist_eval_run,
    preflight_cost_cap,
)
```

Delete the local `_DEFAULT_SYSTEM = (...)` block and replace its three references in `_read_system` with `DEFAULT_EVAL_SYSTEM`.

In `handle`, after `system = self._read_system(options["system_file"])` and before `res = evaluate(...)`, insert the cap pre-flight:

```python
        try:
            preflight_cost_cap("claude")
        except CostCapExceededError as exc:
            raise CommandError(str(exc)) from exc
```

After the `if res["n"] == 0:` early-return block, persist the run:

```python
        persist_eval_run(res, source="manual")
```

(Place it right after the zero-data guard returns, i.e. once we know `res["n"] > 0`, before the success `stdout.write`.)

Update the command's module docstring: change the line implying caps are always respected to state explicitly: *"Respects the provider's configured daily + monthly cost caps via a pre-flight check (aborts with CommandError if already over) and supports `--limit` for cheap smoke runs."*

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -v`
Expected: PASS — new cap/persist tests green; pre-existing `test_command_runs_and_prints`, `test_command_zero_data_friendly_message`, `test_command_prints_calibration_table` still green (no ProviderConfig in those → Infinity cap → no abort).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/aieval/services.py backend/apps/aieval/management/commands/aieval.py backend/apps/aieval/tests/test_aieval.py
git commit -m "feat(aieval): cost-cap pre-flight + persist EvalRun on the manual command"
```

---

## Task 5 — Schedule the harness (opt-in, cost-capped beat task)

**Design:** Default **OFF** (`AIEVAL_SCHEDULED_ENABLED=False`). The harness calls the real model and `run_structured` has no `MOCK_EXTERNAL` short-circuit, so an always-on schedule would spend money / hit the model under any overlay. When enabled, it runs the cap pre-flight first and persists `source="scheduled"`. The scheduled model defaults to `claude-sonnet-4-6` (the profile default) so A3 (Task 6, which matches on `profile.default_model`) actually finds calibration to inject.

**Files:**
- Modify: `backend/config/settings/base.py`
- Create: `backend/apps/aieval/tasks.py`
- Modify: `backend/config/celery.py` (autodiscover + beat entry)
- Test: `backend/apps/aieval/tests/test_aieval.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/apps/aieval/tests/test_aieval.py`:

```python
from apps.aieval.tasks import run_scheduled


def test_scheduled_skips_when_disabled(profile, settings):
    settings.AIEVAL_SCHEDULED_ENABLED = False
    _postmortem(_thesis(profile, snapshot=_snapshot(profile)), verdict="correct", fwd=5.0)
    assert run_scheduled() == {"skipped": "disabled"}
    from apps.aieval.models import EvalRun
    assert EvalRun.objects.count() == 0


def test_scheduled_runs_and_persists_when_enabled(profile, settings):
    settings.AIEVAL_SCHEDULED_ENABLED = True
    settings.AIEVAL_SCHEDULED_MODEL = "claude-sonnet-4-6"
    settings.AIEVAL_SCHEDULED_LIMIT = None
    settings.AIEVAL_SCHEDULED_HORIZON = None
    _postmortem(_thesis(profile, direction="bullish", snapshot=_snapshot(profile)),
                verdict="correct", fwd=5.0)
    from apps.aieval.models import EvalRun

    with patch.object(svc, "run_structured", return_value=_report("bullish")):
        result = run_scheduled()
    assert "ran" in result
    row = EvalRun.objects.get(pk=result["ran"])
    assert row.source == "scheduled"
    assert row.model == "claude-sonnet-4-6"
    assert row.label == "scheduled"


def test_scheduled_skips_on_cost_cap(profile, settings):
    settings.AIEVAL_SCHEDULED_ENABLED = True
    from apps.secrets.models import ProviderConfig
    from apps.threads.models import AIRun

    ProviderConfig.objects.create(provider="claude", daily_cost_cap_usd=Decimal("1.00"))
    AIRun.objects.create(provider="claude", model="claude-opus-4-8",
                         status="done", cost_usd=Decimal("2.00"))
    _postmortem(_thesis(profile, snapshot=_snapshot(profile)), verdict="correct", fwd=5.0)
    assert run_scheduled() == {"skipped": "cost_cap"}


def test_scheduled_skips_when_no_data(settings, db):
    settings.AIEVAL_SCHEDULED_ENABLED = True
    assert run_scheduled() == {"skipped": "no_data"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -k scheduled -v`
Expected: FAIL — `apps.aieval.tasks` does not exist.

- [ ] **Step 3: Add settings defaults**

In `backend/config/settings/base.py`, add near the other feature flags (e.g. after the `MOCK_EXTERNAL` / observer-tz settings block):

```python
# Offline eval harness — scheduled run. OFF by default: it calls the REAL model
# ($) and run_structured has no MOCK_EXTERNAL short-circuit. Enable deliberately.
AIEVAL_SCHEDULED_ENABLED = env.bool("AIEVAL_SCHEDULED_ENABLED", default=False)
AIEVAL_SCHEDULED_MODEL = env.str("AIEVAL_SCHEDULED_MODEL", default="claude-sonnet-4-6")
AIEVAL_SCHEDULED_HORIZON = env.int("AIEVAL_SCHEDULED_HORIZON", default=30)
AIEVAL_SCHEDULED_LIMIT = env.int("AIEVAL_SCHEDULED_LIMIT", default=25)
```

(If `env` is not already imported in `base.py`, it is — the file uses `env.bool(...)` for `MOCK_EXTERNAL`. Match the existing `env` usage style.)

- [ ] **Step 4: Create the task**

Create `backend/apps/aieval/tasks.py`:

```python
"""Beat task: run the offline eval harness on a schedule (opt-in, cost-capped).

OFF by default (AIEVAL_SCHEDULED_ENABLED). When on, it replays labeled theses
through the real model, scores calibration, and persists an EvalRun the live
coach (A3) reads. Guarded by the same cost-cap pre-flight as the manual command.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from apps.ai.cost import CostCapExceededError
from apps.aieval.services import (
    DEFAULT_EVAL_SYSTEM,
    evaluate,
    persist_eval_run,
    preflight_cost_cap,
)

log = logging.getLogger(__name__)


@shared_task(name="aieval.run_scheduled")
def run_scheduled() -> dict:
    if not getattr(settings, "AIEVAL_SCHEDULED_ENABLED", False):
        return {"skipped": "disabled"}

    model = getattr(settings, "AIEVAL_SCHEDULED_MODEL", "claude-sonnet-4-6")
    horizon = getattr(settings, "AIEVAL_SCHEDULED_HORIZON", None)
    limit = getattr(settings, "AIEVAL_SCHEDULED_LIMIT", None)

    try:
        preflight_cost_cap("claude")
    except CostCapExceededError as exc:
        log.warning("aieval.run_scheduled skipped — cost cap: %s", exc)
        return {"skipped": "cost_cap"}

    res = evaluate(
        system=DEFAULT_EVAL_SYSTEM, model=model, label="scheduled",
        horizon=horizon, limit=limit,
    )
    if not res["n"]:
        return {"skipped": "no_data"}

    run = persist_eval_run(res, source="scheduled")
    log.info("aieval.run_scheduled persisted EvalRun #%s (n=%s, hit_rate=%s)",
             run.id, res["n"], res["hit_rate"])
    return {"ran": run.id, "n": res["n"], "hit_rate": res["hit_rate"]}
```

- [ ] **Step 5: Register the task module + beat entry in celery.py**

In `backend/config/celery.py`, add `"apps.aieval"` to the `autodiscover_tasks([...])` list (e.g. after `"apps.recall"`):

```python
        "apps.recall",
        "apps.aieval",
```

And add a beat entry to `app.conf.beat_schedule` (weekly, Mondays 05:00 UTC — inert until the flag is enabled):

```python
    "aieval-run-scheduled": {
        "task": "aieval.run_scheduled",
        "schedule": crontab(hour=5, minute=0, day_of_week=1),
    },
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker compose exec web pytest apps/aieval/tests/test_aieval.py -k scheduled -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/config/settings/base.py backend/apps/aieval/tasks.py backend/config/celery.py backend/apps/aieval/tests/test_aieval.py
git commit -m "feat(aieval): opt-in cost-capped scheduled harness run (beat: aieval.run_scheduled)"
```

---

## Task 6 — A3: live calibration injection into the coach

**Design:** Add a `_calibration_block(profile)` section to `assemble_coach_context`, reading the latest `EvalRun` whose `model == profile.default_model`. It rides the existing primary-ticker gate (A2 — snapshot-free coach — is explicitly deferred). The block states the measured directional hit-rate + Brier and an over/under/well-confident verdict so the model can self-correct. **This touches only the live coach — never the eval replay path**, preserving look-ahead safety.

**Files:**
- Modify: `backend/apps/aieval/services.py` (add `latest_eval_for_model`)
- Modify: `backend/apps/threads/coach.py`
- Test: `backend/apps/threads/tests/test_coach.py` (create if absent), `backend/apps/aieval/tests/test_aieval.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/apps/aieval/tests/test_aieval.py` (query helper):

```python
def test_latest_eval_for_model(db):
    from apps.aieval.services import latest_eval_for_model

    assert latest_eval_for_model("claude-sonnet-4-6") is None
    persist_eval_run({"label": "old", "model": "claude-sonnet-4-6", "n": 1}, source="manual")
    newest = persist_eval_run({"label": "new", "model": "claude-sonnet-4-6", "n": 2},
                              source="scheduled")
    persist_eval_run({"label": "other", "model": "claude-opus-4-8", "n": 9}, source="manual")
    got = latest_eval_for_model("claude-sonnet-4-6")
    assert got.id == newest.id  # newest for THAT model only
```

Create (or append to) `backend/apps/threads/tests/test_coach.py`:

```python
"""Coach calibration-block (A3) tests."""

from __future__ import annotations

import pytest

from apps.threads.coach import (
    _calibration_block,
    _calibration_verdict,
    assemble_coach_context,
)


def test_calibration_verdict_overconfident():
    # observed < stated in both buckets → overconfident
    buckets = [
        {"n": 2, "observed_hit_rate": 0.5, "mean_confidence": 0.9},
        {"n": 1, "observed_hit_rate": 0.6, "mean_confidence": 0.8},
    ]
    assert "OVER-confident" in _calibration_verdict(buckets)


def test_calibration_verdict_underconfident():
    buckets = [{"n": 3, "observed_hit_rate": 0.9, "mean_confidence": 0.6}]
    assert "UNDER-confident" in _calibration_verdict(buckets)


def test_calibration_verdict_well_calibrated():
    buckets = [{"n": 3, "observed_hit_rate": 0.72, "mean_confidence": 0.70}]
    assert "well-calibrated" in _calibration_verdict(buckets)


def test_calibration_verdict_none_when_no_usable_buckets():
    assert _calibration_verdict([{"n": 0, "observed_hit_rate": None, "mean_confidence": None}]) is None


@pytest.fixture
def coach_profile(db):
    from apps.profiles.models import TradingProfile
    return TradingProfile.objects.create(
        name="Coached", style="swing", default_provider="claude",
        default_model="claude-sonnet-4-6", enable_coach=True,
    )


def test_calibration_block_renders_latest_run(coach_profile):
    from apps.aieval.services import persist_eval_run

    persist_eval_run(
        {"label": "scheduled", "model": "claude-sonnet-4-6", "n": 10, "scored": 8,
         "hit_rate": 0.625, "brier": 0.22,
         "calibration": [{"n": 8, "observed_hit_rate": 0.5, "mean_confidence": 0.85}]},
        source="scheduled",
    )
    block = _calibration_block(coach_profile)
    assert "Model calibration" in block
    assert "63%" in block or "62%" in block  # 0.625 formatted as a percentage
    assert "OVER-confident" in block


def test_calibration_block_empty_when_no_run(coach_profile):
    assert _calibration_block(coach_profile) == ""


def test_calibration_block_empty_for_mismatched_model(coach_profile):
    from apps.aieval.services import persist_eval_run

    persist_eval_run({"label": "x", "model": "claude-opus-4-8", "n": 5, "scored": 5,
                      "hit_rate": 0.8}, source="manual")
    # profile.default_model is sonnet; only an opus run exists → no block
    assert _calibration_block(coach_profile) == ""


def test_assemble_coach_context_includes_calibration(coach_profile):
    """End-to-end: the calibration block appears in the assembled coach context."""
    from apps.aieval.services import persist_eval_run
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.create(
        profile=coach_profile, includes=["quotes"], source="manual", status="ready",
    )
    snap.sections.create(kind="quotes", payload={"AAPL": {"last": 150.0}}, status="done")
    # primary_ticker must resolve to AAPL for the ticker gate; set it if the model
    # stores it explicitly, otherwise it derives from the first quotes key.
    persist_eval_run(
        {"label": "scheduled", "model": "claude-sonnet-4-6", "n": 6, "scored": 6,
         "hit_rate": 0.66, "brier": 0.2,
         "calibration": [{"n": 6, "observed_hit_rate": 0.66, "mean_confidence": 0.66}]},
        source="scheduled",
    )
    ctx = assemble_coach_context(snap, coach_profile)
    assert "Model calibration" in ctx
```

NOTE: confirm how `Snapshot.primary_ticker` resolves before finalizing the last test. If it derives from the first `quotes` key, the snapshot above yields `AAPL` and the ticker gate passes. If `primary_ticker` is a stored field that defaults empty, set it explicitly on the snapshot (e.g. `snap.primary_ticker = "AAPL"; snap.save()`), mirroring how `apps/aieval/tests/test_aieval.py::_snapshot` + existing coach call sites construct a primary-ticker-bearing snapshot. Adjust this one test to match the real mechanism — do not weaken the assertion.

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
docker compose exec web pytest apps/aieval/tests/test_aieval.py -k latest_eval_for_model -v
docker compose exec web pytest apps/threads/tests/test_coach.py -v
```
Expected: FAIL — `latest_eval_for_model`, `_calibration_block`, `_calibration_verdict` undefined.

- [ ] **Step 3: Add `latest_eval_for_model` to services.py**

In `backend/apps/aieval/services.py`:

```python
def latest_eval_for_model(model: str) -> "EvalRun | None":
    """Most recent persisted EvalRun for a given model id, or None."""
    if not model:
        return None
    return EvalRun.objects.filter(model=model).order_by("-created_at").first()
```

- [ ] **Step 4: Add the coach blocks**

In `backend/apps/threads/coach.py`, add these two functions (place them after `_lessons_block`, before `_situation_query`):

```python
def _calibration_verdict(buckets: list) -> str | None:
    """Over/under/well-confident verdict from the reliability buckets.

    Signed mean of (observed_hit_rate - mean_confidence) over non-empty buckets:
    negative => model's stated confidence outran realized accuracy (overconfident).
    Returns None when no bucket has both numbers.
    """
    diffs = [
        b["observed_hit_rate"] - b["mean_confidence"]
        for b in buckets
        if b.get("n")
        and b.get("observed_hit_rate") is not None
        and b.get("mean_confidence") is not None
    ]
    if not diffs:
        return None
    signed = sum(diffs) / len(diffs)
    if signed < -0.05:
        return "tends to be OVER-confident (stated confidence runs higher than realized accuracy)"
    if signed > 0.05:
        return "tends to be UNDER-confident (realized accuracy runs higher than stated confidence)"
    return "is well-calibrated (stated confidence ≈ realized accuracy)"


def _calibration_block(profile) -> str:
    """Measured calibration of the profile's model, from the latest EvalRun (A3).

    Lazy cross-app import (threads -> aieval) keeps the documented import-cycle
    discipline. Empty when no eval exists for this model or it scored nothing.
    """
    model = getattr(profile, "default_model", None)
    if not model:
        return ""
    from apps.aieval.services import latest_eval_for_model

    run = latest_eval_for_model(model)
    if run is None or not run.scored:
        return ""
    hr = f"{run.hit_rate:.0%}" if run.hit_rate is not None else "—"
    brier = f"{run.brier:.2f}" if run.brier is not None else "—"
    lines = [
        "### Model calibration (measured on your own past calls)",
        f"- {model} directional hit-rate over {run.scored} decisive past calls: "
        f"{hr} (Brier {brier}).",
    ]
    verdict = _calibration_verdict(run.calibration or [])
    if verdict:
        lines.append(f"- This model {verdict}. Weight your stated confidence accordingly.")
    return "\n".join(lines)
```

- [ ] **Step 5: Wire it into `assemble_coach_context`**

In `assemble_coach_context`, add the calibration block to the `sections` list (after `_lessons_block`):

```python
    sections = [
        _safe(lambda: _theses_block(ticker, snapshot)),
        _safe(lambda: _diff_block(snapshot)),
        _safe(lambda: _track_record_block(ticker)),
        _safe(lambda: _recall_block(snapshot, ticker)),
        _safe(lambda: _lessons_block(ticker)),
        _safe(lambda: _calibration_block(profile)),
    ]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run:
```bash
docker compose exec web pytest apps/aieval/tests/test_aieval.py -k latest_eval_for_model -v
docker compose exec web pytest apps/threads/tests/test_coach.py -v
```
Expected: PASS.

- [ ] **Step 7: Run the full aieval + coach suites to confirm no regressions**

Run:
```bash
docker compose exec web pytest apps/aieval/ apps/threads/tests/test_coach.py -v
```
Expected: PASS — including the pre-existing coach coverage (the new section is `_safe`-wrapped and empty when no EvalRun exists, so existing coach tests with no eval data are unaffected).

- [ ] **Step 8: Commit**

```bash
git add backend/apps/aieval/services.py backend/apps/threads/coach.py backend/apps/threads/tests/test_coach.py backend/apps/aieval/tests/test_aieval.py
git commit -m "feat(coach): inject measured model calibration into the coach context (A3)"
```

---

## Final verification (after all six tasks)

- [ ] **Run the full backend test suite + lint**

```bash
docker compose exec web pytest apps/aieval/ apps/threads/ apps/observer/ -q
make lint
```
Expected: green pytest; `ruff`/`ruff format`/frontend lint clean. (`ty` is advisory — a non-zero `ty` step is NOT a failure per CLAUDE.md.)

- [ ] **Confirm the migration is the only schema change + the beat task registered**

```bash
docker compose exec web python manage.py makemigrations --check --dry-run   # no pending changes
git log --oneline -6                                                         # six task commits
```

- [ ] **Update docs**

Mark Tier A3 / B1 / B2 / B3 + "schedule the harness" as **done** in `docs/superpowers/specs/2026-05-31-remaining-work.md` (leave A1, A2, and all of Tier C as remaining). Add a one-line CLAUDE.md note under the analytics/observer conventions describing the new `/api/aieval/runs/` surface + the opt-in scheduled harness + the coach calibration block. Commit as `docs:`.

- [ ] **STOP — do not push.** Per the standing "autonomous build, no push" directive: report the six local commits and await explicit confirmation before any `git push` / PR / merge.

---

## Self-Review (completed during planning)

**Spec coverage:** Every item in the doc's recommended M7 thread is covered — B3 (Tasks 2+3), schedule (Task 5), A3 (Task 6), B1 (Task 1), B2 (Task 4). Deferred-by-design (A1 `?since=`, A2 snapshot-free coach) and Tier C one-offs are intentionally out of scope per the doc ("independent cherry-picks by appetite") and the A3 note that the ticker-gate stays until A2 is designed.

**Type consistency:** `evaluate()` result keys (`label/model/horizon/n/skipped/scored/hit_rate/brier/avg_confidence/calibration/calibration_error/examples`) map 1:1 to `EvalRun` columns and `persist_eval_run`'s `.get(...)` calls. `preflight_cost_cap` matches `check_daily_cap(provider, cap_usd, prospective_cost=0)` / `check_monthly_cap(provider, cap_usd|None, ...)`. `_calibration_block` reads `profile.default_model` (real field, default `claude-sonnet-4-6`) and `EvalRun.scored/hit_rate/brier/calibration`. `DEFAULT_EVAL_SYSTEM` is defined once in services.py and imported by both the command and the task.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; two NOTE callouts (AIRun field names in Task 4, `primary_ticker` resolution in Task 6) flag a fact to confirm against the real code before writing the test — with an explicit "do not weaken the assertion" instruction, not a placeholder.
