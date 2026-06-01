# M15 F4 — Anomaly-Sweep Autonomy (The Desk) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** The autonomy capstone (`apps.desk`) — a periodic, opt-in sweep that runs anomaly detectors over the universe (watchlist + covered + thesis/position tickers), scores + dedups them, originates a bounded investigation per top-K, and writes findings to a **Desk feed** with one-click suggested actions (primary: Convene War Room → F3). Composes F1 (regime-change detector) + F2 (book-deterioration detector) + F3 (act → debate).

**Architecture:** New `apps.desk` app. A detector registry (`services/detectors.py`) of deterministic functions over existing data + services. `services/sweep.py` orchestrates detect → score → cooldown → top-K → investigate (synchronous `run_structured`) → persist `DeskEntry` + notify. Opt-in beat task gated by `ANOMALY_SWEEP_ENABLED` (default OFF — the autonomy-spends-money rule). DRF feed + act/dismiss + a `/desk` page + a Dashboard unread tile.

**v1 scope (sound defaults; deferrals explicit):**
- **In v1:** the 4 detector buckets (deterministic, reusing existing services); scoring + per-`(ticker,type)` cooldown; synchronous `run_structured` investigation; Desk feed + notify; **"Convene War Room" as the executable one-click action**; opt-in beat (default OFF); manual `/sweep/` endpoint.
- **Deferred to v2 (documented):** the full M14 *agentic tool-loop* investigation (v1 uses a single structured call); executable "Revise coverage" / "Open thesis" actions (surfaced as suggestions; revise needs a captured `Snapshot`); auto-execution (L3 agency).

**Conventions:** identical to F1-F3 (Docker; `-p ws-since-replay`; `-u 1000:1000` for makemigrations + `-e RUFF_CACHE_DIR=/tmp/ruff` for ruff; frontend one-off `docker run`; serializer Meta `ClassVar`; DRF null → `JsonResponse`; commit locally + trailer; `run_structured` patched in tests; worker/beat not running in test stack — beat task is unit-tested).

---

## File structure

**Create (`backend/apps/desk/`):** `__init__.py`, `apps.py` (label `desk`), `constants.py`, `models.py` (`DeskEntry`), `migrations/__init__.py`+`0001`, `services/__init__.py`, `services/universe.py`, `services/detectors.py`, `services/investigate.py`, `services/sweep.py`, `tasks.py`, `serializers.py`, `views.py`, `urls.py`, `tests/`.

**Modify:** `config/settings/base.py` (INSTALLED_APPS + `ANOMALY_SWEEP_ENABLED`), `config/urls.py`, `config/celery.py` (autodiscover + beat), `apps/observer/models.py` (+`("desk","Desk")` kind + migration), frontend `api/desk.ts`+`hooks/useDesk.ts`+`pages/DeskPage.tsx`+`components/DeskTile.tsx`+`router.tsx`+`Dashboard.tsx`+`useDashboard.ts`.

---

## Task 1: Scaffold `apps.desk` + opt-in flag

- [ ] **Step 1:** `backend/apps/desk/apps.py`:
```python
from django.apps import AppConfig


class DeskConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.desk"
    label = "desk"
```

- [ ] **Step 2:** `backend/apps/desk/constants.py`:
```python
"""Anomaly-sweep parameters."""

TOP_K = 3  # max investigations originated per sweep
COOLDOWN_HOURS = 12  # don't re-investigate the same (ticker, anomaly_type) within this window
DAILY_ORIGINATION_CAP = 12  # max DeskEntry investigations per day (cost backstop)

# Price/technical thresholds
GAP_PCT = 3.0
PCT_CHANGE = 5.0
NEAR_52W_PCT = 2.0

# Coverage hygiene
COVERAGE_STALE_DAYS = 14
COVERAGE_MOVE_PCT = 8.0  # covered name moved this much since last revision -> stale
EARNINGS_WITHIN_DAYS = 3
```

- [ ] **Step 3:** `backend/apps/desk/urls.py`:
```python
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
# registered in Task 9
urlpatterns = router.urls
```
plus empty `__init__.py`, `migrations/__init__.py`, `services/__init__.py`, `tests/__init__.py`.

