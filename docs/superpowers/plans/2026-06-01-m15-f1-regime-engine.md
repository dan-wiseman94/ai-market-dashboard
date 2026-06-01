# M15 F1 — Regime Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A scheduled, deterministic-core + best-effort-AI market **regime classifier** (`RegimeReading`) that alerts on regime change, injects a regime block into the decision coach everywhere (incl. bare chats), and surfaces on a Dashboard tile + a `/regime` page.

**Architecture:** A new `apps.regime` Django app. A pure-functional classifier (`services/classify.py`) maps best-effort raw inputs (`services/inputs.py`, composed from the existing `market.services.context`/`fred` + `OHLCBar`) to five independent axis labels + a folded composite. `services/compute.py` orchestrates compute→persist→change-alert; `services/narrative.py` layers an optional Claude paragraph (degrades to `""`). A market-hours-gated beat task produces readings; DRF views + a React page/tile expose them; `threads/coach.py` consumes the latest reading.

**Tech Stack:** Django 5 + DRF, Celery (beat), Postgres, `pydantic` (structured narrative), React + TanStack Query + Vite, pytest + vitest. Everything runs in Docker (`docker compose exec web …` / `frontend …`).

**Conventions for every task:**
- Backend tests run in-container, WORKDIR `/app/backend` (drop the `backend/` path prefix): `docker compose exec web pytest apps/regime/tests/test_x.py -v`.
- All commits are conventional (`feat(regime): …`) and end with the repo's trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- `run_structured` has **no `MOCK_EXTERNAL` short-circuit** → patch it directly in tests. Never set `MOCK_EXTERNAL` on the dev stack.
- After adding the beat task/schedule entry (Task 7): `docker compose restart worker beat` (worker/beat don't hot-reload).

---

## File structure

**Create (all under `backend/apps/regime/`):**
- `__init__.py`, `apps.py` — app config (`label = "regime"`).
- `constants.py` — axis thresholds (single source of truth, tunable).
- `models.py` — `RegimeReading`.
- `migrations/__init__.py`, `migrations/0001_initial.py` (generated).
- `services/__init__.py`
- `services/classify.py` — pure axis classifiers + `fold_composite` + `build_drivers`.
- `services/inputs.py` — best-effort raw-input gathering.
- `services/compute.py` — `compute_and_store`, `current_regime`, `changed_axes`, `_notify_change`.
- `services/narrative.py` — best-effort Claude narrative.
- `tasks.py` — `regime.refresh` beat task.
- `serializers.py`, `views.py`, `urls.py`.
- `tests/__init__.py` + `tests/test_classify.py`, `test_model.py`, `test_inputs.py`, `test_compute.py`, `test_narrative.py`, `test_tasks.py`, `test_views.py`.

**Modify:**
- `backend/config/settings/base.py` — `INSTALLED_APPS += ["apps.regime"]`.
- `backend/config/urls.py` — `path("api/regime/", include("apps.regime.urls"))` **before** the generic `/api/` include.
- `backend/config/celery.py` — add `"apps.regime"` to `autodiscover_tasks([...])` + a `beat_schedule` entry.
- `backend/apps/observer/models.py` — add `("regime", "Regime")` to `Notification.KIND_CHOICES` (+ migration).
- `backend/apps/threads/coach.py` — `_regime_block()` + wire into both assembly functions.
- `backend/apps/dashboard/views.py` — `_regime_section()` + payload key with a contract-valid default.
- `frontend/src/api/regime.ts` (create), `frontend/src/hooks/useRegime.ts` (create), `frontend/src/pages/RegimePage.tsx` (create), `frontend/src/components/RegimeTile.tsx` (create).
- `frontend/src/router.tsx` — `/regime` route; `frontend/src/pages/Dashboard.tsx` — mount `RegimeTile`.

---

## Task 1: Scaffold `apps.regime` app + wiring

**Files:**
- Create: `backend/apps/regime/__init__.py` (empty), `backend/apps/regime/migrations/__init__.py` (empty), `backend/apps/regime/services/__init__.py` (empty), `backend/apps/regime/tests/__init__.py` (empty)
- Create: `backend/apps/regime/apps.py`, `backend/apps/regime/constants.py`, `backend/apps/regime/urls.py`
- Modify: `backend/config/settings/base.py`, `backend/config/urls.py`, `backend/config/celery.py`

- [ ] **Step 1: Create the AppConfig**

`backend/apps/regime/apps.py`:
```python
from django.apps import AppConfig


class RegimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.regime"
    label = "regime"
```

- [ ] **Step 2: Create constants**

`backend/apps/regime/constants.py`:
```python
"""Regime classifier thresholds — single source of truth, tunable later."""

# Volatility (VIX level)
VIX_LOW = 14.0
VIX_ELEVATED = 20.0
VIX_STRESS = 30.0
VIX_PERCENTILE_WINDOW = 252  # trading days of $VIX history for the percentile

# Trend ($SPX moving averages)
MA_FAST = 50
MA_SLOW = 200

# Breadth (advance/decline ratio + TRIN)
BREADTH_BROAD = 0.60
BREADTH_NARROW = 0.40
TRIN_DETERIORATING = 2.0

# Leadership (offensive vs defensive sector ETF N-day return spread, pct points)
OFFENSIVE_ETFS = ["XLK", "XLY", "XLC"]
DEFENSIVE_ETFS = ["XLU", "XLP", "XLV"]
LEADERSHIP_SPREAD = 1.0
SECTOR_RETURN_WINDOW = 20  # trading days

# Composite scoring thresholds
COMPOSITE_RISK_ON = 2
COMPOSITE_RISK_OFF = -2

UNKNOWN = "Unknown"
```

- [ ] **Step 3: Create an empty urls module (views added in Task 8)**

`backend/apps/regime/urls.py`:
```python
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
# ViewSets registered in Task 8.
urlpatterns = router.urls
```

- [ ] **Step 4: Wire INSTALLED_APPS, urls, celery autodiscover**

In `backend/config/settings/base.py`, add `"apps.regime",` to the project-apps section of `INSTALLED_APPS`.

In `backend/config/urls.py`, add **before** the generic `/api/` include (order matters — see CLAUDE.md):
```python
    path("api/regime/", include("apps.regime.urls")),
```

In `backend/config/celery.py`, add `"apps.regime",` to the `autodiscover_tasks([...])` list (beat entry comes in Task 7).

- [ ] **Step 5: Verify the app loads**

Run: `docker compose exec web python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/regime backend/config/settings/base.py backend/config/urls.py backend/config/celery.py
git commit -m "feat(regime): scaffold apps.regime + wiring (M15 F1)"
```

---

## Task 2: Axis classifiers + composite (pure logic)

**Files:**
- Create: `backend/apps/regime/services/classify.py`
- Test: `backend/apps/regime/tests/test_classify.py`

- [ ] **Step 1: Write the failing tests**

`backend/apps/regime/tests/test_classify.py`:
```python
import pytest

from apps.regime.services import classify as c


@pytest.mark.parametrize(
    "vix,expected",
    [(10.0, "Low"), (16.0, "Normal"), (24.0, "Elevated"), (35.0, "Stress"), (None, "Unknown")],
)
def test_classify_volatility(vix, expected):
    assert c.classify_volatility(vix) == expected


@pytest.mark.parametrize(
    "ma_spread,dist50,expected",
    [
        (5.0, 3.0, "Uptrend"),
        (-4.0, -2.0, "Downtrend"),
        (5.0, -1.0, "Range"),
        (None, None, "Unknown"),
    ],
)
def test_classify_trend(ma_spread, dist50, expected):
    assert c.classify_trend(ma_spread, dist50) == expected


@pytest.mark.parametrize(
    "breadth,expected",
    [
        ({"$ADVN": 2000, "$DECN": 800}, "Broad"),
        ({"$ADVN": 800, "$DECN": 2000}, "Narrow"),
        ({"$ADVN": 1000, "$DECN": 1000}, "Mixed"),
        ({"$ADVN": 1500, "$DECN": 1000, "$TRIN": 2.5}, "Deteriorating"),
        ({}, "Unknown"),
    ],
)
def test_classify_breadth(breadth, expected):
    assert c.classify_breadth(breadth) == expected


@pytest.mark.parametrize(
    "rets,expected",
    [
        ({"XLK": 3.0, "XLY": 2.0, "XLC": 2.0, "XLU": 0.0, "XLP": 0.0, "XLV": 0.0}, "Offensive"),
        ({"XLK": -2.0, "XLY": -2.0, "XLC": -2.0, "XLU": 1.0, "XLP": 1.0, "XLV": 1.0}, "Defensive"),
        ({"XLK": 1.0, "XLY": 1.0, "XLC": 1.0, "XLU": 0.8, "XLP": 0.8, "XLV": 0.8}, "Mixed"),
        ({"XLK": 1.0}, "Unknown"),
    ],
)
def test_classify_leadership(rets, expected):
    assert c.classify_leadership(rets) == expected


@pytest.mark.parametrize(
    "t10y2y,tnx_change,expected",
    [
        (-0.3, 0.0, "Inverted"),
        (0.5, 0.05, "Tightening"),
        (0.5, -0.05, "Easing"),
        (0.5, 0.0, "Steepening"),
        (None, None, "Unknown"),
    ],
)
def test_classify_rates(t10y2y, tnx_change, expected):
    assert c.classify_rates(t10y2y, tnx_change) == expected


def test_fold_composite_risk_on():
    axes = {"volatility": "Low", "trend": "Uptrend", "breadth": "Broad",
            "leadership": "Offensive", "rates": "Easing"}
    assert c.fold_composite(axes) == "Risk-On"


def test_fold_composite_risk_off():
    axes = {"volatility": "Elevated", "trend": "Downtrend", "breadth": "Narrow",
            "leadership": "Defensive", "rates": "Inverted"}
    assert c.fold_composite(axes) == "Risk-Off"


def test_fold_composite_stress_short_circuit():
    axes = {"volatility": "Stress", "trend": "Uptrend", "breadth": "Broad",
            "leadership": "Offensive", "rates": "Easing"}
    assert c.fold_composite(axes) == "Stress"


def test_fold_composite_neutral_when_mixed_or_unknown():
    axes = {"volatility": "Normal", "trend": "Range", "breadth": "Unknown",
            "leadership": "Unknown", "rates": "Unknown"}
    assert c.fold_composite(axes) == "Neutral-Transitional"


def test_build_drivers_skips_unknown():
    axes = {"volatility": "Elevated", "trend": "Downtrend", "breadth": "Unknown",
            "leadership": "Unknown", "rates": "Unknown"}
    inp = {"vix_last": 24.0, "vix_percentile": 0.82}
    drivers = c.build_drivers(axes, inp)
    assert any("VIX 24" in d for d in drivers)
    assert all("Unknown" not in d for d in drivers)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec web pytest apps/regime/tests/test_classify.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.regime.services.classify` / `AttributeError`.

- [ ] **Step 3: Implement the classifier**

`backend/apps/regime/services/classify.py`:
```python
"""Pure regime classifiers: raw inputs -> axis labels -> composite.

Every function is total (handles None / empty -> "Unknown") and side-effect free,
so it is exhaustively unit-testable without any DB or network.
"""

from __future__ import annotations

from apps.regime import constants as C

UNKNOWN = C.UNKNOWN


def classify_volatility(vix_last: float | None, vix_percentile: float | None = None) -> str:
    if vix_last is None:
        return UNKNOWN
    v = float(vix_last)
    if v >= C.VIX_STRESS:
        return "Stress"
    if v >= C.VIX_ELEVATED:
        return "Elevated"
    if v >= C.VIX_LOW:
        return "Normal"
    return "Low"


def classify_trend(ma_spread: float | None, dist_50: float | None) -> str:
    if ma_spread is None and dist_50 is None:
        return UNKNOWN
    above_50 = dist_50 is not None and dist_50 > 0
    golden = ma_spread is not None and ma_spread > 0
    if above_50 and golden:
        return "Uptrend"
    below_50 = dist_50 is not None and dist_50 < 0
    death = ma_spread is not None and ma_spread < 0
    if below_50 and death:
        return "Downtrend"
    return "Range"


def classify_breadth(breadth: dict) -> str:
    advn = breadth.get("$ADVN")
    decn = breadth.get("$DECN")
    trin = breadth.get("$TRIN")
    if advn is None or decn is None or (advn + decn) == 0:
        return UNKNOWN
    if trin is not None and trin >= C.TRIN_DETERIORATING:
        return "Deteriorating"
    ratio = advn / (advn + decn)
    if ratio >= C.BREADTH_BROAD:
        return "Broad"
    if ratio <= C.BREADTH_NARROW:
        return "Narrow"
    return "Mixed"


def classify_leadership(sector_returns: dict) -> str:
    off = [sector_returns[t] for t in C.OFFENSIVE_ETFS if t in sector_returns]
    deff = [sector_returns[t] for t in C.DEFENSIVE_ETFS if t in sector_returns]
    if not off or not deff:
        return UNKNOWN
    spread = (sum(off) / len(off)) - (sum(deff) / len(deff))
    if spread >= C.LEADERSHIP_SPREAD:
        return "Offensive"
    if spread <= -C.LEADERSHIP_SPREAD:
        return "Defensive"
    return "Mixed"


def classify_rates(t10y2y: float | None, tnx_change: float | None) -> str:
    if t10y2y is None:
        return UNKNOWN
    if t10y2y < 0:
        return "Inverted"
    if tnx_change is not None and tnx_change > 0:
        return "Tightening"
    if tnx_change is not None and tnx_change < 0:
        return "Easing"
    return "Steepening"


_RISK_ON = {
    "volatility": {"Low", "Normal"},
    "trend": {"Uptrend"},
    "breadth": {"Broad"},
    "leadership": {"Offensive"},
    "rates": {"Easing", "Steepening"},
}
_RISK_OFF = {
    "volatility": {"Elevated"},
    "trend": {"Downtrend"},
    "breadth": {"Narrow", "Deteriorating"},
    "leadership": {"Defensive"},
    "rates": {"Inverted", "Tightening"},
}


def fold_composite(axes: dict[str, str]) -> str:
    if axes.get("volatility") == "Stress":
        return "Stress"
    score = 0
    for axis, label in axes.items():
        if label in _RISK_ON.get(axis, set()):
            score += 1
        elif label in _RISK_OFF.get(axis, set()):
            score -= 1
    if score >= C.COMPOSITE_RISK_ON:
        return "Risk-On"
    if score <= C.COMPOSITE_RISK_OFF:
        return "Risk-Off"
    return "Neutral-Transitional"


def build_drivers(axes: dict[str, str], inp: dict) -> list[str]:
    drivers: list[str] = []
    vix = inp.get("vix_last")
    if vix is not None:
        s = f"VIX {float(vix):.0f}"
        pct = inp.get("vix_percentile")
        if pct is not None:
            s += f" ({pct:.0%}ile)"
        drivers.append(f"{s} — {axes.get('volatility')}")
    for axis, prefix in [
        ("trend", "SPX trend"),
        ("breadth", "breadth"),
        ("leadership", None),
        ("rates", "rates"),
    ]:
        label = axes.get(axis)
        if not label or label == UNKNOWN:
            continue
        if axis == "leadership":
            drivers.append(f"{label} leadership")
        else:
            drivers.append(f"{prefix} {label}")
    return drivers
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/regime/tests/test_classify.py -v`
Expected: PASS (all parametrized cases green).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/regime/services/classify.py backend/apps/regime/tests/test_classify.py
git commit -m "feat(regime): pure axis classifiers + composite folding (M15 F1)"
```

---

## Task 3: `RegimeReading` model + `current_regime()`

**Files:**
- Create: `backend/apps/regime/models.py`, `backend/apps/regime/services/compute.py` (just `current_regime` for now)
- Create (generated): `backend/apps/regime/migrations/0001_initial.py`
- Test: `backend/apps/regime/tests/test_model.py`

- [ ] **Step 1: Write the failing test**

`backend/apps/regime/tests/test_model.py`:
```python
import pytest

from apps.regime.models import RegimeReading
from apps.regime.services.compute import current_regime

pytestmark = pytest.mark.django_db


def test_current_regime_returns_latest():
    RegimeReading.objects.create(composite="Risk-On", axes={"volatility": "Low"})
    latest = RegimeReading.objects.create(composite="Risk-Off", axes={"volatility": "Elevated"})
    assert current_regime().id == latest.id


def test_current_regime_none_when_empty():
    assert current_regime() is None


def test_str():
    r = RegimeReading.objects.create(composite="Stress", axes={})
    assert "Stress" in str(r)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/regime/tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.regime.models`.

- [ ] **Step 3: Implement model + accessor**

`backend/apps/regime/models.py`:
```python
from __future__ import annotations

from typing import ClassVar

from django.db import models


class RegimeReading(models.Model):
    """One classified market-regime reading. Append-only; the latest row is the
    current regime (see services.compute.current_regime)."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    composite = models.CharField(max_length=20)  # "Risk-On" / "Neutral-Transitional" / "Risk-Off" / "Stress"
    axes = models.JSONField(default=dict)  # {"volatility": "Elevated", "trend": "Downtrend", ...}
    drivers = models.JSONField(default=list)  # ["VIX 24 (82%ile) — Elevated", ...]
    narrative = models.TextField(blank=True, default="")
    inputs = models.JSONField(default=dict)  # raw values, for reproducibility
    changed_axes = models.JSONField(default=list)  # axis names that flipped vs the prior reading

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"RegimeReading({self.composite} @ {self.created_at:%Y-%m-%d %H:%M})"
```

`backend/apps/regime/services/compute.py`:
```python
from __future__ import annotations

from apps.regime.models import RegimeReading


def current_regime() -> RegimeReading | None:
    """The latest reading, or None when no reading has been produced yet."""
    return RegimeReading.objects.order_by("-created_at").first()
```

- [ ] **Step 4: Generate the migration**

Run: `docker compose exec web python manage.py makemigrations regime`
Expected: creates `apps/regime/migrations/0001_initial.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec web pytest apps/regime/tests/test_model.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/regime/models.py backend/apps/regime/services/compute.py backend/apps/regime/migrations/0001_initial.py backend/apps/regime/tests/test_model.py
git commit -m "feat(regime): RegimeReading model + current_regime() (M15 F1)"
```

---

## Task 4: Best-effort input gathering

**Files:**
- Create: `backend/apps/regime/services/inputs.py`
- Test: `backend/apps/regime/tests/test_inputs.py`

- [ ] **Step 1: Write the failing test**

`backend/apps/regime/tests/test_inputs.py`:
```python
import pytest
from django.utils import timezone

from apps.market.models import OHLCBar
from apps.regime.services import inputs as I

pytestmark = pytest.mark.django_db


def _seed_daily(ticker, closes):
    base = timezone.now()
    for i, px in enumerate(closes):
        OHLCBar.objects.create(
            ticker=ticker, timeframe="1d", open=px, high=px, low=px, close=px,
            volume=1, ts=base - timezone.timedelta(days=len(closes) - i),
        )


def test_gather_inputs_shape_and_degradation(monkeypatch):
    # No market data, no macro -> everything degrades, never raises.
    monkeypatch.setattr(I, "fetch_market_context", lambda: {"vix_last": 22.0, "breadth": {"$ADVN": 1500, "$DECN": 900}})
    monkeypatch.setattr(I, "fetch_macro", lambda ids: {})
    out = I.gather_inputs()
    assert out["vix_last"] == 22.0
    assert out["breadth"] == {"$ADVN": 1500, "$DECN": 900}
    assert out["spx_ma_spread"] is None  # no $SPX bars
    assert out["t10y2y"] is None


def test_gather_inputs_computes_spx_trend(monkeypatch):
    monkeypatch.setattr(I, "fetch_market_context", lambda: {"vix_last": 15.0, "breadth": {}})
    monkeypatch.setattr(I, "fetch_macro", lambda ids: {})
    _seed_daily("$SPX", [100.0 + i for i in range(220)])  # rising series
    out = I.gather_inputs()
    assert out["spx_ma_spread"] is not None
    assert out["spx_dist_50"] is not None


def test_vix_percentile_needs_enough_history():
    assert I._vix_percentile(20.0, [18.0, 19.0]) is None  # < 30 bars
    pct = I._vix_percentile(20.0, [float(x) for x in range(40)])  # 20 of 40 <= 20
    assert pct is not None and 0.0 <= pct <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/regime/tests/test_inputs.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.regime.services.inputs`.

- [ ] **Step 3: Implement input gathering**

`backend/apps/regime/services/inputs.py`:
```python
"""Best-effort gather of raw regime inputs. NEVER raises — each source is isolated
and degrades to None/{} so a missing feed only blanks one axis."""

from __future__ import annotations

import logging

from apps.market.models import OHLCBar
from apps.market.services.context import fetch_market_context
from apps.market.services.fred import fetch_macro
from apps.regime import constants as C
from apps.triggers.indicators import dist_from_sma_pct, sma_spread_pct

log = logging.getLogger(__name__)


def _daily_closes(ticker: str, limit: int) -> list[float]:
    rows = list(
        OHLCBar.objects.filter(ticker=ticker, timeframe="1d")
        .order_by("-ts")
        .values_list("close", flat=True)[:limit]
    )
    return [float(c) for c in reversed(rows)]  # oldest -> newest


def _vix_percentile(vix_last: float | None, closes: list[float]) -> float | None:
    if vix_last is None or len(closes) < 30:
        return None
    below = sum(1 for c in closes if c <= vix_last)
    return below / len(closes)


def _sector_returns() -> dict:
    out: dict[str, float] = {}
    for etf in C.OFFENSIVE_ETFS + C.DEFENSIVE_ETFS:
        closes = _daily_closes(etf, C.SECTOR_RETURN_WINDOW)
        if len(closes) >= 2 and closes[0]:
            out[etf] = (closes[-1] / closes[0] - 1.0) * 100.0
    return out


def gather_inputs() -> dict:
    out: dict = {
        "vix_last": None, "vix_percentile": None, "spx_ma_spread": None,
        "spx_dist_50": None, "breadth": {}, "sector_returns": {},
        "t10y2y": None, "tnx_change": None,
    }
    try:
        ctx = fetch_market_context()
        out["vix_last"] = ctx.get("vix_last")
        out["breadth"] = ctx.get("breadth") or {}
    except Exception:
        log.warning("regime.inputs.context_failed", exc_info=True)
    try:
        vix_closes = _daily_closes("$VIX", C.VIX_PERCENTILE_WINDOW)
        out["vix_percentile"] = _vix_percentile(out["vix_last"], vix_closes)
    except Exception:
        log.warning("regime.inputs.vix_pct_failed", exc_info=True)
    try:
        spx = _daily_closes("$SPX", C.MA_SLOW + 5)
        if spx:
            out["spx_ma_spread"] = sma_spread_pct(spx, fast=C.MA_FAST, slow=C.MA_SLOW)
            out["spx_dist_50"] = dist_from_sma_pct(spx, period=C.MA_FAST, last=spx[-1])
    except Exception:
        log.warning("regime.inputs.spx_trend_failed", exc_info=True)
    try:
        out["sector_returns"] = _sector_returns()
    except Exception:
        log.warning("regime.inputs.sector_returns_failed", exc_info=True)
    try:
        macro = fetch_macro(["T10Y2Y", "DGS10"])
        out["t10y2y"] = (macro.get("T10Y2Y") or {}).get("value")
        out["tnx_change"] = (macro.get("DGS10") or {}).get("change")
    except Exception:
        log.warning("regime.inputs.macro_failed", exc_info=True)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/regime/tests/test_inputs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/regime/services/inputs.py backend/apps/regime/tests/test_inputs.py
git commit -m "feat(regime): best-effort regime input gathering (M15 F1)"
```

---

## Task 5: Compute orchestration + change alert

**Files:**
- Modify: `backend/apps/regime/services/compute.py`
- Modify: `backend/apps/observer/models.py` (+ migration)
- Test: `backend/apps/regime/tests/test_compute.py`

- [ ] **Step 1: Add the `regime` notification kind**

In `backend/apps/observer/models.py`, add to `Notification.KIND_CHOICES`:
```python
        ("regime", "Regime"),
```
Then: `docker compose exec web python manage.py makemigrations observer`
Expected: a no-op-SQL `AlterField` migration on `Notification.kind`.

- [ ] **Step 2: Write the failing test**

`backend/apps/regime/tests/test_compute.py`:
```python
import pytest

from apps.observer.models import Notification
from apps.regime.models import RegimeReading
from apps.regime.services import compute

pytestmark = pytest.mark.django_db

RISK_OFF_INPUTS = {
    "vix_last": 24.0, "vix_percentile": 0.8, "spx_ma_spread": -3.0, "spx_dist_50": -2.0,
    "breadth": {"$ADVN": 700, "$DECN": 2000}, "sector_returns": {}, "t10y2y": -0.2, "tnx_change": 0.05,
}
RISK_ON_INPUTS = {
    "vix_last": 12.0, "vix_percentile": 0.2, "spx_ma_spread": 4.0, "spx_dist_50": 3.0,
    "breadth": {"$ADVN": 2200, "$DECN": 700}, "sector_returns": {}, "t10y2y": 0.5, "tnx_change": -0.03,
}


def test_compute_and_store_persists_classified_reading(monkeypatch):
    monkeypatch.setattr(compute, "gather_inputs", lambda: RISK_OFF_INPUTS)
    monkeypatch.setattr(compute, "regime_narrative", lambda *a, **k: "")
    reading = compute.compute_and_store()
    assert reading.composite == "Risk-Off"
    assert reading.axes["volatility"] == "Elevated"
    assert RegimeReading.objects.count() == 1


def test_change_fires_notification(monkeypatch):
    monkeypatch.setattr(compute, "regime_narrative", lambda *a, **k: "")
    monkeypatch.setattr(compute, "gather_inputs", lambda: RISK_ON_INPUTS)
    compute.compute_and_store()  # first reading: Risk-On, no prior -> no notify
    assert Notification.objects.filter(kind="regime").count() == 0
    monkeypatch.setattr(compute, "gather_inputs", lambda: RISK_OFF_INPUTS)
    second = compute.compute_and_store()  # flip -> notify
    assert second.composite == "Risk-Off"
    notes = Notification.objects.filter(kind="regime")
    assert notes.count() == 1
    assert "Risk-On" in notes.first().title and "Risk-Off" in notes.first().title


def test_no_change_no_notification(monkeypatch):
    monkeypatch.setattr(compute, "regime_narrative", lambda *a, **k: "")
    monkeypatch.setattr(compute, "gather_inputs", lambda: RISK_ON_INPUTS)
    compute.compute_and_store()
    compute.compute_and_store()  # same composite -> no notify
    assert Notification.objects.filter(kind="regime").count() == 0
    assert RegimeReading.objects.count() == 2
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker compose exec web pytest apps/regime/tests/test_compute.py -v`
Expected: FAIL — `AttributeError: module 'apps.regime.services.compute' has no attribute 'compute_and_store'`.

- [ ] **Step 4: Implement the orchestration**

Replace `backend/apps/regime/services/compute.py` with:
```python
from __future__ import annotations

import logging

from apps.regime.models import RegimeReading
from apps.regime.services.classify import (
    build_drivers,
    classify_breadth,
    classify_leadership,
    classify_rates,
    classify_trend,
    classify_volatility,
    fold_composite,
)
from apps.regime.services.inputs import gather_inputs
from apps.regime.services.narrative import regime_narrative

log = logging.getLogger(__name__)


def current_regime() -> RegimeReading | None:
    """The latest reading, or None when no reading has been produced yet."""
    return RegimeReading.objects.order_by("-created_at").first()


def _classify(inp: dict) -> dict[str, str]:
    return {
        "volatility": classify_volatility(inp.get("vix_last"), inp.get("vix_percentile")),
        "trend": classify_trend(inp.get("spx_ma_spread"), inp.get("spx_dist_50")),
        "breadth": classify_breadth(inp.get("breadth") or {}),
        "leadership": classify_leadership(inp.get("sector_returns") or {}),
        "rates": classify_rates(inp.get("t10y2y"), inp.get("tnx_change")),
    }


def changed_axes(prior: RegimeReading, axes: dict[str, str]) -> list[str]:
    prior_axes = prior.axes or {}
    return [k for k, v in axes.items() if prior_axes.get(k) != v]


def _notify_change(prior: RegimeReading, reading: RegimeReading) -> None:
    from apps.observer.services.notifications import notify

    notify(
        user_id=None,
        kind="regime",
        title=f"Regime change: {prior.composite} → {reading.composite}",
        body="; ".join(reading.drivers[:3]),
        link="/regime",
        meta={"reading_id": reading.id, "prior": prior.composite, "current": reading.composite},
    )


def compute_and_store() -> RegimeReading:
    """Gather -> classify -> persist -> alert on composite change. Never raises out
    of the deterministic core (narrative is already best-effort)."""
    inp = gather_inputs()
    axes = _classify(inp)
    composite = fold_composite(axes)
    drivers = build_drivers(axes, inp)

    prior = current_regime()
    changed = changed_axes(prior, axes) if prior else []
    narrative = regime_narrative(composite, axes, drivers)  # best-effort, "" on failure

    reading = RegimeReading.objects.create(
        composite=composite, axes=axes, drivers=drivers,
        inputs=inp, narrative=narrative, changed_axes=changed,
    )
    if prior is not None and prior.composite != reading.composite:
        try:
            _notify_change(prior, reading)
        except Exception:
            log.warning("regime.notify_failed", exc_info=True)
    return reading
```

Note: `narrative.py` (Task 6) does not exist yet. To keep this task green in isolation, create a temporary stub `backend/apps/regime/services/narrative.py` with:
```python
def regime_narrative(composite, axes, drivers) -> str:  # replaced in Task 6
    return ""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/regime/tests/test_compute.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/regime/services/compute.py backend/apps/regime/services/narrative.py backend/apps/observer/models.py backend/apps/observer/migrations backend/apps/regime/tests/test_compute.py
git commit -m "feat(regime): compute orchestration + regime-change alert (M15 F1)"
```

---

## Task 6: Best-effort AI narrative

**Files:**
- Modify: `backend/apps/regime/services/narrative.py` (replace the stub)
- Test: `backend/apps/regime/tests/test_narrative.py`

This mirrors `apps.thesis.services.postmortem._attempt_ai_narrative`: claude-only, key + caps guarded, degrades to `""` on any failure.

- [ ] **Step 1: Write the failing test**

`backend/apps/regime/tests/test_narrative.py`:
```python
import pytest

from apps.regime.services import narrative as N

pytestmark = pytest.mark.django_db

AXES = {"volatility": "Elevated", "trend": "Downtrend"}
DRIVERS = ["VIX 24 — Elevated", "SPX trend Downtrend"]


def test_no_claude_config_returns_empty():
    # No ProviderConfig rows at all -> "".
    assert N.regime_narrative("Risk-Off", AXES, DRIVERS) == ""


def test_returns_summary_when_provider_ok(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(provider="claude", _api_key="sk-test", default_model="claude-opus-4-8")

    class _Report:
        summary = "Risk-off: volatility elevated, trend rolling over."

    monkeypatch.setattr(N, "run_structured", lambda **kw: _Report())
    monkeypatch.setattr(N, "check_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(N, "check_monthly_cap", lambda *a, **k: None)
    out = N.regime_narrative("Risk-Off", AXES, DRIVERS)
    assert "Risk-off" in out


def test_provider_error_degrades_to_empty(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(provider="claude", _api_key="sk-test", default_model="claude-opus-4-8")

    def _boom(**kw):
        raise RuntimeError("upstream 500")

    monkeypatch.setattr(N, "run_structured", _boom)
    monkeypatch.setattr(N, "check_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(N, "check_monthly_cap", lambda *a, **k: None)
    assert N.regime_narrative("Risk-Off", AXES, DRIVERS) == ""
```

(If `ProviderConfig`'s encrypted field is not named `_api_key`, adjust the fixture to the real write accessor — check `apps/secrets/models.py`; the postmortem tests show the canonical way to seed a claude key.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/regime/tests/test_narrative.py -v`
Expected: FAIL — `regime_narrative` returns the stub `""` for the OK case (`assert "Risk-off" in ""`).

- [ ] **Step 3: Implement the narrative**

Replace `backend/apps/regime/services/narrative.py`:
```python
"""Best-effort one-paragraph regime narrative (Claude). NEVER raises; returns ""
on non-claude / no key / cap hit / any provider error — the deterministic axes +
composite are already persisted by the caller."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured

log = logging.getLogger(__name__)


class RegimeNarrative(BaseModel):
    summary: str = Field(description="One tight paragraph naming the regime and its 2-3 drivers.")


def _build_prompt(composite: str, axes: dict, drivers: list[str]) -> str:
    axes_lines = "\n".join(f"- {k}: {v}" for k, v in axes.items())
    return (
        f"Current market regime composite: {composite}.\n\nAxes:\n{axes_lines}\n\n"
        f"Drivers: {', '.join(drivers) or 'n/a'}.\n\n"
        "Write ONE tight paragraph (<=4 sentences) naming the regime and its key drivers. "
        "Strictly observational; no buy/sell advice."
    )


def regime_narrative(composite: str, axes: dict, drivers: list[str]) -> str:
    from apps.secrets.models import ProviderConfig

    try:
        cfg = ProviderConfig.objects.filter(provider="claude").first()
        if cfg is None or not cfg.api_key:
            return ""
        check_daily_cap("claude", cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap("claude", cap_usd=cfg.monthly_cost_cap_usd)
        report = run_structured(
            api_key=cfg.api_key,
            model=cfg.default_model or "claude-opus-4-8",
            system="",
            user=_build_prompt(composite, axes, drivers),
            output_model=RegimeNarrative,
            base_url=cfg.base_url or "",
        )
        return (getattr(report, "summary", "") or "").strip()
    except CostCapExceededError as exc:
        log.warning("regime.narrative.cap_hit: %s", exc)
        return ""
    except Exception:
        log.warning("regime.narrative.failed", exc_info=True)
        return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/regime/tests/test_narrative.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/regime/services/narrative.py backend/apps/regime/tests/test_narrative.py
git commit -m "feat(regime): best-effort Claude regime narrative (M15 F1)"
```

---

## Task 7: Beat task + Celery wiring

**Files:**
- Create: `backend/apps/regime/tasks.py`
- Modify: `backend/config/celery.py` (`beat_schedule`)
- Test: `backend/apps/regime/tests/test_tasks.py`

- [ ] **Step 1: Write the failing test**

`backend/apps/regime/tests/test_tasks.py`:
```python
import pytest

from apps.regime import tasks

pytestmark = pytest.mark.django_db


def test_refresh_skips_when_market_closed(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(tasks, "is_market_open", lambda: False)
    monkeypatch.setattr(tasks, "compute_and_store", lambda: called.__setitem__("n", called["n"] + 1))
    tasks.refresh.run()  # eager call of the task body
    assert called["n"] == 0


def test_refresh_runs_when_open(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(tasks, "is_market_open", lambda: True)
    monkeypatch.setattr(tasks, "compute_and_store", lambda: called.__setitem__("n", called["n"] + 1))
    tasks.refresh.run()
    assert called["n"] == 1


def test_refresh_force_runs_when_closed(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(tasks, "is_market_open", lambda: False)
    monkeypatch.setattr(tasks, "compute_and_store", lambda: called.__setitem__("n", called["n"] + 1))
    tasks.refresh.run(force=True)
    assert called["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/regime/tests/test_tasks.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.regime.tasks`.

- [ ] **Step 3: Implement the task**

`backend/apps/regime/tasks.py`:
```python
from __future__ import annotations

import logging

from celery import shared_task

from apps.observer.services.market_hours import is_market_open
from apps.regime.services.compute import compute_and_store

log = logging.getLogger(__name__)


@shared_task(name="regime.refresh")
def refresh(force: bool = False) -> int | None:
    """Compute + persist one RegimeReading. Skips when the market is closed unless
    ``force`` (the pre-open / post-close forced readings pass force=True)."""
    if not force and not is_market_open():
        log.info("regime.refresh: market closed, skipping")
        return None
    reading = compute_and_store()
    return reading.id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/regime/tests/test_tasks.py -v`
Expected: PASS.

- [ ] **Step 5: Add the beat schedule entry**

In `backend/config/celery.py`, add to `app.conf.beat_schedule`:
```python
    "regime-refresh-intraday": {
        "task": "regime.refresh",
        "schedule": crontab(minute="*/30"),  # market-hours guard is inside the task
    },
    "regime-refresh-preopen": {
        "task": "regime.refresh",
        "schedule": crontab(hour=13, minute=0),  # 09:00 ET pre-open (UTC); forced below via kwargs
        "kwargs": {"force": True},
    },
```

- [ ] **Step 6: Restart worker + beat (they don't hot-reload) and verify registration**

Run: `docker compose restart worker beat`
Then: `docker compose exec worker celery -A config inspect registered 2>/dev/null | grep regime.refresh`
Expected: `regime.refresh` appears in the registered task list.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/regime/tasks.py backend/config/celery.py backend/apps/regime/tests/test_tasks.py
git commit -m "feat(regime): regime.refresh beat task + schedule (M15 F1)"
```

---

## Task 8: Serializer + DRF views + urls

**Files:**
- Create: `backend/apps/regime/serializers.py`, `backend/apps/regime/views.py`
- Modify: `backend/apps/regime/urls.py`
- Test: `backend/apps/regime/tests/test_views.py`

- [ ] **Step 1: Write the failing test**

`backend/apps/regime/tests/test_views.py`:
```python
import pytest
from rest_framework.test import APIClient

from apps.regime.models import RegimeReading

pytestmark = pytest.mark.django_db


def test_current_empty_returns_null():
    resp = APIClient().get("/api/regime/current/")
    assert resp.status_code == 200
    assert resp.json() is None


def test_current_returns_latest():
    RegimeReading.objects.create(composite="Risk-On", axes={"volatility": "Low"}, drivers=["VIX 12 — Low"])
    resp = APIClient().get("/api/regime/current/")
    body = resp.json()
    assert body["composite"] == "Risk-On"
    assert body["axes"]["volatility"] == "Low"
    assert "id" in body


def test_list_returns_history():
    RegimeReading.objects.create(composite="Risk-On", axes={})
    RegimeReading.objects.create(composite="Risk-Off", axes={})
    resp = APIClient().get("/api/regime/")
    rows = resp.json()
    assert len(rows) == 2
    assert rows[0]["composite"] == "Risk-Off"  # newest first


def test_refresh_endpoint_invokes_compute(monkeypatch):
    from apps.regime import views

    monkeypatch.setattr(
        views, "compute_and_store",
        lambda: RegimeReading.objects.create(composite="Stress", axes={}),
    )
    resp = APIClient().post("/api/regime/refresh/")
    assert resp.status_code == 200
    assert resp.json()["composite"] == "Stress"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/regime/tests/test_views.py -v`
Expected: FAIL — 404s (routes not registered yet).

- [ ] **Step 3: Implement serializer + views + urls**

`backend/apps/regime/serializers.py`:
```python
from rest_framework import serializers

from apps.regime.models import RegimeReading


class RegimeReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegimeReading
        fields = ["id", "created_at", "composite", "axes", "drivers", "narrative", "changed_axes"]
        read_only_fields = fields
```

`backend/apps/regime/views.py`:
```python
from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.regime.models import RegimeReading
from apps.regime.serializers import RegimeReadingSerializer
from apps.regime.services.compute import compute_and_store, current_regime


class RegimeViewSet(ReadOnlyModelViewSet):
    """GET /api/regime/ (history), /current/ (latest or null), POST /refresh/."""

    queryset = RegimeReading.objects.all()
    serializer_class = RegimeReadingSerializer

    @action(detail=False, methods=["get"])
    def current(self, request: Request) -> Response:
        reading = current_regime()
        if reading is None:
            return Response(None)
        return Response(RegimeReadingSerializer(reading).data)

    @action(detail=False, methods=["post"])
    def refresh(self, request: Request) -> Response:
        reading = compute_and_store()
        return Response(RegimeReadingSerializer(reading).data)
```

`backend/apps/regime/urls.py` (replace):
```python
from rest_framework.routers import DefaultRouter

from apps.regime.views import RegimeViewSet

router = DefaultRouter()
router.register("", RegimeViewSet, basename="regime")
urlpatterns = router.urls
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/regime/tests/test_views.py -v`
Expected: PASS. (The DRF router maps `current`/`refresh` to `/api/regime/current/` and `/api/regime/refresh/`.)

- [ ] **Step 5: Commit**

```bash
git add backend/apps/regime/serializers.py backend/apps/regime/views.py backend/apps/regime/urls.py backend/apps/regime/tests/test_views.py
git commit -m "feat(regime): list/current/refresh API (M15 F1)"
```

---

## Task 9: Coach integration (`_regime_block`)

**Files:**
- Modify: `backend/apps/threads/coach.py`
- Test: `backend/apps/threads/tests/test_coach_regime.py`

- [ ] **Step 1: Write the failing test**

`backend/apps/threads/tests/test_coach_regime.py`:
```python
import pytest

from apps.profiles.models import TradingProfile
from apps.regime.models import RegimeReading
from apps.threads.coach import _regime_block, assemble_coach_context_for_message

pytestmark = pytest.mark.django_db


def test_regime_block_empty_when_no_reading():
    assert _regime_block() == ""


def test_regime_block_renders_latest():
    RegimeReading.objects.create(
        composite="Risk-Off", axes={"volatility": "Elevated"},
        drivers=["VIX 24 — Elevated", "SPX trend Downtrend"],
    )
    block = _regime_block()
    assert "Risk-Off" in block
    assert "VIX 24" in block


def test_bare_chat_coach_includes_regime(monkeypatch):
    RegimeReading.objects.create(composite="Stress", axes={}, drivers=["VIX 35 — Stress"])
    profile = TradingProfile.objects.create(name="t", style="", enable_coach=True)
    # No $cashtag, no snapshot — regime is ticker-independent so it still appears.
    out = assemble_coach_context_for_message("what's the setup today?", profile)
    assert "Stress" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/threads/tests/test_coach_regime.py -v`
Expected: FAIL — `ImportError: cannot import name '_regime_block'`.

- [ ] **Step 3: Implement the block + wire it into both assembly functions**

In `backend/apps/threads/coach.py`, add this function (near the other `_*_block` helpers):
```python
def _regime_block() -> str:
    """Current market regime — the only TICKER-INDEPENDENT coach block, so it
    renders even on a snapshot-free / cashtag-free chat. Lazy import keeps the
    threads -> regime boundary clean. "" when no reading exists."""
    from apps.regime.services.compute import current_regime

    reading = current_regime()
    if reading is None:
        return ""
    lines = [f"### Market regime: {reading.composite}"]
    for d in (reading.drivers or [])[:4]:
        lines.append(f"- {d}")
    if reading.narrative:
        lines.append(reading.narrative)
    return "\n".join(lines)
```

In `assemble_coach_context` (the snapshot path), add `_safe(_regime_block)` to the `sections` list — put it first so the macro frame leads:
```python
    sections = [
        _safe(_regime_block),
        _safe(lambda: _theses_block(ticker, snapshot)),
        # ... existing entries unchanged ...
    ]
```

In `assemble_coach_context_for_message` (the bare-chat path), likewise add `_safe(_regime_block)` first:
```python
    sections = [
        _safe(_regime_block),
        _safe(lambda: _recall_block_for_text(text, ticker)),
        # ... existing entries unchanged ...
    ]
```

Note: `assemble_coach_context` still returns `""` early when there's no `primary_ticker` (unchanged) — that path is only reached for snapshot-bearing runs, which always have one. The bare-chat path is where the ticker-independent regime block earns its keep.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/threads/tests/test_coach_regime.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full coach test module to confirm no regression**

Run: `docker compose exec web pytest apps/threads/tests/ -k coach -v`
Expected: PASS (existing coach tests unaffected — the new block is additive and `_safe`-wrapped).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/threads/coach.py backend/apps/threads/tests/test_coach_regime.py
git commit -m "feat(regime): inject regime block into the coach, incl. bare chats (M15 F1)"
```

---

## Task 10: Dashboard regime section + contract-valid default

**Files:**
- Modify: `backend/apps/dashboard/views.py`
- Test: `backend/apps/dashboard/tests/test_dashboard_regime.py`

- [ ] **Step 1: Write the failing test**

`backend/apps/dashboard/tests/test_dashboard_regime.py`:
```python
import pytest
from rest_framework.test import APIClient

from apps.regime.models import RegimeReading

pytestmark = pytest.mark.django_db


def test_dashboard_includes_regime_default_when_empty():
    body = APIClient().get("/api/dashboard/").json()
    assert "regime" in body
    assert body["regime"] == {"composite": None, "drivers": [], "as_of": None}


def test_dashboard_regime_populated():
    RegimeReading.objects.create(composite="Risk-On", axes={}, drivers=["VIX 12 — Low"])
    body = APIClient().get("/api/dashboard/").json()
    assert body["regime"]["composite"] == "Risk-On"
    assert body["regime"]["drivers"] == ["VIX 12 — Low"]
    assert body["regime"]["as_of"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/dashboard/tests/test_dashboard_regime.py -v`
Expected: FAIL — `KeyError: 'regime'` / assertion error (no regime key yet).

- [ ] **Step 3: Implement the section**

In `backend/apps/dashboard/views.py`, add a section helper:
```python
def _regime_section() -> dict:
    from apps.regime.services.compute import current_regime

    reading = current_regime()
    if reading is None:
        return {"composite": None, "drivers": [], "as_of": None}
    return {
        "composite": reading.composite,
        "drivers": reading.drivers or [],
        "as_of": reading.created_at.isoformat(),
    }
```
And add to the `DashboardView.get` response dict (default MUST match the contract — see CLAUDE.md landmine):
```python
                "regime": _safe(_regime_section, {"composite": None, "drivers": [], "as_of": None}),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/dashboard/tests/test_dashboard_regime.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/dashboard/views.py backend/apps/dashboard/tests/test_dashboard_regime.py
git commit -m "feat(regime): dashboard regime section + contract-valid default (M15 F1)"
```

---

## Task 11: Frontend API client + hook

**Files:**
- Create: `frontend/src/api/regime.ts`, `frontend/src/hooks/useRegime.ts`
- Test: `frontend/src/__tests__/useRegime.test.tsx`

- [ ] **Step 1: Write the failing test**

`frontend/src/__tests__/useRegime.test.tsx`:
```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import { useCurrentRegime } from "@/hooks/useRegime";
import { hookWrapper } from "./helpers";

describe("useCurrentRegime", () => {
  it("returns the current regime", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({
      id: 1, created_at: "2026-06-01T12:00:00Z", composite: "Risk-Off",
      axes: { volatility: "Elevated" }, drivers: ["VIX 24 — Elevated"],
      narrative: "", changed_axes: [],
    });
    const { result } = renderHook(() => useCurrentRegime(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.data?.composite).toBe("Risk-Off"));
  });
});
```
(`hookWrapper` is the existing test helper — see the `frontend-test-helpers` memory / `src/__tests__/helpers`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/useRegime.test.tsx`
Expected: FAIL — cannot resolve `@/hooks/useRegime`.

- [ ] **Step 3: Implement the API client + hook**

`frontend/src/api/regime.ts`:
```ts
import { apiGet, apiPost } from "@/api/client";

export type RegimeComposite = "Risk-On" | "Neutral-Transitional" | "Risk-Off" | "Stress";

export interface RegimeReading {
  id: number;
  created_at: string;
  composite: RegimeComposite;
  axes: Record<string, string>;
  drivers: string[];
  narrative: string;
  changed_axes: string[];
}

export const fetchCurrentRegime = () => apiGet<RegimeReading | null>("/api/regime/current/");
export const fetchRegimeHistory = () => apiGet<RegimeReading[]>("/api/regime/");
export const refreshRegime = () => apiPost<RegimeReading>("/api/regime/refresh/");
```

`frontend/src/hooks/useRegime.ts`:
```ts
import { useQuery } from "@tanstack/react-query";

import { fetchCurrentRegime, fetchRegimeHistory } from "@/api/regime";

export const useCurrentRegime = () =>
  useQuery({ queryKey: ["regime", "current"], queryFn: fetchCurrentRegime });

export const useRegimeHistory = () =>
  useQuery({ queryKey: ["regime", "history"], queryFn: fetchRegimeHistory });
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/useRegime.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/regime.ts frontend/src/hooks/useRegime.ts frontend/src/__tests__/useRegime.test.tsx
git commit -m "feat(regime): frontend api client + hooks (M15 F1)"
```

---

## Task 12: `/regime` page + route

**Files:**
- Create: `frontend/src/pages/RegimePage.tsx`
- Modify: `frontend/src/router.tsx`
- Test: `frontend/src/__tests__/RegimePage.test.tsx`

- [ ] **Step 1: Write the failing test**

`frontend/src/__tests__/RegimePage.test.tsx`:
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import RegimePage from "@/pages/RegimePage";
import { renderWithProviders } from "./helpers";

describe("RegimePage", () => {
  it("renders the composite, axes, and drivers", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) => {
      const reading = {
        id: 1, created_at: "2026-06-01T12:00:00Z", composite: "Risk-Off",
        axes: { volatility: "Elevated", trend: "Downtrend" },
        drivers: ["VIX 24 — Elevated"], narrative: "Risk-off backdrop.", changed_axes: [],
      };
      return path.endsWith("/current/") ? reading : [reading];
    });
    renderWithProviders(<RegimePage />);
    await waitFor(() => expect(screen.getByText("Risk-Off")).toBeInTheDocument());
    expect(screen.getByText(/Elevated/)).toBeInTheDocument();
    expect(screen.getByText(/VIX 24/)).toBeInTheDocument();
  });

  it("shows an empty state when there is no reading", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) =>
      path.endsWith("/current/") ? null : [],
    );
    renderWithProviders(<RegimePage />);
    await waitFor(() => expect(screen.getByText(/no regime reading/i)).toBeInTheDocument());
  });
});
```
(`renderWithProviders` is the existing helper that wraps in the QueryClient + router.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/RegimePage.test.tsx`
Expected: FAIL — cannot resolve `@/pages/RegimePage`.

- [ ] **Step 3: Implement the page**

`frontend/src/pages/RegimePage.tsx` (uses the ledger tokens + shared primitives — see `frontend-ledger-design-tokens` memory):
```tsx
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { useCurrentRegime, useRegimeHistory } from "@/hooks/useRegime";

const COMPOSITE_TONE: Record<string, string> = {
  "Risk-On": "text-emerald-600",
  "Neutral-Transitional": "text-ink",
  "Risk-Off": "text-copper",
  Stress: "text-red-600",
};

export default function RegimePage() {
  const { data: current, isLoading } = useCurrentRegime();
  const { data: history = [] } = useRegimeHistory();

  if (isLoading) return <Skeleton />;
  if (!current) {
    return (
      <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
        <EmptyState title="No regime reading yet" body="The regime engine has not produced a reading. Trigger one from Settings or wait for the next scheduled run." />
      </div>
    );
  }

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <h1 className="text-2xl font-semibold">Market regime</h1>
      <p className={`mt-2 text-3xl font-bold ${COMPOSITE_TONE[current.composite] ?? "text-ink"}`}>
        {current.composite}
      </p>
      {current.narrative && <p className="mt-2 text-ink/80">{current.narrative}</p>}

      <h2 className="mt-6 text-lg font-medium">Axes</h2>
      <dl className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-5">
        {Object.entries(current.axes).map(([axis, label]) => (
          <div key={axis} className="rounded border border-rule p-3">
            <dt className="text-xs uppercase tracking-wide text-ink/60">{axis}</dt>
            <dd className="mt-1 font-medium">{label}</dd>
          </div>
        ))}
      </dl>

      <h2 className="mt-6 text-lg font-medium">Drivers</h2>
      <ul className="mt-2 list-disc pl-5">
        {current.drivers.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>

      <h2 className="mt-6 text-lg font-medium">History</h2>
      <ul className="mt-2 divide-y divide-rule">
        {history.map((r) => (
          <li key={r.id} className="flex justify-between py-2 text-sm">
            <span>{new Date(r.created_at).toLocaleString()}</span>
            <span className={COMPOSITE_TONE[r.composite] ?? "text-ink"}>{r.composite}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Add the route**

In `frontend/src/router.tsx`, add a child of the `<AppLayout>` route (near `/scorecard` / `/mirror`):
```tsx
      { path: "regime", element: <RegimePage />, handle: { crumb: "Regime" } },
```
Add the import at the top: `import RegimePage from "@/pages/RegimePage";`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/RegimePage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/RegimePage.tsx frontend/src/router.tsx frontend/src/__tests__/RegimePage.test.tsx
git commit -m "feat(regime): /regime page + route (M15 F1)"
```

---

## Task 13: Dashboard `RegimeTile`

**Files:**
- Create: `frontend/src/components/RegimeTile.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Test: `frontend/src/__tests__/RegimeTile.test.tsx`

- [ ] **Step 1: Write the failing test**

`frontend/src/__tests__/RegimeTile.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RegimeTile } from "@/components/RegimeTile";

describe("RegimeTile", () => {
  it("renders the composite + first driver", () => {
    render(<RegimeTile regime={{ composite: "Risk-Off", drivers: ["VIX 24 — Elevated"], as_of: "2026-06-01T12:00:00Z" }} />);
    expect(screen.getByText("Risk-Off")).toBeInTheDocument();
    expect(screen.getByText(/VIX 24/)).toBeInTheDocument();
  });

  it("renders gracefully with the empty default", () => {
    render(<RegimeTile regime={{ composite: null, drivers: [], as_of: null }} />);
    expect(screen.getByText(/no reading/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/RegimeTile.test.tsx`
Expected: FAIL — cannot resolve `@/components/RegimeTile`.

- [ ] **Step 3: Implement the tile**

`frontend/src/components/RegimeTile.tsx`:
```tsx
import { Link } from "react-router-dom";

export interface DashboardRegime {
  composite: string | null;
  drivers: string[];
  as_of: string | null;
}

const TONE: Record<string, string> = {
  "Risk-On": "text-emerald-600",
  "Neutral-Transitional": "text-ink",
  "Risk-Off": "text-copper",
  Stress: "text-red-600",
};

export function RegimeTile({ regime }: { regime: DashboardRegime }) {
  return (
    <Link to="/regime" className="block rounded border border-rule p-4 hover:bg-ink/5">
      <div className="text-xs uppercase tracking-wide text-ink/60">Market regime</div>
      {regime.composite ? (
        <>
          <div className={`mt-1 text-xl font-bold ${TONE[regime.composite] ?? "text-ink"}`}>
            {regime.composite}
          </div>
          {regime.drivers[0] && <div className="mt-1 text-sm text-ink/70">{regime.drivers[0]}</div>}
        </>
      ) : (
        <div className="mt-1 text-sm text-ink/60">No reading yet</div>
      )}
    </Link>
  );
}
```

- [ ] **Step 4: Mount it on the Dashboard**

In `frontend/src/pages/Dashboard.tsx`: import `RegimeTile` + its type, and render `<RegimeTile regime={data.regime} />` within the tile grid (the dashboard payload already carries `regime` after Task 10). Add the type to the dashboard payload interface (`regime: DashboardRegime`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/RegimeTile.test.tsx`
Expected: PASS.

- [ ] **Step 6: Full gate + commit**

Run: `docker compose exec web pytest apps/regime -v && docker compose exec frontend pnpm exec vitest run src/__tests__/RegimeTile.test.tsx src/__tests__/RegimePage.test.tsx src/__tests__/useRegime.test.tsx`
Expected: all green.

```bash
git add frontend/src/components/RegimeTile.tsx frontend/src/pages/Dashboard.tsx frontend/src/__tests__/RegimeTile.test.tsx
git commit -m "feat(regime): dashboard regime tile (M15 F1)"
```

---

## Final verification

- [ ] Run the full backend regime suite + lint:
  `docker compose exec web pytest apps/regime apps/threads/tests -k "regime or coach" -v`
  then `make lint` (ruff is the gate; `ty` is advisory).
- [ ] Run the dashboard + observer suites (changed shapes):
  `docker compose exec web pytest apps/dashboard apps/observer -v`
- [ ] Confirm `regime.refresh` is registered on worker/beat (Task 7 Step 6).
- [ ] Manual smoke: `POST /api/regime/refresh/` then `GET /api/regime/current/` returns a classified reading; the `/regime` page and the Dashboard tile render it.

---

## Self-review (against the F1 spec section)

**Spec coverage:**
- Hybrid (deterministic + best-effort AI narrative) → Tasks 2, 6. ✓
- Five axes + composite + honest coverage (Unknown) → Task 2. ✓
- Inputs from `context`/`fred`/`OHLCBar` → Task 4. ✓
- `RegimeReading` model + `current_regime()` → Task 3. ✓
- Scheduled market-hours-aware beat + change alert → Tasks 5, 7. ✓
- Coach injection everywhere incl. bare chats (ticker-independent) → Task 9. ✓
- API (list/current/refresh) → Task 8. ✓
- Dashboard tile + `/regime` page → Tasks 10, 12, 13. ✓
- Thresholds in a constants module → Task 1. ✓

**Type consistency:** `compute_and_store()` / `current_regime()` / `regime_narrative(composite, axes, drivers)` / `gather_inputs()` / `fold_composite(axes)` names are identical across Tasks 3–10. The `RegimeReading` field set (composite/axes/drivers/narrative/inputs/changed_axes) matches the serializer (Task 8) and the frontend `RegimeReading` interface (Task 11). The dashboard `regime` payload shape `{composite, drivers, as_of}` matches `DashboardRegime` (Task 13).

**Open verification for the implementer (flagged, not faked):**
- `ProviderConfig`'s encrypted write accessor in the Task 6 test fixture — confirm it's `_api_key` (or use the canonical seed from the postmortem tests).
- The exact frontend test helper names (`hookWrapper` / `renderWithProviders`) — confirm against `frontend/src/__tests__/helpers` (see the `frontend-test-helpers` memory).
