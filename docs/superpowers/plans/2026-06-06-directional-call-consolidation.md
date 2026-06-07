# DirectionalCall / Resolution Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the duplicated "a directional call + how it scored" domain — currently modelled 4–5× across `thesis.PostMortem`, `predictions.AIPrediction`, `coverage.CoverageNote`, `aieval.EvalRun` — by introducing shared abstract bases (`Resolution`, `DirectionalCall`, `TimeStamped`) in `apps.core`, one canonical verdict vocabulary + resolution function, and a single calibration read-model that the scorecard, Mirror, and Coach all consume.

**Architecture:** Three phases, each independently shippable and the first two **non-destructive** (no column data changes — moving a field definition into an identical abstract base produces a state-only migration). Phase 1 factors the shared columns/logic into `apps.core` abstract bases + `apps.market.returns`. Phase 2 unifies the read path behind one `calibration` service. Phase 3 collapses redundant UI/Coach surfaces. EvalRun (a batch *aggregate*, not a per-call resolution) and CoverageNote (a mutable *house view*, not a scored call) are kept as distinct shapes but plugged into the unified read-model rather than re-modelled.

**Tech Stack:** Django 5 / Postgres 17 / DRF / pytest-django. All work runs in Docker (`make test`, `make migrate`, `make check-migrations`, `make lint-imports`).

---

## Background — the evidence (verified 2026-06-06)

| Model | "call" fields | "resolution" fields | lifecycle |
|---|---|---|---|
| `thesis.Thesis` | `ticker, direction(16), conviction(1..5), horizon_days, invalidation_price/note` | — (resolved via PostMortem) | `open → closed` |
| `thesis.PostMortem` | (FK thesis) `horizon_days` | `forward_return_pct, verdict(16), completed_at, report` | `scheduled → running → …` |
| `predictions.AIPrediction` | `ticker, direction(8), confidence(0..1), horizon_days, invalidation_price/note` | `forward_return_pct, verdict(12), resolved_at, invalidated_at` | `open → resolving → resolved` |
| `aieval.EvalRun` | — (batch) | `hit_rate, brier, calibration_error` (aggregate) | one-shot |
| `coverage.CoverageNote` | `ticker, stance, conviction(1..5)` | — (mutable rollup) | n/a |

`PostMortem.forward_return_pct` (`thesis/models.py:172`) and `AIPrediction.forward_return_pct` (`predictions/models.py:69`) are byte-identical; `verdict` differs only in `max_length` (16 vs 12) and choices-list location. Resolution logic is forked: `thesis.services.postmortem.objective_verdict` vs `predictions.services…direction_verdict`. Calibration is read by hand-joining three subsystems (`PostMortem⋈Thesis`, `AIRun⋈Message⋈Thread`, `EvalRun`) in `analytics/calibration.py`, `analytics/trader_calibration.py`, and `threads/coach.py` (11 context blocks, 3 of them calibration).

**Canonical decisions (lock these before Task 1):**
- **Verdict vocabulary:** `("correct","incorrect","mixed","inconclusive")`, `max_length=16`. (Superset of both; AIPrediction widens 12→16 — a safe `AlterField`.)
- **Direction vocabulary:** `("bullish","bearish","neutral")`, `max_length=16`. (AIPrediction widens 8→16.)
- **Abstract bases live in `apps.core`** (the lowest import layer — every app may import it; avoids the `thesis→analytics` up-edge an analytics-hosted base would create).
- **Verdict computation** (`objective_verdict`, `direction_verdict`) consolidates into `apps.market.returns` (already the shared forward-return helper, already imported by both analytics and post-mortems; `market` is a low layer).

---

## File Structure

- `backend/apps/core/model_bases.py` **(create)** — `TimeStamped`, `Resolution`, `DirectionalCall` abstract models + `VERDICT_CHOICES`, `DIRECTION_CHOICES`.
- `backend/apps/market/returns.py` **(modify)** — add canonical `verdict_for(direction, forward_return_pct)` (the deterministic DEADZONE=1% truth-table) used by both resolution paths.
- `backend/apps/thesis/models.py` **(modify)** — `PostMortem(Resolution, models.Model)`; drop its now-inherited columns.
- `backend/apps/predictions/models.py` **(modify)** — `AIPrediction(DirectionalCall, Resolution, models.Model)`; drop inherited columns; widen verdict/direction.
- `backend/apps/thesis/services/postmortem.py`, `backend/apps/predictions/services/resolve.py` **(modify)** — call `returns.verdict_for`; use `Resolution.claim()`.
- `backend/apps/analytics/services/calibration_unified.py` **(create)** — one read-model: a normalized `ScoredCall` row per resolved PostMortem + AIPrediction, plus EvalRun aggregates.
- `backend/apps/analytics/calibration.py`, `trader_calibration.py`, `backend/apps/threads/coach.py` **(modify, Phase 2/3)** — consume the unified read-model; collapse duplicate calibration blocks.