- [ ] **Step 4:** wire `"apps.desk",` into `INSTALLED_APPS`; add `ANOMALY_SWEEP_ENABLED = env.bool("ANOMALY_SWEEP_ENABLED", default=False)` to `base.py` (match the file's env pattern — if it uses `os.environ`, use `os.environ.get("ANOMALY_SWEEP_ENABLED", "") == "1"`); add `path("api/desk/", include("apps.desk.urls")),` before generic `/api/`; add `"apps.desk",` to `autodiscover_tasks([...])`.

- [ ] **Step 5:** `docker compose -p ws-since-replay exec -T web python manage.py check` → no issues.
- [ ] **Step 6:** commit `feat(desk): scaffold apps.desk + ANOMALY_SWEEP_ENABLED flag (M15 F4)`.

---

## Task 2: `DeskEntry` model

- [ ] **Step 1: failing test** `backend/apps/desk/tests/test_model.py`:
```python
import pytest

from apps.desk.models import DeskEntry

pytestmark = pytest.mark.django_db


def test_create_and_defaults():
    e = DeskEntry.objects.create(anomaly_type="regime_change", severity=2.0, evidence={"x": 1})
    assert e.status == "new"
    assert e.ticker == ""
    assert "regime_change" in str(e)
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `backend/apps/desk/models.py`:
```python
from __future__ import annotations

from typing import ClassVar

from django.db import models


class DeskEntry(models.Model):
    STATUS_CHOICES: ClassVar = [("new", "New"), ("acted", "Acted"), ("dismissed", "Dismissed")]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    anomaly_type = models.CharField(max_length=32, db_index=True)
    ticker = models.CharField(max_length=16, blank=True, default="", db_index=True)  # "" = book-wide
    severity = models.FloatField(default=0.0)
    evidence = models.JSONField(default=dict)
    finding = models.TextField(blank=True, default="")
    suggested_actions = models.JSONField(default=list)  # [{"type","label","params"}]
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="new", db_index=True)
    warroom_run = models.ForeignKey("warroom.WarRoomRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["ticker", "anomaly_type", "-created_at"])]

    def __str__(self) -> str:
        return f"DeskEntry({self.anomaly_type} {self.ticker or 'book'})"
```

- [ ] **Step 4:** `makemigrations desk` (`-u 1000:1000`); confirm `dan`-owned.
- [ ] **Step 5:** run → PASS.
- [ ] **Step 6:** commit `feat(desk): DeskEntry model (M15 F4)`.

---

## Task 3: Universe builder

- [ ] **Step 1: failing test** `backend/apps/desk/tests/test_universe.py`:
```python
import pytest

from apps.coverage.models import CoverageNote
from apps.desk.services.universe import build_universe
from apps.thesis.models import Thesis

pytestmark = pytest.mark.django_db


def test_universe_unions_sources():
    Thesis.objects.create(title="t", ticker="nvda", direction="bullish", conviction=3, status="open")
    CoverageNote.objects.create(ticker="AMD", stance="bull", conviction=3)
    uni = build_universe()
    assert "NVDA" in uni and "AMD" in uni  # upper-cased, de-duped
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `backend/apps/desk/services/universe.py`:
```python
"""The set of tickers the sweep cares about: watchlist + covered + open theses +
open positions. Never raises; a failing source contributes nothing."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def build_universe() -> list[str]:
    tickers: set[str] = set()

    def _safe(fn):
        try:
            for t in fn():
                if t:
                    tickers.add(t.upper())
        except Exception:
            log.warning("desk.universe.source_failed", exc_info=True)

    _safe(lambda: __import__("apps.profiles.models", fromlist=["WatchlistSymbol"]).WatchlistSymbol.objects.values_list("ticker", flat=True))
    _safe(lambda: __import__("apps.coverage.models", fromlist=["CoverageNote"]).CoverageNote.objects.values_list("ticker", flat=True))
    _safe(lambda: __import__("apps.thesis.models", fromlist=["Thesis"]).Thesis.objects.filter(status="open").values_list("ticker", flat=True))
    _safe(lambda: __import__("apps.portfolio.models", fromlist=["Position"]).Position.objects.filter(status="open").values_list("ticker", flat=True))
    return sorted(tickers)
```

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): universe builder (M15 F4)`.

---

## Task 4: Detector registry (4 buckets)

- [ ] **Step 1: failing test** `backend/apps/desk/tests/test_detectors.py`:
```python
import pytest
from django.utils import timezone

from apps.book.models import BookSnapshot
from apps.desk.services import detectors as D
from apps.market.models import OHLCBar
from apps.regime.models import RegimeReading

pytestmark = pytest.mark.django_db


def test_price_detector_flags_big_move():
    base = timezone.now()
    # prev close 100, today open 100, today close 110 -> +10% pct_change
    OHLCBar.objects.create(ticker="NVDA", timeframe="1d", open=100, high=100, low=100, close=100, volume=1, ts=base - timezone.timedelta(days=1))
    OHLCBar.objects.create(ticker="NVDA", timeframe="1d", open=100, high=110, low=100, close=110, volume=1, ts=base)
    cands = D.detect_price(["NVDA"])
    assert any(c["anomaly_type"] == "price_move" and c["ticker"] == "NVDA" for c in cands)


def test_regime_change_detector():
    RegimeReading.objects.create(composite="Risk-On", axes={})
    RegimeReading.objects.create(composite="Risk-Off", axes={})
    cands = D.detect_regime_change()
    assert cands and cands[0]["anomaly_type"] == "regime_change"


def test_regime_no_change_no_candidate():
    RegimeReading.objects.create(composite="Risk-On", axes={})
    RegimeReading.objects.create(composite="Risk-On", axes={})
    assert D.detect_regime_change() == []


def test_book_deterioration_detector():
    BookSnapshot.objects.create(as_of_date=timezone.now().date() - timezone.timedelta(days=1),
                                concentration={"hhi": 0.2}, regime_fit={"alignment": "aligned"})
    BookSnapshot.objects.create(as_of_date=timezone.now().date(),
                                concentration={"hhi": 0.5}, regime_fit={"alignment": "misaligned"})
    cands = D.detect_book()
    assert cands and cands[0]["anomaly_type"] == "book_deterioration"


def test_run_detectors_aggregates(monkeypatch):
    monkeypatch.setattr(D, "detect_price", lambda uni: [{"anomaly_type": "price_move", "ticker": "X", "severity": 5.0, "evidence": {}}])
    monkeypatch.setattr(D, "detect_options", lambda uni: [])
    monkeypatch.setattr(D, "detect_regime_change", lambda: [])
    monkeypatch.setattr(D, "detect_book", lambda: [])
    monkeypatch.setattr(D, "detect_coverage_stale", lambda uni: [])
    out = D.run_detectors(["X"])
    assert len(out) == 1 and out[0]["ticker"] == "X"
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `backend/apps/desk/services/detectors.py`:
```python
"""Deterministic anomaly detectors over existing data + services. Each returns a
list of candidate dicts {anomaly_type, ticker, severity, evidence}. Best-effort;
a failing detector contributes nothing. Composes F1 (regime) + F2 (book)."""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.desk import constants as C

log = logging.getLogger(__name__)


def _daily(ticker: str, n: int) -> list[float]:
    from apps.market.models import OHLCBar

    rows = list(
        OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d")
        .order_by("-ts")
        .values_list("close", flat=True)[:n]
    )
    return [float(c) for c in reversed(rows)]


def detect_price(universe: list[str]) -> list[dict]:
    out = []
    for t in universe:
        try:
            closes = _daily(t, 2)
            if len(closes) < 2 or not closes[-2]:
                continue
            pct = (closes[-1] / closes[-2] - 1.0) * 100.0
            if abs(pct) >= C.PCT_CHANGE:
                out.append({"anomaly_type": "price_move", "ticker": t.upper(),
                            "severity": abs(pct), "evidence": {"pct_change": round(pct, 2)}})
        except Exception:
            log.warning("desk.detect_price.failed t=%s", t, exc_info=True)
    return out


def detect_options(universe: list[str]) -> list[dict]:
    from apps.analytics.services.unusual_options import unusual_options

    now = timezone.now()
    out = []
    for t in universe:
        try:
            lines = unusual_options(ticker=t.upper(), at=now, top_n=5)
            if lines:
                top = max(lines, key=lambda x: x.get("score", 0))
                out.append({"anomaly_type": "unusual_options", "ticker": t.upper(),
                            "severity": float(top.get("score", 0)), "evidence": {"line": top}})
        except Exception:
            log.warning("desk.detect_options.failed t=%s", t, exc_info=True)
    return out


def detect_regime_change() -> list[dict]:
    from apps.regime.models import RegimeReading

    last2 = list(RegimeReading.objects.order_by("-created_at")[:2])
    if len(last2) == 2 and last2[0].composite != last2[1].composite:
        return [{"anomaly_type": "regime_change", "ticker": "", "severity": 10.0,
                 "evidence": {"from": last2[1].composite, "to": last2[0].composite}}]
    return []


def detect_book() -> list[dict]:
    from apps.book.models import BookSnapshot

    last2 = list(BookSnapshot.objects.order_by("-created_at")[:2])
    if len(last2) < 2:
        return []
    cur, prev = last2[0], last2[1]
    hhi_jump = (cur.concentration or {}).get("hhi", 0) - (prev.concentration or {}).get("hhi", 0)
    newly_misaligned = (cur.regime_fit or {}).get("alignment") == "misaligned" and (prev.regime_fit or {}).get("alignment") != "misaligned"
    if hhi_jump >= 0.1 or newly_misaligned:
        return [{"anomaly_type": "book_deterioration", "ticker": "", "severity": 8.0,
                 "evidence": {"hhi_jump": round(hhi_jump, 3), "newly_misaligned": newly_misaligned}}]
    return []


def detect_coverage_stale(universe: list[str]) -> list[dict]:
    from apps.coverage.models import CoverageNote

    cutoff = timezone.now() - timezone.timedelta(days=C.COVERAGE_STALE_DAYS)
    out = []
    for note in CoverageNote.objects.filter(updated_at__lt=cutoff):
        closes = _daily(note.ticker, 11)
        if len(closes) >= 11 and closes[0]:
            move = abs(closes[-1] / closes[0] - 1.0) * 100.0
            if move >= C.COVERAGE_MOVE_PCT:
                out.append({"anomaly_type": "coverage_stale", "ticker": note.ticker.upper(),
                            "severity": move, "evidence": {"move_pct": round(move, 1)}})
    return out


_DETECTORS_TICKER = (detect_price, detect_options, detect_coverage_stale)
_DETECTORS_GLOBAL = (detect_regime_change, detect_book)


def run_detectors(universe: list[str]) -> list[dict]:
    out: list[dict] = []
    for fn in _DETECTORS_TICKER:
        try:
            out.extend(fn(universe))
        except Exception:
            log.warning("desk.detector_failed %s", fn.__name__, exc_info=True)
    for fn in _DETECTORS_GLOBAL:
        try:
            out.extend(fn())
        except Exception:
            log.warning("desk.detector_failed %s", fn.__name__, exc_info=True)
    return out
```
NOTE: `run_detectors` calls the module-level names so the `test_run_detectors_aggregates` monkeypatches work — call them via the module (they're referenced through the tuples built at import, so for patchability ALSO support direct calls). To make monkeypatch work, change `run_detectors` to call `D.detect_*` by attribute: replace the tuples with explicit calls inside `run_detectors`:
```python
def run_detectors(universe: list[str]) -> list[dict]:
    import apps.desk.services.detectors as self_mod
    out: list[dict] = []
    for name in ("detect_price", "detect_options", "detect_coverage_stale"):
        try:
            out.extend(getattr(self_mod, name)(universe))
        except Exception:
            log.warning("desk.detector_failed %s", name, exc_info=True)
    for name in ("detect_regime_change", "detect_book"):
        try:
            out.extend(getattr(self_mod, name)())
        except Exception:
            log.warning("desk.detector_failed %s", name, exc_info=True)
    return out
```
(Use this attribute-lookup version so the monkeypatched functions are picked up. Delete the `_DETECTORS_*` tuples.)

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): detector registry — price/options/regime/book/coverage (M15 F4)`.

---

## Task 5: Scoring + cooldown

- [ ] **Step 1: failing test** `backend/apps/desk/tests/test_scoring.py`:
```python
import pytest