---

## Phase 1 — Shared abstract bases (non-destructive)

### Task 1: `Resolution` + `DirectionalCall` + `TimeStamped` abstract bases

**Files:** Create `backend/apps/core/model_bases.py`; Test `backend/apps/core/tests/test_model_bases.py`.

- [ ] **Step 1 — Write the failing test**

```python
# backend/apps/core/tests/test_model_bases.py
import pytest
from apps.core.model_bases import Resolution, VERDICT_CHOICES

pytestmark = pytest.mark.django_db


def test_claim_is_idempotent():
    # PostMortem already inherits Resolution after Task 3; here we assert the
    # contract on a concrete inheritor via the predictions model (Task 4) OR a
    # throwaway test model. Use AIPrediction once Task 4 lands; for Task 1 use a
    # minimal concrete subclass registered under the tests app.
    from apps.predictions.models import AIPrediction  # available after Task 4
    p = AIPrediction.objects.create(  # ...minimal valid kwargs...
        ticker="AAPL", direction="bullish", horizon_days=7, confidence=0.6,
        provider="claude", model="claude-opus-4-8",
        predicted_at="2026-01-01T00:00:00Z", resolve_at="2026-01-08T00:00:00Z",
    )
    assert AIPrediction.claim(p.pk, frm="open", to="resolving") is True
    assert AIPrediction.claim(p.pk, frm="open", to="resolving") is False  # already claimed


def test_verdict_choices_are_canonical():
    assert [c[0] for c in VERDICT_CHOICES] == ["correct", "incorrect", "mixed", "inconclusive"]
```

- [ ] **Step 2 — Run it, watch it fail**
  `make test` target file: `apps/core/tests/test_model_bases.py` — Expected: ImportError (`apps.core.model_bases` missing).

- [ ] **Step 3 — Implement the bases**

```python
# backend/apps/core/model_bases.py
"""Shared abstract model bases. Lowest import layer — any app may import these."""
from __future__ import annotations

from typing import ClassVar

from django.db import models

VERDICT_CHOICES: list[tuple[str, str]] = [
    ("correct", "Correct"),
    ("incorrect", "Incorrect"),
    ("mixed", "Mixed"),
    ("inconclusive", "Inconclusive"),
]
DIRECTION_CHOICES: list[tuple[str, str]] = [
    ("bullish", "Bullish"),
    ("bearish", "Bearish"),
    ("neutral", "Neutral"),
]


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DirectionalCall(models.Model):
    """A stated directional call on a ticker (shared by Thesis and AIPrediction)."""
    ticker = models.CharField(max_length=16, db_index=True)
    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES)
    horizon_days = models.PositiveIntegerField()
    invalidation_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    invalidation_note = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        abstract = True


class Resolution(models.Model):
    """Outcome of a directional call: the scored result + idempotent claim."""
    forward_return_pct = models.FloatField(null=True, blank=True)
    verdict = models.CharField(max_length=16, choices=VERDICT_CHOICES, blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    @classmethod
    def claim(cls, pk: int, *, frm: str, to: str) -> bool:
        """Atomic compare-and-set on the concrete model's ``status`` field.
        Returns True for the single caller that wins the transition, else False.
        Concrete models keep their own ``status`` choices; this only moves it."""
        return cls.objects.filter(pk=pk, status=frm).update(status=to) == 1
```

- [ ] **Step 4 — Run the test, watch it pass** (after Task 4 the `claim` test passes; for Task 1 land only `test_verdict_choices_are_canonical`, then expand in Task 4).
- [ ] **Step 5 — Commit:** `git commit -m "feat(core): shared Resolution/DirectionalCall/TimeStamped model bases"`

### Task 2: canonical `verdict_for` in `apps.market.returns`