from apps.desk.models import DeskEntry
from apps.desk.services.scoring import in_cooldown, rank

pytestmark = pytest.mark.django_db


def test_rank_orders_by_severity():
    cands = [{"anomaly_type": "a", "ticker": "X", "severity": 1.0, "evidence": {}},
             {"anomaly_type": "b", "ticker": "Y", "severity": 9.0, "evidence": {}}]
    ranked = rank(cands)
    assert ranked[0]["ticker"] == "Y"


def test_cooldown_blocks_recent_same_key():
    DeskEntry.objects.create(anomaly_type="price_move", ticker="X", severity=5.0)
    assert in_cooldown("price_move", "X") is True
    assert in_cooldown("price_move", "Z") is False
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `backend/apps/desk/services/scoring.py`:
```python
from __future__ import annotations

from django.utils import timezone

from apps.desk import constants as C


def rank(candidates: list[dict]) -> list[dict]:
    """Highest severity first. (Severity already folds in magnitude; 'how much you
    care' weighting is a v2 refinement.)"""
    return sorted(candidates, key=lambda c: c.get("severity", 0.0), reverse=True)


def in_cooldown(anomaly_type: str, ticker: str) -> bool:
    from apps.desk.models import DeskEntry

    cutoff = timezone.now() - timezone.timedelta(hours=C.COOLDOWN_HOURS)
    return DeskEntry.objects.filter(
        anomaly_type=anomaly_type, ticker=(ticker or ""), created_at__gte=cutoff
    ).exists()
```

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): anomaly scoring + (ticker,type) cooldown (M15 F4)`.

---

## Task 6: Investigation (synchronous)

- [ ] **Step 1: failing test** `backend/apps/desk/tests/test_investigate.py`:
```python
import pytest

from apps.desk.services import investigate as I

pytestmark = pytest.mark.django_db

CAND = {"anomaly_type": "price_move", "ticker": "NVDA", "severity": 8.0, "evidence": {"pct_change": 8.0}}


def test_no_key_returns_none():
    assert I.investigate(CAND) is None


def test_investigate_returns_finding(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(provider="claude", _api_key={"k": "sk"}, default_model="claude-opus-4-8")

    class _F:
        summary = "NVDA gapped on capex headlines."
        implication = "Watch the breakout retest."
        suggested_actions = ["Convene a War Room on NVDA"]

    monkeypatch.setattr(I, "run_structured", lambda **kw: _F())
    monkeypatch.setattr(I, "check_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(I, "check_monthly_cap", lambda *a, **k: None)
    out = I.investigate(CAND)
    assert out["finding"].startswith("NVDA")
    assert out["suggested_actions"]
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `backend/apps/desk/services/investigate.py`:
```python
"""Synchronous per-anomaly investigation via run_structured (Claude-only v1). The
full M14 agentic tool-loop is a v2 upgrade. Returns {finding, suggested_actions}
or None when the AI can't run."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured

log = logging.getLogger(__name__)


class Finding(BaseModel):
    summary: str = Field(description="What the anomaly is, in one or two sentences.")
    implication: str = Field(description="What it implies for our view; observational only.")
    suggested_actions: list[str] = Field(default_factory=list, description="1-3 concrete next steps.")


def _prompt(cand: dict) -> str:
    return (
        f"An automated sweep flagged this anomaly:\n"
        f"- type: {cand.get('anomaly_type')}\n- ticker: {cand.get('ticker') or '(book-wide)'}\n"
        f"- evidence: {cand.get('evidence')}\n\n"
        "Investigate: what is it, what does it imply for our view, and what (if anything) "
        "is worth doing? Strictly observational; no buy/sell directive."
    )


def investigate(cand: dict) -> dict | None:
    from apps.secrets.models import ProviderConfig

    try:
        cfg = ProviderConfig.objects.filter(provider="claude").first()
        if cfg is None or not cfg.api_key:
            return None
        check_daily_cap("claude", cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap("claude", cap_usd=cfg.monthly_cost_cap_usd)
        f = run_structured(
            api_key=cfg.api_key, model=cfg.default_model or "claude-opus-4-8",
            system="", user=_prompt(cand), output_model=Finding, base_url=cfg.base_url or "",
        )
        finding = f"{f.summary} {f.implication}".strip()
        actions = [{"type": "suggestion", "label": s} for s in (f.suggested_actions or [])]
        # The cleanly-wired executable action: convene a War Room on this subject.
        subj = cand.get("ticker") or "the book"
        actions.insert(0, {"type": "convene_warroom", "label": f"Convene War Room on {subj}",
                           "params": {"free_prompt": f"Debate: {finding}"}})
        return {"finding": finding, "suggested_actions": actions}
    except CostCapExceededError as exc:
        log.warning("desk.investigate.cap_hit: %s", exc)
        return None
    except Exception:
        log.warning("desk.investigate.failed", exc_info=True)
        return None
```

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): synchronous anomaly investigation (M15 F4)`.

---

## Task 7: Sweep orchestration + notify + `desk` notification kind

- [ ] **Step 1:** add `("desk", "Desk")` to `Notification.KIND_CHOICES` in `apps/observer/models.py`; `makemigrations observer` (`-u 1000:1000`); confirm `dan`-owned.

- [ ] **Step 2: failing test** `backend/apps/desk/tests/test_sweep.py`:
```python
import pytest

from apps.desk.models import DeskEntry
from apps.desk.services import sweep as S

pytestmark = pytest.mark.django_db


def test_sweep_creates_entries_for_top_k(monkeypatch):
    monkeypatch.setattr(S, "build_universe", lambda: ["NVDA", "AMD"])
    monkeypatch.setattr(S, "run_detectors", lambda uni: [
        {"anomaly_type": "price_move", "ticker": "NVDA", "severity": 9.0, "evidence": {}},
        {"anomaly_type": "price_move", "ticker": "AMD", "severity": 1.0, "evidence": {}},
    ])
    monkeypatch.setattr(S, "investigate", lambda cand: {"finding": "f", "suggested_actions": []})
    n = S.run_sweep(top_k=1)
    assert n == 1
    assert DeskEntry.objects.count() == 1
    assert DeskEntry.objects.first().ticker == "NVDA"  # highest severity


def test_sweep_respects_cooldown(monkeypatch):
    DeskEntry.objects.create(anomaly_type="price_move", ticker="NVDA", severity=9.0)
    monkeypatch.setattr(S, "build_universe", lambda: ["NVDA"])
    monkeypatch.setattr(S, "run_detectors", lambda uni: [{"anomaly_type": "price_move", "ticker": "NVDA", "severity": 9.0, "evidence": {}}])
    monkeypatch.setattr(S, "investigate", lambda cand: {"finding": "f", "suggested_actions": []})
    n = S.run_sweep(top_k=3)
    assert n == 0  # cooled down
```

- [ ] **Step 2b:** run → FAIL.

- [ ] **Step 3:** `backend/apps/desk/services/sweep.py`:
```python
"""Orchestrate one sweep: detect -> rank -> cooldown -> top-K -> investigate ->
persist DeskEntry + notify. Never raises out of the loop."""

from __future__ import annotations

import logging

from apps.desk import constants as C
from apps.desk.models import DeskEntry
from apps.desk.services.detectors import run_detectors
from apps.desk.services.investigate import investigate
from apps.desk.services.scoring import in_cooldown, rank
from apps.desk.services.universe import build_universe

log = logging.getLogger(__name__)


def _notify(entry: DeskEntry) -> None:
    from apps.observer.services.notifications import notify

    notify(user_id=None, kind="desk", title=f"Desk: {entry.anomaly_type} {entry.ticker or 'book'}",
           body=entry.finding[:200], link="/desk", meta={"entry_id": entry.id})


def run_sweep(top_k: int = C.TOP_K) -> int:
    universe = build_universe()
    candidates = rank(run_detectors(universe))
    created = 0
    dropped = 0
    for cand in candidates:
        if created >= top_k:
            dropped += 1
            continue
        if in_cooldown(cand["anomaly_type"], cand.get("ticker", "")):
            continue
        result = investigate(cand)
        if result is None:
            continue  # AI unavailable — don't persist a finding-less entry
        entry = DeskEntry.objects.create(
            anomaly_type=cand["anomaly_type"], ticker=cand.get("ticker", "") or "",
            severity=cand.get("severity", 0.0), evidence=cand.get("evidence", {}),
            finding=result["finding"], suggested_actions=result["suggested_actions"],
        )
        try:
            _notify(entry)
        except Exception:
            log.warning("desk.notify_failed", exc_info=True)
        created += 1
    if dropped:
        log.info("desk.sweep dropped %d candidates beyond top_k=%d (no silent truncation)", dropped, top_k)
    return created
```

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): sweep orchestration + desk notifications (M15 F4)`.

---

## Task 8: Beat task + opt-in gate

- [ ] **Step 1: failing test** `backend/apps/desk/tests/test_tasks.py`:
```python
import pytest
from django.test import override_settings

from apps.desk import tasks

pytestmark = pytest.mark.django_db


@override_settings(ANOMALY_SWEEP_ENABLED=False)
def test_sweep_disabled_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, "run_sweep", lambda **k: calls.append(1))
    assert tasks.sweep.run() is None
    assert calls == []


@override_settings(ANOMALY_SWEEP_ENABLED=True)
def test_sweep_runs_when_enabled(monkeypatch):
    monkeypatch.setattr(tasks, "run_sweep", lambda **k: 2)
    assert tasks.sweep.run() == 2
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `backend/apps/desk/tasks.py`:
```python
from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from apps.desk.services.sweep import run_sweep

log = logging.getLogger(__name__)


@shared_task(name="desk.sweep")
def sweep() -> int | None:
    """Opt-in (ANOMALY_SWEEP_ENABLED, default OFF — autonomy that spends money)."""
    if not getattr(settings, "ANOMALY_SWEEP_ENABLED", False):
        log.info("desk.sweep: disabled (ANOMALY_SWEEP_ENABLED off)")
        return None
    return run_sweep()
```

- [ ] **Step 4:** run → PASS.

- [ ] **Step 5:** add to `config/celery.py` `beat_schedule`:
```python
    "desk-sweep": {
        "task": "desk.sweep",
        "schedule": crontab(minute="*/30"),  # opt-in gate is inside the task
    },
```
Then `manage.py check` → no issues.

- [ ] **Step 6:** commit `feat(desk): opt-in desk.sweep beat task (M15 F4)`.

---

## Task 9: API (feed + sweep + act + dismiss)

- [ ] **Step 1: failing test** `backend/apps/desk/tests/test_views.py`:
```python
import pytest
from rest_framework.test import APIClient

from apps.desk.models import DeskEntry

pytestmark = pytest.mark.django_db


def test_list_feed():
    DeskEntry.objects.create(anomaly_type="price_move", ticker="NVDA", severity=9.0, finding="f")
    rows = APIClient().get("/api/desk/").json()
    assert len(rows) == 1 and rows[0]["ticker"] == "NVDA"


def test_manual_sweep(monkeypatch):
    from apps.desk import views

    monkeypatch.setattr(views, "run_sweep", lambda **k: 3)
    resp = APIClient().post("/api/desk/sweep/")
    assert resp.status_code == 200 and resp.json()["created"] == 3


def test_dismiss():
    e = DeskEntry.objects.create(anomaly_type="x", ticker="Y", severity=1.0)
    resp = APIClient().post(f"/api/desk/{e.id}/dismiss/")
    assert resp.status_code == 200
    e.refresh_from_db()
    assert e.status == "dismissed"


def test_act_convenes_warroom(monkeypatch):
    from apps.desk import views
    from apps.threads.models import Thread
    from apps.warroom.models import WarRoomRun

    e = DeskEntry.objects.create(anomaly_type="price_move", ticker="NVDA", severity=9.0,
                                 finding="big move", suggested_actions=[{"type": "convene_warroom", "label": "Convene", "params": {"free_prompt": "Debate: big move"}}])

    def _fake_convene(**kwargs):
        th = Thread.objects.create(kind="warroom", title="t")
        return WarRoomRun.objects.create(thread=th, subject_kind="free", subject_label="x", confidence=0.5)

    monkeypatch.setattr(views, "convene", _fake_convene)
    resp = APIClient().post(f"/api/desk/{e.id}/act/", {"action": "convene_warroom"}, format="json")
    assert resp.status_code == 200
    e.refresh_from_db()
    assert e.status == "acted" and e.warroom_run_id is not None
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** implement.

`backend/apps/desk/serializers.py`:
```python
from typing import ClassVar

from rest_framework import serializers

from apps.desk.models import DeskEntry


class DeskEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = DeskEntry
        fields: ClassVar = [
            "id", "created_at", "anomaly_type", "ticker", "severity",
            "evidence", "finding", "suggested_actions", "status", "warroom_run_id",
        ]
        read_only_fields: ClassVar = fields
```

`backend/apps/desk/views.py`:
```python
from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.desk.models import DeskEntry
from apps.desk.serializers import DeskEntrySerializer
from apps.desk.services.sweep import run_sweep
from apps.warroom.services.convene import convene


class DeskViewSet(ReadOnlyModelViewSet):
    queryset = DeskEntry.objects.all()
    serializer_class = DeskEntrySerializer

    @action(detail=False, methods=["post"])
    def sweep(self, request: Request) -> Response:
        return Response({"created": run_sweep()})

    @action(detail=True, methods=["post"])
    def dismiss(self, request: Request, pk=None) -> Response:
        entry = self.get_object()
        entry.status = "dismissed"
        entry.save(update_fields=["status"])
        return Response(DeskEntrySerializer(entry).data)

    @action(detail=True, methods=["post"])
    def act(self, request: Request, pk=None) -> Response:
        entry = self.get_object()
        if request.data.get("action") == "convene_warroom":
            params = {}
            for a in entry.suggested_actions or []:
                if a.get("type") == "convene_warroom":
                    params = a.get("params", {})
                    break
            run = convene(free_prompt=params.get("free_prompt") or f"Debate: {entry.finding}")
            entry.warroom_run = run
            entry.status = "acted"
            entry.save(update_fields=["warroom_run", "status"])
        return Response(DeskEntrySerializer(entry).data)
```

`backend/apps/desk/urls.py` (replace):
```python
from rest_framework.routers import DefaultRouter

from apps.desk.views import DeskViewSet

router = DefaultRouter()
router.register("", DeskViewSet, basename="desk")
urlpatterns = router.urls
```
This maps `GET /api/desk/`, `POST /api/desk/sweep/`, `POST /api/desk/:id/dismiss/`, `POST /api/desk/:id/act/`.

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): feed + sweep + act + dismiss API (M15 F4)`.

---

## Task 10: Frontend API client + hook

- [ ] **Step 1: failing test** `frontend/src/__tests__/useDesk.test.tsx`:
```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import { useDeskFeed } from "@/hooks/useDesk";
import { hookWrapper } from "./testUtils";