**Files:** Modify `backend/apps/market/returns.py`; Test `backend/apps/market/tests/test_returns_verdict.py`.

- [ ] **Step 1 — Failing test** (move the existing post-mortem truth-table assertions here; DEADZONE 1%):

```python
from apps.market.returns import verdict_for

def test_verdict_truth_table():
    assert verdict_for("bullish", 5.0) == "correct"
    assert verdict_for("bullish", -5.0) == "incorrect"
    assert verdict_for("bearish", -5.0) == "correct"
    assert verdict_for("neutral", 0.2) == "correct"      # within deadzone
    assert verdict_for("bullish", 0.2) == "inconclusive"  # inside deadzone, directional
    assert verdict_for("bullish", None) == "inconclusive"
```

- [ ] **Step 2 — Run, watch fail** (function missing).
- [ ] **Step 3 — Implement** `verdict_for` by lifting the body of `thesis.services.postmortem.objective_verdict` (the DEADZONE=1.0 logic) into `returns.py`, returning a `VERDICT_CHOICES` key. Import `VERDICT_CHOICES` from `apps.core.model_bases`.
- [ ] **Step 4 — Run, watch pass.**
- [ ] **Step 5 — Commit:** `git commit -m "refactor(market): canonical verdict_for in returns.py"`

### Task 3: retrofit `PostMortem` onto `Resolution` (state-only migration)

**Files:** Modify `backend/apps/thesis/models.py`, `backend/apps/thesis/services/postmortem.py`.

- [ ] **Step 1 — Failing test:** assert `PostMortem` exposes the base API and resolution still works end-to-end:

```python
def test_postmortem_uses_shared_resolution(db):
    from apps.thesis.models import PostMortem
    from apps.core.model_bases import Resolution
    assert issubclass(PostMortem, Resolution)
    # existing objective-verdict behaviour unchanged:
    # (reuse an existing post-mortem fixture; assert verdict/forward_return_pct populate)
```

- [ ] **Step 2 — Run, watch fail** (`issubclass` False).
- [ ] **Step 3 — Implement:** change `class PostMortem(models.Model)` → `class PostMortem(Resolution, models.Model)`; **delete** the now-inherited `forward_return_pct` and `verdict` field lines (keep `status`, `completed_at`, `report`, FKs — they're PostMortem-specific). In `postmortem.py`, replace `objective_verdict(...)` with `returns.verdict_for(thesis.direction, fwd)` and replace the `filter(status="scheduled").update(status="running")` claim with `PostMortem.claim(pm_id, frm="scheduled", to="running")`.
- [ ] **Step 4 — Generate migration & verify it's state-only:**
  `make makemigrations` → inspect: the `verdict` field is unchanged (already max_length=16) so expect **no DB column change**, only a state migration (or empty). Run `make check-migrations` (must pass). Run the thesis suite: `apps/thesis`.
- [ ] **Step 5 — Commit:** `git commit -m "refactor(thesis): PostMortem inherits core.Resolution"`

### Task 4: retrofit `AIPrediction` onto `DirectionalCall` + `Resolution`

**Files:** Modify `backend/apps/predictions/models.py`, `backend/apps/predictions/services/resolve.py` (+ `extract.py` if it builds verdict).

- [ ] **Step 1 — Failing test:** `issubclass(AIPrediction, (DirectionalCall, Resolution))` + a resolve test asserting verdict via `verdict_for`.
- [ ] **Step 2 — Run, watch fail.**
- [ ] **Step 3 — Implement:** `class AIPrediction(DirectionalCall, Resolution, models.Model)`; delete inherited fields (`ticker, direction, horizon_days, invalidation_price, invalidation_note, forward_return_pct, verdict, resolved_at`). **Note the widenings:** `direction` 8→16, `verdict` 12→16 (now from the base). Keep AIPrediction-specific fields (`confidence, rationale, provider, model, source_message, source_snapshot, profile, predicted_at, resolve_at, invalidated_at, status`). Replace the `open→resolving` claim with `AIPrediction.claim(pk, frm="open", to="resolving")` and verdict with `returns.verdict_for`.
- [ ] **Step 4 — Migration:** `make makemigrations` → expect a real `AlterField` for `direction` (8→16) and `verdict` (12→16) only. `make check-migrations`; run `apps/predictions`.
- [ ] **Step 5 — Commit:** `git commit -m "refactor(predictions): AIPrediction inherits core DirectionalCall+Resolution"`

**Phase 1 exit gate:** `make check` green; `make migrate` clean on a fresh DB; no behaviour change (calibration numbers identical).

---

## Phase 2 — Unified calibration read-model

### Task 5: `ScoredCall` read-model

**Files:** Create `backend/apps/analytics/services/calibration_unified.py`; Test `backend/apps/analytics/tests/test_calibration_unified.py`.

- [ ] **Step 1 — Failing test:** seed one resolved `PostMortem` (user call) and one resolved `AIPrediction` (AI call); assert `scored_calls(horizon=7)` yields two normalized rows with `{source, ticker, direction, conviction_or_confidence, verdict, forward_return_pct, resolved_at}` and that `source` ∈ {"user","ai"}.
- [ ] **Step 2 — Run, watch fail.**
- [ ] **Step 3 — Implement** a single function that `UNION`s a normalized projection of decisive `PostMortem⋈Thesis` and resolved `AIPrediction` (both now share `Resolution` fields, so the projection is symmetric), filtering `verdict != "inconclusive"`. Expose `scored_calls(horizon=None, source=None)` returning dataclass rows.
- [ ] **Step 4 — Run, watch pass.**
- [ ] **Step 5 — Commit:** `git commit -m "feat(analytics): unified ScoredCall calibration read-model"`

### Task 6: point `calibration.py` / `trader_calibration.py` at the read-model

- [ ] Per-file TDD: add a characterization test capturing current scorecard JSON for a fixed fixture **before** refactor; refactor each aggregator to build on `scored_calls(...)`; assert byte-identical output. Commit per file.

**Phase 2 exit gate:** scorecard + Mirror endpoints return identical payloads for the seed fixture; `make check` green.

---

## Phase 3 — Collapse redundant surfaces (decision-gated)

These are **subtractive** and need a product decision (see `2026-06-06-app-consolidation-27-to-12.md` for the matching app moves):

- [ ] **Coach diet:** the Coach injects 11 blocks incl. 3 calibration sources (`_calibration_block`, `_cohort_block`, `_distilled_lessons_block`, + ai/track-record). Replace the 3 calibration blocks with **one** block built from `scored_calls`. Add a test asserting the assembled coach context contains exactly one calibration section. Commit.
- [ ] **Pick one self-calibration UI:** `scorecard` (`/scorecard`) and Mirror (`/mirror`) are two joins over the same population. Keep `scorecard`; fold the genuinely-distinct Mirror signal ("you passed on winners") in as a section, or delete Mirror. (Product call — do not delete without sign-off.)
- [ ] **CoverageNote stays** (it is a mutable house view, not a scored call) but its `conviction` should reuse the 1..5 scale constant; `Lesson` stays (distilled cluster). No model merge for these.

**Phase 3 exit gate:** one calibration block in the coach; one self-calibration page; `make check` green; net LOC down (target ≥ −1,200 / removal of one page + 2 coach blocks).

---

## Risks & mitigations

- **Cross-app abstract inheritance:** abstract bases create no tables and no FKs, so `thesis`/`predictions` importing `apps.core.model_bases` is a clean down-edge (core is the lowest layer). Verify with `make lint-imports`.
- **State-only migrations:** moving an *identical* field into a base must not emit a column op. Always run `make check-migrations` and read the generated migration before committing; if Django emits an unexpected `AlterField`, the base field definition diverged from the original — align it.
- **Status-label divergence:** PostMortem (`scheduled/running`) and AIPrediction (`open/resolving/resolved`) keep their own `status`; only the generic `claim()` is shared. Do **not** attempt to unify status labels in this plan (separate, data-migration-bearing change).
- **Look-ahead safety preserved:** the read-model reads only decisive, resolved rows — keep the `inconclusive`/unresolved exclusion that calibration already enforces.

## Self-review checklist
- [ ] Every model in the Background table is addressed (PostMortem ✓, AIPrediction ✓, EvalRun = aggregate source ✓, CoverageNote/Lesson = kept, justified ✓).
- [ ] No placeholders; canonical vocab + max_lengths stated.
- [ ] Names consistent: `Resolution.claim(pk, frm=, to=)`, `returns.verdict_for(direction, fwd)`, `scored_calls(horizon=, source=)` used identically across tasks.