describe("useDeskFeed", () => {
  it("lists entries", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      { id: 1, created_at: "x", anomaly_type: "price_move", ticker: "NVDA", severity: 9, evidence: {}, finding: "big move", suggested_actions: [], status: "new", warroom_run_id: null },
    ]);
    const { result } = renderHook(() => useDeskFeed(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.data?.length).toBe(1));
  });
});
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `frontend/src/api/desk.ts`:
```ts
import { apiGet, apiPost } from "@/api/client";

export interface DeskAction { type: string; label: string; params?: Record<string, unknown> }
export interface DeskEntry {
  id: number;
  created_at: string;
  anomaly_type: string;
  ticker: string;
  severity: number;
  evidence: Record<string, unknown>;
  finding: string;
  suggested_actions: DeskAction[];
  status: "new" | "acted" | "dismissed";
  warroom_run_id: number | null;
}

export const fetchDeskFeed = () => apiGet<DeskEntry[]>("/api/desk/");
export const runDeskSweep = () => apiPost<{ created: number }>("/api/desk/sweep/");
export const actDeskEntry = (id: number, actionType: string) =>
  apiPost<DeskEntry>(`/api/desk/${id}/act/`, { action: actionType });
export const dismissDeskEntry = (id: number) => apiPost<DeskEntry>(`/api/desk/${id}/dismiss/`);
```

`frontend/src/hooks/useDesk.ts`:
```ts
import { useMutation, useQuery } from "@tanstack/react-query";

import { actDeskEntry, dismissDeskEntry, fetchDeskFeed, runDeskSweep } from "@/api/desk";

export const useDeskFeed = () => useQuery({ queryKey: ["desk", "feed"], queryFn: fetchDeskFeed });
export const useRunDeskSweep = () => useMutation({ mutationFn: runDeskSweep });
export const useActDeskEntry = () =>
  useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => actDeskEntry(id, action) });
export const useDismissDeskEntry = () => useMutation({ mutationFn: dismissDeskEntry });
```

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): frontend api client + hooks (M15 F4)`.

---

## Task 11: `/desk` feed page + route

- [ ] **Step 1: failing test** `frontend/src/__tests__/DeskPage.test.tsx`:
```tsx
import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import DeskPage from "@/pages/DeskPage";
import { renderWithProviders } from "./testUtils";

describe("DeskPage", () => {
  it("renders findings + empty state", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      { id: 1, created_at: "2026-06-01T12:00:00Z", anomaly_type: "price_move", ticker: "NVDA", severity: 9, evidence: {}, finding: "NVDA gapped on capex.", suggested_actions: [{ type: "convene_warroom", label: "Convene War Room on NVDA" }], status: "new", warroom_run_id: null },
    ]);
    renderWithProviders(<DeskPage />);
    await waitFor(() => expect(screen.getByText(/NVDA gapped on capex/)).toBeInTheDocument());
    expect(screen.getByText(/Convene War Room on NVDA/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `frontend/src/pages/DeskPage.tsx` (verify Skeleton/EmptyState API as in F1/F2):
```tsx
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { useActDeskEntry, useDeskFeed, useDismissDeskEntry, useRunDeskSweep } from "@/hooks/useDesk";

export default function DeskPage() {
  const { data: entries = [], isLoading, refetch } = useDeskFeed();
  const sweep = useRunDeskSweep();
  const act = useActDeskEntry();
  const dismiss = useDismissDeskEntry();

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">The Desk</h1>
        <button className="rounded border border-rule px-3 py-1 text-sm hover:bg-ink/5 disabled:opacity-50"
                onClick={async () => { await sweep.mutateAsync(); refetch(); }} disabled={sweep.isPending}>
          {sweep.isPending ? "Sweeping…" : "Run sweep"}
        </button>
      </div>
      <p className="mt-1 text-sm text-ink/70">What the analyst flagged on its own — anomalies it investigated.</p>

      {isLoading ? (
        <Skeleton where="desk" />
      ) : entries.length === 0 ? (
        <EmptyState title="Nothing flagged yet" body="The sweep has not surfaced any anomalies. Run a sweep or enable the scheduled sweep." />
      ) : (
        <ul className="mt-4 divide-y divide-rule">
          {entries.map((e) => (
            <li key={e.id} className="py-4">
              <div className="flex justify-between text-sm">
                <span className="font-medium">{e.anomaly_type} · {e.ticker || "book"}</span>
                <span className="text-ink/50">{e.status}</span>
              </div>
              <p className="mt-1 text-sm text-ink/80">{e.finding}</p>
              {e.status === "new" && (
                <div className="mt-2 flex gap-2">
                  {e.suggested_actions.some((a) => a.type === "convene_warroom") && (
                    <button className="rounded border border-rule px-2 py-1 text-xs hover:bg-ink/5"
                            onClick={async () => { await act.mutateAsync({ id: e.id, action: "convene_warroom" }); refetch(); }}>
                      {e.suggested_actions.find((a) => a.type === "convene_warroom")?.label ?? "Convene War Room"}
                    </button>
                  )}
                  <button className="rounded border border-rule px-2 py-1 text-xs text-ink/60 hover:bg-ink/5"
                          onClick={async () => { await dismiss.mutateAsync(e.id); refetch(); }}>
                    Dismiss
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 4:** route in `router.tsx`: `{ path: "desk", element: <DeskPage />, handle: { crumb: "Desk" } },` + import.
- [ ] **Step 5:** run → PASS.
- [ ] **Step 6:** commit `feat(desk): /desk feed page + route (M15 F4)`.

---

## Task 12: Dashboard desk tile + section

- [ ] **Step 1 (backend):** add `_desk_section()` to `apps/dashboard/views.py` returning `{"unread": <count of status='new'>, "latest": <newest finding or None>}` with default `{"unread": 0, "latest": None}`; add `"desk": _safe(_desk_section, {"unread": 0, "latest": None})`. Add `apps/dashboard/tests/test_dashboard_desk.py` (default + populated) and run `pytest apps/dashboard -q`.

- [ ] **Step 2 (frontend test)** `frontend/src/__tests__/DeskTile.test.tsx`:
```tsx
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DeskTile } from "@/components/DeskTile";
import { renderWithProviders } from "./testUtils";

describe("DeskTile", () => {
  it("shows unread count", () => {
    renderWithProviders(<DeskTile desk={{ unread: 3, latest: "NVDA gapped" }} />);
    expect(screen.getByText(/3/)).toBeInTheDocument();
  });
  it("empty", () => {
    renderWithProviders(<DeskTile desk={{ unread: 0, latest: null }} />);
    expect(screen.getByText(/no new/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3:** `frontend/src/components/DeskTile.tsx`:
```tsx
import { Link } from "react-router-dom";

export interface DashboardDesk { unread: number; latest: string | null }

export function DeskTile({ desk }: { desk: DashboardDesk }) {
  return (
    <Link to="/desk" className="block rounded border border-rule p-4 hover:bg-ink/5">
      <div className="text-xs uppercase tracking-wide text-ink/60">The Desk</div>
      {desk.unread > 0 ? (
        <>
          <div className="mt-1 text-xl font-bold text-copper">{desk.unread} new</div>
          {desk.latest && <div className="mt-1 text-sm text-ink/70">{desk.latest}</div>}
        </>
      ) : (
        <div className="mt-1 text-sm text-ink/60">No new flags</div>
      )}
    </Link>
  );
}
```

- [ ] **Step 4:** wire into `Dashboard.tsx` + `useDashboard.ts` (`desk: DashboardDesk`) + the Dashboard test payload fixture (`desk: { unread: 0, latest: null }`). Mirror how regime/book tiles were added.
- [ ] **Step 5:** run DeskTile + Dashboard tests → PASS.
- [ ] **Step 6:** commit `feat(desk): dashboard desk tile + section (M15 F4)`.

---

## Final verification
- `docker compose -p ws-since-replay exec -T web pytest apps/desk apps/dashboard apps/observer -q`
- ruff check + format on apps/desk (`-u 1000:1000 -e RUFF_CACHE_DIR=/tmp/ruff`)
- Frontend: `docker run … vitest run src/__tests__/useDesk.test.tsx src/__tests__/DeskPage.test.tsx src/__tests__/DeskTile.test.tsx`

## Self-review (against the F4 spec section)
- Universe + 4 detector buckets (options/price/regime/book/coverage) → Tasks 3, 4. ✓ (breadth-divergence + earnings-proximity detectors are pluggable adds, noted; the registry supports them.)
- Scoring + (ticker,type) cooldown + top-K + no-silent-truncation log → Tasks 5, 7. ✓
- Investigation per top-K (synchronous v1) → Task 6. ✓
- Desk feed + notify; opt-in `ANOMALY_SWEEP_ENABLED` default OFF + daily cap constant → Tasks 1, 7, 8. ✓
- Agency L2: one-click **Convene War Room** executes (→ F3); revise-coverage/open-thesis surfaced as suggestions (execution deferred) → Tasks 6, 9. ✓ (documented deferral)
- API feed/sweep/act/dismiss → Task 9. ✓ · `/desk` page + Dashboard tile → Tasks 11, 12. ✓
- Composition: F1 regime-change detector + F2 book-deterioration detector + F3 convene-on-act → Tasks 4, 9. ✓
- Type consistency: `run_sweep(top_k=)`, `investigate(cand)→{finding,suggested_actions}|None`, `run_detectors(universe)`, `in_cooldown(type,ticker)` consistent across tasks; frontend `DeskEntry` matches the serializer.
- **Deferred (documented):** agentic tool-loop investigation; executable revise-coverage/open-thesis; daily-origination-cap enforcement (constant defined; wiring is a v2 refinement — v1 bounds via top_k + cooldown).
